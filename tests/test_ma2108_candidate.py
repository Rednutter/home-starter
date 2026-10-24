"""Unpublished candidate gates; no household connections or native activation."""

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from homestarter import ma_control_contract as controls
from homestarter import ma_release_review as review
from test_ma_account_guard import guarded as guarded_fixture
from test_ma_transfer import native as native_fixture
from test_media_preview import preview_state as preview_fixture


def offered():
    return {"protocol": 1, "version": "2.10.8", "review": controls.CANDIDATE_ID, "source_verified": True, "features": dict.fromkeys(controls.FEATURES, True)}


def endpoint():
    return {"version": "2.10.8", "server_id": "example-server", "app": "example-app"}


def test_version_and_catalogue_success_never_enable_controls():
    value = endpoint()
    assert not controls.supports(value, "transport")
    value["catalogue_read_contract"] = True
    assert not controls.supports(value, "transport")
    assert controls.supports({"version": "2.10.7"}, "transport")
    assert not controls.supports({"version": "2.10.7"}, "invented")


@pytest.mark.parametrize("change", ["protocol", "review", "source", "version", "features", "bool-protocol"])
def test_invalid_native_attestation_is_rejected(change):
    value = offered()
    if change == "protocol":
        value["protocol"] = 2
    elif change == "bool-protocol":
        value["protocol"] = True
    elif change == "review":
        value["review"] = "another-review"
    elif change == "source":
        value["source_verified"] = False
    elif change == "version":
        value["version"] = "2.10.9"
    else:
        value["features"]["progress"] = True
    assert controls.attestation(value, endpoint()) is None


@pytest.mark.parametrize("change", ["server_id", "app", "expired", "feature", "progress"])
def test_bound_expiring_feature_contracts_fail_closed(change, monkeypatch):
    monkeypatch.setattr(controls.time, "monotonic", lambda: 100)
    target = endpoint()
    proof = controls.attestation(offered(), target)
    target["_native_review"] = proof
    assert controls.supports(target, "transport")
    if change in {"server_id", "app"}:
        target[change] = "changed"
    elif change == "expired":
        monkeypatch.setattr(controls.time, "monotonic", lambda: 106)
    elif change == "feature":
        proof["features"]["transport"] = False
    else:
        assert not controls.supports(target, "progress")
        return
    assert not controls.supports(target, "transport")


def test_actual_source_manifest_and_only_explicit_hook_normalisation(tmp_path):
    source = Path(__file__).resolve().parents[1] / ".runtime/ma-release-sources/2.10.8/music_assistant"
    if not source.is_dir():
        pytest.skip("Official 2.10.8 source fixture absent; real-source pin check unrun")
    for name in review.PINS:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, dest)
    assert review.source_verified(tmp_path, "2.10.8", "1.1.205")
    assert not review.source_verified(tmp_path, "2.10.9", "1.1.205")
    assert not review.source_verified(tmp_path, "2.10.8", "changed-models")
    mass = tmp_path / "mass.py"
    original = mass.read_bytes()
    mass.write_bytes(original.replace(review.ANCHOR.encode(), review.HOOK.encode()))
    assert review.source_verified(tmp_path, "2.10.8", "1.1.205")
    mass.write_bytes(mass.read_bytes() + b"\n# unreviewed change\n")
    assert not review.source_verified(tmp_path, "2.10.8", "1.1.205")


@pytest.fixture
def native(tmp_path, monkeypatch):
    return native_fixture.__wrapped__(tmp_path, monkeypatch)


async def test_native_transfer_does_not_trust_an_arbitrary_review_object(native):
    adapter, mass, *_ = native
    mass.version = "2.10.8"
    adapter.review = NS(valid=lambda: True)
    assert not (await adapter.status())["pinned"]


async def test_native_candidate_status_requires_live_review_and_wrapper_identity(native, monkeypatch):
    adapter, mass, *_ = native
    mass.version = "2.10.8"
    candidate = object.__new__(review.ReviewedRelease)
    monkeypatch.setattr(candidate, "valid", lambda: True)
    adapter.review = candidate
    assert (await adapter.status())["pinned"]
    mass.player_queues.transfer_queue = NS()  # No stale attestation after native replacement.
    assert not (await adapter.status())["pinned"]


def test_candidate_does_not_modify_old_supported_versions_or_transfer_pins():
    from homestarter.ma_account_guard import SUPPORTED_MA
    from homestarter.ma_transfer import PINS

    assert SUPPORTED_MA == {"2.10.6", "2.10.7"}
    assert PINS["controller.py"] != review.PINS["controllers/player_queues/controller.py"]


@pytest.fixture
def preview_state(tmp_path, monkeypatch):
    return preview_fixture.__wrapped__(tmp_path, monkeypatch)


async def test_catalogue_selection_rechecks_lost_native_control_authority(preview_state):
    from homestarter.media_preview import PreviewService

    state, surface, _ = preview_state
    await PreviewService(state).open("example-admin", surface["id"])
    target = state.music_runtime.endpoint.return_value
    target["version"] = "2.10.8"
    target["_native_review"] = controls.attestation(offered(), target)
    service = PreviewService(state)
    identity, bootstrap = await service.open("example-admin", surface["id"])
    assert not bootstrap["compatibility"]["control_review_required"]
    target.pop("_native_review")
    with pytest.raises(ValueError, match="playback controls need compatibility review"):
        await service.selection(identity, "example-admin", {"profile": "house", "selection": "unoffered"})
    assert bootstrap["compatibility"]["control_review_required"]
    state.music_runtime.control.assert_not_awaited()


@pytest.fixture
def guarded(tmp_path):
    yield from guarded_fixture.__wrapped__(tmp_path)


async def test_candidate_stays_closed_until_late_provider_wrapper_is_ready(guarded, monkeypatch):
    from unittest.mock import AsyncMock

    guard, mass, *_ = guarded
    mass.version = "2.10.8"
    candidate = object.__new__(review.ReviewedRelease)
    monkeypatch.setattr(candidate, "valid", lambda: True)
    guard.review = candidate
    assert not (await guard.status())["isolated"]
    handler = object()

    def loaded():
        guard.soloist_class = NS(_acquire_run=handler)
        guard.soloist_handler = handler

    monkeypatch.setattr(guard, "wrap_soloist", loaded)
    monkeypatch.setattr(guard.engine, "recover", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await guard.recover()
    assert (await guard.status())["isolated"]


@pytest.mark.parametrize("kind", ["audiobook", "podcast_episode"])
async def test_unreviewed_progress_start_rejected_before_any_household_action(kind):
    from homestarter.listening import ListeningRuntime

    with pytest.raises(ValueError, match="progress routing needs review"):
        await ListeningRuntime.play(NS(), endpoint(), None, None, None, None, None, {"kind": kind}, None, None)
