# Fine-tuning

Codey-OS supports personalizing the underlying model using your own interaction history. Heavy training runs off-device on Google Colab (free tier), while your phone handles only lightweight data export and model file management.

---

## Step 1 — Export Your Interaction Data

```bash
# Export last 30 days with default quality threshold
codeyOS --finetune

# Customize the export
codeyOS --finetune --ft-days 60 --ft-quality 0.6 --ft-model 4b
```

| Flag | Default | Description |
|------|---------|-------------|
| `--ft-days` | 30 | Days of history to include |
| `--ft-quality` | 0.7 | Minimum quality score (0.0–1.0) |
| `--ft-model` | 4b | Target variant: `4b` (the deployed Qwen3.5-4B). `1.5b`, `7b` and `both` are legacy Qwen2.5 variants for models Codey-OS no longer runs |
| `--ft-output` | `~/Downloads/codey-finetune` | Output directory |

**Output files:**

- `codey-finetune-4b.jsonl` — Dataset for the deployed Qwen3.5-4B
- A Colab notebook for the chosen variant (legacy variants write `codey-finetune-*-1.5b/7b` files)

---

## Step 2 — Train on Google Colab

1. Go to [colab.research.google.com](https://colab.research.google.com).
2. Upload the generated notebook (`codey-finetune-*.ipynb`).
3. Run all cells. Free T4 GPU takes 1–4 hours depending on model size.
4. Download `codey-lora-adapter.zip` when training completes.

Training uses [Unsloth](https://github.com/unslothai/unsloth) for 2x speed and 70% less VRAM.

---

## Step 3 — Import the Adapter

```bash
# Extract the downloaded adapter
unzip codey-lora-adapter.zip

# Import to Codey-OS
codeyOS --import-lora /path/to/codey-lora-adapter --lora-model primary
```

| Flag | Default | Description |
|------|---------|-------------|
| `--lora-model` | primary | `primary` (the only accepted value) |
| `--lora-quant` | q4_0 | Quantization: `q4_0`, `q5_0`, `q8_0`, `f16` |
| `--lora-merge` | false | Merge on-device (requires llama.cpp, ~8 GB RAM; not re-measured for the 4B) |

---

## Merging On-Device (Advanced)

If you want a single merged GGUF file instead of a base model + adapter:

```bash
# Merge on import
codeyOS --import-lora /path/to/adapter --lora-model primary --lora-merge

# Or manually with llama.cpp
python ~/llama.cpp/convert-lora.py \
  --base-model ~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf \
  --lora-adapter /path/to/adapter \
  --output merged.gguf

./quantize merged.gguf merged-q4.gguf q4_0
```

Merge RAM and time requirements have not been re-measured for the 4B.

---

## Rollback

A full backup is created automatically before any import. To restore:

```bash
codeyOS --rollback --lora-model primary
```

---

## Quality Tips

| Goal | Setting |
|------|---------|
| High quality, smaller dataset | `--ft-quality 0.8` or higher |
| More examples, more diversity | `--ft-quality 0.5` with `--ft-days 90` |
| Any fine-tune | Target the 4B (the only deployed model) |
