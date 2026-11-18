import logging
from email.message import EmailMessage
from typing import Literal, Protocol

import aiosmtplib

log = logging.getLogger(__name__)


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str, html: str) -> None: ...


class SmtpMailer:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        *,
        username: str = "",
        password: str = "",
        security: Literal["none", "starttls", "ssl"] = "none",
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username or None
        self._password = password or None
        self._security = security

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            start_tls=self._security == "starttls",
            use_tls=self._security == "ssl",
            timeout=10,
        )
