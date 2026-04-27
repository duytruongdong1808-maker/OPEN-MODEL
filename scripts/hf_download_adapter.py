from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_ADAPTER_PATH = Path("outputs/qwen2.5_1.5b_lora/final_adapter")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a trained LoRA adapter from Hugging Face.")
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
        print("Missing dependency: huggingface_hub. Install with `pip install -r requirements.txt`.")
        return 1

    adapter_path = args.adapter_path.expanduser().resolve()
    adapter_path.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=args.repo_id,
        repo_type="model",
        revision=args.revision,
        local_dir=str(adapter_path),
        allow_patterns=[
            "adapter_config.json",
            "adapter_model.safetensors",
            "chat_template.jinja",
            "README.md",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ],
    )
    print(f"Downloaded adapter to: {adapter_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
