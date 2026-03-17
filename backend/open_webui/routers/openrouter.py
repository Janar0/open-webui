import asyncio
import json
import logging
from typing import Optional

import aiohttp
from aiocache import cached

from fastapi import Depends, HTTPException, Request, APIRouter
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from open_webui.models.models import Models
from open_webui.models.access_grants import AccessGrants
from open_webui.models.groups import Groups
from open_webui.env import (
    MODELS_CACHE_TTL,
    AIOHTTP_CLIENT_SESSION_SSL,
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST,
    BYPASS_MODEL_ACCESS_CONTROL,
)
from open_webui.models.users import UserModel

from open_webui.constants import ERROR_MESSAGES

from open_webui.utils.payload import (
    apply_model_params_to_body_openai,
    apply_system_prompt_to_body,
)
from open_webui.utils.misc import (
    cleanup_response,
    stream_chunks_handler,
    stream_wrapper,
)

from open_webui.utils.auth import get_admin_user, get_verified_user

log = logging.getLogger(__name__)

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

##########################################
#
# Utility functions
#
##########################################


def get_openrouter_headers(key: str, config: dict = None) -> dict:
    """Build headers for OpenRouter API requests."""
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://openwebui.com/",
        "X-Title": "Open WebUI",
    }

    if key:
        headers["Authorization"] = f"Bearer {key}"

    if config and config.get("headers") and isinstance(config.get("headers"), dict):
        headers = {**headers, **config["headers"]}

    return headers


async def fetch_openrouter_models(url: str, key: str) -> dict:
    """Fetch models from OpenRouter API with rich metadata."""
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            headers = get_openrouter_headers(key)

            async with session.get(
                f"{url}/models",
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                if response.status != 200:
                    log.error(f"OpenRouter models request failed: {response.status}")
                    return None
                return await response.json()
    except Exception as e:
        log.error(f"OpenRouter connection error: {e}")
        return None


def transform_openrouter_model(model: dict, idx: int = 0) -> dict:
    """Transform an OpenRouter model entry to Open WebUI format,
    preserving OpenRouter-specific metadata (pricing, context_length, etc.)."""
    model_id = model.get("id", "")
    pricing = model.get("pricing", {})
    architecture = model.get("architecture", {})

    return {
        "id": model_id,
        "name": model.get("name", model_id),
        "owned_by": "openrouter",
        "openai": {"id": model_id},
        "connection_type": "external",
        "urlIdx": idx,
        # OpenRouter-specific metadata
        "openrouter": {
            "id": model_id,
            "pricing": pricing,
            "context_length": model.get("context_length"),
            "max_completion_tokens": model.get("max_completion_tokens"),
            "description": model.get("description", ""),
            "architecture": architecture,
            "supported_parameters": model.get("supported_parameters", []),
            "input_modalities": model.get("input_modalities", ["text"]),
            "output_modalities": model.get("output_modalities", ["text"]),
        },
    }


def apply_openrouter_params(payload: dict, config: dict) -> dict:
    """Apply OpenRouter-specific parameters to the payload.

    Adds provider routing, transforms, plugins, and modalities
    from the connection config or payload metadata.
    """
    # Provider routing preferences
    provider = config.get("provider")
    if provider:
        payload["provider"] = provider

    # Message transforms (e.g., middle-out compression)
    transforms = config.get("transforms")
    if transforms:
        payload["transforms"] = transforms

    # Plugins (e.g., web search)
    plugins = config.get("plugins")
    if plugins:
        payload["plugins"] = plugins

    # Image generation modalities
    if "modalities" not in payload:
        modalities = config.get("modalities")
        if modalities:
            payload["modalities"] = modalities

    # Image config (aspect_ratio, etc.)
    if "image_config" not in payload:
        image_config = config.get("image_config")
        if image_config:
            payload["image_config"] = image_config

    return payload


def apply_prompt_caching(payload: dict, config: dict) -> dict:
    """Apply prompt caching to messages for supported providers.

    For Anthropic models: adds cache_control breakpoints to system prompts
    and the last user message to maximize cache hits.

    For OpenAI/DeepSeek/Gemini: caching is automatic, no changes needed.

    Can be disabled via config: {"prompt_caching": false}
    TTL can be configured: {"prompt_cache_ttl": "1h"} (default: ephemeral/5min)
    """
    if not config.get("prompt_caching", True):
        return payload

    model_id = payload.get("model", "")
    messages = payload.get("messages", [])

    if not messages:
        return payload

    # Only apply explicit cache_control for Anthropic models
    is_anthropic = any(
        prefix in model_id.lower()
        for prefix in ["anthropic/", "claude"]
    )

    if not is_anthropic:
        # OpenAI, DeepSeek, Gemini have automatic caching — no changes needed
        return payload

    cache_ttl = config.get("prompt_cache_ttl", None)
    cache_control = {"type": "ephemeral"}
    if cache_ttl:
        cache_control["ttl"] = cache_ttl

    # Apply cache_control to system message(s)
    for msg in messages:
        if msg.get("role") != "system":
            continue

        content = msg.get("content")
        if isinstance(content, str):
            # Convert string content to content block format with cache_control
            msg["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": cache_control,
                }
            ]
        elif isinstance(content, list):
            # Add cache_control to the last text block in the system message
            for i in range(len(content) - 1, -1, -1):
                if isinstance(content[i], dict) and content[i].get("type") == "text":
                    content[i]["cache_control"] = cache_control
                    break

    # Also cache the last substantial user message for multi-turn conversations
    # This helps when users have long conversation histories
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") != "user":
            continue

        content = msg.get("content")
        if isinstance(content, str) and len(content) > 500:
            msg["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": cache_control,
                }
            ]
        elif isinstance(content, list):
            # Add cache_control to last text block
            for j in range(len(content) - 1, -1, -1):
                if isinstance(content[j], dict) and content[j].get("type") == "text":
                    content[j]["cache_control"] = cache_control
                    break
        break  # Only the last user message

    return payload


