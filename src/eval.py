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
DEFAULT_SAMPLE_PROMPTS = [
    {
        "instruction": "Summarize the value of LoRA in one sentence.",
        "input": "",
    },
    {
        "instruction": "Rewrite the message to sound more professional.",
        "input": "can you send me the report today? i need it before lunch",
    },
    {
        "instruction": "Explain QLoRA simply.",
        "input": "",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a quick local inference check with the fine-tuned adapter.")
    parser.add_argument("--base_model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--adapter_path", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--max_new_tokens", type=int, default=200)
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

    for index, sample in enumerate(DEFAULT_SAMPLE_PROMPTS, start=1):
        response = generate_response(
            model=model,
            tokenizer=tokenizer,
            instruction=sample["instruction"],
            input_text=sample["input"],
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )

        print(f"\n=== Sample {index} ===")
        print(f"Instruction: {sample['instruction']}")
        if sample["input"]:
            print(f"Input: {sample['input']}")
        print(f"Response: {response}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[eval] Error: {exc}", file=sys.stderr)
        sys.exit(1)
