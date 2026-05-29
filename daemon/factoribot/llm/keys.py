"""Load API keys without exposing them.

Keys are read inside the process from an env var or a key file (default
``~/Dev/secrets/<name>``). They are never logged or printed.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_key(env_var: str, file_name: str, key_file: str | None = None) -> str:
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit.strip()
    path = Path(key_file) if key_file else Path.home() / "Dev" / "secrets" / file_name
    if path.exists():
        return path.read_text().strip()
    raise RuntimeError(
        f"No API key found. Set ${env_var} or place it at {path} "
        f"(or pass --key-file)."
    )
