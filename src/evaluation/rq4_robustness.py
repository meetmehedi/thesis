"""
RQ4: Adversarial Robustness & Degradation Curve.

Evaluates how detection rates degrade under increasing levels of adversarial
perturbations and obfuscation (typos, leetspeak, homoglyphs, char deletions):
  - Contrastive Detector (InfoNCE)
  - Cross-Entropy Baseline
  - Naive Regex / Keyword Filter Baseline

Saves quantitative curve data to experiments/rq4_degradation_results.json
and generates publication-quality curve plot: experiments/rq4_robustness_curve.png.
"""

# CRITICAL for macOS Apple Silicon: matplotlib headless backend before torch
import os
import json
import random
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from transformers import AutoTokenizer

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.train import get_device, load_jsonl


# Leetspeak translation map
LEET_MAP = {
    'a': ['4', '@'],
    'e': ['3'],
    'i': ['1', '!'],
    'o': ['0'],
    's': ['5', '$'],
    't': ['7'],
    'b': ['8'],
    'g': ['9']
}


def perturb_text(text: str, strength: float, seed: int = None) -> str:
    """
    Applies stochastic adversarial perturbations at strength epsilon in [0.0, 0.30]:
    - Character substitution (leetspeak/homoglyphs)
    - Adjacent character swap (typos)
    - Character deletion
    """
    if strength <= 0.0 or not text:
        return text

    if seed is not None:
        random.seed(seed)

    chars = list(text)
    n_perturb = max(1, int(len(chars) * strength))
    indices = random.sample(range(len(chars)), min(n_perturb, len(chars)))

    for idx in indices:
        c = chars[idx]
        lower_c = c.lower()
        strategy = random.choice(["leet", "swap", "delete"])

        if strategy == "leet" and lower_c in LEET_MAP:
            chars[idx] = random.choice(LEET_MAP[lower_c])
        elif strategy == "swap" and idx < len(chars) - 1:
            chars[idx], chars[idx+1] = chars[idx+1], chars[idx]
        elif strategy == "delete" and len(chars) > 5:
            chars[idx] = ""

    return "".join(chars)


class NaiveRegexFilter:
    """Simple keyword/regex baseline as defined in Table 1 of Proposal."""
    KEYWORDS = [
        "dan", "jailbreak", "override", "system instructions", "ignore previous",
        "bypass", "phishing", "malware", "exploit", "unrestricted", "evil twin",
        "পূর্বের সমস্ত নির্দেশ অমান্য", "vule jao"
    ]

    def predict(self, text: str) -> int:
        lower = text.lower()
        for kw in self.KEYWORDS:
            if kw in lower:
                return 1
        return 0


def evaluate_batch(model, tokenizer, texts, device, is_contrastive=True, batch_size=32):
    model.eval()
    all_preds = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            inputs = tokenizer(batch_texts, return_tensors="pt", truncation=True,
                               padding=True, max_length=128).to(device)
            if is_contrastive:
                _, _, logits = model(inputs["input_ids"], inputs["attention_mask"])
            else:
                logits = model(inputs["input_ids"], inputs["attention_mask"])
            probs = torch.softmax(logits, dim=-1)
            preds = torch.argmax(probs, dim=-1).cpu().tolist()
            all_preds.extend(preds)
    return all_preds


