"""
Model Architectures for LLM Prompt Injection & Jailbreak Pre-Filter:
1. ContrastiveDetector (DistilBERT + InfoNCE + Projection Head + Centroid Classifier)
2. CrossEntropyBaseline (DistilBERT + Standard Linear Classification Head)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
from typing import Dict, Tuple, Optional

class ContrastiveDetector(nn.Module):
    """
    Lightweight Pre-filter trained with Supervised Contrastive Loss (InfoNCE).
    Learns an embedding geometry separating adversarial manipulation from benign queries.
    """
    def __init__(
        self,
        model_name: str = "distilbert-base-uncased",
        projection_dim: int = 128
    ):
        super(ContrastiveDetector, self).__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        # Non-linear projection head for contrastive learning
        self.projection_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, projection_dim)
        )

        # Lightweight linear classifier head on top of representation
        self.classifier = nn.Linear(hidden_size, 2)

        # Stored centroids for prototype-based nearest-neighbor zero-shot inference
        self.register_buffer("benign_centroid", torch.zeros(hidden_size))
        self.register_buffer("adv_centroid", torch.zeros(hidden_size))

    def encode(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        """Extracts [CLS] token representation."""
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # First token is [CLS]
        cls_rep = outputs.last_hidden_state[:, 0, :]
        return cls_rep

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns:
            cls_rep: Raw encoder representation [batch_size, hidden_size]
            projected: L2-normalized projection [batch_size, projection_dim] for InfoNCE
            logits: Classification logits [batch_size, 2]
        """
        cls_rep = self.encode(input_ids, attention_mask)
        projected = F.normalize(self.projection_head(cls_rep), p=2, dim=1)
        logits = self.classifier(cls_rep)
        return cls_rep, projected, logits

    def update_centroids(self, all_embeddings: torch.Tensor, all_labels: torch.Tensor):
        """Calculates class centroids across the dataset for fast metric inference."""
        benign_mask = (all_labels == 0)
        adv_mask = (all_labels == 1)

        if benign_mask.sum() > 0:
            self.benign_centroid = F.normalize(all_embeddings[benign_mask].mean(dim=0), p=2, dim=0)
        if adv_mask.sum() > 0:
            self.adv_centroid = F.normalize(all_embeddings[adv_mask].mean(dim=0), p=2, dim=0)

    def predict_similarity_score(self, cls_rep: torch.Tensor) -> torch.Tensor:
        """
        Scores input using cosine similarity against stored centroids:
        Score in [0, 1] representing likelihood of adversarial intent.
        """
        rep_norm = F.normalize(cls_rep, p=2, dim=-1)
        sim_adv = torch.matmul(rep_norm, self.adv_centroid)
        sim_benign = torch.matmul(rep_norm, self.benign_centroid)

        # Softmax over centroid similarities
        stacked = torch.stack([sim_benign, sim_adv], dim=-1)
        probs = F.softmax(stacked / 0.1, dim=-1)
        return probs[:, 1]  # Probability of adversarial


class CrossEntropyBaseline(nn.Module):
    """
    Standard fine-tuned DistilBERT baseline (answers RQ2).
    Uses traditional cross-entropy loss without contrastive geometry.
    """
    def __init__(self, model_name: str = "distilbert-base-uncased"):
        super(CrossEntropyBaseline, self).__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls_rep = outputs.last_hidden_state[:, 0, :]
        logits = self.classifier(cls_rep)
        return logits
