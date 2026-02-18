"""
Local markdown memory writer.

Goal: append the final text stream (chat messages) into project-local storage:

  lifetrace/data/local_memory/{user_key}/{YYYY-MM-DD}/final_text.md

Notes
- `lifetrace/data/` is runtime data (gitignored). Folder is created on demand.
- Writer must be best-effort: failures should not break main flows.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from lifetrace.util.logging_config import get_logger
from lifetrace.util.path_utils import get_user_data_dir
from lifetrace.util.settings import settings

logger = get_logger()

_WRITE_LOCK = threading.Lock()


def _safe_user_key(user_key: str) -> str:
    user_key = (user_key or "").strip() or "default"
    # Avoid path traversal and illegal filename chars on Windows.
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        user_key = user_key.replace(ch, "_")
    user_key = user_key.replace("..", "_")
    return user_key[:80] or "default"


def _parse_user_key_from_metadata(metadata: str | None) -> str | None:
    """Best-effort extract user_key from metadata JSON if present."""
    if not metadata:
        return None
    try:
        data = json.loads(metadata)
        if isinstance(data, dict):
            val = data.get("user_key") or data.get("user") or data.get("user_id")
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        return None
    return None


@dataclass(frozen=True)
class MemoryAppendEvent:
    session_id: str
    role: str
    content: str
    token_count: int | None = None
    model: str | None = None
    metadata: str | None = None
    ts: datetime | None = None
    user_key: str | None = None


class LocalMemoryWriter:
    """Append-only markdown memory writer (best-effort)."""

    def __init__(self) -> None:
        self._enabled = bool(settings.get("local_memory.enabled", True))
        self._root_name = str(settings.get("local_memory.dir_name", "local_memory") or "local_memory")

    def is_enabled(self) -> bool:
        return self._enabled

    def append(self, event: MemoryAppendEvent) -> Path | None:
        """Append an event block into the daily final_text.md. Returns file path on success."""
        if not self._enabled:
            return None

        content = (event.content or "").rstrip()
        if not content:
            return None

        ts = event.ts or datetime.now()
        date_dir = ts.strftime("%Y-%m-%d")
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")

        env_user_key = os.getenv("LIFETRACE_USER_KEY")
        meta_user_key = _parse_user_key_from_metadata(event.metadata)
        user_key = _safe_user_key(event.user_key or meta_user_key or (env_user_key or "") or "default")

        root = get_user_data_dir() / self._root_name / user_key / date_dir
        root.mkdir(parents=True, exist_ok=True)

        md_path = root / "final_text.md"

        # Markdown block format: compact, append-friendly.
        block_lines: list[str] = []
        block_lines.append(f"### [{ts_str}] {event.role}")
        block_lines.append("")
        # Minimal metadata (optional)
        meta_parts: list[str] = [f"session_id={event.session_id}"]
        if event.model:
            meta_parts.append(f"model={event.model}")
        if event.token_count is not None:
            meta_parts.append(f"tokens={event.token_count}")
        block_lines.append(f"> {'; '.join(meta_parts)}")
        block_lines.append("")
        block_lines.append(content)
        block_lines.append("")
        block_lines.append("---")
        block_lines.append("")

        try:
            # Single-process safety; multi-process not guaranteed (acceptable for simple local memory).
            with _WRITE_LOCK:
                with md_path.open("a", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(block_lines))
            return md_path
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local memory append failed: %s", exc)
            return None


