"""Read-only catalogue discovery with source isolation and evidenced ranking."""

import asyncio
import math
import random
import re
import time
from datetime import UTC, datetime
from uuid import UUID

from .discovery_seeds import AUSTRALIAN_SEEDS, RADIO_SEEDS, reviewed_evidence
from .media_identity import record_ids


def number(value):
    try:
        return float(value) if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def evidence_for(row, *, region=None, curated=None, order=0):
    """Only explicit fields or an identity-bound reviewed record establish facts."""
    metadata = row.get("metadata") or {}
    evidence = {"provider_order": order}
    evidence.update(reviewed_evidence(row, region or {}))
    country = row.get("country_code") or row.get("countrycode")
    if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country):
        evidence["country"] = country.upper()
    languages = metadata.get("languages") or []
    if isinstance(languages, str):
        languages = [languages]
    languages = [*languages, row.get("language"), row.get("languagecodes"), metadata.get("description_language")]
    codes = {part.strip().lower().split("-")[0] for value in languages if isinstance(value, str) for part in value.split(",")}
    if codes & {"en", "eng", "english"}:
        evidence["language"] = "en"
    elif codes:
        evidence["language"] = "other"
    score = number(row.get("clickcount"))
    if score is not None:
        evidence.update(popularity=score, popularity_basis="directory-clicks-24h")
    elif (score := number(metadata.get("popularity"))) is not None:
        evidence.update(popularity=score, popularity_basis="native-provider-score")
    # A reviewed locality record must bind exact native URI AND region identity.
    # A name/query/state substring never establishes locality.
    record = (curated or {}).get(row.get("uri"))
    if record and (region or {}).get("id") and record.get("region_id") == region["id"] and record.get("verified") is True:
        evidence.update(local=True, locality_basis="reviewed-station-identity")
    location = str(row.get("state") or "").casefold().strip()
    terms = {str(t).casefold().strip() for t in (region or {}).get("search_terms", []) if isinstance(t, str) and len(t.strip()) >= 4}
    if evidence.get("country") == "AU" and location and any(re.search(r"\b" + re.escape(term) + r"\b", location) for term in terms):
        evidence.update(local=True, locality_basis="directory-station-region-field")
    evidence["label"] = (
        "Verified local station"
        if evidence.get("local")
        else "Australian station"
        if evidence.get("country") == "AU"
        else "English-language station"
        if evidence.get("language") == "en"
        else "Region and language unverified"
    )
    return evidence


def radio_rank(row):
    evidence = row.get("household_discovery", {})
    tier = 0 if evidence.get("local") else 1 if evidence.get("country") == "AU" else 2 if evidence.get("language") == "en" else 3
    return tier, -evidence.get("popularity", -1), evidence.get("provider_order", 0), str(row.get("name", "")).casefold(), str(row.get("uri", ""))


