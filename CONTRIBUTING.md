# Contributing

Use focused branches and pull requests for the reusable Season 3 framework. Describe the rule or interface defect, the corrected behavior and its regression evidence.

## What belongs here

- Rules, roster/configuration data, pathfinding and forward-model fixes.
- Existing web UI integration and scripted/random bot compatibility.
- Generic agent observations, actions, masks, coach ownership and probability previews (`botbowl/ai/season3_env.py` and `season3_actions.py`).
- Tests, install/build support and documentation needed to use those components.

Agent architectures, optimization, rewards/curricula, tactical teachers, scenario collections and experiment reports belong in downstream research repositories. The `botbowl/ai` directory is not a blanket exclusion: generic agent interfaces are part of the framework.

## Checks

Follow the [README setup](README.md). Build the native extension, run `python -m pytest -q`, and verify `python scripts/build_web_js.py --check`. For engine changes, test exact dice outcomes, legal choices, coach ownership and forward-model undo/redo where relevant. Pathfinding changes need Python/native agreement. Use `python -m examples.season3_preview --seed 0` for full-match integration.

Keep rule/roster/action/observation versions explicit. A changed fingerprint must have a documented reason and migration guidance. Do not silently load an incompatible checkpoint or change the ordinary BB2016 defaults.

Retain upstream attribution and license notices. Do not commit rule PDFs, credentials, generated datasets, checkpoints or personal machine paths. Use `codex/` for agent-created branches.
