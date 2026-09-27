"""
Training Engine for LLM Prompt Injection & Jailbreak Pre-Filter:
Supports:
1. Contrastive Training (DistilBERT + InfoNCE Loss + Linear Head)
2. Cross-Entropy Baseline Training (DistilBERT + CrossEntropy)
3. Direct Evaluation on Test Set & Held-Out Psychological Generalization Set (RQ3)
"""

# CRITICAL for macOS Apple Silicon: sklearn must be imported BEFORE torch to avoid libomp deadlock
import sklearn
import sklearn.metrics
import os
import json
import argparse
import time
from typing import Dict, Any, List, Tuple
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.models.loss import SupervisedContrastiveLoss
from src.evaluation.metrics import (
    compute_classification_metrics,
    bootstrap_confidence_intervals,
    evaluate_by_family,
    profile_latency
)

def create_tensor_dataset(records: List[Dict[str, Any]], tokenizer, max_length: int = 96) -> Tuple[TensorDataset, List[Dict[str, Any]]]:
    texts = [r["text"] for r in records]
    encodings = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=max_length,
        return_tensors="pt"
    )
    labels = torch.tensor([r["label"] for r in records], dtype=torch.long)
    indices = torch.arange(len(records), dtype=torch.long)
    dataset = TensorDataset(encodings["input_ids"], encodings["attention_mask"], labels, indices)
    return dataset, records

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")

def evaluate_model(
    model: nn.Module,
    dataloader: DataLoader,
    records: List[Dict[str, Any]],
    device: torch.device,
    is_contrastive: bool = True
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[int], List[float]]:
    model.eval()
    all_true, all_pred, all_scores, all_indices = [], [], [], []

    with torch.no_grad():
        for input_ids, attention_mask, labels_t, indices_t in dataloader:
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)
            labels = labels_t.tolist()
            indices = indices_t.tolist()

            if is_contrastive:
                _, _, logits = model(input_ids, attention_mask)
            else:
                logits = model(input_ids, attention_mask)

            probs = torch.softmax(logits, dim=-1)
            preds = torch.argmax(probs, dim=-1).cpu().tolist()
            scores = probs[:, 1].cpu().tolist()

            all_true.extend(labels)
            all_pred.extend(preds)
            all_scores.extend(scores)
            all_indices.extend(indices)

    all_records = [records[i] for i in all_indices]
    metrics = compute_classification_metrics(all_true, all_pred, all_scores)
    return metrics, all_records, all_pred, all_scores

