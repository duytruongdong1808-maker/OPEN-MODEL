from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed

# `trl` reads package template files using the interpreter's default text
# encoding. On Windows that may be a legacy code page like cp1252, which breaks
# when those files are UTF-8. Re-exec the script in UTF-8 mode so users can run
# `python train_lora.py` without extra flags.
if (
    __name__ == "__main__"
    and sys.platform == "win32"
    and os.environ.get("PYTHONUTF8") != "1"
):
    os.execve(
        sys.executable,
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]],
        {**os.environ, "PYTHONUTF8": "1"},
    )

from trl import SFTConfig, SFTTrainer

try:
    from .utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        collect_cli_option_names,
        configure_logging,
        get_compute_dtype,
        get_logger,
        get_runtime_preset_names,
        load_tokenizer,
        log_runtime_mode,
        read_yaml_dict,
        resolve_model_revision,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
        sync_model_tokenizer_padding,
    )
except ImportError:
    from utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        DEFAULT_RUNTIME_PRESET,
        LOG_LEVEL_NAMES,
        ROOT_DIR,
        collect_cli_option_names,
        configure_logging,
        get_compute_dtype,
        get_logger,
        get_runtime_preset_names,
        load_tokenizer,
        log_runtime_mode,
        read_yaml_dict,
        resolve_model_revision,
        resolve_runtime_preset,
        should_default_to_4bit,
        str_to_bool,
        sync_model_tokenizer_padding,
    )


DEFAULT_DATASET_PATH = ROOT_DIR / "data" / "processed" / "train_sft.jsonl"
DEFAULT_EVAL_DATASET_PATH = ROOT_DIR / "data" / "processed" / "val_sft.jsonl"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs" / "qwen2.5_1.5b_lora"
DEFAULT_MAX_LENGTH = 512
DEFAULT_REPORT_TO = "none"
TRAIN_CONFIG_FIELDS = {
    "base_model",
    "dataset_path",
    "eval_dataset_path",
    "output_dir",
    "preset",
    "max_length",
    "num_train_epochs",
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "learning_rate",
    "warmup_ratio",
    "logging_steps",
    "save_steps",
    "save_total_limit",
    "seed",
    "lora_r",
    "lora_alpha",
    "lora_dropout",
    "model_revision",
    "load_in_4bit",
    "resume_from_checkpoint",
    "report_to",
    "log_level",
}
DEFAULT_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def load_training_config(config_path: Path | None) -> dict[str, object]:
    if config_path is None:
        return {}

    raw_config = read_yaml_dict(config_path)
    unknown_keys = sorted(set(raw_config) - TRAIN_CONFIG_FIELDS)
    if unknown_keys:
        raise ValueError(f"Unknown training config keys: {', '.join(unknown_keys)}")

    normalized_config: dict[str, object] = {}
    for key, value in raw_config.items():
        if key in {"dataset_path", "eval_dataset_path", "output_dir"} and value is not None:
            normalized_config[key] = Path(value)
        elif key == "load_in_4bit" and value is not None:
            normalized_config[key] = str_to_bool(value)
        elif key == "log_level" and value is not None:
            normalized_config[key] = str(value).upper()
        elif key == "report_to" and value is not None:
            normalized_config[key] = str(value).lower()
        else:
            normalized_config[key] = value

    if normalized_config.get("preset") not in {None, *get_runtime_preset_names()}:
        raise ValueError(f"Unknown preset in config: {normalized_config['preset']}")
    if normalized_config.get("report_to") not in {None, "none", "tensorboard", "wandb"}:
        raise ValueError(f"Unknown report_to value in config: {normalized_config['report_to']}")
    if normalized_config.get("log_level") not in {None, *LOG_LEVEL_NAMES}:
        raise ValueError(f"Unknown log_level in config: {normalized_config['log_level']}")
    return normalized_config


