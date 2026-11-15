"""Small, optional DuckDuckGo web search adapter with bounded network timeouts,
real-time weather intelligence (wttr.in / Open-Meteo), deep web scraping (extracting
actual webpage articles), and SQLite caching.
"""
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import httpx

from app.config import DUCKDUCKGO_API_URL, WEB_SEARCH_ENABLED, WEB_SEARCH_TIMEOUT
from app.database import get_db_connection

logger = logging.getLogger(__name__)

# Từ điển dịch tình trạng thời tiết tiếng Anh sang tiếng Việt tự nhiên
WEATHER_DESC_MAP = {
    "sunny": "Trời nắng, quang đãng",
    "clear": "Trời quang đãng, không mây",
    "partly cloudy": "Có mây rải rác / trời nhiều mây",
    "cloudy": "Nhiều mây",
    "overcast": "U ám, nhiều mây",
    "mist": "Sương mù nhẹ",
    "fog": "Sương mù dày",
    "patchy rain nearby": "Có mưa rải rác / mưa nhỏ ngắt quãng",
    "patchy rain possible": "Có thể có mưa rải rác",
    "light rain": "Mưa nhỏ",
    "moderate rain": "Mưa vừa",
    "heavy rain": "Mưa to, mưa lớn",
    "light rain shower": "Mưa rào nhẹ",
    "moderate or heavy rain shower": "Mưa rào vừa đến to",
    "torrential rain shower": "Mưa rất to, mưa như trút nước",
    "thundery outbreaks nearby": "Có dông sét rải rác",
    "patchy light rain with thunder": "Mưa nhỏ kèm theo dông sét",
    "moderate or heavy rain with thunder": "Mưa vừa đến to kèm sấm sét",
}

WIND_DIR_MAP = {
    "N": "Bắc", "S": "Nam", "E": "Đông", "W": "Tây",
    "NE": "Đông Bắc", "SE": "Đông Nam", "NW": "Tây Bắc", "SW": "Tây Nam",
    "NNE": "Bắc Đông Bắc", "ENE": "Đông Đông Bắc",
    "ESE": "Đông Đông Nam", "SSE": "Nam Đông Nam",
    "SSW": "Nam Tây Nam", "WSW": "Tây Tây Nam",
    "WNW": "Tây Tây Bắc", "NNW": "Bắc Tây Bắc",
}

# Tọa độ và mã truy vấn các tỉnh thành Việt Nam
VIETNAM_LOCATIONS: Dict[str, Tuple[str, str, float, float]] = {
    "đà nẵng": ("Đà Nẵng", "Danang", 16.0678, 108.2208),
    "da nang": ("Đà Nẵng", "Danang", 16.0678, 108.2208),
    "hà nội": ("Hà Nội", "Hanoi", 21.0285, 105.8542),
    "ha noi": ("Hà Nội", "Hanoi", 21.0285, 105.8542),
    "hồ chí minh": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "ho chi minh": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "sài gòn": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "sai gon": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "tphcm": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "tp hcm": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "tp.hcm": ("TP. Hồ Chí Minh", "Ho Chi Minh City", 10.8231, 106.6297),
    "hải phòng": ("Hải Phòng", "Haiphong", 20.8449, 106.6881),
    "hai phong": ("Hải Phòng", "Haiphong", 20.8449, 106.6881),
    "cần thơ": ("Cần Thơ", "Cantho", 10.0452, 105.7469),
    "can tho": ("Cần Thơ", "Cantho", 10.0452, 105.7469),
    "nha trang": ("Nha Trang", "Nhatrang", 12.2388, 109.1967),
    "đà lạt": ("Đà Lạt", "Dalat", 11.9404, 108.4583),
    "da lat": ("Đà Lạt", "Dalat", 11.9404, 108.4583),
    "huế": ("Huế", "Hue", 16.4637, 107.5909),
    "hue": ("Huế", "Hue", 16.4637, 107.5909),
    "vũng tàu": ("Vũng Tàu", "Vungtau", 10.3460, 107.0843),
    "vung tau": ("Vũng Tàu", "Vungtau", 10.3460, 107.0843),
    "quy nhơn": ("Quy Nhơn", "Quynhon", 13.7830, 109.2197),
    "quy nhon": ("Quy Nhơn", "Quynhon", 13.7830, 109.2197),
    "quảng nam": ("Quảng Nam", "Tamky", 15.5684, 108.4800),
    "hội an": ("Hội An", "Hoian", 15.8801, 108.3380),
    "hạ long": ("Hạ Long", "Halong", 20.9505, 107.0734),
    "quảng ninh": ("Quảng Ninh", "Halong", 20.9505, 107.0734),
    "thanh hóa": ("Thanh Hóa", "Thanhhoa", 19.8067, 105.7852),
    "vinh": ("Vinh", "Vinh", 18.6734, 105.6813),
    "nghệ an": ("Nghệ An", "Vinh", 18.6734, 105.6813),
    "phú quốc": ("Phú Quốc", "Phuquoc", 10.2241, 103.9716),
    "buôn ma thuột": ("Buôn Ma Thuột", "Buonmathuot", 12.6667, 108.0333),
    "pleiku": ("Pleiku", "Pleiku", 13.9833, 108.0000),
    "phan thiết": ("Phan Thiết", "Phanthiet", 10.9333, 108.1000),
}


