# Blood Bowl Season 3

An independent development repository adapting [Bot Bowl](https://github.com/njustesen/botbowl) to the supplied Blood Bowl Season 3 rules for fixed-roster, standalone Human-versus-Human matches and AI research.

## Status

Repository setup only. The imported engine still uses the upstream BB2016 rules; the Season 3 migration has not been implemented. See [BUILD_PLAN.md](BUILD_PLAN.md) for the agreed scope and implementation stages.

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
