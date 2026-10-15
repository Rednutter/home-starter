# Home Starter

**Waste collection** uses Council collection areas and the dated annual calendar
for concise bin reminders and native HA entities. Confirm the proposed service;
expired schedules require checking. No synthetic calendar events are created.
See [sources, privacy and confirmation boundaries](WASTE_COLLECTION.md).

**Physical screen commissioning** separates dashboard publication from a verified
dedicated HA login, restart and actual display use. Native HA owns credentials;
existing screen choices and publications remain intact.
See [supported automation and commissioning limits](SCREEN_COMMISSIONING.md).

**Household Context** turns the chosen verified calendar and explicit household
rules into a compact passive wall that shifts from today to upcoming weeks.
See [behaviour, privacy and acceptance limits](HOUSEHOLD_CONTEXT.md).

**This House** compares live HA people, floors, rooms and equipment with the
physical home. Review discrepancies and confirm changes before writing them back.
See [house commissioning and limits](THIS_HOUSE.md).

Scan your Home Assistant, pick what you want to do, and let Home Starter set
up the sensible existing component the Home Assistant way, then check it works.

Version 0.4 adds **House + configured people** touch navigation, first-class AirTouch
climate and contextual room/calendar/music views. Manual Active/Ambient/Dark
presentation keeps safety visible; physical wake/sleep and automatic inactivity
need verified device management. Saved Pin / Hide / Reorder and explicit appliance
activity today are preserved. **Fresh Batteries**, **Your home** inventory and **Music around the house**
remain available. Read [surface rules and limits](SURFACES.md).

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
