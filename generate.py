#!/usr/bin/env python3
"""Generate the Nebari pack dashboard.

Reads tracked-packs.yaml, fetches each pack's pack-metadata.yaml and a
small set of GitHub API fields, and renders dashboard markdown to
README.md (or stdout under --dry-run).
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
USER_AGENT = "nebari-pack-dashboard/1.0"

LEVELS = ("experimental", "alpha", "beta", "ga")
NEBARIAPP_VALUES = ("none", "partial", "full", "na")

STALE_DAYS = 90

FLAG_DISPLAY = {
    "metadata-missing": "🆘 metadata-missing",
    "metadata-invalid": "⚠️ metadata-invalid",
    "repo-not-found": "🆘 repo-not-found",
    "stale": "⚠️ stale",
    "no-product-owner": "⚠️ no-product-owner",
    "deprecated": "🚫 deprecated",
}

FLAG_DESCRIPTIONS = {
    "metadata-missing": "Pack repo has no `pack-metadata.yaml` file. Pack-author fields show `–`.",
    "metadata-invalid": "`pack-metadata.yaml` exists but failed validation. The specific error appears in the Notes column.",
    "repo-not-found": "Pack repo could not be reached. Check the `tracked-packs.yaml` entry.",
    "stale": f"Default branch has had no commits in the last {STALE_DAYS} days.",
    "no-product-owner": "Pack is GA but `product_owner` is null in its metadata.",
    "deprecated": "Pack is marked `deprecated: true`. See the Deprecated packs table for sunset details.",
}

COLUMN_DESCRIPTIONS = [
    ("Pack", "Pack name (from `display_name`), linked to its GitHub repo."),
    ("Description", "One-line summary of what the pack does. Sourced from the GitHub repo description (set via repo settings or `gh repo edit -d`)."),
    ("Level", "Maturity level: Experimental, Alpha, Beta, or **GA**. Definitions and promotion criteria live in the [release readiness checklist](https://github.com/nebari-dev/nebari-software-pack-template/blob/main/docs/release-readiness-checklist.md). Sourced from `level` in pack-metadata.yaml."),
    ("Owner", "GitHub handle of the engineer accountable for the pack. From `owner` in pack-metadata.yaml."),
    ("NebariApp", "How the pack integrates with the NebariApp CRD: Full, Partial, None, or N/A. From `nebariapp_integration`."),
    ("Standalone", "Whether the pack installs without the Nebari operator. From `scope.standalone-supported`."),
    ("Last release", "Most recent published release tag (including prereleases). Falls back to the latest git tag if no GitHub Release records exist. Sourced from the GitHub API."),
    ("Last commit", "Date of the most recent commit on the default branch. Sourced from the GitHub API."),
    ("Flags", "Auto-computed status flags. See the Flag reference below."),
    ("Notes", "Free-form `demo_notes` from pack-metadata.yaml (truncated at 100 chars). For packs with validation errors, the error message appears here instead."),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PackRow:
    repo: str
    metadata: dict | None = None
    metadata_errors: list[str] = field(default_factory=list)
    github_data: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    repo_not_found: bool = False


# ---------------------------------------------------------------------------
# Loading & HTTP
# ---------------------------------------------------------------------------


def load_tracked_packs(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "packs" not in data:
        raise ValueError(f"{path}: missing top-level 'packs' key")
    packs = data["packs"]
    if not isinstance(packs, list) or not packs:
        raise ValueError(f"{path}: 'packs' must be a non-empty list")
    for entry in packs:
        if not isinstance(entry, dict) or "repo" not in entry:
            raise ValueError(f"{path}: every pack entry must have a 'repo' field")
        if "/" not in entry["repo"]:
            raise ValueError(f"{path}: repo '{entry['repo']}' must be owner/name")
    return packs


def _request(url: str, token: str | None, accept: str = "application/vnd.github+json") -> tuple[int, bytes]:
    """Single HTTP GET. Returns (status, body). Does not raise on HTTP errors."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


