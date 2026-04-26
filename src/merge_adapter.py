from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        format_missing_dependency_error,
        get_default_adapter_path,
        get_compute_dtype,
        get_logger,
        load_tokenizer,
        resolve_model_revision,
        sync_model_tokenizer_padding,
    )
except ImportError:
    from utils import (
        DEFAULT_BASE_MODEL,
        DEFAULT_LOG_LEVEL,
        LOG_LEVEL_NAMES,
        configure_logging,
        format_missing_dependency_error,
        get_default_adapter_path,
        get_compute_dtype,
        get_logger,
        load_tokenizer,
        resolve_model_revision,
        sync_model_tokenizer_padding,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into the base model.")
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter_path", type=Path, default=None)
    parser.add_argument("--output_dir", type=Path, default=None)
    parser.add_argument("--model_revision", type=str, default=None)
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=LOG_LEVEL_NAMES,
        default=DEFAULT_LOG_LEVEL,
        help="Logging verbosity.",
    )
    args = parser.parse_args()
    if args.adapter_path is None:
        args.adapter_path = get_default_adapter_path(args.base_model)
    return args


def resolve_output_dir(adapter_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    return adapter_path.expanduser().resolve().parent / "merged"


def main() -> int:
    logger = configure_logging()

    try:
        from peft import PeftModel
        import torch
        from transformers import AutoModelForCausalLM

        args = parse_args()
        logger = configure_logging(args.log_level)
        adapter_path = args.adapter_path.expanduser().resolve()
        if not adapter_path.exists():
            raise FileNotFoundError(f"Adapter path not found: {adapter_path}")

        output_dir = resolve_output_dir(adapter_path, args.output_dir)
        tokenizer = load_tokenizer(args.base_model, model_revision=args.model_revision)
        model_kwargs = {
            "trust_remote_code": False,
            "torch_dtype": get_compute_dtype(),
        }
        if torch.cuda.is_available():
            model_kwargs["device_map"] = "auto"
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            revision=resolve_model_revision(args.base_model, args.model_revision),
            **model_kwargs,
        )
        sync_model_tokenizer_padding(model, tokenizer)

        merged_model = PeftModel.from_pretrained(model, str(adapter_path)).merge_and_unload()
        output_dir.mkdir(parents=True, exist_ok=True)
        merged_model.save_pretrained(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))

        logger.info("Merged adapter from: %s", adapter_path)
        logger.info("Saved merged model to: %s", output_dir)
        return 0
    except ModuleNotFoundError as exc:
        get_logger().error("[merge_adapter] Error: %s", format_missing_dependency_error(exc))
        return 1
    except Exception as exc:
        get_logger().error("[merge_adapter] Error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
