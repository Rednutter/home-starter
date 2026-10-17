"""MA-only library policy: disable upstream writes before any optional cleanup."""

HYGIENE = {
    "library_sync_back": False,
    "library_sync_tracks": False,
    "library_sync_albums": False,
    "library_sync_artists": False,
    "library_sync_playlists": True,
    "library_sync_playlist_tracks": [],
    "library_sync_album_tracks": False,
}


async def inspect_policy(mass, prepare=False):
    rows = []
    for provider in list(mass.providers):
        if provider.domain != "spotify":
            continue
        config = await mass.config.get_provider_config(provider.instance_id)
        desired = {k: v for k, v in HYGIENE.items() if k in config.values}
        changes = {k: v for k, v in desired.items() if config.get_value(k) != v}
        if prepare and changes:
            # Persist and read back the safety boundary independently, first.
            await mass.config.save_provider_config("spotify", {"library_sync_back": False}, provider.instance_id)
            safe = await mass.config.get_provider_config(provider.instance_id)
            if safe.get_value("library_sync_back") is not False:
                raise ValueError("Spotify library write-back could not be disabled. Cleanup is blocked.")
            await mass.config.save_provider_config("spotify", changes, provider.instance_id)
            config = await mass.config.get_provider_config(provider.instance_id)
        rows.append(
            {
                "provider": provider.instance_id,
                "state": "connected" if set(desired) == set(HYGIENE) and all(config.get_value(k) == v for k, v in desired.items()) else "needs_attention",
                "settings": {k: config.get_value(k) for k in desired},
            }
        )
    return rows


async def cleanup(mass, apply=False):
    """Remove only imported Spotify mappings through MA's local controller.

    Never invoke music.remove_item_from_library (which can call library_remove).
    Keep mappings from other providers. Repeat after a partial failure is safe.
    """
    providers = {p.instance_id for p in mass.providers if p.domain == "spotify"}
    for provider in providers:
        config = await mass.config.get_provider_config(provider)
        if config.get_value("library_sync_back") is not False or config.get_value("library_sync_tracks") is not False:
            raise ValueError("Apply safe Spotify library settings before reviewing cleanup.")
    candidates = []
    offset = 0
    while True:
        batch = await mass.music.tracks.library_items(provider=list(providers), offset=offset, limit=500, summary=False)
        for item in batch:
            for mapping in item.provider_mappings:
                if mapping.provider_instance in providers and mapping.in_library is True:
                    candidates.append((item.item_id, mapping.provider_instance, mapping.item_id))
        offset += len(batch)
        if len(batch) < 500:
            break
    if apply:
        for item, provider, track in candidates:
            config = await mass.config.get_provider_config(provider)
            if config.get_value("library_sync_back") is not False or config.get_value("library_sync_tracks") is not False:
                raise ValueError("Spotify settings changed. Cleanup stopped safely.")
            await mass.music.tracks.remove_provider_mapping(item, provider, track)
    return {"state": "connected", "imported_mappings": len(candidates), "removed": len(candidates) if apply else 0, "spotify_items_changed": False}
