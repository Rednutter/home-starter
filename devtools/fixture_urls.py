"""Disposable browser harness ports; host is always loopback."""

import os


def port(kind):
    offset = int(os.environ.get("HOME_STARTER_FIXTURE_PORT_OFFSET", "0"))
    if not 0 <= offset <= 10000:
        raise ValueError("Fixture port offset must be between zero and 10000.")
    return {"ingress": 8124, "app": 8099, "supervisor": 8181, "music": 8195}[kind] + offset


def fixture_url(path="", kind="ingress"):
    return f"http://127.0.0.1:{port(kind)}" + path
