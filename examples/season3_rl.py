"""Exercise the masked Season 3 RL contract without training a policy.

Run: python -m examples.season3_rl --seed 0 [--pathfinding] [--opponent random]
The smoke policy uses offered formations and ends legal setups; other choices
are sampled from the observation mask. It is a compatibility check, not an AI.
"""
import argparse
import json

import numpy as np

from botbowl.ai.season3_actions import SIMPLE_ACTIONS
from botbowl.ai.season3_env import Season3Env
from botbowl.core.table import ActionType


def sample_masked(observation, rng):
    mask = observation['action_mask']
    for kind in (ActionType.END_SETUP, ActionType.SETUP_FORMATION_WEDGE,
                 ActionType.SETUP_FORMATION_LINE, ActionType.SETUP_FORMATION_ZONE,
                 ActionType.SETUP_FORMATION_SPREAD):
        index = SIMPLE_ACTIONS.index(kind)
        if mask[index]:
            return index
    return int(rng.choice(np.flatnonzero(mask)))


def run(seed=0, pathfinding=False, opponent=None):
    if isinstance(opponent, str) and opponent == 'scripted':
        from examples.scripted_bot_example import MyScriptedBot
        engine_opponent = MyScriptedBot('scripted')
    else:
        engine_opponent = opponent
    env = Season3Env(pathfinding=pathfinding, opponent=engine_opponent)
    rng = np.random.RandomState(seed)
    observation, info = env.reset(seed=seed)
    actors, action_types = set(), set()
    while True:
        assert env.observation_space.contains(observation)
        actors.add(info['actor'])
        observation, reward, terminated, truncated, info = env.step(sample_masked(observation, rng))
        action_types.add(info['decision']['action_type'])
        if terminated or truncated:
            break
    assert env.observation_space.contains(observation)
    env.close()
    return {'seed': seed, 'pathfinding': pathfinding, 'opponent': getattr(opponent, 'name', opponent),
            'terminated': terminated, 'truncated': truncated, 'decisions': info['decisions'],
            'score': info['score'], 'actors': sorted(actors), 'action_types': sorted(action_types),
            'last_reward': reward, 'terminal_rewards': info['terminal_rewards'],
            'interface_fingerprint': info['interface_fingerprint']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--pathfinding', action='store_true')
    parser.add_argument('--opponent', choices=['random', 'scripted'])
    args = parser.parse_args()
    print(json.dumps(run(args.seed, args.pathfinding, args.opponent), sort_keys=True))
