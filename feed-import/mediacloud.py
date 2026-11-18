#!/usr/bin/env -S ./py
"""Media Cloud news outlets -> their feeds, for harvest.py (sources/mediacloud.txt) and select_active.py
(sources/mediacloud-feeds.json: outlet id -> feed URLs; sources/mediacloud-outlets.json: outlet id -> name,
homepage, collections).

Outlets: the sources in Media Cloud's "<Country> - National" and "<Country> - State & Local" collections.
Feeds: Media Cloud's feed list without sitemaps and disabled feeds, up to FEEDS_PER_OUTLET per outlet with
site-wide feeds first; select_active.py later keeps each outlet's most active one.

Token: $MEDIACLOUD_TOKEN or ~/.config/mediacloud/token (free account at https://search.mediacloud.org).
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://search.mediacloud.org/api/sources"
COUNTRY_COLLECTION = re.compile(r"^[^,]+ - (National|State & Local)$")
SECTION = re.compile(r"/(tag|tags|category|categories|topic|topics|section|sections|author|authors|comments?)/|comments", re.I)
FEEDS_PER_OUTLET = 10


def token():
    if os.environ.get("MEDIACLOUD_TOKEN"):
        return os.environ["MEDIACLOUD_TOKEN"].strip()
    with open(os.path.expanduser("~/.config/mediacloud/token")) as f:
        return f.read().strip()


class OutOfRequests(Exception):
    pass


REQUESTS = 0
BUDGET = int(os.environ.get("MEDIACLOUD_BUDGET", "3000"))  # free accounts get 10000 requests per week


def get(url, auth):
    global REQUESTS
    for attempt in range(5):
        if REQUESTS >= BUDGET:
            raise OutOfRequests(f"request budget {BUDGET} used (MEDIACLOUD_BUDGET)")
        REQUESTS += 1
        request = urllib.request.Request(url, headers={"Authorization": f"Token {auth}", "User-Agent": "brockman-feed-harvest/1.0 (https://brockman.news)"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if "quota" in body.lower():  # retrying only burns more of it
                raise OutOfRequests(f"Media Cloud quota: {body[:200]}")
            print(f"retry {attempt + 1} {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            print(f"retry {attempt + 1} {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"giving up on {url}")


def pages(path, auth, **params):
    """All rows. Media Cloud's listings have no stable order (the same offset returns different rows on every
    call), so one pass over several pages repeats some rows and misses others: page through again, merging, until
    the distinct rows reach the API's count, or 3 passes in a row find nothing new (some collections hold an
    outlet twice, so their count is higher than their distinct outlets)."""
    rows, count, quiet = {}, None, 0
    for attempt in range(1, 31):
        before = len(rows)
        url = f"{API}/{path}/?" + urllib.parse.urlencode({"limit": 1000, **params})
        while url:
            page = get(url, auth)
            count = page["count"]
            for row in page["results"]:
                rows.setdefault(row["id"], row)
            url = page["next"]
        if len(rows) >= count or count <= 1000:  # a single page is complete
            return list(rows.values())
        quiet = quiet + 1 if len(rows) == before else 0
        if quiet == 3:
            print(f"{path} {params}: {len(rows)} distinct rows, API counts {count} (duplicates)", file=sys.stderr)
            return list(rows.values())
    raise SystemExit(f"{path} {params}: {len(rows)} distinct rows after {attempt} passes, API says {count}")


def rank(feed_url):
    # lower is better: site-wide feeds before section feeds, shallow paths before deep ones, then shorter
    path = urllib.parse.urlparse(feed_url).path
    return (bool(SECTION.search(feed_url)), path.count("/"), len(feed_url))


def read_feeds(auth, cache_path):
    """Feed rows by id, merged into cache_path across passes and runs (the listing is unordered, see pages()).
    Stops when the distinct rows reach the API's count, after 2 passes without new rows, or when the request
    budget / quota runs out (the cache keeps what was read; the next run continues)."""
    rows = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            rows = json.load(f)
    count, quiet, stop = None, 0, None
    for p in range(1, 31):
        before = len(rows)
        url = f"{API}/feeds/?limit=1000"
        try:
            while url:
                page = get(url, auth)
                count = page["count"]
                for r in page["results"]:
                    rows[str(r["id"])] = {k: r.get(k) for k in ("url", "source", "admin_rss_enabled")}
                url = page["next"]
        except OutOfRequests as e:
            stop = str(e)
        with open(cache_path + ".tmp", "w") as f:
            json.dump(rows, f)
        os.replace(cache_path + ".tmp", cache_path)
        print(f"feeds pass {p}: {len(rows)} distinct (+{len(rows) - before}) of {count}, {REQUESTS} requests",
              file=sys.stderr, flush=True)
        quiet = quiet + 1 if len(rows) == before else 0
        if stop or (count and len(rows) >= count) or quiet == 2:
            break
    return rows, count, stop


def main():
    auth = token()
    outlets_path = os.path.join(HERE, "sources", "mediacloud-outlets.json")
    if os.path.exists(outlets_path) and not os.environ.get("MEDIACLOUD_REFRESH_OUTLETS"):
        with open(outlets_path) as f:  # outlets barely change; re-reading them costs ~1000 requests
            meta = json.load(f)
        print(f"outlets: {len(meta)} (cached, MEDIACLOUD_REFRESH_OUTLETS=1 re-reads)", file=sys.stderr)
    else:
        collections = [c for c in pages("collections", auth, platform="online_news") if COUNTRY_COLLECTION.match(c["name"])]
        print(f"collections: {len(collections)}", file=sys.stderr)
        meta = {}
        for c in collections:
            for s in pages("sources", auth, collection_id=c["id"]):
                m = meta.setdefault(str(s["id"]), {"name": s.get("name"), "homepage": s.get("homepage"),
                                                   "label": s.get("label"), "collections": []})
                m["collections"].append(c["name"])
        print(f"outlets: {len(meta)}", file=sys.stderr)
        os.makedirs(os.path.dirname(outlets_path), exist_ok=True)
        with open(outlets_path, "w") as f:
            json.dump(meta, f, indent=0)

    rows, count, stop = read_feeds(auth, os.path.join(HERE, "sources", "mediacloud-feed-rows.json"))
    feeds = {}
    for r in rows.values():
        if str(r["source"]) in meta and r.get("admin_rss_enabled", True) and "sitemap" not in r["url"].lower():
            feeds.setdefault(r["source"], []).append(r["url"].strip())
    coverage = {"feed_rows": len(rows), "api_count": count, "complete": bool(count and len(rows) >= count),
                "stopped": stop, "requests": REQUESTS, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    print(f"coverage: {coverage}", file=sys.stderr)
    per_outlet = {str(source): sorted(set(urls), key=rank)[:FEEDS_PER_OUTLET] for source, urls in feeds.items()}
    print(f"outlets with a feed: {len(per_outlet)}, feeds kept: {sum(map(len, per_outlet.values()))}", file=sys.stderr)

    os.makedirs(os.path.join(HERE, "sources"), exist_ok=True)
    with open(os.path.join(HERE, "sources", "mediacloud-feeds.json"), "w") as f:
        json.dump(per_outlet, f, indent=0)
    with open(os.path.join(HERE, "sources", "mediacloud-coverage.json"), "w") as f:
        json.dump(coverage, f, indent=1)
    with open(os.path.join(HERE, "sources", "mediacloud.txt"), "w") as f:
        f.write("\n".join(sorted(u for urls in per_outlet.values() for u in urls)) + "\n")


if __name__ == "__main__":
    main()
