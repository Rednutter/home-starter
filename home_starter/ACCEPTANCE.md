# Release verification

The public repository records product behaviour, synthetic tests and reproducible
checks. Real household names, entity identifiers, state snapshots, device counts,
calendar contents and screenshots belong in private runtime evidence, never here.

## Automated checks

Run the full Python and JavaScript suites, Ruff, App validation and the repository
privacy check. CI also builds amd64/arm64 images. Fixture browser harnesses exercise
Music Assistant setup and household dashboard publication against synthetic sources.
They do not establish native rendering or physical device verification.

## Native acceptance checklist

In an explicitly authorised Home Assistant installation, verify App startup,
inventory, Music Assistant readiness, persisted settings, dashboard publication and
readback. Exercise House/person and contextual room navigation. Test only explicitly
selected climate controls, restore their original values and verify isolation.
Record results privately without copying household data into fixtures or Git.

For display lifecycle limits see [SURFACES.md](SURFACES.md). Docker-based native
harnesses and optional Supervisor schema validation require their supported Linux
runtime; unavailable checks must be reported rather than marked successful.
