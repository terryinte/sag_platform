"""Polite homepage crawl used to draft project key contents.

Depth is at most 2 and stays on the same host. Failures return a reason
instead of raising, so the wizard can show a toast and keep manual rows.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

_MAX_BYTES = 500_000
_MAX_PAGES = 4
_PREFERRED = re.compile(r"product|about|solution|pricing|feature|company|products|关于|产品|解决", re.I)
_SKIP_EXT = re.compile(r"\.(pdf|jpg|jpeg|png|gif|webp|zip|mp4|css|js)(\?|$)", re.I)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.meta_description = ""
        self.links: list[str] = []
        self.paragraphs: list[str] = []
        self._skip = 0
        self._current: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "p"}:
            self._current = tag
            self._buf = []
        if tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.meta_description:
                self.meta_description = _clean(attr.get("content") or "")
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
            return
        if tag == "title":
            self.in_title = False
        if tag == self._current:
            text = _clean("".join(self._buf))
            if text:
                if tag == "h1":
                    self.h1.append(text)
                elif tag == "h2":
                    self.h2.append(text)
                else:
                    self.paragraphs.append(text)
            self._current = None
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self._current:
            self._buf.append(data)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_page(html: str, url: str = "") -> dict:
    parser = _PageParser()
    parser.feed(html or "")
    parser.close()
    title = _clean("".join(parser.title_parts))
    snippets = parser.paragraphs[:4]
    return {
        "url": url,
        "title": title[:180],
        "h1": parser.h1[:4],
        "h2": parser.h2[:8],
        "meta_description": parser.meta_description[:300],
        "snippets": [item[:240] for item in snippets],
        "links": parser.links,
    }


def _normalize(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("请填写官网地址")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("官网地址需要是 http 或 https")
    path = parsed.path or "/"
    return parsed._replace(path=path, params="", query=parsed.query, fragment="").geturl()


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _same_host(candidate: str, home: str) -> str:
    joined = urljoin(home, candidate)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if _host(joined) != _host(home):
        return ""
    if _SKIP_EXT.search(parsed.path or ""):
        return ""
    return parsed._replace(fragment="").geturl()


def _choose_links(links: list[str], home: str, seen: set[str]) -> list[str]:
    absolute = []
    for href in links:
        target = _same_host(href, home)
        if not target or target.rstrip("/") == home.rstrip("/") or target in seen:
            continue
        absolute.append(target)
    preferred = [item for item in absolute if _PREFERRED.search(urlparse(item).path)]
    ordered = preferred or absolute
    unique = []
    for item in ordered:
        if item not in unique:
            unique.append(item)
    return unique[:3]


def _items_from_page(page: dict) -> list[dict]:
    items = []
    title = page.get("title") or (page.get("h1") or [""])[0]
    meta = page.get("meta_description") or ""
    snippets = " ".join(page.get("snippets") or [])
    if title:
        items.append(
            {
                "kind": "产品线",
                "title": title[:80],
                "body": (meta or (page.get("h1") or [""])[0] or snippets)[:400],
                "source": "site_crawl",
            }
        )
    for heading in page.get("h2") or []:
        items.append({"kind": "卖点", "title": heading[:80], "body": snippets[:400], "source": "site_crawl"})
    if meta and meta != (items[0]["body"] if items else ""):
        items.append({"kind": "参数", "title": meta[:40], "body": meta[:400], "source": "site_crawl"})
    elif snippets and not (page.get("h2") or []):
        items.append({"kind": "参数", "title": (snippets[:24] or "页面摘要"), "body": snippets[:400], "source": "site_crawl"})
    deduped = []
    seen = set()
    for item in items:
        key = (item["kind"], item["title"])
        if not item["title"] or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:8]


def _default_fetcher(url: str, timeout: float) -> tuple[int, bytes]:
    headers = {"User-Agent": "SAG-GEO-SiteCrawl/1.0", "Accept": "text/html"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        body = response.content[:_MAX_BYTES]
        return response.status_code, body


def crawl_site(url: str, *, fetcher=None, timeout: float = 12.0, max_pages: int = _MAX_PAGES) -> dict:
    try:
        home = _normalize(url)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "items": [], "pages": []}
    fetch = fetcher or _default_fetcher
    queue: list[tuple[str, int]] = [(home, 1)]
    seen: set[str] = set()
    pages: list[dict] = []
    error = ""
    while queue and len(pages) < max_pages:
        current, depth = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        try:
            status, body = fetch(current, timeout)
        except Exception as exc:
            reason = "抓取超时" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else f"抓取失败：{type(exc).__name__}"
            if not pages:
                return {"ok": False, "error": reason, "items": [], "pages": []}
            error = reason
            continue
        if status in {401, 403}:
            if not pages:
                return {"ok": False, "error": f"官网返回 {status}，需要登录或拒绝了访问", "items": [], "pages": []}
            continue
        if status >= 400:
            if not pages:
                return {"ok": False, "error": f"官网返回 {status}", "items": [], "pages": []}
            continue
        try:
            html = body.decode("utf-8", errors="replace")
        except Exception:
            html = ""
        parsed = parse_page(html, current)
        pages.append(parsed)
        if depth < 2:
            for link in _choose_links(parsed["links"], home, seen):
                queue.append((link, depth + 1))
    if not pages:
        return {"ok": False, "error": error or "没有抓到页面", "items": [], "pages": []}
    items: list[dict] = []
    seen_items: set[tuple[str, str]] = set()
    for page in pages:
        for item in _items_from_page(page):
            key = (item["kind"], item["title"])
            if key in seen_items:
                continue
            seen_items.add(key)
            items.append(item)
    return {"ok": True, "error": error, "items": items[:12], "pages": [{"url": page["url"], "title": page["title"]} for page in pages]}


def upsert_site_contents(db, project_id: int, items: list[dict]) -> dict:
    """Insert or refresh site_crawl rows. Manual rows with the same title stay."""
    existing = db.fetch_all(
        "SELECT * FROM project_key_contents WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    created = 0
    updated = 0
    kept_manual = 0
    for item in items:
        match = next(
            (row for row in existing if row["kind"] == item["kind"] and row["title"] == item["title"]),
            None,
        )
        if match is None:
            record_id = db.execute(
                """
                INSERT INTO project_key_contents (project_id, kind, title, body, confirmed, source)
                VALUES (?, ?, ?, ?, 0, 'site_crawl')
                """,
                (project_id, item["kind"], item["title"], item.get("body") or ""),
            )
            existing.append({"id": record_id, "kind": item["kind"], "title": item["title"], "source": "site_crawl", "body": item.get("body") or ""})
            created += 1
            continue
        if (match.get("source") or "manual") != "site_crawl":
            kept_manual += 1
            continue
        db.execute(
            "UPDATE project_key_contents SET body = ?, source = 'site_crawl' WHERE id = ?",
            (item.get("body") or "", match["id"]),
        )
        updated += 1
    return {"created": created, "updated": updated, "kept_manual": kept_manual}


def crawl_project_site(db, project_id: int, url: str) -> dict:
    result = crawl_site(url)
    if not result["ok"]:
        return {**result, "created": 0, "updated": 0, "kept_manual": 0}
    saved = upsert_site_contents(db, project_id, result["items"])
    return {**result, **saved}
