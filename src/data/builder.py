"""
Dataset Builder: Assembles public datasets with psychological, cultural,
and hard-negative datasets, creating reproducible train/val/test splits.
"""

import os
import json
import uuid
import random
from typing import List, Dict, Tuple
from datasets import load_dataset
from src.data.schema import PromptRecord, AttackCategory, AttackFamily, Language
from src.data.seed_generator import generate_seed_records

def load_public_benchmark() -> List[PromptRecord]:
    """Loads and standardizes public prompt-injection benchmark."""
    print("Loading public benchmark: deepset/prompt-injections...")
    records = []
    try:
        ds = load_dataset('deepset/prompt-injections')
        for split in ['train', 'test']:
            for item in ds[split]:
                text = item['text']
                label = int(item['label'])
                category = AttackCategory.DIRECT_INJECTION if label == 1 else AttackCategory.NONE
                family = AttackFamily.TECHNICAL_INSTRUCTION_OVERRIDE if label == 1 else AttackFamily.BENIGN_STANDARD
                
                records.append(PromptRecord(
                    id=str(uuid.uuid4()),
                    text=text,
                    label=label,
                    attack_category=category,
                    attack_family=family,
                    language=Language.EN,
                    source="deepset_prompt_injections"
                ))
    except Exception as e:
        print(f"Warning: Failed to fetch deepset/prompt-injections: {e}")
    return records

def build_dataset(
    output_dir: str = "data/processed",
    held_out_family: AttackFamily = AttackFamily.PSYCH_EMPATHY_EXPLOIT,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42
) -> Dict[str, str]:
    """
    Builds and partitions the dataset, holding out `held_out_family` for generalization testing.
    """
    random.seed(seed)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Combine public and domain-specific seeds
    public_records = load_public_benchmark()
    seed_records = generate_seed_records()
    all_records = public_records + seed_records

    print(f"Total aggregated records: {len(all_records)}")

    # 2. Separate held-out family for zero-shot cross-family generalization (RQ3)
    held_out_records = [r for r in all_records if r.attack_family == held_out_family]
    standard_records = [r for r in all_records if r.attack_family != held_out_family]

    print(f"Standard pool: {len(standard_records)}, Held-out ({held_out_family.value}): {len(held_out_records)}")

    # 3. Stratified split (by label) on standard records
    benign = [r for r in standard_records if r.label == 0]
    adversarial = [r for r in standard_records if r.label == 1]

    random.shuffle(benign)
    random.shuffle(adversarial)

    def split_pool(pool: List[PromptRecord]) -> Tuple[List[PromptRecord], List[PromptRecord], List[PromptRecord]]:
        n = len(pool)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        return pool[:n_train], pool[n_train:n_train + n_val], pool[n_train + n_val:]

    train_benign, val_benign, test_benign = split_pool(benign)
    train_adv, val_adv, test_adv = split_pool(adversarial)

    train_set = train_benign + train_adv
    val_set = val_benign + val_adv
    test_set = test_benign + test_adv

    random.shuffle(train_set)
    random.shuffle(val_set)
    random.shuffle(test_set)

    # 4. Save to JSONL
    splits = {
        "train": train_set,
        "val": val_set,
        "test": test_set,
        "held_out_generalization": held_out_records
    }

    output_paths = {}
    for split_name, dataset in splits.items():
        filepath = os.path.join(output_dir, f"{split_name}.jsonl")
        with open(filepath, "w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        output_paths[split_name] = filepath
        print(f"Saved {split_name}: {len(dataset)} records -> {filepath}")

    return output_paths

if __name__ == "__main__":
    build_dataset()
