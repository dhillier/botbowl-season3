# Blood Bowl Season 3

An independent development repository adapting [Bot Bowl](https://github.com/njustesen/botbowl) to the supplied Blood Bowl Season 3 rules for fixed-roster, standalone Human-versus-Human matches and AI research.

## Status

The Season 3 migration preview includes fixed Human profiles with PA, native target characteristics, revised ball resolution/re-rolls, Secure the Ball, declared Blitz targets, jumping over downed players, stalling/Forego Activation, end-of-turn stunned recovery, and the status restrictions on Human starting skills. These actions include engine resolution, legal choices, bot/pathfinding integration and controls for preview matches in the existing web interface. It is incomplete; ordinary defaults still use upstream BB2016. See the [coverage and validation notes](docs/season3-migration.md) and [build plan](BUILD_PLAN.md).

With the project environment installed, run a headless scripted-versus-scripted preview from the repository root:

```sh
python -m examples.season3_preview --seed 0
python -m pytest tests/game/test_season3.py tests/game/test_secure_ball.py tests/game/test_season3_actions.py tests/game/test_season3_status.py -q
```

Revised match events/tables, remaining timing/geometry interactions and versioned observations remain to be migrated. Do not use this preview for Season 3 training or claim full rules fidelity yet.

## Scope

- Preserve the fixed Human roster composition, existing interface, scripted opponent, pathfinding assistance, and headless AI environments.
- Implement Season 3 changes needed for those matches, including Passing Ability, Secure the Ball, and applicable core rules and starting skills.
- Update probability calculations, pathfinding, search, observations, and legal-action masks alongside the match engine.
- Keep league play, progression, roster building, other teams, and optional player types outside the initial scope.

## Upstream provenance

This repository retains Bot Bowl's Git history. The starting revision and source references are recorded in [UPSTREAM.md](UPSTREAM.md). The original project introduction and installation instructions are preserved in [README.upstream.md](README.upstream.md).

Upstream installation instructions describe the older research environment. Dependencies and hardware compatibility will be pinned and verified for this project before training; do not assume a current Python environment works unchanged.

## Local work

The local remote named `origin` is reserved for this independent repository. The `upstream` remote fetches the original project and has its push URL disabled. Changes to this project are committed and pushed here; contributing back upstream would be a separate decision.

Use `codex/` branches for implementation work. The initial setup commit is on `main`.

Local rule PDFs, credentials, virtual environments, training datasets, model checkpoints, and generated replays are not part of the initial repository contents. The build plan references the supplied local rules folder.

## Attribution and license

Based on Bot Bowl by Niels Justesen and its contributors. The original source license is retained unchanged in [LICENSE](LICENSE). As upstream states, that license does not cover its graphics. See [README.upstream.md](README.upstream.md) for the original attribution, paper citation, and graphics notices.

This README was replaced for the independent Season 3 project on 28 October 2026; the original is preserved separately. This is not an official Games Workshop project.
