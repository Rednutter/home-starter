"""Music Assistant detection and verification state (pure evaluation)."""

from __future__ import annotations

import copy

import pytest
from conftest import core_fixture, ma_fixture, sup_fixture
from homestarter import music
from homestarter.music import Facts, evaluate


def facts(
    *,
    repos="store_repositories.json",
    store="store_addons.json",
    installed="addons_without_ma.json",
    info=None,
    role="manager",
    entries="ma_entries_none.json",
    flows=None,
    server="server_info.json",
    ha_version="2026.10.1",
    **overrides,
) -> Facts:
    f = Facts(
        ha_version=ha_version,
        self_role=role,
        repositories=sup_fixture(repos) if repos else None,
        store_apps=sup_fixture(store)["addons"] if store else None,
        installed_apps=sup_fixture(installed)["addons"] if installed else None,
        app_info=sup_fixture(info) if info else None,
        config_entries=core_fixture(entries) if entries else None,
        flows=core_fixture(flows) if flows else [],
        server=None,
        ingress_responding=bool(info and server),
    )
    if info and server and f.app_info and f.app_info.get("state") == "started":
        raw = ma_fixture(server)
        f.server = {k: raw[k] for k in ("server_version", "schema_version", "onboard_done", "homeassistant_addon", "status")}
    for k, v in overrides.items():
        setattr(f, k, v)
    return f


def check(result, check_id):
    return next(c for c in result["checks"] if c["id"] == check_id)


def kinds(result):
    return [(a["kind"], a["style"]) for a in result["actions"]]


# ---- detection helpers ------------------------------------------------------


def test_repository_slug_comes_from_metadata_not_hardcoded():
    repos = copy.deepcopy(sup_fixture("store_repositories.json"))
    for r in repos:
        if r["slug"] == "d5369777":
            r["slug"] = "abcdef12"  # e.g. a different hash scheme in future
            r["source"] = "https://github.com/music-assistant/home-assistant-addon/"
    assert music.ma_repository_slug(repos) == "abcdef12"
    store = [dict(a, slug=a["slug"].replace("d5369777", "abcdef12"), repository="abcdef12") for a in sup_fixture("store_addons.json")["addons"]]
    assert music.find_store_app(store, "abcdef12")["slug"] == "abcdef12_music_assistant"


def test_store_app_lookup_ignores_beta_and_other_repos():
    store = sup_fixture("store_addons.json")["addons"]
    assert music.find_store_app(store, "d5369777")["slug"] == "d5369777_music_assistant"
    assert music.find_store_app(store, None)["slug"] == "d5369777_music_assistant"
    fake = [dict(store[0], slug="1234abcd_music_assistant", name="Not Music Assistant", repository="1234abcd")]
    assert music.find_store_app(fake, None) is None


def test_installed_variant_detection_prefers_running_stable():
    apps = sup_fixture("addons_with_ma_beta.json")["addons"]
    assert music.find_installed(apps, "d5369777")["slug"] == "d5369777_music_assistant_beta"
    both = sup_fixture("addons_with_ma.json")["addons"] + [sup_fixture("addons_with_ma_beta.json")["addons"][-1]]
    assert music.find_installed(both, "d5369777")["slug"] == "d5369777_music_assistant"
    stopped_stable = [dict(a, state="stopped") if a["slug"] == "d5369777_music_assistant" else a for a in both]
    assert music.find_installed(stopped_stable, "d5369777")["slug"] == "d5369777_music_assistant_beta"
    assert music.find_installed(sup_fixture("addons_without_ma.json")["addons"], "d5369777") is None


def test_normalize_repo_url():
    assert music.normalize_repo_url("https://GitHub.com/music-assistant/home-assistant-addon.git#main") == music.normalize_repo_url(music.MA_REPOSITORY_URL)


# ---- states ---------------------------------------------------------------------


def test_absent_repository_not_in_store():
    r = evaluate(facts(repos="store_repositories_without_ma.json", store="store_addons_without_ma_repo.json"))
    assert r["state"] == "not_in_store"
    assert check(r, "store")["status"] == "fail"
    assert kinds(r)[0] == ("setup", "primary")
    assert r["direct_install"]["available"] is True
    assert r["handoff_path"].startswith("/_my_redirect/supervisor_add_addon_repository?repository_url=https%3A%2F%2Fgithub.com%2Fmusic-assistant")
    assert not r["verified"]


