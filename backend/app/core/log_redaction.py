"""Redact secrets and personal data from log records.

This exists for a specific, measured reason. The Phase 9/10 audit
(``docs/PHASE9-10-AUDIT.md``, findings 3 and 4) confirmed two live leaks into
the log stream:

* ``app/api/v1/integrations/meta.py:47`` logs the real ``META_VERIFY_TOKEN`` in
  plaintext on every webhook verification attempt, including attacker-driven
  ones.
* ``app/api/v1/integrations/meta.py:73`` logs the entire inbound webhook body,
  which carries sender phone numbers and message text.

Phase 11 is under instruction not to modify those files, so the leak is
intercepted one layer down instead: a logging filter sees every record on its
way to a handler and masks the sensitive substrings.

**This is mitigation, not a fix.** A filter that pattern-matches text is
strictly weaker than not logging the secret in the first place, and it cannot
know about a secret whose value it was never told. The call sites still need
fixing. What this does buy: the specific confirmed leaks stop reaching the log
files today, and any *future* log line that happens to include a configured
secret is masked too.

Values are taken from settings at filter-construction time. Short values are
skipped -- masking a two-character secret would redact half the log file --
and matching is plain substring replacement rather than a regex over
attacker-controlled text, so a hostile message body cannot make the filter
expensive.
"""
from __future__ import annotations

import logging
import re

_REDACTED = "***REDACTED***"

# A secret shorter than this is not worth masking: the risk of mangling
# unrelated log text outweighs the benefit.
_MIN_SECRET_LENGTH = 8

# Phone numbers in E.164-ish form: 9-15 digits, optionally +-prefixed. Keeps the
# last two digits so an operator can still correlate a report with a caller
# without the full number sitting in the log.
#
# The surrounding boundaries are essential and were added after this filter was
# observed mangling a live request id: correlation ids, UUIDs and SHA hashes are
# alphanumeric strings that contain long digit runs, and masking part of one
# destroys the ability to trace a request across log lines. Requiring that the
# run is not adjacent to another alphanumeric character keeps the filter to
# things that actually look like phone numbers.
_PHONE_RE = re.compile(r"(?<![0-9A-Za-z])\+?\d{9,15}(?![0-9A-Za-z])")

# Bearer tokens and JWTs that end up in log text (e.g. a logged request header).
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]{16,}=*", re.IGNORECASE)


def _mask_phone(match: re.Match[str]) -> str:
    digits = match.group(0)
    tail = digits[-2:]
    return f"{'*' * max(0, len(digits) - 2)}{tail}"


def _collect_secret_values() -> list[str]:
    """Gather configured secret values worth masking.

    Imported lazily and defensively: a missing or unreadable setting must never
    stop the application from logging.
    """
    values: list[str] = []

    def _add(value: object) -> None:
        if isinstance(value, str) and len(value) >= _MIN_SECRET_LENGTH:
            values.append(value)

    try:
        from app.core.config import settings

        for name in (
            "SECRET_KEY",
            "META_VERIFY_TOKEN",
            "META_APP_SECRET",
            "META_ACCESS_TOKEN",
            "VAPI_SECRET",
            "VAPI_API_KEY",
            "POSTGRES_PASSWORD",
        ):
            _add(getattr(settings, name, None))
    except Exception:  # noqa: BLE001 - logging must not depend on config loading
        pass

    # Longest first, so a secret that contains another is masked whole.
    return sorted(set(values), key=len, reverse=True)


class RedactingFilter(logging.Filter):
    """Mask configured secrets, phone numbers and bearer tokens in log records.

    A ``logging.Filter`` is used rather than a formatter because it applies
    wherever it is attached regardless of how the record is later rendered --
    the project has both a plain and a JSON formatter, and a filter covers both.
    """

    def __init__(self, redact_phones: bool = True) -> None:
        super().__init__()
        self._secrets = _collect_secret_values()
        self._redact_phones = redact_phones

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, _REDACTED)
        text = _BEARER_RE.sub(rf"\1{_REDACTED}", text)
        if self._redact_phones:
            text = _PHONE_RE.sub(_mask_phone, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Render args into the message now, then clear them: a lazily-formatted
        # record would otherwise re-expand the raw args at handler time and
        # undo the scrub.
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True

        scrubbed = self._scrub(message)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()

        # Structured extras travel separately and are just as likely to carry a
        # phone number or token.
        for key, value in list(record.__dict__.items()):
            if key in _LOG_RECORD_RESERVED or not isinstance(value, str):
                continue
            scrubbed_value = self._scrub(value)
            if scrubbed_value != value:
                record.__dict__[key] = scrubbed_value

        return True


# Attributes the logging module owns; scrubbing these would corrupt the record.
# ``request_id`` is ours but belongs here too: it is a correlation identifier,
# never a secret, and masking it makes the logs untraceable.
_LOG_RECORD_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
        "request_id",
    }
)


def install_log_redaction(redact_phones: bool = True) -> None:
    """Attach the filter to the root logger's handlers.

    Attaching to handlers rather than to the root logger matters: a filter on a
    logger is not consulted for records that propagate up from child loggers,
    so a logger-level filter would miss exactly the ``app.api.v1.integrations``
    records this exists to scrub.
    """
    redacting = RedactingFilter(redact_phones=redact_phones)
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(redacting)
