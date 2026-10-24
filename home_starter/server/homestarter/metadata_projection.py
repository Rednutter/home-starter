"""Read-only native media models with explicit attribution and scoped artwork."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from urllib.parse import urlsplit

from .listening_collections import merge
from .media_identity import record_ids as record_ids
from .playlist_visibility import identities as playlist_identities
from .playlist_visibility import rule_for, visible

KINDS = {"artists": "artist", "albums": "album", "tracks": "track", "playlists": "playlist", "radios": "radio", "podcasts": "podcast"}
MODEL_FIELDS = {
    "item_id",
    "provider",
    "name",
    "sort_name",
    "uri",
    "media_type",
    "version",
    "is_playable",
    "external_ids",
    "favorite",
    "provider_mappings",
    "metadata",
    "artist_type",
    "artists",
    "album",
    "album_type",
    "year",
    "duration",
    "disc_number",
    "track_number",
    "position",
    "is_dynamic",
    "is_editable",
    "supported_mediatypes",
}


ARTWORK_HOSTS = {
    "i.scdn.co",
    "mosaic.scdn.co",
    "image-cdn-fa.spotifycdn.com",
    "images.fanart.tv",
    "assets.fanart.tv",
    "www.theaudiodb.com",
    "theaudiodb.com",
    "lastfm.freetls.fastly.net",
    "coverartarchive.org",
    # Native MA-issued image IDs only; these public broadcasters/podcast CDNs
    # were read from actual catalogue/feed artwork, never supplied by a client.
    "images.ctfassets.net",
    "www.abc.net.au",
    "live-production.wcms.abc-cdn.net.au",
    "is1-ssl.mzstatic.com",
    "www.omnycontent.com",
    "files.flightcast.com",
    "megaphone.imgix.net",
}


def approved_image(image):
    if not isinstance(image, dict) or not isinstance(image.get("provider"), str) or not isinstance(image.get("path"), str):
        return False
    try:
        url = urlsplit(image["path"])
        return url.scheme == "https" and url.hostname in ARTWORK_HOSTS and not url.username and not url.password and url.port in {None, 443}
    except ValueError:
        return False


def native_artwork_path(image):
    """Only MA-issued opaque image IDs, never a client URL or legacy URL proxy."""
    identity = image.get("proxy_id") if isinstance(image, dict) else None
    if approved_image(image) and isinstance(identity, str) and re.fullmatch(r"[a-f0-9]{64}", identity):
        return "/imageproxy/" + identity + "?size=512"
    return None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_ids(row):
    return {m.get("provider_instance") for m in row.get("provider_mappings", []) if isinstance(m, dict)} | {row.get("provider")}


def native_record(row, allowed):
    """Keep real native models, but never expose credentials or upstream owners."""
    if not isinstance(row, dict) or not source_ids(row) & set(allowed):
        return None
    result = {key: copy.deepcopy(value) for key, value in row.items() if key in MODEL_FIELDS - {"metadata"}}
    result["provider_mappings"] = [
        {k: v for k, v in m.items() if k in {"item_id", "provider_instance", "provider_domain", "available", "in_library", "audio_format"}}
        for m in result.get("provider_mappings", [])
        if m.get("provider_instance") in allowed
    ]
    for mapping in result["provider_mappings"]:
        # Native cards require the AudioFormat shape even when source metadata
        # omits quality. Unknown defaults must not blank the entire collection.
        audio = mapping.get("audio_format")
        audio = audio if isinstance(audio, dict) else {}
        mapping["audio_format"] = {
            key: audio.get(key, default) for key, default in {"content_type": "unknown", "sample_rate": 0, "bit_depth": 0, "channels": 0}.items()
        }
    metadata = row.get("metadata") or {}
    result["metadata"] = {
        key: copy.deepcopy(value)
        for key, value in metadata.items()
        if key in {"genres", "description", "description_language", "explicit", "release_date", "label"}
    }
    image = next((i for i in metadata.get("images") or [] if isinstance(i, dict) and i.get("type") == "thumb" and approved_image(i)), None)
    result["metadata"]["images"] = [copy.deepcopy(image)] if image else []
    for key in ("artists",):
        if isinstance(result.get(key), list):
            nested = []
            for item in result[key]:
                value = native_record(item, allowed)
                if value is None and isinstance(item, dict) and item.get("provider") == "library":
                    # Native ItemMappings inherit their display name from this
                    # already admitted parent; standalone access is still checked.
                    value = {
                        k: copy.deepcopy(v)
                        for k, v in item.items()
                        if k in {"item_id", "provider", "uri", "media_type", "name", "sort_name", "version", "is_playable"}
                    }
                    value["available"] = True
                if value:
                    nested.append(value)
            result[key] = nested
    if isinstance(result.get("album"), dict):
        result["album"] = native_record(result["album"], allowed)
    result["is_editable"] = False
    if isinstance(row.get("household_discovery"), dict):
        result["household_discovery"] = {
            k: v
            for k, v in row["household_discovery"].items()
            if k in {"local", "country", "language", "provider_order", "popularity", "popularity_basis", "locality_basis", "label", "recommendation_basis"}
        }
    result["household_provenance"] = sorted(source_ids(result) & set(allowed))
    return result


def visible_playlist(row, profile, rules, saved):
    rule = rule_for(row, rules) or rules.get(row.get("uri"))
    if playlist_identities(row) & rules.keys():
        return visible(rule, profile)
    if rule:
        return visible(rule, profile)
    # A saved personal reference is visibility evidence, not upstream ownership.
    return bool(record_ids(row) & set(saved))


def project(rows, category, profile, allowed, *, saved=(), playlist_rules=None):
    if category not in KINDS or not allowed:
        raise PermissionError("Catalogue source assignments are unavailable.")
    values, unassigned = [], 0
    for raw in rows:
        row = native_record(raw, allowed)
        if not row or row.get("media_type") != KINDS[category]:
            continue
        if category == "playlists" and not visible_playlist(row, profile, playlist_rules or {}, saved):
            unassigned += 1
            continue
        # Personal saved pages do not become copies of the shared library.
        if profile != "house" and category != "playlists" and not record_ids(row) & set(saved):
            continue
        values.append(row)
    return merge(values, KINDS[category]), unassigned


class ArtworkLedger:
    """Only registered native image references; no client-supplied URL fetch."""

    def __init__(self):
        self.contexts = {}
        self.images = {}

    def select(self, context, profile, generation, policy):
        if type(generation) is not int or generation < 0:
            raise PermissionError("Refresh the metadata view.")
        old = self.contexts.get(context)
        if old and (generation < old["generation"] or generation == old["generation"] and profile != old["profile"]):
            raise PermissionError("This profile request was superseded.")
        self.contexts[context] = {"profile": profile, "generation": generation, "policy": policy}
        if old and (old["profile"] != profile or old["policy"] != policy):
            self.images = {k: v for k, v in self.images.items() if v["context"] != context}

    def register(self, context, model, selection=None):
        selected = self.contexts[context]
        if selection is not None and selected != selection:
            raise PermissionError("This metadata request was superseded.")
        result = copy.deepcopy(model)
        images = (result.get("metadata") or {}).get("images") or []
        image = next((i for i in images if i.get("type") == "thumb" and approved_image(i)), None)
        result.setdefault("metadata", {})["images"] = []
        if image:
            identity = fingerprint([context, selected, result.get("uri"), image])
            self.images[identity] = {"context": context, "selection": dict(selected), "reference": image, "sources": source_ids(result)}
            result["metadata"]["images"] = [{"type": "thumb", "provider": "builtin", "path": "/art/" + identity, "remotely_accessible": True}]
        for key in ("artists",):
            if isinstance(result.get(key), list):
                result[key] = [self.register(context, value, selection) for value in result[key]]
        if isinstance(result.get("album"), dict):
            result["album"] = self.register(context, result["album"], selection)
        return result

    def reference(self, context, identity, policy, allowed):
        record = self.images.get(identity)
        current = self.contexts.get(context)
        if (
            not record
            or record["context"] != context
            or not current
            or any(current[key] != record["selection"][key] for key in ("profile", "policy"))
            or current["policy"] != policy
            or not record["sources"] & set(allowed)
        ):
            raise PermissionError("Artwork is unavailable for this profile.")
        return dict(record["reference"])