def test_available_but_not_installed():
    r = evaluate(facts())
    assert r["state"] == "available"
    assert r["app"]["slug"] == "d5369777_music_assistant"
    assert check(r, "installed")["status"] == "fail"
    assert check(r, "compatible")["status"] == "pass"
    assert kinds(r)[:2] == [("setup", "primary"), ("navigate", "secondary")]
    assert r["actions"][1]["path"] == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"


def test_available_but_unsupported_architecture():
    err = sup_fixture  # noqa: F841 - fixture kept for readability
    r = evaluate(facts(availability_error={"kind": "api", "message": "App d5369777_music_assistant not supported on this platform", "status": 400}))
    assert r["state"] == "unsupported"
    assert check(r, "compatible")["status"] == "fail"
    assert all(a["kind"] != "setup" for a in r["actions"])
    r2 = evaluate(facts(store="store_addons_ma_unavailable.json"))
    assert r2["state"] == "unsupported"


def test_installed_but_stopped():
    r = evaluate(facts(installed="addons_with_ma_stopped.json", info="app_info_ma_stopped.json"))
    assert r["state"] == "stopped"
    assert check(r, "installed")["status"] == "pass"
    assert check(r, "running")["status"] == "fail"
    assert r["actions"][0] == {"kind": "setup", "label": "Start Music Assistant", "style": "primary"}
    assert not r["verified"]


def test_installed_with_error_state():
    r = evaluate(facts(installed="addons_with_ma_stopped.json", info="app_info_ma_error.json"))
    assert r["state"] == "stopped"
    assert "error" in r["detail"]


def test_starting():
    r = evaluate(facts(installed="addons_with_ma_stopped.json", info="app_info_ma_startup.json"))
    assert r["state"] == "starting"
    assert check(r, "running")["status"] == "pending"


def test_running_but_integration_missing():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json"))
    assert r["state"] == "needs_integration"
    assert check(r, "running")["status"] == "pass"
    assert check(r, "web_ui")["status"] == "pass"
    assert check(r, "integration")["status"] == "fail"
    assert r["actions"][0]["path"] == "/_my_redirect/config_flow_start?domain=music_assistant"
    assert r["open_path"] == "/app/d5369777_music_assistant"
    assert not r["verified"]


def test_running_and_discovered_waits_for_confirmation():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", flows="flow_progress_ma_discovered.json"))
    assert r["state"] == "integration_discovered"
    assert r["actions"][0]["path"] == "/config/integrations/dashboard"


def test_running_but_integration_ignored():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_ignored.json"))
    assert r["state"] == "integration_ignored"


def test_integration_disabled():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_disabled.json"))
    assert r["state"] == "integration_disabled"
    assert r["actions"][0]["path"] == "/_my_redirect/integration?domain=music_assistant"


@pytest.mark.parametrize("fixture", ["ma_entries_setup_retry.json", "ma_entries_setup_error.json"])
def test_integration_failed_is_not_success(fixture):
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries=fixture))
    assert r["state"] == "integration_error"
    assert check(r, "integration")["status"] == "fail"
    assert not r["verified"]


def test_integration_setting_up():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_in_progress.json"))
    assert r["state"] == "integration_starting"


def test_setup_incomplete_inside_music_assistant():
    r = evaluate(
        facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json", server="server_info_not_onboarded.json")
    )
    assert r["state"] == "needs_onboarding"
    assert check(r, "integration")["status"] == "pass"
    assert r["actions"][0]["label"] == "Finish setup in Music Assistant"
    assert r["actions"][0]["path"] == "/app/d5369777_music_assistant"
    assert not r["verified"]


def test_verified_ready():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json"))
    assert r["state"] == "ready"
    assert r["verified"] is True
    assert r["title"] == "Music Assistant is ready"
    assert [c["status"] for c in r["checks"]] == ["pass"] * 6
    assert r["actions"][0] == {"kind": "navigate", "label": "Open Music Assistant", "style": "primary", "path": "/app/d5369777_music_assistant"}


def test_failed_server_probe_is_not_verified():
    f = facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json")
    f.server, f.server_error = None, "ClientConnectorError: refused"
    r = evaluate(f)
    assert r["state"] == "running_unverified"
    assert not r["verified"]
    assert check(r, "server")["status"] == "unknown"


def test_running_but_core_unreadable_is_not_verified():
    f = facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries=None)
    f.core_error = {"kind": "unreachable", "message": "Home Assistant websocket not reachable"}
    r = evaluate(f)
    assert r["state"] == "running_unverified"
    assert not r["verified"]