def _clean_web_url(raw_url: str) -> str:
    """Trích xuất URL thật từ link chuyển hướng của DuckDuckGo (//duckduckgo.com/l/?uddg=...)."""
    if not raw_url:
        return ""
    if "uddg=" in raw_url:
        try:
            full_url = raw_url if raw_url.startswith("http") else ("https:" + raw_url if raw_url.startswith("//") else "https://" + raw_url)
            parsed = urlparse(full_url)
            qs = parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                return unquote(qs["uddg"][0])
        except Exception:
            pass
    if raw_url.startswith("//"):
        return "https:" + raw_url
    return raw_url


def _detect_weather_location(query: str) -> Optional[Tuple[str, str, float, float]]:
    """Phát hiện xem câu hỏi có phải về thời tiết/nhiệt độ và xác định địa điểm."""
    q = query.lower()
    weather_keywords = [
        "thời tiết", "nhiệt độ", "dự báo thời tiết", "mưa không",
        "trời nắng không", "nắng không", "weather", "temperature",
    ]
    if not any(k in q for k in weather_keywords):
        return None

    for key in sorted(VIETNAM_LOCATIONS.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", q):
            return VIETNAM_LOCATIONS[key]

    m = re.search(
        r"(?:thời tiết|nhiệt độ|weather)\s+(?:tại|ở|in\s+)?([a-zA-ZÀ-ỹ\s]+?)(?:\s+(?:hôm nay|hiện tại|ngày mai|bây giờ|tuần này)|$)",
        q,
    )
    if m:
        loc = m.group(1).strip()
        stop_words = ["hôm nay", "hiện tại", "ngày mai", "bây giờ", "tuần này", "cho tôi", "xem", "tra cứu"]
        if len(loc) >= 2 and loc not in stop_words:
            return loc.title(), loc, 0.0, 0.0

    return None


async def _fetch_live_weather(
    display_name: str,
    city_code: str,
    lat: float = 0.0,
    lon: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """Lấy thông số thời tiết thực tế qua wttr.in với fallback Open-Meteo."""
    try:
        async with httpx.AsyncClient(
            timeout=3.5,
            headers={"User-Agent": "curl/7.68.0"},
            follow_redirects=True,
        ) as client:
            r = await client.get(f"https://wttr.in/{city_code}?format=j1")
            if r.status_code == 200:
                data = r.json()
                curr = data["current_condition"][0]
                today = data["weather"][0]

                temp_c = curr.get("temp_C", "")
                feels_like = curr.get("FeelsLikeC", temp_c)
                humidity = curr.get("humidity", "")
                wind_kmph = curr.get("windspeedKmph", "")
                wind_dir_code = curr.get("winddir16Point", "")
                wind_dir = WIND_DIR_MAP.get(wind_dir_code, wind_dir_code)

                raw_desc = curr.get("weatherDesc", [{}])[0].get("value", "").lower()
                desc_vi = WEATHER_DESC_MAP.get(raw_desc, curr.get("weatherDesc", [{}])[0].get("value", ""))

                min_temp = today.get("mintempC", "")
                max_temp = today.get("maxtempC", "")

                snippet = (
                    f"DỮ LIỆU THỜI TIẾT THỜI GIAN THỰC TẠI {display_name.upper()}:\n"
                    f"- Nhiệt độ hiện tại: {temp_c}°C (Cảm giác thực tế như: {feels_like}°C)\n"
                    f"- Tình trạng thời tiết: {desc_vi}\n"
                    f"- Độ ẩm không khí: {humidity}%\n"
                    f"- Tốc độ gió: {wind_kmph} km/h (hướng {wind_dir})\n"
                    f"- Dự báo nhiệt độ hôm nay: Thấp nhất {min_temp}°C, Cao nhất {max_temp}°C."
                )
                return {
                    "source_type": "web",
                    "title": f"Thời tiết thực tế tại {display_name} (wttr.in)",
                    "url": f"https://wttr.in/{city_code}",
                    "snippet": snippet,
                    "ref_id": 1,
                }
    except Exception as exc:
        logger.warning("wttr.in fetch failed for %s: %s", display_name, exc)

    if lat and lon:
        try:
            async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
                url = (
                    f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
                    "&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FBangkok"
                )
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    curr = data.get("current", {})
                    daily = data.get("daily", {})
                    temp = curr.get("temperature_2m", "")
                    feels = curr.get("apparent_temperature", temp)
                    humidity = curr.get("relative_humidity_2m", "")
                    wind = curr.get("wind_speed_10m", "")
                    min_t = daily.get("temperature_2m_min", [None])[0]
                    max_t = daily.get("temperature_2m_max", [None])[0]

                    code = curr.get("weather_code", 0)
                    weather_status = (
                        "Trời quang đãng, không mây" if code == 0
                        else "Có mây rải rác" if code in (1, 2)
                        else "Nhiều mây, u ám" if code == 3
                        else "Có sương mù" if code in (45, 48)
                        else "Mưa phùn nhẹ" if code in (51, 53, 55)
                        else "Mưa nhỏ đến vừa" if code in (61, 63)
                        else "Mưa to" if code == 65
                        else "Mưa rào" if code in (80, 81, 82)
                        else "Có dông sét" if code in (95, 96, 99)
                        else "Thời tiết bình thường"
                    )

                    snippet = (
                        f"DỮ LIỆU THỜI TIẾT THỜI GIAN THỰC TẠI {display_name.upper()} (Open-Meteo):\n"
                        f"- Nhiệt độ hiện tại: {temp}°C (Cảm giác thực tế như: {feels}°C)\n"
                        f"- Tình trạng thời tiết: {weather_status}\n"
                        f"- Độ ẩm không khí: {humidity}%\n"
                        f"- Tốc độ gió: {wind} km/h\n"
                        f"- Dự báo nhiệt độ hôm nay: Thấp nhất {min_t}°C, Cao nhất {max_t}°C."
                    )
                    return {
                        "source_type": "web",
                        "title": f"Thời tiết thực tế tại {display_name} (Open-Meteo)",
                        "url": f"https://open-meteo.com/en/docs#latitude={lat}&longitude={lon}",
                        "snippet": snippet,
                        "ref_id": 1,
                    }
        except Exception as exc:
            logger.warning("Open-Meteo fetch failed for %s: %s", display_name, exc)

    return None


class MainContentExtractor(HTMLParser):
    """Trích xuất văn bản thực tế từ bài viết (bỏ qua script, nav, header, footer, ads)."""
    def __init__(self):
        super().__init__()
        self.paragraphs: List[str] = []
        self._current_tag = ""
        self._current_text: List[str] = []
        self._ignore_depth = 0
        self._ignored_tags = {
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            'noscript', 'svg', 'form', 'button', 'iframe', 'select', 'input'
        }

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self._ignored_tags:
            self._ignore_depth += 1
        elif self._ignore_depth == 0:
            if t in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'td', 'blockquote', 'article'):
                self._current_tag = t
                self._current_text = []

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self._ignored_tags:
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
        elif self._ignore_depth == 0:
            if t in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'td', 'blockquote', 'article') and self._current_text:
                line = " ".join("".join(self._current_text).split())
                if len(line) > 25:
                    self.paragraphs.append(line)
                self._current_text = []
                self._current_tag = ""

    def handle_data(self, data):
        if self._ignore_depth == 0 and self._current_tag:
            self._current_text.append(data)

    def get_content(self, max_chars: int = 1500) -> str:
        text = "\n".join(self.paragraphs)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text


