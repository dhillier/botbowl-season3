# Community extraction record

Extracted on 31 October 2026. The community branch descends from BotBowl commit `3e550bda3666c39efe478fb9465646af24576665` through the initial migration commits to `91c2bf1957d3c27d4b6b6bfe705211ecc29153bc`. The latter includes the initial Season 3 Gym interface and airborne/carried-ball observation correction, before custom learning experiments began.

Later reusable changes were extracted from research snapshot `bb07205b17f6adf69eee568bdf437b9f7537523e`, preserving their source behavior:

| Original commit | Retained framework change |
| --- | --- |
| `83bbd04` | Scripted bot handles combined block-die/re-roll choices exposed to external agents. |
| `8b57537` | Either home or away can be the learner against a supplied opponent. |
| `ded2809` | Handoff previews include receiver catch risk and the shared remaining re-roll budget; Python/native pathfinders agree; observation contract becomes v2. |

The corresponding generic environment, scripted-bot and handoff regression tests are retained. Research-specific trainers, checkpoint converters, teachers and reports from those commits are excluded. At extraction commit `7888cc6`, the `botbowl/core`, web/data trees, generic AI modules and scripted example match the source snapshot.

A subsequent CI run exposed an inherited `Game.swap` rollback defect during setup reorganization. The community engine now explicitly logs swapped player positions and board cells. Deterministic regressions cover undo/redo in BB2016 and Season 3. Ordinary swap execution, rules and agent-interface fingerprints are unchanged; downstream research receives the same fix through its engine pin.

This branch does not descend from the custom-learning commits. BotBowl's upstream examples and history remain intact. Community documentation and CI describe only the reusable framework. Historical migration commits can still contain the original project planning text; no experiment history is imported.

Downstream research retains a vendored engine snapshot to preserve imports and reproducible source archives. Its `community-engine.lock.json` pins this repository's exact commit and Git blobs, and its check verifies the shared runtime against that pin. New framework fixes should land here first and be synchronized downstream deliberately.

The current release status remains a fixed-Human preview, with coach playtesting and digital-ruler review pending. Test and smoke results for the extraction are recorded in [split validation](split-validation.md).
