"""The plugin end to end against a fake Sochen: what it registers, each tool, the approval hook,
finished-job reports, /sochen, and that the free tools never send the key."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from fakes import DESK, KEY, ROOT, FakeCtx, FakeSochen, load_plugin

plugin = load_plugin()
client = __import__("sochen_plugin.client", fromlist=["x"])


def manifest_list(field: str) -> list[str]:
    """A list field of plugin.yaml, read without a YAML library."""
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    block = re.search(rf"^{field}:\n((?:  - .+\n)+)", text, re.M)
    return [line.strip()[2:].strip() for line in block.group(1).splitlines()] if block else []


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def setup(server: FakeSochen, key: str | None = KEY, **config):
    ctx = FakeCtx({"base_url": server.url, **config})
    clock = Clock()
    instance = plugin.SochenPlugin(ctx, key_reader=lambda: key, clock=clock)
    # register() builds its own SochenPlugin; tests drive this one, wired up the same way.
    plugin_register(ctx, instance)
    return ctx, instance, clock


def plugin_register(ctx, instance):
    original = plugin.SochenPlugin
    plugin.SochenPlugin = lambda c: instance
    try:
        plugin.register(ctx)
    finally:
        plugin.SochenPlugin = original


def call(ctx, name, args=None):
    return json.loads(ctx.tools[name]["handler"](args or {}, task_id="t1"))


class Registration(unittest.TestCase):
    def test_registers_what_the_manifest_declares(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
        self.assertEqual(sorted(ctx.tools), sorted(manifest_list("provides_tools")))
        self.assertEqual(sorted(ctx.hooks), sorted(manifest_list("provides_hooks")))
        self.assertIn("sochen", ctx.commands)
        self.assertIn("sochen", ctx.skills)
        self.assertIn("morning-desk", ctx.blueprints)
        for name, tool in ctx.tools.items():
            self.assertEqual(tool["toolset"], "sochen")
            self.assertEqual(tool["schema"]["name"], name)
            self.assertEqual(tool["schema"]["parameters"]["type"], "object")
            self.assertTrue(tool["schema"]["description"])

    def test_versions_agree(self):
        manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn(f"version: {client.VERSION}\n", manifest)
        self.assertIn(f"version: {client.VERSION}\n", (ROOT / "skills" / "sochen" / "SKILL.md").read_text(encoding="utf-8"))

    def test_blueprint_prompt_uses_a_registered_tool(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
        self.assertIn("sochen_desk", ctx.blueprints["morning-desk"]["prompt_template"])


class WithoutAKey(unittest.TestCase):
    def test_account_tools_explain_the_setup(self):
        with FakeSochen() as server:
            ctx, instance, _ = setup(server, key=None)
            for name, args in (("sochen_handoff", {"task": "Call the bike shop"}), ("sochen_job", {"chat_id": "ses_1"}), ("sochen_desk", {})):
                reply = call(ctx, name, args)
                self.assertFalse(reply["ok"])
                self.assertTrue(reply["needs_setup"])
                self.assertIn("sochen.dev/hermes", reply["message"])
            self.assertEqual(server.requests, [])
            self.assertIsNone(instance.before_tool(tool_name="sochen_handoff", args={"task": "x"}))
            self.assertIsNone(instance.before_turn())
            self.assertIn("SOCHEN_API_KEY", ctx.commands["sochen"](""))

    def test_free_tools_work(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server, key=None)
            reply = call(ctx, "sochen_gst_invoice", {"seller": {"name": "A"}, "buyer": {"name": "B"}, "items": [], "invoice_number": "INV-7"})
        self.assertTrue(reply["ok"])
        self.assertIn("Invoice.pdf", reply["text"])
        self.assertEqual(server.requests[0]["body"]["params"]["name"], "make_gst_invoice")


class HandingOff(unittest.TestCase):
    def test_a_job_starts_and_is_remembered(self):
        with FakeSochen() as server:
            ctx, instance, _ = setup(server)
            reply = call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza at +1 415 555 0134 and ask if they're open till 11", "wait_seconds": 5})
            sent = server.requests[0]
        self.assertEqual(reply["status"], "working")
        self.assertEqual(reply["chat_id"], "ses_1")
        self.assertIn("report back", reply["note"])
        self.assertEqual(sent["body"], {"message": "Call Joe's Pizza at +1 415 555 0134 and ask if they're open till 11", "wait": 5})
        self.assertEqual({k.lower(): v for k, v in sent["headers"].items()}["x-sochen-client"], f"hermes-sochen/{client.VERSION}")
        [job] = instance.store.all()
        self.assertEqual(job["chat_id"], "ses_1")
        self.assertEqual(job["cursor"], 0)
        self.assertTrue(job["label"].startswith("Call Joe's Pizza"))

    def test_hermes_asks_before_a_job_that_uses_credits(self):
        with FakeSochen() as server:
            ctx, instance, _ = setup(server)
            directive = instance.before_tool(tool_name="sochen_handoff", args={"task": "Call the bike shop"})
            self.assertEqual(directive["action"], "approve")
            self.assertEqual(directive["rule_key"], "sochen_handoff")
            self.assertIn("Call the bike shop", directive["message"])
            self.assertIn("credits", directive["message"])
            # Other tools, and the free ones, are never held up.
            self.assertIsNone(instance.before_tool(tool_name="terminal", args={}))
            self.assertIsNone(instance.before_tool(tool_name="sochen_gst_invoice", args={}))
            ctx2, instance2, _ = setup(server, ask_before_handoff=False)
            self.assertIsNone(instance2.before_tool(tool_name="sochen_handoff", args={"task": "x"}))

    def test_a_declined_approval_sends_nothing(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            ctx.approve = False
            text = ctx.commands["sochen"]("call the bike shop and ask if my repair is ready")
        self.assertIn("declined", text)
        self.assertEqual([r for r in server.requests if r["path"] == "/api/v1/run"], [])

    def test_a_plan_refusal_comes_back_with_where_to_go(self):
        with FakeSochen() as server:
            server.run_reply = (402, {"error": "That's your free job done.", "reason": "free_job_done", "upgrade_url": "https://sochen.dev/pricing"})
            ctx, _, _ = setup(server)
            reply = call(ctx, "sochen_handoff", {"task": "Another job"})
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["upgrade_url"], "https://sochen.dev/pricing")
        self.assertIn("free job", reply["error"])

    def test_a_revoked_key_explains_the_setup(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server, key="sk_sochen_revoked")
            reply = call(ctx, "sochen_handoff", {"task": "x"})
        self.assertTrue(reply["needs_setup"])

    def test_a_follow_up_keeps_the_job_and_its_new_cursor(self):
        with FakeSochen() as server:
            ctx, instance, _ = setup(server)
            call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza"})
            call(ctx, "sochen_handoff", {"task": "Now ask about Saturday", "chat_id": "ses_1"})
        [job] = instance.store.all()
        self.assertTrue(job["label"].startswith("Call Joe's Pizza"))
        self.assertEqual(job["cursor"], 9)

    def test_no_task_is_refused_without_a_request(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            self.assertFalse(call(ctx, "sochen_handoff", {"task": "  "})["ok"])
        self.assertEqual(server.requests, [])


class FinishedJobs(unittest.TestCase):
    def test_hermes_hears_once_when_a_job_needs_the_user_and_once_when_it_is_done(self):
        with FakeSochen() as server:
            ctx, instance, clock = setup(server)
            call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza"})
            # Too soon to look again.
            self.assertIsNone(instance.before_turn())
            server.job_replies = [
                {"status": "needs_approval", "waiting_for": "Okay to go ahead? Calling +1 415 555 0134"},
                {"status": "needs_approval", "waiting_for": "Okay to go ahead? Calling +1 415 555 0134"},
                {"status": "answered", "answer": "They're open till 11 and deliver to 94110."},
            ]
            clock.now += 30
            first = instance.before_turn()
            self.assertIn("waiting for the user", first["context"])
            self.assertIn("Only the user can approve", first["context"])
            clock.now += 30
            self.assertIsNone(instance.before_turn())  # still waiting: not news again
            clock.now += 30
            done = instance.before_turn()
            self.assertIn("open till 11", done["context"])
            self.assertIn("https://sochen.dev/s/ses_1", done["context"])
            clock.now += 30
            self.assertIsNone(instance.before_turn())  # finished jobs aren't looked at again
            job_checks = [r for r in server.requests if r["path"] == "/api/v1/jobs/ses_1"]
        self.assertEqual(len(job_checks), 3)
        self.assertEqual(job_checks[0]["query"], {"cursor": ["0"]})

    def test_a_job_the_model_already_checked_is_not_reported_again(self):
        with FakeSochen() as server:
            ctx, instance, clock = setup(server)
            call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza"})
            server.job_replies = [{"status": "answered", "answer": "Open till 11."}]
            self.assertEqual(call(ctx, "sochen_job", {"chat_id": "ses_1"})["status"], "answered")
            clock.now += 30
            self.assertIsNone(instance.before_turn())

    def test_reports_can_be_turned_off(self):
        with FakeSochen() as server:
            ctx, instance, clock = setup(server, report_finished_jobs=False)
            call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza"})
            clock.now += 30
            self.assertIsNone(instance.before_turn())
            self.assertEqual([r for r in server.requests if r["path"].startswith("/api/v1/jobs/")], [])

    def test_sochen_being_down_never_breaks_a_turn(self):
        with FakeSochen() as server:
            ctx, instance, clock = setup(server)
            call(ctx, "sochen_handoff", {"task": "Call Joe's Pizza"})
        clock.now += 30
        self.assertIsNone(instance.before_turn())  # the server is gone now
        reply = call(ctx, "sochen_job", {"chat_id": "ses_1"})
        self.assertFalse(reply["ok"])
        self.assertIn("Couldn't reach Sochen", reply["error"])


class SlashCommand(unittest.TestCase):
    def test_the_desk(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            text = ctx.commands["sochen"]("")
        self.assertIn("Good evening, Asha", text)
        self.assertIn("Needs your OK (1)", text)
        self.assertIn("landlord@example.com", text)
        self.assertIn("Working now (1)", text)
        self.assertIn("Done today (1)", text)
        self.assertIn("63 of your 100 free API credits left", text)

    def test_credits(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            self.assertEqual(ctx.commands["sochen"]("credits"), "63 of your 100 free API credits left")
            server.credits = {"plan": "free", "credits_left": 0, "free_start": {"total": 100, "used": 100, "left": 0}, "upgrade_url": "https://sochen.dev/pricing"}
            self.assertEqual(ctx.commands["sochen"]("credits"), "0 of your 100 free API credits left. Get more: https://sochen.dev/pricing")
            server.credits = {"plan": "builder", "plan_name": "Builder", "credits_left": 12345, "free_start": None, "upgrade_url": None}
            self.assertEqual(ctx.commands["sochen"]("credits"), "12,345 API credits left (Builder)")
        with FakeSochen() as server:
            ctx, _, _ = setup(server, key=None)
            self.assertIn("100 free API credits", ctx.commands["sochen"]("credits"))

    def test_a_job_goes_through_the_tool_and_its_approval(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            text = ctx.commands["sochen"]("call the bike shop and ask if my repair is ready")
        self.assertEqual(ctx.dispatched[0][0], "sochen_handoff")
        self.assertIn("Sochen is on it", text)
        self.assertIn("https://sochen.dev/s/ses_1", text)

    def test_jobs_and_help(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            self.assertIn("No jobs", ctx.commands["sochen"]("jobs"))
            ctx.commands["sochen"]("call the bike shop")
            server.job_replies = [{"status": "answered", "answer": "Ready."}]
            self.assertIn("call the bike shop: done", ctx.commands["sochen"]("jobs"))
            self.assertIn("/sochen jobs", ctx.commands["sochen"]("help"))


class Addresses(unittest.TestCase):
    def test_only_https_or_this_computer(self):
        normalize = client.normalize_base_url
        self.assertEqual(normalize(None), "https://sochen.dev")
        self.assertEqual(normalize("https://sochen.dev/"), "https://sochen.dev")
        self.assertEqual(normalize("http://localhost:3210"), "http://localhost:3210")
        self.assertEqual(normalize("http://127.0.0.1:3210/"), "http://127.0.0.1:3210")
        for bad in ("http://sochen.dev", "ftp://sochen.dev", "https://user:pw@sochen.dev", "javascript:alert(1)", "sochen.dev", "https://"):
            self.assertEqual(normalize(bad), "https://sochen.dev", bad)


class TheKeyStaysPut(unittest.TestCase):
    def test_free_tools_never_send_the_key(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            call(ctx, "sochen_gst_invoice", {"invoice_number": "1"})
            reply = call(ctx, "sochen_upi_split", {})
        self.assertFalse(reply["ok"])
        for request in server.requests:
            self.assertNotIn("authorization", {k.lower() for k in request["headers"]})

    def test_the_key_is_read_through_hermes_not_files_or_the_environment(self):
        source = "\n".join(p.read_text(encoding="utf-8") for p in ROOT.glob("*.py"))
        self.assertIn("from agent.secret_scope import get_secret", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn(".env", source.replace(".env file", ""))

    def test_the_desk_tool_returns_the_desk(self):
        with FakeSochen() as server:
            ctx, _, _ = setup(server)
            reply = call(ctx, "sochen_desk")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["needs"], DESK["needs"])


if __name__ == "__main__":
    unittest.main()
