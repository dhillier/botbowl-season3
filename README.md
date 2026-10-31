# BotBowl Season 3

A community adaptation of [BotBowl](https://github.com/njustesen/botbowl) for Blood Bowl Season 3, retaining its Python simulation, web interface, pathfinding, scripted bots and generic agent interfaces.

**Current scope: a preview for fixed Human-versus-Human standalone matches.** This is not an all-team or league implementation. Automated rule scenarios are covered; representative coach playtesting and review of the digital interception ruler remain release gates. Ordinary game defaults and legacy v4 environments still use BB2016. Select Season 3 explicitly.

The local team expansion now includes data for all 30 supplied Season 3 rosters (159 positionals), plus an inventory of all 108 skills and traits. Data availability is separate from rules certification. Skill mechanics are being implemented and checked before validating additional teams; see `python scripts/skill_audit.py` for the remaining work. The existing prepared Human squads and Human-only RL interface retain their scope.

## Get started

Use Python 3.8–3.11 and a C++ compiler (Visual Studio C++ Build Tools on Windows). The dependency set is inherited from BotBowl; use a dedicated environment.

```sh
git clone https://github.com/dhillier/botbowl-season3.git
cd botbowl-season3
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install setuptools==68.2.2 wheel==0.41.3
python -m pip install -r requirements.txt
python -m pip install --no-build-isolation -e .
python -m examples.season3_preview --seed 0
```

Verify the native pathfinder and run the suite:

```sh
python -c "from botbowl.core.pathfinding import cython_pathfinding; print(cython_pathfinding.__file__)"
python scripts/build_web_js.py --check
python -m pytest -q
```

To run the CI checks locally with saved logs and no GitHub Actions usage:

```sh
python scripts/check_local.py
# Faster checks while developing skill mechanics:
python scripts/check_local.py --suite skills
```

This uses the current Python environment and installed dependencies. Add `--rebuild-native` after changing Cython sources. Reports are written under the ignored `artifacts/local-checks/` directory. A green test run does not certify skills still listed in the skill audit.

Access the complete team data independently of prepared squads:

```python
from botbowl import load_team_catalog, get_team_profile, load_rule_set
catalog = load_team_catalog()            # 30 rosters, including source hashes
vampires = get_team_profile('Vampire')   # positions, limits, skills, costs and staff
rules = load_rule_set('BB2025')          # all 159 Season 3 positional profiles
runner = rules.get_role('Vampire Runner', 'Vampire')
```

Start the existing local web interface with `python examples/server_example.py`, open `http://127.0.0.1:1234`, and select the Season 3 preview mode. This entry point also registers the scripted opponent. See [installation notes](docs/installation.md) for inherited platform details.

## Included

- Season 3 Human profiles, PA, passing/catching/interception and re-roll resolution.
- Secure the Ball, declared Blitz targets, jumping, stalling, stunned recovery and applicable starting skills.
- Selected-roster kick-off, weather, injury, drive flow, scoring and ball boundaries.
- Python and Cython pathfinding, web controls and compatible scripted/random opponents.
- Versioned Gym 0.26 observations, actions, legal masks, either learner side and public probability previews.
- Regression tests, rule interpretations and provenance.

The generic agent environments are `botbowl-s3-v1` and `botbowl-s3-pathfinding-v1`:

```sh
python -m examples.season3_rl --seed 0
python -m examples.season3_rl --seed 4 --opponent scripted --pathfinding
```

See [rule coverage](docs/season3-migration.md), [acceptance and interpretation decisions](docs/season3-acceptance.md), and the [agent interface contract](docs/season3-rl.md). League progression remains outside the standalone engine's scope. Additional team data is available; complete squad loading, skill certification and team playtesting are separate remaining steps.

## Community boundary

This repository owns the reusable game framework. Project-specific neural policies, training curricula, datasets, checkpoints and experiment reports live separately. The original upstream research examples remain as part of BotBowl; they are not certified for Season 3.

Engine fixes discovered while developing agents should be contributed here with focused tests. Agents should pin an engine revision and validate their observation/action fingerprints. See [CONTRIBUTING.md](CONTRIBUTING.md), the [community roadmap](BUILD_PLAN.md), and the [extraction record](docs/community-extraction.md).

## Attribution and license

BotBowl's original Git history is retained. [UPSTREAM.md](UPSTREAM.md) records the baseline, and [README.upstream.md](README.upstream.md) preserves the original introduction and credits. The original source [LICENSE](LICENSE) is unchanged; as upstream states, it does not cover the graphics. See the original README for graphics notices and paper attribution. Supplied rule PDFs are not distributed. This is not an official Games Workshop project.
