"""The Desktop page's backend (dashboard/plugin_api.py) with stand-ins for FastAPI and Hermes's
secret scope: setup without a key, the desk with one, and Sochen's refusals passed on."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest

from fakes import DESK, KEY, ROOT, FakeSochen


class _Router:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorate(fn):
            self.routes[path] = fn
            return fn

        return decorate


def load_api(key, base_url):
    """Import plugin_api.py the way Hermes does (a file on its own), with stand-in modules."""
    fastapi = types.ModuleType("fastapi")
    fastapi.APIRouter = _Router
    secret_scope = types.ModuleType("agent.secret_scope")
    secret_scope.get_secret = lambda name: key if name == "SOCHEN_API_KEY" else None
    agent = types.ModuleType("agent")
    agent.secret_scope = secret_scope
    config = types.ModuleType("hermes_cli.config")
    config.load_config_readonly = lambda: {"plugins": {"entries": {"sochen": {"settings": {"base_url": base_url}}}}}
    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.config = config
    stand_ins = {"fastapi": fastapi, "agent": agent, "agent.secret_scope": secret_scope, "hermes_cli": hermes_cli, "hermes_cli.config": config}
    saved = {name: sys.modules.get(name) for name in stand_ins}
    sys.modules.update(stand_ins)
    try:
        spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_sochen", ROOT / "dashboard" / "plugin_api.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        raise
    finally:
        # Keep the stand-ins only while the route runs: the tests call it right away.
        pass
    return module, lambda: [sys.modules.__setitem__(n, m) if m else sys.modules.pop(n, None) for n, m in saved.items()]


class DeskRoute(unittest.TestCase):
    def test_without_a_key_it_asks_to_connect(self):
        api, restore = load_api(None, "https://sochen.dev")
        try:
            reply = api.router.routes["/desk"]()
        finally:
            restore()
        self.assertEqual(reply["state"], "setup")
        self.assertIn("sochen.dev/agents", reply["setup_url"])

    def test_with_a_key_it_returns_the_desk_and_keeps_the_key(self):
        with FakeSochen() as server:
            api, restore = load_api(KEY, server.url)
            try:
                reply = api.router.routes["/desk"]()
            finally:
                restore()
        self.assertEqual(reply["state"], "ready")
        self.assertEqual(reply["desk"]["needs"], DESK["needs"])
        self.assertNotIn(KEY, repr(reply))

    def test_a_revoked_key_asks_to_connect_again(self):
        with FakeSochen() as server:
            api, restore = load_api("sk_sochen_revoked", server.url)
            try:
                reply = api.router.routes["/desk"]()
            finally:
                restore()
        self.assertEqual(reply["state"], "setup")

    def test_sochen_down_is_an_error_not_a_crash(self):
        with FakeSochen() as server:
            url = server.url
        api, restore = load_api(KEY, url)
        try:
            reply = api.router.routes["/desk"]()
        finally:
            restore()
        self.assertEqual(reply["state"], "error")
        self.assertIn("Couldn't reach Sochen", reply["error"])


if __name__ == "__main__":
    unittest.main()
