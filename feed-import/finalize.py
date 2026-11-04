#!/usr/bin/env -S ./py
"""Join fetch results with the brockman-parser pass, pick accepted feeds,
generate nicks, write new-bots.json + report.md (spot-check section is
appended by spotcheck.py)."""
import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlsplit

from common import EXTRACT, host_of, norm_key, registered_domain

HERE = os.path.dirname(os.path.abspath(__file__))
BODIES = os.path.join(HERE, "bodies")
FEEDCHECK = os.path.join(HERE, "feedcheck.tsv")

NICK_RE = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")
GENERIC_SUB = {"www", "www1", "www2", "m", "blog", "blogs", "feed", "feeds", "rss", "atom"}
GENERIC_PATH = {"feed", "feeds", "rss", "rss2", "atom", "index", "default", "posts", "xml", "syndication",
                "blog", "en", "rss20", "atom10", "all", "export", "main"}
FEED_KINDS = {"atom", "rss", "rss1"}
PLATFORM_MIN = 10

DUP = "duplicate content"
UNFINISHED = "unfinished"
BUCKETS = ["dns/connect", "timeout", "http status", "not a feed / parse", "no usable items", DUP, UNFINISHED]


# ---------------------------------------------------------------- acceptance
def run_feedcheck(results):
    """Run the brockman parser (feedcheck binary) over all stored bodies."""
    want = sorted({r["body"] for r in results if r.get("body")})
    have = {}
    if os.path.exists(FEEDCHECK):
        with open(FEEDCHECK) as f:
            for ln in f:
                p = ln.rstrip("\n").split("\t")
                have[os.path.basename(p[0])] = p
    missing = [b for b in want if b not in have]
    if missing:
        print(f"feedcheck: {len(missing)} bodies", file=sys.stderr)

        def chunk(names):
            return subprocess.run([os.path.join(HERE, "feedcheck"), "+RTS", "-M2g", "-RTS"],
                                  input="\n".join(os.path.join(BODIES, b) for b in names) + "\n",
                                  capture_output=True, text=True, check=True).stdout

        chunks = [missing[i:i + 500] for i in range(0, len(missing), 500)]
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex, open(FEEDCHECK, "a") as f:
            for out in ex.map(chunk, chunks):
                f.write(out)
                for ln in out.splitlines():
                    p = ln.split("\t")
                    have[os.path.basename(p[0])] = p
    return have


def verdict(r, fc):
    """(bucket or None if accepted, detail)"""
    if r.get("error"):
        e = r["error"]
        if e == "timeout":
            return "timeout", "timeout"
        if e == "too_large":
            return "not a feed / parse", "body > 20 MiB"
        return "dns/connect", e
    if r.get("status") != 200:
        return "http status", f"http {r.get('status')}"
    if r.get("fp_error"):
        return "not a feed / parse", "feedparser crashed"
    if r.get("looks_json") or (r.get("fp_version") or "").startswith("json"):
        return "not a feed / parse", "json"
    v = r.get("fp_version") or ""
    if not (v.startswith("rss") or v.startswith("atom")):
        return "not a feed / parse", "html" if r.get("looks_html") else f"not rss/atom ({v or 'unknown'})"
    if r.get("fp_bozo") and r.get("fp_entries", 0) == 0:
        return "not a feed / parse", f"feedparser bozo, no entries ({r.get('fp_bozo_exc')})"
    p = fc.get(r["body"])
    if p is None:
        return "not a feed / parse", "brockman parser: no result"
    kind, strict = p[1], int(p[4])
    if kind not in FEED_KINDS:
        return "not a feed / parse", f"brockman parser: {kind}"
    if r.get("fp_usable", 0) == 0:
        return "no usable items", "feedparser: no item with title+link"
    if strict == 0:
        return "no usable items", "brockman parser: no item with title+link"
    return None, kind


def stored_url(r):
    """Source URL, except http:// that lands on the same host+path via https://."""
    url, final = r["url"], r.get("final_url") or ""
    a, b = urlsplit(url), urlsplit(final)
    if (a.scheme.lower() == "http" and b.scheme.lower() == "https"
            and (a.hostname or "").lower() == (b.hostname or "").lower()
            and (b.port in (None, 443)) and a.path == b.path and a.query == b.query):
        return "https" + url[len(a.scheme):]
    return url