class MediaDiscovery:
    def __init__(self, command, providers, *, region=None, timeout=6, curated=None, directory_lookup=None):
        self.command, self.providers = command, providers
        self.region, self.timeout = region or {}, timeout
        self.curated = curated or {}
        self.directory_lookup = directory_lookup

    async def radio_landing(self, identity):
        """Browse plus exact-identity fallbacks in parallel, within one read budget."""
        budget = min(3, self.timeout / 2)

        async def popular():
            roots = await self.command("music/browse", path=identity + "://")
            folder = next((r for r in roots if r.get("name") == "By popularity" and r.get("media_type") == "folder"), None)
            rows = await self.command("music/browse", path=folder["path"]) if folder else []
            if not any(r.get("media_type") == "radio" for r in rows):
                folder = next((r for r in rows if r.get("media_type") == "folder" and r.get("name") != ".."), None)
                rows = await self.command("music/browse", path=folder["path"]) if folder else []
            return rows

        async def regional(seed):
            response = await self.command("music/search", search_query=seed[0], providers=[identity], media_types=["radio"], limit=40)
            return [r for r in response.get("radios", response.get("radio", [])) if str(r.get("item_id")) == seed[1]]

        tasks = [popular(), *(regional(seed) for seed in (*RADIO_SEEDS, *AUSTRALIAN_SEEDS))]
        results = await asyncio.gather(*(asyncio.wait_for(task, budget) for task in tasks), return_exceptions=True)
        rows, seen = [], set()
        for result in results:
            if not isinstance(result, list):
                continue
            for row in result:
                key = row.get("uri") or row.get("item_id")
                if key and key not in seen:
                    rows.append(row)
                    seen.add(key)
        if not rows and any(isinstance(r, Exception) for r in results):
            raise RuntimeError("Radio directory is unavailable.")
        return rows, any(isinstance(r, Exception) for r in results)

    async def find(self, category, query, allowed, *, child=False, saved=None):
        if not allowed:
            raise PermissionError("Source assignments are unavailable.")
        if category not in {"radio", "podcast"} or not isinstance(query, str) or len(query) > 120:
            raise ValueError("Choose a supported discovery search.")
        domains = {"radiobrowser", "abc_radio_network", "tunein", "radioparadise"} if category == "radio" else {"itunes_podcasts"}
        sources = [p for p in self.providers.values() if p["instance_id"] in allowed and p.get("domain") in domains and p.get("available")]

        async def source(provider):
            identity = provider["instance_id"]
            try:
                partial = False
                if query.strip():
                    result = await asyncio.wait_for(
                        self.command("music/search", search_query=query.strip(), providers=[identity], media_types=[category], limit=40), self.timeout
                    )
                    rows = result.get("radio" if category == "radio" else "podcasts", [])
                    if category == "radio":
                        rows = result.get("radios", rows)
                elif provider["domain"] == "abc_radio_network":
                    rows = await asyncio.wait_for(self.command("music/browse", path=identity + "://"), self.timeout)
                elif category == "podcast" and provider["domain"] == "itunes_podcasts":
                    # Verified installed 2.10.7 row: public trending, not a
                    # personal recommendation feed or automatic subscription.
                    rows = await asyncio.wait_for(self.command("music/recommendations/items", provider=identity, item_id="itunes-top-podcasts"), self.timeout)
                elif category == "radio" and provider["domain"] == "radiobrowser":
                    rows, partial = await self.radio_landing(identity)
                else:
                    return [], {"source": provider["domain"], "state": "search-needed"}
                directory = {}
                if provider["domain"] == "radiobrowser" and self.directory_lookup:
                    ids = []
                    for row in rows:
                        try:
                            ids.append(str(UUID(str(row.get("item_id")))))
                        except ValueError:
                            pass
                    try:
                        directory = await asyncio.wait_for(self.directory_lookup(ids[:100]), min(3, self.timeout))
                    except Exception:
                        # Optional public metadata enrichment must not take down
                        # otherwise usable, source-filtered native results.
                        directory = {}
                values = []
                for index, row in enumerate(rows):
                    if row.get("media_type") != category:
                        continue
                    # Popularity alone never establishes child suitability.
                    if category == "podcast" and child and (row.get("metadata") or {}).get("explicit") is not False:
                        continue
                    extra = directory.get(row.get("item_id"), {})
                    evidence = evidence_for({**row, **extra}, region=self.region, curated=self.curated, order=index)
                    if provider["domain"] == "abc_radio_network":
                        evidence.update(country="AU", language="en", label="Australian station")
                    if category == "podcast" and evidence.get("language") not in {None, "en"}:
                        continue
                    if category == "podcast":
                        evidence["label"] = "English-language podcast" if evidence.get("language") == "en" else "Podcast language unverified"
                        if not query.strip():
                            evidence["recommendation_basis"] = "general-provider-trending"
                    values.append({**row, "household_discovery": evidence})
                return values, {"source": provider["domain"], "state": "partial" if partial else "ready", "count": len(values)}
            except (TimeoutError, RuntimeError, ValueError, KeyError, TypeError):
                return [], {"source": provider["domain"], "state": "unavailable"}

        async def bounded(provider):
            try:
                return await asyncio.wait_for(source(provider), self.timeout)
            except TimeoutError:
                return [], {"source": provider["domain"], "state": "unavailable"}

        results = await asyncio.gather(*(bounded(p) for p in sources))
        rows = [r for values, _ in results for r in values]
        if category == "radio":
            rows.sort(key=radio_rank)
        else:
            # Exact saved identities can rank an existing show. No tastes are
            # inferred from names, age, account allocation or household history.
            recent = {r.get("uri") for key in ("favorites", "recent") for r in (saved or {}).get(key, []) if r.get("kind") == "podcast"}
            saved_ids = {r.get("id") for key in ("favorites", "recent") for r in (saved or {}).get(key, []) if r.get("kind") == "podcast" and r.get("id")}
            for row in rows:
                if row.get("uri") in recent or record_ids(row) & saved_ids:
                    row["household_discovery"]["recommendation_basis"] = "your-saved-podcast"
            if not query.strip():
                rows.sort(
                    key=lambda r: (
                        r["household_discovery"].get("recommendation_basis") != "your-saved-podcast",
                        r["household_discovery"].get("language") != "en",
                        r["household_discovery"]["provider_order"],
                    )
                )
        return {
            "items": rows,
            "sources": [state for _, state in results],
            "region": self.region.get("name"),
            "personalised": any(r["household_discovery"].get("recommendation_basis") == "your-saved-podcast" for r in rows),
            "note": (
                "Search existing catalogues. No subscriptions or favourites are added. "
                "Language/locality is unverified where provider metadata is absent. "
                "Personal recommendations need explicit interests or attributed listening evidence."
            ),
        }


