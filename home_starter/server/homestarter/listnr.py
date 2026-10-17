"""Public LiSTNR GraphQL catalogue and bounded, cookie-free HLS resolution."""

import math
import re
import time
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp

API = "https://api.listnr.com/v2"
FIELDS = (
    "id slug name description stationCode stationType state network latitude longitude "
    "audioStreams { callSign url vast } images { logoLarge } categories { name } genres { name }"
)
HOSTS = (".scastream.com.au", ".streamguys1.com", ".streamtheworld.com", ".scahw.com.au")
AMBIENT = {
    "rain": ("rain",),
    "nature": ("rainforest", "waterfall", "nature", "ocean", "forest"),
    "noise": ("white noise", "pink noise", "brown noise", "cooling fan"),
    "sleep": ("sleep", "deep calm", "wind down"),
    "focus": ("focus", "stress free", "morning yoga"),
}


class CatalogueError(ValueError):
    pass


def ambient_group(label):
    return next((group for group, words in AMBIENT.items() if any(re.search(r"\b" + re.escape(word) + r"\b", label.casefold()) for word in words)), None)


def media_url(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and any((parsed.hostname or "").endswith(suffix) for suffix in HOSTS)
        )
    except (TypeError, ValueError):
        return False


def aac_frames(sample):
    for index in range(len(sample) - 8):
        if sample[index] != 255 or sample[index + 1] & 246 != 240:
            continue
        size = ((sample[index + 3] & 3) << 11) | (sample[index + 4] << 3) | (sample[index + 5] >> 5)
        following = index + size
        if size >= 7 and following + 1 < len(sample) and sample[following] == 255 and sample[following + 1] & 246 == 240:
            return True
    return False


async def public_request(url, payload=None, limit=2_000_000):
    """Redirects remain on reviewed public hosts; no sessions/cookies survive a call."""
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=20), headers={"User-Agent": "Home-Starter-Public-Radio/1.0"}
    ) as session:
        for _ in range(5):
            api_request = bool(re.fullmatch(re.escape(API) + r"(?:\?postcode=\d{4})?", url))
            if not api_request and not media_url(url):
                raise CatalogueError("unsupported_stream_host")
            try:
                async with session.request("POST" if payload else "GET", url, json=payload, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        if payload:
                            raise CatalogueError("catalogue_unavailable")
                        url = urljoin(url, response.headers.get("Location", ""))
                        continue
                    if response.status != 200:
                        raise CatalogueError(
                            {401: "authentication_required", 403: "access_denied", 451: "geo_restricted", 429: "rate_limited"}.get(
                                response.status, "upstream_unavailable"
                            )
                        )
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        data.extend(chunk[: limit - len(data)])
                        if len(data) >= limit:
                            break
                    return bytes(data), response.headers.get("Content-Type", ""), url
            except (aiohttp.ClientError, TimeoutError):
                raise CatalogueError("upstream_unavailable") from None
    raise CatalogueError("stream_resolution_failed")


def normalize(value, networks=None):
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) and value[k] for k in ("id", "slug", "name")):
        raise CatalogueError("catalogue_schema_changed")
    category, subcategory = ("music", None) if value.get("stationType") == "Music" else ("radio", "live")
    label = (value["name"] + " " + value["slug"]).casefold().replace("-", " ")
    if category == "music":
        group = ambient_group(label)
        if group:
            category, subcategory = "ambient", group
    return {
        "id": "listnr:" + value["id"],
        "provider": "listnr",
        "station_id": value["id"],
        "slug": value["slug"],
        "name": value["name"],
        "category": category,
        "subcategory": subcategory,
        "region": value.get("state"),
        "location": value.get("stationCode"),
        "network": (networks or {}).get(value.get("network")),
        "network_id": value.get("network"),
        "artwork": (value.get("images") or {}).get("logoLarge"),
        "page": "https://play.listnr.com/station/" + value["slug"],
        "resolver": {"provider": "listnr", "station_id": value["id"]},
        "availability": "active",
        "last_discovered": time.time(),
    }


def distance(station, home):
    try:
        a, b, c, d = [math.radians(float(v)) for v in (station["latitude"], station["longitude"], home["latitude"], home["longitude"])]
        h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
        return 6371 * 2 * math.asin(min(1, math.sqrt(h)))
    except (ValueError, TypeError, KeyError):
        return None


