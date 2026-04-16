from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

from utils import (
    DEFAULT_BASE_MODEL,
    DEFAULT_RUNTIME_PRESET,
    ROOT_DIR,
    get_compute_dtype,
    get_runtime_preset_names,
    load_tokenizer,
    resolve_runtime_preset,
    should_default_to_4bit,
    str_to_bool,
)


DEFAULT_DATASET_PATH = ROOT_DIR / "data" / "processed" / "train_sft.jsonl"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs" / "smollm2_1.7b_lora"
DEFAULT_MAX_LENGTH = 512
DEFAULT_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune a small open model with LoRA or QLoRA.")
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--dataset_path", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output_dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--preset",
        type=str,
        choices=get_runtime_preset_names(),
        default=None,
        help=f"Optional hardware preset, for example {DEFAULT_RUNTIME_PRESET}.",
    )
    parser.add_argument("--max_length", type=int, default=None)
    parser.add_argument("--num_train_epochs", type=float, default=3.0)
    parser.add_argument("--per_device_train_batch_size", type=int, default=None)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=None)
    parser.add_argument("--learning_rate", type=float, default=1e-4)
    parser.add_argument("--warmup_ratio", type=float, default=0.03)
    parser.add_argument("--logging_steps", type=int, default=10)
    parser.add_argument("--save_steps", type=int, default=50)
    parser.add_argument("--save_total_limit", type=int, default=2)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    parser.add_argument(
        "--load_in_4bit",
        type=str_to_bool,
        default=None,
        help="Use 4-bit QLoRA when the local environment supports it.",
    )
    parser.add_argument(
        "--resume_from_checkpoint",
        type=str,
        default=None,
        help="Optional checkpoint path inside outputs/ to resume training.",
    )
    args = parser.parse_args()
    preset_defaults = resolve_runtime_preset(
        preset_name=args.preset,
        scope="train",
        fallback_defaults={
            "max_length": DEFAULT_MAX_LENGTH,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "load_in_4bit": should_default_to_4bit(),
        },
    )
    for field_name, field_value in preset_defaults.items():
        if getattr(args, field_name) is None:
            setattr(args, field_name, field_value)
    return args


def validate_environment(args: argparse.Namespace) -> None:
    if not args.dataset_path.exists():
        raise FileNotFoundError(
            f"Processed dataset not found: {args.dataset_path}. Run src/prepare_data.py first."
        )

    if args.load_in_4bit and not torch.cuda.is_available():
        raise EnvironmentError(
            "4-bit QLoRA requires a CUDA-enabled GPU. On Windows, use WSL/Linux for the cleanest setup. "
            "If you still want to test the script flow, rerun with --load_in_4bit false."
        )


def load_model(args: argparse.Namespace):
    compute_dtype = get_compute_dtype()
    model_kwargs = {"trust_remote_code": False}

    if args.load_in_4bit:
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["torch_dtype"] = compute_dtype
        if torch.cuda.is_available():
            model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    if args.load_in_4bit:
        model = prepare_model_for_kbit_training(model)

    model.config.use_cache = False
    return model


def main() -> None:
    args = parse_args()
    validate_environment(args)

    if args.preset:
        print(f"Using preset: {args.preset}")

    tokenizer = load_tokenizer(args.base_model)
    dataset = load_dataset("json", data_files=str(args.dataset_path), split="train")
    model = load_model(args)

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=DEFAULT_TARGET_MODULES,
    )

    bf16_enabled = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    fp16_enabled = torch.cuda.is_available() and not bf16_enabled

    training_args = SFTConfig(
        output_dir=str(args.output_dir),
        max_length=args.max_length,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type="cosine",
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_strategy="steps",
        save_total_limit=args.save_total_limit,
        gradient_checkpointing=True,
        bf16=bf16_enabled,
        fp16=fp16_enabled,
        report_to="none",
        optim="paged_adamw_8bit" if args.load_in_4bit else "adamw_torch",
        remove_unused_columns=False,
        completion_only_loss=True,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    trainer.model.print_trainable_parameters()
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    final_adapter_dir = args.output_dir / "final_adapter"
    final_adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(str(final_adapter_dir))
    tokenizer.save_pretrained(str(final_adapter_dir))

    print("Training finished.")
    print(f"Checkpoints saved under: {args.output_dir.resolve()}")
    print(f"Final adapter saved to: {final_adapter_dir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[train_lora] Error: {exc}", file=sys.stderr)
        sys.exit(1)
