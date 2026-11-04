#!/usr/bin/env -S ./py
"""Re-fetch 10 random accepted feeds independently (curl, not aiohttp), check
them with feedparser and brockman's parser (feedcheck), and append the result
to report.md."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time

import feedparser

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "## Spot-check: 10 random accepted feeds re-fetched"


def main():
    with open(os.path.join(HERE, "new-bots.json")) as f:
        bots = json.load(f)
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else int(time.time())
    picks = random.Random(seed).sample(sorted(bots), 10)
    tmp = tempfile.mkdtemp(prefix="spotcheck-")
    rows, paths = [], []
    for nick in picks:
        url = bots[nick]["feed"]
        path = os.path.join(tmp, nick)
        p = subprocess.run(["curl", "-sSL", "--compressed", "-m", "30", "-o", path,
                            "-A", "brockman/1.0 (+https://brockman.news)",
                            "-H", "Accept: application/atom+xml, application/rss+xml, */*",
                            "-w", "%{http_code}\t%{content_type}", url], capture_output=True, text=True)
        code, _, ctype = p.stdout.partition("\t")
        rows.append({"nick": nick, "url": url, "code": code, "ctype": ctype.split(";")[0],
                     "curl_err": p.stderr.strip()})
        paths.append(path)
    fc = subprocess.run([os.path.join(HERE, "feedcheck")], input="\n".join(paths) + "\n",
                        capture_output=True, text=True).stdout.splitlines()
    ok = 0
    lines = [MARK, "", f"Run {time.strftime('%Y-%m-%d %H:%M %Z')}, seed {seed}, fetched with curl "
             "(same UA/Accept), checked with feedparser and brockman's parser (`feedcheck`).", "",
             "| nick | url | http | content-type | feedparser | brockman parser (kind, items, titled+linked) | first item | ok |",
             "|---|---|---|---|---|---|---|---|"]
    for row, path, fcl in zip(rows, paths, fc):
        kind, n, _, strict = fcl.split("\t")[1:5]
        first = "-"
        fpv = "-"
        if os.path.exists(path):
            d = feedparser.parse(path)
            fpv = f"{d.get('version')} ({len(d.entries)} entries)"
            good = [e for e in d.entries if (e.get("title") or "").strip() and e.get("link")]
            if good:
                first = f"{good[0].title.strip()[:50]} — {good[0].link}".replace("|", "\\|")
        passed = row["code"] == "200" and kind in ("atom", "rss", "rss1") and int(strict) > 0 and first != "-"
        ok += passed
        lines.append(f"| `{row['nick']}` | {row['url']} | {row['code']} | {row['ctype']} | {fpv} | "
                     f"{kind}, {n}, {strict} | {first} | {'yes' if passed else 'NO ' + row['curl_err'][:60]} |")
    lines += ["", f"**{ok}/10 passed.**", ""]
    report = os.path.join(HERE, "report.md")
    with open(report) as f:
        text = f.read()
    if MARK in text:
        text = text[: text.index(MARK)]
    with open(report, "w") as f:
        f.write(text.rstrip("\n") + "\n\n" + "\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
