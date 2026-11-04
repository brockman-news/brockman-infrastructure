#!/usr/bin/env -S ./py
"""Fetch every candidate and classify it with feedparser.

Reads candidates.json, appends one JSON object per candidate to results.jsonl
(resumable: already-recorded keys are skipped; the latest line per key wins).
Bodies of HTTP 200 responses are stored in bodies/<sha1(key)> for the
brockman-parser pass (feedcheck).

`--refetch-status 429 --concurrency 2 --pace 2` re-fetches rate-limited
candidates slowly: shared hosters (DreamHost) answer 429 to *all* their
customers' sites once the full-speed pass has hit them from one IP.
"""
import argparse
import asyncio
import hashlib
import json
import os
import random
import socket
import ssl
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

import aiohttp

from common import host_of, registered_domain

HERE = os.path.dirname(os.path.abspath(__file__))
BODIES = os.path.join(HERE, "bodies")
RESULTS = os.path.join(HERE, "results.jsonl")

CONCURRENCY = 200
PER_HOST = 4  # keyed by registered domain, so *.substack.com etc. share one limit
PER_IP = 2  # keyed by first IPv4 address: custom-domain hosters (bearblog's domain proxy) tarpit bursts
TIMEOUT = 30
MAX_BODY = 20 * 1024 * 1024
HEADERS = {
    "User-Agent": "brockman/1.0 (+https://brockman.news)",
    "Accept": "application/atom+xml, application/rss+xml, */*",
}


