from __future__ import annotations

import hashlib


def subject_hash(subject: str | None) -> str | None:
    if not subject:
        return None
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]


def email_domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[1].lower() or None


def first_recipient_domain(recipients: list[str]) -> str | None:
    for recipient in recipients:
        domain = email_domain(recipient)
        if domain:
            return domain
    return None
