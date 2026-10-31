# Season 3 incremental team validation

The local validation runner is `scripts/validate_season3_teams.py`. It tests each
team separately and stops on the first failure. Reports and failure traces stay
in the ignored `artifacts/team-validation/` directory.

```sh
python scripts/validate_season3_teams.py --team amazon
python scripts/validate_season3_teams.py --team vampire --team wood-elf
python scripts/validate_season3_teams.py
python scripts/validate_season3_teams.py --resume artifacts/team-validation/RUN_DIRECTORY
```

The matrix contains 37 coverage squads across all 30 rosters. Squads contain
11 players, except Snotlings, whose 16-player squad supplies Swarming reserves.
Each costs at most 1,000,000 including purchased re-rolls and Apothecaries,
and obeys positional, shared Big Guy and Insignificant limits. Every one of the
159 positional profiles appears in at least one squad. Chaos Chosen has three
variants, Chaos Renegades four, Old World Alliance two and Underworld Denizens
two. These are coverage fixtures, not recommended competitive rosters.

Each squad plays the prepared Human baseline at home with seed 0 and away with
seed 1, using the actual scripted bot and the native pathfinder. The 74-match
matrix checks legal actions, board/player consistency, ball possession, all
positionals deployed, and completion of both halves with normal turn limits.
Each match has a 180-second timeout and a procedure-step limit. No action errors
are hidden by substituting random actions. Reports retain scores, actions,
reported skills, team-rule events, maximum players on the pitch, deployed
positionals and timing. Resume only reuses passing
results with the same source fingerprint.

`examples/season3_teams.py` exposes `coverage_squads(team_id)` and
`build_team(squad)` for standalone clients. For example:

```python
from examples.season3_teams import coverage_squads, build_team

squad = next(coverage_squads('vampire'))
team = build_team(squad)
```

The helper nominates a captain for Human and Orc coverage squads. Other clients
can call `team.nominate_captain(player)` before creating the game. This adds Pro
and the captain's match effects. Nomination is optional; the fixed Human preview
does not nominate a captain, preserving its existing RL contract.

The deterministic skill scenarios remain a separate gate:

```sh
python scripts/skill_audit.py --require-complete
python scripts/check_local.py
```

## Findings from the first incremental pass

- Chaos Renegades exposed stale ball possession when end-of-drive heat removed
  the carrier. Possession now expires before drive-end removals, without a bounce.
- Elven Union exposed a planning crash for a completely surrounded Side Step
  player. Push-square previews now fall back to the normal chain-push choices.
- Goblins exposed ordinary Move planning for a Fanatic. The scripted bot now
  declares Ball & Chain, evaluates its three possible directional destinations,
  avoids obvious friendly/crowd risks, and stops before rushing.
- Old World Alliance's Treeman exposed blocked chain pushes. Stand Firm or an
  immovable player now stops preceding movement while the original knockdown
  still resolves in place. No successful push or follow-up is reported.
- Recruitment reversal exposed unlogged dictionary insertions. Undo and replay
  now restore both player registries, the roster and reserves for Masters of
  Undeath and Plague Ridden.
- Setup checks now count end-zone corner squares toward their wide zone. The
  Swarming placement choices respect the same limit.

## Live team special rules

The incremental review also found four team rules present in roster metadata
but missing from match resolution. These now have deterministic tests in
`tests/game/test_season3_team_rules.py`:

| Rule | Implemented match behavior |
| --- | --- |
| Bribery and Corruption | Optional once-per-game re-roll of a natural 1 when arguing the call, without spending a Team Re-roll. |
| Masters of Undeath | After an eligible opponent dies on the Casualty Table and treatment resolves, optionally recruit a roster Lineman into reserves, once per game, including beyond 16 players. Shambling Undead can choose a Skeleton or Zombie. |
| Swarming | After both normal setups and before kick-off, add up to D3 available reserve Linemen, allowing more than 11 players while observing setup boundaries. |
| Team Captain | Optional non-Big Guy nomination grants Pro; an on-pitch captain can make a Team Re-roll free on a natural 6 and must be fielded during setup when available. |