def train(
    mode: str = "contrastive",
    model_name: str = "distilbert-base-uncased",
    epochs: int = 3,
    batch_size: int = 64,
    eval_batch_size: int = 128,
    lr: float = 2e-5,
    seed: int = 42,
    data_dir: str = "data/processed_25k",
    save_dir: str = "experiments"
):
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    os.makedirs(save_dir, exist_ok=True)
    device = get_device()
    print(f"--- Starting Training [{mode.upper()}] on Device: {device} (Seed: {seed}) ---", flush=True)
    if not os.path.exists(os.path.join(data_dir, "train.jsonl")):
        data_dir = "data/processed"
    print(f"Using dataset from: {data_dir}", flush=True)

    # 1. Load Data
    train_records = load_jsonl(os.path.join(data_dir, "train.jsonl"))
    val_records = load_jsonl(os.path.join(data_dir, "val.jsonl"))
    test_records = load_jsonl(os.path.join(data_dir, "test.jsonl"))
    held_out_path = os.path.join(data_dir, "held_out_generalization.jsonl")
    held_out_records = load_jsonl(held_out_path) if os.path.exists(held_out_path) else []

    print(f"Loaded {len(train_records)} train, {len(val_records)} val, {len(test_records)} test samples.", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    train_ds, train_recs = create_tensor_dataset(train_records, tokenizer, max_length=96)
    val_ds, val_recs = create_tensor_dataset(val_records, tokenizer, max_length=96)
    test_ds, test_recs = create_tensor_dataset(test_records, tokenizer, max_length=96)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=eval_batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=eval_batch_size, shuffle=False)

    # 2. Setup Model & Loss
    if mode == "contrastive":
        model = ContrastiveDetector(model_name=model_name).to(device)
        contrastive_criterion = SupervisedContrastiveLoss(temperature=0.07)
        ce_criterion = nn.CrossEntropyLoss()
    else:
        model = CrossEntropyBaseline(model_name=model_name).to(device)
        ce_criterion = nn.CrossEntropyLoss()

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps)

    # 3. Training Loop
    import time
    best_f1 = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        start_time = time.time()

        for step, (input_ids, attention_mask, labels, _) in enumerate(train_loader):
            optimizer.zero_grad()
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)
            labels = labels.to(device)

            if mode == "contrastive":
                _, projected, logits = model(input_ids, attention_mask)
                loss_contrastive = contrastive_criterion(projected, labels)
                loss_ce = ce_criterion(logits, labels)
                loss = loss_contrastive + loss_ce
            else:
                logits = model(input_ids, attention_mask)
                loss = ce_criterion(logits, labels)

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

            if (step + 1) % 25 == 0 or (step + 1) == len(train_loader):
                elapsed = time.time() - start_time
                samples_per_sec = ((step + 1) * batch_size) / elapsed
                remaining_steps = len(train_loader) - (step + 1)
                eta_s = remaining_steps * (elapsed / (step + 1))
                print(f"  [Epoch {epoch}/{epochs}] Step {step+1:3d}/{len(train_loader)} | Loss: {loss.item():.4f} | Speed: {samples_per_sec:.1f} samples/s | ETA: {eta_s:.0f}s", flush=True)

        avg_loss = total_loss / len(train_loader)
        val_metrics, _, _, _ = evaluate_model(model, val_loader, val_recs, device, is_contrastive=(mode == "contrastive"))
        print(f"Epoch {epoch}/{epochs} | Train Loss: {avg_loss:.4f} | Val F1: {val_metrics['f1']:.4f} | Val AUROC: {val_metrics['auroc']:.4f} | Val FPR: {val_metrics['fpr']:.4f}", flush=True)

        if val_metrics["f1"] >= best_f1:
            best_f1 = val_metrics["f1"]
            torch.save(model.state_dict(), os.path.join(save_dir, f"{mode}_best_model.pt"))
            print(f"  --> Saved new best checkpoint to {save_dir}/{mode}_best_model.pt", flush=True)

    # 4. Final Evaluation on Test Set
    ckpt_path = os.path.join(save_dir, f"{mode}_best_model.pt")
    if os.path.exists(ckpt_path):
        model.load_state_dict(torch.load(ckpt_path, map_location=device))
    test_metrics, eval_test_recs, test_preds, test_scores = evaluate_model(model, test_loader, test_recs, device, is_contrastive=(mode == "contrastive"))

    # Bootstrapping CIs
    y_test_true = [r["label"] for r in test_recs]
    cis = bootstrap_confidence_intervals(y_test_true, test_preds, test_scores)
    print(f"Test Precision: {test_metrics['precision']:.4f} (95% CI: {cis.get('precision', (0,0))})")
    print(f"Test Recall:    {test_metrics['recall']:.4f} (95% CI: {cis.get('recall', (0,0))})")
    print(f"Test F1-Score:  {test_metrics['f1']:.4f} (95% CI: {cis.get('f1', (0,0))})")
    print(f"Test AUROC:     {test_metrics['auroc']:.4f} (95% CI: {cis.get('auroc', (0,0))})")
    print(f"Test FPR:       {test_metrics['fpr']:.4f}")

    # Family Breakdown (Psychological, Cultural, Hard-Negatives)
    family_breakdown = evaluate_by_family(test_recs, test_preds, test_scores)
    print("\n--- Breakdown by Attack Family & Human Factors ---")
    for fam, stats in family_breakdown.items():
        print(f"  • Family: {fam:30s} | Count: {stats['sample_count']:2d} | F1: {stats['f1']:.3f} | Recall: {stats['recall']:.3f} | FPR: {stats['fpr']:.3f}")

    # Latency Profile
    test_sample_texts = [r["text"] for r in test_records[:20]]
    latency_stats = profile_latency(model, tokenizer, test_sample_texts, device)
    print("\n--- Latency Profile (RQ6 Real-Time Pre-Filter) ---")
    print(f"  P50: {latency_stats['p50_ms']:.2f} ms | P95: {latency_stats['p95_ms']:.2f} ms | Mean: {latency_stats['mean_ms']:.2f} ms")

    # Save summary report
    summary = {
        "mode": mode,
        "test_metrics": test_metrics,
        "confidence_intervals": cis,
        "family_breakdown": family_breakdown,
        "latency_stats": latency_stats
    }
    with open(os.path.join(save_dir, f"{mode}_results.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, default="contrastive", choices=["contrastive", "cross_entropy"])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--eval_batch_size", type=int, default=128)
    parser.add_argument("--data_dir", type=str, default="data/processed_25k")
    args = parser.parse_args()

    train(
        mode=args.mode,
        epochs=args.epochs,
        batch_size=args.batch_size,
        eval_batch_size=args.eval_batch_size,
        data_dir=args.data_dir
    )
