"""Real reservation engine, synthetic observations; no Spotify credentials."""

import asyncio
from copy import deepcopy

import pytest
from homestarter.spotify_leases import AccountsBusy, SpotifyLeases


@pytest.fixture
def accounts():
    return [{"id": n.lower(), "name": n, "domain": "spotify", "available": True} for n in ("House", "House #2", "Grant", "Renae")]


@pytest.fixture
def authority(tmp_path):
    rows, personal, now, stops = {}, ["idle"], [1000], []

    async def observe():
        return deepcopy(rows)

    async def grant():
        return personal[0]

    async def stop(lease):
        stops.append(deepcopy(lease))
        row = rows.get(lease["queue"])
        if row and row["session"] == lease["session"]:
            rows.pop(lease["queue"])
            return True
        return False

    engine = SpotifyLeases(tmp_path / "leases.json", observe, grant, stop, clock=lambda: now[0])
    return engine, rows, personal, now, stops


async def test_concurrent_allocator_is_deterministic_and_never_uses_renae(authority, accounts):
    engine, rows, personal, now, stops = authority
    results = await asyncio.gather(
        *(engine.reserve(accounts, f"q{i}", f"s{i}", n) for i, n in enumerate(("Edie", "Maddie", "Flynn", "House"))), return_exceptions=True
    )
    assert [r["provider"] for r in results[:3]] == ["house", "house #2", "grant"]
    assert isinstance(results[3], AccountsBusy)
    assert "renae" not in engine.leases
    assert not stops
    # A duplicate request is the same reservation, including after restart.
    other = SpotifyLeases(engine.path, engine.observe, engine.grant_state, engine.stop, clock=engine.clock)
    assert await other.reserve(accounts, "q0", "s0", "Edie") == results[0]


async def test_unknown_or_personal_grant_never_becomes_overflow(authority, accounts):
    engine, rows, personal, now, stops = authority
    for n in ("house", "house #2"):
        rows[n] = {"session": "native", "provider": n, "state": "playing"}
    for state in ("unknown", "personal", "owned", None):
        personal[0] = state
        with pytest.raises(AccountsBusy):
            await engine.reserve(accounts, "shared", "new", "Edie")
    assert not engine.leases and not stops
    # Renae remains personal-only, and her missing provider is not a fallback.
    assert (await engine.reserve(accounts, "personal", "one", "Renae"))["provider"] == "renae"
    with pytest.raises(AccountsBusy):
        await engine.reserve(accounts[:-1], "other", "two", "Renae")


async def test_grant_personal_preempts_only_confirmed_owned_overflow(authority, accounts):
    engine, rows, personal, now, stops = authority
    for i, n in enumerate(("Edie", "Maddie", "Flynn")):
        lease = await engine.reserve(accounts, f"q{i}", f"s{i}", n)
        rows[f"q{i}"] = {"session": f"s{i}", "provider": lease["provider"], "state": "playing"}
    personal[0] = "personal"
    result = await engine.reserve(accounts, "grant-personal", "personal", "Grant")
    assert result["provider"] == "grant"
    assert [r["queue"] for r in stops] == ["q2"]
    assert {"q0", "q1"} <= rows.keys()
    # Never stop a native personal session to make room for shared playback.
    rows["grant-personal"] = {"session": "personal", "provider": "grant", "state": "playing"}
    with pytest.raises(AccountsBusy):
        await engine.reserve(accounts, "overflow", "no", "House")
    assert len(stops) == 1


async def test_periodic_recovery_releases_overflow_when_external_personal_starts(authority, accounts):
    engine, rows, personal, now, stops = authority
    for i, n in enumerate(("Edie", "Maddie", "Flynn")):
        lease = await engine.reserve(accounts, f"q{i}", f"s{i}", n)
        rows[f"q{i}"] = {"session": f"s{i}", "provider": lease["provider"], "state": "playing"}
    personal[0] = "owned"
    await engine.recover(accounts)
    assert not stops
    personal[0] = "personal"
    await engine.recover(accounts)
    assert len(stops) == 1 and "grant" not in engine.leases


async def test_stale_pending_recovery_and_active_sessions_do_not_expire(authority, accounts):
    engine, rows, personal, now, stops = authority
    abandoned = await engine.reserve(accounts, "failed", "abandoned", "Edie")
    now[0] += 31
    active = await engine.reserve(accounts, "active", "real", "Maddie")
    assert active["provider"] == abandoned["provider"] == "house"
    rows["active"] = {"session": "real", "provider": "house", "state": "playing"}
    now[0] += 86400
    await engine.recover(accounts)
    assert engine.leases["house"]["token"] == active["token"]
    assert engine.leases["house"]["confirmed"]
    assert not await engine.release(abandoned["token"])
    # Queue replacement heals without pausing its new owner.
    rows["active"] = {"session": "native-new", "provider": "house", "state": "playing"}
    await engine.recover(accounts)
    assert not engine.leases and not stops
    assert (await engine.reserve(accounts, "another", "new", "House"))["provider"] == "house #2"


async def test_uncertain_inventory_and_failed_preemption_fail_closed(authority, accounts):
    engine, rows, personal, now, stops = authority
    engine.observe = lambda: asyncio.sleep(0, result={"broken": {}})
    with pytest.raises(AccountsBusy, match="could not be checked"):
        await engine.reserve(accounts, "q", "s", "House")
    assert not engine.leases


async def test_failed_stop_does_not_reassign_grant_or_touch_native_playback(authority, accounts):
    engine, rows, personal, now, stops = authority
    for i, name in enumerate(("Edie", "Maddie", "Flynn")):
        lease = await engine.reserve(accounts, f"q{i}", f"s{i}", name)
        rows[f"q{i}"] = {"session": f"s{i}", "provider": lease["provider"], "state": "playing"}

    async def refused(lease):
        return False

    engine.stop = refused
    old = engine.leases["grant"]["token"]
    with pytest.raises(AccountsBusy, match="released safely"):
        await engine.reserve(accounts, "personal", "new", "Grant")
    assert engine.leases["grant"]["token"] == old
    # A different native session replaced the overflow: never issue a stop to it.
    rows["q2"]["session"] = "native-personal"
    await engine.recover(accounts)
    assert "grant" not in engine.leases
    with pytest.raises(AccountsBusy):
        await engine.reserve(accounts, "shared", "new", "House")


async def test_bad_reservation_store_is_preserved(tmp_path):
    path = tmp_path / "leases.json"
    path.write_text('{"version":2,"leases":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="administrator attention"):
        SpotifyLeases(path, None, None, None)
    assert '"version":2' in path.read_text()
