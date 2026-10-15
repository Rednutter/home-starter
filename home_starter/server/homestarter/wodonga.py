"""Wodonga's public collection-day polygons and dated annual colour calendar.

Coordinates stay local. No address queries, indefinite parity anchor or PDF cache.
The intentionally narrow A5 calendar reader rejects unfamiliar layouts/streams.
"""

import asyncio
import calendar
import hashlib
import io
import json
import math
import re
from datetime import date, timedelta
from html import unescape
from urllib.parse import urljoin, urlsplit

import aiohttp
from pypdf import PdfReader

ITEM = "f22429353e8a4552945dfa39684e6bc8"
PAGE = "https://www.wodonga.vic.gov.au/Services/Recycling-and-Waste/Bins-and-Collection"
FAQ = "https://www.wodonga.vic.gov.au/Services/Recycling-and-Waste/Recycling-centre/Recycling-and-waste-FAQs"
ARCGIS = "https://www.arcgis.com/sharing/rest/content/items/" + ITEM
COLORS = {(0.01, 0.182, 1.0, 0.0): "recycling", (0.065, 0.976, 1.0, 0.006): "general"}


class SourceError(ValueError):
    """Safe public error; never includes coordinates or upstream payloads."""

    def __init__(self, message, kind="changed"):
        super().__init__(message)
        self.kind = kind


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe_url(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if (
        parts.scheme != "https"
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or not any(host == suffix or host.endswith("." + suffix) for suffix in ("arcgis.com", "wodonga.vic.gov.au", "halvewaste.com.au"))
    ):
        raise SourceError("Council source address changed; review required.")
    return url


async def get(session, url, *, params=None, binary=False):
    url = safe_url(url)
    try:
        # Redirects are checked before following; no arbitrary source or local URL.
        for _ in range(4):
            async with session.get(
                url,
                params=params,
                allow_redirects=False,
                headers={"User-Agent": "HomeStarter/0.7 (+https://github.com/Rednutter/home-starter)"},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    url = safe_url(urljoin(url, response.headers.get("Location", "")))
                    params = None
                    continue
                if response.status != 200:
                    raise SourceError("Council source currently unavailable.", "unavailable")
                chunks, length = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    length += len(chunk)
                    if length > 8_000_000:
                        raise SourceError("Council response exceeds the supported size.")
                    chunks.append(chunk)
                body = b"".join(chunks)
                return body if binary else body.decode("utf-8", errors="strict")
    except (aiohttp.ClientError, TimeoutError, UnicodeError, OSError):
        raise SourceError("Council source currently unavailable.", "unavailable") from None
    raise SourceError("Council source redirected too many times.")


def match_area(features, latitude, longitude):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (latitude, longitude)):
        raise SourceError("HA home location is not usable. Confirm the collection day instead.")
    matches = []
    for feature in features:
        inside = False
        rings = feature["geometry"]["rings"]
        for ring in rings:
            if len(ring) < 4:
                raise SourceError("Collection map has incomplete geometry.")
            for a, b in zip(ring, ring[1:], strict=False):
                x1, y1 = a[:2]
                x2, y2 = b[:2]
                if (
                    abs((longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)) < 1e-12
                    and min(x1, x2) <= longitude <= max(x1, x2)
                    and min(y1, y2) <= latitude <= max(y1, y2)
                ):
                    raise SourceError("Home is on a collection-area boundary. Confirm its collection day.")
                if (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
                    inside = not inside
        if inside:
            label = feature["attributes"]["type"]
            if label not in ["Collection " + calendar.day_name[d] for d in range(5)]:
                raise SourceError("Collection map has an unfamiliar service day.")
            matches.append({"day": list(calendar.day_name).index(label.removeprefix("Collection ")), "zone": str(feature["attributes"]["OBJECTID"])})
    if len(matches) != 1:
        raise SourceError("Collection area is unresolved or conflicting. Confirm the collection day.")
    return matches[0]


def decode_calendar(body):
    try:
        reader = PdfReader(io.BytesIO(body), strict=True)
        if len(reader.pages) != 1:
            raise SourceError("Annual calendar layout changed; review required.")
        page = reader.pages[0]
        if abs(float(page.mediabox.width) - 419.528) > 2 or abs(float(page.mediabox.height) - 595.276) > 2 or len(page.get_contents().get_data()) > 4_000_000:
            raise SourceError("Annual calendar layout changed; review required.")
        texts, boxes, stack, points = [], [], [], []
        color = None

        def text(value, cm, tm, font, size):
            if value.strip() and list(cm) == [1, 0, 0, 1, 0, 0]:
                texts.append((value.strip(), float(tm[4]), float(tm[5])))

        def operand(op, args, cm, tm):
            nonlocal color, points

            def point(x, y):
                return float(x) * cm[0] + float(y) * cm[2] + cm[4], float(x) * cm[1] + float(y) * cm[3] + cm[5]

            if op == b"q":
                stack.append(color)
            elif op == b"Q":
                color = stack.pop() if stack else None
            elif op == b"k":
                color = tuple(round(float(v), 3) for v in args)
            elif op in (b"rg", b"g"):
                color = None
            elif op == b"m":
                points = [point(*args)]
            elif op == b"l":
                points.append(point(*args))
            elif op == b"re":
                x, y, w, h = map(float, args)
                points = [point(x, y), point(x + w, y + h)]
            elif op in (b"f", b"f*", b"B", b"B*"):
                if color in COLORS and points:
                    xs, ys = zip(*points, strict=True)
                    boxes.append((min(xs), min(ys), max(xs), max(ys), COLORS[color]))
                points = []
            elif op in (b"n", b"S", b"s"):
                points = []

        page.extract_text(visitor_text=text, visitor_operand_before=operand)
        return dated_cells(texts, boxes)
    except SourceError:
        raise
    except Exception:
        raise SourceError("Annual calendar could not be validated; last verified data preserved.") from None


def dated_cells(texts, boxes):
    years = {int(t) for t, _, y in texts if re.fullmatch(r"20\d{2}", t) and y > 500}
    names = {m: i for i, m in enumerate(calendar.month_name) if m}
    names["Febuary"] = 2  # Council's published spelling.
    months = [(names[t], x, y) for t, x, y in texts if t in names]
    if len(years) != 1 or len(months) != 12 or {m for m, _, _ in months} != set(range(1, 13)) or not any(t == "Wodonga" for t, _, _ in texts):
        raise SourceError("Annual calendar identity is incomplete or changed.")
    year = years.pop()
    headers = [(x, y) for t, x, y in texts if t == "Mo Tu We Th Fr Sa Su"]
    if len(headers) != 12 or not all(any(word in t for t, _, _ in texts) for word in ("Organics", "Recycling", "General Waste")):
        raise SourceError("Annual calendar services or weekday grid changed.")
    for label, stream in (("Recycling", "recycling"), ("General Waste", "general")):
        if not any(t == label and any(b[4] == stream and b[0] <= x + 2 <= b[2] and b[1] <= y + 1 <= b[3] for b in boxes) for t, x, y in texts):
            raise SourceError("Annual calendar colour legend changed.")
    dates = {}
    for month, mx, my in months:
        hx, hy = min(headers, key=lambda h: abs(h[1] - (my - 9)) + abs(h[0] + 35 - mx))
        if not 6 < my - hy < 12 or not 0 < mx - hx < 65:
            raise SourceError("Annual calendar grid changed.")
        first = date(year, month, 1).weekday()
        first_cells = [(x, y) for t, x, y in texts if re.fullmatch(r"1(?:\s+\d+)*", t) and abs(hy - y - 10) < 2 and -2 < x - hx < 78]
        if first_cells:
            if len(first_cells) != 1 or abs(first_cells[0][0] - (hx + 11 * first)) > 4:
                raise SourceError("Printed dates conflict with the annual calendar year.")
        elif first + calendar.monthrange(year, month)[1] <= 35:
            raise SourceError("Annual calendar printed dates are incomplete.")
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            current = date(year, month, day)
            if current.weekday() > 4:
                continue
            row = ((day - 1 + date(year, month, 1).weekday()) // 7) % 5
            x, y = hx + 3 + 11.0 * current.weekday(), hy - 7 - row * 11.68
            hits = {b[4] for b in boxes if b[0] <= x <= b[2] and b[1] <= y <= b[3]}
            if len(hits) != 1:
                raise SourceError("Annual calendar has missing or conflicting dated colours.")
            dates[current.isoformat()] = hits.pop()
    # Check the entire printed year, including short first/last weeks. Never extend it.
    weeks = {}
    for key, stream in sorted(dates.items()):
        d = date.fromisoformat(key)
        monday = (d - timedelta(days=d.weekday())).isoformat()
        if monday in weeks and weeks[monday] != stream:
            raise SourceError("Annual calendar conflicts within a collection week.")
        weeks[monday] = stream
    if any(a == b for a, b in zip(weeks.values(), list(weeks.values())[1:], strict=False)):
        raise SourceError("Annual alternating pattern changed; review required.")
    return {"year": year, "valid_from": f"{year}-01-01", "valid_to": f"{year}-12-31", "dates": dates}


class WodongaProvider:
    id = "wodonga"
    services = [
        {"id": "organics", "label": "Green", "cadence": "weekly"},
        {"id": "recycling", "label": "Recycling", "cadence": "fortnightly"},
        {"id": "general", "label": "General waste", "cadence": "fortnightly"},
    ]

    def __init__(self, session):
        self.session = session

    async def location(self, config):
        item = json.loads(await get(self.session, ARCGIS, params={"f": "json"}))
        if item.get("id") != ITEM or item.get("owner") != "GIS_CityOfWodonga" or item.get("type") != "Feature Service":
            raise SourceError("Council map identity changed.")
        service = safe_url(item["url"])
        info = json.loads(await get(self.session, service, params={"f": "json"}))
        if len(info.get("layers", [])) != 1:
            raise SourceError("Council collection layers changed.")
        layer = info["layers"][0]["id"]
        raw = json.loads(
            await get(
                self.session,
                service + f"/{layer}/query",
                params={"f": "json", "where": "1=1", "outFields": "OBJECTID,type", "returnGeometry": "true", "outSR": "4326"},
            )
        )
        if raw.get("exceededTransferLimit") or not raw.get("features") or raw.get("spatialReference", {}).get("wkid") != 4326:
            raise SourceError("Council collection map is partial or unavailable.")
        result = match_area(raw["features"], config.get("latitude"), config.get("longitude"))
        return {**result, "location_source": "arcgis", "map_version": str(item["modified"])}

    async def fetch(self, year):
        page, faq = await asyncio.gather(get(self.session, PAGE), get(self.session, FAQ))
        plain = re.sub(r"<[^>]+>", " ", unescape(page + " " + faq))
        plain = re.sub(r"\s+", " ", plain)
        if not all(s in plain for s in ("Weekly collection", "Alternate fortnightly collection", "collected on all public holidays")):
            raise SourceError("Council collection policy changed or could not be verified.")
        links = []
        for href, label in re.findall(r"<a\b[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>", page, re.I | re.S):
            label = re.sub(r"<[^>]+>", " ", unescape(label))
            years = re.findall(r"20\d{2}", label)
            if "collection calendar" in label.lower() and years:
                target = int(years[0])
                if year <= target <= year + 1:
                    links.append((target, safe_url(urljoin(PAGE, unescape(href)))))
        if len({y for y, _ in links}) != len(links) or not links:
            raise SourceError("Current annual Council schedule is unavailable; renewal needs checking.")
        schedules = []
        for target, url in sorted(links):
            body = await get(self.session, url, binary=True)
            annual = await asyncio.to_thread(decode_calendar, body)
            if annual["year"] != target:
                raise SourceError("Annual calendar year conflicts with its Council link.")
            annual["dates"] = {key: ["organics", stream] for key, stream in annual["dates"].items()}
            schedules.append({**annual, "source_type": "annual_calendar", "source_id": url, "version": hashlib.sha256(body).hexdigest()})
        return schedules
