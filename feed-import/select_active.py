#!/usr/bin/env -S ./py
"""News cleanup: keep one active feed per Media Cloud outlet.

  ./py select_active.py prepare [--news imported/2026-11-04-news.json ...]
      -> news-active/candidates.json: every Media Cloud feed of every outlet plus every live news bot's feed
  ./py validate.py --workdir news-active          (and the slow 429 / timeout passes with --workdir news-active)
  ./py select_active.py select [--min-recent 10] [--prefer-best] [--unmapped keep|active|drop] [--remove none|duplicates|all]
      -> news-active/changes.json, news-active/news-active.json, news-active/selection.jsonl, news-active/report.md

News bots are the bots of the given import batches (imported/*-news.json) that are still live. Every other live
bot (hand-made ones, the list imports) is never touched, and no new bot duplicates one of their feeds.

Outlet of a live news bot, first that matches exactly one outlet: its feed URL is one of the outlet's Media Cloud
feeds; its feed host is the host of the outlet's feeds; its feed host or registered domain is the outlet's name.

A feed is active if it passes the same checks as finalize.py (HTTP 200, feedparser and brockman's own parser) and
has >= --min-recent distinct items dated within 7 days of the fetch. Per outlet:
  - by default an active feed of one of the outlet's live news bots is kept (fewest URL changes); with
    --prefer-best the outlet's most active feed wins even if a live bot carries another active feed;
  - otherwise the most active feed (ties: Media Cloud's rank, site-wide and short first);
  - outlets without an active feed get no bot.
The outlet's live news bot keeps its nick when its feed URL changes; further live news bots of the outlet go.
New outlets get nicks like finalize.py's. Live news bots matching no current Media Cloud outlet: --unmapped.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, OrderedDict, defaultdict

import finalize
from common import host_of, norm_key, registered_domain
from mediacloud import rank

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "news-active")
SRC = os.path.join(HERE, "sources")
STATE = "/tmp/brockman-state.json"


def load(path):
    with open(path) as f:
        return json.load(f)


def bare_host(url_or_host):
    h = host_of(url_or_host) if "/" in url_or_host else url_or_host.lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def news_bots(state, batches):
    bots = OrderedDict()
    for path in batches:
        for nick, b in load(path).items():
            live = state["bots"].get(nick)
            if live is not None:  # still live; the live feed URL is what counts
                bots[nick] = live["feed"]
    return bots


def outlet_index(feeds, meta):
    by_feed, by_host, by_name = defaultdict(set), defaultdict(set), defaultdict(set)
    for o, urls in feeds.items():
        for u in urls:
            by_feed[norm_key(u)].add(o)
            by_host[bare_host(u)].add(o)
    for o, m in meta.items():
        if o in feeds and m.get("name"):
            by_name[bare_host(m["name"].split("/")[0])].add(o)
    return by_feed, by_host, by_name


def map_outlet(url, idx):
    by_feed, by_host, by_name = idx
    h = bare_host(url)
    ambiguous = None
    for how, hit in (("feed", by_feed.get(norm_key(url))), ("host", by_host.get(h)), ("name", by_name.get(h)),
                     ("domain", by_name.get(registered_domain(h)))):
        if hit and len(hit) == 1:
            return next(iter(hit)), how
        if hit and ambiguous is None:
            ambiguous = f"ambiguous {how}"
    return None, ambiguous or "none"


def prepare(args):
    feeds = load(os.path.join(SRC, "mediacloud-feeds.json"))
    meta = load(os.path.join(SRC, "mediacloud-outlets.json"))
    state = load(STATE)
    news = news_bots(state, args.news)
    idx = outlet_index(feeds, meta)
    cands = OrderedDict()

    def add(url, tag):
        k = norm_key(url)
        c = cands.setdefault(k, {"key": k, "url": url, "sources": []})
        c["sources"].append(tag)
        if c["url"].lower().startswith("http://") and url.lower().startswith("https://"):
            c["url"] = url

    for nick, url in news.items():  # live URL spelling first: that is the URL that keeps running
        add(url, f"live:{nick}")
    for o, urls in feeds.items():
        for u in urls:
            add(u, f"outlet:{o}")
    mapping = {nick: dict(zip(("outlet", "how"), map_outlet(url, idx)), feed=url) for nick, url in news.items()}
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "candidates.json"), "w") as f:
        json.dump(list(cands.values()), f, indent=0)
    with open(os.path.join(WORK, "mapping.json"), "w") as f:
        json.dump({"batches": args.news, "bots": mapping}, f, indent=0)
    how = Counter(m["how"] if m["outlet"] else ("unmapped: " + m["how"]) for m in mapping.values())
    print(f"live news bots: {len(news)}, mapped by {dict(how)}", file=sys.stderr)
    print(f"candidates: {len(cands)} (outlets {len(feeds)})", file=sys.stderr)


def select(args):
    finalize.BODIES = os.path.join(WORK, "bodies")
    finalize.FEEDCHECK = os.path.join(WORK, "feedcheck.tsv")
    feeds = load(os.path.join(SRC, "mediacloud-feeds.json"))
    meta = load(os.path.join(SRC, "mediacloud-outlets.json"))
    state = load(STATE)
    mp = load(os.path.join(WORK, "mapping.json"))
    news = news_bots(state, mp["batches"])
    mapping = mp["bots"]
    drifted = [n for n in news if n not in mapping or mapping[n]["feed"] != news[n]]
    if drifted:
        raise SystemExit(f"{len(drifted)} news bots changed since prepare (e.g. {drifted[:3]}): run prepare again")
    cands = {c["key"]: c for c in load(os.path.join(WORK, "candidates.json"))}
    results = {}
    with open(os.path.join(WORK, "results.jsonl")) as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            results[r["key"]] = r
    fc = finalize.run_feedcheck(list(results.values()))

    def check(url):
        """(recent item count or None if the feed fails, reason)"""
        r = results.get(norm_key(url))
        if r is None:
            return None, "not fetched"
        bucket, detail = finalize.verdict(r, fc)
        if bucket:
            return None, f"{bucket}: {detail}"
        return r.get("fp_recent7", 0), "ok"

    live_keys = {norm_key(b["feed"]): n for n, b in state["bots"].items()}
    other_keys = {k for k, n in live_keys.items() if n not in news}
    by_outlet = defaultdict(list)
    for nick, m in mapping.items():
        if m["outlet"]:
            by_outlet[m["outlet"]].append(nick)
    other_outlets = set()
    idx = outlet_index(feeds, meta)
    for n, b in state["bots"].items():
        if n not in news:
            o, _ = map_outlet(b["feed"], idx)
            if o:
                other_outlets.add(o)

    keep, change, add, remove = OrderedDict(), OrderedDict(), OrderedDict(), OrderedDict()
    rows = []
    # feeds no new bot may get: non-news bots' feeds, every live news bot's feed (it stays with its own outlet)
    taken_keys = set(other_keys) | {norm_key(u) for u in news.values()}
    stats = Counter()
    for o in sorted(set(feeds) | set(by_outlet), key=lambda x: int(x)):
        bots = sorted(by_outlet.get(o, []), key=lambda n: (len(n), n))
        options = []  # (recent, url, live nick or None)
        seen = set()
        for n in bots:
            seen.add(norm_key(news[n]))
            options.append((news[n], n))
        for u in sorted(feeds.get(o, []), key=rank):
            if norm_key(u) not in seen:
                seen.add(norm_key(u))
                options.append((u, None))
        scored = []
        for u, n in options:
            recent, why = check(u)
            scored.append({"url": u, "live": n, "recent": recent, "why": why})
        active = [s for s in scored if s["recent"] is not None and s["recent"] >= args.min_recent
                  and (s["live"] or norm_key(s["url"]) not in taken_keys)]
        pick = None
        if active:
            live_active = [s for s in active if s["live"]]
            pool = live_active if live_active and not args.prefer_best else active
            pick = max(pool, key=lambda s: (s["recent"], -pool.index(s)))
        best = max(active, key=lambda s: (s["recent"], -active.index(s))) if active else None
        row = {"outlet": o, "name": (meta.get(o) or {}).get("name"), "bots": bots, "pick": pick and pick["url"],
               "pick_recent": pick and pick["recent"], "best_differs": bool(best and pick and best is not pick),
               "feeds": scored}
        if pick is None:
            for n in bots:
                remove[n] = "outlet has no active feed"
            row["action"] = "none active" + (", remove all" if bots else "")
        else:
            taken_keys.add(norm_key(pick["url"]))
            if pick["live"]:
                keep[pick["live"]] = news[pick["live"]]
                row["action"] = "keep"
                holder = pick["live"]
            elif bots:
                holder = bots[0]
                change[holder] = {"from": news[holder], "to": stored_url(pick["url"], results)}
                row["action"] = "change"
            elif o in other_outlets:
                holder = None
                row["action"] = "covered by a non-news bot"
            else:
                holder = None
                add[norm_key(pick["url"])] = stored_url(pick["url"], results)
                row["action"] = "add"
            for n in bots:
                if n != holder:
                    remove[n] = "second bot of the outlet"
        stats[row["action"]] += 1
        rows.append(row)

    unmapped = [n for n, m in mapping.items() if not m["outlet"]]
    unmapped_stats = Counter()
    for n in unmapped:
        recent, why = check(news[n])
        active = recent is not None and recent >= args.min_recent
        unmapped_stats["active" if active else "inactive" if recent is not None else "failing"] += 1
        if args.unmapped == "drop" or (args.unmapped == "active" and not active):
            remove[n] = f"no current Media Cloud outlet ({'active' if active else why if recent is None else f'{recent} recent items'})"
        else:
            keep[n] = news[n]

    # by default nothing is removed: the threshold only decides new bots and URL changes
    for n in list(remove):
        reason = remove[n]
        if args.remove == "none" or (args.remove == "duplicates" and reason != "second bot of the outlet"):
            del remove[n]
            keep[n] = news[n]

    plats = finalize.platforms([c["url"] for c in cands.values()] + [b["feed"] for b in state["bots"].values()])
    nicks = finalize.assign_nicks(list(add.values()), set(state["bots"]), plats)
    new_bots = OrderedDict((nicks[u], {"feed": u}) for u in sorted(add.values(), key=lambda u: nicks[u]))
    final = OrderedDict()
    for n in sorted(set(keep) | set(change)):
        final[n] = {"feed": change[n]["to"] if n in change else keep[n]}
    final.update(new_bots)
    final = OrderedDict(sorted(final.items()))

    # sanity: every news bot is decided exactly once; no feed twice; nothing touches a non-news bot
    assert set(keep) | set(change) | set(remove) == set(news), "undecided news bots"
    assert not (set(keep) & set(remove)) and not (set(change) & set(remove)) and not (set(keep) & set(change))
    keys = [norm_key(b["feed"]) for b in final.values()]
    assert len(keys) == len(set(keys)), "a feed would run twice"
    assert not set(keys) & other_keys, "a new feed duplicates a non-news bot"
    assert not set(new_bots) & set(state["bots"])

    with open(os.path.join(WORK, "changes.json"), "w") as f:
        json.dump({"made": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "batches": mp["batches"],
                   "remove": remove, "change": change, "add": new_bots}, f, indent=1)
    with open(os.path.join(WORK, "news-active.json"), "w") as f:
        json.dump(final, f, indent=2)
        f.write("\n")
    with open(os.path.join(WORK, "selection.jsonl"), "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    report(args, news, mapping, stats, keep, change, new_bots, remove, final, rows, unmapped, unmapped_stats, results)
    print(f"news bots {len(news)} -> {len(final)}: keep {len(keep)}, change {len(change)}, add {len(new_bots)}, "
          f"remove {len(remove)}", file=sys.stderr)


def stored_url(url, results):
    r = results.get(norm_key(url))
    return finalize.stored_url(r) if r else url


def report(args, news, mapping, stats, keep, change, new_bots, remove, final, rows, unmapped, unmapped_stats, results):
    runs = []
    if os.path.exists(os.path.join(WORK, "validate-runs.jsonl")):
        with open(os.path.join(WORK, "validate-runs.jsonl")) as f:
            runs = [json.loads(l) for l in f]
    status = Counter()
    for r in results.values():
        status[r.get("error") or f"http {r.get('status')}"] += 1
    how = Counter(m["how"] if m["outlet"] else "unmapped: " + m["how"] for m in mapping.values())
    L = []
    w = L.append
    w("# News cleanup: one active feed per Media Cloud outlet\n")
    w(f"Settings: >= {args.min_recent} items in 7 days, removals: {args.remove}, "
      f"{'most active feed wins' if args.prefer_best else 'an active live feed is kept'}, unmapped bots: {args.unmapped}.\n")
    w(f"- Live news bots: **{len(news)}** → after the cleanup **{len(final)}**")
    w(f"- Kept unchanged: **{len(keep)}** (of them {sum(1 for n in keep if not mapping[n]['outlet'])} without a "
      "current Media Cloud outlet)")
    w(f"- Feed URL changes (nick kept): **{len(change)}**")
    w(f"- New bots (active outlets without a news bot): **{len(new_bots)}**")
    w(f"- Removed: **{len(remove)}**")
    for why, n in Counter(v.split(" (")[0] for v in remove.values()).most_common():
        w(f"  - {why}: {n}")
    alt = sum(1 for r in rows if r["best_differs"])
    if not args.prefer_best:
        w(f"- Outlets where another feed is more active than the kept live one: {alt} (`--prefer-best` would change "
          "those URLs too)")
    w("")
    w("## Outlets\n")
    for a, n in stats.most_common():
        w(f"- {a}: {n}")
    w("")
    w("## How the live news bots were matched to outlets\n")
    for h, n in how.most_common():
        w(f"- {h}: {n}")
    w(f"\nUnmapped news bots ({len(unmapped)}): " + ", ".join(f"{k} {v}" for k, v in unmapped_stats.most_common()) + "\n")
    w("## Fetches\n")
    for k, n in status.most_common(12):
        w(f"- {k}: {n}")
    for r in runs:
        w(f"- run {r.get('mode')}: {r['fetched']} fetches in {finalize.fmt_wall(r['wall_seconds'])}, "
          f"started {r['started']}, concurrency {r['concurrency']}, pace {r.get('pace')}")
    w("")
    w("## Sample URL changes\n")
    for n in list(change)[:: max(1, len(change) // 15)][:15]:
        w(f"- `{n}`: {change[n]['from']} → {change[n]['to']}")
    w("")
    w("## Sample new bots\n")
    for n in list(new_bots)[:: max(1, len(new_bots) // 15)][:15]:
        w(f"- `{n}`: {new_bots[n]['feed']}")
    with open(os.path.join(WORK, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--news", nargs="+", default=[os.path.join(HERE, "imported", "2026-11-04-news.json")])
    s = sub.add_parser("select")
    s.add_argument("--min-recent", type=int, default=10)
    s.add_argument("--prefer-best", action="store_true")
    s.add_argument("--unmapped", choices=("keep", "active", "drop"), default="keep")
    s.add_argument("--remove", choices=("none", "duplicates", "all"), default="none",
                   help="which news bots to remove: none (default; the activity threshold only picks feeds for new "
                        "bots and URL changes), duplicates (second bots of an outlet), all (also inactive outlets)")
    args = ap.parse_args()
    prepare(args) if args.cmd == "prepare" else select(args)


if __name__ == "__main__":
    main()
