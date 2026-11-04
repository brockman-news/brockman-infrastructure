"""Shared helpers: URL normalization for dedupe, host classification."""
from urllib.parse import urlsplit

import tldextract

# bundled public suffix snapshot only; never hit the network
EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def host_of(url: str) -> str:
    try:
        h = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return ""
    return h.lower().rstrip(".")


def norm_key(url: str) -> str:
    """Dedupe key: scheme-insensitive, lowercase host, no www., no trailing slash.
    Path/query keep their case."""
    url = url.strip()
    try:
        s = urlsplit(url)
        host = (s.hostname or "").lower().rstrip(".")
        port = s.port
    except ValueError:
        return url.lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if port and not ((s.scheme == "http" and port == 80) or (s.scheme == "https" and port == 443)):
        netloc += f":{port}"
    rest = s.path
    if s.query:
        rest += "?" + s.query
    rest = rest.rstrip("/")
    return netloc + rest


def is_youtube(url: str) -> bool:
    h = host_of(url)
    return h in ("youtube.com", "youtu.be") or h.endswith(".youtube.com") or h.endswith(".youtu.be")


def registered_domain(host: str) -> str:
    """eTLD+1 (e.g. alice.substack.com -> substack.com, x.blogspot.com -> x.blogspot.com)."""
    e = EXTRACT(host)
    return e.top_domain_under_public_suffix or host
