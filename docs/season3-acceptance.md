# Season 3 rules acceptance record

28 October 2026. Scope: the prepared Human roster, ordinary standalone matches,
and effects reachable through that roster and the kick-off table. This records
the eighth rules migration slice. The ninth slice adds the
[versioned RL adapter](season3-rl.md). Human playtesting remains a release gate; the shipped default remains BB2016.

## Source and decision precedence

Use the supplied PDFs as the baseline, with the official May 2026 commentary
where it clarifies the included rules. User rulings take precedence for this
project and are identified below. Digital geometry conventions are implementation
decisions, not official published measurements or new tabletop rules.

The [official May 2026 FAQ and errata](https://assets.warhammer-community.com/eng_20-05_blood_bowl_faq_errata-gytvlserev-ngihd3chox.pdf)
confirms that modified D6 results can fall below 1, Rain affects Secure the Ball,
and its opponent-exclusion requirement is checked at declaration. It does not
resolve the supplied fumble wording or specify numerical interception geometry.
The audit also corrected clearing Distracted before the Blitz target declaration.
Existing tests cover the other applicable FAQ points: Charge team re-rolls,
repeated jumps, inactive-team possession after a Pass/Hand-off, and Distracted
Block/Dodge restrictions.

## Fumbles: user ruling accepted

The supplied game chapter, PDF page 44, says a natural 1 or exactly 1 after
modifiers. The user explicitly chose **modified 1 or less** on 28 October 2026.
The engine therefore uses a natural 1 or a modified result <= 1, with the natural
6 success rule retained. For a Long Bomb with only its -3 range modifier, natural
1–4 fumble, 5 is inaccurate, and 6 is accurate.

This is an approved project interpretation, not an official erratum. Tests
enumerate all natural results across the four ranges, sunny weather and marking,
and check that both Pass and team re-rolls resolve before flight/interception.
The existing no-second-re-roll cases remain part of acceptance.

## Bomb rethrows with no Passing Ability: user ruling accepted

For the all-team skill expansion, the user approved **drop and explode in place**
on 31 October 2026 when a player with PA "-" catches a bomb and must rethrow it.
The bomb explodes in that player's square without a passing roll or a bounce;
the normal explosion effects then resolve. This is an approved project
interpretation, not an official erratum.

`tests/game/test_season3_bombs.py` covers the Woodland Fox case, including the
explosion position, injury resolution and preservation of the catcher's unused
activation. Separate scenarios cover ordinary rethrows, failed catches,
interceptions and turnovers. This closes the Bombardier skill audit entry;
individual teams still require incremental match validation.

## Interception: pinned digital geometry

The supplied game chapter, PDF pages 44–47, requires ruler overlap with an eligible
opponent's square, following the actual landing square after scatter. Both supplied
examples remain regression fixtures. The PDFs contain no numerical ruler width.

The project adopts a 59 mm ruler width on 34 mm pitch squares, dimensions reported
by the [Jervis BB2025 ruler implementation at commit 66f5a9c5](https://github.com/cmelchior/jervis-ffb/blob/66f5a9c5b149ba555ef2d0b715a65b58cef4c8bd/modules/jervis-engine/rules-bb2025/src/commonMain/kotlin/com/jervisffb/engine/bb2025/tables/RangeRuler2025.kt).
Its documented FFB convention also supplies the endpoint test: an eligible square's
centre must be strictly nearer to each endpoint than those endpoints are to each
other. The ratio here is exactly 59/34, without rounding to 1.74. These dimensions
were not measured from the user's physical components and are not asserted to be
an official Season 3 specification.

`botbowl/core/geometry.py` independently computes positive square/strip overlap
using integer arithmetic. It replaces grid-line neighbours and Chebyshev endpoint
limits for BB2025. The entire candidate square counts; a centre-only test does
not. Endpoint squares and zero-length passes are excluded. Choices retain roster
order and filter off-pitch, prone, Distracted and No Hands players. Ordinary
accurate/inaccurate interception penalties and decision ownership are unchanged.

An independent floating-point polygon-clipping oracle checks every square around
each non-zero vector in the 0–13 by 0–13 chart envelope. Additional tests cover
rotation, reflection, translation, pass reversal, adjacent-row overlap, endpoint
limits, status/roster order, the supplied examples and interception after scatter.
This establishes correctness for the stated model, not equivalence to every
manufactured tabletop ruler. The older Luccini interception chart uses a different
pitch scale and is not treated as a Season 3 golden dataset.

## Final interaction audit

| Boundary | Evidence and resulting change |
| --- | --- |
| Rain / Secure the Ball / planning | Corrected resolution, direct movement and jump previews, and both Python/Cython pathfinders to 3+ in Rain. AG and Sure Hands still do not apply. Tests cover natural 2 failing, team re-roll 3 succeeding, exclusion at declaration, and subsequent marking not becoming an AG penalty. |
| Blizzard / movement / jump / Blitz / pickup | Corrected the Season 3 engine's Rush modifier from +1 to -1. Controlled natural 2/3 cases check failure/success before later jump, Block or pickup dice; pathfinding already used 3+. Legacy engine resolution is retained. |
| Follow-up / POW or crowd / touchdown | A following carrier must complete the selected Block's effects before the drive ends. Tests require the follow-up decision before injury dice, then armour/injury, casualty or opposing Apothecary treatment before scoring, followed by one drive-end recovery. |
| Both Down / ball / touchdown or turnover | Both unprotected players become prone before any bouncing ball can be caught. A Season 3 Block-resolution boundary finishes all pending pushes, injuries, treatment and ball effects before awarding a valid touchdown or turnover. Tests prevent a falling attacker catching the defender's ball, require both armour checks even when another player scores, and preserve chain-push scoring and friendly-surf turnovers. |
| Defensive treatment / decision ownership | Corrected an inherited call to a nonexistent clock method when the opponent chooses Apothecary treatment. A secondary decision clock now starts and is removed on completion. Treatment belongs to the injured player's coach. |
| Search / newly created procedures | Scoring candidates and turnover state are reversible. Selection and KO-recovery bookkeeping now uses logged assignments when procedures are created after search is enabled. Tests undo/redo Solid Defence, Quick Snap, Charge, pending defensive treatment and recovery, alongside the earlier action/ball/drive reversal fixtures. |
| Ball / boundaries / scoring | Earlier tests remain gates: PA before scatter/interception, re-roll order, catching eligibility, Pass/Hand-off possession turnovers, friendly recovery versus fumble turnover, throw-in origin/direction and repeated exits, jump/dodge/Rush before scoring, and defensive touchdowns consuming the next turn. |
| Events / statuses / drives | The selected six starting skills, all kick-off entries, temporary resources/characteristics, end-of-turn stunned recovery, heat, KO recovery, halves, substitutions and final-turn scoring retain their controlled scenarios. No new roster, purchased inducement, league or optional-skill content was added. |

The game chapter's landing-resolution wording (PDF page 45) remains the basis
for a friendly recovery preserving a non-fumbled pass's turn. A fumble always
causes turnover after its ball resolution. This audit does not broaden that
exception to ordinary failed pickups, failed movement or knocked-down players.

## Validation and limits

See [migration validation](season3-migration.md) for current suite counts and
repeatable commands. Build the Cython extension before testing; Python/Cython
agreement is required. Full matches test integration stability, not tactical
strength. The inherited pathfinder is not certified globally optimal.

Automated rules acceptance for the recorded fixed-roster model is complete when
the listed regression gates pass. Remaining release gates are representative
coach playtesting, reviewing the chosen digital ruler against the desired tabletop
convention, and a repeatable opponent evaluation. The subsequent
[RL compatibility slice](season3-rl.md) supplies versioned observations, actions,
masks and acting-coach transition metadata. Production data/learning pipelines
and throughput/hardware checks remain; old observations and weights are
incompatible. No training or default switch is part of the acceptance work.

The supplied PDFs remain outside Git. Instructions to tabletop coaches are rule
content, not instructions authorizing assistant actions or repository operations.
