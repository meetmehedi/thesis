"""
Training Engine for LLM Prompt Injection & Jailbreak Pre-Filter:
Supports:
1. Contrastive Training (DistilBERT + InfoNCE Loss + Linear Head)
2. Cross-Entropy Baseline Training (DistilBERT + CrossEntropy)
3. Direct Evaluation on Test Set & Held-Out Psychological Generalization Set (RQ3)
"""

import os
import json
import argparse
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
from typing import Dict, Any, List, Tuple

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.models.loss import SupervisedContrastiveLoss
from src.evaluation.metrics import (
    compute_classification_metrics,
    bootstrap_confidence_intervals,
    evaluate_by_family,
    profile_latency
)

class PromptDataset(Dataset):
    def __init__(self, records: List[Dict[str, Any]], tokenizer, max_length: int = 128):
        self.records = records
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        item = self.records[idx]
        encoding = self.tokenizer(
            item["text"],
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "label": torch.tensor(item["label"], dtype=torch.long),
            "idx": idx  # Store index; retrieve full record after batching
        }

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
    device: torch.device,
    is_contrastive: bool = True
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[int], List[float]]:
    model.eval()
    all_true, all_pred, all_scores, all_indices = [], [], [], []

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].cpu().tolist()
            indices = batch["idx"].cpu().tolist()

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

    # The full dataset is accessible via the DataLoader's dataset attribute
    dataset = dataloader.dataset
    all_records = [dataset.records[i] for i in all_indices]
    metrics = compute_classification_metrics(all_true, all_pred, all_scores)
    return metrics, all_records, all_pred, all_scores

def train(
    mode: str = "contrastive",
    model_name: str = "distilbert-base-uncased",
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 2e-5,
    save_dir: str = "experiments"
):
    os.makedirs(save_dir, exist_ok=True)
    device = get_device()
    print(f"--- Starting Training [{mode.upper()}] on Device: {device} ---")

    # 1. Load Data
    train_records = load_jsonl("data/processed/train.jsonl")
    val_records = load_jsonl("data/processed/val.jsonl")
    test_records = load_jsonl("data/processed/test.jsonl")
    held_out_records = load_jsonl("data/processed/held_out_generalization.jsonl")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    train_ds = PromptDataset(train_records, tokenizer)
    val_ds = PromptDataset(val_records, tokenizer)
    test_ds = PromptDataset(test_records, tokenizer)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

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
    best_f1 = 0.0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0

        for batch in train_loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)

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

        avg_loss = total_loss / len(train_loader)
        val_metrics, _, _, _ = evaluate_model(model, val_loader, device, is_contrastive=(mode == "contrastive"))
        print(f"Epoch {epoch}/{epochs} | Train Loss: {avg_loss:.4f} | Val F1: {val_metrics['f1']:.4f} | Val AUROC: {val_metrics['auroc']:.4f} | Val FPR: {val_metrics['fpr']:.4f}")

        if val_metrics["f1"] >= best_f1:
            best_f1 = val_metrics["f1"]
            torch.save(model.state_dict(), os.path.join(save_dir, f"{mode}_best_model.pt"))

    # 4. Final Evaluation on Test Set
    ckpt_path = os.path.join(save_dir, f"{mode}_best_model.pt")
    if os.path.exists(ckpt_path):
        model.load_state_dict(torch.load(ckpt_path, map_location=device))
    test_metrics, test_recs, test_preds, test_scores = evaluate_model(model, test_loader, device, is_contrastive=(mode == "contrastive"))

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
    parser.add_argument("--batch_size", type=int, default=16)
    args = parser.parse_args()

    train(mode=args.mode, epochs=args.epochs, batch_size=args.batch_size)
