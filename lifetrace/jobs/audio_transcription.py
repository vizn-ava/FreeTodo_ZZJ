"""Audio transcription job helpers."""

import os

from lifetrace.core.dependencies import get_audio_transcription_service
from lifetrace.storage import audio_mgr
from lifetrace.util.local_memory_writer import LocalMemoryWriter, MemoryRecord
from lifetrace.util.logging_config import get_logger

logger = get_logger()
_memory_writer = LocalMemoryWriter()


def _write_transcription_to_md(audio_id: int, segments: list[dict], language: str | None, file_path: str | None) -> None:
    """Best-effort write transcription result to local markdown memory."""
    try:
        if not _memory_writer.is_enabled() or not segments:
            return
        # Build readable text from segments
        text_parts: list[str] = []
        for seg in segments:
            speaker = seg.get("speaker") or ""
            text = seg.get("text_content") or seg.get("textContent") or ""
            if not text:
                continue
            if speaker:
                text_parts.append(f"[{speaker}] {text}")
            else:
                text_parts.append(text)

        full_text = "\n".join(text_parts)
        if not full_text.strip():
            return

        extra: dict[str, str] = {"audio_id": str(audio_id)}
        if language:
            extra["language"] = language
        if file_path:
            extra["file"] = os.path.basename(file_path)

        _memory_writer.append_record(
            MemoryRecord(
                source="audio_transcription",
                action="transcribed",
                title=f"音频转写 (audio_id={audio_id})",
                content=full_text,
                extra=extra,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Audio transcription md write skipped: %s", exc)


def process_audio_record(audio_id: int, language: str | None = None) -> dict:
    record = audio_mgr.get_audio_record(audio_id)
    if not record:
        return {"success": False, "error": "audio record not found"}

    if record["status"] == "processing":
        return {"success": False, "error": "audio record already processing"}

    audio_mgr.update_audio_status(audio_id, "processing")

    try:
        service = get_audio_transcription_service()
        result = service.transcribe(
            record["file_path"],
            language=language or record.get("language"),
            diarization_enabled=record.get("diarization_enabled", False),
        )
        segments = result.get("segments", [])
        if segments:
            audio_mgr.add_segments(audio_id, segments)
        audio_mgr.update_audio_status(audio_id, "done", language=result.get("language"))

        # Write transcription to md
        _write_transcription_to_md(audio_id, segments, result.get("language"), record.get("file_path"))

        return {"success": True, "segments": segments, "language": result.get("language")}
    except Exception as e:
        logger.error(f"Audio transcription failed: {e}")
        audio_mgr.update_audio_status(audio_id, "failed", error_message=str(e))
        return {"success": False, "error": str(e)}


def execute_audio_transcription_task() -> int:
    pending = audio_mgr.list_audio_records(status="pending", limit=50, offset=0)
    processed = 0
    for record in pending:
        result = process_audio_record(record["id"])
        if result.get("success"):
            processed += 1
    return processed
