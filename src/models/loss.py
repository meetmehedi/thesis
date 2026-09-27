"""
InfoNCE and Supervised Contrastive Loss (SupCon) Implementation for LLM Security Pre-filter.
Optimizes embedding space to maximize intra-class compactness and inter-class separation.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class SupervisedContrastiveLoss(nn.Module):
    """
    Supervised Contrastive Learning (SupCon) with InfoNCE objective.
    Reference: Khosla et al., 'Supervised Contrastive Learning', NeurIPS 2020.
    """
    def __init__(self, temperature: float = 0.07, base_temperature: float = 0.07):
        super(SupervisedContrastiveLoss, self).__init__()
        self.temperature = temperature
        self.base_temperature = base_temperature

    def forward(self, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        Args:
            features: Normalized embeddings of shape [batch_size, hidden_dim]
            labels: Ground truth labels of shape [batch_size] (0 or 1)
        """
        device = features.device
        batch_size = features.shape[0]
        if batch_size <= 1:
            return torch.tensor(0.0, device=device, requires_grad=True)

        # Normalize features to unit sphere
        features = F.normalize(features, p=2, dim=1)

        # Compute cosine similarity matrix: [batch_size, batch_size]
        similarity_matrix = torch.matmul(features, features.T) / self.temperature

        # Create mask: 1 where labels match, 0 otherwise
        labels = labels.contiguous().view(-1, 1)
        mask = torch.eq(labels, labels.T).float().to(device)

        # Mask out self-contrast (diagonal)
        logits_mask = torch.scatter(
            torch.ones_like(mask),
            1,
            torch.arange(batch_size).view(-1, 1).to(device),
            0
        )
        mask = mask * logits_mask

        # For numerical stability
        logits_max, _ = torch.max(similarity_matrix, dim=1, keepdim=True)
        logits = similarity_matrix - logits_max.detach()

        # Compute log-probability
        exp_logits = torch.exp(logits) * logits_mask
        log_prob = logits - torch.log(exp_logits.sum(1, keepdim=True) + 1e-8)

        # Compute mean of log-likelihood over positive pairs
        mean_log_prob_pos = (mask * log_prob).sum(1) / (mask.sum(1) + 1e-8)

        # Only compute loss for anchors that have at least one positive partner in batch
        valid_anchors = (mask.sum(1) > 0)
        if valid_anchors.sum() == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)

        loss = - (self.temperature / self.base_temperature) * mean_log_prob_pos[valid_anchors].mean()
        return loss
