"""OpenAI Realtime session endpoints for voice chat."""

from __future__ import annotations

import asyncio
import os
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websockets
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from lifetrace.util.logging_config import get_logger
from lifetrace.util.settings import settings

router = APIRouter(prefix="/api/voice-chat", tags=["voice-chat"])
logger = get_logger()

OPENAI_API_BASE = "https://api.openai.com/v1"
PLACEHOLDER_VALUES = {"", "YOUR_OPENAI_API_KEY_HERE", "YOUR_LLM_KEY_HERE", "xxx"}
BAILIAN_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"


class RealtimeSessionRequest(BaseModel):
    model: str | None = None
    voice: str | None = None
    instructions: str | None = None


@router.get("/bailian/bootstrap")
def get_bailian_bootstrap() -> dict[str, Any]:
    config = _resolve_bailian_config()
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Missing Bailian config: api_key/workspace_id/app_id",
        )
    return {
        "workspace_id": config["workspace_id"],
        "app_id": config["app_id"],
        "model": "multimodal-dialog",
    }


def _is_valid_value(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in PLACEHOLDER_VALUES)


def _resolve_openai_api_key() -> str | None:
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key

    openai_config_key = settings.get("openai.api_key")
    if isinstance(openai_config_key, str) and openai_config_key not in PLACEHOLDER_VALUES:
        return openai_config_key

    llm_base_url = str(settings.get("llm.base_url", "") or "")
    llm_api_key = str(settings.get("llm.api_key", "") or "")
    if "openai.com" in llm_base_url and llm_api_key not in PLACEHOLDER_VALUES:
        return llm_api_key

    return None


def _resolve_bailian_config() -> dict[str, str] | None:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
    if not _is_valid_value(api_key):
        config_key = str(settings.get("bailian.api_key", "") or "")
        if _is_valid_value(config_key):
            api_key = config_key
        else:
            llm_base_url = str(settings.get("llm.base_url", "") or "")
            llm_api_key = str(settings.get("llm.api_key", "") or "")
            if "dashscope.aliyuncs.com" in llm_base_url and _is_valid_value(llm_api_key):
                api_key = llm_api_key

    workspace_id = os.getenv("BAILIAN_WORKSPACE_ID") or str(
        settings.get("bailian.workspace_id", "") or ""
    )
    app_id = os.getenv("BAILIAN_APP_ID") or str(settings.get("bailian.app_id", "") or "")

    if not (_is_valid_value(api_key) and _is_valid_value(workspace_id) and _is_valid_value(app_id)):
        return None

    return {
        "api_key": api_key.strip(),
        "workspace_id": workspace_id.strip(),
        "app_id": app_id.strip(),
        "model": "multimodal-dialog",
    }


def _resolve_realtime_defaults() -> tuple[str, str]:
    model = str(settings.get("openai.realtime.model", "") or "").strip()
    voice = str(settings.get("openai.realtime.voice", "") or "").strip()
    return (model or "gpt-4o-realtime-preview", voice or "alloy")


@router.post("/session")
def create_realtime_session(payload: RealtimeSessionRequest) -> dict[str, Any]:
    api_key = _resolve_openai_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "OpenAI API key is missing. Set OPENAI_API_KEY or "
                "configure openai.api_key in config.yaml."
            ),
        )

    default_model, default_voice = _resolve_realtime_defaults()
    model = (payload.model or default_model).strip()
    voice = (payload.voice or default_voice).strip()
    instructions = (payload.instructions or "").strip()

    session_body: dict[str, Any] = {
        "model": model,
        "voice": voice,
        # Enable user transcript events from realtime input audio.
        "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
    }
    if instructions:
        session_body["instructions"] = instructions

    try:
        request = Request(
            url=f"{OPENAI_API_BASE}/realtime/sessions",
            method="POST",
            data=json.dumps(session_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            raw_body = response.read().decode("utf-8")
            return json.loads(raw_body)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        logger.error(
            "OpenAI realtime session request failed. status=%s body=%s",
            exc.code,
            error_body,
        )
        raise HTTPException(
            status_code=exc.code,
            detail="Failed to create realtime session",
        ) from exc
    except URLError as exc:
        logger.error("Failed to create OpenAI realtime session: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to connect to OpenAI") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create OpenAI realtime session: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to connect to OpenAI") from exc


@router.websocket("/bailian/ws")
async def proxy_bailian_voice_chat(websocket: WebSocket):
    """Proxy browser websocket traffic to Bailian realtime websocket.

    Browser websocket cannot attach custom Authorization headers, so we terminate
    at backend and forward upstream with API key header.
    """

    await websocket.accept()
    config = _resolve_bailian_config()
    if not config:
        logger.warning(
            "Bailian WS: config missing. api_key=%s, workspace_id=%s, app_id=%s",
            bool(os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY") or settings.get("bailian.api_key", "")),
            bool(settings.get("bailian.workspace_id", "")),
            bool(settings.get("bailian.app_id", "")),
        )
        await websocket.send_json(
            {
                "header": {"event": "TaskFailed"},
                "payload": {
                    "error_code": "CONFIG_MISSING",
                    "error_message": "Missing Bailian config: api_key/workspace_id/app_id",
                },
            }
        )
        await websocket.close(code=1008)
        return

    logger.info(f"Bailian WS: config OK, connecting to upstream (workspace={config['workspace_id']}, app={config['app_id']})")
    uri = f"{BAILIAN_WS_URL}?workspace_id={config['workspace_id']}&app_id={config['app_id']}"
    logger.info(f"Bailian WS: upstream URI = {uri}")
    upstream = None
    try:
        upstream = await websockets.connect(
            uri,
            additional_headers={
                "Authorization": f"Bearer {config['api_key']}",
                "X-DashScope-WorkSpace": config["workspace_id"],
            },
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        logger.info("Bailian WS: upstream connected successfully")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to connect Bailian websocket: {exc}")
        await websocket.send_json(
            {
                "header": {"event": "TaskFailed"},
                "payload": {
                    "error_code": "UPSTREAM_CONNECT_FAILED",
                    "error_message": f"Failed to connect Bailian websocket: {exc}",
                },
            }
        )
        await websocket.close(code=1011)
        return

    async def client_to_upstream():
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    logger.info("Bailian WS: client disconnected")
                    break
                if message.get("text") is not None:
                    logger.debug(f"Bailian WS: client -> upstream (text, {len(message['text'])} bytes)")
                    await upstream.send(message["text"])
                elif message.get("bytes") is not None:
                    logger.debug(f"Bailian WS: client -> upstream (binary, {len(message['bytes'])} bytes)")
                    await upstream.send(message["bytes"])
        except WebSocketDisconnect:
            logger.info("Bailian WS: client WebSocket disconnected")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Client -> Bailian forwarding ended: {exc}")

    async def upstream_to_client():
        try:
            msg_count = 0
            async for message in upstream:
                msg_count += 1
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    if msg_count <= 3:
                        logger.info(f"Bailian WS: upstream -> client msg#{msg_count}: {message[:200] if len(message) > 200 else message}")
                    await websocket.send_text(message)
            logger.info(f"Bailian WS: upstream closed after {msg_count} messages")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Bailian -> client forwarding ended: {exc}")

    tasks = [
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        try:
            task.result()
        except Exception:
            pass

    try:
        await upstream.close()
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass
