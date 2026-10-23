"""Reviewed public catalogue identities; suggestions, never saved subscriptions.

RadioBrowser UUIDs read back 23 October 2026 and matched to the broadcasters'
public Border station pages. Language is recorded only where explicitly supplied
by the directory/feed. No stream/session URLs, account IDs or home coordinates.
"""

RADIO_SEEDS = (
    ("Triple M The Border", "1964e4d2-1395-4586-9f7f-2c2e91c49497", "en", "https://triplem.listnr.com/the-border/"),
    ("hit104.9", "960358b8-91d4-4394-954f-a5a6d956691e", "en", "https://hit.listnr.com/the-border/"),
    ("2AY", "31a5ca57-a995-4363-bad8-f62668331e79", None, "https://2ay.com.au/"),
)

# Australian English-language directory records, including public broadcasters.
# This is a reviewed discovery fallback, not a fixed/live popularity ranking.
AUSTRALIAN_SEEDS = (
    ("SBS Chill", "0ed4232a-a293-11e8-abb8-52543be04c81", "en", "https://www.sbs.com.au/radio/chill"),
    ("ABC NewsRadio", "9615d27a-0601-11e8-ae97-52543be04c81", "en", "https://www.abc.net.au/newsradio/"),
    ("ABC Radio National", "9616206e-0601-11e8-ae97-52543be04c81", "en", "https://www.abc.net.au/radionational/"),
    ("Triple J", "06faec0e-52eb-11e8-a4d1-52543be04c81", "en", "https://www.abc.net.au/triplej/"),
    ("3AW", "94ab6f5f-b684-4ca1-ae5c-c5c868ed20c6", "en", "https://www.3aw.com.au/"),
    ("Gold 104.3", "a4c32662-98bc-42bd-b05b-dcf656272369", "en", "https://www.gold1043.com.au/"),
    ("Smooth FM 95.3", "f7c04bff-1317-478b-8f00-736b9d89dc31", "en", "https://smooth.com.au/station/smoothfm953"),
)

# Feed <language> read directly; no recommendation is inferred from a title.
ENGLISH_PODCAST_FEEDS = {
    "https://www.abc.net.au/feeds/7711104/podcast.xml",
    "https://www.abc.net.au/feeds/103599966/podcast.xml",
    "https://rss2.flightcast.com/imzibs9ivjda8knahyaer2f0.xml",
    "https://feeds.megaphone.fm/GLT5336643697",
}


def reviewed_evidence(row, region):
    mappings = row.get("provider_mappings") or []
    if row.get("media_type") == "podcast" and any(
        m.get("provider_domain") == "itunes_podcasts" and m.get("item_id") in ENGLISH_PODCAST_FEEDS for m in mappings
    ):
        return {"language": "en"}
    ids = {str(m.get("item_id")) for m in mappings if m.get("provider_domain") == "radiobrowser"}
    if row.get("provider") == "radiobrowser":
        ids.add(str(row.get("item_id")))
    record = next((r for r in (*RADIO_SEEDS, *AUSTRALIAN_SEEDS) if r[1] in ids), None)
    if not record:
        return {}
    evidence = {"country": "AU"}
    if record[2]:
        evidence["language"] = record[2]
    # Exact station identity proves its regional service, not the home's location.
    # Activate this local section only for the already configured Border region.
    terms = " ".join([str(region.get("name", "")), *region.get("search_terms", [])]).casefold()
    if record in RADIO_SEEDS and ("albury" in terms or "wodonga" in terms):
        evidence.update(local=True, locality_basis="reviewed-station-identity")
    return evidence
