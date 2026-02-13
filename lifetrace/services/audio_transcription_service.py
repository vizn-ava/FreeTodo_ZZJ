"""Audio transcription and diarization service."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from lifetrace.util.logging_config import get_logger
from lifetrace.util.settings import settings

logger = get_logger()


@dataclass
class AudioMetadata:
    duration: float | None = None
    sample_rate: int | None = None
    channels: int | None = None


class AudioTranscriptionService:
    """Run Bailian ASR transcription with optional diarization."""

    def __init__(self) -> None:
        self._diarization_pipeline = None
        self._opencc_converter = None

    def _get_opencc_converter(self):
        if self._opencc_converter is not None:
            return self._opencc_converter
        try:
            from opencc import OpenCC

            self._opencc_converter = OpenCC("t2s")
            return self._opencc_converter
        except Exception as e:  # pragma: no cover - optional dependency/runtime
            logger.warning(f"OpenCC not available, skip t2s normalization: {e}")
            self._opencc_converter = False
            return None

    def _should_normalize_to_simplified(self, language: str | None) -> bool:
        enabled = settings.get("audio_transcription.normalize_to_simplified", True)
        if not enabled:
            return False
        if language is None:
            return True
        lang = language.lower().strip()
        return lang.startswith("zh")

    def _normalize_segments_to_simplified(
        self, segments: list[dict[str, Any]], language: str | None
    ) -> list[dict[str, Any]]:
        if not segments or not self._should_normalize_to_simplified(language):
            return segments
        converter = self._get_opencc_converter()
        if converter is None:
            return segments
        for segment in segments:
            text = segment.get("text_content")
            if isinstance(text, str) and text:
                segment["text_content"] = converter.convert(text)
        return segments

    def _resolve_bailian_api_key(self) -> str | None:
        invalid_values = {"", "xxx", "YOUR_BAILIAN_API_KEY_HERE", "YOUR_LLM_KEY_HERE"}
        env_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
        if env_key and env_key.strip() and env_key.strip() not in invalid_values:
            return env_key.strip()

        config_key = str(settings.get("bailian.api_key", "") or "").strip()
        if config_key and config_key not in invalid_values:
            return config_key

        llm_base_url = str(settings.get("llm.base_url", "") or "")
        llm_api_key = str(settings.get("llm.api_key", "") or "").strip()
        if "dashscope.aliyuncs.com" in llm_base_url and llm_api_key not in invalid_values:
            return llm_api_key
        return None

    @staticmethod
    def _is_valid_config_value(value: Any) -> bool:
        if value is None:
            return False
        text = str(value).strip()
        invalid_values = {"", "xxx", "YOUR_BAILIAN_API_KEY_HERE", "YOUR_LLM_KEY_HERE"}
        return text not in invalid_values

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _resolve_bailian_workspace(self) -> str | None:
        env_workspace = os.getenv("DASHSCOPE_WORKSPACE") or os.getenv("BAILIAN_WORKSPACE_ID")
        if self._is_valid_config_value(env_workspace):
            return str(env_workspace).strip()

        workspace_id = settings.get("audio_transcription.bailian.workspace_id")
        if self._is_valid_config_value(workspace_id):
            return str(workspace_id).strip()
        return None

    @staticmethod
    def _guess_audio_format(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower().lstrip(".")
        mapping = {
            "wav": "wav",
            "webm": "webm",
            "ogg": "ogg",
            "opus": "ogg",
            "mp3": "mp3",
            "m4a": "m4a",
            "mp4": "mp4",
            "aac": "aac",
            "flac": "flac",
        }
        return mapping.get(suffix, "wav")

    def _create_bailian_recognition(
        self,
        language: str | None = None,
        audio_format: str | None = None,
        sample_rate: int | None = None,
    ):
        api_key = self._resolve_bailian_api_key()
        if not api_key:
            raise RuntimeError("Bailian API key is missing")

        try:
            import dashscope
            from dashscope.audio.asr import Recognition
        except Exception as e:
            raise RuntimeError("dashscope sdk is not installed") from e

        dashscope.api_key = api_key

        bailian_cfg = settings.get("audio_transcription.bailian", {}) or {}
        model = bailian_cfg.get("model", "paraformer-realtime-v2")
        sample_rate_value = int(sample_rate or bailian_cfg.get("sample_rate", 16000))
        audio_format_value = str(audio_format or bailian_cfg.get("format", "wav"))
        workspace = self._resolve_bailian_workspace()

        recognition_kwargs: dict[str, Any] = {
            "model": model,
            "format": audio_format_value,
            "sample_rate": sample_rate_value,
            "callback": None,
        }
        if workspace:
            recognition_kwargs["workspace"] = workspace

        lang = (language or "").strip().lower()
        if lang and lang != "auto":
            recognition_kwargs["language_hints"] = [lang]

        logger.info(
            f"Using Bailian ASR model: {model}, format={audio_format_value}, sample_rate={sample_rate_value}"
        )
        return Recognition(**recognition_kwargs)

    def _prepare_audio_for_bailian(self, file_path: str) -> tuple[str, str | None, str]:
        source_format = self._guess_audio_format(file_path)
        if source_format == "wav":
            return file_path, None, source_format

        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav_path = temp_file.name
        temp_file.close()

        try:
            import av
            from av.audio.resampler import AudioResampler

            with av.open(file_path) as input_container, av.open(
                temp_wav_path, mode="w", format="wav"
            ) as output_container:
                output_stream = output_container.add_stream("pcm_s16le", rate=16000)
                output_stream.layout = "mono"
                resampler = AudioResampler(format="s16", layout="mono", rate=16000)

                for frame in input_container.decode(audio=0):
                    for resampled in self._as_list(resampler.resample(frame)):
                        for packet in self._as_list(output_stream.encode(resampled)):
                            output_container.mux(packet)

                for packet in self._as_list(output_stream.encode(None)):
                    output_container.mux(packet)

            return temp_wav_path, temp_wav_path, "wav"
        except Exception as exc:
            if os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass

            # Browser recorded WebM/Ogg may be truncated on some systems.
            # Fallback to direct upload and let Bailian decode the container.
            if source_format in {"webm", "ogg", "mp3", "m4a", "mp4", "aac", "flac"}:
                logger.warning(
                    f"Audio conversion failed ({exc}); fallback to direct ASR with format={source_format}"
                )
                return file_path, None, source_format
            raise

    @staticmethod
    def _extract_text_from_sentence_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            value = payload.get("text")
            if isinstance(value, str):
                return value.strip()
            return ""
        if isinstance(payload, list):
            chunks: list[str] = []
            for item in payload:
                value = AudioTranscriptionService._extract_text_from_sentence_payload(item)
                if value:
                    chunks.append(value)
            return " ".join(chunks).strip()
        return ""

    @staticmethod
    def _extract_text_from_bailian_result(result: Any) -> str:
        try:
            if hasattr(result, "get_sentence"):
                sentence = result.get_sentence()
                sentence_text = AudioTranscriptionService._extract_text_from_sentence_payload(
                    sentence
                )
                if sentence_text:
                    return sentence_text
        except Exception:
            pass

        output = getattr(result, "output", None)
        if isinstance(output, dict):
            return AudioTranscriptionService._extract_text_from_output_dict(output)
        return ""

    @staticmethod
    def _extract_text_from_output_dict(output: dict[str, Any]) -> str:
        sentence_text = AudioTranscriptionService._extract_text_from_sentence_payload(
            output.get("sentence")
        )
        if sentence_text:
            return sentence_text

        for key in ("text", "transcript", "content"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        transcripts = output.get("transcripts")
        if not isinstance(transcripts, list):
            return ""

        chunks = [
            item.get("text", "").strip()
            for item in transcripts
            if isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and item.get("text", "").strip()
        ]
        return " ".join(chunks).strip()

    @staticmethod
    def _extract_sentence_items_from_bailian_result(result: Any) -> list[dict[str, Any]]:
        sentence_payload = None
        if hasattr(result, "get_sentence"):
            try:
                sentence_payload = result.get_sentence()
            except Exception:
                sentence_payload = None

        if sentence_payload is None:
            output = getattr(result, "output", None)
            if isinstance(output, dict):
                sentence_payload = output.get("sentence")

        if isinstance(sentence_payload, dict):
            return [sentence_payload]
        if isinstance(sentence_payload, list):
            return [item for item in sentence_payload if isinstance(item, dict)]
        return []

    def _build_asr_segments_from_bailian_result(
        self,
        result: Any,
        duration: float,
        language: str | None,
    ) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        sentence_items = self._extract_sentence_items_from_bailian_result(result)
        for sentence in sentence_items:
            text = str(sentence.get("text", "") or "").strip()
            if not text:
                continue

            begin_ms = sentence.get("begin_time")
            end_ms = sentence.get("end_time")
            try:
                start_time = float(begin_ms) / 1000.0 if begin_ms is not None else 0.0
            except Exception:
                start_time = 0.0
            try:
                end_time = float(end_ms) / 1000.0 if end_ms is not None else start_time
            except Exception:
                end_time = start_time
            end_time = max(end_time, start_time)

            speaker_id = sentence.get("speaker_id")
            speaker = None
            if speaker_id is not None:
                speaker = f"speaker_{speaker_id}"

            segments.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "text_content": text,
                    "confidence": sentence.get("confidence"),
                    "language": language,
                    "speaker": speaker,
                }
            )

        if segments:
            return segments

        text = self._extract_text_from_bailian_result(result)
        if not text:
            return []

        return [
            {
                "start_time": 0.0,
                "end_time": duration if duration > 0 else 0.0,
                "text_content": text,
                "confidence": None,
                "language": language,
                "speaker": None,
            }
        ]

    def _get_diarization_pipeline(self):
        if self._diarization_pipeline is None:
            try:
                from pyannote.audio import Pipeline
            except Exception as e:  # pragma: no cover - optional dependency
                logger.warning(f"pyannote.audio not available: {e}")
                return None

            diarization_cfg = settings.get("audio_transcription.diarization", {})
            model_id = diarization_cfg.get("model", "pyannote/speaker-diarization-3.1")
            auth_token = diarization_cfg.get("auth_token") or None
            logger.info(f"Loading diarization model: {model_id}")
            try:
                self._diarization_pipeline = Pipeline.from_pretrained(
                    model_id,
                    use_auth_token=auth_token,
                )
            except Exception as e:
                logger.error(f"Failed to load diarization model: {e}")
                return None
        return self._diarization_pipeline

    def get_audio_metadata(self, file_path: str) -> AudioMetadata:
        try:
            import av

            with av.open(file_path) as container:
                stream = next((s for s in container.streams if s.type == "audio"), None)
                if not stream:
                    return AudioMetadata()
                duration = None
                if stream.duration is not None and stream.time_base is not None:
                    duration = float(stream.duration * stream.time_base)
                return AudioMetadata(
                    duration=duration,
                    sample_rate=getattr(stream, "rate", None),
                    channels=getattr(stream, "channels", None),
                )
        except Exception as e:
            logger.warning(f"Failed to read audio metadata: {e}")
            return AudioMetadata()

    def _run_diarization(
        self, file_path: str, diarization_enabled: bool | None = None
    ) -> list[dict[str, Any]]:
        diarization_cfg = settings.get("audio_transcription.diarization", {})
        if diarization_enabled is None:
            diarization_enabled = diarization_cfg.get("enabled", False)
        if not diarization_enabled:
            return []

        model_id = diarization_cfg.get("model", "pyannote/speaker-diarization-3.1")
        auth_token = diarization_cfg.get("auth_token") or None
        if isinstance(model_id, str) and "/" in model_id and not auth_token:
            logger.warning(
                "Diarization enabled but auth_token is missing; skip diarization and return ASR only."
            )
            return []

        pipeline = self._get_diarization_pipeline()
        if pipeline is None:
            return []

        try:
            diarization = pipeline(file_path)
        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return []

        segments: list[dict[str, Any]] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                {
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "speaker": str(speaker),
                }
            )
        return segments

    def _assign_speakers(
        self, asr_segments: list[dict[str, Any]], diarization_segments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not diarization_segments:
            for segment in asr_segments:
                if not segment.get("speaker"):
                    segment["speaker"] = "speaker_0"
            return asr_segments

        for segment in asr_segments:
            best_speaker = "speaker_0"
            best_overlap = 0.0
            for diar in diarization_segments:
                overlap = max(
                    0.0,
                    min(segment["end_time"], diar["end"]) - max(segment["start_time"], diar["start"]),
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = diar["speaker"]
            segment["speaker"] = best_speaker
        return asr_segments

    def transcribe(
        self,
        file_path: str,
        language: str | None = None,
        diarization_enabled: bool | None = None,
    ) -> dict[str, Any]:
        normalized_language = None if language in (None, "auto") else language

        source_metadata = self.get_audio_metadata(file_path)
        prepared_path, temp_path, source_format = self._prepare_audio_for_bailian(file_path)
        try:
            prepared_metadata = (
                source_metadata if prepared_path == file_path else self.get_audio_metadata(prepared_path)
            )
            recognition = self._create_bailian_recognition(
                language=normalized_language,
                audio_format=source_format,
                sample_rate=prepared_metadata.sample_rate,
            )
            result = recognition.call(prepared_path)
            status_code = getattr(result, "status_code", None)
            if status_code not in (HTTPStatus.OK, 200):
                message = str(getattr(result, "message", "Bailian ASR failed"))
                raise RuntimeError(message)

            duration = float(source_metadata.duration or 0.0)
            asr_segments = self._build_asr_segments_from_bailian_result(
                result=result,
                duration=duration,
                language=normalized_language,
            )

            diarization_segments = self._run_diarization(file_path, diarization_enabled)
            asr_segments = self._assign_speakers(asr_segments, diarization_segments)
            asr_segments = self._normalize_segments_to_simplified(
                asr_segments,
                normalized_language or language,
            )

            return {
                "segments": asr_segments,
                "language": normalized_language,
            }
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
