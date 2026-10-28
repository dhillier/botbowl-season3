# Season 3 RL interface, version 1

28 October 2026. This is the fixed-Human, full-pitch decision interface for the
recorded [Season 3 rules model](season3-acceptance.md). It supports externally
controlled self-play and a home learner against an engine bot. It provides no
trained policy, optimizer, production dataset or GPU training job.

## Starting a rollout

Use the repository's pinned Gym 0.26 environment:

```python
import gym
import botbowl  # Registers both the legacy and Season 3 IDs.

env = gym.make('botbowl-s3-v1')
observation, info = env.reset(seed=0)
interface = info['interface']  # Save this with datasets and model checkpoints.
while True:
    actor = info['actor']
    action = env.action_space.sample(mask=observation['action_mask'])
    next_observation, reward, terminated, truncated, next_info = env.step(action)
    # A collector can store observation, actor, action, reward, terminal flags
    # and next_info['decision']; that record contains the exact legal indices.
    observation, info = next_observation, next_info
    if terminated or truncated:
        break
env.close()
```

`botbowl-s3-pathfinding-v1` enables the engine's multi-step path actions. The
default ID uses direct movement. Both use the same shapes and action slots, with
different interface fingerprints because MOVE has different route semantics.

`Season3Env(opponent='random')` controls the home team against a seeded random
bot. `Season3Env(opponent=MyScriptedBot('opponent'))` accepts the existing scripted
bot from `examples.scripted_bot_example`; other non-human engine Agents can also
be supplied. The opponent handles its start/coin-toss and subsequent choices
automatically. All returned decisions then belong to the home learner, including
defensive decisions during the opponent's turn. With `opponent=None`, both coaches
are external and every pending decision is returned.

Executable smoke rollouts use offered formation macros and finish legal setups,
then sample remaining choices from the mask:

```sh
python -m examples.season3_rl --seed 0
python -m examples.season3_rl --seed 1 --pathfinding
python -m examples.season3_rl --seed 2 --opponent random
python -m examples.season3_rl --seed 3 --pathfinding --opponent random
python -m examples.season3_rl --seed 4 --opponent scripted
```

## Coach perspective and action encoding

The acting coach determines observation rows, ownership features and coordinates.
Rows 0–11 are that coach's prepared roster, in its stable file order; rows 12–23
are the opposing roster. Off-pitch players retain their rows. Away-coach decisions
mirror x as `27 - x`; y is unchanged. Both coaches therefore attack toward x=1.
The 28×17 arena includes crowd squares used by pushes.

The fixed `Discrete(10256)` action space has these contiguous blocks:

| Block | Offset | Size | Payload |
| --- | ---: | ---: | --- |
| Simple choices | 0 | 32 | Explicit action-type order |
| Player choices | 32 | 216 | Nine types × 24 relative roster slots |
| Position choices | 248 | 4,284 | Nine types × 476 squares, row-major |
| Player placement | 4,532 | 5,724 | Own roster slot × 477 destinations; 476 means reserves |

`Season3ActionCodec.encode(Action(...))` and `.decode(index)` round-trip these
structural slots. The codec's `action_manifest()` records their exact type order.
The placement block represents individual reserves, swaps and Solid Defence
placements. Player choices include Secure the Ball, Forego Activation and Blitz
target selection; positions include Jump. Simple choices include Argue the Call,
Bribes, treatment, formations and re-rolls. The engine aliases
`SELECT_SECOND_ROLL` to `DONT_USE_REROLL`; the shared slot uses the current
procedure's semantics, and both casualty rolls are visible when choosing treatment.

`action_mask` is an int8 `MultiBinary(10256)`. A 1 means the complete payload can
be submitted now. Mask construction merges all enabled ActionChoices, excludes
disabled choices, requires a legal formation before End Setup, and excludes a
reserve being placed onto an occupied square. Unsupported actions, ambiguous
payloads and mixed enabled coach ownership fail explicitly. The environment
rejects masked, out-of-range, boolean and non-integral indices before engine
mutation. `decode()` alone is structural and does not promise current legality.

## Observation dictionary

The exported name tuples in `botbowl/ai/season3_env.py` define feature order.

| Key | Shape | Dtype and meaning |
| --- | --- | --- |
| `spatial` | 63×17×28 | float32, 0–1; native characteristics, statuses, ownership, skills, ball/terrain, declared target, pending tests and planned route |
| `players` | 24×56 | float32, 0–1; stable identities including bench, KO, casualties, ejection, heat and snack exclusions |
| `global` | 241 | float32, 0–1; weather, team resources, action allowances, selected groups, current/stack/re-roll procedures and decision ownership |
| `public_rolls` | 8×46 | float32, -1–1; up to eight already-rolled pending tests, their targets/modifiers and RollType |
| `action_features` | 10,256×3 | float32, -1–1; test-success preview, signed Block dice / 3, and preview-present flag, indexed by action |
| `action_mask` | 10,256 | int8, 0/1; current legal actions |

