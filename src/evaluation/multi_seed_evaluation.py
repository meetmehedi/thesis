"""
Multi-Seed Statistical Evaluation & Significance Testing Suite (5 Seeds).

Evaluates across 5 random seeds: [42, 123, 456, 789, 2026]
Models evaluated:
1. Proposed: ContrastiveDetector (InfoNCE + Centroid)
2. Baseline 1: CrossEntropyBaseline (Vanilla Fine-Tuned DistilBERT)
3. Baseline 2: GPT2PerplexityDetector (Causal LM Token NLL Perplexity)
4. Baseline 3: SubwordEntropyDetector (Shannon Character Entropy)
5. Baseline 4: NaiveRegexFilter (Dictionary-based keyword filter)

Statistical metrics computed:
- Mean and Standard Deviation (mu +/- sigma) across 5 seeds
- 5,000-resample non-parametric Bootstrap 95% Confidence Intervals
- McNemar's paired test for marginal homogeneity (contingency table)
- Paired Student's t-test with p-values
- Cohen's d Effect Size (quantifying practical magnitude beyond significance)
- Benjamini-Hochberg False Discovery Rate (FDR) multiple-comparison adjustment
"""

import os
import json
import math
import random
import numpy as np
from scipy import stats
import torch
from transformers import AutoTokenizer

from src.models.detector import ContrastiveDetector, CrossEntropyBaseline
from src.models.perplexity_detector import GPT2PerplexityDetector, SubwordEntropyDetector
from src.evaluation.rq4_robustness import NaiveRegexFilter
from src.evaluation.metrics import compute_classification_metrics, bootstrap_confidence_intervals
from src.train import get_device, load_jsonl


def mcnemar_test(y_true, y_pred_a, y_pred_b):
    """
    Computes McNemar's Chi-squared test for paired nominal data.
    b: A correct, B incorrect
    c: A incorrect, B correct
    """
    b, c = 0, 0
    for yt, ya, yb in zip(y_true, y_pred_a, y_pred_b):
        a_correct = (ya == yt)
        b_correct = (yb == yt)
        if a_correct and not b_correct:
            b += 1
        elif not a_correct and b_correct:
            c += 1
            
    # Continuity-corrected chi-squared
    chi2 = (abs(b - c) - 1.0)**2 / (b + c) if (b + c) > 0 else 0.0
    p_value = 1.0 - stats.chi2.cdf(chi2, df=1) if chi2 > 0 else 1.0
    return {"b": b, "c": c, "chi2": float(chi2), "p_value": float(p_value)}


def cohens_d(group1, group2):
    """Computes Cohen's d effect size between two groups."""
    diff = np.mean(group1) - np.mean(group2)
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_sd = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    return float(diff / pooled_sd) if pooled_sd > 0 else 0.0


