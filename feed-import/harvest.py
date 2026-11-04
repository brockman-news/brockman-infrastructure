#!/usr/bin/env -S ./py
"""Collect candidate feed URLs from the public lists, dedupe, drop existing.

Outputs:
  candidates.json  [{key, url, sources:[...]}]  (only NEW, non-YouTube, unique)
  harvest-stats.json  per-source counts
"""
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict

from common import is_youtube, norm_key

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "sources")
RAW = "https://raw.githubusercontent.com"


def fetch(url, dest):
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(dest + ".tmp", "wb") as f:
            f.write(r.read())
        os.rename(dest + ".tmp", dest)
    with open(dest, "rb") as f:
        return f.read()


def lines(data):
    # one URL per line; a few smallweb lines hold two URLs separated by spaces
    out = []
    for ln in data.decode("utf-8", "replace").splitlines():
        if not ln.strip().startswith("#"):
            out.extend(ln.split())
    return out


def opml_urls(data):
    try:
        root = ET.fromstring(data)
        urls = [o.get("xmlUrl") for o in root.iter("outline") if o.get("xmlUrl")]
        return [u.strip() for u in urls]
    except ET.ParseError:
        text = data.decode("utf-8", "replace")
        return [html.unescape(m).strip() for m in re.findall(r'xmlUrl\s*=\s*"([^"]*)"', text)]


def main():
    sources = OrderedDict()  # source name -> [urls]
    sources["kagi/smallweb"] = lines(fetch(f"{RAW}/kagisearch/smallweb/main/smallweb.txt", f"{SRC}/smallweb.txt"))
    sources["kagi/smallcomic"] = lines(fetch(f"{RAW}/kagisearch/smallweb/main/smallcomic.txt", f"{SRC}/smallcomic.txt"))
    sources["hn-personal-blogs"] = opml_urls(
        fetch(f"{RAW}/outcoldman/hackernews-personal-blogs/master/list.opml", f"{SRC}/hn-personal-blogs.opml"))

    paths_file = f"{SRC}/plenary-paths.txt"
    if not os.path.exists(paths_file):
        out = subprocess.check_output(
            ["gh", "api", "repos/plenaryapp/awesome-rss-feeds/git/trees/master?recursive=1",
             "--jq", '.tree[]|select(.path|endswith(".opml"))|.path'])
        with open(paths_file, "wb") as f:
            f.write(out)
    with open(paths_file) as f:
        ppaths = [p.strip() for p in f if p.strip()]
    for p in ppaths:
        data = fetch(f"{RAW}/plenaryapp/awesome-rss-feeds/master/{urllib.parse.quote(p)}", f"{SRC}/plenary/{p}")
        sources[f"awesome-rss-feeds/{p}"] = opml_urls(data)

    with open("/tmp/brockman-state.json") as f:
        state = json.load(f)
    existing = {norm_key(b["feed"]) for b in state["bots"].values()}

    stats = OrderedDict()
    cands = OrderedDict()  # key -> {url, sources}
    for name, urls in sources.items():
        st = stats[name] = {"listed": len(urls), "invalid_url": 0, "youtube": 0,
                            "dup_within_source": 0, "dup_existing": 0, "candidates": 0}
        seen = set()
        for u in urls:
            if not re.match(r"^https?://[^/\s]+", u, re.I) or re.search(r"\s", u):
                st["invalid_url"] += 1
                continue
            if is_youtube(u):
                st["youtube"] += 1
                continue
            k = norm_key(u)
            if k in seen:
                st["dup_within_source"] += 1
                continue
            seen.add(k)
            if k in existing:
                st["dup_existing"] += 1
                continue
            st["candidates"] += 1
            c = cands.get(k)
            if c is None:
                cands[k] = {"key": k, "url": u, "sources": [name]}
            else:
                c["sources"].append(name)
                # prefer an https spelling if any source offers one
                if c["url"].lower().startswith("http://") and u.lower().startswith("https://"):
                    c["url"] = u

    out = list(cands.values())
    with open(os.path.join(HERE, "candidates.json"), "w") as f:
        json.dump(out, f, indent=0)
    with open(os.path.join(HERE, "harvest-stats.json"), "w") as f:
        json.dump({"sources": stats, "unique_candidates": len(out), "existing_feeds": len(existing)}, f, indent=1)
    print(f"unique new candidates: {len(out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
