"""The jobs Hermes handed to Sochen, kept in the plugin's own state (``ctx.state``, per profile).

Each job remembers where its turn began (the cursor), a short label, and what Hermes was last
told about it, so a finished job is reported once, and a job waiting for the user's OK once per
wait. Nothing here is a secret, and nothing leaves this computer.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

KEY = "jobs"
# Old jobs are forgotten: a week after they started, or past this many.
KEEP_SECONDS = 7 * 86_400
MAX_JOBS = 40
# A job is looked at again no sooner than this.
CHECK_EVERY_SECONDS = 20
OPEN = ("working", "needs_approval")


def label(task: str, limit: int = 90) -> str:
    """A job's short name: its first line, cut to ``limit`` characters."""
    first = (task or "").strip().splitlines()[0] if (task or "").strip() else "A job"
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


class JobStore:
    def __init__(self, state: Any, clock: Callable[[], float] = time.time):
        self._state = state
        self._clock = clock

    def _load(self) -> dict[str, dict]:
        try:
            raw = self._state.get(KEY, default={})
        except Exception:
            return {}
        return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}

    def _save(self, jobs: dict[str, dict]) -> None:
        now = self._clock()
        kept = {k: v for k, v in jobs.items() if now - float(v.get("started", now)) < KEEP_SECONDS}
        newest = sorted(kept.items(), key=lambda item: float(item[1].get("started", 0)), reverse=True)[:MAX_JOBS]
        try:
            self._state.set(KEY, dict(newest))
        except Exception:
            pass

    def all(self) -> list[dict]:
        """Every remembered job, newest first."""
        jobs = self._load()
        return [{"chat_id": k, **v} for k, v in sorted(jobs.items(), key=lambda item: float(item[1].get("started", 0)), reverse=True)]

    def get(self, chat_id: str) -> Optional[dict]:
        job = self._load().get(chat_id)
        return {"chat_id": chat_id, **job} if job else None

    def remember(self, reply: dict, task: str) -> None:
        """Note a job Sochen took on (from a run's reply), or a follow-up in one it already has."""
        chat_id = reply.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id:
            return
        jobs = self._load()
        now = self._clock()
        status = reply.get("status") if isinstance(reply.get("status"), str) else "working"
        previous = jobs.get(chat_id, {})
        jobs[chat_id] = {
            "label": label(task) if not previous else previous.get("label", label(task)),
            "cursor": reply.get("cursor") if isinstance(reply.get("cursor"), int) else previous.get("cursor"),
            "chat_url": reply.get("chat_url") or previous.get("chat_url"),
            "status": status,
            "started": previous.get("started", now) if previous else now,
            "checked": now,
            # What Hermes already knows: the reply to the run itself told it this status.
            "told": status,
        }
        self._save(jobs)

    def due(self, limit: int = 2) -> list[dict]:
        """Open jobs not looked at for a while, longest-unchecked first."""
        now = self._clock()
        open_jobs = [job for job in self.all() if job.get("status") in OPEN and now - float(job.get("checked", 0)) >= CHECK_EVERY_SECONDS]
        open_jobs.sort(key=lambda job: float(job.get("checked", 0)))
        return open_jobs[:limit]

    def update(self, chat_id: str, reply: dict) -> Optional[dict]:
        """Record a job's latest status. Returns the job when Hermes hasn't been told this status yet
        and it's worth telling (finished, failed, or newly waiting for the user's OK)."""
        jobs = self._load()
        job = jobs.get(chat_id)
        if job is None:
            return None
        status = reply.get("status")
        job["checked"] = self._clock()
        if status in ("working", "needs_approval", "answered", "failed"):
            job["status"] = status
        # Approved and back at work: a later wait for the user's OK is news again.
        if status == "working" and job.get("told") == "needs_approval":
            job["told"] = "working"
        news = status in ("answered", "failed", "needs_approval") and job.get("told") != status
        if news:
            job["told"] = status
        jobs[chat_id] = job
        self._save(jobs)
        return {"chat_id": chat_id, **job} if news else None