def regional_score(station, region):
    if not region:
        return 0
    haystack = " ".join(str(station.get(k) or "") for k in ("name", "slug", "region", "location")).casefold().replace("-", " ")
    terms = [region.get("name", ""), *region.get("search_terms", [])]
    return max((len(t.strip()) for t in terms if len(t.strip()) >= 3 and t.strip().casefold() in haystack), default=0)


class LiSTNR:
    def __init__(self, request=public_request):
        self.request = request

    async def query(self, query, variables=None, postcode=None):
        import json

        if postcode is not None and not re.fullmatch(r"\d{4}", postcode):
            raise CatalogueError("regional_lookup_unavailable")
        url = API + "?postcode=" + postcode if postcode is not None else API
        raw, _, _ = await self.request(url, {"query": query, "variables": variables or {}})
        try:
            body = json.loads(raw)
            if body.get("errors") or not isinstance(body.get("data"), dict):
                raise ValueError
            return body["data"]
        except (ValueError, AttributeError, TypeError):
            raise CatalogueError("catalogue_unavailable") from None

    async def discover(self):
        data = await self.query("query HomeStarterCatalogue { stations { " + FIELDS + " } networks { id name slug } }")
        if not isinstance(data.get("stations"), list) or not data["stations"]:
            raise CatalogueError("catalogue_unavailable")
        networks = {n["id"]: n["name"] for n in data.get("networks", [])}
        return [{**normalize(row, networks), "latitude": row.get("latitude"), "longitude": row.get("longitude")} for row in data["stations"]]

    async def resolve(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"listnr:[A-Za-z0-9_-]{1,150}", identity):
            raise CatalogueError("station_not_found")
        data = await self.query("query HomeStarterStation($ids:[ID!]) { stations(ids:$ids) { " + FIELDS + " } }", {"ids": [identity[7:]]})
        station = next((s for s in data.get("stations", []) if s.get("id") == identity[7:]), None)
        if not station:
            raise CatalogueError("upstream_missing")
        streams = station.get("audioStreams") or []
        url = streams[0].get("url") if streams else None
        if not media_url(url):
            raise CatalogueError("unsupported_stream_host")
        # Never persist a delivery URL with credentials/session/signature parameters.
        if set(parse_qs(urlsplit(url).query)) - {"dist"}:
            raise CatalogueError("dynamic_stream_requires_runtime_adapter")
        return {"url": url, "format": "hls", "codec": None, "bitrate": None, "expires_at": None, "resolved_at": time.time()}

    async def nearby(self, postcode):
        data = await self.query("query HomeStarterNearby { networks { nearmeStations { id } } }", postcode=postcode)
        return {"listnr:" + station["id"] for network in data.get("networks", []) for station in network.get("nearmeStations") or []}

    async def validate(self, resolution):
        url = resolution["url"]
        codec, bitrate = None, None
        for _ in range(3):
            raw, content_type, final = await self.request(url)
            text = raw.decode("utf-8-sig", errors="replace")
            if not text.startswith("#EXTM3U") or not any(t in content_type.lower() for t in ("mpegurl", "text/plain", "application/octet-stream")):
                raise CatalogueError("stream_validation_failed")
            if any("METHOD=NONE" not in line for line in text.splitlines() if line.startswith("#EXT-X-KEY:")):
                raise CatalogueError("unsupported_protected_stream")
            lines = text.splitlines()
            variant = next((i for i, line in enumerate(lines) if line.startswith("#EXT-X-STREAM-INF:")), None)
            if variant is not None:
                attrs = lines[variant]
                if "RESOLUTION=" in attrs or "avc" in attrs:
                    raise CatalogueError("unsupported_stream_format")
                match = re.search(r'CODECS="([^"]+)"', attrs)
                codec = match.group(1) if match else codec
                match = re.search(r"BANDWIDTH=(\d+)", attrs)
                bitrate = int(match.group(1)) if match else bitrate
                if variant + 1 >= len(lines):
                    raise CatalogueError("stream_validation_failed")
                url = urljoin(final, lines[variant + 1])
                continue
            segments = [line for line in lines if line and not line.startswith("#")]
            if not segments or "#EXTINF:" not in text or "#EXT-X-ENDLIST" in text:
                raise CatalogueError("stream_validation_failed")
            sample, kind, _ = await self.request(urljoin(final, segments[-1]), limit=8192)
            if not kind.lower().startswith("audio/") or not aac_frames(sample):
                raise CatalogueError("stream_validation_failed")
            return {**resolution, "codec": codec, "bitrate": bitrate, "validated_at": time.time()}
        raise CatalogueError("stream_validation_failed")
