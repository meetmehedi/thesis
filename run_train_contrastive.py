"""
Standalone training script – ContrastiveDetector on 25k dataset.
Handles MPS JIT warmup, reports every 25 steps, saves best checkpoint.
"""
# sklearn MUST be imported before torch on Apple Silicon
import sklearn, sklearn.metrics

import os, sys, json, time, argparse
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from src.models.detector import ContrastiveDetector
from src.models.loss import SupervisedContrastiveLoss
from src.train import load_jsonl, create_tensor_dataset, get_device, evaluate_model

parser = argparse.ArgumentParser()
parser.add_argument("--epochs",     type=int,   default=3)
parser.add_argument("--batch_size", type=int,   default=64)
parser.add_argument("--eval_batch", type=int,   default=128)
parser.add_argument("--lr",         type=float, default=2e-5)
parser.add_argument("--data_dir",   type=str,   default="data/processed_25k")
parser.add_argument("--save_dir",   type=str,   default="experiments")
parser.add_argument("--model_name", type=str,   default="distilbert-base-uncased")
parser.add_argument("--temp",       type=float, default=0.07)
args = parser.parse_args()

def log(msg): print(msg, flush=True)

log(f"{'='*70}")
log(f"  PhD-Grade Contrastive Training  |  Epochs={args.epochs}  |  LR={args.lr}  |  Temp={args.temp}")
log(f"{'='*70}")

os.makedirs(args.save_dir, exist_ok=True)
device = get_device()
log(f"Device: {device}")

# Load data
t0 = time.time()
train_records = load_jsonl(f"{args.data_dir}/train.jsonl")
val_records   = load_jsonl(f"{args.data_dir}/val.jsonl")
test_records  = load_jsonl(f"{args.data_dir}/test.jsonl")
log(f"Loaded {len(train_records):,} train | {len(val_records):,} val | {len(test_records):,} test")

tokenizer = AutoTokenizer.from_pretrained(args.model_name)
train_ds, train_recs = create_tensor_dataset(train_records, tokenizer, max_length=96)
val_ds,   val_recs   = create_tensor_dataset(val_records,   tokenizer, max_length=96)
test_ds,  test_recs  = create_tensor_dataset(test_records,  tokenizer, max_length=96)
log(f"Tokenisation done in {time.time()-t0:.1f}s")

train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  num_workers=0)
val_loader   = DataLoader(val_ds,   batch_size=args.eval_batch, shuffle=False, num_workers=0)
test_loader  = DataLoader(test_ds,  batch_size=args.eval_batch, shuffle=False, num_workers=0)
log(f"Batches – train:{len(train_loader)} val:{len(val_loader)} test:{len(test_loader)}")

# Model, optimizer, scheduler
model = ContrastiveDetector(args.model_name).to(device)
from src.models.loss import SupervisedContrastiveLoss
contrastive_crit = SupervisedContrastiveLoss(temperature=args.temp)
ce_crit = nn.CrossEntropyLoss()
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
total_steps = len(train_loader) * args.epochs
scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1*total_steps), total_steps)

# MPS JIT warmup
log("MPS warmup (JIT kernel compilation) ...")
model.train()
dummy_ids  = torch.randint(0, 1000, (args.batch_size, 96)).to(device)
dummy_mask = torch.ones(args.batch_size, 96).to(device)
dummy_lbl  = torch.randint(0, 2, (args.batch_size,)).to(device)
optimizer.zero_grad()
_, proj, logits = model(dummy_ids, dummy_mask)
loss = contrastive_crit(proj, dummy_lbl) + ce_crit(logits, dummy_lbl)
loss.backward(); optimizer.step(); optimizer.zero_grad()
log("Warmup done. Starting real training...\n")

best_f1 = 0.0
for epoch in range(1, args.epochs + 1):
    model.train()
    total_loss = 0.0
    t_ep = time.time()
    log(f"──── EPOCH {epoch}/{args.epochs} ────")

    for step, (ids, mask, labels, _) in enumerate(train_loader):
        ids    = ids.to(device)
        mask   = mask.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        _, proj, logits = model(ids, mask)
        loss_con = contrastive_crit(proj, labels)
        loss_ce  = ce_crit(logits, labels)
        loss     = loss_con + loss_ce
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step(); scheduler.step()
        total_loss += loss.item()

        if (step + 1) % 25 == 0 or (step + 1) == len(train_loader):
            elapsed = time.time() - t_ep
            spd     = (step + 1) * args.batch_size / elapsed
            eta     = (len(train_loader) - (step + 1)) * (elapsed / (step + 1))
            log(f"  Step {step+1:3d}/{len(train_loader)} | Loss:{loss.item():.4f} (c={loss_con.item():.3f}/ce={loss_ce.item():.3f}) | {spd:.0f} s/s | ETA:{eta:.0f}s")

    avg_loss = total_loss / len(train_loader)
    val_m, _, _, _ = evaluate_model(model, val_loader, val_recs, device, is_contrastive=True)
    log(f"  >> Epoch {epoch} | Loss:{avg_loss:.4f} | ValF1:{val_m['f1']:.4f} | ValAUROC:{val_m['auroc']:.4f} | ValFPR:{val_m['fpr']:.4f}")

    if val_m["f1"] >= best_f1:
        best_f1 = val_m["f1"]
        ckpt = os.path.join(args.save_dir, "contrastive_best_model.pt")
        torch.save(model.state_dict(), ckpt)
        log(f"  --> NEW BEST F1={best_f1:.4f} saved → {ckpt}")
    log("")

# Final test
log("="*70)
log("  FINAL TEST EVALUATION")
ckpt = os.path.join(args.save_dir, "contrastive_best_model.pt")
model.load_state_dict(torch.load(ckpt, map_location=device))
test_m, _, _, _ = evaluate_model(model, test_loader, test_recs, device, is_contrastive=True)
log(f"  Precision: {test_m['precision']:.4f}")
log(f"  Recall:    {test_m['recall']:.4f}")
log(f"  F1-Score:  {test_m['f1']:.4f}")
log(f"  AUROC:     {test_m['auroc']:.4f}")
log(f"  FPR:       {test_m['fpr']:.4f}")

summary = {"mode":"contrastive", "epochs":args.epochs, "n_train":len(train_records), "test_metrics":test_m}
with open(os.path.join(args.save_dir, "contrastive_results.json"), "w") as f:
    json.dump(summary, f, indent=2)
log("DONE ✓")
