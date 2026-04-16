# open-model-v1

A clean, minimal starter repo for supervised fine-tuning a small open-weight language model with LoRA or QLoRA.

This v1 project is meant to be easy to read and easy to extend. It focuses on a simple workflow:

1. Start with raw JSONL training data.
2. Convert it into a processed dataset aligned with the base model tokenizer.
3. Fine-tune a small instruct model with LoRA or QLoRA.
4. Save checkpoints and a final adapter.
5. Run quick evaluation prompts or open a local terminal chat loop.

## What This Repo Does

- Uses Python and Hugging Face tooling.
- Defaults to `HuggingFaceTB/SmolLM2-1.7B-Instruct` as the base model.
- Supports raw training examples in this format:

```json
{"instruction":"...", "input":"...", "output":"..."}
```

- Prepares a processed training file with:
  - `prompt`
  - `completion`
  - `text`
- Fine-tunes with:
  - `transformers`
  - `datasets`
  - `peft`
  - `trl`
  - `bitsandbytes` for 4-bit QLoRA where supported

## Project Layout

```text
open-model-v1/
  data/
    raw/
      train.jsonl
    processed/
  src/
    prepare_data.py
    train_lora.py
    eval.py
    chat.py
    utils.py
  outputs/
  requirements.txt
  README.md
  .gitignore
```

## Environment Setup

### 1. Create a virtual environment

From the repo root:

```bash
python -m venv .venv
```

Activate it:

```bash
# PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you are training on GPU, install the correct PyTorch build for your CUDA version from the official PyTorch install page first, then run:

```bash
pip install -r requirements.txt
```

## Data Preparation

Put your raw training data in `data/raw/train.jsonl`.

Expected format per line:

```json
{"instruction":"Explain LoRA simply.", "input":"", "output":"LoRA trains small adapter weights instead of updating the full model."}
```

Run:

```bash
python src/prepare_data.py
```

This writes:

```text
data/processed/train_sft.jsonl
```

The processed file keeps the original fields and adds model-ready prompt fields built with the base model tokenizer.

If you want to prepare data for a different base model:

```bash
python src/prepare_data.py --base_model Qwen/Qwen2.5-0.5B-Instruct
```

If you change the base model, rerun data preparation before training.

## Training

Default training command:

```bash
python src/train_lora.py
```

This will:

- load the processed dataset
- load the base model
- enable 4-bit QLoRA by default when CUDA is available
- train LoRA adapters
- save checkpoints under `outputs/`
- save the final adapter to:

```text
outputs/smollm2_1.7b_lora/final_adapter
```

Example with a few explicit overrides:

```bash
python src/train_lora.py ^
  --num_train_epochs 1 ^
  --per_device_train_batch_size 1 ^
  --gradient_accumulation_steps 8 ^
  --learning_rate 1e-4
```

On macOS or Linux shells:

```bash
python src/train_lora.py \
  --num_train_epochs 1 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8 \
  --learning_rate 1e-4
```

If you want to disable 4-bit loading:

```bash
python src/train_lora.py --load_in_4bit false
```

That is mainly useful for debugging or environments where `bitsandbytes` is not available. For real low-VRAM training, use the default 4-bit path on a CUDA GPU.

## Evaluation

Run a quick inference smoke test with built-in prompts:

```bash
python src/eval.py
```

This loads the base model plus the saved adapter and prints a few sample generations to the terminal.

If your adapter is saved somewhere else:

```bash
python src/eval.py --adapter_path outputs/smollm2_1.7b_lora/final_adapter
```

## Local Chat

Start a simple terminal chat loop:

```bash
python src/chat.py
```

This v1 chat loop is intentionally simple:

- it loads the base model plus adapter
- it treats each turn as a fresh instruction
- it is useful for quick local testing, not production serving

Type `exit` or `quit` to stop.

## Common Troubleshooting

### `bitsandbytes` install or runtime errors

- Native Windows support can be inconsistent.
- The cleanest path for QLoRA is Linux or WSL with an NVIDIA GPU.
- If you only want to test the code path, try:

```bash
python src/train_lora.py --load_in_4bit false
```

### CUDA out-of-memory

- Start with fewer examples.
- Lower `--max_length`.
- Keep `--per_device_train_batch_size 1`.
- Increase `--gradient_accumulation_steps`.
- Use the default 4-bit mode.

### Tokenizer or prompt mismatch after changing models

- Rerun:

```bash
python src/prepare_data.py --base_model <your-model>
```

- Then train again with the same base model name.

### Training data errors

Each JSONL row must include:

- `instruction` as a non-empty string
- `output` as a non-empty string
- `input` may be empty

### Very slow CPU inference

- This starter is designed mainly for GPU experimentation.
- CPU runs can still work for smoke tests, but they will be slow.

## Notes For Extending Later

Good next steps after this v1:

- add a validation split
- add structured experiment configs
- log metrics to Weights & Biases or TensorBoard
- add adapter merging
- expose inference behind a small FastAPI service
- support DPO or preference tuning later

This repo is intentionally not that yet. It is the first working version.
