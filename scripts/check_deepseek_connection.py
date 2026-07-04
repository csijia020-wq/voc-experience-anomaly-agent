"""DeepSeek connection diagnostic tool.

This script performs layered checks without printing the full API key:
environment -> DNS -> TCP -> TLS -> minimal API call.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import socket
import ssl
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
load_dotenv(BACKEND / ".env")


def mask_key(value: str) -> str:
    if not value or value.startswith("your_"):
        return ""
    return f"****{value[-4:]}" if len(value) >= 4 else "****"


def status(ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"ok": ok, "detail": detail}


def classify_http_status(code: int) -> str:
    if code == 401:
        return "LLM_AUTH_ERROR"
    if code == 402:
        return "LLM_QUOTA_ERROR"
    if code == 404:
        return "LLM_NOT_FOUND"
    if code == 429:
        return "LLM_RATE_LIMIT"
    if 400 <= code < 500:
        return f"LLM_HTTP_{code}"
    if code >= 500:
        return f"LLM_SERVER_{code}"
    return "OK"


def main() -> int:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("DEEPSEEK_MODEL", os.getenv("MODEL_NAME", "deepseek-chat"))
    parsed = urlparse(base_url)
    host = parsed.hostname or "api.deepseek.com"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    result: Dict[str, Any] = {
        "environment": {
            "api_key_configured": bool(api_key and not api_key.startswith("your_")),
            "api_key_suffix": mask_key(api_key),
            "base_url": base_url,
            "model": model,
            "http_proxy_configured": bool(os.getenv("HTTP_PROXY") or os.getenv("http_proxy")),
            "https_proxy_configured": bool(os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")),
            "no_proxy": os.getenv("NO_PROXY") or os.getenv("no_proxy") or "",
            "python": sys.version.split()[0],
            "openai_sdk": importlib.metadata.version("openai"),
            "httpx": importlib.metadata.version("httpx"),
        },
        "dns": None,
        "tcp": None,
        "tls": None,
        "api": None,
        "model_call": None,
    }

    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["dns"] = status(True, ", ".join(sorted({item[4][0] for item in addresses})[:5]))
    except Exception as exc:
        result["dns"] = status(False, f"LLM_DNS_ERROR: {type(exc).__name__}: {exc}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        with socket.create_connection((host, port), timeout=10):
            pass
        result["tcp"] = status(True, f"{host}:{port} reachable")
    except Exception as exc:
        result["tcp"] = status(False, f"LLM_CONNECTION_ERROR: {type(exc).__name__}: {exc}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                result["tls"] = status(
                    True,
                    f"TLS {tls.version()}, issuer={cert.get('issuer', '')}, cafile={ssl.get_default_verify_paths().cafile}",
                )
    except Exception as exc:
        result["tls"] = status(False, f"LLM_TLS_ERROR: {type(exc).__name__}: {exc}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not result["environment"]["api_key_configured"]:
        result["api"] = status(False, "LLM_CONFIG_ERROR: DEEPSEEK_API_KEY is not configured")
        result["model_call"] = status(False, "Skipped because API key is missing")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复：连接成功"}],
        "max_tokens": 8,
        "temperature": 0,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(connect=10, read=30, write=10, pool=10)) as client:
            response = client.post(endpoint, headers=headers, json=payload)
        code = classify_http_status(response.status_code)
        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            result["api"] = status(True, "HTTP 200")
            result["model_call"] = status(True, content)
        else:
            safe_body = response.text[:500]
            result["api"] = status(False, f"{code}: HTTP {response.status_code}: {safe_body}")
            result["model_call"] = status(False, f"Skipped after API error {code}")
    except httpx.ConnectError as exc:
        text = str(exc).lower()
        code = "LLM_TLS_ERROR" if "tls" in text or "ssl" in text or "eof" in text else "LLM_CONNECTION_ERROR"
        result["api"] = status(False, f"{code}: {type(exc).__name__}: {exc}")
        result["model_call"] = status(False, "Skipped after connection error")
    except httpx.TimeoutException as exc:
        result["api"] = status(False, f"LLM_TIMEOUT: {type(exc).__name__}: {exc}")
        result["model_call"] = status(False, "Skipped after timeout")
    except Exception as exc:
        result["api"] = status(False, f"LLM_API_ERROR: {type(exc).__name__}: {exc}")
        result["model_call"] = status(False, "Skipped after API error")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
