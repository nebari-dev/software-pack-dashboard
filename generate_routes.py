#!/usr/bin/env python3
"""Generate worker/src/routes.json from tracked-packs.yaml + extra-routes.json.

The route table maps a first URL segment (slug) to the Cloudflare Pages host
that serves that pack's docs. Tracked packs with `docs_site: true` get a route
`<slug> -> https://<slug>.pages.dev`; static non-pack docs come from
worker/extra-routes.json; everything else falls through to `__default__`
(the dashboard host). The Worker consumes this file (see worker/src/index.js).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

CONTENTS_URL = "https://api.github.com/repos/{repo}/contents/pack-metadata.yaml"


def fetch_metadata(repo: str, token: str | None = None) -> dict:
    # Contents API rather than raw.githubusercontent.com: the latter does not
    # reliably honor fine-grained PATs, which breaks private pack repos.
    req = urllib.request.Request(CONTENTS_URL.format(repo=repo))
    req.add_header("Accept", "application/vnd.github.raw+json")
    req.add_header("User-Agent", "nebari-pack-dashboard/1.0")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return yaml.safe_load(resp.read()) or {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise


def build_search_indexes(routes: dict, extras: dict) -> list[str]:
    """Bundle paths for packs that publish their own Pagefind index.

    A docs-enabled pack has a `<slug> -> https://<slug>.pages.dev` route; we
    exclude __default__ (the dashboard) and the static extra-routes (which are
    not Starlight packs with a Pagefind bundle).
    """
    skip = {"__default__", *extras.keys()}
    return [f"/{slug}/pagefind/" for slug in routes if slug not in skip]


def build_routes(packs, fetch, extras, default_host):
    routes = {"__default__": default_host}
    for repo in packs:
        meta = fetch(repo) or {}
        if meta.get("docs_site") is True:
            slug = repo.split("/")[-1]
            routes[slug] = f"https://{slug}.pages.dev"
    routes.update(extras)
    return routes


def main():
    root = Path(__file__).parent
    packs = [p["repo"] for p in yaml.safe_load((root / "tracked-packs.yaml").read_text())["packs"]]
    extras = json.loads((root / "worker" / "extra-routes.json").read_text())
    token = os.environ.get("GITHUB_TOKEN")
    routes = build_routes(packs, lambda repo: fetch_metadata(repo, token), extras,
                          default_host="https://software-pack-dashboard.pages.dev")
    out = root / "worker" / "src" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(routes, indent=2) + "\n")
    print(f"wrote {out} ({len(routes) - 1} docs routes)", file=sys.stderr)
    search_indexes = build_search_indexes(routes, extras)
    idx_out = root / "site" / "src" / "generated" / "search-indexes.json"
    idx_out.parent.mkdir(parents=True, exist_ok=True)
    idx_out.write_text(json.dumps(search_indexes, indent=2) + "\n")
    print(f"wrote {idx_out} ({len(search_indexes)} search indexes)", file=sys.stderr)


if __name__ == "__main__":
    main()