def _request_with_retry(url: str, token: str | None, accept: str = "application/vnd.github+json") -> tuple[int, bytes]:
    """Retry once on 5xx or network failure with 2s backoff."""
    try:
        status, body = _request(url, token, accept)
    except urllib.error.URLError as e:
        print(f"WARN: network error for {url}: {e}; retrying once", file=sys.stderr)
        time.sleep(2)
        try:
            return _request(url, token, accept)
        except urllib.error.URLError as e2:
            print(f"ERROR: network error for {url} (retry failed): {e2}", file=sys.stderr)
            return 0, b""

    if 500 <= status < 600:
        print(f"WARN: {status} for {url}; retrying once", file=sys.stderr)
        time.sleep(2)
        try:
            return _request(url, token, accept)
        except urllib.error.URLError as e:
            print(f"ERROR: network error for {url} (retry failed): {e}", file=sys.stderr)
            return 0, b""

    if status == 403:
        # Rate limit detection
        print(f"ERROR: 403 for {url} (rate limit?)", file=sys.stderr)
    return status, body


def fetch_metadata(repo: str, token: str | None) -> tuple[dict | None, list[str]]:
    """Fetch pack-metadata.yaml. Returns (data | None, errors).

    errors is a list of error message strings. If the file is missing,
    the single error 'metadata-missing' is returned. If the file is
    present but malformed, returns (None, [parse error]).
    """
    url = f"{RAW_BASE}/{repo}/HEAD/pack-metadata.yaml"
    status, body = _request_with_retry(url, token, accept="*/*")
    if status == 404:
        return None, ["metadata-missing"]
    if status == 0 or status >= 400:
        return None, [f"fetch failed: HTTP {status}"]
    try:
        data = yaml.safe_load(body.decode("utf-8"))
    except yaml.YAMLError as e:
        return None, [f"YAML parse error: {e}"]
    if not isinstance(data, dict):
        return None, ["pack-metadata.yaml is not a YAML mapping"]
    return data, []


def fetch_github_data(repo: str, token: str | None) -> dict:
    """Fetch latest release, last commit date, open issue count.

    Returns dict with keys: release_tag, release_date, last_commit_date,
    open_issues_count, repo_not_found. Missing values are None.
    """
    out: dict[str, Any] = {
        "release_tag": None,
        "release_date": None,
        "last_commit_date": None,
        "open_issues_count": None,
        "description": None,
        "repo_not_found": False,
    }

    status, body = _request_with_retry(f"{GITHUB_API}/repos/{repo}", token)
    if status == 404:
        out["repo_not_found"] = True
        return out
    if status == 200:
        try:
            repo_info = json.loads(body)
            out["open_issues_count"] = repo_info.get("open_issues_count")
            desc = repo_info.get("description")
            if isinstance(desc, str) and desc.strip():
                out["description"] = desc.strip()
        except json.JSONDecodeError:
            pass

    # Use /releases?per_page=1 instead of /releases/latest so prereleases
    # are included. /releases/latest skips prereleases and drafts, which 404s
    # for packs whose only releases so far are alphas/betas.
    status, body = _request_with_retry(f"{GITHUB_API}/repos/{repo}/releases?per_page=1", token)
    if status == 200:
        try:
            releases = json.loads(body)
            if releases and isinstance(releases, list):
                rel = releases[0]
                if not rel.get("draft"):
                    out["release_tag"] = rel.get("tag_name")
                    published = rel.get("published_at")
                    if published:
                        out["release_date"] = _parse_iso(published)
        except json.JSONDecodeError:
            pass

    # Fall back to git tags when no GitHub Release records exist. Some packs
    # tag releases (v0.1.0-alpha.N) without creating Release objects, and
    # the dashboard should still surface a recent version. We use the most
    # recent tag from /tags (GitHub returns these in reverse-chronological
    # tag-creation order; imperfect for semver but good enough), then a
    # second call to /commits/{tag} to recover the tag's commit date.
    if out["release_tag"] is None:
        status, body = _request_with_retry(f"{GITHUB_API}/repos/{repo}/tags?per_page=1", token)
        if status == 200:
            try:
                tags = json.loads(body)
                if tags and isinstance(tags, list):
                    tag_name = tags[0].get("name")
                    if tag_name:
                        out["release_tag"] = tag_name
                        ts, tb = _request_with_retry(
                            f"{GITHUB_API}/repos/{repo}/commits/{urllib.parse.quote(tag_name, safe='')}",
                            token,
                        )
                        if ts == 200:
                            try:
                                commit = json.loads(tb)
                                committed = commit.get("commit", {}).get("committer", {}).get("date")
                                if committed:
                                    out["release_date"] = _parse_iso(committed)
                            except json.JSONDecodeError:
                                pass
            except json.JSONDecodeError:
                pass

    status, body = _request_with_retry(f"{GITHUB_API}/repos/{repo}/commits?per_page=1", token)
    if status == 200:
        try:
            commits = json.loads(body)
            if commits and isinstance(commits, list):
                committed = commits[0].get("commit", {}).get("committer", {}).get("date")
                if committed:
                    out["last_commit_date"] = _parse_iso(committed)
        except json.JSONDecodeError:
            pass

    return out


