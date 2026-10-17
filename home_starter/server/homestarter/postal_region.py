"""Find an approximate postcode locally from public country-wide centroid data.

GeoNames postal data: https://download.geonames.org/export/zip/ (attribution licence; see its readme).
No home coordinate or address is sent to GeoNames. Only a consented postcode
may subsequently be sent to a radio catalogue's regional lookup.
"""

import io
import time
import zipfile

import aiohttp

from .listnr import CatalogueError, distance

_cache = {}


def nearest_postcode(raw, country, home, terms=()):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entry = archive.getinfo(country + ".txt")
        if entry.file_size > 20_000_000:
            raise ValueError("Postal catalogue is too large.")
        text = archive.read(entry).decode("utf-8")
    best = None
    matched = []
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 11 or fields[0] != country:
            continue
        km = distance({"latitude": fields[9], "longitude": fields[10]}, home)
        if any(fields[2].casefold() == term.casefold().strip() for term in terms):
            matched.append((km if km is not None else 0, fields[1]))
        if km is not None and (best is None or km < best[0]):
            best = km, fields[1]
    if matched:
        return min(matched)[1]  # Explicit configured region wins over an old/default HA home zone.
    if not best or best[0] > 100:
        raise ValueError("The home region could not be matched to postal data.")
    return best[1]


async def postcode(country, home, terms=()):
    # LiSTNR's postcode catalogue currently describes Australia, not arbitrary countries.
    if country != "AU":
        raise ValueError("Regional lookup is unavailable for this country.")
    cached = _cache.get(country)
    if not cached or time.monotonic() - cached[0] > 86400:
        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get("https://download.geonames.org/export/zip/AU.zip", allow_redirects=False) as response:
                    if response.status != 200:
                        raise CatalogueError("postal_catalogue_unavailable")
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise CatalogueError("postal_catalogue_unavailable")
            _cache[country] = time.monotonic(), bytes(raw)
        except (aiohttp.ClientError, TimeoutError, OSError):
            raise CatalogueError("postal_catalogue_unavailable") from None
    try:
        return nearest_postcode(_cache[country][1], country, home, terms)
    except (zipfile.BadZipFile, KeyError, UnicodeError, ValueError):
        raise CatalogueError("postal_catalogue_unavailable") from None
