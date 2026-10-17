"""Exercise stream resolution, cached buffers and background chunks under the guard."""

import asyncio
import json
import logging
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock

import pytest
from homestarter.ma_account_guard import AccountGuard, _pin
from homestarter.spotify_leases import AccountsBusy


class Audio:
    def __init__(self, providers):
        self.providers = providers
        self.candidates = []
        self.match_attempts = 0
        self.fail_provider = None
        self.closed = False

    def _get_mapping_providers(self, mapping):
        return self.providers  # MA normally widens a Spotify mapping to all siblings.

    async def _discover_alternative_provider_mappings(self, queue_item, busy_instances, remaining):
        self.match_attempts += 1
        return {"fixture-escape"}

    async def get_stream_details(self, queue_item, seek_position=0, fade_in=False, prefer_album_loudness=False, excluded_provider_instances=None):
        if queue_item.streamdetails and queue_item.streamdetails.provider not in (excluded_provider_instances or set()):
            return queue_item.streamdetails
        candidates = [p for p in self._get_mapping_providers(None) if p.instance_id not in (excluded_provider_instances or set())]
        self.candidates.append([p.instance_id for p in candidates])
        assert len(candidates) == 1
        queue_item.streamdetails = Obj(provider=candidates[0].instance_id, queue_id=queue_item.queue_id, queue_session_id="session-" + queue_item.queue_id)
        return queue_item.streamdetails

    async def get_audio_buffer(self, queue_item, seek_position_ms=0, reason="", capacity_wait_timeout=10, allow_provider_match=True):
        if not queue_item.streamdetails:
            await self.get_stream_details(queue_item)
        if queue_item.streamdetails.provider == self.fail_provider:
            if allow_provider_match:
                await self._discover_alternative_provider_mappings(queue_item, set(), 10)
            raise ValueError("Fixture provider saturated")
        return Obj(provider=queue_item.streamdetails.provider)

    async def get_media_stream(self, streamdetails, *args, **kwargs):
        try:
            for _ in range(4):
                await asyncio.sleep(0)
                yield b"synthetic-audio"
        finally:
            self.closed = True


@pytest.fixture
def guarded(tmp_path):
    providers = [
        Obj(instance_id=n.lower(), name=n, domain="spotify", available=True, _sp_user={"id": "fixture-" + n}) for n in ("Grant", "Renae", "House", "House #2")
    ]
    for provider in providers:
        provider.get_setup_value = lambda key, p=provider: json.dumps({"username": p._sp_user["id"]}) if key == "librespot_credentials" else "librespot"
    audio = Audio(providers)
    queues, data = {}, {}
    for i in range(4):
        pid = "q" + str(i)
        item = Obj(queue_id=pid, queue_item_id="item-" + pid, media_item=Obj(provider_mappings=[Obj(provider_domain="spotify")]), streamdetails=None)
        queues[pid] = Obj(queue_id=pid, current_item=item, state="playing")
        data[pid] = Obj(queue=queues[pid], items=[item], session_id="session-" + pid, userid="Edie")
    mass = Obj(
        version="2.10.6",
        providers=providers,
        storage_path=str(tmp_path),
        streams=Obj(audio=audio),
        player_queues=Obj(all=lambda: list(queues.values()), queue_data_or_none=data.get),
        webserver=Obj(auth=Obj(get_user=AsyncMock(side_effect=lambda name: Obj(display_name=name, username=name)))),
    )
    guard = AccountGuard(mass)
    guard.engine.grant_state = AsyncMock(return_value="idle")
    guard.wrap()
    yield guard, mass, queues, data, audio
    logging.getLogger("music_assistant").removeHandler(guard.log_handler)


async def test_resolver_isolates_concurrent_queues_and_cached_streamdetails(guarded):
    guard, mass, queues, data, audio = guarded
    queues["q0"].current_item.streamdetails = Obj(provider="grant", queue_id="q0", queue_session_id="old")
    queues["q0"].state = "idle"  # cached previous playback, not a live Grant session
    results = await asyncio.gather(*(audio.get_stream_details(queues[f"q{i}"].current_item) for i in range(4)), return_exceptions=True)
    assert [r.provider for r in results[:3]] == ["house", "house #2", "grant"]
    assert isinstance(results[3], AccountsBusy)
    assert all(len(c) == 1 and c[0] != "renae" for c in audio.candidates)
    assert (await guard.status())["isolated"] is True


