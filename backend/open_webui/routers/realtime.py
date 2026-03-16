"""
Voice mode backend.

Two modes:
  1. WebSocket proxy → OpenAI Realtime API (wss)
     GET /api/v1/realtime  ?token=
  2. HTTP audio chat completions → OpenAI-compatible API (OpenRouter etc.)
     POST /api/v1/realtime/audio
     Body: multipart audio file + JSON fields (history)
     Returns: { text, audio_base64, audio_format }
"""

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import aiohttp

from open_webui.utils.auth import decode_token, get_verified_user

log = logging.getLogger(__name__)

router = APIRouter()

OPENAI_REALTIME_WSS = "wss://api.openai.com/v1/realtime"
OPENAI_API_BASE = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Mode 1: WebSocket proxy to OpenAI Realtime API
# ---------------------------------------------------------------------------

@router.websocket("")
async def realtime_proxy(ws: WebSocket):
    """
    Proxy browser ↔ OpenAI/compatible Realtime WebSocket API.
    Uses admin-configured REALTIME_API_KEY and REALTIME_API_BASE_URL.

    Query params:
      token – JWT auth token
    """
    token = ws.query_params.get("token", "")

    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    user_data = decode_token(token)
    if not user_data or "id" not in user_data:
        await ws.close(code=4001, reason="Invalid token")
        return

    cfg = ws.app.state.config
    api_key = cfg.REALTIME_API_KEY
    model = cfg.REALTIME_MODEL
    api_base_url = cfg.REALTIME_API_BASE_URL or ""

    if not api_key:
        await ws.close(code=4002, reason="API key not configured")
        return

    await ws.accept()

    # If the configured URL is already a WSS URL, use it directly; otherwise build one
    if api_base_url.startswith("wss://"):
        target_url = f"{api_base_url.rstrip('/')}?model={model}"
    else:
        target_url = f"{OPENAI_REALTIME_WSS}?model={model}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                target_url, headers=headers, heartbeat=30, max_msg_size=0
            ) as upstream:
                log.info(f"Realtime WS proxy: user={user_data['id']} model={model}")

                async def to_upstream():
                    try:
                        while True:
                            data = await ws.receive_text()
                            await upstream.send_str(data)
                    except (WebSocketDisconnect, Exception):
                        pass

                async def to_client():
                    try:
                        async for msg in upstream:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws.send_text(msg.data)
                            elif msg.type in (
                                aiohttp.WSMsgType.ERROR,
                                aiohttp.WSMsgType.CLOSE,
                                aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.CLOSED,
                            ):
                                break
                    except Exception:
                        pass

                done, pending = await asyncio.wait(
                    [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

    except Exception as e:
        log.error(f"Realtime WS proxy error: {e}")
        try:
            await ws.send_text(json.dumps({"type": "error", "error": {"message": str(e)}}))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mode 2: HTTP audio chat completions (OpenRouter / OpenAI audio models)
# ---------------------------------------------------------------------------

@router.post("/audio")
async def audio_chat(
    request: Request,
    audio: UploadFile = File(...),
    history: str = Form("[]"),   # JSON-encoded list of {role, content} dicts
    image_b64: str = Form(""),   # optional JPEG base64 from camera
    user=Depends(get_verified_user),
):
    """
    Send a recorded audio blob to an OpenAI-compatible chat completions endpoint.
    Uses admin-configured REALTIME_MODEL, REALTIME_API_BASE_URL, REALTIME_API_KEY.

    Returns JSON:
      { "text": "...", "audio_base64": "...", "audio_format": "wav" }
    """
    cfg = request.app.state.config
    model = cfg.REALTIME_MODEL
    api_base = (cfg.REALTIME_API_BASE_URL or OPENAI_API_BASE).rstrip("/")
    api_key = cfg.REALTIME_API_KEY

    if not api_key:
        raise HTTPException(status_code=400, detail="Realtime API key not configured")

    voice = getattr(request.app.state.config, "TTS_VOICE", None) or "alloy"

    audio_bytes = await audio.read()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    # Detect format from MIME type or filename
    content_type = audio.content_type or ""
    if "webm" in content_type or (audio.filename or "").endswith(".webm"):
        audio_format = "webm"
    elif "mp4" in content_type or (audio.filename or "").endswith(".mp4"):
        audio_format = "mp4"
    else:
        audio_format = "wav"

    # Parse conversation history
    try:
        hist = json.loads(history)
    except Exception:
        hist = []

    # Describe camera frame with vision model (if provided and vision model configured)
    camera_description = ""
    vision_model = getattr(cfg, "REALTIME_VISION_MODEL", "") or ""
    if image_b64 and vision_model:
        vision_payload = {
            "model": vision_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Briefly describe what you see in this image in 1-2 sentences."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ]}],
            "max_tokens": 150,
        }
        try:
            async with aiohttp.ClientSession() as vsession:
                async with vsession.post(
                    f"{api_base}/chat/completions",
                    json=vision_payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as vresp:
                    if vresp.status == 200:
                        vdata = await vresp.json()
                        camera_description = vdata["choices"][0]["message"]["content"] or ""
        except Exception as e:
            log.warning(f"Vision model error: {e}")

    # Build user message content — audio model only receives audio + text (no images)
    user_content: list = [
        {
            "type": "input_audio",
            "input_audio": {
                "data": audio_b64,
                "format": audio_format,
            },
        }
    ]
    if camera_description:
        user_content.append({"type": "text", "text": f"[Camera: {camera_description}]"})

    # System prompt
    if not image_b64:
        sys_content = "You are a voice assistant. Respond based only on what you hear. Do not describe or reference any visual content."
    else:
        sys_content = "You are a voice assistant with access to a camera feed described in text."
    sys_msg = [{"role": "system", "content": sys_content}]

    # Build messages — frontend handles turn limiting/compression, send as-is
    messages = sys_msg + hist + [{"role": "user", "content": user_content}]

    response_mode = getattr(cfg, "REALTIME_RESPONSE_MODE", "streaming")
    use_streaming = response_mode != "non-streaming"

    payload: dict = {
        "model": model,
        "modalities": ["text", "audio"],
        "audio": {"voice": voice, "format": "pcm16" if use_streaming else "wav"},
        "input_audio_transcription": {"model": "whisper-1"},
        "messages": messages,
        "stream": use_streaming,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if use_streaming:
        # Return SSE stream — forward audio/transcript chunks to client as they arrive
        async def generate():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{api_base}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            log.error(f"Audio chat completions error {resp.status}: {body}")
                            yield f"data: {json.dumps({'type': 'error', 'detail': body})}\n\n"
                            return

                        async for raw_line in resp.content:
                            line = raw_line.decode("utf-8").strip()
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                continue

                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if delta.get("content"):
                                yield f"data: {json.dumps({'type': 'text', 'text': delta['content']})}\n\n"
                            audio_delta = delta.get("audio", {}) or {}
                            if audio_delta.get("data"):
                                yield f"data: {json.dumps({'type': 'audio', 'data': audio_delta['data']})}\n\n"
                            if audio_delta.get("transcript"):
                                yield f"data: {json.dumps({'type': 'transcript', 'text': audio_delta['transcript']})}\n\n"
                            # User speech transcription (if model supports it)
                            user_trans = chunk.get("input_audio_transcription") or {}
                            if user_trans.get("transcript"):
                                yield f"data: {json.dumps({'type': 'user_text', 'text': user_trans['transcript']})}\n\n"

                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                log.error(f"Audio streaming exception: {e}")
                try:
                    yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
                except Exception:
                    pass

        return StreamingResponse(generate(), media_type="text/event-stream")

    # Non-streaming: OpenAI-compatible JSON response
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error(f"Audio chat completions error {resp.status}: {body}")
                    raise HTTPException(status_code=resp.status, detail=body)

                data = await resp.json()
                choice = data["choices"][0]["message"]
                text = choice.get("content") or ""
                audio_out = choice.get("audio", {}) or {}
                audio_out_b64 = audio_out.get("data", "")
                audio_out_fmt = audio_out.get("format", "wav")
                if not text and audio_out.get("transcript"):
                    text = audio_out["transcript"]

        user_text = data.get("input_audio_transcription", {}).get("transcript", "")
        return {
            "text": text,
            "audio_base64": audio_out_b64,
            "audio_format": audio_out_fmt,
            "user_text": user_text,
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Audio chat completions exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))