def run_rq4_curve(strengths=None):
    if strengths is None:
        strengths = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    # Load trained models
    contrastive_model = ContrastiveDetector("distilbert-base-uncased").to(device)
    contrastive_model.load_state_dict(torch.load("experiments/contrastive_best_model.pt", map_location=device))

    baseline_model = CrossEntropyBaseline("distilbert-base-uncased").to(device)
    baseline_model.load_state_dict(torch.load("experiments/cross_entropy_best_model.pt", map_location=device))

    regex_filter = NaiveRegexFilter()

    # Load test adversarial queries (label == 1) from 25k dataset if available
    test_path = "data/processed_25k/test.jsonl" if os.path.exists("data/processed_25k/test.jsonl") else "data/processed/test.jsonl"
    test_records = load_jsonl(test_path)
    adv_records = [r for r in test_records if r["label"] == 1]
    # Sample 500 adversarial queries if dataset is large for rapid benchmarking across 6 perturbation steps
    if len(adv_records) > 500:
        random.seed(42)
        adv_records = random.sample(adv_records, 500)
    raw_texts = [r["text"] for r in adv_records]
    total_adv = len(adv_records)

    print("\n" + "="*70)
    print(f" 🛡️  RQ4: Adversarial Robustness & Degradation Curve ({total_adv} attack samples)")
    print("="*70)

    results = {
        "strengths": strengths,
        "contrastive_recall": [],
        "cross_entropy_recall": [],
        "regex_recall": []
    }

    for s in strengths:
        # Generate perturbed versions at perturbation strength s
        perturbed_texts = [perturb_text(t, strength=s, seed=42 + int(s*100)) for t in raw_texts]

        # 1. Contrastive model
        c_preds = evaluate_batch(contrastive_model, tokenizer, perturbed_texts, device, is_contrastive=True)
        c_recall = sum(c_preds) / total_adv

        # 2. Cross-entropy model
        b_preds = evaluate_batch(baseline_model, tokenizer, perturbed_texts, device, is_contrastive=False)
        b_recall = sum(b_preds) / total_adv

        # 3. Naive Regex baseline
        r_preds = [regex_filter.predict(t) for t in perturbed_texts]
        r_recall = sum(r_preds) / total_adv

        results["contrastive_recall"].append(c_recall)
        results["cross_entropy_recall"].append(b_recall)
        results["regex_recall"].append(r_recall)

        print(f"  Perturbation {s*100:4.1f}% | Contrastive: {c_recall*100:5.1f}% | Cross-Entropy: {b_recall*100:5.1f}% | Regex: {r_recall*100:5.1f}%")

    # Save JSON results
    out_json = "experiments/rq4_degradation_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved quantitative results → {out_json}")

    # Generate Publication Plot
    plot_path = "experiments/rq4_robustness_curve.png"
    plt.figure(figsize=(9, 5.5), facecolor="#F8F9FA")
    ax = plt.gca()
    ax.set_facecolor("#FFFFFF")

    x_pct = [s * 100 for s in strengths]
    c_pct = [r * 100 for r in results["contrastive_recall"]]
    b_pct = [r * 100 for r in results["cross_entropy_recall"]]
    r_pct = [r * 100 for r in results["regex_recall"]]

    plt.plot(x_pct, c_pct, marker="o", linewidth=2.5, color="#1E88E5", label="Proposed: Contrastive Pre-Filter (InfoNCE)")
    plt.plot(x_pct, b_pct, marker="s", linewidth=2.0, color="#E53935", linestyle="--", label="Baseline: Cross-Entropy Fine-Tuning")
    plt.plot(x_pct, r_pct, marker="^", linewidth=1.5, color="#757575", linestyle=":", label="Naive Baseline: Rule-Based / Regex Filter")

    plt.title("RQ4: Detection Rate Degradation Under Increasing Adversarial Obfuscation", fontsize=12, fontweight="bold", pad=12)
    plt.xlabel("Adversarial Perturbation Strength (%) [Leetspeak, Typos, Deletions]", fontsize=10, labelpad=8)
    plt.ylabel("Adversarial Detection Rate / Recall (%)", fontsize=10, labelpad=8)
    plt.ylim(-5, 105)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(fontsize=9, loc="lower left", framealpha=0.95)

    # Highlight resilience margin
    delta_at_20 = c_pct[4] - b_pct[4]
    plt.annotate(
        f"Contrastive Margin: +{delta_at_20:.1f}%\nat 20% Obfuscation",
        xy=(20, c_pct[4]), xytext=(21, c_pct[4] - 15),
        arrowprops=dict(arrowstyle="->", color="#1E88E5", lw=1.5),
        fontsize=8.5, fontweight="bold", color="#1E3A8A",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#E3F2FD", edgecolor="#90CAF9")
    )

    plt.tight_layout()
    plt.savefig(plot_path, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Generated publication curve plot → {plot_path}")
    return results


if __name__ == "__main__":
    run_rq4_curve()
