"""
Evaluation Metrics & Statistical Rigor Suite for LLM Security Pre-Filter:
1. Standard Classification Metrics (Precision, Recall, F1, AUROC)
2. Non-parametric Bootstrap Confidence Intervals (95% CI)
3. Breakdown by Attack Family & Language (Technical, Psychological, Banglish, Hard-Negatives)
4. End-to-end Latency Profiling (P50, P95, P99 in ms)
"""

import time
import numpy as np
import torch
from typing import List, Dict, Any, Tuple
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score, confusion_matrix

def compute_classification_metrics(
    y_true: List[int],
    y_pred: List[int],
    y_scores: List[float]
) -> Dict[str, float]:
    """Computes basic evaluation metrics."""
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    y_scores_arr = np.array(y_scores)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true_arr, y_pred_arr, average="binary", zero_division=0
    )

    try:
        auroc = roc_auc_score(y_true_arr, y_scores_arr)
    except Exception:
        auroc = 0.5  # Fallback if only 1 class present

    tn, fp, fn, tp = confusion_matrix(y_true_arr, y_pred_arr, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auroc": float(auroc),
        "fpr": float(fpr),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn)
    }

def bootstrap_confidence_intervals(
    y_true: List[int],
    y_pred: List[int],
    y_scores: List[float],
    n_bootstraps: int = 1000,
    alpha: float = 0.05,
    seed: int = 42
) -> Dict[str, Tuple[float, float]]:
    """
    Computes 95% non-parametric bootstrap confidence intervals.
    Returns: Dict mapping metric name to (ci_lower, ci_upper).
    """
    rng = np.random.RandomState(seed)
    n = len(y_true)
    if n == 0:
        return {}

    bootstrapped_metrics = {"precision": [], "recall": [], "f1": [], "auroc": []}

    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    y_scores_arr = np.array(y_scores)

    for _ in range(n_bootstraps):
        indices = rng.randint(0, n, size=n)
        if len(np.unique(y_true_arr[indices])) < 2:
            continue  # Need both classes for AUROC/binary metrics
        
        metrics = compute_classification_metrics(
            y_true_arr[indices], y_pred_arr[indices], y_scores_arr[indices]
        )
        for k in bootstrapped_metrics:
            bootstrapped_metrics[k].append(metrics[k])

    ci_results = {}
    for k, values in bootstrapped_metrics.items():
        if len(values) > 0:
            low = float(np.percentile(values, 100 * (alpha / 2)))
            high = float(np.percentile(values, 100 * (1 - alpha / 2)))
            ci_results[k] = (low, high)
        else:
            ci_results[k] = (0.0, 0.0)

    return ci_results

def evaluate_by_family(
    records: List[Dict[str, Any]],
    y_pred: List[int],
    y_scores: List[float]
) -> Dict[str, Dict[str, Any]]:
    """
    Groups and calculates metrics across different attack families:
    Psychological, Technical, Cultural (Bangla/Banglish), and Hard-Negatives.
    """
    families = set(r["attack_family"] for r in records)
    family_results = {}

    for fam in families:
        indices = [i for i, r in enumerate(records) if r["attack_family"] == fam]
        fam_true = [records[i]["label"] for i in indices]
        fam_pred = [y_pred[i] for i in indices]
        fam_scores = [y_scores[i] for i in indices]

        fam_results = compute_classification_metrics(fam_true, fam_pred, fam_scores)
        fam_results["sample_count"] = len(indices)
        family_results[fam] = fam_results

    return family_results

def profile_latency(
    model: torch.nn.Module,
    tokenizer: Any,
    sample_texts: List[str],
    device: torch.device,
    runs: int = 100
) -> Dict[str, float]:
    """Measures inference latency in milliseconds."""
    model.eval()
    latencies = []

    # Warmup — 20 passes to eliminate MPS cold-start spike from P95/P99
    warmup_texts = (sample_texts * 5)[:20]
    for text in warmup_texts:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(device)
        with torch.no_grad():
            if hasattr(model, "encode"):
                _ = model.encode(inputs["input_ids"], inputs["attention_mask"])
            else:
                _ = model(inputs["input_ids"], inputs["attention_mask"])
    if hasattr(torch, "mps"):
        torch.mps.synchronize()  # Flush MPS command buffer before timing

    # Benchmarking
    for _ in range(runs):
        text = sample_texts[_ % len(sample_texts)]
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128).to(device)
        start_time = time.perf_counter()
        with torch.no_grad():
            if hasattr(model, "encode"):
                _ = model.encode(inputs["input_ids"], inputs["attention_mask"])
            else:
                _ = model(inputs["input_ids"], inputs["attention_mask"])
        end_time = time.perf_counter()
        latencies.append((end_time - start_time) * 1000.0)  # ms

    return {
        "mean_ms": float(np.mean(latencies)),
        "std_ms": float(np.std(latencies)),
        "p50_ms": float(np.percentile(latencies, 50)),
        "p95_ms": float(np.percentile(latencies, 95)),
        "p99_ms": float(np.percentile(latencies, 99))
    }
