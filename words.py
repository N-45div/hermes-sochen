"""What the plugin says: the desk and jobs as plain text for /sochen, and the lines Hermes is
given when a job it handed to Sochen moves on. Pure functions, tested on their own."""

from __future__ import annotations

from typing import Any, Iterable

from .client import SETUP_URL

SETUP = (
    "Sochen isn't connected yet. Make a key at " + SETUP_URL + " (every account gets 100 free API credits), then "
    "run `hermes config set SOCHEN_API_KEY <your key>`, or add it in Hermes Desktop under Settings → Plugins → Sochen. "
    "GST invoices, rent receipts and UPI bill splits work without a key."
)


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _section(title: str, rows: Iterable[str]) -> list[str]:
    rows = list(rows)
    return [f"{title} ({len(rows)})", *rows] if rows else []


def credits_text(credits: dict) -> str:
    """What's left to spend, in a line: "63 of your 100 free API credits left", "1,234 API credits left (Builder)"."""
    if not isinstance(credits, dict) or credits.get("credits_left") is None:
        return ""
    left = int(credits["credits_left"])
    start = credits.get("free_start")
    plan = credits.get("plan_name")
    named = f" ({plan})" if isinstance(plan, str) and plan and not isinstance(start, dict) else ""
    line = f"{left} of your {start['total']} free API credits left" if isinstance(start, dict) else f"{left:,} API credits left{named}"
    if left <= 0 and credits.get("upgrade_url"):
        line += f". Get more: {credits['upgrade_url']}"
    return line


def desk_text(desk: dict) -> str:
    """The desk as a few short lines, the way /sochen shows it."""
    if desk.get("held"):
        url = desk.get("upgrade_url")
        return _clip(desk.get("message") or "Sochen needs a plan to keep going.", 400) + (f"\n{url}" if url else "")
    head = " · ".join(part for part in (desk.get("greeting"), desk.get("date")) if part)
    needs = [f"• {_clip(n.get('title'), 70)}: {_clip(n.get('waiting_for'), 110)}\n  {n.get('chat_url', '')}" for n in desk.get("needs") or []]
    heads_ups = [f"• {_clip(h.get('title'), 70)}: {_clip(h.get('detail'), 110)}" for h in desk.get("heads_ups") or []]
    working = [f"• {_clip(w.get('title'), 70)} ({_clip(w.get('line'), 60)})" for w in desk.get("working") or []]
    done = [f"• {_clip(d.get('title'), 70)} ({_clip(d.get('line'), 60)})" for d in desk.get("done") or []]
    lines = [head] if head else []
    money = credits_text(desk.get("credits") or {})
    if money:
        lines.append(money[0].upper() + money[1:])
    body = _section("Needs your OK", needs) + _section("Heads-ups", heads_ups) + _section("Working now", working) + _section("Done today", done)
    if not body:
        body = ["Nothing on your Sochen desk today. Hand it a job: /sochen <what you need>"]
    return "\n".join(lines + body)


def job_line(job: dict, reply: dict) -> str:
    """One job's news for Hermes: what it was, how it stands, and Sochen's words."""
    name = _clip(job.get("label"), 90)
    url = reply.get("chat_url") or job.get("chat_url") or ""
    status = reply.get("status")
    question = reply.get("question") if isinstance(reply.get("question"), dict) else None
    if question:
        business = _clip(question.get("business") or "The business", 80)
        left = question.get("seconds_left")
        hold = f"about {left} seconds" if isinstance(left, int) else "about a minute"
        return (
            f'- On the call for "{name}", {business} asked something only the user can answer, and is holding for {hold}. '
            f'Their words: "{_clip(question.get("text"), 500)}". Ask the user now; send their exact reply with '
            f'sochen_answer (chat_id {job.get("chat_id")}), then keep following the job with sochen_job.'
        )
    if isinstance(reply.get("call"), dict):
        return f'- "{name}": the phone call is still going on ({url})'
    if status == "answered":
        return f'- "{name}" is done. Sochen said: {_clip(reply.get("answer"), 1500)} ({url})'
    if status == "failed":
        return f'- "{name}" stopped: {_clip(reply.get("error"), 300)} ({url})'
    if status == "needs_approval":
        waiting = _clip(reply.get("waiting_for") or "your OK", 200)
        return f'- "{name}" is waiting for the user in the Sochen app: {waiting}. Only the user can approve it ({url})'
    return f'- "{name}" is still working ({url})'


def job_status_text(job: dict, reply: dict) -> str:
    """One job for /sochen jobs."""
    status = reply.get("status") or job.get("status") or "working"
    if isinstance(reply.get("question"), dict):
        status = "question"
    elif isinstance(reply.get("call"), dict):
        status = "on_call"
    word = {"working": "working", "needs_approval": "needs your OK", "answered": "done", "failed": "stopped", "on_call": "on the phone",
            "question": "the business is asking you something"}.get(status, status)
    return f"• {_clip(job.get('label'), 70)}: {word}\n  {reply.get('chat_url') or job.get('chat_url') or ''}"
