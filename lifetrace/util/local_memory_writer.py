"""
Local markdown memory writer.

Goal: append all modality data into project-local storage:

  lifetrace/data/local_memory/{user_key}/{YYYY-MM-DD}/final_text.md

Supported modalities:
- chat (user/assistant messages)
- todo (create/update/complete/delete)
- journal (create/update)
- ocr (screenshot text recognition)
- activity (AI activity summaries)
- audio_transcription (speech-to-text)
- voice_chat (realtime voice conversation)

Notes
- `lifetrace/data/` is runtime data (gitignored). Folder is created on demand.
- Writer must be best-effort: failures should not break main flows.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
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
    """Chat message append event (backward compatible)."""
    session_id: str
    role: str
    content: str
    token_count: int | None = None
    model: str | None = None
    metadata: str | None = None
    ts: datetime | None = None
    user_key: str | None = None


@dataclass(frozen=True)
class MemoryRecord:
    """General-purpose memory record for any modality.

    Attributes:
        source: modality identifier, e.g. "todo", "journal", "ocr", "activity",
                "audio_transcription", "voice_chat"
        action: action type, e.g. "created", "updated", "completed", "deleted"
        title: short title / summary line
        content: main body text
        extra: optional key-value metadata pairs shown as blockquote
        ts: timestamp (defaults to now)
        user_key: user key for directory partitioning
    """
    source: str
    action: str
    title: str
    content: str
    extra: dict[str, str] = field(default_factory=dict)
    ts: datetime | None = None
    user_key: str | None = None


class LocalMemoryWriter:
    """Append-only markdown memory writer (best-effort)."""

    def __init__(self) -> None:
        self._enabled = bool(settings.get("local_memory.enabled", True))
        self._root_name = str(settings.get("local_memory.dir_name", "local_memory") or "local_memory")

    def is_enabled(self) -> bool:
        return self._enabled

    # ----- internal helpers -----

    def _resolve_md_path(self, ts: datetime, user_key: str | None = None) -> Path:
        """Resolve the daily final_text.md path."""
        date_dir = ts.strftime("%Y-%m-%d")
        env_user_key = os.getenv("LIFETRACE_USER_KEY")
        safe_key = _safe_user_key(user_key or (env_user_key or "") or "default")
        root = get_user_data_dir() / self._root_name / safe_key / date_dir
        root.mkdir(parents=True, exist_ok=True)
        return root / "final_text.md"

    def _write_block(self, md_path: Path, block_lines: list[str]) -> Path | None:
        """Write a block of lines to the md file."""
        try:
            with _WRITE_LOCK:
                with md_path.open("a", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(block_lines))
            return md_path
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local memory append failed: %s", exc)
            return None

    # ----- chat message append (backward compatible) -----

    def append(self, event: MemoryAppendEvent) -> Path | None:
        """Append a chat message block into the daily final_text.md."""
        if not self._enabled:
            return None

        content = (event.content or "").rstrip()
        if not content:
            return None

        ts = event.ts or datetime.now()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")

        meta_user_key = _parse_user_key_from_metadata(event.metadata)
        user_key = event.user_key or meta_user_key
        md_path = self._resolve_md_path(ts, user_key)

        block_lines: list[str] = []
        block_lines.append(f"### [{ts_str}] {event.role}")
        block_lines.append("")
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

        return self._write_block(md_path, block_lines)

    # ----- general-purpose record append -----

    def append_record(self, record: MemoryRecord) -> Path | None:
        """Append a general modality record into the daily final_text.md.

        Format:
            ### [2026-02-18 14:30:00] 📋 todo/created
            > id=42; priority=high
            **待办标题**
            待办描述内容...
            ---
        """
        if not self._enabled:
            return None

        content = (record.content or "").rstrip()
        title = (record.title or "").strip()
        if not content and not title:
            return None

        # Emoji prefix per source for visual distinction
        _SOURCE_EMOJI = {
            "todo": "📋",
            "journal": "📓",
            "ocr": "🔍",
            "activity": "📊",
            "audio_transcription": "🎙️",
            "voice_chat": "🗣️",
        }
        emoji = _SOURCE_EMOJI.get(record.source, "📝")

        ts = record.ts or datetime.now()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        md_path = self._resolve_md_path(ts, record.user_key)

        block_lines: list[str] = []
        block_lines.append(f"### [{ts_str}] {emoji} {record.source}/{record.action}")
        block_lines.append("")

        # Metadata line
        if record.extra:
            meta_parts = [f"{k}={v}" for k, v in record.extra.items()]
            block_lines.append(f"> {'; '.join(meta_parts)}")
            block_lines.append("")

        # Title (bold)
        if title:
            block_lines.append(f"**{title}**")
            block_lines.append("")

        # Body content
        if content:
            block_lines.append(content)
            block_lines.append("")

        block_lines.append("---")
        block_lines.append("")

        return self._write_block(md_path, block_lines)