def _parse_iso(s: str) -> date | None:
    """Parse YYYY-MM-DD or full ISO 8601 timestamp into a date."""
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_metadata(data: dict, expected_name: str) -> list[str]:
    """Run validation rules from §4.4. Returns list of error strings."""
    errors: list[str] = []
    required = ("name", "display_name", "level", "owner", "deprecated")

    for field_name in required:
        if field_name not in data:
            errors.append(f"missing required field: {field_name}")
            continue
        val = data[field_name]
        if field_name == "deprecated":
            if not isinstance(val, bool):
                errors.append("deprecated must be a boolean")
        elif val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"{field_name} must be non-empty")

    if data.get("name") and data["name"] != expected_name:
        errors.append(f"name '{data['name']}' does not match repo name '{expected_name}'")

    level = data.get("level")
    if level is not None and level not in LEVELS:
        errors.append(f"level must be one of {LEVELS}, got '{level}'")

    nai = data.get("nebariapp_integration")
    if nai is not None and nai not in NEBARIAPP_VALUES:
        errors.append(f"nebariapp_integration must be one of {NEBARIAPP_VALUES}, got '{nai}'")

    if data.get("deprecated") is True:
        sunset = data.get("sunset_date")
        if not sunset:
            errors.append("deprecated: true requires sunset_date")
        elif _parse_iso(str(sunset)) is None:
            errors.append(f"sunset_date '{sunset}' is not a valid ISO date")

    if level == "ga":
        po = data.get("product_owner")
        if po is None or (isinstance(po, str) and not po.strip()):
            errors.append("level: ga requires non-null product_owner")

    for df in ("sunset_date", "last_promoted_at"):
        v = data.get(df)
        if v is not None and _parse_iso(str(v)) is None:
            errors.append(f"{df} '{v}' is not a valid ISO date (YYYY-MM-DD)")

    desc = data.get("description")
    if isinstance(desc, str) and len(desc) > 200:
        errors.append(f"description exceeds 200 chars ({len(desc)})")

    notes = data.get("demo_notes")
    if isinstance(notes, str) and len(notes) > 500:
        errors.append(f"demo_notes exceeds 500 chars ({len(notes)})")

    links = data.get("links")
    if isinstance(links, dict):
        for k, v in links.items():
            if v is None:
                continue
            if not isinstance(v, str):
                errors.append(f"links.{k} must be a string URL")
                continue
            parsed = urllib.parse.urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                errors.append(f"links.{k} '{v}' is not a valid URL")

    return errors


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def compute_flags(
    metadata: dict | None,
    github_data: dict,
    today: date,
    metadata_errors: list[str] | None = None,
) -> list[str]:
    flags: list[str] = []
    errors = metadata_errors or []

    if github_data.get("repo_not_found"):
        flags.append("repo-not-found")

    if "metadata-missing" in errors:
        flags.append("metadata-missing")
    elif errors:
        flags.append("metadata-invalid")

    md = metadata or {}
    deprecated = bool(md.get("deprecated"))

    last_commit = github_data.get("last_commit_date")
    if last_commit and not deprecated:
        if (today - last_commit).days > STALE_DAYS:
            flags.append("stale")

    level = md.get("level")
    if level == "ga" and md.get("product_owner") in (None, ""):
        flags.append("no-product-owner")

    if deprecated:
        flags.append("deprecated")

    return flags


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt_date(d: date | None) -> str:
    if d is None:
        return "–"
    return d.strftime("%b %d")


