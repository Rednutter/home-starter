"""Generator for the Supervisor API fixtures in tests/fixtures/supervisor (wire format).

Field sets mirror supervisor 2026.10.1: api/root.py info, api/homeassistant.py
info, api/host.py _info_data (+v1 all_features), api/resolution.py
_build_info_response, api/apps.py _list_apps_data/info_data_v1,
api/store.py _generate_app_information / _generate_repository_information,
jobs/__init__.py SupervisorJob.as_dict (+child_jobs from api/jobs.py).
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "supervisor"
OUT.mkdir(parents=True, exist_ok=True)


def ok(data):
    return {"result": "ok", "data": data}


def w(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n")


w(
    "info.json",
    ok(
        {
            "supervisor": "2026.10.1",
            "homeassistant": "2026.10.1",
            "hassos": "17.0",
            "docker": "28.3.3",
            "hostname": "homeassistant",
            "operating_system": "Home Assistant OS 17.0",
            "features": ["reboot", "shutdown", "services", "network", "hostname", "timedate", "os_agent", "haos", "resolved", "journal", "disk", "mount"],
            "machine": "generic-x86-64",
            "machine_id": "8b6f1c2d9e0a4b7c8d1e2f3a4b5c6d7e",
            "arch": "amd64",
            "state": "running",
            "supported_arch": ["amd64"],
            "supported": True,
            "channel": "stable",
            "logging": "info",
            "timezone": "Australia/Melbourne",
        }
    ),
)

w(
    "core_info.json",
    ok(
        {
            "version": "2026.10.1",
            "version_latest": "2026.10.2",
            "update_available": True,
            "machine": "generic-x86-64",
            "ip_address": "172.30.32.1",
            "arch": "amd64",
            "image": "ghcr.io/home-assistant/qemux86-64-homeassistant",
            "boot": True,
            "port": 8123,
            "ssl": False,
            "watchdog": True,
            "audio_input": None,
            "audio_output": None,
            "backups_exclude_database": False,
            "duplicate_log_file": False,
        }
    ),
)

w(
    "host_info.json",
    ok(
        {
            "agent_version": "1.8.1",
            "apparmor_version": "3.1.7",
            "chassis": "embedded",
            "virtualization": "",
            "cpe": "cpe:2.3:o:home-assistant:haos:17.0:*:production:*:*:*:generic-x86-64:*",
            "deployment": "production",
            "disk_free": 84.2,
            "disk_total": 116.7,
            "disk_used": 27.5,
            "disk_life_time": None,
            "features": ["reboot", "shutdown", "services", "network", "hostname", "timedate", "os_agent", "haos", "resolved", "journal", "disk", "mount"],
            "hostname": "homeassistant",
            "llmnr_hostname": "homeassistant",
            "kernel": "6.12.49-haos",
            "operating_system": "Home Assistant OS 17.0",
            "timezone": "Australia/Melbourne",
            "dt_utc": "2026-10-11T21:05:00.000000+00:00",
            "dt_synchronized": True,
            "use_ntp": True,
            "startup_time": 4.2,
            "boot_timestamp": 1791600000000000,
            "broadcast_llmnr": True,
            "broadcast_mdns": True,
            "all_features": [
                "reboot",
                "shutdown",
                "services",
                "network",
                "hostname",
                "timedate",
                "os_agent",
                "haos",
                "resolved",
                "journal",
                "disk",
                "mount",
                "ntp",
            ],
        }
    ),
)

w(
    "resolution_info.json",
    ok(
        {
            "unsupported": [],
            "unhealthy": [],
            "suggestions": [],
            "issues": [{"type": "no_current_backup", "context": "system", "reference": None, "uuid": "9a1b2c3d4e5f60718293a4b5c6d7e8f9"}],
            "checks": [{"enabled": True, "slug": "free_space"}, {"enabled": True, "slug": "backups"}],
        }
    ),
)


def installed(name, slug, repo, version, latest, state, desc="", stage="stable", url=None):
    return {
        "name": name,
        "slug": slug,
        "description": desc,
        "stage": stage,
        "version": version,
        "version_latest": latest,
        "update_available": version != latest,
        "available": True,
        "detached": False,
        "homeassistant": None,
        "state": state,
        "repository": repo,
        "build": False,
        "url": url,
        "icon": True,
        "logo": True,
        "system_managed": False,
        "advanced": False,
    }


HS = installed(
    "Home Starter",
    "8a7b9c1d_home_starter",
    "8a7b9c1d",
    "0.1.0",
    "0.1.0",
    "started",
    "A simple wizard that scans your Home Assistant and sets up useful outcomes.",
    url="https://github.com/Rednutter/home-starter",
)
HS["build"] = True
BASE_INSTALLED = [
    installed("Mosquitto broker", "core_mosquitto", "core", "6.5.2", "6.5.2", "started", "An Open Source MQTT broker"),
    installed("File editor", "core_configurator", "core", "5.8.0", "5.9.0", "stopped", "Simple browser-based file editor for Home Assistant"),
    installed("Studio Code Server", "a0d7b954_vscode", "a0d7b954", "6.0.1", "6.0.1", "started", "Fully featured VSCode experience"),
    HS,
]
w("addons_without_ma.json", ok({"addons": BASE_INSTALLED}))
MA_INST = installed(
    "Music Assistant",
    "d5369777_music_assistant",
    "d5369777",
    "2.10.6",
    "2.10.6",
    "started",
    "The Music Assistant server is a free, opensource Media library manager that connects to your streaming services and a wide range of connected speakers.",
    url="https://music-assistant.io",
)
w("addons_with_ma.json", ok({"addons": BASE_INSTALLED + [MA_INST]}))
MA_STOPPED = dict(MA_INST, state="stopped")
w("addons_with_ma_stopped.json", ok({"addons": BASE_INSTALLED + [MA_STOPPED]}))
MA_BETA = installed(
    "Music Assistant (BETA)",
    "d5369777_music_assistant_beta",
    "d5369777",
    "2.11.0b4",
    "2.11.0b4",
    "started",
    "BETA version of the Music Assistant Server.",
    url="https://music-assistant.io",
)
w("addons_with_ma_beta.json", ok({"addons": BASE_INSTALLED + [MA_BETA]}))

REPOS = [
    {
        "slug": "local",
        "name": "Local apps",
        "source": "local",
        "url": "https://home-assistant.io/hassio",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
    {
        "slug": "core",
        "name": "Official apps",
        "source": "core",
        "url": "https://home-assistant.io/addons",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
    {
        "slug": "a0d7b954",
        "name": "Home Assistant Community Apps",
        "source": "https://github.com/hassio-addons/repository",
        "url": "https://addons.community",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
    {
        "slug": "5c53de3b",
        "name": "ESPHome",
        "source": "https://github.com/esphome/home-assistant-addon",
        "url": "https://esphome.io",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
    {
        "slug": "d5369777",
        "name": "Music Assistant",
        "source": "https://github.com/music-assistant/home-assistant-addon",
        "url": "https://github.com/music-assistant/core",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
    {
        "slug": "8a7b9c1d",
        "name": "Home Starter",
        "source": "https://github.com/Rednutter/home-starter",
        "url": "https://github.com/Rednutter/home-starter",
        "maintainer": "Example Maintainer <maintainer@example.invalid>",
    },
]
w("store_repositories.json", ok(REPOS))
w("store_repositories_without_ma.json", ok([r for r in REPOS if r["slug"] != "d5369777"]))


def store(name, slug, repo, latest, installed_version=None, available=True, desc="", url=None, arch=("aarch64", "amd64"), stage="stable", ha=None):
    return {
        "advanced": False,
        "arch": list(arch),
        "available": available,
        "build": False,
        "description": desc,
        "documentation": True,
        "homeassistant": ha,
        "icon": True,
        "installed": installed_version is not None,
        "logo": True,
        "name": name,
        "repository": repo,
        "slug": slug,
        "stage": stage,
        "update_available": False,
        "url": url,
        "version_latest": latest,
        "version": installed_version,
    }


STORE_BASE = [
    store("Mosquitto broker", "core_mosquitto", "core", "6.5.2", "6.5.2", desc="An Open Source MQTT broker"),
    store("File editor", "core_configurator", "core", "5.9.0", "5.8.0", desc="Simple browser-based file editor for Home Assistant"),
    store("Samba share", "core_samba", "core", "12.5.4", desc="Expose Home Assistant folders with SMB/CIFS"),
    store("Studio Code Server", "a0d7b954_vscode", "a0d7b954", "6.0.1", "6.0.1", desc="Fully featured VSCode experience"),
    store("ESPHome Device Builder", "5c53de3b_esphome", "5c53de3b", "2026.10.0", desc="Build ESPHome devices"),
    store(
        "Home Starter",
        "8a7b9c1d_home_starter",
        "8a7b9c1d",
        "0.1.0",
        "0.1.0",
        desc="A simple wizard that scans your Home Assistant and sets up useful outcomes.",
    ),
]
MA_DESC = (
    "The Music Assistant server is a free, opensource Media library manager that connects to your streaming services and a wide range of connected speakers."
)
MA_STORE = [
    store("Music Assistant", "d5369777_music_assistant", "d5369777", "2.10.6", desc=MA_DESC, url="https://music-assistant.io"),
    store(
        "Music Assistant (BETA)",
        "d5369777_music_assistant_beta",
        "d5369777",
        "2.11.0b4",
        desc="BETA version of the Music Assistant Server.",
        url="https://music-assistant.io",
    ),
    store(
        "Music Assistant (NIGHTLY)",
        "d5369777_music_assistant_nightly",
        "d5369777",
        "2.11.0.dev2026101103",
        desc="NIGHTLY version of Music Assistant.",
        url="https://music-assistant.io",
        stage="experimental",
    ),
    store(
        "Local Audio",
        "d5369777_local_audio",
        "d5369777",
        "0.1.13",
        desc="Turns this Home Assistant system into a synchronized Sendspin player for Music Assistant.",
        url="https://github.com/music-assistant/local-audio-addon",
        stage="experimental",
    ),
]
w("store_addons_without_ma_repo.json", ok({"addons": STORE_BASE}))
w("store_addons.json", ok({"addons": STORE_BASE + MA_STORE}))
inst = [dict(a) for a in MA_STORE]
inst[0]["installed"] = True
inst[0]["version"] = "2.10.6"
w("store_addons_ma_installed.json", ok({"addons": STORE_BASE + inst}))
unav = [dict(a) for a in MA_STORE]
unav[0]["available"] = False
w("store_addons_ma_unavailable.json", ok({"addons": STORE_BASE + unav}))


def app_info(
    name,
    slug,
    repo,
    version,
    state,
    *,
    role="default",
    ingress=False,
    ingress_port=8099,
    host_network=False,
    hassio_api=False,
    homeassistant_api=False,
    auth_api=False,
    ip="172.30.33.4",
    panel=True,
    webui=None,
    options=None,
    schema=None,
    privileged=(),
    audio=False,
    url=None,
    desc="",
    long_desc="",
    rating=6,
    token="Bb3QkZ1nX2rS4tU6vW8yA0cE2gI4kM6oQ8sU0wY2",
    host="",
    latest=None,
    discovery=(),
):
    return {
        "name": name,
        "slug": slug,
        "hostname": host or slug.replace("_", "-"),
        "dns": [f"{slug.replace('_', '-')}.local.hass.io"],
        "description": desc,
        "long_description": long_desc,
        "stage": "stable",
        "repository": repo,
        "version_latest": latest or version,
        "protected": True,
        "rating": rating,
        "boot_config": "auto",
        "boot": "auto",
        "options": options or {},
        "schema": schema or [],
        "arch": ["aarch64", "amd64"],
        "machine": [],
        "homeassistant": None,
        "url": url,
        "detached": False,
        "available": True,
        "build": False,
        "network": None,
        "network_description": None,
        "host_network": host_network,
        "host_pid": False,
        "host_ipc": False,
        "host_uts": False,
        "host_dbus": False,
        "privileged": list(privileged),
        "full_access": False,
        "apparmor": "default",
        "icon": True,
        "logo": True,
        "changelog": True,
        "documentation": True,
        "stdin": False,
        "hassio_api": hassio_api,
        "hassio_role": role,
        "auth_api": auth_api,
        "homeassistant_api": homeassistant_api,
        "gpio": False,
        "usb": False,
        "uart": False,
        "kernel_modules": False,
        "devicetree": False,
        "udev": False,
        "docker_api": False,
        "video": False,
        "audio": audio,
        "startup": "application",
        "services": [],
        "discovery": list(discovery),
        "translations": {},
        "ingress": ingress,
        "signed": False,
        "state": state,
        "webui": webui,
        "ingress_entry": f"/api/hassio_ingress/{token}" if ingress else None,
        "ingress_url": f"/api/hassio_ingress/{token}/" if ingress else None,
        "ingress_port": ingress_port if ingress else None,
        "ingress_panel": panel if ingress else None,
        "audio_input": None,
        "audio_output": None,
        "auto_update": False,
        "ip_address": ip,
        "version": version,
        "update_available": False,
        "watchdog": False,
        "devices": [],
        "system_managed": False,
        "system_managed_config_entry": None,
        "advanced": False,
    }


w(
    "self_info_manager.json",
    ok(
        app_info(
            "Home Starter",
            "8a7b9c1d_home_starter",
            "8a7b9c1d",
            "0.1.0",
            "started",
            role="manager",
            ingress=True,
            hassio_api=True,
            homeassistant_api=True,
            ip="172.30.33.7",
            rating=6,
            url="https://github.com/Rednutter/home-starter",
            desc="A simple wizard that scans your Home Assistant and sets up useful outcomes.",
            token="Xk3mN8pQ2rT5vW9yB1dF4hJ7lN0pS3uW6zA9cE2g",
        )
    ),
)
d = json.loads((OUT / "self_info_manager.json").read_text())
d["data"]["hassio_role"] = "default"
w("self_info_default.json", d)

MA_KW = dict(
    role="manager",
    ingress=True,
    ingress_port=8094,
    host_network=True,
    hassio_api=True,
    homeassistant_api=True,
    auth_api=True,
    ip="172.30.32.1",
    panel=True,
    audio=True,
    privileged=("SYS_ADMIN", "DAC_READ_SEARCH"),
    url="https://music-assistant.io",
    desc=MA_DESC,
    rating=4,
    options={"log_level": "info", "safe_mode": False},
    schema=[
        {
            "name": "log_level",
            "required": True,
            "type": "select",
            "options": [["debug", "debug"], ["info", "info"], ["warning", "warning"], ["error", "error"]],
        },
        {"name": "safe_mode", "required": True, "type": "boolean"},
    ],
    token="Q7wE4rT1yU8iO5pA2sD9fG6hJ3kL0zX7cV4bN1mQ",
    host="d5369777-music-assistant",
    discovery=("music_assistant",),
)
w("app_info_ma_started.json", ok(app_info("Music Assistant", "d5369777_music_assistant", "d5369777", "2.10.6", "started", **MA_KW)))
w("app_info_ma_stopped.json", ok(app_info("Music Assistant", "d5369777_music_assistant", "d5369777", "2.10.6", "stopped", **MA_KW)))
w("app_info_ma_startup.json", ok(app_info("Music Assistant", "d5369777_music_assistant", "d5369777", "2.10.6", "startup", **MA_KW)))
w("app_info_ma_error.json", ok(app_info("Music Assistant", "d5369777_music_assistant", "d5369777", "2.10.6", "error", **MA_KW)))
# Legacy routing for a not-installed app returns store info + state "unknown" (supervisor/api/__init__.py apps_app_info).
w(
    "app_info_ma_not_installed.json",
    ok(
        {
            "advanced": False,
            "arch": ["aarch64", "amd64"],
            "available": True,
            "build": False,
            "description": MA_DESC,
            "documentation": True,
            "homeassistant": None,
            "icon": True,
            "installed": False,
            "logo": True,
            "name": "Music Assistant",
            "repository": "d5369777",
            "slug": "d5369777_music_assistant",
            "stage": "stable",
            "update_available": False,
            "url": "https://music-assistant.io",
            "version_latest": "2.10.6",
            "version": None,
            "apparmor": "default",
            "auth_api": True,
            "detached": False,
            "docker_api": False,
            "full_access": False,
            "hassio_api": True,
            "hassio_role": "manager",
            "homeassistant_api": True,
            "host_network": True,
            "host_pid": False,
            "ingress": True,
            "long_description": "",
            "rating": 4,
            "signed": False,
            "state": "unknown",
            "options": {"log_level": "info", "safe_mode": False},
        }
    ),
)


def job(done, progress, errors=(), stage=None):
    return ok(
        {
            "name": "app_manager_install",
            "reference": "d5369777_music_assistant",
            "uuid": "3f2b8c9d0e1a4b5c6d7e8f9a0b1c2d3e",
            "progress": progress,
            "stage": stage,
            "done": done,
            "parent_id": None,
            "errors": list(errors),
            "created": "2026-10-11T21:10:00.000000+00:00",
            "extra": None,
            "child_jobs": [],
        }
    )


w("job_install_running.json", job(False, 42.5))
w("job_install_done.json", job(True, 100))
w(
    "job_install_failed.json",
    job(
        True,
        12.0,
        [
            {
                "type": "DockerError",
                "message": "Can't install ghcr.io/music-assistant/server:2.10.6: 500 Server Error: no space left on device",
                "stage": None,
                "error_key": None,
                "extra_fields": None,
            }
        ],
    ),
)
w("install_background.json", ok({"job_id": "3f2b8c9d0e1a4b5c6d7e8f9a0b1c2d3e"}))
w("ok_empty.json", ok({}))
w(
    "error_already_added.json",
    {
        "result": "error",
        "message": "Can't add https://github.com/music-assistant/home-assistant-addon, already in the store",
        "error_key": "store_repository_already_added_error",
        "extra_fields": {"url": "https://github.com/music-assistant/home-assistant-addon"},
    },
)
w(
    "error_unavailable_arch.json",
    {
        "result": "error",
        "message": "App d5369777_music_assistant not supported on this platform, supported architectures: aarch64, amd64",
        "error_key": "app_not_supported_architecture_error",
        "extra_fields": {"app": "d5369777_music_assistant", "architectures": "aarch64, amd64"},
    },
)
print("ok", sorted(p.name for p in OUT.iterdir()))
