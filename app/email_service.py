from __future__ import annotations

import base64
import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

from azure.communication.email import EmailClient


class EmailConfigurationError(RuntimeError):
    pass


def _bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def send_report_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Iterable[Path],
) -> None:
    acs_connection_string = os.getenv("ACS_EMAIL_CONNECTION_STRING")
    acs_sender = os.getenv("ACS_EMAIL_SENDER")
    if acs_connection_string and acs_sender:
        _send_report_email_acs(
            connection_string=acs_connection_string,
            sender=acs_sender,
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
        )
        return

    smtp_host = os.getenv("SMTP_HOST")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("EMAIL_FROM")

    if not smtp_host or not smtp_from:
        raise EmailConfigurationError(
            "SMTP_HOST and EMAIL_FROM must be set to send emails."
        )

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = _bool_from_env("SMTP_USE_TLS", True)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content("Your email client does not support HTML. Please view the PDF attachment.")
    msg.add_alternative(html_body, subtype="html")

    for path in attachments:
        data = Path(path).read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        if mime:
            maintype, subtype = mime.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if smtp_username:
            server.login(smtp_username, smtp_password or "")
        server.send_message(msg)


def _send_report_email_acs(
    *,
    connection_string: str,
    sender: str,
    to_email: str,
    subject: str,
    html_body: str,
    attachments: Iterable[Path],
) -> None:
    client = EmailClient.from_connection_string(connection_string)

    acs_attachments = []
    for path in attachments:
        file_bytes = Path(path).read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        acs_attachments.append(
            {
                "name": path.name,
                "contentType": content_type,
                "contentInBase64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )

    message = {
        "senderAddress": sender,
        "recipients": {"to": [{"address": to_email}]},
        "content": {
            "subject": subject,
            "plainText": "Please view the attached PDF report.",
            "html": html_body,
        },
        "attachments": acs_attachments,
    }

    poller = client.begin_send(message)
    result = poller.result()
    status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
    if status and status not in {"queued", "outfordelivery", "success", "succeeded"}:
        raise RuntimeError(f"ACS email send returned status: {status}")
