#!/usr/bin/env -S ./py
"""Media Cloud news outlets -> their feeds, for harvest.py (sources/mediacloud.txt) and select.py
(sources/mediacloud-feeds.json: outlet id -> feed URLs).

Outlets: the sources in Media Cloud's "<Country> - National" and "<Country> - State & Local" collections.
Feeds: Media Cloud's feed list without sitemaps and disabled feeds, up to FEEDS_PER_OUTLET per outlet with
site-wide feeds first; select.py later keeps each outlet's most active one.

Token: $MEDIACLOUD_TOKEN or ~/.config/mediacloud/token (free account at https://search.mediacloud.org).
"""
import json
import os
import re
import sys
import time
import urllib.parse
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


def get(url, auth):
    for attempt in range(5):
        request = urllib.request.Request(url, headers={"Authorization": f"Token {auth}", "User-Agent": "brockman-feed-harvest/1.0 (https://brockman.news)"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except Exception as e:
            print(f"retry {attempt + 1} {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"giving up on {url}")


def pages(path, auth, **params):
    url = f"{API}/{path}/?" + urllib.parse.urlencode({"limit": 1000, **params})
    while url:
        page = get(url, auth)
        yield from page["results"]
        url = page["next"]


def rank(feed_url):
    # lower is better: site-wide feeds before section feeds, shallow paths before deep ones, then shorter
    path = urllib.parse.urlparse(feed_url).path
    return (bool(SECTION.search(feed_url)), path.count("/"), len(feed_url))


def main():
    auth = token()
    collections = [c for c in pages("collections", auth, platform="online_news") if COUNTRY_COLLECTION.match(c["name"])]
    print(f"collections: {len(collections)}", file=sys.stderr)
    outlets = set()
    for c in collections:
        outlets.update(s["id"] for s in pages("sources", auth, collection_id=c["id"]))
    print(f"outlets: {len(outlets)}", file=sys.stderr)

    feeds = {}
    for n, feed in enumerate(pages("feeds", auth), 1):
        if feed["source"] in outlets and feed.get("admin_rss_enabled", True) and "sitemap" not in feed["url"].lower():
            feeds.setdefault(feed["source"], []).append(feed["url"].strip())
        if n % 20000 == 0:
            print(f"feeds read: {n}", file=sys.stderr)
    per_outlet = {str(source): sorted(set(urls), key=rank)[:FEEDS_PER_OUTLET] for source, urls in feeds.items()}
    print(f"outlets with a feed: {len(per_outlet)}, feeds kept: {sum(map(len, per_outlet.values()))}", file=sys.stderr)

    os.makedirs(os.path.join(HERE, "sources"), exist_ok=True)
    with open(os.path.join(HERE, "sources", "mediacloud-feeds.json"), "w") as f:
        json.dump(per_outlet, f, indent=0)
    with open(os.path.join(HERE, "sources", "mediacloud.txt"), "w") as f:
        f.write("\n".join(sorted(u for urls in per_outlet.values() for u in urls)) + "\n")


if __name__ == "__main__":
    main()
