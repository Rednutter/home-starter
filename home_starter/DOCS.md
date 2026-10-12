# Home Starter

## How to use it

1. Start the app and open it from the sidebar (**Home Starter**) or with
   **Open web UI**.
2. The top of the page is a read-only scan of your system: versions, machine,
   storage, apps, integrations (and any that failed to set up), areas,
   unavailable entities and waiting repairs. Nothing is changed by scanning.
3. Under **What do you want to do?** choose **Music around the house**.
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
touches integrations, devices or automations.

## Limitations

* Needs Home Assistant OS or a Supervised installation.
* The first install builds the app on your machine (a few minutes).
* Only the music outcome exists in this version.
