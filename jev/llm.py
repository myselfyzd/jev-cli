"""HTTP 客户端。只用标准库，密钥绝不进日志/文件。"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
MAX_RETRIES = 3


class LLMError(RuntimeError):
    """带上人话的错误，CLI 直接把 message 打给用户。"""


def redact(text: str, *secrets: str) -> str:
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "[REDACTED]")
    return out


def http_post_json(url: str, headers: dict, body: dict, *, timeout: float = 60,
                   retries: int = MAX_RETRIES, secrets: tuple = ()) -> dict:
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
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", errors="replace")[:300], *secrets)
            last_error = f"HTTP {exc.code}：{detail}"
            if exc.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
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
    raise LLMError(last_error)


def deepseek_chat(api_key: str, messages: list[dict], *, model: str = "deepseek-chat",
                  temperature: float = 0.7, json_mode: bool = True, max_tokens: int = 800,
                  timeout: float = 60) -> tuple[str, dict]:
    body: dict = {"model": model, "messages": messages, "temperature": temperature,
                  "stream": False, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = http_post_json(DEEPSEEK_URL, {"Authorization": f"Bearer {api_key}"}, body,
                              timeout=timeout, secrets=(api_key,))
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"接口返回结构异常：{exc}") from None
    return content, response.get("usage") or {}


def openrouter_decisions(api_key: str, state: dict, questions: dict, *,
                         model: str = JEV_MODEL, timeout: float = 25) -> dict:
    response = http_post_json(JEV_ENDPOINT, {"Authorization": f"Bearer {api_key}"},
                              {"model": model or JEV_MODEL, "state": state, "questions": questions},
                              timeout=timeout, secrets=(api_key,))
    if isinstance(response.get("data"), dict) and "answers" in response["data"]:
        response = response["data"]
    if "answers" not in response:
        raise LLMError(f"Jev 返回里没有 answers：{json.dumps(response, ensure_ascii=False)[:200]}")
    return response