def _user_link(username: str) -> str:
    return f"[@{username}](https://github.com/{username})"


def _standalone_value(scope: Any) -> str:
    if not isinstance(scope, dict):
        return "–"
    if "standalone-supported" not in scope:
        return "–"
    v = scope["standalone-supported"]
    if v is True or (isinstance(v, str) and v.lower() == "yes"):
        return "Yes"
    if v is False or (isinstance(v, str) and v.lower() == "no"):
        return "No"
    return "–"


def _nebariapp_value(v: Any) -> str:
    mapping = {"none": "None", "partial": "Partial", "full": "Full", "na": "N/A"}
    if not isinstance(v, str):
        return "N/A"
    return mapping.get(v, "N/A")


def _level_label(level: Any) -> str:
    if not isinstance(level, str) or level not in LEVELS:
        return "–"
    label = {"experimental": "Experimental", "alpha": "Alpha", "beta": "Beta", "ga": "GA"}[level]
    return f"**{label}**" if level == "ga" else label


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def render_row(row: PackRow) -> str:
    md = row.metadata or {}
    gh = row.github_data

    display = md.get("display_name") or row.repo.split("/")[-1]
    pack_cell = f"[{display}](https://github.com/{row.repo})"

    desc = gh.get("description")
    if isinstance(desc, str) and desc.strip():
        description_cell = desc.replace("|", "\\|").replace("\n", " ")
    else:
        description_cell = "–"

    level_cell = _level_label(md.get("level"))
    owner = md.get("owner")
    owner_cell = _user_link(owner) if isinstance(owner, str) and owner else "–"
    nai_cell = _nebariapp_value(md.get("nebariapp_integration", "na"))
    standalone_cell = _standalone_value(md.get("scope"))

    tag = gh.get("release_tag")
    rdate = gh.get("release_date")
    release_cell = f"{tag} ({_fmt_date(rdate)})" if tag else "–"

    commit_cell = _fmt_date(gh.get("last_commit_date"))

    flags_cell = " ".join(FLAG_DISPLAY.get(f, f) for f in row.flags) if row.flags else "–"

    notes = md.get("demo_notes")
    if row.metadata_errors and "metadata-missing" not in row.metadata_errors:
        notes_cell = "; ".join(row.metadata_errors)
    elif isinstance(notes, str) and notes:
        notes_cell = _truncate(notes, 100)
    else:
        notes_cell = "–"
    notes_cell = notes_cell.replace("|", "\\|").replace("\n", " ")

    return (
        f"| {pack_cell} | {description_cell} | {level_cell} | {owner_cell} | {nai_cell} | {standalone_cell} "
        f"| {release_cell} | {commit_cell} | {flags_cell} | {notes_cell} |"
    )


def render_deprecated_row(row: PackRow) -> str:
    md = row.metadata or {}
    display = md.get("display_name") or row.repo.split("/")[-1]
    pack_cell = f"[{display}](https://github.com/{row.repo})"
    was_level = _level_label(md.get("level"))
    sunset = md.get("sunset_date") or "–"
    docs = (md.get("links") or {}).get("docs") if isinstance(md.get("links"), dict) else None
    migration = docs or "–"
    return f"| {pack_cell} | {was_level} | {sunset} | {migration} |"


