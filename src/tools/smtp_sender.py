from __future__ import annotations

from email.message import EmailMessage as MIMEEmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Any

import aiosmtplib
import structlog

from .config import EmailSettings
from .email_client import redact
from .errors import AuthError, ToolError
from .safety import SafetyPipeline
from .schemas import SendRequest, SendResult

logger = structlog.get_logger(__name__)


class SMTPSender:
    def __init__(self, settings: EmailSettings, safety: SafetyPipeline):
        self.settings = settings
        self.safety = safety
        self._client: Any | None = None

    async def __aenter__(self) -> "SMTPSender":
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def send(self, req: SendRequest) -> SendResult:
        decision = await self.safety.evaluate(req)
        if decision.status != "allowed":
            return decision.to_send_result()

        message = self._build_mime(req)
        recipients = [str(item) for item in [*req.to, *req.cc, *req.bcc]]
        await self._ensure_connected()
        try:
            await self._client.send_message(message, recipients=recipients)
        except Exception as exc:
            secret = self.settings.smtp_pass.get_secret_value()
            raise ToolError(redact(f"SMTP send failed: {exc}", [secret])) from exc

        await self.safety.record_sent(req)
        message_id = str(message["Message-ID"])
        logger.info("smtp_send", recipients=len(recipients), subject_len=len(req.subject))
        return SendResult(status="sent", message_id=message_id)

    def _build_mime(self, req: SendRequest) -> MIMEEmailMessage:
        message = MIMEEmailMessage()
        from_header = str(self.settings.smtp_from)
        _, from_address = parseaddr(from_header)
        from_domain = from_address.rsplit("@", 1)[-1] if "@" in from_address else "localhost"

        message["From"] = from_header
        message["To"] = ", ".join(str(item) for item in req.to)
        if req.cc:
            message["Cc"] = ", ".join(str(item) for item in req.cc)
        message["Subject"] = req.subject
        message["Message-ID"] = make_msgid(domain=from_domain)
        message["Date"] = formatdate(localtime=True)
        if req.in_reply_to:
            message["In-Reply-To"] = req.in_reply_to
            references = [*req.references]
            if req.in_reply_to not in references:
                references.append(req.in_reply_to)
            message["References"] = " ".join(references)

        message.set_content(req.body_text)
        if req.body_html:
            message.add_alternative(req.body_html, subtype="html")
        return message

    async def _ensure_connected(self) -> None:
        if self._client is not None:
            return
        secret = self.settings.smtp_pass.get_secret_value()
        try:
            client = aiosmtplib.SMTP(
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                start_tls=False,
            )
            await client.connect()
            if self.settings.smtp_starttls:
                await client.starttls()
            if self._supports_auth(client):
                await client.login(self.settings.smtp_user, secret)
            self._client = client
            logger.info("smtp_connect", host=self.settings.smtp_host)
        except aiosmtplib.SMTPAuthenticationError as exc:
            raise AuthError(redact(f"SMTP authentication failed: {exc}", [secret])) from exc
        except Exception as exc:
            raise ToolError(redact(f"SMTP connect failed: {exc}", [secret])) from exc

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.quit()
        finally:
            self._client = None
            logger.info("smtp_close")

    @staticmethod
    def _supports_auth(client: Any) -> bool:
        try:
            return bool(client.supports_extension("auth"))
        except Exception:
            return True
