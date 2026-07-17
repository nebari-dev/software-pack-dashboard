"""Unit tests for generate.py. No network access."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

import generate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture,expected_name,must_error_contain",
    [
        ("valid-metadata.yaml", "nebari-data-science-pack", None),
        ("invalid-missing-field.yaml", "nebari-data-science-pack", "owner"),
        ("invalid-bad-level.yaml", "nebari-data-science-pack", "level must be one of"),
        ("deprecated-without-sunset.yaml", "nebari-data-science-pack", "sunset_date"),
    ],
)
def test_validate_metadata_fixtures(fixture, expected_name, must_error_contain):
    data = _load(fixture)
    errors = generate.validate_metadata(data, expected_name)
    if must_error_contain is None:
        assert errors == [], f"expected no errors, got {errors}"
    else:
        assert any(must_error_contain in e for e in errors), (
            f"expected an error containing '{must_error_contain}', got {errors}"
        )


def test_validate_metadata_name_mismatch():
    data = _load("valid-metadata.yaml")
    errors = generate.validate_metadata(data, "wrong-name")
    assert any("does not match repo name" in e for e in errors)


def test_validate_metadata_ga_requires_product_owner():
    data = _load("valid-metadata.yaml")
    data["level"] = "ga"
    data["product_owner"] = None
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert any("product_owner" in e for e in errors)


def test_validate_metadata_ga_with_product_owner_ok():
    data = _load("valid-metadata.yaml")
    data["level"] = "ga"
    data["product_owner"] = "alice"
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert errors == []


def test_validate_metadata_description_too_long():
    data = _load("valid-metadata.yaml")
    data["description"] = "x" * 201
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert any("description exceeds" in e for e in errors)


def test_validate_metadata_description_optional():
    data = _load("valid-metadata.yaml")
    del data["description"]
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert errors == [], f"description is optional, got {errors}"


def test_validate_metadata_bad_url():
    data = _load("valid-metadata.yaml")
    data["links"] = {"docs": "not-a-url"}
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert any("links.docs" in e for e in errors)


def test_validate_metadata_bad_nebariapp_value():
    data = _load("valid-metadata.yaml")
    data["nebariapp_integration"] = "kinda"
    errors = generate.validate_metadata(data, "nebari-data-science-pack")
    assert any("nebariapp_integration" in e for e in errors)


# ---------------------------------------------------------------------------
# Flag computation
# ---------------------------------------------------------------------------


TODAY = date(2026, 5, 14)


@pytest.mark.parametrize(
    "metadata,github_data,errors,expected",
    [
        # Stale: last commit > 90 days ago, not deprecated
        (
            {"level": "alpha", "deprecated": False, "last_presales_demo": "2026-05-01"},
            {"last_commit_date": date(2025, 1, 1)},
            [],
            {"stale"},
        ),
        # Not stale: deprecated overrides
        (
            {"level": "alpha", "deprecated": True, "sunset_date": "2026-12-01"},
            {"last_commit_date": date(2025, 1, 1)},
            [],
            {"deprecated"},
        ),
        # Alpha with no demo metadata: clean (demo-lapsed flag was removed)
        (
            {"level": "alpha", "deprecated": False},
            {"last_commit_date": date(2026, 5, 1)},
            [],
            set(),
        ),
        # Experimental: clean
        (
            {"level": "experimental", "deprecated": False},
            {"last_commit_date": date(2026, 5, 1)},
            [],
            set(),
        ),
        # no-product-owner: ga without product_owner
        (
            {
                "level": "ga",
                "deprecated": False,
                "last_presales_demo": "2026-05-01",
                "product_owner": None,
            },
            {"last_commit_date": date(2026, 5, 1)},
            [],
            {"no-product-owner"},
        ),
        # GA with product_owner and recent demo: clean
        (
            {
                "level": "ga",
                "deprecated": False,
                "last_presales_demo": "2026-05-01",
                "product_owner": "alice",
            },
            {"last_commit_date": date(2026, 5, 1)},
            [],
            set(),
        ),
        # metadata-missing flag from errors
        (
            None,
            {"last_commit_date": date(2026, 5, 1)},
            ["metadata-missing"],
            {"metadata-missing"},
        ),
        # metadata-invalid flag from errors
        (
            {"level": "alpha", "deprecated": False, "last_presales_demo": "2026-05-01"},
            {"last_commit_date": date(2026, 5, 1)},
            ["some error"],
            {"metadata-invalid"},
        ),
        # repo-not-found
        (
            None,
            {"repo_not_found": True},
            ["metadata-missing"],
            {"repo-not-found", "metadata-missing"},
        ),
    ],
)
def test_compute_flags(metadata, github_data, errors, expected):
    flags = generate.compute_flags(metadata, github_data, TODAY, errors)
    assert set(flags) == expected


# ---------------------------------------------------------------------------
# Date formatting & rendering
# ---------------------------------------------------------------------------


def test_fmt_date():
    assert generate._fmt_date(date(2026, 4, 28)) == "Apr 28"
    assert generate._fmt_date(None) == "–"


def test_render_row_full():
    row = generate.PackRow(
        repo="nebari-dev/nebari-data-science-pack",
        metadata={
            "display_name": "Data Science Pack",
            "level": "alpha",
            "owner": "chuckmcandrew",
            "deprecated": False,
            "nebariapp_integration": "partial",
            "scope": {"standalone-supported": "yes"},
            "last_presales_demo": "2026-05-01",
            "last_presales_demo_by": "jdoe",
            "demo_notes": "Use the small-instance profile for demos.",
        },
        github_data={
            "release_tag": "v0.5.2",
            "release_date": date(2026, 4, 12),
            "last_commit_date": date(2026, 4, 28),
            "description": "A Helm chart that deploys JupyterHub and jhub-apps.",
        },
        flags=[],
    )
    expected = (
        "| [Data Science Pack](https://github.com/nebari-dev/nebari-data-science-pack) "
        "| A Helm chart that deploys JupyterHub and jhub-apps. "
        "| Alpha "
        "| [@chuckmcandrew](https://github.com/chuckmcandrew) "
        "| Partial | Yes "
        "| v0.5.2 (Apr 12) | Apr 28 "
        "| – "
        "| Use the small-instance profile for demos. |"
    )
    assert generate.render_row(row) == expected


def test_render_row_metadata_missing():
    row = generate.PackRow(
        repo="nebari-dev/foo-pack",
        metadata=None,
        metadata_errors=["metadata-missing"],
        github_data={"last_commit_date": date(2026, 5, 10)},
        flags=["metadata-missing"],
    )
    out = generate.render_row(row)
    assert "[foo-pack](https://github.com/nebari-dev/foo-pack)" in out
    assert "May 10" in out
    assert "metadata-missing" in out


def test_render_row_ga_is_bolded():
    row = generate.PackRow(
        repo="nebari-dev/x",
        metadata={
            "display_name": "X",
            "level": "ga",
            "owner": "a",
            "deprecated": False,
            "product_owner": "b",
        },
        github_data={},
        flags=[],
    )
    out = generate.render_row(row)
    assert "**GA**" in out


def test_render_dashboard_smoke():
    from datetime import datetime, timezone

    rows = [
        generate.PackRow(
            repo="nebari-dev/a",
            metadata={
                "display_name": "A",
                "level": "ga",
                "owner": "u",
                "deprecated": False,
                "product_owner": "po",
            },
            github_data={},
            flags=[],
        ),
        generate.PackRow(
            repo="nebari-dev/b",
            metadata={
                "display_name": "B",
                "level": "beta",
                "owner": "u",
                "deprecated": True,
                "sunset_date": "2026-12-01",
            },
            github_data={},
            flags=["deprecated"],
        ),
    ]
    out = generate.render_dashboard(rows, datetime(2026, 5, 14, 3, 0, 0, tzinfo=timezone.utc))
    assert "# Nebari Software Packs" in out
    assert "1 GA" in out
    assert "1 Deprecated" in out
    assert "## Deprecated packs" in out
    assert "## How this dashboard works" in out
    # Deprecated pack not in main table
    main_table_section = out.split("## Deprecated packs")[0]
    assert "| [B]" not in main_table_section


# ---------------------------------------------------------------------------
# Landing page renderer (render_landing_markdown) - legacy renderer tests
# updated from render_html after migration to themed Hugo markdown
# ---------------------------------------------------------------------------


def test_render_landing_has_intro_links_and_catalog():
    rows = [
        generate.PackRow(
            repo="nebari-dev/llm-serving-pack",
            metadata={
                "display_name": "LLM Serving Pack",
                "level": "alpha",
                "owner": "chuckmcandrew",
                "deprecated": False,
                "docs_site": True,
                "links": {"docs": "https://packs.nebari.dev/llm-serving-pack/"},
            },
            github_data={},
            flags=[],
        ),
    ]
    out = generate.render_landing_markdown(rows, generated_at="2026-06-24")
    # Starlight splash front matter + a card catalog (not a markdown table)
    assert out.startswith("---\n")
    assert "template: splash" in out
    assert '<div class="pack-grid">' in out
    assert 'class="pack-card"' in out
    # Required links + intro copy
    assert "nebari.dev" in out
    assert "/building-a-software-pack/" in out
    assert "software pack" in out.lower()
    # Card content: name, owner, maturity level, docs href
    assert '<span class="pack-card__name">LLM Serving Pack</span>' in out
    assert "@chuckmcandrew" in out
    assert 'data-level="alpha"' in out
    assert 'href="https://packs.nebari.dev/llm-serving-pack/"' in out
    assert "2026-06-24" in out


def test_render_landing_escapes_name_and_falls_back_to_repo():
    rows = [
        generate.PackRow(
            repo="nebari-dev/x-pack",
            metadata={
                "display_name": "A & B Pack",
                "level": "ga",
                "owner": "alice",
                "deprecated": False,
                "product_owner": "bob",
            },
            github_data={},
            flags=[],
        ),
    ]
    out = generate.render_landing_markdown(rows, generated_at="2026-06-24")
    # Display name is HTML-escaped: & becomes &amp;
    assert "A &amp; B Pack" in out
    assert "A & B Pack" not in out
    # No links.docs, so the card links to the repo
    assert 'href="https://github.com/nebari-dev/x-pack"' in out


def test_render_landing_rejects_unsafe_docs_scheme():
    rows = [
        generate.PackRow(
            repo="nebari-dev/evil-pack",
            metadata={
                "display_name": "Evil",
                "level": "alpha",
                "owner": "a",
                "deprecated": False,
                "links": {"docs": "javascript:alert(1)"},
            },
            github_data={},
            flags=[],
        ),
    ]
    out = generate.render_landing_markdown(rows, generated_at="2026-06-24")
    assert "javascript:" not in out
    assert 'href="https://github.com/nebari-dev/evil-pack"' in out


def test_load_tracked_packs(tmp_path):
    p = tmp_path / "tp.yaml"
    p.write_text("packs:\n  - repo: a/b\n  - repo: c/d\n")
    out = generate.load_tracked_packs(str(p))
    assert out == [{"repo": "a/b"}, {"repo": "c/d"}]


def test_load_tracked_packs_bad_format(tmp_path):
    p = tmp_path / "tp.yaml"
    p.write_text("packs:\n  - name: a\n")  # missing repo
    with pytest.raises(ValueError):
        generate.load_tracked_packs(str(p))


def test_load_tracked_packs_missing_top_level(tmp_path):
    p = tmp_path / "tp.yaml"
    p.write_text("foo: bar\n")
    with pytest.raises(ValueError):
        generate.load_tracked_packs(str(p))


# ---------------------------------------------------------------------------
# Starlight landing page renderer (render_landing_markdown)
# ---------------------------------------------------------------------------


from generate import render_landing_markdown, PackRow


def _row(repo, display, level, owner, docs=None):
    r = PackRow(repo=repo)
    md = {"display_name": display, "level": level, "owner": owner}
    if docs is not None:
        md["links"] = {"docs": docs}
    r.metadata = md
    return r


def test_landing_frontmatter_intro_and_catalog():
    out = render_landing_markdown([], "2026-06-25T00:00:00Z")
    assert out.startswith("---\n")
    assert "title: Nebari Software Packs" in out
    assert "template: splash" in out
    assert "https://nebari.dev" in out
    assert "/building-a-software-pack/" in out
    assert '<div class="pack-grid">' in out


def test_landing_card_links_docs_when_present():
    rows = [_row("nebari-dev/llm-serving-pack", "LLM Serving Pack", "alpha", "dcmcand",
                 docs="https://packs.nebari.dev/llm-serving-pack/")]
    out = render_landing_markdown(rows, "t")
    assert 'href="https://packs.nebari.dev/llm-serving-pack/"' in out
    assert '<span class="pack-card__name">LLM Serving Pack</span>' in out
    assert 'data-level="alpha"' in out
    assert "@dcmcand" in out


def test_landing_card_falls_back_to_repo_link():
    rows = [_row("nebari-dev/chat-pack", "Chat Pack", "beta", "owner")]
    out = render_landing_markdown(rows, "t")
    assert 'href="https://github.com/nebari-dev/chat-pack"' in out
    assert 'data-level="beta"' in out


def test_landing_rejects_unsafe_docs_scheme_card():
    rows = [_row("nebari-dev/x", "X", "ga", "o", docs="javascript:alert(1)")]
    out = render_landing_markdown(rows, "t")
    assert "javascript:" not in out
    assert 'href="https://github.com/nebari-dev/x"' in out


def test_landing_unknown_level_maps_to_none():
    rows = [_row("nebari-dev/p", "P", None, "o")]
    out = render_landing_markdown(rows, "t")
    assert 'data-level="none"' in out


def test_landing_missing_owner_shows_unassigned():
    r = PackRow(repo="nebari-dev/q")
    r.metadata = {"display_name": "Q", "level": "ga"}
    out = render_landing_markdown([r], "t")
    assert "unassigned" in out


def test_landing_href_escapes_double_quote():
    # A docs URL containing a double quote must not break out of the href attribute.
    rows = [_row("nebari-dev/r", "R", "ga", "o", docs='https://x.dev/"onmouseover=alert(1)')]
    out = render_landing_markdown(rows, "t")
    assert '"onmouseover=alert(1)' not in out
    assert "&quot;onmouseover=alert(1)" in out


# ---------------------------------------------------------------------------
# Starlight splash front matter + HTML injection escaping
# ---------------------------------------------------------------------------


def test_render_landing_emits_starlight_splash_catalog():
    rows = [PackRow(repo="nebari-dev/demo-pack", metadata={"display_name": "Demo Pack", "level": "beta", "owner": "alice"})]
    out = render_landing_markdown(rows, "2026-06-30T00:00:00Z")
    # Starlight YAML front matter (not Hugo +++), splash template.
    assert out.startswith("---\n")
    assert "title: Nebari Software Packs" in out
    assert "template: splash" in out
    assert "+++" not in out
    # Card catalog with a row for the pack.
    assert "## Officially supported packs" in out
    assert '<div class="pack-grid">' in out
    assert '<span class="pack-card__name">Demo Pack</span>' in out


def test_render_landing_html_escapes_display_name_and_owner():
    """Regression: display_name and owner with HTML special chars must be escaped."""
    rows = [PackRow(
        repo="nebari-dev/evil-pack",
        metadata={
            "display_name": "Foo <script> & Bar",
            "level": "alpha",
            "owner": "bob<evil>",
        },
    )]
    out = render_landing_markdown(rows, "2026-06-30T00:00:00Z")
    # Raw angle brackets and ampersands must not appear in display_name or owner cells
    assert "<script>" not in out
    assert "<evil>" not in out
    # Escaped forms must be present instead
    assert "&lt;script&gt;" in out
    assert "&amp;" in out
    assert "&lt;evil&gt;" in out


# ---------------------------------------------------------------------------
# fetch_metadata (contents API)
# ---------------------------------------------------------------------------


def test_fetch_metadata_uses_contents_api(monkeypatch):
    """fetch_metadata must use the contents API, not raw.githubusercontent.com.

    raw.githubusercontent.com does not reliably honor fine-grained PATs, so
    private pack repos (e.g. data-engineering-pack) come back 404 even with
    a valid token. The contents API with the raw media type works for both
    public and private repos.
    """
    calls = []

    def fake_request(url, token, accept="application/vnd.github+json"):
        calls.append({"url": url, "token": token, "accept": accept})
        return 200, b"name: foo\nlevel: beta\n"

    monkeypatch.setattr(generate, "_request_with_retry", fake_request)
    data, errors = generate.fetch_metadata("nebari-dev/foo", "tok123")

    assert data == {"name": "foo", "level": "beta"}
    assert errors == []
    assert calls[0]["url"] == "https://api.github.com/repos/nebari-dev/foo/contents/pack-metadata.yaml"
    assert calls[0]["token"] == "tok123"
    assert calls[0]["accept"] == "application/vnd.github.raw+json"


def test_fetch_metadata_404_reports_missing(monkeypatch):
    monkeypatch.setattr(generate, "_request_with_retry", lambda *a, **k: (404, b""))
    data, errors = generate.fetch_metadata("nebari-dev/foo", None)
    assert data is None
    assert errors == ["metadata-missing"]


def test_fetch_metadata_non_mapping_rejected(monkeypatch):
    monkeypatch.setattr(generate, "_request_with_retry", lambda *a, **k: (200, b"- just\n- a list\n"))
    data, errors = generate.fetch_metadata("nebari-dev/foo", None)
    assert data is None
    assert errors == ["pack-metadata.yaml is not a YAML mapping"]


# ---------------------------------------------------------------------------
# _select_latest_release (deterministic release selection)
# ---------------------------------------------------------------------------

# GitHub's list-releases endpoint does not document a sort order, so selection
# must never depend on list position. Each case lists releases in a
# deliberately unhelpful order and asserts the most recently *published*
# non-draft release is chosen. Prereleases are included; only drafts excluded.
@pytest.mark.parametrize(
    "releases,expected_tag",
    [
        # Regression for the llm-serving-pack bug (issue #20): the newest
        # published release is not first in the list.
        (
            [
                {"tag_name": "v0.1.0-alpha.9", "published_at": "2026-06-16T15:04:20Z", "created_at": "2026-06-16T15:02:54Z", "draft": False, "prerelease": False},
                {"tag_name": "nebari-llm-serving-0.1.2", "published_at": "2026-07-15T21:40:25Z", "created_at": "2026-07-15T21:40:06Z", "draft": False, "prerelease": False},
                {"tag_name": "v0.1.1", "published_at": "2026-07-13T12:52:13Z", "created_at": "2026-07-10T11:16:48Z", "draft": False, "prerelease": False},
            ],
            "nebari-llm-serving-0.1.2",
        ),
        # Prereleases count: a prerelease with the latest publish date wins.
        (
            [
                {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z", "created_at": "2026-01-01T00:00:00Z", "draft": False, "prerelease": False},
                {"tag_name": "v1.1.0-alpha.1", "published_at": "2026-02-01T00:00:00Z", "created_at": "2026-02-01T00:00:00Z", "draft": False, "prerelease": True},
            ],
            "v1.1.0-alpha.1",
        ),
        # Drafts are excluded even when created most recently.
        (
            [
                {"tag_name": "v2.0.0-draft", "published_at": None, "created_at": "2026-09-01T00:00:00Z", "draft": True, "prerelease": False},
                {"tag_name": "v1.0.0", "published_at": "2026-08-01T00:00:00Z", "created_at": "2026-08-01T00:00:00Z", "draft": False, "prerelease": False},
            ],
            "v1.0.0",
        ),
        # A non-draft with null published_at falls back to created_at ordering.
        (
            [
                {"tag_name": "older", "published_at": "2026-03-01T00:00:00Z", "created_at": "2026-03-01T00:00:00Z", "draft": False, "prerelease": False},
                {"tag_name": "newer-null-publish", "published_at": None, "created_at": "2026-05-01T00:00:00Z", "draft": False, "prerelease": False},
            ],
            "newer-null-publish",
        ),
        # Single release.
        (
            [{"tag_name": "v0.1.0", "published_at": "2026-01-01T00:00:00Z", "created_at": "2026-01-01T00:00:00Z", "draft": False, "prerelease": False}],
            "v0.1.0",
        ),
        # Malformed (non-dict) list entries are ignored, not fatal.
        (
            [
                "not-a-dict",
                None,
                {"tag_name": "v1.0.0", "published_at": "2026-01-01T00:00:00Z", "created_at": "2026-01-01T00:00:00Z", "draft": False, "prerelease": False},
            ],
            "v1.0.0",
        ),
    ],
)
def test_select_latest_release_picks_most_recent_published(releases, expected_tag):
    rel = generate._select_latest_release(releases)
    assert rel is not None
    assert rel["tag_name"] == expected_tag


def test_select_latest_release_tie_is_deterministic_by_id():
    """On identical published_at, selection must not depend on list order.

    Ties are broken by the monotonically increasing release id, so the newest
    (higher id) wins regardless of the order GitHub returns them in.
    """
    low = {"tag_name": "same-time-low-id", "id": 100, "published_at": "2026-04-01T00:00:00Z", "created_at": "2026-04-01T00:00:00Z", "draft": False}
    high = {"tag_name": "same-time-high-id", "id": 200, "published_at": "2026-04-01T00:00:00Z", "created_at": "2026-04-01T00:00:00Z", "draft": False}
    assert generate._select_latest_release([low, high])["tag_name"] == "same-time-high-id"
    assert generate._select_latest_release([high, low])["tag_name"] == "same-time-high-id"


@pytest.mark.parametrize(
    "releases",
    [
        [],
        [{"tag_name": "draft-only", "published_at": None, "created_at": "2026-01-01T00:00:00Z", "draft": True, "prerelease": False}],
    ],
)
def test_select_latest_release_returns_none_when_no_usable_release(releases):
    assert generate._select_latest_release(releases) is None


def test_fetch_github_data_selects_newest_published_release(monkeypatch):
    """fetch_github_data must not trust the position of /releases results.

    Regression for issue #20: given releases returned in an order where the
    newest published one is not first, the newest published tag must win.
    """
    releases_json = json.dumps(
        [
            {"tag_name": "v0.1.0-alpha.9", "published_at": "2026-06-16T15:04:20Z", "created_at": "2026-06-16T15:02:54Z", "draft": False, "prerelease": False},
            {"tag_name": "nebari-llm-serving-0.1.2", "published_at": "2026-07-15T21:40:25Z", "created_at": "2026-07-15T21:40:06Z", "draft": False, "prerelease": False},
            {"tag_name": "v0.1.1", "published_at": "2026-07-13T12:52:13Z", "created_at": "2026-07-10T11:16:48Z", "draft": False, "prerelease": False},
        ]
    ).encode()

    def fake_request(url, token, accept="application/vnd.github+json"):
        if "/releases" in url:
            return 200, releases_json
        if "/commits" in url:
            return 200, json.dumps([{"commit": {"committer": {"date": "2026-07-16T00:00:00Z"}}}]).encode()
        # repo metadata call
        return 200, json.dumps({"open_issues_count": 0, "description": "x"}).encode()

    monkeypatch.setattr(generate, "_request_with_retry", fake_request)
    data = generate.fetch_github_data("nebari-dev/foo", "tok")
    assert data["release_tag"] == "nebari-llm-serving-0.1.2"
    assert data["release_date"] == date(2026, 7, 15)


def test_landing_card_includes_repo_description():
    """Cards should show the GitHub repo description, HTML-escaped."""
    rows = [PackRow(
        repo="nebari-dev/foo-pack",
        metadata={"display_name": "Foo", "level": "beta", "owner": "alice"},
        github_data={"description": "Deploys Foo <fast> & easy"},
    )]
    out = render_landing_markdown(rows, "2026-07-03T00:00:00Z")
    assert '<span class="pack-card__desc">Deploys Foo &lt;fast&gt; &amp; easy</span>' in out


def test_landing_card_omits_description_span_when_missing():
    rows = [PackRow(
        repo="nebari-dev/foo-pack",
        metadata={"display_name": "Foo", "level": "beta", "owner": "alice"},
    )]
    out = render_landing_markdown(rows, "2026-07-03T00:00:00Z")
    assert "pack-card__desc" not in out
