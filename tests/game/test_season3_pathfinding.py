"""Actual Season 3 re-roll budgets in both pathfinders and action previews."""
from itertools import combinations
from math import prod

import pytest

from tests.util import *
from tests.game.test_season3 import season3_turn
from botbowl.core.pathfinding import python_pathfinding


@pytest.fixture(params=['python', 'cython'])
def pf(request):
    return python_pathfinding if request.param == 'python' else pytest.importorskip(
        'botbowl.core.pathfinding.cython_pathfinding')


def successful_tests(targets, budget):
    """Sum disjoint outcomes with at most budget failed first attempts.

    Every test must ultimately succeed; each failed first attempt gets exactly
    one second attempt. Extra resources must never buy a third attempt.
    """
    probabilities = [(7 - target) / 6 for target in targets]
    return prod(probabilities) * sum(
        prod(1 - probabilities[i] for i in failed)
        for count in range(min(budget, len(targets)) + 1)
        for failed in combinations(range(len(targets)), count))


@pytest.mark.parametrize('budget', [0, 1, 2, 3, 8])
@pytest.mark.parametrize('allowed', [False, True])
def test_two_rushes_share_actual_remaining_budget(pf, budget, allowed):
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12), rerolls=budget)
    player.state.moves = player.get_ma()
    player.team.state.reroll_used = True  # A previous test does not cap S3.
    before = game.state.to_json(ignore_clocks=True)
    path = pf.get_safest_path(game, player, Square(7, 5), allow_team_reroll=allowed)
    assert path.prob == pytest.approx(successful_tests([2, 2], budget if allowed else 0))
    assert game.state.to_json(ignore_clocks=True) == before


@pytest.mark.parametrize('restriction', ['opponent', 'quick_snap', 'no_turn'])
def test_planning_cannot_spend_an_ineligible_teams_rerolls(pf, restriction):
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12), rerolls=5)
    player.state.moves = player.get_ma()
    if restriction == 'opponent':
        game.state.current_team = game.get_opp_team(player.team)
    elif restriction == 'quick_snap':
        game.current_turn().quick_snap = True
    else:
        game.state.stack.items.clear()
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(7, 5))
    assert path.prob == pytest.approx((5 / 6) ** 2)


@pytest.mark.parametrize('budget', [0, 1, 2, 3, 4, 8])
@pytest.mark.parametrize('secure', [False, True])
def test_rush_jump_and_pickup_share_one_budget(pf, budget, secure):
    game, (player, *wall) = season3_turn(
        [(5, 5), (6, 4), (6, 5), (6, 6)], ball=(7, 5), rerolls=budget)
    for body in wall:
        body.state.up = False
    player.state.moves = player.get_ma()
    path = pf.Pathfinder(game, player, trr=True, secure_ball=secure).get_path(Square(7, 5))
    targets = [2, 2, 3, 2 if secure else 3]
    assert path.steps == (Square(7, 5),)
    assert list(path.rolls[0]) == targets
    assert path.prob == pytest.approx(successful_tests(targets, budget))


@pytest.mark.parametrize('budget', [0, 1, 2, 4])
def test_skill_rerolls_do_not_allow_team_reroll_of_same_test(pf, budget):
    game, (player, _) = season3_turn([(5, 5)], [(4, 5)], ball=(6, 5), rerolls=budget)
    player.state.moves = player.get_ma()
    player.extra_skills = [Skill.DODGE, Skill.SURE_HANDS]
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(6, 5))
    # Rush has no skill re-roll; Dodge and pickup have distinct skill re-rolls.
    # Even eight team re-rolls could not rescue a failed skill's second roll.
    rush = 35 / 36 if budget else 5 / 6
    assert path.prob == pytest.approx(rush * (8 / 9) ** 2)


@pytest.mark.parametrize('budget', [0, 1, 2])
def test_used_dodge_is_unavailable_but_team_rerolls_remain(pf, budget):
    game, (player, _) = season3_turn([(5, 5)], [(4, 5)], ball=(20, 12), rerolls=budget)
    player.state.moves = player.get_ma()
    player.extra_skills = [Skill.DODGE]
    player.state.used_skills.add(Skill.DODGE)
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(6, 5))
    assert path.prob == pytest.approx(successful_tests([2, 3], budget))


