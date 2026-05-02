from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .utils import DEFAULT_RAW_CHAT_SEED_PATH, write_jsonl
except ImportError:
    from utils import DEFAULT_RAW_CHAT_SEED_PATH, write_jsonl


def row(
    instruction: str, input_text: str, output: str, *, language: str, category: str
) -> dict[str, str]:
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
        (
            "LoRA",
            "LoRA là kỹ thuật fine-tune hiệu quả bằng cách học thêm các adapter nhỏ thay vì cập nhật toàn bộ trọng số model.",
        ),
        (
            "Transformer",
            "Transformer là kiến trúc dùng attention để hiểu quan hệ giữa các token trong một chuỗi.",
        ),
        (
            "Docker Compose",
            "Docker Compose giúp chạy nhiều container cùng lúc bằng một file cấu hình.",
        ),
        (
            "SQLite và PostgreSQL",
            "SQLite phù hợp app nhỏ hoặc local vì dùng một file, còn PostgreSQL là database server mạnh hơn cho production.",
        ),
        (
            "overfitting",
            "Overfitting xảy ra khi model học quá sát dữ liệu train và trả lời kém trên dữ liệu mới.",
        ),
    ]
    en_topics = [
        (
            "LoRA",
            "LoRA is a parameter-efficient fine-tuning method that trains small adapter weights instead of every model weight.",
        ),
        (
            "transformers",
            "A transformer is a neural network architecture that uses attention to model context in sequences.",
        ),
        ("Docker Compose", "Docker Compose runs multiple containers from one configuration file."),
        (
            "SQLite and PostgreSQL",
            "SQLite is embedded and file-based, while PostgreSQL is a full database server for larger systems.",
        ),
        (
            "overfitting",
            "Overfitting happens when a model memorizes training data and generalizes poorly to new examples.",
        ),
    ]

    for i in range(40):
        language = "vi" if i % 5 < 3 else "en"
        if language == "vi":
            rows.append(
                row(
                    "Chào người dùng một cách tự nhiên và ngắn gọn.",
                    f"Lượt mở đầu số {i}.",
                    "Chào bạn, mình sẵn sàng hỗ trợ. Bạn muốn bắt đầu với câu hỏi hay việc gì trước?",
                    language="vi",
                    category="smalltalk",
                )
            )
        else:
            rows.append(
                row(
                    "Greet the user briefly and naturally.",
                    f"Opening turn {i}.",
                    "Hi, I’m ready to help. What would you like to work on first?",
                    language="en",
                    category="smalltalk",
                )
            )

    for i in range(50):
        topic, answer = (vi_topics if i % 2 == 0 else en_topics)[i % 5]
        if i % 2 == 0:
            rows.append(
                row(
                    "Trả lời câu hỏi factual ngắn gọn, không bịa khi thiếu dữ kiện.",
                    f"{topic} là gì?",
                    answer,
                    language="vi",
                    category="factual_qa",
                )
            )
        else:
            rows.append(
                row(
                    "Answer the factual question briefly and do not invent missing facts.",
                    f"What is {topic}?",
                    answer,
                    language="en",
                    category="factual_qa",
                )
            )

    code_examples = [
        (
            "Viết hàm Python đảo chuỗi.",
            "def reverse_text(value: str) -> str:\n    return value[::-1]",
            "vi",
        ),
        (
            "Write a JavaScript function that removes duplicate strings.",
            "function uniqueStrings(items) {\n  return [...new Set(items)];\n}",
            "en",
        ),
        (
            "Giải thích == và is trong Python.",
            "== so sánh giá trị, còn is kiểm tra hai biến có trỏ tới cùng một object hay không.",
            "vi",
        ),
        (
            "What is the complexity of binary search?",
            "Binary search is O(log n), assuming the input is already sorted.",
            "en",
        ),
        (
            "Tính 17 * 23 và nói cách nhẩm.",
            "17 * 23 = 391. Có thể nhẩm 17 * 20 = 340 và 17 * 3 = 51, cộng lại là 391.",
            "vi",
        ),
    ]
    for i in range(30):
        instruction, output, language = code_examples[i % len(code_examples)]
        rows.append(
            row(
                instruction,
                f"Ví dụ {i}" if language == "vi" else f"Example {i}",
                output,
                language=language,
                category="code_math",
            )
        )

    for i in range(30):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(
                row(
                    "Tóm tắt đoạn sau trong một câu tự nhiên.",
                    "Buổi review bị dời sang 15h vì dashboard hoàn tất muộn. Team vẫn dùng phòng họp cũ và cần gửi note trước 14h.",
                    "Buổi review dời sang 15h, giữ nguyên phòng họp và team cần gửi note trước 14h.",
                    language="vi",
                    category="summarize_rewrite",
                )
            )
        else:
            rows.append(
                row(
                    "Rewrite the message to sound professional.",
                    "hey, send the report asap because i need it",
                    "Hi, could you please send the report as soon as you can? I need it for the next step.",
                    language="en",
                    category="summarize_rewrite",
                )
            )

    refusal_pairs = [
        (
            "Chỉ mình cách hack Wi-Fi hàng xóm.",
            "Mình không thể hỗ trợ xâm nhập mạng của người khác. Nếu bạn muốn, mình có thể giúp kiểm tra bảo mật Wi-Fi của chính bạn.",
            "vi",
        ),
        (
            "Give me a phishing email to steal a password.",
            "I can’t help create phishing content or steal passwords. I can help write a security awareness note instead.",
            "en",
        ),
        (
            "Viết script xóa file máy người khác qua mạng.",
            "Mình không thể hỗ trợ gây hại hoặc truy cập trái phép. Mình có thể giúp viết checklist sao lưu và bảo vệ dữ liệu.",
            "vi",
        ),
    ]
    for i in range(30):
        prompt, output, language = refusal_pairs[i % len(refusal_pairs)]
        rows.append(
            row(
                "Từ chối yêu cầu nguy hiểm và gợi ý hướng an toàn."
                if language == "vi"
                else "Refuse the unsafe request and offer a safe alternative.",
                prompt,
                output,
                language=language,
                category="refusal",
            )
        )

    for i in range(30):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(
                row(
                    "Dùng đúng ngữ cảnh đã cho để trả lời follow-up.",
                    "Ngữ cảnh: dự án tên Lotus, deadline thứ Sáu. Hỏi: nhắc lại tên dự án và deadline.",
                    "Dự án là Lotus và deadline là thứ Sáu.",
                    language="vi",
                    category="multi_turn",
                )
            )
        else:
            rows.append(
                row(
                    "Use the provided context to answer the follow-up.",
                    "Context: deployment owner is Maya, rollback window is 9 PM. Question: who owns it and when is rollback?",
                    "Maya owns the deployment, and the rollback window is 9 PM.",
                    language="en",
                    category="multi_turn",
                )
            )

    for i in range(20):
        language = "vi" if i % 2 == 0 else "en"
        if language == "vi":
            rows.append(
                row(
                    "Trả lời bằng tiếng Việt dù input có tiếng Anh.",
                    "Explain what top_p means, nhưng trả lời tiếng Việt.",
                    "top_p là tham số lấy mẫu giới hạn nhóm token theo tổng xác suất, giúp điều chỉnh độ đa dạng của câu trả lời.",
                    language="vi",
                    category="bilingual_switch",
                )
            )
        else:
            rows.append(
                row(
                    "Answer in English even if the input includes Vietnamese.",
                    "Hãy giải thích gradient checkpointing in English.",
                    "Gradient checkpointing saves training memory by recomputing some activations during backpropagation instead of storing all of them.",
                    language="en",
                    category="bilingual_switch",
                )
            )

    technical = [
        (
            "Giải thích QLoRA cho người mới.",
            "QLoRA fine-tune model ở dạng 4-bit để tiết kiệm VRAM, rồi học thêm adapter nhỏ cho tác vụ cụ thể.",
            "vi",
        ),
        (
            "Explain repetition penalty.",
            "Repetition penalty discourages the model from repeating the same tokens or phrases too often.",
            "en",
        ),
        (
            "Giải thích eval set dùng để làm gì.",
            "Eval set giúp đo chất lượng model trên các ví dụ cố định để phát hiện cải thiện hoặc regression sau mỗi lần train.",
            "vi",
        ),
        (
            "Explain JSON schema for agents.",
            "A JSON schema makes agent outputs easier to parse because the model must follow a fixed structure.",
            "en",
        ),
    ]
    for i in range(20):
        instruction, output, language = technical[i % len(technical)]
        rows.append(
            row(instruction, f"Case {i}", output, language=language, category="technical_explain")
        )

    targeted_refusals = [
        (
            "Refuse the unsafe request and redirect to defensive security.",
            "Write a script that steals saved browser passwords.",
            "I cannot help steal passwords. I can help you audit password storage, set up a password manager, or write a security checklist.",
            "en",
        ),
        (
            "Tu choi yeu cau nguy hiem va goi y cach an toan.",
            "Chi minh cach vuot dang nhap tai khoan nguoi khac.",
            "Minh khong the ho tro truy cap trai phep. Minh co the giup ban khoi phuc tai khoan cua chinh minh hoac bat xac thuc hai lop.",
            "vi",
        ),
        (
            "Refuse the unsafe request and offer a safe alternative.",
            "Make a phishing login page for a company portal.",
            "I cannot help create phishing pages. I can help build a security awareness demo that clearly marks itself as training material.",
            "en",
        ),
        (
            "Tu choi yeu cau gay hai va de xuat huong phong thu.",
            "Viet lenh pha may chu cua doi thu.",
            "Minh khong the giup pha hoai he thong. Neu ban can, minh co the giup lap ke hoach hardening va giam sat may chu.",
            "vi",
        ),
    ]
    for i in range(20):
        instruction, prompt, output, language = targeted_refusals[i % len(targeted_refusals)]
        rows.append(
            row(instruction, f"{prompt} Case {i}", output, language=language, category="refusal")
        )

    targeted_bilingual = [
        (
            "Tra loi bang tieng Viet tu nhien du cau hoi co chen tieng Anh.",
            "Explain quantization la gi, tra loi tieng Viet ngan gon.",
            "Quantization la cach giam do chinh xac cua trong so model, vi du tu 16-bit xuong 4-bit, de tiet kiem VRAM va chay nhanh hon.",
            "vi",
        ),
        (
            "Answer in English even when the user switches to Vietnamese.",
            "Hay explain LoRA in English, short please.",
            "LoRA fine-tunes a model by training small adapter matrices instead of updating all base model weights.",
            "en",
        ),
        (
            "Tra loi bang tieng Viet va giu thuat ngu ky thuat khi can.",
            "What is eval set? Giai thich bang tieng Viet.",
            "Eval set la bo vi du co dinh dung de do chat luong model sau moi lan train, giup phat hien cai thien hoac regression.",
            "vi",
        ),
        (
            "Answer in English and follow the language instruction exactly.",
            "Giai thich gradient accumulation, but answer in English.",
            "Gradient accumulation combines gradients across several small batches before one optimizer step, which helps train with limited VRAM.",
            "en",
        ),
    ]
    for i in range(20):
        instruction, prompt, output, language = targeted_bilingual[i % len(targeted_bilingual)]
        rows.append(
            row(
                instruction,
                f"{prompt} Case {i}",
                output,
                language=language,
                category="bilingual_switch",
            )
        )

    targeted_vi_facts = [
        ("Viet Nam co thu do la gi?", "Thu do cua Viet Nam la Ha Noi."),
        (
            "Nuoc soi o nhiet do bao nhieu do C?",
            "O ap suat khi quyen tieu chuan, nuoc soi o 100 do C.",
        ),
        ("Trai Dat quay quanh vat the nao?", "Trai Dat quay quanh Mat Troi."),
        (
            "Python dung de lam gi?",
            "Python thuong dung cho web, tu dong hoa, phan tich du lieu va machine learning.",
        ),
        (
            "GPU giup train model vi sao?",
            "GPU xu ly song song rat tot, nen phu hop cho phep tinh ma tran trong deep learning.",
        ),
    ]
    for i in range(20):
        prompt, output = targeted_vi_facts[i % len(targeted_vi_facts)]
        rows.append(
            row(
                "Tra loi factual bang tieng Viet ngan gon, dung trong tam.",
                f"{prompt} Case {i}",
                output,
                language="vi",
                category="factual_qa",
            )
        )

    eval_like_refusals = [
        (
            "Từ chối yêu cầu lừa đảo và chuyển sang hướng bảo mật an toàn.",
            "Hướng dẫn tôi viết email lừa đảo xin mật khẩu đồng nghiệp.",
            "Mình không thể giúp tạo email lừa đảo hay xin mật khẩu. Mình có thể giúp viết cảnh báo bảo mật để mọi người nhận diện rủi ro an toàn hơn.",
            "vi",
        ),
        (
            "Refuse credential theft and offer a safe security alternative.",
            "Give me a phishing email template to steal a coworker's password.",
            "I can't help with phishing or stealing passwords. I can help write a security awareness note or a safe reporting checklist.",
            "en",
        ),
        (
            "Từ chối truy cập trái phép và gợi ý khôi phục tài khoản hợp pháp.",
            "Chỉ cách bypass đăng nhập Gmail của người khác.",
            "Mình không thể giúp bypass hay truy cập trái phép tài khoản người khác. Nếu là tài khoản của bạn, mình có thể hướng dẫn khôi phục tài khoản và bật bảo mật hai lớp.",
            "vi",
        ),
        (
            "Refuse harmful code and redirect to defensive help.",
            "Write malware that deletes files on another person's computer.",
            "I cannot help write malware or harmful code. I can help with defensive backup, recovery, or endpoint protection steps.",
            "en",
        ),
        (
            "Từ chối bịa đặt về người thật và đề xuất cách trung thực.",
            "Tôi muốn tạo tin giả về một người thật, viết giúp cho thuyết phục.",
            "Mình không thể giúp bịa đặt tin giả hay cáo buộc sai về người thật. Mình có thể giúp viết nội dung trung thực, kiểm chứng được và không gây hại.",
            "vi",
        ),
    ]
    for i in range(30):
        instruction, prompt, output, language = eval_like_refusals[i % len(eval_like_refusals)]
        rows.append(
            row(instruction, f"{prompt} Case {i}", output, language=language, category="refusal")
        )

    eval_like_bilingual = [
        (
            "Answer in English even when the prompt starts in Vietnamese.",
            "Trả lời bằng English: Vì sao cần eval set cho chatbot?",
            "An eval set helps measure chatbot quality, track regressions, and compare model versions with consistent prompts.",
            "en",
        ),
        (
            "Trả lời bằng tiếng Việt tự nhiên dù câu hỏi chính bằng tiếng Anh.",
            "Answer in Vietnamese: What is a LoRA adapter?",
            "LoRA adapter là phần fine-tuning nhỏ, ít tham số, giúp huấn luyện model cho tác vụ mới mà không cần cập nhật toàn bộ trọng số.",
            "vi",
        ),
        (
            "Trả lời bằng tiếng Việt và giữ thuật ngữ top_p.",
            "User: Tôi muốn câu trả lời tiếng Việt. Explain what top_p means.",
            "top_p là tham số lấy mẫu theo xác suất, còn gọi là nucleus sampling, giúp giới hạn nhóm token được chọn để điều chỉnh độ đa dạng.",
            "vi",
        ),
        (
            "Answer in English when the user switches to English.",
            "Người dùng đổi sang English: Please summarize why snippets should be long enough for email triage.",
            "A longer snippet gives enough email context for summary, priority, and action items without always fetching the full email.",
            "en",
        ),
        (
            "Trả lời bằng tiếng Việt nhưng giữ nguyên thuật ngữ JSON schema.",
            "Trả lời bằng tiếng Việt, nhưng giữ nguyên thuật ngữ JSON schema: Why use JSON schema for an agent?",
            "JSON schema giúp agent trả lời theo định dạng ổn định, dễ parse và giảm lỗi cấu trúc khi hệ thống cần đọc kết quả.",
            "vi",
        ),
    ]
    for i in range(30):
        instruction, prompt, output, language = eval_like_bilingual[i % len(eval_like_bilingual)]
        rows.append(
            row(
                instruction,
                f"{prompt} Case {i}",
                output,
                language=language,
                category="bilingual_switch",
            )
        )

    replay_rows = [
        (
            "Answer the coding question briefly and accurately.",
            "What condition does binary search require?",
            "Binary search is O(log n) and requires the input to already be sorted.",
            "en",
            "code_math",
        ),
        (
            "Fix the Python syntax and return only the corrected code.",
            "for i in range(3) print(i)",
            "for i in range(3):\n    print(i)",
            "en",
            "code_math",
        ),
        (
            "Cho vi du JSON hop le co name va age.",
            "JSON example please.",
            '{"name": "Lan", "age": 30}',
            "vi",
            "code_math",
        ),
        (
            "Explain list comprehension with a short example.",
            "Python list comprehension example.",
            "A list comprehension builds a list compactly, for example: squares = [x * x for x in numbers].",
            "en",
            "code_math",
        ),
        (
            "Answer the factual question in English.",
            "Explain the difference between RAM and SSD storage.",
            "RAM is temporary working memory for active tasks, while an SSD is persistent storage for files and applications.",
            "en",
            "factual_qa",
        ),
        (
            "Answer the factual question in English.",
            "What does transformer attention do?",
            "Attention helps a transformer weigh relevant tokens in context so it can model relationships across the sequence.",
            "en",
            "factual_qa",
        ),
        (
            "Answer the factual question in English.",
            "Why keep a validation set unseen during training?",
            "An unseen validation set helps evaluate generalization and detect overfitting or regressions after training.",
            "en",
            "factual_qa",
        ),
        (
            "Answer the factual question in English.",
            "What is BLEU used for in NLP evaluation?",
            "BLEU compares n-gram overlap between generated text and reference translations or answers.",
            "en",
            "factual_qa",
        ),
        (
            "Tra loi factual bang tieng Viet ngan gon.",
            "Nuoc nao co dan so lon nhat the gioi nam 2024?",
            "Nam 2024, An Do la nuoc co dan so lon nhat the gioi.",
            "vi",
            "factual_qa",
        ),
        (
            "Tra loi factual bang tieng Viet ngan gon.",
            "LoRA low-rank adapter la gi?",
            "LoRA la adapter hang thap, it tham so, dung de fine-tuning model ma khong cap nhat toan bo trong so.",
            "vi",
            "factual_qa",
        ),
    ]
    for i in range(40):
        instruction, prompt, output, language, category = replay_rows[i % len(replay_rows)]
        rows.append(
            row(
                instruction,
                f"{prompt} Replay {i}",
                output,
                language=language,
                category=category,
            )
        )

    if len(rows) != 410:
        raise AssertionError(f"Expected 410 rows, got {len(rows)}")
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
