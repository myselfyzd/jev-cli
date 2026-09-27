"""HTTP 客户端。只用标准库，密钥绝不进日志/文件。"""

from __future__ import annotations

import itertools
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
MAX_RETRIES = 3
_TRACE_COUNTER = itertools.count(1)


def _trace_dir() -> Path | None:
    """JEV_TRACE_DIR=/tmp/x 时，把每一步的原始请求/响应落盘，方便讲解和排错。"""
    raw = (os.environ.get("JEV_TRACE_DIR") or "").strip()
    return Path(raw).expanduser() if raw else None


def _mask_headers(headers: dict) -> dict:
    masked = {}
    for key, value in headers.items():
        if key.lower() == "authorization" and isinstance(value, str) and " " in value:
            scheme, secret = value.split(" ", 1)
            value = f"{scheme} {secret[:6]}…{secret[-4:]}（已脱敏）"
        masked[key] = value
    return masked


def _write_trace(label: str, url: str, headers: dict, body: dict,
                 response: dict | None = None, error: str | None = None) -> None:
    directory = _trace_dir()
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "step": next(_TRACE_COUNTER),
        "label": label,
        "url": url,
        "request": {"headers": _mask_headers(headers), "body": body},
    }
    if response is not None:
        entry["response"] = response
    if error is not None:
        entry["error"] = error
    path = directory / f"{entry['step']:02d}-{label}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


class LLMError(RuntimeError):
    """带上人话的错误，CLI 直接把 message 打给用户。"""


def redact(text: str, *secrets: str) -> str:
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "[REDACTED]")
    return out


def http_post_json(url: str, headers: dict, body: dict, *, timeout: float = 60,
                   retries: int = MAX_RETRIES, secrets: tuple = (), label: str = "request") -> dict:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Accept": "application/json", **headers},
    )
    last_error = "未知错误"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
                _write_trace(label, url, headers, body, response=parsed)
                return parsed
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", errors="replace")[:300], *secrets)
            last_error = f"HTTP {exc.code}：{detail}"
            if exc.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            _write_trace(label, url, headers, body, error=last_error)
            raise LLMError(last_error) from None
        except (TimeoutError, socket.timeout) as exc:
            last_error = f"请求超时（{timeout}s）：{exc}"
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
        except urllib.error.URLError as exc:
            last_error = f"连不上：{redact(getattr(exc, 'reason', exc), *secrets)}"
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
        except json.JSONDecodeError as exc:
            raise LLMError(f"接口返回的不是合法 JSON：{exc}") from None
    _write_trace(label, url, headers, body, error=last_error)
    raise LLMError(last_error)


def deepseek_chat(api_key: str, messages: list[dict], *, model: str = "deepseek-chat",
                  temperature: float = 0.7, json_mode: bool = True, max_tokens: int = 800,
                  timeout: float = 60, label: str = "deepseek") -> tuple[str, dict]:
    body: dict = {"model": model, "messages": messages, "temperature": temperature,
                  "stream": False, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = http_post_json(DEEPSEEK_URL, {"Authorization": f"Bearer {api_key}"}, body,
                              timeout=timeout, secrets=(api_key,), label=label)
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"接口返回结构异常：{exc}") from None
    return content, response.get("usage") or {}


def openrouter_decisions(api_key: str, state: dict, questions: dict, *,
                         model: str = JEV_MODEL, timeout: float = 25, label: str = "jev") -> dict:
    response = http_post_json(JEV_ENDPOINT, {"Authorization": f"Bearer {api_key}"},
                              {"model": model or JEV_MODEL, "state": state, "questions": questions},
                              timeout=timeout, secrets=(api_key,), label=label)
    if isinstance(response.get("data"), dict) and "answers" in response["data"]:
        response = response["data"]
    if "answers" not in response:
        raise LLMError(f"Jev 返回里没有 answers：{json.dumps(response, ensure_ascii=False)[:200]}")
    return response
