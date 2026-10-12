"""Completion-count acceptance on disposable localhost Core only."""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from homestarter.activity import activity_entity


def main():
    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    house = json.loads(Path("screens/v3-data/household.json").read_text())
    rule = house["activities"][0]
    base = "http://127.0.0.1:18123/api"
    headers = {"Authorization": "Bearer " + credentials["token"], "Content-Type": "application/json"}

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        with urlopen(Request(base + path, data=data, headers=headers), timeout=10) as response:  # noqa: S310 - hardcoded loopback
            return json.load(response)

    def set_cycle(value):
        request("/services/input_select/select_option", {"entity_id": "input_select.washer_cycle", "option": value})
        deadline = time.monotonic() + 10
        while request("/states/sensor.washer_status")["state"] != value and time.monotonic() < deadline:
            time.sleep(0.2)
        assert request("/states/sensor.washer_status")["state"] == value

    source = activity_entity(rule)
    original = request("/states/input_select.washer_cycle")["state"]
    before = int(request("/states/" + source)["state"])
    try:
        for _ in range(2):
            set_cycle("running")
            set_cycle("complete")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            value = request("/states/" + source)
            if value["state"] == str(before + 2):
                assert value["attributes"]["ran_today"] is True and value["attributes"]["last_run"]
                print("Official recorder: two explicit completions counted once each; ran_today and last_run verified.")
                break
            time.sleep(1)
        else:
            raise AssertionError("Completion count did not arrive within two polling intervals")
    finally:
        set_cycle(original)


if __name__ == "__main__":
    main()
