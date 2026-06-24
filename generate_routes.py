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
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

RAW = "https://raw.githubusercontent.com/{repo}/main/pack-metadata.yaml"


def fetch_metadata(repo: str) -> dict:
    url = RAW.format(repo=repo)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return yaml.safe_load(resp.read()) or {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise


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
    routes = build_routes(packs, fetch_metadata, extras,
                          default_host="https://software-pack-dashboard.pages.dev")
    out = root / "worker" / "src" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(routes, indent=2) + "\n")
    print(f"wrote {out} ({len(routes) - 1} docs routes)", file=sys.stderr)


if __name__ == "__main__":
    main()
