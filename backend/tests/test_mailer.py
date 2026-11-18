from email.message import EmailMessage
from typing import Any

import aiosmtplib
import pytest

from lunch.mailer import SmtpMailer


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[EmailMessage, dict[str, Any]]]:
    calls: list[tuple[EmailMessage, dict[str, Any]]] = []

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        calls.append((message, kwargs))

    # The mailer calls aiosmtplib.send at call time, so patching the module attribute is enough.
    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    return calls


async def test_builds_text_and_html_message(
    sent: list[tuple[EmailMessage, dict[str, Any]]],
) -> None:
    await SmtpMailer("mailpit", 1025, "Lunch <no-reply@lunch.test>").send(
        "ann@example.com", "Hello", "plain body", "<p>html body</p>"
    )
    [(message, kwargs)] = sent
    assert message["To"] == "ann@example.com"
    assert message["From"] == "Lunch <no-reply@lunch.test>"
    assert message["Subject"] == "Hello"
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]
    assert kwargs == {
        "hostname": "mailpit",
        "port": 1025,
        "username": None,
        "password": None,
        "start_tls": False,
        "use_tls": False,
        "timeout": 10,
    }


@pytest.mark.parametrize(
    ("security", "start_tls", "use_tls"), [("starttls", True, False), ("ssl", False, True)]
)
async def test_real_servers_get_login_and_encryption(
    sent: list[tuple[EmailMessage, dict[str, Any]]], security: Any, start_tls: bool, use_tls: bool
) -> None:
    mailer = SmtpMailer(
        "smtp.example.com",
        587,
        "x@example.com",
        username="user",
        password="secret",
        security=security,
    )
    await mailer.send("to@example.com", "s", "t", "<p>h</p>")
    [(_, kwargs)] = sent
    assert (kwargs["username"], kwargs["password"]) == ("user", "secret")
    assert (kwargs["start_tls"], kwargs["use_tls"]) == (start_tls, use_tls)
