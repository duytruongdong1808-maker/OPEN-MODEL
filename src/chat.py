from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utils import (
    DEFAULT_BASE_MODEL,
    ROOT_DIR,
    generate_response,
    load_model_and_tokenizer,
    str_to_bool,
)


DEFAULT_ADAPTER_PATH = ROOT_DIR / "outputs" / "smollm2_1.7b_lora" / "final_adapter"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a basic local chat loop with the fine-tuned model.")
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter_path", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument(
        "--load_in_4bit",
        type=str_to_bool,
        default=True,
        help="Load the base model in 4-bit when CUDA is available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.adapter_path.exists():
        raise FileNotFoundError(
            f"Adapter path not found: {args.adapter_path}. Train the model first or pass --adapter_path."
        )

    model, tokenizer = load_model_and_tokenizer(
        base_model=args.base_model,
        adapter_path=str(args.adapter_path),
        load_in_4bit=args.load_in_4bit,
    )

    print("Local chat is ready.")
    print("Each prompt is handled as a fresh single-turn instruction.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        user_text = input("You: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        response = generate_response(
            model=model,
            tokenizer=tokenizer,
            instruction=user_text,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )
        print(f"Assistant: {response}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[chat] Stopped by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"[chat] Error: {exc}", file=sys.stderr)
        sys.exit(1)