MODES = {"anything", "familiar", "era", "genre"}
TOKENS = ("love", "night", "blue", "sun", "dance", "dream", "road", "home", "wild", "world", "time", "light", "rain", "river", "heart", "gold")
GENRES = ("rock", "pop", "jazz", "soul", "folk", "classical", "country", "electronic", "reggae", "blues", "disco", "funk", "metal", "ambient")


def constraints(value):
    if not isinstance(value, dict) or set(value) - {"mode", "era", "genre", "genres", "exclude_explicit", "reseed_tracks", "reseed_minutes"}:
        raise ValueError("Choose supported discovery settings.")
    result = {"mode": "anything", "reseed_tracks": 8, "reseed_minutes": 35, **value}
    if result["mode"] not in MODES:
        raise ValueError("Choose a supported discovery mode.")
    if result["mode"] == "era" and result.get("era") not in {*range(1960, 2030, 10), "current"}:
        raise ValueError("Choose a decade or current music.")
    if result["mode"] == "genre" and not valid_token(result.get("genre")):
        raise ValueError("Choose a music genre.")
    if "genres" in result and (not isinstance(result["genres"], list) or len(result["genres"]) > 12 or any(not valid_token(g) for g in result["genres"])):
        raise ValueError("Choose up to twelve preferred genres.")
    if any(type(result[k]) is not int or not low <= result[k] <= high for k, low, high in [("reseed_tracks", 3, 30), ("reseed_minutes", 10, 120)]):
        raise ValueError("Choose a reseed interval of 3–30 tracks or 10–120 minutes.")
    if "exclude_explicit" in result and type(result["exclude_explicit"]) is not bool:
        raise ValueError("Choose an explicit-content preference.")
    return result


def valid_token(value):
    return isinstance(value, str) and 1 <= len(value) <= 40 and all(c.isalpha() or c in " -&" for c in value)


class Discovery:
    def __init__(self, rng=None, clock=time.time):
        self.rng, self.clock = rng or random.SystemRandom(), clock
        self.recent = []

    def seed(self, options):
        options = constraints(options)
        year = datetime.now(UTC).year
        strategy = self.rng.choice(("year", "token", "genre", "decade"))
        token = self.rng.choice(TOKENS)
        genre = self.rng.choice(options.get("genres") or GENRES)
        if options["mode"] == "genre":
            genre = options["genre"]
            strategy = self.rng.choice(("genre", "genre-year", "genre-token"))
        elif options["mode"] == "familiar" and options.get("genres"):
            strategy = self.rng.choice(("genre", "genre-year", "genre-token", "year"))
        if options["mode"] == "era":
            first = year - 2 if options["era"] == "current" else options["era"]
            last = year if options["era"] == "current" else min(year, first + 9)
            picked = self.rng.randint(first, last)
            return "era", f"year:{picked} {token}" if self.rng.choice((True, False)) else f"year:{first}-{last} {token}"
        picked = self.rng.randint(1960, year)
        queries = {
            "year": f"year:{picked}",
            "token": token,
            "genre": f'genre:"{genre}"',
            "decade": f"year:{picked // 10 * 10}-{min(year, picked // 10 * 10 + 9)} {token}",
            "genre-year": f'genre:"{genre}" year:{picked}',
            "genre-token": f'genre:"{genre}" {token}',
        }
        return strategy, queries[strategy]

    def prune(self):
        self.recent = [r for r in self.recent if 0 <= self.clock() - r["at"] < 7200][-60:]

    def remember(self, track):
        self.prune()
        self.recent.append(
            {
                "id": track["item_id"],
                "album": (track.get("album") or {}).get("item_id"),
                "artists": [a.get("item_id") or a.get("name") for a in track.get("artists", [])],
                "at": self.clock(),
            }
        )

    def playable(self, track, provider, options):
        if not isinstance(track, dict) or track.get("media_type") != "track" or not track.get("item_id"):
            return False
        if not any(m.get("provider_instance") == provider and m.get("available") is True for m in track.get("provider_mappings", [])):
            return False
        if options.get("exclude_explicit") and (track.get("metadata") or {}).get("explicit") is not False:
            return False  # Unknown explicit status fails closed for restricted listeners.
        artists = {a.get("item_id") or a.get("name") for a in track.get("artists", [])}
        album = (track.get("album") or {}).get("item_id")
        return not any(r["id"] == track["item_id"] or album and album == r["album"] or artists & set(r["artists"]) for r in self.recent)

    async def choose(self, search, provider, options):
        options = constraints(options)
        self.prune()
        for _ in range(6):
            strategy, query = self.seed(options)
            try:
                tracks = await search(query, 50)
            except Exception:
                tracks = []  # Try another bounded catalogue query; never a library fallback.
            candidates = [t for t in tracks if self.playable(t, provider, options)]
            if candidates:
                chosen = self.rng.choice(candidates)
                self.remember(chosen)
                return chosen, {"strategy": strategy, "query": query, "exclusion_count": len(self.recent)}
        raise ValueError("Spotify catalogue discovery is unavailable. Try again or choose another source.")
