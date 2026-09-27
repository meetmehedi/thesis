"""
RQ3: Zero-Shot Held-Out Generalization Evaluation.
Tests both trained models on the HELD-OUT attack family (psych_empathy_exploit)
that was NEVER seen during training — measuring true generalization.
"""

import os
import sys
import json
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.evaluation.metrics import compute_classification_metrics, bootstrap_confidence_intervals
from src.train import get_device

def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def infer_model(model, tokenizer, records, device, is_contrastive=True):
    model.eval()
    all_true, all_pred, all_scores = [], [], []

    with torch.no_grad():
        for r in records:
            inputs = tokenizer(r["text"], return_tensors="pt",
                               truncation=True, padding="max_length",
                               max_length=128).to(device)
            if is_contrastive:
                _, _, logits = model(inputs["input_ids"], inputs["attention_mask"])
            else:
                logits = model(inputs["input_ids"], inputs["attention_mask"])

            probs = torch.softmax(logits, dim=-1)
            pred = int(torch.argmax(probs, dim=-1).item())
            score = float(probs[0, 1].item())

            all_true.append(r["label"])
            all_pred.append(pred)
            all_scores.append(score)
            print(f"  [{'+' if pred == r['label'] else 'X'}] Label={r['label']} | Pred={pred} | Score={score:.3f} | {r['text'][:80]}...")

    return all_true, all_pred, all_scores

def run_rq3():
    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    # Load held-out records
    held_out_path = "data/processed/held_out_generalization.jsonl"
    if not os.path.exists(held_out_path):
        print("Held-out file not found. Run data builder first.")
        sys.exit(1)

    held_out = load_jsonl(held_out_path)
    print(f"\n{'='*65}")
    print(f" RQ3: Zero-Shot Generalization on Held-Out Attack Family")
    print(f" Family: psych_empathy_exploit | Samples: {len(held_out)}")
    print(f"{'='*65}")

    results = {}

    for mode, ModelClass, ckpt in [
        ("contrastive", ContrastiveDetector, "experiments/contrastive_best_model.pt"),
        ("cross_entropy", CrossEntropyBaseline, "experiments/cross_entropy_best_model.pt")
    ]:
        if not os.path.exists(ckpt):
            print(f"\n⚠️  {ckpt} not found — skipping {mode}.")
            continue

        print(f"\n--- {mode.upper()} MODEL ---")
        model = ModelClass(model_name="distilbert-base-uncased").to(device)
        model.load_state_dict(torch.load(ckpt, map_location=device))

        y_true, y_pred, y_scores = infer_model(
            model, tokenizer, held_out, device, is_contrastive=(mode == "contrastive")
        )

        if len(set(y_true)) < 2:
            # Single-class held-out — report recall/detection rate directly
            n_correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
            detection_rate = n_correct / len(y_true)
            print(f"\n  Detection Rate: {detection_rate*100:.1f}% ({n_correct}/{len(y_true)})")
            print(f"  Mean Adversarial Score: {sum(y_scores)/len(y_scores):.4f}")
            results[mode] = {
                "detection_rate": detection_rate,
                "mean_adv_score": sum(y_scores) / len(y_scores),
                "samples": len(y_true),
                "individual_scores": y_scores,
                "individual_preds": y_pred,
                "individual_labels": y_true
            }
        else:
            metrics = compute_classification_metrics(y_true, y_pred, y_scores)
            print(f"\n  Recall:   {metrics['recall']:.4f}")
            print(f"  F1:       {metrics['f1']:.4f}")
            print(f"  AUROC:    {metrics['auroc']:.4f}")
            results[mode] = metrics

    # Save RQ3 results
    os.makedirs("experiments", exist_ok=True)
    with open("experiments/rq3_held_out_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*65}")
    print(" RQ3 SUMMARY — Zero-Shot Generalization")
    print(f"{'='*65}")
    for mode, res in results.items():
        dr = res.get("detection_rate", res.get("recall", "N/A"))
        ms = res.get("mean_adv_score", "N/A")
        print(f"  {mode:20s}: Detection Rate={dr:.2%}  Mean Adv Score={ms:.4f}" if isinstance(ms, float) else f"  {mode:20s}: {res}")

    print("\nResults saved → experiments/rq3_held_out_results.json")
    return results

if __name__ == "__main__":
    run_rq3()
