from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_ADAPTER_PATH = Path("outputs/qwen2.5_1.5b_lora/final_adapter")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload the trained LoRA adapter to Hugging Face.")
    parser.add_argument(
        "repo_id",
        help="Target Hugging Face model repo, for example: username/open-model-qwen25-lora",
    )
    parser.add_argument(
        "--adapter-path",
        type=Path,
        default=DEFAULT_ADAPTER_PATH,
        help=f"Local adapter folder to upload. Defaults to {DEFAULT_ADAPTER_PATH}.",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Create the Hugging Face repo as private if it does not exist.",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional branch or revision to upload to.",
    )
    parser.add_argument(
        "--commit-message",
        default="Upload trained LoRA adapter",
        help="Commit message for the Hub upload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from huggingface_hub import HfApi
    except ModuleNotFoundError:
        print("Missing dependency: huggingface_hub. Install with `pip install -r requirements.txt`.")
        return 1

    adapter_path = args.adapter_path.expanduser().resolve()
    if not adapter_path.exists():
        print(f"Adapter path not found: {adapter_path}")
        return 1
    if not (adapter_path / "adapter_model.safetensors").exists():
        print(f"Missing adapter_model.safetensors in: {adapter_path}")
        return 1

    api = HfApi()
    api.create_repo(repo_id=args.repo_id, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=args.repo_id,
        repo_type="model",
        folder_path=str(adapter_path),
        revision=args.revision,
        commit_message=args.commit_message,
    )
    print(f"Uploaded adapter folder to https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