async def test_capacity_failure_cannot_cross_accounts_or_match_other_sources(guarded):
    guard, mass, queues, data, audio = guarded
    item = queues["q0"].current_item
    audio.fail_provider = "house"
    with pytest.raises(ValueError, match="saturated"):
        await audio.get_audio_buffer(item)
    assert item.streamdetails.provider == "house"
    assert not audio.match_attempts
    assert audio.candidates == [["house"]]
    assert guard.playback_checks["house"]["state"] == "connected_but_incomplete"
    restored = AccountGuard(mass)
    assert restored.playback_checks == guard.playback_checks


async def test_revoked_stream_closes_before_emitting_more_audio(guarded):
    guard, mass, queues, data, audio = guarded
    item = queues["q0"].current_item
    await audio.get_audio_buffer(item)
    chunks = audio.get_media_stream(item.streamdetails)
    assert await anext(chunks) == b"synthetic-audio"
    await guard.engine.release(guard.engine.leases["house"]["token"])
    with pytest.raises(AccountsBusy, match="ended"):
        await anext(chunks)
    assert audio.closed


async def test_old_stream_cannot_attach_to_new_session(guarded):
    guard, mass, queues, data, audio = guarded
    item = queues["q0"].current_item
    old = await audio.get_stream_details(item)
    data["q0"].session_id = "replacement"
    await guard.engine.recover(guard.providers())
    with pytest.raises(AccountsBusy):
        await anext(audio.get_media_stream(old))
    queues["q0"].current_item = Obj(queue_id="q0", queue_item_id="new-item", media_item=item.media_item, streamdetails=None)
    data["q0"].items = [queues["q0"].current_item]
    with pytest.raises(AccountsBusy, match="session changed"):
        await audio.get_stream_details(item)


async def test_personal_accounts_stay_personal_and_radio_is_unaffected(guarded):
    guard, mass, queues, data, audio = guarded
    data["q0"].userid = "Renae"
    assert (await audio.get_stream_details(queues["q0"].current_item)).provider == "renae"
    data["q1"].userid = "Grant"
    assert (await audio.get_stream_details(queues["q1"].current_item)).provider == "grant"
    radio = Obj(queue_id="unused", media_item=Obj(provider_mappings=[Obj(provider_domain="radio")]), streamdetails=Obj(provider="radio"))
    assert (await audio.get_stream_details(radio)).provider == "radio"


async def test_drift_in_resolver_registration_is_unhealthy(guarded):
    guard, mass, queues, data, audio = guarded
    audio._get_mapping_providers = lambda mapping: mass.providers
    assert (await guard.status())["isolated"] is False


async def test_two_labels_cannot_disguise_the_same_spotify_account(guarded):
    guard, mass, queues, data, audio = guarded
    mass.providers[-1]._sp_user = mass.providers[-2]._sp_user
    assert (await guard.status())["isolated"] is False
    with pytest.raises(AccountsBusy, match="identities"):
        await audio.get_stream_details(queues["q0"].current_item)


async def test_library_and_audio_credentials_must_belong_to_same_account(guarded):
    guard, mass, queues, data, audio = guarded
    mass.providers[-1].get_setup_value = lambda key: '{"username":"fixture-wrong-person"}' if key == "librespot_credentials" else "librespot"
    assert (await guard.status())["isolated"] is False
    with pytest.raises(AccountsBusy, match="identities"):
        await audio.get_stream_details(queues["q0"].current_item)


async def test_soloist_needs_explicit_consent_key_and_matching_pairing(guarded, monkeypatch):
    guard, mass, queues, data, audio = guarded
    p = mass.providers[-1]
    settings = {"playback_backend": "soloist", "soloist_download_consent": False, "soloist_api_key": object()}
    p.get_setup_value = settings.get
    monkeypatch.setattr(guard, "soloist_account", lambda provider: provider._sp_user["id"])
    assert not guard.account_integrity()[0]
    settings["soloist_download_consent"] = True
    assert guard.account_integrity()[0]
    monkeypatch.setattr(guard, "soloist_account", lambda provider: "fixture-wrong-person")
    assert not guard.account_integrity()[0]


