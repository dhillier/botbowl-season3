"""The extracted framework must support agents on either coach side."""
import numpy as np
import pytest

from botbowl.ai.season3_env import Season3Env
from examples.season3_rl import sample_masked


@pytest.mark.parametrize('learner_side', [0, 1])
@pytest.mark.parametrize('pathfinding', [False, True])
def test_supplied_opponent_returns_only_learner_decisions(learner_side, pathfinding):
    env = Season3Env(opponent='random', learner_side=learner_side,
                     pathfinding=pathfinding)
    observation, info = env.reset(seed=73)
    rng = np.random.RandomState(19)
    try:
        for _ in range(64):
            assert info['actor'] == learner_side
            assert env.observation_space.contains(observation)
            assert observation['action_mask'].any()
            observation, _, terminated, truncated, info = env.step(
                sample_masked(observation, rng))
            assert not truncated
            if terminated:
                break
    finally:
        env.close()


@pytest.mark.parametrize('side', [-1, 2, True, 0.0, 'away'])
def test_invalid_learner_side_is_rejected(side):
    with pytest.raises(ValueError, match='learner_side'):
        Season3Env(opponent='random', learner_side=side)


def test_away_learner_requires_an_opponent():
    with pytest.raises(ValueError, match='supplied opponent'):
        Season3Env(learner_side=1)