def classify_body(path, content_type, url):
    """feedparser verdict for a stored body (runs in a worker process)."""
    import feedparser

    with open(path, "rb") as f:
        body = f.read()
    head = body[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    out = {"looks_json": head.startswith(b"{") or head.startswith(b"["),
           "looks_html": head.startswith(b"<!doctype html") or head.startswith(b"<html")}
    d = feedparser.parse(body, response_headers={"content-type": content_type or "", "content-location": url})
    entries = d.get("entries", [])
    usable = 0
    for e in entries:
        if (e.get("title") or "").strip() and (e.get("link") or "").strip():
            usable += 1
    out.update({
        "fp_version": d.get("version", ""),
        "fp_bozo": bool(d.get("bozo")),
        "fp_bozo_exc": type(d.get("bozo_exception")).__name__ if d.get("bozo") else None,
        "fp_bozo_msg": str(d.get("bozo_exception"))[:200] if d.get("bozo") else None,
        "fp_entries": len(entries),
        "fp_usable": usable,
        "fp_title": (d.get("feed", {}).get("title") or "")[:200],
    })
    return out


def err_bucket(exc):
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    dns_cls = getattr(aiohttp, "ClientConnectorDNSError", ())
    if dns_cls and isinstance(exc, dns_cls):
        return "dns"
    if isinstance(exc, (aiohttp.ClientConnectorCertificateError, aiohttp.ClientConnectorSSLError, ssl.SSLError)):
        return "tls"
    if isinstance(exc, aiohttp.ClientConnectorError):
        if isinstance(exc.os_error, socket.gaierror):
            return "dns"
        return "connect"
    if isinstance(exc, aiohttp.TooManyRedirects):
        return "redirects"
    if isinstance(exc, (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError, aiohttp.ClientPayloadError,
                        ConnectionError)):
        return "connect"
    if isinstance(exc, (aiohttp.InvalidURL, ValueError)):
        return "invalid_url"
    if isinstance(exc, aiohttp.ClientResponseError):
        return "protocol"
    return "other"


RETRYABLE = {"timeout", "connect", "dns", "other"}


class Validator:
    def __init__(self, todo, mode="full", concurrency=CONCURRENCY, pace=0.0, retry_status=(), per_ip=PER_IP):
        self.todo = todo
        self.mode = mode
        self.concurrency = concurrency
        self.pace = pace  # seconds to keep a slot after each request (slow retry passes)
        self.retry_status = set(retry_status)  # HTTP statuses worth one more try after Retry-After
        self.gsem = asyncio.Semaphore(concurrency)
        self.hsems = defaultdict(lambda: asyncio.Semaphore(PER_HOST))
        self.per_ip = per_ip
        self.isems = defaultdict(lambda: asyncio.Semaphore(per_ip))
        self.dns_sem = asyncio.Semaphore(100)
        self.ipcache = {}
        self.resolver = None
        self.pool = ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) - 2))
        self.out = open(RESULTS, "a")
        self.stats = Counter()
        self.n = 0

    async def fetch_once(self, session, url, dest):
        t0 = time.monotonic()
        async with session.get(url, headers=HEADERS, allow_redirects=True, max_redirects=10) as r:
            size = 0
            with open(dest + ".part", "wb") as f:
                async for chunk in r.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > MAX_BODY:
                        raise ValueError("body too large")
                    f.write(chunk)
            return {
                "status": r.status,
                "final_url": str(r.url),
                "content_type": r.headers.get("Content-Type", ""),
                "size": size,
                "elapsed": round(time.monotonic() - t0, 2),
                "redirects": [str(h.url) for h in r.history],
                "retry_after": r.headers.get("Retry-After"),
            }

    async def _resolve(self, host):
        async with self.dns_sem:
            try:
                infos = await asyncio.wait_for(self.resolver.resolve(host, 443, socket.AF_INET), 15)
                return infos[0]["host"]
            except Exception:  # noqa: BLE001 - the fetch itself reports DNS failures
                return "unresolved:" + host

    async def ip_key(self, host):
        if host not in self.ipcache:
            self.ipcache[host] = asyncio.ensure_future(self._resolve(host))
        return await self.ipcache[host]

    async def one(self, session, c):
        url, key = c["url"], c["key"]
        dest = os.path.join(BODIES, hashlib.sha1(key.encode()).hexdigest())
        rec = {"key": key, "url": url}
        host = host_of(url)
        hsem = self.hsems[registered_domain(host)]
        ip = await self.ip_key(host)
        rec["ip"] = ip
        isem = self.isems[ip]
        for attempt in (1, 2):
            rec["attempts"] = attempt
            retry_wait = None
            async with hsem, isem, self.gsem:
                try:
                    res = await asyncio.wait_for(self.fetch_once(session, url, dest), TIMEOUT + 5)
                    rec.update(res)
                    rec.pop("error", None)
                    rec.pop("error_detail", None)
                    if res["status"] in self.retry_status:
                        ra = res.get("retry_after") or ""
                        retry_wait = min(int(ra), 120) if ra.isdigit() else 60
                except Exception as e:  # noqa: BLE001 - every failure is a data point
                    b = err_bucket(e)
                    if isinstance(e, ValueError) and "too large" in str(e):
                        b = "too_large"
                    rec["error"] = b
                    rec["error_detail"] = f"{type(e).__name__}: {e}"[:300]
                    if b in RETRYABLE:
                        retry_wait = 3 + random.random() * 5
                if self.pace:
                    await asyncio.sleep(self.pace)
            if retry_wait is None or attempt == 2:
                break
            await asyncio.sleep(retry_wait)
        if os.path.exists(dest + ".part"):
            if rec.get("status") == 200 and "error" not in rec:
                os.replace(dest + ".part", dest)
                rec["body"] = os.path.basename(dest)
                loop = asyncio.get_running_loop()
                try:
                    rec.update(await loop.run_in_executor(self.pool, classify_body, dest,
                                                          rec["content_type"], rec["final_url"]))
                except Exception as e:  # noqa: BLE001
                    rec["fp_error"] = f"{type(e).__name__}: {e}"[:300]
            else:
                os.remove(dest + ".part")
        self.out.write(json.dumps(rec) + "\n")
        self.n += 1
        self.stats[rec.get("error") or f"http_{rec.get('status')}"] += 1
        self.out.flush()  # killed runs keep what they fetched

    async def progress(self, total, t0):
        while True:
            await asyncio.sleep(30)
            print(f"[{time.monotonic() - t0:7.0f}s] {self.n}/{total} {dict(self.stats.most_common(8))}",
                  file=sys.stderr, flush=True)

    async def run(self):
        todo = list(self.todo)
        random.Random(42).shuffle(todo)  # spread hosts over time
        print(f"{self.mode}: {len(todo)} to fetch", file=sys.stderr, flush=True)
        t0 = time.monotonic()
        self.resolver = aiohttp.AsyncResolver()
        # force_close: no idle keep-alive sockets. Almost every URL is a different host, so reuse buys nothing,
        # and lingering sockets exhaust per-client connection limits of shared front ends (bearblog's proxy).
        connector = aiohttp.TCPConnector(limit=self.concurrency, limit_per_host=0, ttl_dns_cache=600,
                                         force_close=True, resolver=aiohttp.AsyncResolver())
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        prog = asyncio.create_task(self.progress(len(todo), t0))
        # cookies only matter across redirects of one fetch (like http-client); jar is domain-scoped
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            await asyncio.gather(*(self.one(session, c) for c in todo))
        prog.cancel()
        self.out.close()
        wall = time.monotonic() - t0
        print(f"done: {len(todo)} in {wall:.0f}s", file=sys.stderr, flush=True)
        with open(os.path.join(HERE, "validate-runs.jsonl"), "a") as f:
            f.write(json.dumps({"mode": self.mode,
                                "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - wall)),
                                "fetched": len(todo), "wall_seconds": round(wall, 1),
                                "concurrency": self.concurrency, "per_host": PER_HOST, "per_ip": self.per_ip,
                                "pace": self.pace,
                                "retry_status": sorted(self.retry_status)}) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N candidates (test runs)")
    ap.add_argument("--refetch-status", help="comma-separated HTTP statuses: re-fetch candidates whose latest "
                                             "result has one of them (slow pass for shared-host rate limits)")
    ap.add_argument("--refetch-error", help="comma-separated error buckets (timeout,dns,connect,...): re-fetch "
                                            "candidates whose latest result failed that way")
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    ap.add_argument("--pace", type=float, default=0.0, help="seconds each request keeps its slots afterwards")
    ap.add_argument("--per-ip", type=int, default=PER_IP)
    args = ap.parse_args()

    os.makedirs(BODIES, exist_ok=True)
    with open(os.path.join(HERE, "candidates.json")) as f:
        cands = json.load(f)
    if args.limit:
        cands = cands[: args.limit]
    latest = {}
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                    latest[r["key"]] = r
                except (ValueError, KeyError):
                    pass
    kw = {"concurrency": args.concurrency, "pace": args.pace, "per_ip": args.per_ip}
    if args.refetch_status:
        statuses = {int(s) for s in args.refetch_status.split(",")}
        todo = [c for c in cands if (r := latest.get(c["key"])) and "error" not in r and r.get("status") in statuses]
        v = Validator(todo, mode=f"refetch status {sorted(statuses)}", retry_status=statuses, **kw)
    elif args.refetch_error:
        errors = set(args.refetch_error.split(","))
        todo = [c for c in cands if latest.get(c["key"], {}).get("error") in errors]
        v = Validator(todo, mode=f"refetch error {sorted(errors)}", **kw)
    else:  # resumable: skip candidates that already have a result
        todo = [c for c in cands if c["key"] not in latest]
        v = Validator(todo, **kw)
    asyncio.run(v.run())


if __name__ == "__main__":
    main()
