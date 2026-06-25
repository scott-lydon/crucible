"""Process-level active Anthropic key store for the deploy-time fallback path.

Runs execute in a FastAPI background task, detached from the request that
started them, so the active key cannot ride on a request object. The smallest
honest mechanism is a process-global holder the admin-login and user-key
endpoints write and `get_llm_client` reads when it resolves the deployed
fallback path. It is in-memory only (never persisted, never logged in full), so
a process restart clears it and the operator re-enters the key. Single-operator
demo scope, so no per-session isolation: the active key is process-wide.

The two key kinds are kept distinct only for the provider indicator's label:
- PROJECT: the server's own `ANTHROPIC_API_KEY`, enabled by an admin login.
- USER: a key the visitor pasted, used without admin.
The selector prefers the project key when admin enabled it, else the user key.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KeySource(StrEnum):
    """Which path supplied the active key, for the provider indicator label."""

    PROJECT = "project_key"
    USER = "user_key"


@dataclass(frozen=True, slots=True)
class ActiveKey:
    """The Anthropic key currently selected for the fallback path, with its source."""

    value: str
    source: KeySource


# Mutable process-global, justified: it is the cross-request handoff this
# deploy-time fallback needs, and it is the only mutable state in this module.
_active: ActiveKey | None = None


def set_active_key(value: str, source: KeySource) -> None:
    """Install the active fallback key. Replaces any prior key."""
    global _active
    _active = ActiveKey(value=value, source=source)


def clear_active_key() -> None:
    """Forget the active fallback key (revert the deployed instance to none)."""
    global _active
    _active = None


def get_active_key() -> ActiveKey | None:
    """The active fallback key, or None when no key has been supplied."""
    return _active


# Process-level run-provider preference: when True, runs prefer the Anthropic
# API (fast, metered) over the local `claude` CLI even when the CLI is on PATH.
# In-memory only, single-operator scope like `_active`: a restart reverts it to
# the default (False), so the safe, free CLI path is always the unprimed state.
# SECURITY: the API path spends the active key owner's money per run, so this
# defaults OFF; it only changes the selection when an active key already exists.
_prefer_api: bool = False


def set_prefer_api(value: bool) -> None:
    """Set whether runs should prefer the Anthropic API over the local CLI."""
    global _prefer_api
    _prefer_api = value


def get_prefer_api() -> bool:
    """Whether runs prefer the Anthropic API over the local CLI (default False)."""
    return _prefer_api


def key_hint(value: str) -> str:
    """A safe display hint for a key: never the full value, only the last four."""
    tail = value[-4:] if len(value) >= 4 else value
    return f"sk-…{tail}"
