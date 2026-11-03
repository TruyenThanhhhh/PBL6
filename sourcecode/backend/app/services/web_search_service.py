"""Small, optional DuckDuckGo web search adapter with bounded network timeouts."""
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from app.config import DUCKDUCKGO_API_URL, WEB_SEARCH_ENABLED, WEB_SEARCH_TIMEOUT


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


async def search_web(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not WEB_SEARCH_ENABLED or not query.strip():
        return []
    try:
        url = DUCKDUCKGO_API_URL
        if "?" not in url:
            url += "?"
        async with httpx.AsyncClient(timeout=WEB_SEARCH_TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": "PBL6-Knowledge-Platform/0.1"}) as client:
            response = await client.get("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
            response.raise_for_status()
            parser = _ResultParser()
            parser.feed(response.text)
            if parser.results:
                return [
                    {"source_type": "web", "title": item["title"].strip(), "url": item["url"],
                     "snippet": item.get("snippet", "").strip() or item["title"].strip(), "ref_id": index}
                    for index, item in enumerate(parser.results[:limit], start=1)
                ]

            # Instant-answer API fallback, useful when the HTML endpoint has no results.
            answer = await client.get(url, params={"q": query, "format": "json", "no_html": 1,
                                                    "skip_disambig": 1})
            answer.raise_for_status()
            payload = answer.json()
            text = payload.get("AbstractText") or payload.get("Answer") or ""
            if text:
                return [{"source_type": "web", "title": payload.get("Heading") or query,
                         "url": payload.get("AbstractURL") or "", "snippet": text, "ref_id": 1}]
    except (httpx.HTTPError, ValueError):
        return []
    return []