##########################################
#
# API routes
#
##########################################

router = APIRouter()


# ---- Config endpoints ----


class OpenRouterConfigForm(BaseModel):
    ENABLE_OPENROUTER_API: Optional[bool] = None
    OPENROUTER_API_BASE_URL: str
    OPENROUTER_API_KEY: str
    OPENROUTER_API_CONFIG: dict


@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_OPENROUTER_API": request.app.state.config.ENABLE_OPENROUTER_API,
        "OPENROUTER_API_BASE_URL": request.app.state.config.OPENROUTER_API_BASE_URL,
        "OPENROUTER_API_KEY": request.app.state.config.OPENROUTER_API_KEY,
        "OPENROUTER_API_CONFIG": request.app.state.config.OPENROUTER_API_CONFIG,
    }


@router.post("/config/update")
async def update_config(
    request: Request, form_data: OpenRouterConfigForm, user=Depends(get_admin_user)
):
    if form_data.ENABLE_OPENROUTER_API is not None:
        request.app.state.config.ENABLE_OPENROUTER_API = (
            form_data.ENABLE_OPENROUTER_API
        )
    request.app.state.config.OPENROUTER_API_BASE_URL = form_data.OPENROUTER_API_BASE_URL
    request.app.state.config.OPENROUTER_API_KEY = form_data.OPENROUTER_API_KEY
    request.app.state.config.OPENROUTER_API_CONFIG = form_data.OPENROUTER_API_CONFIG

    return {
        "ENABLE_OPENROUTER_API": request.app.state.config.ENABLE_OPENROUTER_API,
        "OPENROUTER_API_BASE_URL": request.app.state.config.OPENROUTER_API_BASE_URL,
        "OPENROUTER_API_KEY": request.app.state.config.OPENROUTER_API_KEY,
        "OPENROUTER_API_CONFIG": request.app.state.config.OPENROUTER_API_CONFIG,
    }


