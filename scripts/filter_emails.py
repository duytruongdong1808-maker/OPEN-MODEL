import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "emails.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "filtered" / "emails.jsonl"

SENDER_BAD = re.compile(
    r"^("
    r"no.?reply|donotreply|notification|notif|mailer-daemon|automated|"
    r"messages|message|info|news|newsletter|hello|hi|team|support|"
    r"updates?|alerts?|notify|notifications|birthdays?|groupupdates?|"
    r"friendupdates?|recommendations?|promotions?|marketing|promo|"
    r"deals?|offers?|sale|crm_?asia|samsungelectronics|account|billing|"
    r"system|service|customer|membership|community|digest|reminder"
    r")(?:[._+\-].*)?@",
    re.IGNORECASE,
)

NOISY_DOMAINS = {
    "facebookmail.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
    "discord.com",
    "soundcloud.com",
    "spotify.com",
    "youtube.com",
    "shopee.vn",
    "lazada.vn",
    "tiki.vn",
    "sendo.vn",
    "samsung.com",
    "ubisoft.com",
    "505games.com",
    "ef.com",
    "dolenglish.vn",
    "airtable.com",
    "medium.com",
    "substack.com",
    "quora.com",
}

LOW_VALUE_LABELS = {
    "spam",
    "trash",
    "bin",
    "category_promotions",
    "category_social",
    "category_updates",
    "category_forums",
    "promotions",
    "social",
    "updates",
    "forums",
    "khuyen mai",
    "mang xa hoi",
    "cap nhat",
    "dien dan",
    "thong tin cap nhat",
}

PROMO_SUBJECT = (
    "flash sale",
    "limited time",
    "% off",
    "khuyen mai",
    "giam gia",
    "uu dai",
    "mien phi ship",
    "freeship",
    "sale up",
    "khoa hoc mien phi",
    "voucher",
    "code giam",
    "deal hot",
    "tang qua",
    "qua tang",
    "san pham moi",
    "giam toi",
    "giam ngay",
    "siet bung",
    "san sale",
    "happy hour",
    "tang ban",
    "co hoi",
    "duy nhat",
    "uu dai cuc soc",
    "deal soc",
    "ban se thich",
    "moi ngay",
    "big sale",
    "mega sale",
)

BOT_NAMES = re.compile(
    r"\b("
    r"facebook|twitter|linkedin|instagram|pinterest|tiktok|youtube|"
    r"samsung|shopee|lazada|tiki|sendo|grab|momo|zalopay|"
    r"google|microsoft|github|stackoverflow|netflix|spotify"
    r")\b",
    re.IGNORECASE,
)


def strip_diacritics(value):
    nfd = unicodedata.normalize("NFD", value)
    no_marks = "".join(char for char in nfd if unicodedata.category(char) != "Mn")
    return no_marks.replace("\u0111", "d").replace("\u0110", "D")


def fail_length(email):
    body = email.get("body_text", "")
    return len(body) < 80 or len(body) > 8000


def fail_sender_username(email):
    return bool(SENDER_BAD.match(email.get("from", "").strip()))


def fail_domain(email):
    sender = email.get("from", "").lower()
    if "@" not in sender:
        return False

    domain = sender.split("@", 1)[1]
    parts = domain.split(".")
    for index in range(len(parts) - 1):
        if ".".join(parts[index:]) in NOISY_DOMAINS:
            return True
    return False


def fail_list_unsub(email):
    return email.get("list_unsubscribe") and len(email.get("body_text", "")) < 1500


def fail_label(email):
    for label in email.get("labels", []):
        raw = label.lower()
        norm = strip_diacritics(raw).strip()
        if norm in LOW_VALUE_LABELS or raw in LOW_VALUE_LABELS:
            return True
        for noisy in ("khuyen mai", "mang xa hoi", "promo", "social", "updates"):
            if noisy in norm:
                return True
    return False


def fail_subject(email):
    subject = strip_diacritics(email.get("subject", "").lower())
    return any(keyword in subject for keyword in PROMO_SUBJECT)


def fail_bot_name(email):
    return bool(BOT_NAMES.search(email.get("from_name", "")))


RULES = [
    ("length", fail_length),
    ("sender_username", fail_sender_username),
    ("domain", fail_domain),
    ("list_unsub", fail_list_unsub),
    ("label", fail_label),
    ("promo_subject", fail_subject),
    ("bot_name", fail_bot_name),
]


def skip_reasons(record):
    return [name for name, rule in RULES if rule(record)]


def parse_args():
    parser = argparse.ArgumentParser(description="Filter low-value parsed emails from JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to parsed input JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to filtered output JSONL.")
    return parser.parse_args()


def main():
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Reading emails: {args.input}")
    print(f"Writing filtered emails: {args.output}")

    total = 0
    kept = 0
    skip_counts = Counter()

    with args.input.open("r", encoding="utf-8") as input_file, args.output.open(
        "w", encoding="utf-8"
    ) as output_file:
        for line in input_file:
            if not line.strip():
                continue

            total += 1
            record = json.loads(line)
            reasons = skip_reasons(record)
            if reasons:
                skip_counts.update(reasons)
            else:
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1

            if total % 1000 == 0:
                print(f"Processed {total} emails, kept {kept}...")

    kept_percent = (kept / total * 100) if total else 0
    print(f"Total emails read: {total}")
    print(f"Emails kept: {kept} ({kept_percent:.1f}%)")
    print("Skip reason breakdown:")
    for reason, _ in RULES:
        print(f"- {reason}: {skip_counts[reason]}")


if __name__ == "__main__":
    main()
