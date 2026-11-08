"""What the model reads to decide when to use each tool. The free tools' schemas come from Sochen's
own MCP server (data/free_tools.json), so they stay exactly what the server accepts."""

from __future__ import annotations

import json
from pathlib import Path

HANDOFF = {
    "name": "sochen_handoff",
    "description": (
        "Hand a job to Sochen (sochen.dev), the user's cloud agent with a phone, its own computer and the apps they "
        "connected there, when Hermes can't do it well itself. Use it to: phone a US business and bring back what "
        "they said (opening hours, a price, stock, a free table); research or browsing that takes a long time and "
        "should keep running in the cloud; or a job with the email and calendar the user connected in Sochen. "
        "Sochen keeps working after this returns: it comes back answered, or working (check it later with "
        "sochen_job; Hermes is also told when it finishes). Anything that pays, books, sends or deletes waits for "
        "the user's OK in the Sochen app, and you can't approve it. Write the job as complete instructions: who to "
        "call and their number, what to ask, what to bring back, and any deadline. Don't use it for what Hermes's "
        "own tools do well, like files on this computer, code, or a quick web search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The job, as complete instructions Sochen can act on without asking back.",
                "maxLength": 20000,
            },
            "chat_id": {
                "type": "string",
                "description": "To follow up on an earlier Sochen job, its chat_id. Leave out for a new job.",
            },
            "wait_seconds": {
                "type": "integer",
                "minimum": 0,
                "maximum": 120,
                "description": "How long to wait for a quick answer before it comes back as working (default 20).",
            },
        },
        "required": ["task"],
    },
}

JOB = {
    "name": "sochen_job",
    "description": (
        "Check a job handed to Sochen with sochen_handoff, without sending it anything: working (with its latest "
        "words), needs_approval (what it waits for; only the user can approve, in the Sochen app), answered (with "
        "the answer) or failed. Use it when the user asks how a Sochen job is going."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {"type": "string", "description": "The job's chat_id, from sochen_handoff."},
        },
        "required": ["chat_id"],
    },
}

DESK = {
    "name": "sochen_desk",
    "description": (
        "The user's Sochen desk: what waits for their OK (with links), heads-ups, what's running and what Sochen "
        "finished today. Titles and states only. Use it when the user asks what Sochen is doing or what needs them."
    ),
    "parameters": {"type": "object", "properties": {}},
}


def free_tools() -> list[dict]:
    """The free tools: name, server_tool, description and parameters."""
    path = Path(__file__).parent / "data" / "free_tools.json"
    return json.loads(path.read_text(encoding="utf-8"))["tools"]