AG and PA are distinct native targets divided by 6; MA uses 10, ST 8, AV 12.
A PA-present feature distinguishes a missing characteristic from an empty square.
Counts use `n/(1+abs(n))`, preserving differences even when re-rolls, Bribes or
scores accumulate beyond the legacy feature scales. `rerolls` is the total usable
pool; `drive_rerolls` identifies its temporary subset and must not be added again.
Having spent a re-roll this turn is separate from being able to spend another.

For each selected starting skill, possession, status-based usability and previous
spending are separate features. Other features include Distracted, stalling's
activation snapshot, stunned-at-turn-start recovery, Cheering Fans, Fan Factor,
Secure the Ball allowance, kick-off selected/eligible players and Solid Defence's
original positions. The adapter rejects unselected roles/skills at binding.

Pending-test origins/destinations and ordered remaining path squares make a
re-roll decision interpretable after a chosen multi-step move. Pass target and
actual landing are separate, including inaccurate-pass interception decisions.
Public rolls traverse the pending stack from the top, then each procedure's
`roll`, `roll_first`, `roll_second`, deduplicating shared rolls. Dice values and
targets are divided by 16; modifiers use the signed bounded encoding. Block faces
use their enum values. Empty rows have present=0. No RNG state, future roll,
opponent policy internals or wall clocks are included. Observation reads consume
no randomness and agree after engine search undo/redo.

Action previews retain engine semantics. Path previews include route risks and
the available re-roll budget; downstream Block/hand-off/foul consequences remain
separate. Direct roll previews multiply the displayed test chances without
assuming re-roll use. FOUL previews use 2D6. These are test previews, not complete
possession probabilities, expected rewards or globally optimal routes. Each
action has its own row, so Jump and MOVE to the same square do not overwrite one
another. Illegal-action rows are zero.

## Episodes, rewards and recording

The API is Gym 0.26: reset returns `(observation, info)` and step returns
`(observation, reward, terminated, truncated, info)`. `info['actor']` identifies
the next coach as home=0 or away=1. `info['decision']['actor']` is the coach who
just acted; the decision also records the encoded index, action type, relative
player slot, raw engine position and exact legal indices. Reset info supplies the
game seed and full interface metadata; later info includes its fingerprint.

Self-play does not alternate on every step. Interceptions, disadvantageous Blocks,
pushes, re-rolls and treatment can hand decisions to either coach or keep the
same coach. A trainer must retain coach identity for every transition.

Rewards are zero until match completion, then +1/0/-1 for win/draw/loss from the
**pre-step actor's** perspective. `info['terminal_rewards']` supplies both home and
away outcomes for credit assignment to earlier decisions. A self-play collector
must use those identities when building returns; blindly treating successive
decisions as one player's ordinary transitions will assign credit incorrectly.
This slice does not prescribe a learning algorithm or reward shaping.

A completed match returns a valid final observation with an all-zero action mask
and actor=None. The default 10,000-decision limit sets truncated=True if a policy
keeps rearranging setup or otherwise fails to finish. A truncated observation
retains its legal mask for value bootstrapping and has no terminal outcome reward.
Both conditions require reset before another step.

Observations are roughly 255 KiB each before compression. A collector can retain
the previous observation and append `next_info['decision']` and eventual outcome;
there is no persistent dataset writer in this slice. Benchmark throughput and
choose storage/compression before generating a large replay buffer. Custom
opponents may need their own seeded implementation for reproducible internal
choices; the provided random opponent is seeded by the environment.

## Compatibility and validation

Save `env.unwrapped.adapter.metadata()` with every checkpoint/dataset and call
`adapter.require_compatible(saved_metadata)` before applying it. Metadata pins
rules interpretation version, action and observation schemas, ordered roster
profiles, feature units, shape and pathfinding semantics under a SHA-256
fingerprint. Missing or changed metadata fails. Schema/semantic changes require
version review and updated golden fingerprints in tests.

Legacy `botbowl-*-v4` environments retain their old API and BB2016 defaults.
Constructing their adapter with BB2025 now fails with a pointer to Season3Env.
Legacy A2C examples, wrappers, tuple observations, datasets and saved weights need
explicit migration before use with this dictionary/five-return API.

Policies must sample with the mask. Gym's generic `check_env` samples unmasked
indices and therefore reaches the deliberate illegal-action rejection; registered
rollouts use Gym's passive checks with masked actions. Gym also emits advisory
warnings about these structured matrix observations and float feature planes.
Every returned observation is checked against the declared spaces in integration
tests; these are feature tensors for a custom policy, not RGB images.

Validation includes every action index in both orientations, mask/engine round
trips, PA/status/resource features, choice ownership, treatment aliases, disabled
Block choices, re-roll context, search reversal, terminal/truncation semantics,
and five full masked rollouts. See [migration validation](season3-migration.md)
for current suite counts. Representative coach review, throughput measurements,
a learning/evaluation pipeline and Windows/5090 validation remain before expensive
training. No training, deployment or change to ordinary game defaults occurred.
