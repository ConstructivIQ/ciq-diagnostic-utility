"""
collectors/email_collector.py
Connects to an IMAP mailbox and retrieves recent support emails.
"""
from __future__ import annotations
import email as email_lib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional
import config


@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    date: str
    body: str
    has_attachments: bool = False


def _decode_header_value(value: str) -> str:
    parts = decode_header(value or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg: email_lib.message.Message) -> str:
    body_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode(charset, errors="replace"))
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            body_parts.append(payload.decode(charset, errors="replace"))
    return "\n".join(body_parts)[:3000]


def fetch_emails(keyword: Optional[str] = None, since_days: int = 7, max_messages: int = 30) -> list[EmailMessage]:
    """Connect to IMAP and return recent support emails."""
    if not (config.EMAIL_HOST and config.EMAIL_USER and config.EMAIL_PASSWORD):
        return []
    try:
        from imapclient import IMAPClient
    except ImportError:
        return []

    results: list[EmailMessage] = []
    try:
        with IMAPClient(config.EMAIL_HOST, port=config.EMAIL_PORT, ssl=True) as client:
            client.login(config.EMAIL_USER, config.EMAIL_PASSWORD)
            client.select_folder(config.EMAIL_FOLDER, readonly=True)
            since_date = (datetime.utcnow() - timedelta(days=since_days)).date()
            criteria = ["SINCE", since_date]
            if keyword:
                criteria += ["SUBJECT", keyword]
            uids = client.search(criteria)
            if not uids:
                return []
            uids = list(uids)[-max_messages:]
            raw_messages = client.fetch(uids, ["RFC822"])
            for uid, data in raw_messages.items():
                raw = data[b"RFC822"]
                msg = email_lib.message_from_bytes(raw)
                has_attach = any(
                    part.get_content_disposition() == "attachment"
                    for part in (msg.walk() if msg.is_multipart() else [msg])
                )
                results.append(EmailMessage(
                    uid=str(uid),
                    subject=_decode_header_value(msg.get("Subject", "(no subject)")),
                    sender=_decode_header_value(msg.get("From", "")),
                    date=msg.get("Date", ""),
                    body=_extract_body(msg),
                    has_attachments=has_attach,
                ))
    except Exception as exc:
        import sys
        print(f"[email_collector] Warning: {exc}", file=sys.stderr)
    return results
