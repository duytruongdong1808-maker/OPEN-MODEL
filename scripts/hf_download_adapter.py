from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ADAPTER_PATH = Path("outputs/qwen2.5_1.5b_lora/final_adapter")
DEFAULT_MERGED_PATH = Path("outputs/qwen2.5_1.5b_lora/merged")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a trained LoRA adapter or merged model from Hugging Face."
    )
    parser.add_argument(
        "repo_id",
        help="Source Hugging Face model repo, for example: username/open-model-qwen25-lora",
    )
    parser.add_argument(
        "--adapter-path",
        type=Path,
        default=DEFAULT_ADAPTER_PATH,
        help=f"Local adapter folder to populate. Defaults to {DEFAULT_ADAPTER_PATH}.",
    )
    parser.add_argument(
        "--artifact",
        choices=("adapter", "merged"),
        default="adapter",
        help="Download the LoRA adapter or the merged full model. Defaults to adapter.",
    )
    parser.add_argument(
        "--merged-path",
        type=Path,
        default=DEFAULT_MERGED_PATH,
        help=f"Local merged model folder to populate. Defaults to {DEFAULT_MERGED_PATH}.",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional branch, tag, or commit to download.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError:
        print(
            "Missing dependency: huggingface_hub. Install with `pip install -r requirements.txt`."
        )
        return 1

    artifact_path = (
        (args.adapter_path if args.artifact == "adapter" else args.merged_path)
        .expanduser()
        .resolve()
    )
    artifact_path.mkdir(parents=True, exist_ok=True)
    allow_patterns = (
        [
            "adapter_config.json",
            "adapter_model.safetensors",
            "chat_template.jinja",
            "README.md",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ]
        if args.artifact == "adapter"
        else [
            "chat_template.jinja",
            "config.json",
            "generation_config.json",
            "model.safetensors",
            "README.md",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ]
    )
    snapshot_download(
        repo_id=args.repo_id,
        repo_type="model",
        revision=args.revision,
        local_dir=str(artifact_path),
        allow_patterns=allow_patterns,
    )
    print(f"Downloaded {args.artifact} to: {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