async def _fetch_webpage_content(url: str, timeout: float = 3.5) -> Optional[str]:
    """Tải và cào nội dung chi tiết bài viết thực tế từ trang web đích."""
    if not url or not url.startswith("http"):
        return None
    headers = {
        'User-Agent': 'KnowledgeRAGBot/1.0 (https://github.com/TruyenThanhhhh/PBL6; contact@example.com) Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and 'text/html' in resp.headers.get('content-type', ''):
                parser = MainContentExtractor()
                parser.feed(resp.text)
                content = parser.get_content(1500)
                if len(content) > 120:
                    return content
    except Exception:
        pass
    return None


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._active: Optional[Dict[str, str]] = None
        self._capture = False
        self._snippet = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._active = {"title": "", "url": attrs_dict.get("href", "")}
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


def _save_cached_results(
    query_hash: str,
    query: str,
    results: List[Dict[str, Any]],
    ttl_minutes: int = 360,
) -> None:
    if not results:
        return
    conn = get_db_connection()
    try:
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
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
    """
    Thực hiện tìm kiếm Web:
    1. Tự động kiểm tra thời tiết thời gian thực nếu câu hỏi về thời tiết/nhiệt độ.
    2. Lấy danh sách kết quả tìm kiếm từ DuckDuckGo.
    3. TỰ ĐỘNG CÀO NỘI DUNG THẬT (deep scraping) từ các trang web hàng đầu
       để cung cấp đầy đủ nội dung bài viết thay vì chỉ lấy mô tả ngắn (snippet).
    """
    if not WEB_SEARCH_ENABLED or not query.strip():
        return []

    normalized = " ".join(query.strip().lower().split())
    query_hash = hashlib.md5(f"{normalized}:{limit}".encode("utf-8")).hexdigest()
    cached = _get_cached_results(query_hash)
    if cached is not None:
        return cached

    # 1. Kiểm tra intent thời tiết
    weather_loc = _detect_weather_location(query)
    weather_source: Optional[Dict[str, Any]] = None
    if weather_loc:
        display_name, city_code, lat, lon = weather_loc
        weather_source = await _fetch_live_weather(display_name, city_code, lat, lon)

    # 2. Tìm kiếm DuckDuckGo cho các bài viết liên quan
    web_results: List[Dict[str, Any]] = []
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
                web_results = [
                    {
                        "source_type": "web",
                        "title": item["title"].strip(),
                        "url": _clean_web_url(item["url"]),
                        "snippet": item.get("snippet", "").strip() or item["title"].strip(),
                    }
                    for item in parser.results[:limit]
                ]
            else:
                answer = await client.get(
                    url,
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                )
                answer.raise_for_status()
                payload = answer.json()
                text = payload.get("AbstractText") or payload.get("Answer") or ""
                if text:
                    web_results = [{
                        "source_type": "web",
                        "title": payload.get("Heading") or query,
                        "url": payload.get("AbstractURL") or "",
                        "snippet": text,
                    }]
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("DuckDuckGo web search failed: %s", exc)

    # 3. TỰ ĐỘNG CÀO NỘI DUNG BÀI VIẾT THẬT (Deep Content Extraction)
    # Lấy nội dung chi tiết của tối đa 3 trang web đầu tiên song song (concurrent I/O)
    scrape_candidates = web_results[:3]
    if scrape_candidates:
        tasks = [_fetch_webpage_content(item["url"]) for item in scrape_candidates]
        scraped_contents = await asyncio.gather(*tasks, return_exceptions=True)
        for item, content in zip(scrape_candidates, scraped_contents):
            if isinstance(content, str) and content.strip():
                item["snippet"] = content.strip()

    # 4. Kết hợp kết quả: Đưa live weather lên đầu nếu có
    combined: List[Dict[str, Any]] = []
    if weather_source:
        combined.append(weather_source)
        for item in web_results:
            if len(combined) >= limit:
                break
            combined.append(item)
    else:
        combined = web_results[:limit]

    # Đánh lại ref_id từ 1 đến N
    for idx, item in enumerate(combined, start=1):
        item["ref_id"] = idx

    if combined:
        ttl = 15 if weather_source else 360  # Dữ liệu thời tiết lưu cache 15 phút, nội dung web lưu 6 giờ
        _save_cached_results(query_hash, query.strip(), combined, ttl_minutes=ttl)

    return combined
