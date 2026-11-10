"""Talks to Sochen (sochen.dev) over HTTPS with the standard library only.

Three account endpoints (the Agent API, with the user's ``sk_sochen_`` key) and one public one:

- ``POST /api/v1/run``: hand Sochen a job; returns at once or after a short wait.
- ``GET /api/v1/jobs/{chat_id}``: how a job stands, without sending it anything (``wait`` holds it
  up to a minute for news: a question from a call's business, or the job being done).
- ``POST /api/v1/jobs/{chat_id}/answer``: the user's answer to a question a call is holding for.
- ``GET /api/v1/desk``: what needs the user, what's running and what finished today.
- ``GET /api/v1/credits``: the API credits left to spend (every account starts with 100 free).
- ``POST /api/mcp``: Sochen's free tools (invoices, rent receipts, UPI splits), no account.

Nothing else is called, and nothing about the user's Hermes chats is sent.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

VERSION = "0.3.0"
CLIENT = f"hermes-sochen/{VERSION}"
DEFAULT_BASE_URL = "https://sochen.dev"
SETUP_URL = "https://sochen.dev/agents?utm_source=hermes&utm_medium=plugin"

# A job request waits at most this long for a quick answer before coming back "working".
MAX_WAIT_SECONDS = 120
# A status check waits at most this long for news.
MAX_CHECK_WAIT_SECONDS = 60


class SochenError(Exception):
    """A request Sochen refused or couldn't answer. ``data`` is the reply's JSON when there was one."""

    def __init__(self, message: str, status: int = 0, data: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.data = data or {}


class NoKey(SochenError):
    """The account tools were used before an API key was set."""

    def __init__(self) -> None:
        super().__init__("Sochen isn't connected yet: no SOCHEN_API_KEY.", 401)


def normalize_base_url(raw: Any) -> str:
    """The Sochen address to use: https, or http only for this computer (local development)."""
    text = str(raw or "").strip().rstrip("/")
    if not text:
        return DEFAULT_BASE_URL
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return DEFAULT_BASE_URL
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme == "https" or (parts.scheme == "http" and local):
        if parts.username or parts.password or not parts.hostname:
            return DEFAULT_BASE_URL
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
    return DEFAULT_BASE_URL


class Sochen:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: Optional[str] = None, timeout: float = 30.0):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None, *, auth: bool = True,
                 timeout: Optional[float] = None, accept: str = "application/json") -> tuple[int, dict]:
        headers = {"accept": accept, "user-agent": CLIENT, "x-sochen-client": CLIENT}
        if auth:
            if not self.api_key:
                raise NoKey()
            headers["authorization"] = f"Bearer {self.api_key}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return response.status, _json(response.read())
        except urllib.error.HTTPError as error:
            payload = _json(error.read())
            # A run or job that failed still says how it stands (status "failed", with its chat).
            if isinstance(payload.get("status"), str):
                return error.code, payload
            message = payload.get("error") if isinstance(payload.get("error"), str) else f"Sochen answered HTTP {error.code}."
            raise SochenError(message, error.code, payload) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise SochenError(f"Couldn't reach Sochen ({reason}). Try again in a moment.") from None

    def run(self, task: str, *, chat_id: Optional[str] = None, wait: int = 0) -> dict:
        """Hand Sochen a job (or a follow-up in an earlier job's chat)."""
        wait = max(0, min(MAX_WAIT_SECONDS, int(wait)))
        body: dict[str, Any] = {"message": task, "wait": wait}
        if chat_id:
            body["chat_id"] = chat_id
        _, data = self._request("POST", "/api/v1/run", body, timeout=wait + 45)
        return data

    def job(self, chat_id: str, cursor: Optional[int] = None, *, wait: int = 0, timeout: Optional[float] = None) -> dict:
        """How a job stands: working, needs_approval, answered or failed, with ``call`` while a phone call it
        placed goes on and ``question`` when that call's business is holding for the user's answer. ``wait``
        (seconds, up to 60) holds the check until there's a question or the job and its call are done."""
        params: dict[str, str] = {}
        if isinstance(cursor, int) and cursor >= 0:
            params["cursor"] = str(int(cursor))
        wait = max(0, min(MAX_CHECK_WAIT_SECONDS, int(wait)))
        if wait:
            params["wait"] = str(wait)
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        _, data = self._request("GET", f"/api/v1/jobs/{urllib.parse.quote(chat_id, safe='')}{query}", timeout=timeout or (wait + 20))
        return data

    def answer(self, chat_id: str, answer: str, question_id: Optional[str] = None, *, timeout: Optional[float] = 20) -> dict:
        """The user's answer to the question a job's call is holding for; Sochen tells the business at once."""
        body: dict[str, Any] = {"answer": answer}
        if question_id:
            body["question_id"] = question_id
        _, data = self._request("POST", f"/api/v1/jobs/{urllib.parse.quote(chat_id, safe='')}/answer", body, timeout=timeout)
        return data

    def desk(self, *, timeout: Optional[float] = None) -> dict:
        """What needs the user, what's running and what finished today."""
        _, data = self._request("GET", "/api/v1/desk", timeout=timeout)
        return data

    def credits(self, *, timeout: Optional[float] = None) -> dict:
        """What's left to spend on jobs, a new account's free start, and where to get more."""
        _, data = self._request("GET", "/api/v1/credits", timeout=timeout)
        return data

    def free_tool(self, server_tool: str, arguments: dict) -> dict:
        """Call one of Sochen's free tools on its public MCP server (no account, no key sent)."""
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": server_tool, "arguments": arguments}}
        _, data = self._request("POST", "/api/mcp", call, auth=False, timeout=90, accept="application/json, text/event-stream")
        if isinstance(data.get("error"), dict):
            raise SochenError(str(data["error"].get("message") or "Sochen couldn't run that tool."))
        result = data.get("result")
        if not isinstance(result, dict):
            raise SochenError("Sochen sent an answer this plugin doesn't understand.")
        return result


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
