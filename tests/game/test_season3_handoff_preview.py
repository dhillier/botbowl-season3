"""Movement and catch share rerolls; legacy movement-only path probabilities stay intact."""
from copy import deepcopy
import pickle

import numpy as np
import pytest

from botbowl import Action, ActionType, OutcomeType, Skill, WeatherType
from botbowl.ai.season3_env import Season3Adapter
from botbowl.core.pathfinding import python_pathfinding
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_pathfinding import successful_tests
from tests.util import only_fixed_rolls


@pytest.fixture(params=['python', 'cython'])
def pf(request):
    return python_pathfinding if request.param == 'python' else pytest.importorskip(
        'botbowl.core.pathfinding.cython_pathfinding')


@pytest.mark.parametrize('budget', [0, 1, 2, 4])
@pytest.mark.parametrize('catch', ['none', 'usable', 'spent'])
@pytest.mark.parametrize('rain', [False, True])
def test_handoff_completion_shares_budget_and_receiver_skill(pf, budget, catch, rain):
    game, (carrier, receiver) = season3_turn([(5, 5), (8, 5)], ball=(5, 5), rerolls=budget)
    carrier.state.moves = carrier.get_ma() - 1  # One Rush on the way to the receiver.
    if catch != 'none':
        receiver.extra_skills = [Skill.CATCH]
    if catch == 'spent':
        receiver.state.used_skills.add(Skill.CATCH)
    if rain:
        game.state.weather = WeatherType.POURING_RAIN
    before = deepcopy(game.state.to_json(ignore_clocks=True))
    rng = game.rng.get_state()
    path = pf.Pathfinder(game, carrier, trr=True, can_handoff=True).get_path(receiver.position)
    catch_target = 4 if rain else 3
    assert path.handoff_roll == catch_target
    assert path.prob == pytest.approx(successful_tests([2], budget))
    if catch == 'usable':
        p = (7 - catch_target) / 6
        expected = successful_tests([2], budget) * (p + (1 - p) * p)
    else:
        expected = successful_tests([2, catch_target], budget)
    assert path.handoff_prob == pytest.approx(expected)
    assert game.state.to_json(ignore_clocks=True) == before
    np.testing.assert_equal(game.rng.get_state(), rng)
    restored = pickle.loads(pickle.dumps(path))
    assert restored == path
    assert restored.handoff_prob == path.handoff_prob


@pytest.mark.parametrize('pathfinding', [False, True])
@pytest.mark.parametrize('markers', [0, 1, 2, 3])
@pytest.mark.parametrize('budget', [0, 1])
def test_adapter_handoff_preview_includes_marked_receiver_catch(pathfinding, markers, budget):
    opponents = [(14, 7), (13, 8), (14, 9)][:markers]
    game, (carrier, receiver, *_) = season3_turn(
        [(15, 8), (14, 8)], opponents, ball=(15, 8), rerolls=budget)
    game.config.pathfinding_enabled = pathfinding
    game.set_available_actions()
    game.step(Action(ActionType.START_HANDOFF, player=carrier))
    adapter = Season3Adapter(game)
    before = deepcopy(game.state.to_json(ignore_clocks=True))
    rng = game.rng.get_state()
    obs = adapter.observe()
    index = adapter.codec().encode(Action(ActionType.HANDOFF, position=receiver.position))
    p = (4 - markers) / 6
    expected = p + (1 - p) * p if budget else p
    assert obs['action_mask'][index]
    assert obs['action_features'][index, 0] == pytest.approx(expected)
    assert obs['action_features'][index, 2] == 1
    assert game.state.to_json(ignore_clocks=True) == before
    np.testing.assert_equal(game.rng.get_state(), rng)


def test_team_reroll_spent_on_movement_is_unavailable_for_catch():
    game, (carrier, receiver) = season3_turn([(5, 5), (8, 5)], ball=(5, 5), rerolls=1)
    carrier.state.moves = carrier.get_ma() - 1
    game.config.pathfinding_enabled = True
    game.set_available_actions()
    game.step(Action(ActionType.START_HANDOFF, player=carrier))
    adapter = Season3Adapter(game)
    index = adapter.codec().encode(Action(ActionType.HANDOFF, position=receiver.position))
    assert adapter.observe()['action_features'][index, 0] == pytest.approx(5 / 6)
    # Fail the Rush, spend the only team reroll, then fail the catch. The ball
    # bounces to an empty square, ending possession without a second reroll.
    with only_fixed_rolls(game, d6=[1, 2, 1], d8=[2]):
        game.step(Action(ActionType.HANDOFF, position=receiver.position))
        game.step(Action(ActionType.USE_REROLL))
    assert carrier.team.state.rerolls == 0
    assert game.get_ball_carrier() is None
    assert game.has_report_of_type(OutcomeType.FAILED_CATCH)