The supplied `10 - The Teams.pdf`, pages 6-9, is the source for these rules.
SHA-256: `8f7dd1ecb95f735a55dfe891163e1058e9186e4423889f706e42a3d4db7eefb4`.
The PDF stays outside Git. Brawlin' Brutes SPP changes, Low Cost Linemen CTV,
Favoured alignment/inducement eligibility, post-game recruitment and captain
replacement belong to league/drafting workflows and are not implemented by this
standalone match expansion. Their roster metadata remains available.

## Completed team matrix, 31 October 2026

All **74 matches across 37 squads and 30 teams passed** on the same source
fingerprint. Every one of the 159 positional profiles was deployed. Each squad
completed one home and one away match against the Human baseline; both halves
reached their normal eight turns. The longest match took 13.5 seconds.

| Team | Squads | Matches passed |
| --- | ---: | ---: |
| Amazon | 1 | 2/2 |
| Black Orc | 1 | 2/2 |
| Bretonnian | 1 | 2/2 |
| Chaos Chosen | 3 | 6/6 |
| Chaos Dwarf | 1 | 2/2 |
| Chaos Renegades | 4 | 8/8 |
| Dark Elf | 1 | 2/2 |
| Dwarf | 1 | 2/2 |
| Elven Union | 1 | 2/2 |
| Gnome | 1 | 2/2 |
| Goblin | 1 | 2/2 |
| Halfling | 1 | 2/2 |
| High Elf | 1 | 2/2 |
| Human | 1 | 2/2 |
| Imperial Nobility | 1 | 2/2 |
| Khorne | 1 | 2/2 |
| Lizardmen | 1 | 2/2 |
| Necromantic Horror | 1 | 2/2 |
| Norse | 1 | 2/2 |
| Nurgle | 1 | 2/2 |
| Ogre | 1 | 2/2 |
| Old World Alliance | 2 | 4/4 |
| Orc | 1 | 2/2 |
| Shambling Undead | 1 | 2/2 |
| Skaven | 1 | 2/2 |
| Snotling | 1 | 2/2 |
| Tomb Kings | 1 | 2/2 |
| Underworld Denizens | 2 | 4/4 |
| Vampire | 1 | 2/2 |
| Wood Elf | 1 | 2/2 |

The Human and Orc matches exercised captain re-rolls. Both Snotling matches
fielded 13 players through Swarming. Rare events such as raising a dead player
and retrying an argue-call 1 have deterministic scenario coverage independently
of whether these particular match seeds produced them.

Local reports: `artifacts/team-validation/20261031T223227Z/`.
Source fingerprint (Python version, native binary and relevant source/data files):
`224b888e36bb29be77c31bf6c42ddcb17bd635d6f638a444dece37afaab21ff6`.
All case fingerprints were checked against the final source after completion.
The initial seven team-rule checks were reused by the full run only after their
fingerprints matched; earlier diagnostic runs are not counted in this matrix.

## Local regression gate

On 31 October 2026, the full local check passed **2,267 tests** with 116 existing
Gym/deprecation warnings, plus dependency consistency, native pathfinder import,
fatal lint and web bundle checks. JavaScript syntax validation also passed.
`skill_audit.py --require-complete` reported 108 skills and traits with no open
certification entries. These are the recorded scenario gates, not an exhaustive
proof of every possible rules combination.

The environment was Windows with Python 3.11.9 and the compiled Cython
pathfinder. Logs and JUnit output are in the ignored
`artifacts/local-checks/20261031T223329Z/` directory. No GitHub Actions run was
requested for these checks.

## What this establishes

This is an initial full-match integration gate for the recorded squads and seeds.
It does not certify every match-up, skill combination, purchased inducement,
league progression or tactical policy. Merely deploying a player does not prove
the scripted bot used every skill that player possesses. Bombs, teammate throws
and kicks, Hypnotic Gaze and other specialist actions still need tactical planning.
The bot's route probabilities retain the limitations recorded in
[migration coverage](season3-migration.md). The web preview's prepared squads and
the versioned RL interfaces retain their existing scope; these coverage squads
are available through the standalone Python helper.

Further validation can expand seeds, opponents, roster compositions and coach
playtesting without changing the fixed Human RL contract.
