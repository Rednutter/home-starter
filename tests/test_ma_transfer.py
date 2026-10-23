"""Separate native candidate with fake MA controllers, locks and auth context."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest
from homestarter import ma_transfer


@pytest.fixture
def native(tmp_path, monkeypatch):
    root = tmp_path / "player_queues"
    pins = {}
    for name in ma_transfer.PINS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic source " + name.encode())
        pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(ma_transfer, "PINS", pins)

    class State:
        def __init__(self, **values):
            self.__dict__.update(values)

        def to_dict(self):
            return deepcopy(self.__dict__)

    media = State(
        uri="local://track/one", provider="local", media_type="track", provider_mappings=[{"provider_domain": "filesystem", "provider_instance": "local"}]
    )
    item = NS(queue_item_id="item", media_item=media)
    data = {
        pid: NS(
            userid="source-user" if pid == "a" else "former-user",
            items=[item] if pid == "a" else [],
            queue=State(
                queue_id=pid,
                active=pid == "a",
                state="playing" if pid == "a" else "idle",
                current_index=0,
                current_item=item if pid == "a" else None,
                shuffle_enabled=False,
                repeat_mode="off",
                autoplay_enabled=False,
                is_dynamic=False,
                elapsed_time=42,
                resume_pos=42,
            ),
        )
        for pid in ("a", "b")
    }
    players = {
        pid: NS(
            state=State(
                player_id=pid,
                type="player",
                available=True,
                playback_state="playing" if pid == "a" else "idle",
                active_source=pid,
                active_group=None,
                synced_to=None,
                group_members=[],
                static_group_members=[],
                elapsed_time=42,
            )
        )
        for pid in data
    }
    users = {name: NS(user_id=name, enabled=True, provider_filter={"local"}, player_filter={"a", "b"}) for name in ("source-user", "former-user", "admin")}
    context = NS(current=users["admin"])
    context.get_current_user = lambda: context.current
    context.set_current_user = lambda value: setattr(context, "current", value)
    locks = {pid: asyncio.Lock() for pid in data}
    acquired, calls = [], []

    @asynccontextmanager
    async def lock(pid):
        async with locks[pid]:
            acquired.append(pid)
            yield

    async def get_user(userid):
        return users.get(userid)

    def permission(pid):
        if pid not in context.current.player_filter:
            raise PermissionError("Native player permission denied")

    async def transfer(source, target, auto_play):
        assert locks[source].locked() and locks[target].locked()
        assert context.current is users["source-user"]
        calls.append((source, target, auto_play))
        data[target].items = list(data[source].items)
        for key, value in vars(data[source].queue).items():
            setattr(data[target].queue, key, deepcopy(value))
        data[target].queue.queue_id = target
        data[target].queue.state = "playing" if auto_play else "idle"
        data[target].queue.active = auto_play
        data[source].items = []
        data[source].queue.current_item = None
        data[source].queue.state = "idle"
        players[source].state.playback_state = "idle"
        players[target].state.playback_state = data[target].queue.state
        if getattr(mass, "fail_after", False):
            raise OSError("Synthetic lost response")

    mass = NS(
        version="2.10.7",
        player_queues=NS(queue_data=data.__getitem__, transfer_queue=transfer, _check_player_permission=permission),
        players=NS(get_player=players.get, get_group_and_player_lock=lock),
        webserver=NS(auth=NS(get_user=get_user)),
        get_provider=lambda pid: NS(domain="spotify" if pid == "spotify" else "filesystem"),
    )
    adapter = ma_transfer.NativeTransfers(mass, source_root=root, auth=context)
    return adapter, mass, data, players, users, context, acquired, calls


async def move(native, **extra):
    adapter = native[0]
    a, b = await adapter.snapshot("a"), await adapter.snapshot("b")
    args = {
        "source_queue_id": "a",
        "target_queue_id": "b",
        "source_revision": a["revision"],
        "target_revision": b["revision"],
        "request_id": "a" * 32,
        "auto_play": a["queue"]["state"] == "playing",
        **extra,
    }
    return await adapter.transfer(**args), args


async def test_native_bridge_reuses_transfer_and_preserves_user_under_player_locks(native):
    result, args = await move(native)
    adapter, _, data, _, users, context, locks, calls = native
    assert result == {"state": "complete"}
    assert data["b"].userid == "source-user" and data["b"].queue.resume_pos == 42
    assert context.current is users["admin"] and locks == ["a", "b"]
    assert await adapter.transfer(**args) == result
    assert calls == [("a", "b", True)]
    with pytest.raises(ValueError, match="another move"):
        await adapter.transfer(**{**args, "auto_play": False})


async def test_native_bridge_keeps_paused_transfer_quiet(native):
    native[2]["a"].queue.state = native[3]["a"].state.playback_state = "paused"
    await move(native)
    assert native[7] == [("a", "b", False)] and native[2]["b"].queue.state == "idle"


@pytest.mark.parametrize("change", ["occupied", "spotify", "book", "permission", "version", "pin"])
async def test_native_candidate_rejects_unsafe_combinations_before_native_command(native, change):
    adapter, mass, data, players, users, context, _, calls = native
    old_user = data["b"].userid
    if change == "occupied":
        players["b"].state.playback_state = "paused"
    elif change == "spotify":
        data["a"].items[0].media_item.provider = "spotify"
    elif change == "book":
        data["a"].items[0].media_item.media_type = "audiobook"
    elif change == "permission":
        users["source-user"].player_filter = {"a"}
    elif change == "version":
        mass.version = "2.10.8"
    else:
        (adapter.root / "controller.py").write_bytes(b"changed")
    with pytest.raises((ValueError, PermissionError)):
        await move(native)
    assert calls == [] and data["b"].userid == old_user and context.current is users["admin"]


async def test_permission_change_invalidates_native_snapshot_revision(native):
    adapter = native[0]
    a, b = await adapter.snapshot("a"), await adapter.snapshot("b")
    native[4]["source-user"].provider_filter = {"different"}
    with pytest.raises(ValueError, match="permission changed"):
        await adapter.transfer("a", "b", a["revision"], b["revision"], "b" * 32, True)
    assert native[7] == []


async def test_native_partial_response_keeps_owner_restores_context_and_never_reexecutes(native):
    adapter, mass, data, _, users, context, _, calls = native
    mass.fail_after = True
    a, b = await adapter.snapshot("a"), await adapter.snapshot("b")
    args = ("a", "b", a["revision"], b["revision"], "c" * 32, True)
    with pytest.raises(OSError):
        await adapter.transfer(*args)
    assert data["b"].userid == "source-user" and context.current is users["admin"]
    assert await adapter.transfer(*args) == {"state": "uncertain"}
    assert len(calls) == 1


async def test_byte_pins_reject_windows_newline_rewriting(native, monkeypatch):
    adapter = native[0]
    path = adapter.root / "controller.py"
    path.write_bytes(b"synthetic\nsource\n")
    monkeypatch.setitem(ma_transfer.PINS, "controller.py", hashlib.sha256(path.read_bytes()).hexdigest())
    assert (await adapter.status())["pinned"]
    path.write_bytes(b"synthetic\r\nsource\r\n")
    assert (await adapter.status())["pinned"] is False
