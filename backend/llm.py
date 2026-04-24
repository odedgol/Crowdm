from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from anthropic import AsyncAnthropic


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_PREFIX = "ollama:"


class OllamaUnavailable(RuntimeError):
    pass


def is_ollama_model(model: str) -> bool:
    return model.startswith(OLLAMA_PREFIX)


def strip_ollama_prefix(model: str) -> str:
    return model[len(OLLAMA_PREFIX):] if model.startswith(OLLAMA_PREFIX) else model


def requires_anthropic_key(model: str) -> bool:
    return not is_ollama_model(model)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_loose(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_RE.search(raw)
        if not match:
            raise
        return json.loads(match.group(0))


def _anthropic_text(message: Any) -> str:
    chunks: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    return "\n".join(chunks)


def _anthropic_usage(message: Any) -> dict:
    u = message.usage
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }


async def _anthropic_chat(
    client: AsyncAnthropic,
    *,
    model: str,
    max_tokens: int,
    system_blocks: list[dict],
    messages: list[dict],
) -> tuple[str, dict]:
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
    )
    return _anthropic_text(resp), _anthropic_usage(resp)


def _flatten_system(blocks: list[dict]) -> str:
    return "\n\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _flatten_user(content) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content, []
    text_parts: list[str] = []
    images: list[str] = []
    for block in content:
        t = block.get("type")
        if t == "text":
            text_parts.append(block.get("text", ""))
        elif t == "image":
            src = block.get("source", {})
            if src.get("type") == "base64":
                images.append(src.get("data", ""))
            text_parts.append("[image attached]")
    return "\n\n".join(p for p in text_parts if p), images


async def _ollama_chat(
    *,
    model: str,
    max_tokens: int,
    system_blocks: list[dict],
    messages: list[dict],
) -> tuple[str, dict]:
    flat_messages: list[dict] = []
    sys_text = _flatten_system(system_blocks)
    if sys_text:
        flat_messages.append({"role": "system", "content": sys_text})
    for msg in messages:
        role = msg.get("role", "user")
        text, images = _flatten_user(msg.get("content"))
        entry: dict = {"role": role, "content": text}
        if images:
            entry["images"] = images
        flat_messages.append(entry)

    payload = {
        "model": model,
        "messages": flat_messages,
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.7,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
    except httpx.ConnectError as exc:
        raise OllamaUnavailable(
            f"Could not reach Ollama at {OLLAMA_BASE_URL}. Is `ollama serve` running? ({exc})"
        ) from exc
    if resp.status_code == 404:
        raise OllamaUnavailable(
            f"Ollama model '{model}' not found. Pull it first: `ollama pull {model}`."
        )
    if resp.status_code != 200:
        raise OllamaUnavailable(
            f"Ollama call failed ({resp.status_code}): {resp.text[:300]}"
        )
    data = resp.json()
    text = data.get("message", {}).get("content", "") or ""
    usage = {
        "input_tokens": int(data.get("prompt_eval_count", 0) or 0),
        "output_tokens": int(data.get("eval_count", 0) or 0),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    return text, usage


def accumulate_usage(total: dict, usage: dict) -> None:
    for key, val in usage.items():
        total[key] = total.get(key, 0) + int(val or 0)


async def chat_text(
    *,
    model: str,
    max_tokens: int,
    system_blocks: list[dict],
    messages: list[dict],
    anthropic_client: AsyncAnthropic | None = None,
) -> tuple[str, dict]:
    if is_ollama_model(model):
        return await _ollama_chat(
            model=strip_ollama_prefix(model),
            max_tokens=max_tokens,
            system_blocks=system_blocks,
            messages=messages,
        )
    if anthropic_client is None:
        anthropic_client = AsyncAnthropic()
    return await _anthropic_chat(
        anthropic_client,
        model=model,
        max_tokens=max_tokens,
        system_blocks=system_blocks,
        messages=messages,
    )


async def chat_json(
    *,
    model: str,
    max_tokens: int,
    system_blocks: list[dict],
    messages: list[dict],
    anthropic_client: AsyncAnthropic | None = None,
) -> tuple[dict, dict]:
    raw, usage = await chat_text(
        model=model,
        max_tokens=max_tokens,
        system_blocks=system_blocks,
        messages=messages,
        anthropic_client=anthropic_client,
    )
    try:
        return parse_json_loose(raw), usage
    except json.JSONDecodeError:
        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "That response was not valid JSON. Resend ONLY the JSON object, no prose."},
        ]
        raw2, usage2 = await chat_text(
            model=model,
            max_tokens=max_tokens,
            system_blocks=system_blocks,
            messages=repair_messages,
            anthropic_client=anthropic_client,
        )
        for k, v in usage2.items():
            usage[k] = usage.get(k, 0) + v
        return parse_json_loose(raw2), usage
