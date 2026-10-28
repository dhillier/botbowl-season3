# Season 3 migration coverage

Status: incomplete preview, 28 October 2026. Rules identifier `BB2025`; configuration `season3-preview`. Three implementation slices of the fixed-Human, standalone-match scope in [BUILD_PLAN.md](../BUILD_PLAN.md) are complete: characteristics/ball resolution, Secure the Ball, and declared Blitz targets/jumping.

The ordinary configurations, web default, and registered Gym environments still select BB2016. The preview must be requested explicitly. Its configuration name, serialized game status, and example launcher all identify it as incomplete. A completed preview match establishes integration stability, not complete rules fidelity or bot strength.

## Implemented and checked in this slice

| Area | Implementation and evidence |
| --- | --- |
| Fixed roster | Same 12 identities/composition: two Blitzers, one Thrower, two Catchers, seven Linemen. Season 3 MA/ST/AG/PA/AV and starting skills loaded from a separate Human profile. Catchers now have ST3; Blitzers have Tackle. No captain or optional player types. |
| Characteristics | AG and PA use native targets; AV uses the armour target. Edition-independent target accessors update resolution, action previews, and probability helpers. PA and the profile format are serialized; passing rolls have a separate roll type. Native characteristic limits are represented; progression and new casualty effects remain outside this slice. |
| Passing | Ball passes test PA before interception. Pass and team re-rolls resolve before flight. Quick/short/long/bomb modifiers are 0/-1/-2/-3, with existing marking/weather penalties. Natural 1 fails and natural 6 succeeds. Fumbles bounce from the passer and cause a turnover; inaccurate passes scatter three times before determining the interception path. |
| Interception | Eligible players are selected using the actual landing square. Accurate passes impose -3; inaccurate passes -2, plus marking/rain. Catch does not re-roll an interception. Only the active team may use team re-rolls. Existing flight-line geometry is retained; a precise ruler/geometry audit is still pending. |
| Landing/catching | Accurate, inaccurate, hand-off, and kick catches have no base modifier; bounce/throw-in catches have -1. Existing marking/rain penalties apply. Catch still re-rolls catches. A pass landing on the ground or an opposing carrier causes turnover after resolution; a friendly recovery can preserve the turn. A fumble causes turnover even if recovered. |
| Team re-rolls | More than one may be spent in the same team turn on distinct tests. Neither a skill nor team re-roll can re-roll an already re-rolled test. Existing BB2016 configurations retain their one-team-re-roll limit. |
| Secure the Ball | Once per normal team turn, spent at declaration even when a pre-action trait fails. Requires a reachable loose ground ball more than two squares from every standing, non-Distracted opponent (diagonals count). Big Guy/No Hands players are excluded. Uses normal movement, standing, dodge and rush risks, then a fixed 2+ roll unaffected by AG, weather or Sure Hands. Team re-rolls are allowed, once per test. Success ends activation; failure bounces and turns over. Ending movement short of the ball also turns over. Starting on a loose ball, prone starts, turn reset and scoring are covered. |
| Declared Blitz target | Starting a Blitz opens a target declaration owned by the active coach. Only reachable standing opponents are offered; reachability accounts for standing up, Rushes, jumps and continuing after a successful pickup, and reserves movement for the Block. The target is chosen before activation traits roll. The Blitz allowance is consumed even if the player fails a trait or declines the Block. Undo cannot restore it. Subsequent Block choices/pathfinding are restricted to that target, and the target is exposed in the existing highlight/feature layer. Movement can continue after the Block. |
| Jumping over players | Any selected roster player can jump over adjacent prone/stunned players into eligible empty squares, following both supplied diagrams. A jump costs two movement points. Any required Rushes occur first and fail at take-off. The jump tests AG with the worse of take-off/landing marking, without a Dodge skill re-roll. A natural 1 falls at take-off; another failed jump falls at landing. Success can continue movement, recover a ball, score, or finish Secure the Ball. Team re-rolls and repeated jumps are supported. |
| Movement/armour integration | Ordinary dodge/pickup and armour resolution use the new targets. Python and compiled Cython pathfinding use native dodge, pickup, hand-off, and foul targets. Hand-off previews use the receiver's AG. Formation selection treats lower AG targets as better. |
| Search and bot integration | Pass, Secure the Ball, Blitz declaration and jump decisions survive forward-model revert/forward, including allowances, targets and pending re-rolls; wall clocks remain excluded as upstream. Both pathfinders include jump edges, their movement/Rush/AG costs and declared-target block restrictions. The scripted bot declares its planned target and translates jump edges into legal actions. Secure the Ball planning compares team-wide recovery options and ends its plan at pickup; existing random/decision-dispatch bots can handle the new choices. |
| Web interface | Secure the Ball and Jump controls, roll previews, action logs and a pre-movement Blitz target choice work for preview matches. Browser verification covered both declaration flows, pickup/activation end, and a Rush followed by a marked jump into Blitz position; Flask tests cover the serialized action round trips. The existing new-game defaults remain legacy; these are controls for explicitly supplied preview matches, not a default switch. |
| Distracted foundation | Explicit serialized status plus existing Bone Head/Really Stupid/Hypnotized aliases support the eligibility check. Distracted players cannot mark, catch or assist; the explicit status clears on activation or reset. Actual new effects that apply Distracted and the full active/passive skill audit remain pending. Possession helpers distinguish a loose ball under a player from a carried ball in preview games. |

The controlled scenarios live in `tests/game/test_season3.py`, `tests/game/test_secure_ball.py` and `tests/game/test_season3_actions.py`. They cover ball resolution and re-rolls, action eligibility and timing, exact failure locations, both jump diagrams, both pathfinders (including jumps followed by later movement/Rushes), target restrictions, bot action translation, API round trips and search reversal. Existing edition tests remain regression fixtures for the shared infrastructure.