def test_beta_variant_is_detected_and_opened():
    info = copy.deepcopy(sup_fixture("app_info_ma_started.json"))
    info.update(slug="d5369777_music_assistant_beta", name="Music Assistant (BETA)", version="2.11.0b4")
    f = facts(installed="addons_with_ma_beta.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json")
    f.app_info = info
    f.server["server_version"] = info["version"]
    r = evaluate(f)
    assert r["state"] == "ready"
    assert r["app"]["variant"] == "music_assistant_beta"
    assert r["open_path"] == "/app/d5369777_music_assistant_beta"


def test_old_frontend_uses_hassio_ingress_route():
    r = evaluate(facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json", ha_version="2025.12.3"))
    assert r["open_path"] == "/hassio/ingress/d5369777_music_assistant"


def test_no_ingress_falls_back_to_app_page():
    info = dict(sup_fixture("app_info_ma_started.json"), ingress=False, ingress_url=None)
    f = facts(installed="addons_with_ma.json", entries="ma_entries_loaded.json")
    f.app_info = info
    r = evaluate(f)
    assert check(r, "web_ui")["status"] == "fail"
    assert r["open_path"] == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"
    assert not r["verified"]


# ---- permission / API failures fall back to native handoff ------------------


def test_default_role_falls_back_to_handoff():
    r = evaluate(facts(role="default"))
    assert r["state"] == "available"
    assert r["direct_install"]["available"] is False
    assert "default" in r["direct_install"]["reason"]
    assert all(a["kind"] != "setup" for a in r["actions"])
    assert r["actions"][0]["kind"] == "navigate" and r["actions"][0]["style"] == "primary"
    assert r["actions"][0]["path"] == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"


def test_store_forbidden_falls_back_to_handoff():
    forbidden = {"kind": "forbidden", "message": "nope", "status": 403}
    f = facts(repos=None, store=None, installed=None, role=None)
    f.self_error = forbidden
    f.repositories_error = forbidden
    f.store_error = forbidden
    f.installed_error = forbidden
    r = evaluate(f)
    assert r["state"] == "unknown"
    assert r["direct_install"]["available"] is False
    assert r["actions"][0]["kind"] == "navigate"
    assert r["actions"][0]["path"].startswith("/_my_redirect/supervisor_add_addon_repository")


def test_store_unreadable_is_not_reported_as_missing():
    f = facts(repos=None, store=None)
    f.store_error = f.repositories_error = {"kind": "api", "message": "Store is reloading", "status": 400}
    r = evaluate(f)
    assert r["state"] == "unknown"
    assert check(r, "store")["status"] == "unknown"
    assert all(a["kind"] != "setup" for a in r["actions"])


def test_store_check_names_the_repository():
    r = evaluate(facts())
    assert check(r, "store")["detail"] == "From the Music Assistant repository · version 2.10.6"


def test_supervisor_unreachable():
    down = {"kind": "unreachable", "message": "Supervisor not reachable", "status": None}
    f = facts(repos=None, store=None, installed=None, role=None)
    f.self_error = f.repositories_error = f.store_error = f.installed_error = down
    r = evaluate(f)
    assert r["state"] == "unknown"
    assert r["actions"][0]["kind"] == "recheck"
    assert r["actions"][1]["path"] == "/_my_redirect/supervisor_store"


def test_operation_in_progress_overrides():
    r = evaluate(facts(), {"finished": False, "message": "Installing…"})
    assert r["state"] == "installing"
    assert r["actions"] == []


def test_every_navigation_path_is_safe():
    from homestarter.navigation import is_safe_ha_path

    variants = [
        facts(),
        facts(repos="store_repositories_without_ma.json", store="store_addons_without_ma_repo.json"),
        facts(installed="addons_with_ma.json", info="app_info_ma_started.json"),
        facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json"),
        facts(installed="addons_with_ma_stopped.json", info="app_info_ma_stopped.json", role="default"),
    ]
    for f in variants:
        r = evaluate(f)
        for a in r["actions"]:
            if "path" in a:
                assert is_safe_ha_path(a["path"]), a
        assert is_safe_ha_path(r["handoff_path"])


def test_options_and_secrets_from_app_info_never_reach_the_result():
    info = copy.deepcopy(sup_fixture("app_info_ma_started.json"))
    info["options"] = {"api_key": "super-secret-value"}
    f = facts(installed="addons_with_ma.json", entries="ma_entries_loaded.json")
    f.app_info = info
    text = repr(evaluate(f))
    assert "super-secret-value" not in text
    assert info["ingress_entry"] not in text  # ingress session token path stays server-side
