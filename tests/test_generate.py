"""Unit tests for generate.py. No network access."""
from __future__ import annotations

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
