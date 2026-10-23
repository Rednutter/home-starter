# Household audio 0.8.43 release

Status: IN PROGRESS. The production interface is locally tested; no live
deployment or physical playback acceptance is implied.

The retained local candidate `household-audio-rc2` contains 481 verified assets.
Its asset manifest SHA-256 is
`076c36f846e3cc8bc243279f11d94407975129e58a3b9258d28342d92dab548d`.
The upstream frontend is pinned to commit
`dc3caf60f124301a32e21bcb053523d2451a6bfa` (2.17.297.post1), with the verified
archive hash enforced by the CI preparation script. The upstream source and
licence remain unchanged. Generated dependency notices accompany the bundle.

The main media route uses native MA library/detail components with a household
metadata projection and the existing household playback service. Native write
menus do not bypass that service. Person data, source filters, allocator guards,
queue revisions and progress attribution remain in the service. Missing native
account protection fails closed. Multi-speaker checkboxes do not start separate
unsynchronised streams; grouping remains uncommissioned.

Local validation: 1,024 Python tests, 102 existing JS tests, six projection JS
tests, Ruff and privacy checks. Packaged fictional browser acceptance covers
catalogue/detail navigation, play, pause, queue insertion, timer, repeated taps,
uncertain stop reconciliation, profile changes and three viewport sizes. It
reported no page errors, external requests or CSP violations. No speaker was
controlled by these tests.

## CI and release gate

The normal add-on source now contains the exact tested compiled assets and
dependency notices. Its Docker ignore rules admit only those specific paths.
An image-build verification step checks the manifest and every asset inside the
image, preventing a successful build that silently serves the old interface.
CI rebuilds the hash-pinned upstream and compares all compiled assets before
building amd64 and arm64 images from the normal home_starter Docker context.
It does not publish images or deploy. The ordinary Supervisor store builds the
versioned main source after the scoped release merge authorised for deployment.
Generated third-party privacy exceptions require the exact reviewed manifest
and individual file hashes; no household runtime files receive an exception.

Deployment requires terminal passing CI and a final readiness review. Before the
authorised scoped Home Starter update, back up its current options/data, record
active timers/jobs and deployed image identity, and verify the rollback copy.
Preserve household state, existing dashboards, Google routines and listener
restrictions. Do not combine this update with native MA repair, HA climate
maintenance, audiobook installation or household cutover.

Rollback target is the existing 0.8.42 release at
`fb5d43ade11e5abce0a29ed185106aa41259c5a7`, using the recorded original image and
backed-up options/data. Stop the candidate before restoring the original service;
inspect uncertain timer/action outcomes before retrying anything. Verify the
original entry route and state after rollback. No rollback has been necessary
because this candidate has not been deployed.