# ---- Connection verification ----


class OpenRouterVerifyForm(BaseModel):
    url: str
    key: str


@router.post("/verify")
async def verify_connection(
    request: Request,
    form_data: OpenRouterVerifyForm,
    user=Depends(get_admin_user),
):
    result = await fetch_openrouter_models(form_data.url, form_data.key)
    if result is None:
        raise HTTPException(
            status_code=500, detail="Failed to connect to OpenRouter API"
        )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ---- Models ----


async def get_all_models_responses(request: Request) -> list:
    """Fetch models from OpenRouter and return as a list."""
    if not request.app.state.config.ENABLE_OPENROUTER_API:
        return []

    url = request.app.state.config.OPENROUTER_API_BASE_URL
    key = request.app.state.config.OPENROUTER_API_KEY

    response = await fetch_openrouter_models(url, key)
    if response:
        return [response]
    return []


async def get_filtered_models(models, user):
    """Filter models based on user access control."""
    model_ids = [model["id"] for model in models.get("data", [])]
    model_infos = {
        model_info.id: model_info
        for model_info in Models.get_models_by_ids(model_ids)
    }
    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id)
    }

    accessible_model_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="model",
        resource_ids=list(model_infos.keys()),
        permission="read",
        user_group_ids=user_group_ids,
    )

    filtered_models = []
    for model in models.get("data", []):
        model_info = model_infos.get(model["id"])
        if model_info:
            if user.id == model_info.user_id or model_info.id in accessible_model_ids:
                filtered_models.append(model)
    return filtered_models


@cached(
    ttl=MODELS_CACHE_TTL,
    key=lambda _, user: f"openrouter_all_models_{user.id}"
    if user
    else "openrouter_all_models",
)
async def get_all_models(request: Request, user: UserModel) -> dict:
    """Fetch, transform, and cache all OpenRouter models."""
    log.info("openrouter.get_all_models()")

    if not request.app.state.config.ENABLE_OPENROUTER_API:
        return {"data": []}

    config = request.app.state.config.OPENROUTER_API_CONFIG or {}

    responses = await get_all_models_responses(request)

    models = {}
    for response in responses:
        model_list = response.get("data", []) if isinstance(response, dict) else []

        # Filter by configured model_ids if specified
        allowed_ids = config.get("model_ids", [])

        for model in model_list:
            model_id = model.get("id", "")

            # Skip if model_ids filter is set and this model isn't in it
            if allowed_ids and model_id not in allowed_ids:
                continue

            if model_id and model_id not in models:
                models[model_id] = transform_openrouter_model(model)

    request.app.state.OPENROUTER_MODELS = models
    return {"data": list(models.values())}


@router.get("/models")
async def get_models(
    request: Request, user=Depends(get_verified_user)
):
    if not request.app.state.config.ENABLE_OPENROUTER_API:
        raise HTTPException(status_code=503, detail="OpenRouter API is disabled")

    models = await get_all_models(request, user=user)

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        models["data"] = await get_filtered_models(models, user)

    return models


# ---- Chat Completions ----