def render_dashboard(rows: list[PackRow], generated_at: datetime, workflow_url: str | None = None) -> str:
    active = [r for r in rows if not (r.metadata and r.metadata.get("deprecated"))]
    deprecated = [r for r in rows if r.metadata and r.metadata.get("deprecated")]

    counts = {"ga": 0, "beta": 0, "alpha": 0, "experimental": 0}
    for r in active:
        lvl = (r.metadata or {}).get("level")
        if lvl in counts:
            counts[lvl] += 1

    flag_totals: dict[str, int] = {}
    flagged_packs = 0
    for r in rows:
        non_deprecated_flags = [f for f in r.flags if f != "deprecated"]
        if non_deprecated_flags:
            flagged_packs += 1
        for f in r.flags:
            flag_totals[f] = flag_totals.get(f, 0) + 1

    ts = generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    refresh_link = f"[Trigger a refresh]({workflow_url})." if workflow_url else "Trigger a refresh via the `Refresh pack dashboard` workflow."

    lines: list[str] = []
    lines.append("<!-- This file is auto-generated by generate.py. Do not edit directly. -->")
    lines.append("")
    lines.append("# Nebari Software Packs")
    lines.append("")
    lines.append(f"_Last regenerated: {ts}. {refresh_link}_")
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    lines.append(
        f"- {counts['ga']} GA · {counts['beta']} Beta · {counts['alpha']} Alpha · "
        f"{counts['experimental']} Experimental · {len(deprecated)} Deprecated"
    )
    if flag_totals:
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(flag_totals.items()))
        lines.append(f"- {flagged_packs} packs flagged · breakdown: {breakdown}")
    else:
        lines.append(f"- {flagged_packs} packs flagged")
    lines.append("")
    lines.append("## Packs")
    lines.append("")
    lines.append("| Pack | Description | Level | Owner | NebariApp | Standalone | Last release | Last commit | Flags | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in active:
        lines.append(render_row(r))
    lines.append("")

    if deprecated:
        lines.append("## Deprecated packs")
        lines.append("")
        lines.append("| Pack | Was Level | Sunset date | Migration |")
        lines.append("|---|---|---|---|")
        for r in deprecated:
            lines.append(render_deprecated_row(r))
        lines.append("")

    lines.append("## Column reference")
    lines.append("")
    for name, desc in COLUMN_DESCRIPTIONS:
        lines.append(f"- **{name}** - {desc}")
    lines.append("")
    lines.append("## Flag reference")
    lines.append("")
    for flag, display in FLAG_DISPLAY.items():
        lines.append(f"- {display} - {FLAG_DESCRIPTIONS[flag]}")
    lines.append("")
    lines.append("## How this dashboard works")
    lines.append("")
    lines.append(
        "Each row is built from two sources: a `pack-metadata.yaml` file at the "
        "root of each pack repo (edited by the pack's owner) and a small set of "
        "GitHub API fields (latest release, last commit, open issues)."
    )
    lines.append("")
    lines.append(
        "To add a pack to this dashboard:"
    )
    lines.append("")
    lines.append(
        "1. Copy [`schema/pack-metadata.example.yaml`](schema/pack-metadata.example.yaml) "
        "into your pack repo as `pack-metadata.yaml`, fill in the required fields, "
        "and merge to your default branch."
    )
    lines.append(
        "2. Open a PR against this repo adding your pack to "
        "[`tracked-packs.yaml`](tracked-packs.yaml)."
    )
    lines.append("")
    lines.append("See [CONTRIBUTING.md](CONTRIBUTING.md) for the full walkthrough.")
    lines.append("")
    lines.append(f"_Generated: {ts}_")
    lines.append("")

    return "\n".join(lines)


def _html_level_label(level: Any) -> str:
    """Plain-text level label for HTML (markdown-free version of _level_label)."""
    if not isinstance(level, str) or level not in LEVELS:
        return "–"
    return {"experimental": "Experimental", "alpha": "Alpha", "beta": "Beta", "ga": "GA"}[level]


def render_html(rows: list[PackRow], generated_at: str) -> str:
    """Render a minimal, self-contained landing page for packs.nebari.dev.

    One intro paragraph defining a software pack, a link to nebari.dev, a link
    to the build-a-pack guide, and a table reusing the same per-pack data as
    render_dashboard (display_name, level, owner, and an optional docs link
    from links.docs). All dynamic values are HTML-escaped.
    """
    head = (
        "<!doctype html><meta charset=utf-8>"
        "<title>Nebari Software Packs</title>"
        "<style>body{font-family:system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}</style>"
    )
    intro = (
        "<h1>Nebari Software Packs</h1>"
        "<p>A <strong>software pack</strong> is a packaged, opinionated way to deploy a "
        "service on a Nebari cluster - with routing, TLS, and OIDC wired in - so teams add "
        "capabilities without re-solving the platform plumbing each time.</p>"
        "<p>See the <a href=\"https://nebari.dev\">Nebari documentation</a>, or learn to build "
        "one in the <a href=\"/building-a-software-pack/\">Building a software pack</a> guide.</p>"
        "<h2>Officially supported packs</h2>"
    )
    header = "<tr><th>Pack</th><th>Level</th><th>Owner</th><th>Docs</th></tr>"

    body_rows: list[str] = []
    for r in rows:
        md = r.metadata or {}
        display = md.get("display_name") or r.repo.split("/")[-1]
        owner = md.get("owner") or ""
        links = md.get("links") if isinstance(md.get("links"), dict) else {}
        docs = links.get("docs") if isinstance(links, dict) else None

        display_cell = html_lib.escape(str(display))
        level_cell = html_lib.escape(_html_level_label(md.get("level")))
        owner_cell = html_lib.escape(str(owner)) if owner else "–"
        # Only emit http(s) hrefs - pack-metadata.yaml comes from third-party
        # repos, so reject javascript:/data: and other unsafe schemes.
        if isinstance(docs, str) and urllib.parse.urlparse(docs.strip()).scheme in ("http", "https"):
            docs_cell = f'<a href="{html_lib.escape(docs.strip(), quote=True)}">docs</a>'
        else:
            docs_cell = "–"

        body_rows.append(
            f"<tr><td>{display_cell}</td><td>{level_cell}</td>"
            f"<td>{owner_cell}</td><td>{docs_cell}</td></tr>"
        )

    body = "".join(body_rows)
    generated = html_lib.escape(str(generated_at))
    return (
        f"{head}{intro}<table>{header}{body}</table>"
        f"<p><small>Generated {generated}</small></p>"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_row(pack: dict, token: str | None, today: date) -> PackRow:
    repo = pack["repo"]
    expected_name = repo.split("/")[-1]
    row = PackRow(repo=repo)

    github_data = fetch_github_data(repo, token)
    row.github_data = github_data
    if github_data.get("repo_not_found"):
        row.repo_not_found = True
        print(f"ERROR: repo not found: {repo}", file=sys.stderr)
        row.flags = compute_flags(None, github_data, today, ["metadata-missing"])
        return row

    metadata, errors = fetch_metadata(repo, token)
    if metadata is None:
        row.metadata = None
        row.metadata_errors = errors
        if errors == ["metadata-missing"]:
            print(f"WARN: pack-metadata.yaml missing in {repo}", file=sys.stderr)
        else:
            print(f"WARN: pack-metadata.yaml unreadable in {repo}: {errors}", file=sys.stderr)
    else:
        validation_errors = validate_metadata(metadata, expected_name)
        row.metadata = metadata
        row.metadata_errors = validation_errors
        if validation_errors:
            print(f"WARN: pack-metadata.yaml invalid in {repo}: {validation_errors}", file=sys.stderr)
        else:
            print(f"INFO: {repo} ok", file=sys.stderr)

    row.flags = compute_flags(row.metadata, github_data, today, row.metadata_errors)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Nebari pack dashboard.")
    parser.add_argument("--tracked-packs", default="tracked-packs.yaml")
    parser.add_argument("--output", default="README.md")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of writing the output file.")
    parser.add_argument("--workflow-url", default=None, help="URL to the refresh workflow for the regen link.")
    parser.add_argument(
        "--html",
        nargs="?",
        const="site/index.html",
        default=None,
        help="Render the landing page HTML to PATH (default site/index.html when the flag is given with no value).",
    )
    args = parser.parse_args(argv)

    try:
        packs = load_tracked_packs(args.tracked_packs)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        print(f"ERROR: cannot load {args.tracked_packs}: {e}", file=sys.stderr)
        return 1

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("WARN: GITHUB_TOKEN not set; using unauthenticated requests (60/hr limit)", file=sys.stderr)

    today = datetime.now(timezone.utc).date()
    rows = [build_row(p, token, today) for p in packs]

    generated_at = datetime.now(timezone.utc)
    output = render_dashboard(rows, generated_at, workflow_url=args.workflow_url)

    if args.html:
        html_out = render_html(rows, generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
        html_path = Path(args.html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_out + "\n", encoding="utf-8")
        print(f"INFO: wrote {html_path}", file=sys.stderr)

    if args.dry_run:
        sys.stdout.write(output)
        return 0

    try:
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = None

    if existing == output:
        print("INFO: no changes to output", file=sys.stderr)
        return 0

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"INFO: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
