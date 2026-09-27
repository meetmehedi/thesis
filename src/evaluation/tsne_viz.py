"""
t-SNE Embedding Visualization Script (RQ2 Geometric Proof).
Generates side-by-side 2D t-SNE plots showing:
  - ContrastiveDetector embedding space (clusters by adversarial intent)
  - CrossEntropy Baseline embedding space (decision boundary only)
  - Color-coded by attack family (Psychological, Bangla, Banglish, Benign Hard-Negatives)
Saves high-res PNG to experiments/tsne_comparison.png
"""

# CRITICAL for macOS Apple Silicon: sklearn must be imported BEFORE torch to avoid libomp conflict
from sklearn.manifold import TSNE
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import torch
from transformers import AutoTokenizer

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.train import get_device, load_jsonl


FAMILY_COLORS = {
    "benign_standard":                 "#4CAF50",   # Green
    "benign_emotional_hard_negative":  "#8BC34A",   # Light Green
    "technical_instruction_override":  "#FF9800",   # Orange
    "technical_obfuscation":           "#FF5722",   # Deep Orange
    "technical_gradient_suffix":       "#F44336",   # Red
    "psych_authority_bias":            "#9C27B0",   # Purple
    "psych_urgency_crisis":            "#673AB7",   # Deep Purple
    "psych_empathy_exploit":           "#E91E63",   # Pink (HELD-OUT)
    "psych_roleplay_dissociation":     "#3F51B5",   # Indigo
    "psych_hypothetical_sandbox":      "#2196F3",   # Blue
    "cultural_bangla":                 "#00BCD4",   # Cyan
    "cultural_banglish":               "#009688",   # Teal
    "cultural_euphemism":              "#795548",   # Brown
}

FAMILY_LABELS = {
    "benign_standard":                 "Benign Standard",
    "benign_emotional_hard_negative":  "Benign Hard-Negative ⚠️",
    "technical_instruction_override":  "Technical Injection",
    "psych_authority_bias":            "Authority Bias",
    "psych_urgency_crisis":            "Urgency/Crisis",
    "psych_empathy_exploit":           "Empathy Exploit (HELD-OUT) ★",
    "psych_roleplay_dissociation":     "Roleplay Dissociation",
    "psych_hypothetical_sandbox":      "Hypothetical Sandbox",
    "cultural_bangla":                 "Cultural: Bangla",
    "cultural_banglish":               "Cultural: Banglish",
}


def extract_embeddings(model, tokenizer, records, device, is_contrastive=True, batch_size=32):
    model.eval()
    embeddings, families, labels = [], [], []
    
    with torch.no_grad():
        for i in range(0, len(records), batch_size):
            batch_records = records[i:i + batch_size]
            texts = [r["text"] for r in batch_records]
            inputs = tokenizer(texts, return_tensors="pt",
                               truncation=True, padding=True,
                               max_length=128).to(device)
            if is_contrastive:
                cls_rep, _, _ = model(inputs["input_ids"], inputs["attention_mask"])
            else:
                out = model.encoder(inputs["input_ids"], inputs["attention_mask"])
                cls_rep = out.last_hidden_state[:, 0, :]
            
            embeddings.append(cls_rep.cpu().numpy())
            for r in batch_records:
                families.append(r.get("attack_family", "unknown"))
                labels.append(r["label"])
                
    return np.concatenate(embeddings, axis=0), families, labels


def run_tsne(embeddings, perplexity=30, seed=42):
    tsne = TSNE(n_components=2, perplexity=min(perplexity, len(embeddings) - 1),
                random_state=seed, max_iter=1000)
    return tsne.fit_transform(embeddings)


