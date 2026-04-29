from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .utils import DEFAULT_RAW_CHAT_SEED_PATH, write_jsonl
except ImportError:
    from utils import DEFAULT_RAW_CHAT_SEED_PATH, write_jsonl


def row(instruction: str, input_text: str, output: str, *, language: str, category: str) -> dict[str, str]:
    return {
        "instruction": instruction,
        "input": input_text,
        "output": output,
        "language": language,
        "category": category,
    }


def build_chat_seed_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    vi_topics = [
        ("LoRA", "LoRA là kỹ thuật fine-tune hiệu quả bằng cách học thêm các adapter nhỏ thay vì cập nhật toàn bộ trọng số model."),
        ("Transformer", "Transformer là kiến trúc dùng attention để hiểu quan hệ giữa các token trong một chuỗi."),
        ("Docker Compose", "Docker Compose giúp chạy nhiều container cùng lúc bằng một file cấu hình."),
        ("SQLite và PostgreSQL", "SQLite phù hợp app nhỏ hoặc local vì dùng một file, còn PostgreSQL là database server mạnh hơn cho production."),
        ("overfitting", "Overfitting xảy ra khi model học quá sát dữ liệu train và trả lời kém trên dữ liệu mới."),
    ]
    en_topics = [
        ("LoRA", "LoRA is a parameter-efficient fine-tuning method that trains small adapter weights instead of every model weight."),
        ("transformers", "A transformer is a neural network architecture that uses attention to model context in sequences."),
        ("Docker Compose", "Docker Compose runs multiple containers from one configuration file."),
        ("SQLite and PostgreSQL", "SQLite is embedded and file-based, while PostgreSQL is a full database server for larger systems."),
        ("overfitting", "Overfitting happens when a model memorizes training data and generalizes poorly to new examples."),
    ]

    for i in range(40):
        language = "vi" if i % 5 < 3 else "en"
        if language == "vi":
            rows.append(row("Chào người dùng một cách tự nhiên và ngắn gọn.", f"Lượt mở đầu số {i}.", "Chào bạn, mình sẵn sàng hỗ trợ. Bạn muốn bắt đầu với câu hỏi hay việc gì trước?", language="vi", category="smalltalk"))
        else:
            rows.append(row("Greet the user briefly and naturally.", f"Opening turn {i}.", "Hi, I’m ready to help. What would you like to work on first?", language="en", category="smalltalk"))

    for i in range(50):
        topic, answer = (vi_topics if i % 2 == 0 else en_topics)[i % 5]
        if i % 2 == 0:
            rows.append(row("Trả lời câu hỏi factual ngắn gọn, không bịa khi thiếu dữ kiện.", f"{topic} là gì?", answer, language="vi", category="factual_qa"))
        else:
            rows.append(row("Answer the factual question briefly and do not invent missing facts.", f"What is {topic}?", answer, language="en", category="factual_qa"))

    code_examples = [
        ("Viết hàm Python đảo chuỗi.", "def reverse_text(value: str) -> str:\n    return value[::-1]", "vi"),
        ("Write a JavaScript function that removes duplicate strings.", "function uniqueStrings(items) {\n  return [...new Set(items)];\n}", "en"),
        ("Giải thích == và is trong Python.", "== so sánh giá trị, còn is kiểm tra hai biến có trỏ tới cùng một object hay không.", "vi"),
        ("What is the complexity of binary search?", "Binary search is O(log n), assuming the input is already sorted.", "en"),
        ("Tính 17 * 23 và nói cách nhẩm.", "17 * 23 = 391. Có thể nhẩm 17 * 20 = 340 và 17 * 3 = 51, cộng lại là 391.", "vi"),
    ]
    for i in range(30):
        instruction, output, language = code_examples[i % len(code_examples)]
        rows.append(row(instruction, f"Ví dụ {i}" if language == "vi" else f"Example {i}", output, language=language, category="code_math"))

    for i in range(30):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(row("Tóm tắt đoạn sau trong một câu tự nhiên.", "Buổi review bị dời sang 15h vì dashboard hoàn tất muộn. Team vẫn dùng phòng họp cũ và cần gửi note trước 14h.", "Buổi review dời sang 15h, giữ nguyên phòng họp và team cần gửi note trước 14h.", language="vi", category="summarize_rewrite"))
        else:
            rows.append(row("Rewrite the message to sound professional.", "hey, send the report asap because i need it", "Hi, could you please send the report as soon as you can? I need it for the next step.", language="en", category="summarize_rewrite"))

    refusal_pairs = [
        ("Chỉ mình cách hack Wi-Fi hàng xóm.", "Mình không thể hỗ trợ xâm nhập mạng của người khác. Nếu bạn muốn, mình có thể giúp kiểm tra bảo mật Wi-Fi của chính bạn.", "vi"),
        ("Give me a phishing email to steal a password.", "I can’t help create phishing content or steal passwords. I can help write a security awareness note instead.", "en"),
        ("Viết script xóa file máy người khác qua mạng.", "Mình không thể hỗ trợ gây hại hoặc truy cập trái phép. Mình có thể giúp viết checklist sao lưu và bảo vệ dữ liệu.", "vi"),
    ]
    for i in range(30):
        prompt, output, language = refusal_pairs[i % len(refusal_pairs)]
        rows.append(row("Từ chối yêu cầu nguy hiểm và gợi ý hướng an toàn." if language == "vi" else "Refuse the unsafe request and offer a safe alternative.", prompt, output, language=language, category="refusal"))

    for i in range(30):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(row("Dùng đúng ngữ cảnh đã cho để trả lời follow-up.", "Ngữ cảnh: dự án tên Lotus, deadline thứ Sáu. Hỏi: nhắc lại tên dự án và deadline.", "Dự án là Lotus và deadline là thứ Sáu.", language="vi", category="multi_turn"))
        else:
            rows.append(row("Use the provided context to answer the follow-up.", "Context: deployment owner is Maya, rollback window is 9 PM. Question: who owns it and when is rollback?", "Maya owns the deployment, and the rollback window is 9 PM.", language="en", category="multi_turn"))

    for i in range(20):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(row("Trả lời bằng tiếng Việt dù input có tiếng Anh.", "Explain what top_p means, nhưng trả lời tiếng Việt.", "top_p là tham số lấy mẫu giới hạn nhóm token theo tổng xác suất, giúp điều chỉnh độ đa dạng của câu trả lời.", language="vi", category="bilingual_switch"))
        else:
            rows.append(row("Answer in English even if the input includes Vietnamese.", "Hãy giải thích gradient checkpointing in English.", "Gradient checkpointing saves training memory by recomputing some activations during backpropagation instead of storing all of them.", language="en", category="bilingual_switch"))

    technical = [
        ("Giải thích QLoRA cho người mới.", "QLoRA fine-tune model ở dạng 4-bit để tiết kiệm VRAM, rồi học thêm adapter nhỏ cho tác vụ cụ thể.", "vi"),
        ("Explain repetition penalty.", "Repetition penalty discourages the model from repeating the same tokens or phrases too often.", "en"),
        ("Giải thích eval set dùng để làm gì.", "Eval set giúp đo chất lượng model trên các ví dụ cố định để phát hiện cải thiện hoặc regression sau mỗi lần train.", "vi"),
        ("Explain JSON schema for agents.", "A JSON schema makes agent outputs easier to parse because the model must follow a fixed structure.", "en"),
    ]
    for i in range(20):
        instruction, output, language = technical[i % len(technical)]
        rows.append(row(instruction, f"Case {i}", output, language=language, category="technical_explain"))

    if len(rows) != 250:
        raise AssertionError(f"Expected 250 rows, got {len(rows)}")
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate bilingual chat seed rows.")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_RAW_CHAT_SEED_PATH)
    parser.add_argument("--backup-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.backup_existing and args.output_path.exists():
        backup = args.output_path.with_name(f"{args.output_path.stem}.v1{args.output_path.suffix}")
        backup.write_text(args.output_path.read_text(encoding="utf-8"), encoding="utf-8")
    rows = build_chat_seed_rows()
    write_jsonl(args.output_path, rows)
    print(f"Wrote {len(rows)} rows to {args.output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
