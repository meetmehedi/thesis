#!/bin/bash
# pack_for_colab.sh — creates thesis_project.zip ready for Colab upload
# Run from: /Users/md.mehedihasan/Documents/Thesis
set -e
cd "$(dirname "$0")"
echo "📦 Packing thesis project for Google Colab..."
[ -f thesis_project.zip ] && rm thesis_project.zip

zip -r thesis_project.zip \
    src/ \
    data/processed_25k/ \
    configs/ \
    run_experiments.py \
    run_train_contrastive.py \
    --exclude "*/__pycache__/*" \
    --exclude "*.pyc" \
    --exclude "*.pt" \
    --exclude ".git/*" \
    --exclude "data/raw/*" \
    --exclude "data/synthetic/*"

SIZE=$(du -sh thesis_project.zip | cut -f1)
echo "✅ Done! thesis_project.zip ($SIZE)"
echo ""
echo "Next steps:"
echo "  1. Open https://colab.research.google.com"
echo "  2. Upload notebooks/thesis_colab_runner.ipynb"
echo "  3. Runtime → Change runtime type → T4 GPU"
echo "  4. Run cells top-to-bottom, upload thesis_project.zip when prompted"
