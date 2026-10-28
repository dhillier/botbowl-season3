# Blood Bowl Season 3

An independent development repository adapting [Bot Bowl](https://github.com/njustesen/botbowl) to the supplied Blood Bowl Season 3 rules for fixed-roster, standalone Human-versus-Human matches and AI research.

## Status

The Season 3 migration preview includes fixed Human profiles with PA, native target characteristics, revised ball resolution/re-rolls, Secure the Ball, declared Blitz targets, jumping over downed players, stalling/Forego Activation, end-of-turn stunned recovery, Human starting-skill restrictions, selected-roster kick-off/weather/injury/drive flow, audited scoring/throw-in boundaries, multiple team re-rolls per planned path, and native PA/AG/AV display. These actions include engine resolution, legal choices, bot/pathfinding integration and controls for preview matches in the existing web interface. The automated rules gates pass for the recorded fixed-roster model; release acceptance remains pending and ordinary defaults still use upstream BB2016. See the [coverage and validation notes](docs/season3-migration.md) and [build plan](BUILD_PLAN.md).

With the project environment installed, run a headless scripted-versus-scripted preview from the repository root:

```sh
python -m examples.season3_preview --seed 0
python -m pytest tests/game/test_season3.py tests/game/test_secure_ball.py tests/game/test_season3_actions.py tests/game/test_season3_status.py tests/game/test_season3_flow.py tests/game/test_season3_ball.py tests/game/test_season3_pathfinding.py tests/game/test_season3_geometry.py tests/game/test_season3_acceptance.py -q
```

The [acceptance record](docs/season3-acceptance.md) pins the digital interception model, records the user-approved modified-1-or-less fumble ruling, and documents the final interaction fixes. The versioned Season 3 RL interface now supplies observations, player/placement actions, legal masks and acting-coach transition metadata. Representative coach playtesting, review of the digital ruler convention and learning/evaluation work remain. Use the dedicated Season 3 IDs for small learning experiments; coach review and performance/evaluation work remain before expensive training or a full-fidelity release claim.

## Season 3 RL interface

`botbowl-s3-v1` and `botbowl-s3-pathfinding-v1` expose the versioned Gym 0.26 interface for the fixed Human match. Observations include PA, statuses, re-roll resources, pending dice/routes and off-pitch identities. The 10,256-action space has matching legal masks, including individual placements and defensive decisions. Self-play exposes both coaches; a supplied random or scripted opponent leaves the home coach to the learner. Old v4 policies require explicit migration.

```sh
python -m examples.season3_rl --seed 0
python -m examples.season3_rl --seed 4 --opponent scripted
python -m pytest tests/ai/test_season3_env.py -q
```

See the [RL contract and usage](docs/season3-rl.md) for shapes, action indices, coach/reward handling, checkpoint metadata and limits. No learned opponent or training job is included.

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
