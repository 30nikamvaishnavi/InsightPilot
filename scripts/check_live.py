#!/usr/bin/env python3
"""Check the public-demo endpoints at a deployed or local base URL."""
from __future__ import annotations

import argparse
import base64
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def request(base_url: str, path: str, *, method: str = "GET", payload: dict | None = None,
            timeout: float = 10) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def response_json(body: bytes) -> dict:
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def wait_for_health(base_url: str, timeout: float = 90) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    last_error = "health endpoint did not become ready"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, last_error
        try:
            status, body = request(base_url, "/api/health", timeout=min(5, remaining))
            if status != 200:
                last_error = f"HTTP {status}"
            else:
                health = response_json(body)
                if health.get("status") == "ok" and health.get("public_demo") is True:
                    return True, "HTTP 200; status=ok; public_demo=true"
                last_error = "health response must have status=ok and public_demo=true"
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def check(name: str, passed: bool, detail: str) -> bool:
    print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    return passed


def run_checks(base_url: str, skip_rate_limit: bool = False) -> int:
    failures = 0

    healthy, health_detail = wait_for_health(base_url)
    failures += not check("health", healthy, health_detail)
    if not healthy:
        for name in ("home page", "verified ask", "ingest disabled", "traces disabled"):
            failures += not check(name, False, "skipped because health did not become ready")
        if skip_rate_limit:
            print("SKIP rate limit: --skip-rate-limit")
        else:
            failures += not check("rate limit", False, "skipped because health did not become ready")
        return 1

    try:
        status, _ = request(base_url, "/")
        passed = status == 200
        detail = f"HTTP {status}" if passed else f"expected HTTP 200, got HTTP {status}"
    except (OSError, URLError, TimeoutError) as exc:
        passed, detail = False, str(exc)
    failures += not check("home page", passed, detail)

    try:
        status, body = request(base_url, "/api/ask", method="POST",
                               payload={"question": "total revenue by region"}, timeout=30)
        answer = response_json(body) if status == 200 else {}
        passed = status == 200 and answer.get("verified") is True
        detail = "HTTP 200; verified=true" if passed else f"expected verified=true, got HTTP {status}"
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        passed, detail = False, str(exc)
    failures += not check("verified ask", passed, detail)

    ingest_payload = {
        "filename": "live-check.csv",
        "content_base64": base64.b64encode(b"item,value\nsample,1\n").decode("ascii"),
    }
    try:
        status, _ = request(base_url, "/api/ingest", method="POST", payload=ingest_payload)
        passed = status == 403
        detail = "HTTP 403" if passed else f"expected HTTP 403, got HTTP {status}"
    except (OSError, URLError, TimeoutError) as exc:
        passed, detail = False, str(exc)
    failures += not check("ingest disabled", passed, detail)

    try:
        status, _ = request(base_url, "/api/traces")
        passed = status == 403
        detail = "HTTP 403" if passed else f"expected HTTP 403, got HTTP {status}"
    except (OSError, URLError, TimeoutError) as exc:
        passed, detail = False, str(exc)
    failures += not check("traces disabled", passed, detail)

    if skip_rate_limit:
        print("SKIP rate limit: --skip-rate-limit")
    else:
        rate_limited_at = None
        error = None
        for index in range(1, 32):
            try:
                status, _ = request(base_url, "/api/ask", method="POST",
                                   payload={"question": "total revenue by region"}, timeout=30)
                if status == 429 and rate_limited_at is None:
                    rate_limited_at = index
            except (OSError, URLError, TimeoutError) as exc:
                error = str(exc)
        passed = rate_limited_at is not None
        if passed:
            detail = f"HTTP 429 by request {rate_limited_at}/31"
        else:
            detail = f"no HTTP 429 after 31 requests{f': {error}' if error else ''}"
        failures += not check("rate limit", passed, detail)

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Base URL, such as https://insightpilot-demo.onrender.com")
    parser.add_argument("--skip-rate-limit", action="store_true", help="Skip the 31-request rate-limit check")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parser.error("base_url must be an absolute http:// or https:// URL")
    return run_checks(args.base_url, skip_rate_limit=args.skip_rate_limit)


if __name__ == "__main__":
    raise SystemExit(main())
