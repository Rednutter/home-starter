"""Minimal defensive log redaction; runtime objects must never be dumped."""

import logging
import re

PRIVATE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "authorization",
    "cookie",
    "client_secret",
    "webhook_secret",
    "email",
    "phone",
    "latitude",
    "longitude",
}


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: "[redacted]" if str(k).lower() in PRIVATE_KEYS else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(redact(v, secrets) for v in value)
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        value = re.sub(r"(?i)Bearer\s+[^\s,;]+", "Bearer [redacted]", value)
        value = re.sub(
            r"(?i)(password|access_token|refresh_token|api_key|client_secret|cookie|authorization|token)[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]+",
            r"\1=[redacted]",
            value,
        )
    return value


class PrivacyFilter(logging.Filter):
    def __init__(self, secrets=()):
        super().__init__()
        self.secrets = tuple(secrets)

    def filter(self, record):
        record.msg = redact(record.msg, self.secrets)
        record.args = redact(record.args, self.secrets)
        record.msg = redact(record.getMessage(), self.secrets)
        record.args = ()
        if record.exc_info:
            record.exc_text = record.exc_info[0].__name__ + " (private exception details omitted)"
            record.exc_info = None
        return True
