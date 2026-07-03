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


def test_build_search_indexes_only_docs_packs():
    from generate_routes import build_search_indexes
    extras = {"building-a-software-pack": "https://template.pages.dev"}
    routes = {
        "__default__": "https://dash.pages.dev",
        "superset-pack": "https://superset-pack.pages.dev",
        "building-a-software-pack": "https://template.pages.dev",
    }
    idx = build_search_indexes(routes, extras)
    assert idx == ["/superset-pack/pagefind/"]  # docs pack only; not __default__, not extras


def test_fetch_metadata_uses_contents_api_with_token(monkeypatch):
    """Must use the contents API with auth so private pack repos resolve.

    The old raw.githubusercontent.com URL returned 404 for private repos,
    silently dropping their docs routes.
    """
    import io
    import urllib.request

    import generate_routes

    captured = {}

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["accept"] = req.get_header("Accept")
        captured["auth"] = req.get_header("Authorization")
        return FakeResponse(b"docs_site: true\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    meta = generate_routes.fetch_metadata("nebari-dev/foo", token="tok123")

    assert meta == {"docs_site": True}
    assert captured["url"] == "https://api.github.com/repos/nebari-dev/foo/contents/pack-metadata.yaml"
    assert captured["accept"] == "application/vnd.github.raw+json"
    assert captured["auth"] == "Bearer tok123"


def test_fetch_metadata_no_token_sends_no_auth_header(monkeypatch):
    import io
    import urllib.request

    import generate_routes

    captured = {}

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")
        return FakeResponse(b"{}\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_routes.fetch_metadata("nebari-dev/foo", token=None)
    assert captured["auth"] is None
