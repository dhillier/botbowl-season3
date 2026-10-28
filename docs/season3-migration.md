# Season 3 migration coverage

Status: incomplete preview, 28 October 2026. Rules identifier `BB2025`; configuration `season3-preview`. This is the first implementation slice of the fixed-Human, standalone-match scope in [BUILD_PLAN.md](../BUILD_PLAN.md).

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
| Movement/armour integration | Ordinary dodge/pickup and armour resolution use the new targets. Python and compiled Cython pathfinding use native dodge, pickup, hand-off, and foul targets. Hand-off previews use the receiver's AG. Formation selection treats lower AG targets as better. |
| Search and bot integration | Accurate and inaccurate pass decisions survive forward-model revert/forward, excluding wall clocks as in upstream. The scripted baseline can complete a full preview match without new decision handlers. |

The controlled scenarios live in `tests/game/test_season3.py`. They include pass-versus-AG independence, all six long-bomb die results, fumble/interception timing, scatter changing interception eligibility, out-of-bounds throw-ins, skill/team re-roll restrictions, multiple re-rolls in one turn, catch contexts, marking/rain, armour boundaries, both pathfinders, and search reversal. Existing edition tests remain regression fixtures for the shared infrastructure.

Validation on this Mac: **43 targeted scenarios passed; 529 tests passed in the complete suite** (102 existing dependency/Gym warnings). Both Python and compiled Cython cases ran. The Cython extension built successfully, and the full-match check used the preview configuration with scripted Human teams and seed 0.

## Interpretation that needs coach review

The supplied revised fumble wording says a natural 1 or a result of **exactly 1 after modifiers**. The general dice revision strikes out the lower bound on modified rolls, retaining only an upper cap of 6. Taken together, a natural 2 with a -3 passing modifier produces -1 and is an inaccurate pass; a natural 4 with that modifier produces 1 and is a fumble. A natural 6 still succeeds.

The preview follows that literal wording, rather than the upstream `modified <= 1` rule. All six long-bomb results are tested so this interpretation is visible and easy to change if the supplied document is clarified. This decision is based on visually checking the revised pages, not only PDF text extraction.

## Remaining work

| Area | Current classification / next work |
| --- | --- |
| Secure the Ball | Missing. Add declaration limits, eligibility, movement restrictions, fixed 2+ pickup, turnover, activation end, bot choices and interface action. |
| Movement and declarations | Modified/missing rules need audit and implementation: jumping over prone players, blitz target declaration, activation timing, stalling. Ordinary move/rush/block behavior is retained provisionally, not yet certified unchanged. |
| Statuses and starting skills | Audit Distracted, Tackle, Dodge, Block, Catch, Pass and Sure Hands against all reachable interactions. Native tests and Catch/interception behavior are migrated; this is not a full skill audit. No Pro/Team Captain is reachable in the chosen roster. |
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
python -m pytest tests/game/test_season3.py -q
python -m pytest -q
python -m examples.season3_preview --seed 0
```

The first command builds the optional Cython pathfinder. When it is unavailable, the engine falls back to Python and the tests explicitly skip compiled-only cases. Rebuild after changing `.pyx` sources. The example loads the preview configuration and two fresh fixed Human teams, then plays a full match between the existing scripted bots.

Development environment verified on this Mac: Apple Python 3.9.6 in `.venv`, the upstream `requirements.txt`, and a local override `urllib3==1.26.20`. The upstream urllib3 2.0.2 pin cannot import with this Apple Python's LibreSSL. To reproduce this specific environment after installing requirements, run `python -m pip install urllib3==1.26.20`. This is a recorded local compatibility workaround; dependency modernization and Windows/5090 validation remain separate work. The full upstream suite emits existing Gym observation/deprecation warnings; a passing suite does not certify those interfaces for Season 3 training.

## Local rules references

PDF page numbers below count from the first page of each supplied file:

- `BB S3/Teams/Human.pdf`, page 1: fixed Human characteristics/skills and role costs. The internal legacy role name `Lineman` is retained to preserve existing roster identities.
- `BB S3/2 - Rules and Regulations.pdf`, pages 5–6: revised dice modifiers, natural results, re-roll eligibility and restrictions.
- `BB S3/3 - The Game of Blood Bowl.pdf`, pages 4, 37, 41, 44–45: characteristic targets, passing, interception and catching; pages 23–25 guide the next Secure the Ball slice.
- `BB S3/8 - Skills & Traits.pdf`: starting skill checks; the broader audit is pending.

The supplied PDFs stay outside Git. Instructions addressed to tabletop coaches are rule content, not instructions authorizing repository operations or assistant behavior.
