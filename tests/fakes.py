"""A fake Hermes plugin context and a fake Sochen server, so the plugin is tested without either."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk_sochen_test_key"


def load_plugin():
    """Import the plugin directory as a package, the way Hermes does (relative imports included)."""
    name = "sochen_plugin"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeState:
    def __init__(self):
        self.data: dict = {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self.data.get(key, default)))

    def set(self, key, value):
        self.data[key] = json.loads(json.dumps(value))


class FakeCtx:
    """Records what register() asks for, like Hermes's PluginContext, and runs dispatched tools."""

    def __init__(self, config=None):
        self.state = FakeState()
        self.config = dict(config or {})
        self.tools: dict = {}
        self.hooks: dict = {}
        self.commands: dict = {}
        self.skills: dict = {}
        self.blueprints: dict = {}
        self.dispatched: list = []
        # What Hermes's approval gate answers when a pre_tool_call hook asks it.
        self.approve = True

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        assert name not in self.tools, name
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **kwargs}

    def register_hook(self, name, callback, **kwargs):
        self.hooks.setdefault(name, []).append(callback)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_skill(self, name, path):
        assert Path(path).is_file()
        self.skills[name] = Path(path)

    def register_automation_blueprint(self, key, **fields):
        self.blueprints[key] = fields

    def dispatch_tool(self, name, args, **kwargs):
        """Like Hermes: pre_tool_call hooks first (an approve goes to the approval gate), then the tool."""
        self.dispatched.append((name, args))
        for hook in self.hooks.get("pre_tool_call", []):
            directive = hook(tool_name=name, args=args, task_id="t1")
            if isinstance(directive, dict) and directive.get("action") == "approve" and not self.approve:
                return f"BLOCKED: the user declined {name}"
        return self.tools[name]["handler"](args, task_id="t1")


class FakeSochen:
    """Answers the Agent API and the MCP server the way sochen.dev does, from a script of replies."""

    def __init__(self):
        self.requests: list[dict] = []
        self.job_replies: list[dict] = []
        self.run_reply: tuple[int, dict] | None = None
        self.answer_reply: tuple[int, dict] | None = None
        self.credits = {"plan": "free", "plan_name": "Free credits", "credits_left": 63, "free_start": {"total": 100, "used": 37, "left": 63}, "upgrade_url": None}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _record(self, body=None):
                parts = urlsplit(self.path)
                entry = {"method": self.command, "path": parts.path, "query": parse_qs(parts.query), "headers": dict(self.headers), "body": body}
                fake.requests.append(entry)
                return entry

            def _authorized(self):
                return self.headers.get("authorization") == f"Bearer {KEY}"

            def do_GET(self):
                entry = self._record()
                if not self._authorized():
                    return self._send(401, {"error": "Send your Sochen API key."})
                if entry["path"] == "/api/v1/desk":
                    return self._send(200, DESK)
                if entry["path"] == "/api/v1/credits":
                    return self._send(200, fake.credits)
                if entry["path"].startswith("/api/v1/jobs/"):
                    chat_id = entry["path"].rsplit("/", 1)[1]
                    if chat_id != "ses_1":
                        return self._send(404, {"error": "That chat isn't this account's."})
                    reply = fake.job_replies.pop(0) if fake.job_replies else {"status": "working", "progress": None}
                    return self._send(200, {**reply, "chat_id": "ses_1", "chat_url": "https://sochen.dev/s/ses_1"})
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                entry = self._record(body)
                if entry["path"] == "/api/mcp":
                    params = body.get("params") or {}
                    if params.get("name") == "make_gst_invoice":
                        return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": {
                            "content": [{"type": "text", "text": "Invoice INV-7: total ₹11,800.\nPDF (link works for 24 hours): https://sochen.dev/api/mcp/files/abc/Invoice.pdf"}],
                            "structuredContent": {"pdf": {"url": "https://sochen.dev/api/mcp/files/abc/Invoice.pdf"}},
                        }})
                    return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "Missing the people to split between."}], "isError": True}})
                if entry["path"] == "/api/v1/jobs/ses_1/answer":
                    if not self._authorized():
                        return self._send(401, {"error": "Send your Sochen API key."})
                    if fake.answer_reply:
                        return self._send(*fake.answer_reply)
                    return self._send(200, {"status": "sent", "question": "What name for the booking?", "chat_id": "ses_1"})
                if entry["path"] == "/api/v1/run":
                    if not self._authorized():
                        return self._send(401, {"error": "Send your Sochen API key."})
                    if fake.run_reply:
                        return self._send(*fake.run_reply)
                    if body.get("chat_id"):
                        return self._send(202, {"status": "working", "chat_id": body["chat_id"], "chat_url": "https://sochen.dev/s/ses_1", "cursor": 9})
                    return self._send(202, {"status": "working", "note": "Started.", "chat_id": "ses_1", "chat_url": "https://sochen.dev/s/ses_1", "cursor": 0})
                return self._send(404, {"error": "not found"})

        return Handler


DESK = {
    "held": False,
    "date": "Saturday, November 7",
    "greeting": "Good evening, Asha",
    "first_run": False,
    "needs": [{"chat_id": "ses_9", "title": "Reply to the landlord", "who": "Eli · Sochen", "ago": "5 min ago",
               "waiting_for": "Okay to go ahead? Sending an email to landlord@example.com", "chat_url": "https://sochen.dev/s/ses_9"}],
    "heads_ups": [],
    "working": [{"id": "ses_1", "title": "Call Joe's Pizza", "line": "Eli · on a call", "chat_url": "https://sochen.dev/s/ses_1"}],
    "done": [{"chat_id": "ses_3", "title": "Flights to Goa", "line": "Eli · 7:42 PM", "stopped": False, "chat_url": "https://sochen.dev/s/ses_3"}],
    "credits": {"plan": "free", "plan_name": "Free credits", "credits_left": 63, "free_start": {"total": 100, "used": 37, "left": 63}, "upgrade_url": None},
}
