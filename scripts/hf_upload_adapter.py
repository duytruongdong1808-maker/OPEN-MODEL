from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ADAPTER_PATH = Path("outputs/qwen2.5_1.5b_lora/final_adapter")
DEFAULT_MERGED_PATH = Path("outputs/qwen2.5_1.5b_lora/merged")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload the trained LoRA adapter or merged model to Hugging Face."
    )
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
        "--artifact",
        choices=("adapter", "merged"),
        default="adapter",
        help="Upload the LoRA adapter or the merged full model. Defaults to adapter.",
    )
    parser.add_argument(
        "--merged-path",
        type=Path,
        default=DEFAULT_MERGED_PATH,
        help=f"Local merged model folder to upload. Defaults to {DEFAULT_MERGED_PATH}.",
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
        default=None,
        help="Commit message for the Hub upload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from huggingface_hub import HfApi
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
    required_file = (
        "adapter_model.safetensors" if args.artifact == "adapter" else "model.safetensors"
    )
    if not artifact_path.exists():
        print(f"{args.artifact.title()} path not found: {artifact_path}")
        return 1
    if not (artifact_path / required_file).exists():
        print(f"Missing {required_file} in: {artifact_path}")
        return 1

    api = HfApi()
    api.create_repo(repo_id=args.repo_id, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=args.repo_id,
        repo_type="model",
        folder_path=str(artifact_path),
        revision=args.revision,
        commit_message=args.commit_message or f"Upload trained {args.artifact} artifact",
    )
    print(f"Uploaded {args.artifact} folder to https://huggingface.co/{args.repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