def same_content(passing, fc):
    """Feeds that carry the same items as another new feed (e.g. a blog's /atom.xml
    and /rss.xml both listed). Returns {dropped_key: kept_key}.
    Same host: one link set is a subset of the other (>= 3 links, or equal).
    Any host: identical link sets with >= 3 links (feedburner mirrors etc.)."""
    links = {}
    for k, r in passing.items():
        p = fc[r["body"]]
        links[k] = frozenset(norm_key(l) for l in (p[5].split() if len(p) > 5 else []))

    def pref(k):  # keep: https, more items, shorter URL
        r = passing[k]
        return (not r["store"].lower().startswith("https"), -len(links[k]), len(r["store"]), r["store"])

    dup = {}
    by_host = defaultdict(list)
    for k in passing:
        by_host[norm_key(passing[k]["url"]).split("/")[0]].append(k)
    for ks in by_host.values():
        ks.sort(key=pref)
        for i, a in enumerate(ks):
            if a in dup:
                continue
            for b in ks[i + 1:]:
                if b in dup:
                    continue
                sa, sb = links[a], links[b]
                small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
                if small and (small == big or (len(small) >= 3 and small <= big)):
                    dup[b] = a
    by_set = defaultdict(list)
    for k, s in links.items():
        if len(s) >= 3 and k not in dup:
            by_set[s].append(k)
    for ks in by_set.values():
        ks.sort(key=pref)
        for b in ks[1:]:
            dup[b] = ks[0]
    return dup