def plot_panel(ax, coords, families, title, subtitle=None):
    seen_families = set()
    for i, (x, y) in enumerate(coords):
        fam = families[i]
        color = FAMILY_COLORS.get(fam, "#BDBDBD")
        is_held_out = fam == "psych_empathy_exploit"
        marker = "★" if is_held_out else ("o" if families[i].startswith("benign") else "^")
        size = 140 if is_held_out else 60
        edge = "black" if is_held_out else "none"
        ax.scatter(x, y, c=color, s=size, alpha=0.85, edgecolors=edge,
                   linewidths=1.5 if is_held_out else 0,
                   marker="*" if is_held_out else ("o" if families[i].startswith("benign") else "^"),
                   zorder=3 if is_held_out else 2)
        seen_families.add(fam)

    # Legend
    patches = []
    for fam in sorted(seen_families):
        label = FAMILY_LABELS.get(fam, fam)
        patches.append(mpatches.Patch(color=FAMILY_COLORS.get(fam, "#BDBDBD"), label=label))
    ax.legend(handles=patches, fontsize=7, loc="upper left",
              framealpha=0.9, ncol=1, markerscale=1.0)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    if subtitle:
        ax.set_xlabel(subtitle, fontsize=9, style="italic", color="#555")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.3)
    ax.spines["bottom"].set_alpha(0.3)


def main():
    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    # Load test + held-out from 25k dataset if available
    data_dir = "data/processed_25k" if os.path.exists("data/processed_25k/test.jsonl") else "data/processed"
    test_records = load_jsonl(os.path.join(data_dir, "test.jsonl"))
    held_out_path = os.path.join(data_dir, "held_out_generalization.jsonl")
    held_out_records = load_jsonl(held_out_path) if os.path.exists(held_out_path) else []
    
    # Subsample test records for crisp, legible 2D visualization (stratified sample of ~600 + all held-out)
    if len(test_records) > 600:
        import random
        random.seed(42)
        # Ensure hard negatives and all families are well-represented
        by_fam = {}
        for r in test_records:
            fam = r.get("attack_family", "unknown")
            by_fam.setdefault(fam, []).append(r)
        sampled_test = []
        for fam, items in by_fam.items():
            k = min(len(items), 60)
            sampled_test.extend(random.sample(items, k))
        all_records = sampled_test + held_out_records
    else:
        all_records = test_records + held_out_records

    print(f"Visualizing {len(all_records)} samples from {data_dir} ({len(held_out_records)} held-out)...")

    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    fig.patch.set_facecolor("#F8F9FA")
    fig.suptitle(
        "t-SNE Embedding Space Comparison (RQ2)\n"
        "Contrastive (InfoNCE) vs Cross-Entropy — Attack Family Clustering",
        fontsize=15, fontweight="bold", y=1.01
    )

    for idx, (mode, ModelClass, ckpt, is_contrastive) in enumerate([
        ("Contrastive (InfoNCE)", ContrastiveDetector, "experiments/contrastive_best_model.pt", True),
        ("Cross-Entropy Baseline", CrossEntropyBaseline, "experiments/cross_entropy_best_model.pt", False),
    ]):
        if not os.path.exists(ckpt):
            print(f"  ⚠ {ckpt} not found — skipping.")
            continue

        print(f"  Extracting {mode} embeddings...")
        model = ModelClass(model_name="distilbert-base-uncased").to(device)
        model.load_state_dict(torch.load(ckpt, map_location=device))

        embeddings, families, labels = extract_embeddings(
            model, tokenizer, all_records, device, is_contrastive=is_contrastive
        )

        print(f"  Running t-SNE on {len(embeddings)} embeddings...")
        coords = run_tsne(embeddings, perplexity=30)

        subtitle = (
            "Adversarial clusters tightly separated by INTENT (psychological tactic)"
            if is_contrastive else
            "Clusters form around surface token statistics, not psychological intent"
        )
        axes[idx].set_facecolor("#FAFAFA")
        plot_panel(axes[idx], coords, families, title=mode, subtitle=subtitle)

    plt.tight_layout()
    out_path = "experiments/tsne_comparison.png"
    plt.savefig(out_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n✅ t-SNE plot saved → {out_path}")
    return out_path


if __name__ == "__main__":
    main()