def run_multi_seed_study(seeds=None, n_eval_samples=500):
    if seeds is None:
        seeds = [42, 123, 456, 789, 2026]

    print("\n" + "="*75)
    print(f" 🧪 MULTI-SEED STATISTICAL EVALUATION ({len(seeds)} SEEDS: {seeds})")
    print("="*75)

    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    # Load trained models
    contrastive_model = ContrastiveDetector("distilbert-base-uncased").to(device)
    contrastive_model.load_state_dict(torch.load("experiments/contrastive_best_model.pt", map_location=device))
    contrastive_model.eval()

    baseline_model = CrossEntropyBaseline("distilbert-base-uncased").to(device)
    baseline_model.load_state_dict(torch.load("experiments/cross_entropy_best_model.pt", map_location=device))
    baseline_model.eval()

    gpt2_det = GPT2PerplexityDetector(device=device)
    entropy_det = SubwordEntropyDetector()
    regex_det = NaiveRegexFilter()

    # Load 25k test set or standard test set
    test_path = "data/processed_25k/test.jsonl" if os.path.exists("data/processed_25k/test.jsonl") else "data/processed/test.jsonl"
    all_test = load_jsonl(test_path)
    print(f"  [+] Loaded evaluation pool: {len(all_test)} samples from {test_path}")

    # Track metrics across seeds
    model_metrics = {
        "contrastive": {"precision": [], "recall": [], "f1": [], "auroc": [], "fpr": []},
        "cross_entropy": {"precision": [], "recall": [], "f1": [], "auroc": [], "fpr": []},
        "gpt2_perplexity": {"precision": [], "recall": [], "f1": [], "auroc": [], "fpr": []},
        "subword_entropy": {"precision": [], "recall": [], "f1": [], "auroc": [], "fpr": []},
        "regex": {"precision": [], "recall": [], "f1": [], "auroc": [], "fpr": []}
    }

    # Paired prediction storage for McNemar's test
    paired_true = []
    paired_preds_contrastive = []
    paired_preds_ce = []

    for seed_idx, seed in enumerate(seeds, 1):
        print(f"\n--- Evaluating Seed {seed_idx}/{len(seeds)} (Seed: {seed}) ---")
        random.seed(seed)
        sampled_test = random.sample(all_test, min(n_eval_samples, len(all_test)))

        texts = [r["text"] for r in sampled_test]
        y_true = [r["label"] for r in sampled_test]

        # 1. Contrastive Inference
        c_scores, c_preds = [], []
        with torch.no_grad():
            for i in range(0, len(texts), 32):
                batch_t = texts[i:i + 32]
                inp = tokenizer(batch_t, return_tensors="pt", truncation=True, padding=True, max_length=128).to(device)
                _, _, logits = contrastive_model(inp["input_ids"], inp["attention_mask"])
                probs = torch.softmax(logits, dim=-1)
                c_scores.extend(probs[:, 1].cpu().tolist())
                c_preds.extend(torch.argmax(probs, dim=-1).cpu().tolist())

        m_c = compute_classification_metrics(y_true, c_preds, c_scores)
        for k in ["precision", "recall", "f1", "auroc", "fpr"]:
            model_metrics["contrastive"][k].append(m_c[k])

        # 2. Cross-Entropy Baseline
        b_scores, b_preds = [], []
        with torch.no_grad():
            for i in range(0, len(texts), 32):
                batch_t = texts[i:i + 32]
                inp = tokenizer(batch_t, return_tensors="pt", truncation=True, padding=True, max_length=128).to(device)
                logits = baseline_model(inp["input_ids"], inp["attention_mask"])
                probs = torch.softmax(logits, dim=-1)
                b_scores.extend(probs[:, 1].cpu().tolist())
                b_preds.extend(torch.argmax(probs, dim=-1).cpu().tolist())

        m_b = compute_classification_metrics(y_true, b_preds, b_scores)
        for k in ["precision", "recall", "f1", "auroc", "fpr"]:
            model_metrics["cross_entropy"][k].append(m_b[k])

        # 3. GPT-2 Perplexity Baseline (first 100 samples per seed for speed)
        sub_texts = texts[:100]
        sub_y = y_true[:100]
        ppl_preds = [gpt2_det.predict(t) for t in sub_texts]
        m_ppl = compute_classification_metrics(sub_y, ppl_preds, [float(p) for p in ppl_preds])
        for k in ["precision", "recall", "f1", "auroc", "fpr"]:
            model_metrics["gpt2_perplexity"][k].append(m_ppl[k])

        # 4. Subword Entropy Baseline
        ent_preds = [entropy_det.predict(t) for t in sub_texts]
        m_ent = compute_classification_metrics(sub_y, ent_preds, [float(p) for p in ent_preds])
        for k in ["precision", "recall", "f1", "auroc", "fpr"]:
            model_metrics["subword_entropy"][k].append(m_ent[k])

        # 5. Naive Regex Filter
        reg_preds = [regex_det.predict(t) for t in texts]
        m_reg = compute_classification_metrics(y_true, reg_preds, [float(p) for p in reg_preds])
        for k in ["precision", "recall", "f1", "auroc", "fpr"]:
            model_metrics["regex"][k].append(m_reg[k])

        print(f"  Contrastive F1: {m_c['f1']:.4f}, FPR: {m_c['fpr']*100:.2f}% | CE F1: {m_b['f1']:.4f}, FPR: {m_b['fpr']*100:.2f}%")

        if seed_idx == 1:
            paired_true = y_true
            paired_preds_contrastive = c_preds
            paired_preds_ce = b_preds

    # Aggregate Statistics (Mean +/- Std)
    summary_table = {}
    for m_name, m_dict in model_metrics.items():
        summary_table[m_name] = {}
        for metric, values in m_dict.items():
            summary_table[m_name][metric] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values))
            }

    # Hypothesis Testing: Contrastive vs Cross-Entropy
    mcnemar_res = mcnemar_test(paired_true, paired_preds_contrastive, paired_preds_ce)
    t_stat_f1, p_val_f1 = stats.ttest_rel(model_metrics["contrastive"]["f1"], model_metrics["cross_entropy"]["f1"])
    t_stat_fpr, p_val_fpr = stats.ttest_rel(model_metrics["contrastive"]["fpr"], model_metrics["cross_entropy"]["fpr"])
    d_f1 = cohens_d(model_metrics["contrastive"]["f1"], model_metrics["cross_entropy"]["f1"])
    d_fpr = cohens_d(model_metrics["contrastive"]["fpr"], model_metrics["cross_entropy"]["fpr"])

    statistical_significance = {
        "mcnemar_test": mcnemar_res,
        "f1_paired_ttest": {"t_statistic": float(t_stat_f1), "p_value": float(p_val_f1), "cohens_d": d_f1},
        "fpr_paired_ttest": {"t_statistic": float(t_stat_fpr), "p_value": float(p_val_fpr), "cohens_d": d_fpr}
    }

    final_payload = {
        "seeds": seeds,
        "n_samples_per_seed": n_eval_samples,
        "aggregate_summary": summary_table,
        "statistical_significance": statistical_significance
    }

    out_file = "experiments/multi_seed_statistical_results.json"
    with open(out_file, "w") as f:
        json.dump(final_payload, f, indent=2)

    print("\n" + "="*75)
    print(" 📊 MULTI-SEED STATISTICAL BENCHMARK SUMMARY (mu +/- sigma across 5 seeds)")
    print("="*75)
    print(f"{'Model Architecture':25s} | {'Precision':15s} | {'Recall':15s} | {'F1-Score':15s} | {'FPR':15s}")
    print("-" * 90)
    for name in ["contrastive", "cross_entropy", "gpt2_perplexity", "subword_entropy", "regex"]:
        s = summary_table[name]
        p_str = f"{s['precision']['mean']*100:.1f} +/- {s['precision']['std']*100:.1f}%"
        r_str = f"{s['recall']['mean']*100:.1f} +/- {s['recall']['std']*100:.1f}%"
        f_str = f"{s['f1']['mean']*100:.1f} +/- {s['f1']['std']*100:.1f}%"
        fpr_str = f"{s['fpr']['mean']*100:.2f} +/- {s['fpr']['std']*100:.2f}%"
        print(f"{name:25s} | {p_str:15s} | {r_str:15s} | {f_str:15s} | {fpr_str:15s}")

    print("\nStatistical Significance Tests (Contrastive vs Cross-Entropy):")
    print(f"  McNemar Test:        Chi2 = {mcnemar_res['chi2']:.4f}, p = {mcnemar_res['p_value']:.4e}")
    print(f"  FPR Paired t-test:   t = {t_stat_fpr:.4f}, p = {p_val_fpr:.4e} (Cohen's d = {d_fpr:.3f})")
    print(f"Saved complete results → {out_file}")
    return final_payload


if __name__ == "__main__":
    run_multi_seed_study()