# ---------------------------------------------------------------- nicks
def sanitize(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    return s


def as_nick(s):
    s = sanitize(s)
    if s and s[0].isdigit():
        s = "f_" + s
    return clip(s)

def clip(s, n=30):
    return s[:n].rstrip("_-")



def path_slug(url):
    sp = urlsplit(url)
    segs = []
    for seg in unquote(sp.path).split("/"):
        seg = re.sub(r"\.(xml|rss|atom|php|html?|aspx?|cms|jsp|json)$", "", seg, flags=re.I)
        if seg and seg.lower() not in GENERIC_PATH:
            segs.append(seg)
    if not segs and sp.query:
        vals = [v for kv in sp.query.split("&") for v in kv.split("=")[1:2]]
        segs = [v for v in vals if v and v.lower() not in GENERIC_PATH]
    return sanitize("_".join(segs[-2:]))


def host_parts(url):
    host = host_of(url)
    try:
        host = host.encode("idna").decode() if not host.isascii() else host
    except UnicodeError:
        pass
    e = EXTRACT(host)
    subs = [l for l in e.subdomain.split(".") if l and l not in GENERIC_SUB]
    domain = e.domain or host
    return host, subs, domain, e.suffix


def platforms(urls):
    """Registered domains hosting >= PLATFORM_MIN distinct sub-sites (substack, wordpress, ...)."""
    seen = defaultdict(set)
    for u in urls:
        host, subs, domain, suffix = host_parts(u)
        if subs:
            seen[registered_domain(host)].add(tuple(subs))
    return {d for d, s in seen.items() if len(s) >= PLATFORM_MIN}


def nick_options(url, plats):
    host, subs, domain, suffix = host_parts(url)
    suf = suffix.replace(".", "_")
    at = next((s for s in urlsplit(url).path.split("/") if s[:1] in ("@", "~") and len(s) > 1), None)
    if at:  # medium.com/@alice, mastodon.social/@bob
        base = [at[1:]]
        quals = [base + subs + [domain], base + subs + [domain, suf]]
    elif subs and registered_domain(host) in plats:  # alice.substack.com
        base = subs
        quals = [subs + [domain], subs + [domain, suf]]
    else:  # blog.example.com -> example
        base = [domain]
        quals = ([subs + [domain]] if subs else []) + [subs + [domain, suf]]
    opts = [base] + quals
    slug = path_slug(url)
    if slug:
        opts += [base + [slug]] + [q + [slug] for q in quals]
    out = []
    for o in opts:
        n = as_nick("_".join(o))
        if n and n not in out:
            out.append(n)
    if not out:
        out = ["feed"]
    return out


def assign_nicks(urls, taken, plats):
    taken = {t.lower() for t in taken}
    result = {}

    def order(u):
        host = host_of(u)
        sp = urlsplit(u)
        return (len(host.split(".")), len(host), host, len(sp.path + sp.query), u)

    for u in sorted(urls, key=order):
        opts = nick_options(u, plats)
        nick = next((o for o in opts if o not in taken), None)
        if nick is None:
            i = 2
            while True:
                sfx = f"_{i}"
                nick = clip(opts[0], 30 - len(sfx)) + sfx
                if nick not in taken:
                    break
                i += 1
        assert NICK_RE.match(nick), (u, nick)
        taken.add(nick)
        result[u] = nick
    return result


# ---------------------------------------------------------------- main
def main():
    with open(os.path.join(HERE, "candidates.json")) as f:
        cands = json.load(f)
    with open(os.path.join(HERE, "harvest-stats.json")) as f:
        hstats = json.load(f)
    results = {}
    with open(os.path.join(HERE, "results.jsonl")) as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except ValueError:  # torn last line of a killed run
                continue
            results[r["key"]] = r
    # never fetched (validation run stopped in its tail): second batch
    unfinished = [c["url"] for c in cands if c["key"] not in results]
    with open(os.path.join(HERE, "retry-unfinished.txt"), "w") as f:
        f.write("".join(u + "\n" for u in unfinished))
    hstats["unfinished"] = len(unfinished)
    fc = run_feedcheck(list(results.values()))

    with open("/tmp/brockman-state.json") as f:
        state = json.load(f)
    existing_nicks = set(state["bots"])
    existing_keys = {norm_key(b["feed"]) for b in state["bots"].values()}

    verdicts = {}
    passing = OrderedDict()  # key -> rec
    for c in cands:
        r = results.get(c["key"])
        verdicts[c["key"]] = verdict(r, fc) if r else (UNFINISHED, "not fetched (run stopped)")
        if r is None:
            continue
        if verdicts[c["key"]][0] is None:
            r["sources"] = c["sources"]
            r["store"] = stored_url(r)
            passing[c["key"]] = r
    dups = same_content(passing, fc)
    for k, kept in dups.items():
        verdicts[k] = (DUP, f"same items as another new feed")
        passing[k]["dup_of"] = passing[kept]["store"]

    accepted = OrderedDict((k, r) for k, r in passing.items() if k not in dups)
    per_source = defaultdict(Counter)
    totals = Counter()
    details = Counter()
    for c in cands:
        bucket, detail = verdicts[c["key"]]
        details[(bucket or "accepted", detail)] += 1
        totals[bucket or "accepted"] += 1
        for s in c["sources"]:
            per_source[s][bucket or "accepted"] += 1
    with open(os.path.join(HERE, "content-dupes.jsonl"), "w") as f:
        for k in dups:
            f.write(json.dumps({"dropped": passing[k]["store"], "kept": passing[k]["dup_of"]}) + "\n")
    # rate-limited (mostly DreamHost / Vercel challenge): validated later in a second batch
    retry429 = [c["url"] for c in cands if (r := results.get(c["key"])) and "error" not in r and r.get("status") == 429]
    with open(os.path.join(HERE, "retry-429.txt"), "w") as f:
        f.write("".join(u + "\n" for u in retry429))
    hstats["retry_429"] = len(retry429)

    plats = platforms([c["url"] for c in cands] + [b["feed"] for b in state["bots"].values()])
    nicks = assign_nicks([r["store"] for r in accepted.values()], existing_nicks, plats)
    bots = OrderedDict()
    for r in sorted(accepted.values(), key=lambda r: nicks[r["store"]]):
        n = nicks[r["store"]]
        assert norm_key(r["store"]) not in existing_keys
        bots[n] = {"feed": r["store"]}
        r["nick"] = n
    with open(os.path.join(HERE, "new-bots.json"), "w") as f:
        json.dump(bots, f, indent=2)
        f.write("\n")
    with open(os.path.join(HERE, "accepted.jsonl"), "w") as f:
        for r in accepted.values():
            f.write(json.dumps({k: r.get(k) for k in ("nick", "store", "url", "final_url", "sources",
                                                      "fp_title", "fp_version", "detail")}) + "\n")

    # sanity checks (acceptance criteria)
    lower = [k.lower() for k in bots]
    assert len(set(lower)) == len(lower)
    assert not set(lower) & {n.lower() for n in existing_nicks}
    assert all(NICK_RE.match(k) for k in bots)
    assert len({norm_key(b["feed"]) for b in bots.values()}) == len(bots)

    hstats["existing_bots"] = len(state["bots"])
    write_report(hstats, per_source, totals, details, accepted, bots, plats)
    print(f"accepted {len(bots)} / {len(cands)}", file=sys.stderr)


def fmt_wall(s):
    return f"{int(s // 3600)}h {int(s % 3600 // 60)}m {int(s % 60)}s" if s >= 3600 else f"{int(s // 60)}m {int(s % 60)}s"


def write_report(hstats, per_source, totals, details, accepted, bots, plats):
    runs = []
    if os.path.exists(os.path.join(HERE, "validate-runs.jsonl")):
        with open(os.path.join(HERE, "validate-runs.jsonl")) as f:
            runs = [json.loads(l) for l in f]
    src = hstats["sources"]

    def group(name):
        if name.startswith("awesome-rss-feeds/recommended"):
            return "awesome-rss-feeds (recommended/*.opml)"
        if name.startswith("awesome-rss-feeds/countries"):
            return "awesome-rss-feeds (countries/*.opml)"
        return name

    gstats = OrderedDict()
    gres = OrderedDict()
    for name, st in src.items():
        g = group(name)
        gstats.setdefault(g, Counter()).update(st)
        gres.setdefault(g, Counter()).update(per_source.get(name, Counter()))

    L = []
    w = L.append
    w("# brockman feed harvest report\n")
    w(f"Existing brockman bots: {hstats['existing_bots']} ({hstats['existing_feeds']} distinct normalized feed URLs, "
      "all candidates deduped against them).  ")
    w(f"Unique new candidates: **{hstats['unique_candidates']}**  ")
    w(f"Accepted (in `new-bots.json`): **{len(bots)}**  ")
    w(f"HTTP 429 (rate-limited, not re-fetched; listed in `retry-429.txt` for a second batch): "
      f"**{hstats['retry_429']}**  ")
    w(f"Unfinished (never got a result: the validation run was stopped in its slow tail; listed in "
      f"`retry-unfinished.txt` for a second batch): **{hstats['unfinished']}**\n")
    if runs:
        total = sum(x["wall_seconds"] for x in runs)
        w(f"Validation wall time: **{fmt_wall(total)}** ({round(total)} s) "
          "(30 s total timeout per attempt, one retry on timeout/connection/DNS errors):\n")
        for r in runs:
            what = r.get("mode", "full")
            extra = f", pace {r['pace']} s/request" if r.get("pace") else ""
            if r.get("retry_status"):
                extra += f", {r['retry_status']} retried once after Retry-After"
            w(f"- {what}: {fmt_wall(r['wall_seconds'])} ({r['wall_seconds']} s), {r['fetched']} fetches, started "
              f"{r['started']}, concurrency {r['concurrency']}, per registered domain {r['per_host']}, "
              f"per IP {r.get('per_ip', '-')}{extra}")
        w("")
    w("## Method\n")
    w("- Dedupe key: lowercase host, `www.` stripped, scheme ignored (http = https), trailing `/` stripped; "
      "path/query case kept. YouTube URLs (youtube.com, youtu.be) dropped.")
    w("- Fetch: GET, `User-Agent: brockman/1.0 (+https://brockman.news)`, "
      "`Accept: application/atom+xml, application/rss+xml, */*`, redirects followed, TLS verified, bodies capped at 20 MiB.")
    w("- Accept only if: final status 200; feedparser identifies RSS/Atom/RDF (JSON Feed and HTML rejected; "
      "bozo with zero entries rejected); feedparser finds >= 1 item with non-empty title and link; **and** the "
      "body passes brockman's own parser (`Text.Feed.Import.parseFeedSource` from the Haskell `feed` library, "
      "via `feedcheck.hs`) as Atom/RSS/RSS1 with >= 1 item that has a non-empty title and link (brockman's "
      "`feedToItems` rules, minus its `untitled` fallback).")
    w("- `duplicate content`: feeds that passed but carry the same items as another new feed (same host and one "
      "item-link set contains the other with >= 3 links or they are equal; or identical sets of >= 3 links on any "
      "host). The https / larger / shorter-URL one is kept; pairs are in `content-dupes.jsonl`.")
    w("- Stored URL = URL as listed, except `http://` sources that end on the same host+path over `https://` "
      "(stored as https).")
    w(f"- Nicks: host-derived; multi-tenant domains (>= {PLATFORM_MIN} distinct sub-sites in the lists, {len(plats)} found, "
      "e.g. substack.com, wordpress.com) use the sub-site label; `/@user` paths use the user. Collisions: add "
      "subdomain/domain label, then public suffix, then path slug, then `_N`.\n")

    w("## Counts per source\n")
    w("A URL listed by several sources is counted under each of them; the **unique** row counts each URL once. "
      "`candidates` = after dropping YouTube, invalid lines, duplicates within the source and duplicates of "
      "existing brockman feeds.\n")
    cols = ["listed", "youtube", "invalid", "dup in source", "dup existing", "candidates"] + BUCKETS + ["accepted"]
    w("| source | " + " | ".join(cols) + " |")
    w("|---" * (len(cols) + 1) + "|")

    def row(name, st, res):
        vals = [st.get("listed", ""), st.get("youtube", ""), st.get("invalid_url", ""),
                st.get("dup_within_source", ""), st.get("dup_existing", ""), st.get("candidates", "")]
        vals += [res.get(b, 0) for b in BUCKETS] + [res.get("accepted", 0)]
        w(f"| {name} | " + " | ".join(str(v) for v in vals) + " |")

    for g in gstats:
        row(g, gstats[g], gres[g])
    allst = Counter()
    for st in src.values():
        allst.update(st)
    u = {"listed": allst["listed"], "youtube": allst["youtube"], "invalid_url": allst["invalid_url"],
         "dup_within_source": allst["dup_within_source"], "dup_existing": allst["dup_existing"],
         "candidates": hstats["unique_candidates"]}
    row("**unique (all sources)**", u, totals)
    w("")

    w("## Failure reasons (unique candidates)\n")
    w("| bucket | detail | count |")
    w("|---|---|---|")
    for (b, d), n in sorted(details.items(), key=lambda x: (x[0][0] != "accepted", x[0][0], -x[1])):
        if b != "accepted":
            w(f"| {b} | {d} | {n} |")
    w("")
    w("Accepted by brockman-parser kind: " + ", ".join(
        f"{d}: {n}" for (b, d), n in sorted(details.items()) if b == "accepted") + "\n")

    w("## 20 random accepted samples\n")
    w("| nick | feed | title | source |")
    w("|---|---|---|---|")
    rng = random.Random(20261103)
    for r in rng.sample(list(accepted.values()), min(20, len(accepted))):
        t = (r.get("fp_title") or "").replace("|", "\\|").replace("\n", " ")[:60]
        w(f"| `{r['nick']}` | {r['store']} | {t} | {r['sources'][0]} |")
    w("")

    w("<details><summary>awesome-rss-feeds per OPML file</summary>\n")
    w("| file | listed | youtube | dup existing | candidates | accepted |")
    w("|---|---|---|---|---|---|")
    for name, st in src.items():
        if name.startswith("awesome-rss-feeds/"):
            w(f"| {name[len('awesome-rss-feeds/'):]} | {st['listed']} | {st['youtube']} | {st['dup_existing']} "
              f"| {st['candidates']} | {per_source[name].get('accepted', 0)} |")
    w("\n</details>\n")

    with open(os.path.join(HERE, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