Validation on this Mac: **all 632 tests passed**, including 146 targeted Season 3 scenarios (54 for Blitz/jumping), with 102 existing dependency/Gym warnings. Both Python and compiled Cython cases ran, and the Cython extension rebuilt successfully. Full scripted preview matches completed with seeds 0, 1 and 2, using respectively 5, 7 and 6 declared Blitz targets; seed 1 also exercised a failed jump. The tracked JavaScript bundle was rebuilt, syntax-checked and verified in the browser.

## Interpretation that needs coach review

The supplied revised fumble wording says a natural 1 or a result of **exactly 1 after modifiers**. The general dice revision strikes out the lower bound on modified rolls, retaining only an upper cap of 6. Taken together, a natural 2 with a -3 passing modifier produces -1 and is an inaccurate pass; a natural 4 with that modifier produces 1 and is a fumble. A natural 6 still succeeds.

The preview follows that literal wording, rather than the upstream `modified <= 1` rule. All six long-bomb results are tested so this interpretation is visible and easy to change if the supplied document is clarified. This decision is based on visually checking the revised pages, not only PDF text extraction.

## Remaining work

| Area | Current classification / next work |
| --- | --- |
| Movement and declarations | Stalling and remaining activation timing need audit/implementation. Ordinary jumping and declared Blitz targets are migrated; broader move/rush/block interactions remain provisional. Optional Leap/Very Long Legs and other unselected-roster skills are not claimed as migrated. |
| Statuses and starting skills | Audit Distracted effects, Tackle, Dodge, Block, Catch, Pass and Sure Hands against all reachable interactions. Native tests, Catch/interception and Sure Hands/Secure the Ball behavior are migrated; this is not a full skill audit. No Pro/Team Captain is reachable in the chosen roster. |
| Match flow | Audit/revise kick-off events, weather, injury/casualty and recovery tables, substitutions, drive/half transitions, scoring timing, and resource/fan fields. Old tables and procedures currently remain. Include dependencies awarded by ordinary match events even though purchased inducements are excluded. |
| Probability and search | Pathfinding still models at most one team re-roll per planned path. Extend it to the available re-roll budget and verify resulting action previews. Wall clocks remain outside upstream search reversal. Validate combinations of new actions and statuses. |
| Frontend and RL | PA is serialized but not yet displayed by the existing web UI. Add characteristic formatting, new actions, versioned observation/action encodings and masks. Existing RL observations and saved weights are not Season 3 compatible. |
| Geometry and ball details | Audit ruler distances, interception geometry and remaining catch/bounce/throw-in/scoring edge cases against supplied diagrams. Old-edition optional skills, bombs and thrown team-mates are outside the selected roster. |
| Final acceptance | Complete the coverage audit, scenario/interaction tests, representative coach review, and repeatable match evaluation before switching the default or starting expensive training. |
| Intentionally excluded | Leagues, progression, roster construction, other teams, optional Ogres/Halflings, nominated captains, purchased inducement selection, and backward compatibility with old weights/replays. |

## Running and verifying

From the repository root, with dependencies installed:

```sh
python setup.py build_ext --inplace
python scripts/build_web_js.py --check
python -m pytest tests/game/test_season3.py tests/game/test_secure_ball.py tests/game/test_season3_actions.py -q
python -m pytest -q
python -m examples.season3_preview --seed 0
```

The first command builds the optional Cython pathfinder. When it is unavailable, the engine falls back to Python and the tests explicitly skip compiled-only cases. Rebuild after changing `.pyx` sources. The example loads the preview configuration and two fresh fixed Human teams, then plays a full match between the existing scripted bots.

The web page serves `static/dist/js/botbowl.js`, not the individual source files. After editing `botbowl/web/static/js/*.js`, run `python scripts/build_web_js.py` and commit the generated bundle too. This standard-library script reproduces the existing Gulp concatenation task without requiring its old Node dependencies. `--check` detects stale output.

Development environment verified on this Mac: Apple Python 3.9.6 in `.venv`, the upstream `requirements.txt`, and a local override `urllib3==1.26.20`. The upstream urllib3 2.0.2 pin cannot import with this Apple Python's LibreSSL. To reproduce this specific environment after installing requirements, run `python -m pip install urllib3==1.26.20`. This is a recorded local compatibility workaround; dependency modernization and Windows/5090 validation remain separate work. The full upstream suite emits existing Gym observation/deprecation warnings; a passing suite does not certify those interfaces for Season 3 training.

## Local rules references

PDF page numbers below count from the first page of each supplied file:

- `BB S3/Teams/Human.pdf`, page 1: fixed Human characteristics/skills and role costs. The internal legacy role name `Lineman` is retained to preserve existing roster identities.
- `BB S3/2 - Rules and Regulations.pdf`, pages 5–6 and 16–17: revised dice/re-roll rules and Distracted status.
- `BB S3/3 - The Game of Blood Bowl.pdf`, pages 4, 37, 41, 44–45: characteristic targets, passing, interception and catching; pages 10 and 23–25: Secure the Ball; pages 17–19: jumping diagrams, Rush order and failure locations; page 34: Blitz target declaration and movement/block sequencing.
- `BB S3/8 - Skills & Traits.pdf`, page 11: Sure Hands excludes Secure the Ball; the broader starting-skill audit is pending.

The supplied PDFs stay outside Git. Instructions addressed to tabletop coaches are rule content, not instructions authorizing repository operations or assistant behavior.
