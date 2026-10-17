"""Anonymous public LiSTNR resolver experiment; no Home Starter/MA integration.

Python 3.11+, standard library only. Never saves cookies, sessions or audio.
Example: python resolve_listnr.py mmm-theborder --validate --observe-seconds 12
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.listnr.com/v2"
FIELDS = """id slug name description stationCode stationType state network
audioStreams { callSign url vast } images { logoLarge }
categories { id name } genres { id name slug }"""
SLUG_QUERY = "query ResolveStation($slug:String!) { station(where:{slug:$slug}) { " + FIELDS + " } }"
ID_QUERY = "query ResolveStationId($ids:[ID!]) { stations(ids:$ids) { " + FIELDS + " } }"


class ResolutionError(Exception):
    def __init__(self, code, status=None):
        self.code = code
        self.status = status
        super().__init__(code)


def reviewed_media_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and not parsed.username and not parsed.password and (parsed.hostname or "").endswith(".scastream.com.au")


class MediaRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not reviewed_media_url(newurl):
            raise ResolutionError("unreviewed_stream_host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, payload=None, limit=2_000_000, phase="catalogue"):
    """Use a fresh, cookie-free HTTP request; do not include upstream bodies in errors."""
    headers = {"User-Agent": "LiSTNR-Resolver-Research/1.0"}
    if phase == "catalogue" and url != API:
        raise ResolutionError("catalogue_unavailable")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    try:
        opener = build_opener(MediaRedirects()) if phase == "stream" else build_opener()
        if phase == "stream" and not reviewed_media_url(url):
            raise ResolutionError("unreviewed_stream_host")
        with opener.open(Request(url, data=data, headers=headers), timeout=20) as response:  # noqa: S310 -- fixed HTTPS API or reviewed HTTPS CDN above
            body = response.read(limit)
            return body, dict(response.headers), response.geturl(), response.status
    except HTTPError as exc:
        if exc.code == 401:
            code = "authentication_required"
        elif exc.code == 451:
            code = "geo_restricted"
        elif exc.code == 429:
            code = "rate_limited"
        elif exc.code == 403:
            code = "access_denied"  # A 403 alone cannot prove geo-blocking or expiry.
        elif phase == "catalogue":
            code = "catalogue_unavailable"
        else:
            code = "stream_resolution_failed"
        raise ResolutionError(code, exc.code) from None
    except (URLError, TimeoutError, OSError):
        code = "catalogue_unavailable" if phase == "catalogue" else "stream_resolution_failed"
        raise ResolutionError(code) from None


def resolve(identity, by_id=False):
    identity = identity.removeprefix("listnr:")
    if not identity or len(identity) > 150 or not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
        raise ResolutionError("invalid_station_identity")
    payload = {
        "query": ID_QUERY if by_id else SLUG_QUERY,
        "variables": {"ids": [identity]} if by_id else {"slug": identity},
    }
    raw, _, _, _ = fetch(API, payload)
    try:
        response = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ResolutionError("catalogue_unavailable") from None
    if not isinstance(response, dict) or response.get("errors") or not isinstance(response.get("data"), dict):
        raise ResolutionError("catalogue_unavailable")
    value = response["data"].get("stations" if by_id else "station")
    if by_id:
        if not isinstance(value, list):
            raise ResolutionError("catalogue_unavailable")
        value = next((s for s in value if isinstance(s, dict) and s.get("id") == identity), None)
    if value is None:
        raise ResolutionError("station_not_found")
    if not isinstance(value, dict) or not all(value.get(k) for k in ["id", "slug", "name"]):
        raise ResolutionError("catalogue_unavailable")
    streams = value.get("audioStreams") or []
    # Same first-stream choice as the observed player; no guessed mount paths.
    if not streams or not isinstance(streams[0], dict) or not streams[0].get("url"):
        raise ResolutionError("stream_resolution_failed")
    url = streams[0]["url"]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ResolutionError("stream_resolution_failed")
    return {
        "station_id": value["id"],
        "identity": "listnr:" + value["id"],
        "slug": value["slug"],
        "name": value["name"],
        "station_type": value.get("stationType"),
        "station_code": value.get("stationCode"),
        "call_sign": streams[0].get("callSign"),
        "network_id": value.get("network"),
        "state": value.get("state"),
        "categories": value.get("categories"),
        "genres": value.get("genres"),
        "stream_url": url,
        "stream_type": "hls" if parsed.path.endswith(".m3u8") else "unknown",
        "expires_at": None,
        "expiry_status": "not_advertised",
        "codec": None,
        "bitrate": None,
        "artwork_url": (value.get("images") or {}).get("logoLarge"),
        "resolved_at": datetime.now(UTC).isoformat(),
    }


def attributes(line):
    return dict(re.findall(r'([\w-]+)=("[^"]*"|[^,\r\n]*)', line))


def playlist(url):
    # This experiment deliberately validates only the observed SCA stream hosts.
    # Third-party partner stations need their own reviewed validation policy.
    host = urlsplit(url).hostname or ""
    if not host.endswith(".scastream.com.au") or urlsplit(url).scheme != "https":
        raise ResolutionError("unreviewed_stream_host")
    raw, headers, final, status = fetch(url, phase="stream")
    # Reject off-host redirects before consuming any following media requests.
    if not (urlsplit(final).hostname or "").endswith(".scastream.com.au"):
        raise ResolutionError("unreviewed_stream_host")
    text = raw.decode("utf-8-sig", errors="replace")
    if not text.startswith("#EXTM3U"):
        raise ResolutionError("stream_resolution_failed", status)
    if any(attributes(line).get("METHOD") != "NONE" for line in text.splitlines() if line.startswith("#EXT-X-KEY:")):
        raise ResolutionError("unsupported_protected_content")
    return text, headers, final


def variants(text, base):
    result = []
    pending = None
    for line in text.splitlines():
        if line.startswith("#EXT-X-STREAM-INF:"):
            pending = attributes(line)
        elif line and not line.startswith("#") and pending is not None:
            result.append({"url": urljoin(base, line), "attributes": pending})
            pending = None
    return result


def segment_urls(text, base):
    return [urljoin(base, line) for line in text.splitlines() if line and not line.startswith("#")]


def adts_audio_info(sample):
    """Recognize two consecutive AAC ADTS frames, allowing leading ID3 metadata."""
    rates = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]
    for i in range(len(sample) - 8):
        if sample[i] != 255 or sample[i + 1] & 246 != 240:
            continue
        frequency = (sample[i + 2] >> 2) & 15
        length = ((sample[i + 3] & 3) << 11) | (sample[i + 4] << 3) | (sample[i + 5] >> 5)
        next_frame = i + length
        if frequency >= len(rates) or length < 7 or next_frame + 1 >= len(sample):
            continue
        if sample[next_frame] != 255 or sample[next_frame + 1] & 246 != 240:
            continue
        return {"codec": "aac", "adts_core_sample_rate": rates[frequency], "channels": ((sample[i + 2] & 1) << 2) | (sample[i + 3] >> 6), "adts_offset": i}
    raise ResolutionError("audio_validation_failed")


def validate(result, observe_seconds=12):
    text, headers, base = playlist(result["stream_url"])
    options = variants(text, base)
    master_attributes = None
    if options:
        # The tested stations have a single audio-only variant. Do not choose video.
        audio = [v for v in options if "RESOLUTION" not in v["attributes"] and "avc" not in v["attributes"].get("CODECS", "")]
        if not audio:
            raise ResolutionError("unsupported_stream_format")
        chosen = audio[0]
        master_attributes = chosen["attributes"]
        text, _, base = playlist(chosen["url"])
        if variants(text, base):
            raise ResolutionError("unsupported_stream_format")
    urls = segment_urls(text, base)
    if not urls or "#EXTINF:" not in text:
        raise ResolutionError("stream_resolution_failed")
    for url in urls:
        if not (urlsplit(url).hostname or "").endswith(".scastream.com.au") or urlsplit(url).scheme != "https":
            raise ResolutionError("unreviewed_stream_host")
    sample, _, _, status = fetch(urls[-1], limit=32768, phase="stream")
    info = adts_audio_info(sample)
    started = time.monotonic()
    time.sleep(observe_seconds)
    after, _, after_base = playlist(base)  # Refresh the SAME session playlist.
    later = segment_urls(after, after_base)
    advanced = bool(set(later) - set(urls))
    if not advanced:
        raise ResolutionError("live_progress_not_observed")
    later_sample, _, _, _ = fetch(later[-1], limit=32768, phase="stream")
    adts_audio_info(later_sample)
    result.update(stream_type="hls", codec=info["codec"])
    if master_attributes and master_attributes.get("CODECS"):
        result["codec"] = master_attributes["CODECS"].strip('"')
    if master_attributes and master_attributes.get("BANDWIDTH", "").isdigit():
        result["bitrate"] = int(master_attributes["BANDWIDTH"])
        result["bitrate_kind"] = "manifest_bandwidth"
    result["validation"] = {
        "status": "passed",
        "http_status": status,
        "master_variant_count": len(options),
        "master_attributes": master_attributes,
        "target_duration": re.search(r"#EXT-X-TARGETDURATION:(\d+)", text).group(1) if "#EXT-X-TARGETDURATION:" in text else None,
        "segment_durations": [float(x) for x in re.findall(r"#EXTINF:([0-9.]+)", text)],
        "audio": info,
        "live_playlist_advanced": advanced,
        "observation_seconds": round(time.monotonic() - started, 2),
        "audio_bytes_read_maximum": 65536,
        "audio_retained": False,
        "cookies_sent": False,
        "authentication_sent": False,
        "manifest_cache_control": next((v for k, v in headers.items() if k.lower() == "cache-control"), None),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("station", help="slug, or opaque station ID with --id / listnr: prefix")
    parser.add_argument("--id", action="store_true", help="resolve by the stable catalogue ID")
    parser.add_argument("--validate", action="store_true", help="sample HLS headers and observe live progression")
    parser.add_argument("--observe-seconds", type=int, choices=range(10, 31), default=12, metavar="10..30")
    args = parser.parse_args()
    try:
        result = resolve(args.station, args.id or args.station.startswith("listnr:"))
        if args.validate:
            result = validate(result, args.observe_seconds)
        else:
            result["validation"] = {"status": "not_requested"}
    except ResolutionError as exc:
        print(json.dumps({"error": exc.code, "http_status": exc.status}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