async def test_audio_key_failure_is_distinct_from_login_and_raw_logs_are_not_saved(guarded):
    guard, mass, queues, data, audio = guarded
    lease = await guard.bind(queues["q0"].current_item)
    marker = _pin.set(lease)
    try:
        logging.getLogger("music_assistant.spotify").warning("error audio key 0 1 synthetic-private-sentinel")
        guard.record_playback(lease["provider"], "connected_but_incomplete")
    finally:
        _pin.reset(marker)
    assert guard.playback_checks[lease["provider"]]["issue"] == "audio_key_unavailable"
    assert "synthetic-private-sentinel" not in guard.check_path.read_text()
    guard.record_playback(lease["provider"], "connected")
    assert guard.playback_checks[lease["provider"]]["issue"] is None


async def test_guard_maps_authenticated_identity_without_renaming_provider(guarded):
    guard, mass, queues, data, audio = guarded
    renae = mass.providers[1]
    renae.name = "Spotify"
    await guard.configure_accounts({"Renae": renae.instance_id})
    assert renae.name == "Spotify"
    data["q0"].userid = "Renae"
    assert (await audio.get_stream_details(queues["q0"].current_item)).provider == renae.instance_id
    restored = AccountGuard(mass)
    assert restored.identities == {"Renae": renae.instance_id}
    with pytest.raises(ValueError, match="two household identities"):
        await guard.configure_accounts({"Grant": renae.instance_id})


async def test_old_buffer_cannot_inherit_a_new_lease_via_mutated_streamdetails(guarded):
    guard, mass, queues, data, audio = guarded
    item = queues["q0"].current_item
    await audio.get_audio_buffer(item)
    old = item.streamdetails
    chunks = audio.get_media_stream(old)
    assert await anext(chunks) == b"synthetic-audio"
    previous = guard.engine.leases["house"]["token"]
    data["q0"].session_id = "replacement"
    replacement = Obj(queue_id="q0", queue_item_id="replacement-item", media_item=item.media_item, streamdetails=None)
    data["q0"].items = [replacement]
    queues["q0"].current_item = replacement
    lease = await guard.bind(replacement)
    assert lease["provider"] == "house" and lease["token"] != previous
    old.queue_session_id = "replacement"  # MA can mutate cached details while reusing them.
    with pytest.raises(AccountsBusy, match="ended"):
        await anext(chunks)
    assert audio.closed


async def test_native_source_replacement_releases_confirmed_account_without_stopping_it(guarded):
    guard, mass, queues, data, audio = guarded
    await audio.get_audio_buffer(queues["q0"].current_item)
    await guard.engine.recover(guard.providers())
    assert guard.engine.leases["house"]["confirmed"]
    queues["q0"].active = False
    await guard.engine.recover(guard.providers())
    assert "house" not in guard.engine.leases


@pytest.mark.parametrize("active", ["playing", "paused", "replaced", "untracked", "same_session"])
async def test_soloist_settles_only_recorded_revoked_native_runs(guarded, active):
    guard, mass, queues, data, _ = guarded

    class Run:
        pass

    old, new = Run(), Run()
    owner = {"provider": "house", "queue": "q0", "session": "session-q0", "token": "old"}
    lease = {**owner, "queue": "q1", "session": "session-q1", "token": "new"}
    if active == "same_session":
        lease = dict(owner)
    if active != "untracked":
        guard.soloist_runs[old] = dict(owner)
    queues["q0"].state = "paused" if active == "paused" else "playing"
    if active == "replaced":
        data["q0"].session_id = "replacement"
    guard.engine.leases["house"] = dict(lease)
    backend = Obj(_run=old, provider=Obj(instance_id="house"), discard_run=AsyncMock())
    original = AsyncMock(return_value=new)
    marker = _pin.set(lease)
    try:
        assert await guard.soloist_acquire(original, backend, "spotify:track:fixture") is new
    finally:
        _pin.reset(marker)
    assert backend.discard_run.await_count == (1 if active == "replaced" else 0)
    assert guard.soloist_runs[new] == lease


async def test_soloist_revoked_request_cannot_release_a_recorded_run(guarded):
    guard, _, _, data, _ = guarded

    class Run:
        pass

    old = Run()
    owner = {"provider": "house", "queue": "q0", "session": "session-q0", "token": "old"}
    guard.soloist_runs[old] = owner
    data["q0"].session_id = "replacement"
    backend = Obj(_run=old, provider=Obj(instance_id="house"), discard_run=AsyncMock())
    original = AsyncMock()
    marker = _pin.set({**owner, "session": "revoked", "token": "revoked"})
    try:
        with pytest.raises(AccountsBusy, match="reservation changed"):
            await guard.soloist_acquire(original, backend)
    finally:
        _pin.reset(marker)
    backend.discard_run.assert_not_awaited()
    original.assert_not_awaited()