@router.post("/chat/completions")
async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user=Depends(get_verified_user),
    bypass_filter: Optional[bool] = False,
    bypass_system_prompt: bool = False,
):
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    payload = {**form_data}
    metadata = payload.pop("metadata", None)

    model_id = form_data.get("model")
    model_info = Models.get_model_by_id(model_id)

    # Check model info and override the payload
    if model_info:
        if model_info.base_model_id:
            base_model_id = (
                request.base_model_id
                if hasattr(request, "base_model_id")
                else model_info.base_model_id
            )
            payload["model"] = base_model_id
            model_id = base_model_id

        params = model_info.params.model_dump()

        if params:
            system = params.pop("system", None)
            payload = apply_model_params_to_body_openai(params, payload)
            if not bypass_system_prompt:
                payload = apply_system_prompt_to_body(system, payload, metadata, user)

        # Check if user has access to the model
        if not bypass_filter and user.role == "user":
            user_group_ids = {
                group.id for group in Groups.get_groups_by_member_id(user.id)
            }
            if not (
                user.id == model_info.user_id
                or AccessGrants.has_access(
                    user_id=user.id,
                    resource_type="model",
                    resource_id=model_info.id,
                    permission="read",
                    user_group_ids=user_group_ids,
                )
            ):
                raise HTTPException(status_code=403, detail="Model not found")
    elif not bypass_filter:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Model not found")

    # Verify model exists in cache
    models = request.app.state.OPENROUTER_MODELS
    if not models or model_id not in models:
        await get_all_models(request, user=user)
        models = request.app.state.OPENROUTER_MODELS
    model = models.get(model_id) if models else None

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    url = request.app.state.config.OPENROUTER_API_BASE_URL
    key = request.app.state.config.OPENROUTER_API_KEY
    config = request.app.state.config.OPENROUTER_API_CONFIG or {}

    # Apply OpenRouter-specific parameters from config
    payload = apply_openrouter_params(payload, config)

    # Also apply any per-request OpenRouter params from metadata
    if metadata and metadata.get("openrouter"):
        payload = apply_openrouter_params(payload, metadata["openrouter"])

    # Apply prompt caching (cache_control for Anthropic, auto for others)
    payload = apply_prompt_caching(payload, config)

    # Handle max_tokens / max_completion_tokens
    if "max_completion_tokens" in payload:
        payload["max_tokens"] = payload.pop("max_completion_tokens")

    headers = get_openrouter_headers(key, config)

    request_url = f"{url}/chat/completions"
    payload_json = json.dumps(payload)

    r = None
    session = None
    streaming = False

    try:
        session = aiohttp.ClientSession(
            trust_env=True,
            timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT),
        )

        r = await session.request(
            method="POST",
            url=request_url,
            data=payload_json,
            headers=headers,
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        )

        # Check if response is SSE
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            streaming = True
            return StreamingResponse(
                stream_wrapper(r, session, stream_chunks_handler),
                status_code=r.status,
                headers=dict(r.headers),
            )
        else:
            try:
                response = await r.json()
            except Exception as e:
                log.error(e)
                response = await r.text()

            if r.status >= 400:
                if isinstance(response, (dict, list)):
                    return JSONResponse(status_code=r.status, content=response)
                else:
                    return PlainTextResponse(status_code=r.status, content=response)

            return response
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=r.status if r else 500,
            detail="Open WebUI: OpenRouter Connection Error",
        )
    finally:
        if not streaming:
            await cleanup_response(r, session)


# ---- Generation Stats ----


@router.get("/generation/{generation_id}")
async def get_generation_stats(
    request: Request,
    generation_id: str,
    user=Depends(get_verified_user),
):
    """Get generation stats (token counts, cost) from OpenRouter."""
    if not request.app.state.config.ENABLE_OPENROUTER_API:
        raise HTTPException(status_code=503, detail="OpenRouter API is disabled")

    url = request.app.state.config.OPENROUTER_API_BASE_URL
    key = request.app.state.config.OPENROUTER_API_KEY
    config = request.app.state.config.OPENROUTER_API_CONFIG or {}

    headers = get_openrouter_headers(key, config)

    try:
        async with aiohttp.ClientSession(
            trust_env=True,
            timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT),
        ) as session:
            async with session.get(
                f"{url}/generation?id={generation_id}",
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                if r.status != 200:
                    try:
                        error_data = await r.json()
                    except Exception:
                        error_data = await r.text()
                    raise HTTPException(status_code=r.status, detail=error_data)
                return await r.json()
    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=500, detail="OpenRouter: Connection Error")