def build_parser(config_defaults: dict[str, object]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fine-tune a small open model with LoRA or QLoRA.")
    parser.add_argument("--config", type=Path, default=config_defaults.get("config"))
    parser.add_argument("--base_model", type=str, default=config_defaults.get("base_model", DEFAULT_BASE_MODEL))
    parser.add_argument(
        "--dataset_path",
        type=Path,
        default=config_defaults.get("dataset_path", DEFAULT_DATASET_PATH),
    )
    parser.add_argument(
        "--eval_dataset_path",
        type=Path,
        default=config_defaults.get("eval_dataset_path", DEFAULT_EVAL_DATASET_PATH),
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=config_defaults.get("output_dir", DEFAULT_OUTPUT_DIR),
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=get_runtime_preset_names(),
        default=config_defaults.get("preset"),
        help=f"Optional hardware preset, for example {DEFAULT_RUNTIME_PRESET}.",
    )
    parser.add_argument("--max_length", type=int, default=config_defaults.get("max_length"))
    parser.add_argument("--num_train_epochs", type=float, default=config_defaults.get("num_train_epochs", 3.0))
    parser.add_argument(
        "--per_device_train_batch_size",
        type=int,
        default=config_defaults.get("per_device_train_batch_size"),
    )
    parser.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=config_defaults.get("gradient_accumulation_steps"),
    )
    parser.add_argument("--learning_rate", type=float, default=config_defaults.get("learning_rate", 1e-4))
    parser.add_argument("--warmup_ratio", type=float, default=config_defaults.get("warmup_ratio", 0.03))
    parser.add_argument("--logging_steps", type=int, default=config_defaults.get("logging_steps", 10))
    parser.add_argument("--save_steps", type=int, default=config_defaults.get("save_steps", 50))
    parser.add_argument("--save_total_limit", type=int, default=config_defaults.get("save_total_limit", 2))
    parser.add_argument("--seed", type=int, default=config_defaults.get("seed", 42))
    parser.add_argument("--lora_r", type=int, default=config_defaults.get("lora_r", 16))
    parser.add_argument("--lora_alpha", type=int, default=config_defaults.get("lora_alpha", 32))
    parser.add_argument("--lora_dropout", type=float, default=config_defaults.get("lora_dropout", 0.05))
    parser.add_argument(
        "--model_revision",
        type=str,
        default=config_defaults.get("model_revision"),
        help="Optional Hugging Face revision override for the base model.",
    )
    parser.add_argument(
        "--load_in_4bit",
        type=str_to_bool,
        default=config_defaults.get("load_in_4bit"),
        help="Use 4-bit QLoRA when the local environment supports it.",
    )
    parser.add_argument(
        "--resume_from_checkpoint",
        type=str,
        default=config_defaults.get("resume_from_checkpoint"),
        help="Optional checkpoint path inside outputs/ to resume training.",
    )
    parser.add_argument(
        "--report_to",
        type=str,
        choices=["none", "tensorboard", "wandb"],
        default=config_defaults.get("report_to", DEFAULT_REPORT_TO),
        help="Metric reporting backend.",
    )
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=config_defaults.get("log_level", DEFAULT_LOG_LEVEL),
        help="Logging verbosity.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    effective_argv = sys.argv[1:] if argv is None else argv
    initial_parser = argparse.ArgumentParser(add_help=False)
    initial_parser.add_argument("--config", type=Path, default=None)
    initial_args, _ = initial_parser.parse_known_args(effective_argv)
    config_values = load_training_config(initial_args.config)
    parser = build_parser(config_values)
    args = parser.parse_args(effective_argv)
    explicit_option_names = collect_cli_option_names(effective_argv)
    args.load_in_4bit_was_set = "load_in_4bit" in explicit_option_names or "load_in_4bit" in config_values
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


