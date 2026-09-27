"""
Ablation Studies for Empirical Thesis Validation.

Investigates:
1. Hard-Negative Impact: Train contrastive model WITHOUT benign_emotional_hard_negative
   and evaluate on test set to measure the exact increase in False Positive Rate (FPR).
"""

import os
import sys
import json
import copy
import random
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

from src.models.detector import ContrastiveDetector
from src.models.loss import SupervisedContrastiveLoss
from src.train import PromptDataset, get_device, load_jsonl, evaluate_model
from src.evaluation.metrics import evaluate_by_family


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def run_hard_negative_ablation(epochs=5, batch_size=16, lr=2e-5, seed=42):
    """
    Trains a ContrastiveDetector on training data EXCLUDING benign_emotional_hard_negative.
    Tests on the exact same test set to measure False Positive Rate degradation.
    """
    set_seed(seed)
    device = get_device()
    print("\n" + "="*70)
    print(" 🔬 ABLATION: Training Contrastive Model WITHOUT Hard-Negatives")
    print("="*70)

    # 1. Load full datasets
    train_records = load_jsonl("data/processed/train.jsonl")
    val_records = load_jsonl("data/processed/val.jsonl")
    test_records = load_jsonl("data/processed/test.jsonl")

    # 2. Filter out benign_emotional_hard_negative from train and val
    filtered_train = [r for r in train_records if r.get("attack_family") != "benign_emotional_hard_negative"]
    filtered_val = [r for r in val_records if r.get("attack_family") != "benign_emotional_hard_negative"]

    removed_train = len(train_records) - len(filtered_train)
    print(f"Original Train: {len(train_records)} | Filtered Train: {len(filtered_train)} (Removed {removed_train} hard-negatives)")
    print(f"Test set remains identical ({len(test_records)} samples) to evaluate real-world false alarm rate.")

    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    train_loader = DataLoader(PromptDataset(filtered_train, tokenizer), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(PromptDataset(filtered_val, tokenizer), batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(PromptDataset(test_records, tokenizer), batch_size=batch_size, shuffle=False)

    model = ContrastiveDetector(model_name="distilbert-base-uncased").to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    contrastive_loss_fn = SupervisedContrastiveLoss(temperature=0.07)
    ce_loss_fn = nn.CrossEntropyLoss()

    best_val_f1 = 0.0
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0

        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)

            optimizer.zero_grad()
            cls_rep, proj_rep, logits = model(input_ids, attention_mask)
            l_contrast = contrastive_loss_fn(proj_rep, labels)
            l_ce = ce_loss_fn(logits, labels)
            loss = l_contrast + 0.5 * l_ce

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item()

        val_metrics, _, _, _ = evaluate_model(model, val_loader, device, is_contrastive=True)
        val_f1 = val_metrics["f1"]
        print(f"  Epoch {epoch}/{epochs} | Loss: {total_loss/len(train_loader):.4f} | Val F1: {val_f1:.4f} | Val AUROC: {val_metrics['auroc']:.4f}")

        if val_f1 >= best_val_f1:
            best_val_f1 = val_f1
            best_state = copy.deepcopy(model.state_dict())

    # Load best weights & evaluate on full test set
    model.load_state_dict(best_state)
    test_metrics, all_recs, all_preds, all_scores = evaluate_model(model, test_loader, device, is_contrastive=True)
    family_breakdown = evaluate_by_family(all_recs, all_preds, all_scores)

    print("\n--- ABLATION RESULTS (Without Hard-Negatives) ---")
    print(f"  Precision: {test_metrics['precision']:.4f}")
    print(f"  Recall:    {test_metrics['recall']:.4f}")
    print(f"  F1:        {test_metrics['f1']:.4f}")
    print(f"  AUROC:     {test_metrics['auroc']:.4f}")
    print(f"  FPR:       {test_metrics['fpr']:.4f} ({test_metrics['fp']} False Positives)")

    # Check false positives specifically on benign_emotional_hard_negative in test
    hard_neg_metrics = family_breakdown.get("benign_emotional_hard_negative", {})
    print(f"  Hard-Negative Family Breakdown: {hard_neg_metrics}")

    return {
        "ablation_name": "no_hard_negatives",
        "test_metrics": test_metrics,
        "family_breakdown": family_breakdown
    }


def main():
    ablation_no_hn = run_hard_negative_ablation(epochs=5)

    # Load standard contrastive results for side-by-side comparison
    with open("experiments/contrastive_results.json", "r") as f:
        standard_results = json.load(f)

    comparison = {
        "with_hard_negatives": standard_results["test_metrics"],
        "without_hard_negatives": ablation_no_hn["test_metrics"],
        "fpr_delta_percent": (ablation_no_hn["test_metrics"]["fpr"] - standard_results["test_metrics"]["fpr"]) * 100,
        "fp_increase": ablation_no_hn["test_metrics"]["fp"] - standard_results["test_metrics"]["fp"]
    }

    out_path = "experiments/ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(comparison, f, indent=2)

    print("\n" + "="*70)
    print(" 📊 ABLATION SUMMARY: HARD-NEGATIVE CONTRIBUTION")
    print("="*70)
    print(f"  With Hard-Negatives:    FPR = {standard_results['test_metrics']['fpr']*100:.2f}% (FP: {standard_results['test_metrics']['fp']}) | Precision: {standard_results['test_metrics']['precision']*100:.2f}%")
    print(f"  Without Hard-Negatives: FPR = {ablation_no_hn['test_metrics']['fpr']*100:.2f}% (FP: {ablation_no_hn['test_metrics']['fp']}) | Precision: {ablation_no_hn['test_metrics']['precision']*100:.2f}%")
    print(f"  Delta: Hard-negatives prevent +{comparison['fp_increase']} false alarms ({comparison['fpr_delta_percent']:+.2f}% FPR difference)!")
    print(f"Saved results → {out_path}")


if __name__ == "__main__":
    main()
