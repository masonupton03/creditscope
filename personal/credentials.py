"""Local credential storage for the personal edition.

Where credentials may come from (first match wins):
  1. environment variables ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY
  2. a file in the private home directory (default ~/.creditscope/credentials.json), created with `python -m personal setup`

Rules enforced here:
  * credentials are never written inside a git working tree (refused),
  * the file is created with owner-only permissions (0600) in an owner-only directory (0700),
  * the secret is never printed, logged or included in an exception message.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from . import config

ENV_KEY = "ALPACA_API_KEY_ID"
ENV_SECRET = "ALPACA_API_SECRET_KEY"


class CredentialError(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    key_id: str
    secret: str
    source: str = "file"

    def __repr__(self) -> str:                              # never leak the secret by accident (logs, tracebacks)
        return f"Credentials(key_id={redact(self.key_id)!r}, secret='***', source={self.source!r})"

    __str__ = __repr__


def redact(value: str) -> str:
    value = value or ""
    return value[:4] + "…" if len(value) > 4 else "…"


def credentials_path() -> Path:
    return config.home() / "credentials.json"


def _clean(text) -> str:
    return (text or "").strip()


def load() -> Credentials:
    """Return the credentials or raise CredentialError with a message that contains no secret."""
    key, secret = _clean(os.environ.get(ENV_KEY)), _clean(os.environ.get(ENV_SECRET))
    if key and secret:
        return Credentials(key, secret, "environment")
    path = credentials_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise CredentialError("No credentials found. Run: python -m personal setup") from None
    except (OSError, ValueError):
        raise CredentialError(f"Credentials file {path} is unreadable or not valid JSON") from None
    key, secret = _clean(data.get("key_id")), _clean(data.get("secret"))
    if not key or not secret:
        raise CredentialError(f"Credentials file {path} is incomplete. Run: python -m personal setup")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:                                      # readable by group/others: tighten it and carry on
            try:
                os.chmod(path, 0o600)
            except OSError:
                raise CredentialError(f"Credentials file {path} is accessible by other users and could not be fixed") from None
    return Credentials(key, secret, "file")


def validate_format(key_id: str, secret: str) -> None:
    if not key_id or not secret:
        raise CredentialError("Both the key ID and the secret are required")
    if any(c.isspace() for c in key_id + secret):
        raise CredentialError("Credentials must not contain spaces or line breaks")
    if len(key_id) < 8 or len(secret) < 16:
        raise CredentialError("These look too short to be Alpaca credentials. Nothing was saved.")


def save(key_id: str, secret: str) -> Path:
    """Write credentials to the private home with owner-only permissions. Refuses to write inside a git repo."""
    key_id, secret = _clean(key_id), _clean(secret)
    validate_format(key_id, secret)
    path = credentials_path()
    if config.inside_git_repo(path.parent):
        raise CredentialError("Refusing to store credentials inside a git working tree. Set CREDITSCOPE_HOME to a folder outside any repository.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"key_id": key_id, "secret": secret}, fh)
    os.replace(tmp, path)
    if os.name == "posix":
        os.chmod(path, 0o600)
    return path


def forget() -> bool:
    """Delete the stored credentials file (user-initiated). Returns True if a file was removed."""
    try:
        credentials_path().unlink()
        return True
    except FileNotFoundError:
        return False