def jsonl_has_rows(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def validate_environment(args: argparse.Namespace) -> None:
    if not jsonl_has_rows(args.dataset_path):
        raise FileNotFoundError(
            f"Processed dataset not found: {args.dataset_path}. Run src/prepare_data.py first."
        )

    if args.load_in_4bit and not torch.cuda.is_available():
        raise EnvironmentError(
            "4-bit QLoRA requires a CUDA-enabled GPU. On Windows, use WSL/Linux for the cleanest setup. "
            "If you still want to test the script flow, rerun with --load_in_4bit false."
        )


def load_model(args: argparse.Namespace, tokenizer):
    compute_dtype = get_compute_dtype()
    model_kwargs = {"trust_remote_code": False}
    model_revision = resolve_model_revision(args.base_model, args.model_revision)

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

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        revision=model_revision,
        **model_kwargs,
    )
    sync_model_tokenizer_padding(model, tokenizer)
    if args.load_in_4bit:
        model = prepare_model_for_kbit_training(model)

    model.config.use_cache = False
    return model


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.log_level)

    try:
        if args.preset:
            logger.info("Using preset: %s", args.preset)
        log_runtime_mode(logger, args.load_in_4bit, args.load_in_4bit_was_set)
        validate_environment(args)
        set_seed(args.seed)

        tokenizer = load_tokenizer(args.base_model, model_revision=args.model_revision)
        dataset = load_dataset("json", data_files=str(args.dataset_path), split="train")
        eval_dataset = None
        if jsonl_has_rows(args.eval_dataset_path):
            eval_dataset = load_dataset("json", data_files=str(args.eval_dataset_path), split="train")
        else:
            logger.warning("Validation dataset not found or empty at: %s. Skipping eval.", args.eval_dataset_path)
        model = load_model(args, tokenizer)
        logger.debug("train_lora args: %s", vars(args))
        logger.debug(
            "Tokenizer config: %s",
            {
                "base_model": args.base_model,
                "model_revision": resolve_model_revision(args.base_model, args.model_revision),
                "pad_token": tokenizer.pad_token,
                "pad_token_id": tokenizer.pad_token_id,
                "padding_side": tokenizer.padding_side,
                "dataset_path": str(args.dataset_path),
                "eval_dataset_path": str(args.eval_dataset_path),
                "config": str(args.config) if args.config else None,
            },
        )
        logger.debug(
            "Model config: %s",
            {
                "model_type": getattr(model.config, "model_type", None),
                "pad_token_id": getattr(model.config, "pad_token_id", None),
                "vocab_size": getattr(model.config, "vocab_size", None),
                "torch_dtype": str(getattr(model.config, "torch_dtype", None)),
            },
        )

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
        eval_enabled = eval_dataset is not None

        training_args = SFTConfig(
            output_dir=str(args.output_dir),
            max_length=args.max_length,
            num_train_epochs=args.num_train_epochs,
            per_device_train_batch_size=args.per_device_train_batch_size,
            gradient_accumulation_steps=args.gradient_accumulation_steps,
            learning_rate=args.learning_rate,
            warmup_ratio=args.warmup_ratio,
            lr_scheduler_type="cosine",
            seed=args.seed,
            data_seed=args.seed,
            logging_steps=args.logging_steps,
            eval_strategy="steps" if eval_enabled else "no",
            eval_steps=args.save_steps if eval_enabled else None,
            save_steps=args.save_steps,
            save_strategy="steps",
            save_total_limit=args.save_total_limit,
            load_best_model_at_end=eval_enabled,
            metric_for_best_model="eval_loss" if eval_enabled else None,
            gradient_checkpointing=True,
            bf16=bf16_enabled,
            fp16=fp16_enabled,
            per_device_eval_batch_size=args.per_device_train_batch_size,
            report_to=args.report_to,
            optim="paged_adamw_8bit" if args.load_in_4bit else "adamw_torch",
            remove_unused_columns=False,
            # TRL's prompt-completion path creates a completion mask and its collator
            # masks both prompt tokens and padded positions to -100 before loss.
            completion_only_loss=True,
            packing=False,
        )

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
            peft_config=peft_config,
        )

        trainer.model.print_trainable_parameters()
        trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

        final_adapter_dir = args.output_dir / "final_adapter"
        final_adapter_dir.mkdir(parents=True, exist_ok=True)
        trainer.model.save_pretrained(str(final_adapter_dir))
        tokenizer.save_pretrained(str(final_adapter_dir))

        logger.info("Training finished.")
        logger.info("Checkpoints saved under: %s", args.output_dir.resolve())
        logger.info("Final adapter saved to: %s", final_adapter_dir.resolve())
        return 0
    except Exception as exc:
        get_logger().error("[train_lora] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
