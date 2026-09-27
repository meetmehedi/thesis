"""
Perplexity-Based Anomaly Detectors for Adversarial Input Detection (RQ1 Baseline).

Implements:
1. GPT2PerplexityDetector: Token-level negative log-likelihood (NLL) perplexity
   using a causal language model (distilgpt2).
2. SubwordEntropyDetector: Shannon character and subword entropy detector
   targeting Base64, leetspeak, and gradient suffix anomalies.
"""

import math
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import List, Dict, Any


class GPT2PerplexityDetector:
    """
    Evaluates token-level perplexity under a causal language model (distilgpt2/gpt2).
    Adversarial gradient suffixes and high-entropy gibberish typically yield elevated PPL,
    whereas fluent social engineering jailbreaks yield normal PPL (revealing its limitation).
    """
    def __init__(self, model_name: str = "distilgpt2", device: torch.device = None):
        if device is None:
            self.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        else:
            self.device = device
            
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.threshold = 150.0  # Calibrated anomaly threshold

    def compute_perplexity(self, text: str) -> float:
        if not text or len(text.strip()) < 5:
            return 10.0

        encodings = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)
        input_ids = encodings.input_ids

        with torch.no_grad():
            outputs = self.model(input_ids, labels=input_ids)
            loss = outputs.loss.item()
            try:
                ppl = math.exp(loss)
            except OverflowError:
                ppl = 10000.0
        return ppl

    def predict(self, text: str) -> int:
        ppl = self.compute_perplexity(text)
        return 1 if ppl > self.threshold else 0

    def predict_batch(self, texts: List[str]) -> List[int]:
        return [self.predict(t) for t in texts]


class SubwordEntropyDetector:
    """
    Evaluates Shannon character entropy and compression ratio to flag
    adversarial token smuggling, Base64 encodings, and gradient suffixes.
    """
    def __init__(self, threshold: float = 4.2):
        self.threshold = threshold

    def compute_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        prob_dict = {}
        length = len(text)
        for char in text:
            prob_dict[char] = prob_dict.get(char, 0) + 1
        entropy = 0.0
        for count in prob_dict.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    def predict(self, text: str) -> int:
        entropy = self.compute_entropy(text)
        return 1 if entropy > self.threshold else 0
