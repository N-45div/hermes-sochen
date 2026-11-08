"""Backend for the Sochen page in Hermes Desktop, mounted at /api/plugins/sochen/.

One read-only route: GET /desk, the user's Sochen desk fetched with their key. The key is read
through Hermes's secret scope and never sent to the page; the page gets the desk, or whether a key
is missing. Hermes imports this file only while the plugin is enabled.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter

router = APIRouter()

_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _client_module():
    """The plugin's own client.py (this file is loaded on its own, outside the plugin package)."""
    spec = importlib.util.spec_from_file_location("hermes_sochen_client", _PLUGIN_DIR / "client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_client = _client_module()


def _key() -> Optional[str]:
    try:
        from agent.secret_scope import get_secret
    except Exception:
        return None
    try:
        value = (get_secret("SOCHEN_API_KEY") or "").strip()
    except Exception:
        return None
    return value or None


def _base_url() -> str:
    try:
        from hermes_cli.config import load_config_readonly

        settings = (((load_config_readonly() or {}).get("plugins") or {}).get("entries") or {}).get("sochen", {}).get("settings") or {}
    except Exception:
        settings = {}
    return _client.normalize_base_url(settings.get("base_url"))


@router.get("/desk")
def desk() -> dict[str, Any]:
    key = _key()
    if not key:
        return {"state": "setup", "setup_url": _client.SETUP_URL}
    try:
        data = _client.Sochen(_base_url(), key).desk(timeout=15)
    except _client.SochenError as error:
        if error.status == 401:
            return {"state": "setup", "setup_url": _client.SETUP_URL, "error": error.message}
        return {"state": "error", "error": error.message}
    except Exception as error:  # the page shows it; the gateway carries on
        return {"state": "error", "error": f"The Sochen plugin hit an error: {error}"}
    if data.get("held"):
        return {"state": "held", "message": data.get("message"), "upgrade_url": data.get("upgrade_url")}
    return {"state": "ready", "desk": data}
