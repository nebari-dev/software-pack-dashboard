"""Unit tests for generate_routes.py. No network access."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_routes import build_routes  # noqa: E402


def fake_fetch(repo):
    return {
        "nebari-dev/llm-serving-pack": {"docs_site": True},
        "nebari-dev/chat-pack": {"docs_site": False},
        "nebari-dev/nebi-pack": {},  # absent == false
    }[repo]


def test_build_routes_includes_only_docs_site_true():
    packs = ["nebari-dev/llm-serving-pack", "nebari-dev/chat-pack", "nebari-dev/nebi-pack"]
    extras = {"building-a-software-pack": "https://nebari-software-pack-template.pages.dev"}
    routes = build_routes(packs, fake_fetch, extras,
                          default_host="https://software-pack-dashboard.pages.dev")
    assert routes["__default__"] == "https://software-pack-dashboard.pages.dev"
    assert routes["llm-serving-pack"] == "https://llm-serving-pack.pages.dev"
    assert routes["building-a-software-pack"] == "https://nebari-software-pack-template.pages.dev"
    assert "chat-pack" not in routes
    assert "nebi-pack" not in routes
