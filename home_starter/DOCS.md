# Home Starter

For calendar mappings, household service identities, Pi endpoint commissioning,
internal calling and recovery boundaries, see [Household services](HOUSEHOLD_SERVICES.md).

## How to use it

1. Start the app and open it from the sidebar (**Home Starter**) or with
   **Open web UI**.
2. **Fresh Batteries** is an optional checklist to wake and power things worth
   keeping. Press **Scan now** whenever you are ready; no boxes are required.
3. **Your home** groups rooms, devices and entities. Expand a finding for its
   confidence and reasons. Room changes require review/confirmation and are
   verified against HA. **Home Assistant health and technical details** retains
   the read-only system scan. Under **Useful things**, choose **Music around the house**.
4. Home Starter shows what it found and the next step:
   * **Install Music Assistant**: after you confirm, Home Starter adds the
     official Music Assistant repository if it's missing, installs the app,
     starts it and waits until it runs. You can leave the page meanwhile.
   * **Start Music Assistant**: when it's installed but stopped.
   * **Confirm the integration**: Home Assistant discovers Music Assistant a
     minute after it starts. Confirm it under **Settings → Devices & services →
     Discovered**, then come back and press **Check again**.
   * **Finish setup in Music Assistant**: when Music Assistant's own first-run
     setup or music provider sign-in is still open.
5. When everything checks out you'll see **Music Assistant is ready** and an
   **Open Music Assistant** button.
6. **Make the house usable**: add people and screens, choose their room and audience,
   save settings, then generate and review a native dashboard. Pin, hide and reorder
   belong either to a person or the physical screen. Publication creates its own
   dashboard and verifies it by reading it back. Open that dashboard on its intended
   device and check the useful controls. Read [surface rules and limits](SURFACES.md).
   Phone, tablet and AirTouch/specialist screens share **House + saved people** tabs.
   Rooms and Climate/Today/Music expand into contextual views. Use **Ambient** or
   **Dark** under Display to reduce information; **Active/Wake** returns to House.
   Dark keeps HA chrome and a Wake target. Automatic idle and physical wake/sleep
   require verified device management; no such integration is installed for you.
   Link a child's personal screen to their room to establish personal room context.

If any step can't be done directly, Home Starter sends you to the matching
Home Assistant screen instead, and re-checks when you come back.

## What "ready" means

All of these must be true:

* the Supervisor reports Music Assistant installed and started;
* its internal ingress listener responds to the read-only `/info` endpoint;
* the responding server version matches the installed app and reports app
  mode, running status and completed first-run setup;
* there is one Music Assistant app and one app-discovered Home Assistant
  integration, and that integration is loaded (not failed, disabled or ignored).

Manual integrations and multiple servers stay **running, unverified** because
the public Home Assistant config-entry API doesn't expose server IDs or URLs.
The Open button remains available for reviewing setup. Even **ready** does not
prove provider sign-in, speaker availability or audio playback; test those in
Music Assistant. The listener check also doesn't prove the browser ingress
session works: that is checked when you open Music Assistant.

## Permissions

The app uses the Home Assistant API read-only for the scan, and the
Supervisor `manager` role, which is the lowest role allowed to add a
repository and install and start an app. It only does that when you press the
button and confirm, and Core confirms that the ingress user is an active
administrator. If that lookup fails, use Home Assistant's App Store. It never
uninstalls apps, changes other apps' settings, edits your configuration, or
removes integrations, devices or entities, or changes automations. The only
inventory write is a reviewed device room assignment. Read [inventory rules and
limits](INVENTORY.md) for details.

Screen settings and dashboard publication also require a verified active administrator.
The app saves only its own reviewed dashboard addresses and refuses externally edited
dashboards. Explicit activity tracking publishes virtual sensors in its own namespace;
it does not call appliance services. Native dashboard controls use the viewing HA
account, not the App's Supervisor credential. Person/audience settings are layout
preferences, not account permissions or a kiosk security boundary.

## Limitations

* Needs Home Assistant OS or a Supervised installation.
* The first install builds the app on your machine (a few minutes).
* Music Assistant remains the only installation outcome. Inventory has room
  assignment only; no destructive cleanup or network discovery is implemented.