@pytest.mark.parametrize('budget', [0, 1, 2])
def test_dodge_skill_is_one_shared_allowance_across_two_dodges(pf, budget):
    # At the sideline with the diagonal square occupied, the only two-step
    # route has two marked departures/landings. No unmarked detour fits.
    game, (player, _) = season3_turn([(1, 1)], [(2, 2)], ball=(20, 12), rerolls=budget)
    player.extra_skills = [Skill.DODGE]
    player.state.moves = player.get_ma() - 2
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(3, 1))
    assert path.steps == (Square(2, 1), Square(3, 1))
    assert path.prob == pytest.approx(successful_tests([4, 4], budget + 1))


def test_drive_bonus_rerolls_are_included_once_and_decline_when_spent(pf):
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12), rerolls=1)
    player.team.state.rerolls += 1
    player.team.state.drive_rerolls = 1
    player.state.moves = player.get_ma()
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(7, 5))
    assert path.prob == pytest.approx(successful_tests([2, 2], 2))
    player.team.state.use_reroll()
    assert player.team.state.drive_rerolls == 0
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(7, 5))
    assert path.prob == pytest.approx(successful_tests([2, 2], 1))


def test_legacy_opt_in_keeps_hypothetical_single_reroll(pf):
    game, (player,) = get_custom_game_turn([(5, 5)], ball_position=(20, 12))
    player.state.moves = player.get_ma()
    # The public legacy API has always treated trr=True as hypothetical,
    # independently of the game's actual pool/turn ownership.
    player.team.state.rerolls = 5
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(7, 5))
    assert path.prob == pytest.approx(successful_tests([2, 2], 1))


def test_path_preview_and_execution_allow_four_distinct_rerolls():
    game, (player, *wall) = season3_turn(
        [(5, 5), (6, 4), (6, 5), (6, 6)], ball=(7, 5), rerolls=4)
    for body in wall:
        body.state.up = False
    player.state.moves = player.get_ma()
    game.config.pathfinding_enabled = True
    game.set_available_actions()
    game.step(Action(ActionType.START_SECURE_BALL, player=player))
    choice = next(a for a in game.get_available_actions() if a.action_type == ActionType.MOVE)
    path = choice.paths[choice.positions.index(Square(7, 5))]
    assert path.prob == pytest.approx(successful_tests([2, 2, 3, 2], 4))
    data = choice.to_json()
    assert data['paths'][choice.positions.index(Square(7, 5))]['prob'] == path.prob
    with only_fixed_rolls(game, d6=[1, 2, 1, 2, 2, 3, 1, 2]):
        game.step(Action(ActionType.MOVE, position=Square(7, 5)))
        for _ in range(4):
            assert isinstance(game.get_procedure(), Reroll)
            game.step(Action(ActionType.USE_REROLL))
    assert game.get_ball_carrier() == player
    assert player.team.state.rerolls == 0
    assert player.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_failed_second_attempt_cannot_spend_another_budget_unit():
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12), rerolls=4)
    player.state.moves = player.get_ma()
    with only_fixed_rolls(game, d6=[1, 1, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        game.step(Action(ActionType.USE_REROLL))
    assert player.team.state.rerolls == 3
    assert not player.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_python_and_compiled_paths_agree_with_season3_budget():
    cython = pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, (player, _, _) = season3_turn([(5, 5)], [(4, 5), (8, 6)], ball=(9, 5), rerolls=3)
    player.extra_skills = [Skill.DODGE]
    player.state.moves = 2
    python_paths = {p.get_last_step(): p for p in python_pathfinding.Pathfinder(game, player, trr=True).get_paths()}
    compiled_paths = {p.get_last_step(): p for p in cython.Pathfinder(game, player, trr=True).get_paths()}
    assert python_paths.keys() == compiled_paths.keys()
    for square, path in python_paths.items():
        assert path.prob == pytest.approx(compiled_paths[square].prob)
        assert len(path.steps) == len(compiled_paths[square].steps)
