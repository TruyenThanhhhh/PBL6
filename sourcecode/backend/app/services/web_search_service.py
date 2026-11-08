"""Small, optional DuckDuckGo web search adapter with bounded network timeouts and SQLite caching."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from app.config import DUCKDUCKGO_API_URL, WEB_SEARCH_ENABLED, WEB_SEARCH_TIMEOUT
from app.database import get_db_connection


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._active: Optional[Dict[str, str]] = None
        self._capture = False
        self._snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._active = {"title": "", "url": attrs.get("href", "")}
            self._capture = True
        elif self._active and "result__snippet" in classes:
            self._snippet = True

    def handle_data(self, data):
        if self._active:
            if self._capture:
                self._active["title"] += data
            elif self._snippet:
                self._active["snippet"] = self._active.get("snippet", "") + data

    def handle_endtag(self, tag):
        if tag == "a" and self._active and self._capture:
            self._capture = False
            if self._active.get("title") and self._active.get("url"):
                self.results.append(self._active)
        if tag in ("a", "div") and self._snippet:
            self._snippet = False


def _get_cached_results(query_hash: str) -> Optional[List[Dict[str, Any]]]:
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT results_json, expires_at FROM web_search_cache WHERE query_hash = ?",
            (query_hash,),
        ).fetchone()
        if not row:
            return None
        now_iso = datetime.now(timezone.utc).isoformat()
        if row["expires_at"] and row["expires_at"] < now_iso:
            conn.execute("DELETE FROM web_search_cache WHERE query_hash = ?", (query_hash,))
            conn.commit()
            return None
        return json.loads(row["results_json"])
    except Exception:
        return None
    finally:
        conn.close()


def _save_cached_results(query_hash: str, query: str, results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    conn = get_db_connection()
    try:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        conn.execute(
            """
            INSERT INTO web_search_cache (query_hash, query, results_json, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(query_hash) DO UPDATE SET
                results_json = excluded.results_json,
                expires_at = excluded.expires_at,
                created_at = CURRENT_TIMESTAMP
            """,
            (query_hash, query, json.dumps(results, ensure_ascii=False), expires_at),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


async def search_web(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not WEB_SEARCH_ENABLED or not query.strip():
        return []
    normalized = " ".join(query.strip().lower().split())
    query_hash = hashlib.md5(f"{normalized}:{limit}".encode("utf-8")).hexdigest()
    cached = _get_cached_results(query_hash)
    if cached is not None:
        return cached

    try:
        url = DUCKDUCKGO_API_URL
        if "?" not in url:
            url += "?"
        async with httpx.AsyncClient(
            timeout=WEB_SEARCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "PBL6-Knowledge-Platform/0.2"},
        ) as client:
            response = await client.get("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
            response.raise_for_status()
            parser = _ResultParser()
            parser.feed(response.text)
            if parser.results:
                results = [
                    {
                        "source_type": "web",
                        "title": item["title"].strip(),
                        "url": item["url"],
                        "snippet": item.get("snippet", "").strip() or item["title"].strip(),
                        "ref_id": index,
                    }
                    for index, item in enumerate(parser.results[:limit], start=1)
                ]
                _save_cached_results(query_hash, query.strip(), results)
                return results

            # Instant-answer API fallback, useful when the HTML endpoint has no results.
            answer = await client.get(
                url,
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            answer.raise_for_status()
            payload = answer.json()
            text = payload.get("AbstractText") or payload.get("Answer") or ""
            if text:
                results = [{
                    "source_type": "web",
                    "title": payload.get("Heading") or query,
                    "url": payload.get("AbstractURL") or "",
                    "snippet": text,
                    "ref_id": 1,
                }]
                _save_cached_results(query_hash, query.strip(), results)
                return results
    except (httpx.HTTPError, ValueError):
        return []
    return []
