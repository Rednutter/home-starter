"""Provider catalogue discovery and short-lived repeat exclusion; no library access."""

import random
import time
from datetime import UTC, datetime

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
