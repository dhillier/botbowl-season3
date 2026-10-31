import pytest

from botbowl import (Action, ActionType, Skill, Square, OutcomeType, Kickoff, Scatter,
                     OnTheBallReaction, D6)
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc, kickoff_game
from tests.util import only_fixed_rolls


def test_kicker_is_selected_before_placing_ball_and_excludes_wings_and_scrimmage():
    game, (kicker, other, wing, line, receiver) = kickoff_game(
        [(20, 5), (21, 5), (20, 1), (14, 5)], [(10, 5)])
    kicker.extra_skills = [Skill.KICK]
    with only_fixed_rolls(game):
        run_proc(game, Kickoff(game))
        assert set(game.get_available_actions()[0].players) == {kicker, other}
        game.step(Action(ActionType.SELECT_PLAYER, player=kicker))
    assert game.get_available_actions()[0].action_type == ActionType.PLACE_BALL
    reports = [r for r in game.state.reports if r.outcome_type == OutcomeType.KICKER_NOMINATED]
    assert reports[-1].player == kicker


@pytest.mark.parametrize('use_kick,distance', [(True, 3), (False, 4)])
def test_kick_can_choose_d3_or_normal_d6_deviation(use_kick, distance):
    game, (kicker, receiver) = kickoff_game()
    kicker.extra_skills = [Skill.KICK]
    ball = game.get_ball()
    ball.move_to(Square(6, 8))
    with only_fixed_rolls(game, d8=[5], d3=[3] if use_kick else [], d6=[] if use_kick else [4]):
        run_proc(game, Scatter(game, ball, kick=True, kicker=kicker))
        game.step(Action(ActionType.USE_SKILL if use_kick else ActionType.DONT_USE_SKILL))
    assert ball.position == Square(6 + distance, 8)
    assert not ball.is_carried


def test_punt_ground_result_is_not_a_turnover_and_does_not_spend_pass():
    game, (player,) = season3_turn([(13, 5)], ball=(13, 5))
    player.extra_skills = [Skill.PUNT]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[3, 3], d8=[7]):
        game.step(Action(ActionType.START_PUNT, player=player))
        game.step(Action(ActionType.MOVE, position=Square(14, 5)))
        game.step(Action(ActionType.PUNT, position=Square(15, 5)))
    assert game.get_ball_position() == Square(17, 6)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.current_turn().pass_available
    assert not game.current_turn().punt_available
    assert player.state.used


@pytest.mark.parametrize('opponent', [False, True])
def test_punt_catch_turnover_depends_on_final_possession(opponent):
    game, players = season3_turn([(13, 5)] + ([] if opponent else [(16, 5)]),
                                [(16, 5)] if opponent else None, ball=(13, 5))
    player, catcher = players
    player.extra_skills = [Skill.PUNT]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[3, 3, 3]):
        game.step(Action(ActionType.START_PUNT, player=player))
        game.step(Action(ActionType.PUNT, position=Square(14, 5)))
    assert game.get_ball_carrier() == catcher
    assert game.has_report_of_type(OutcomeType.TURNOVER) == opponent


def test_kick_rerolls_punt_direction_before_distance_and_can_reroll_both():
    game, (player,) = season3_turn([(13, 5)], ball=(13, 5))
    player.extra_skills = [Skill.PUNT, Skill.KICK]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[1, 3, 1, 3], d8=[7]):
        game.step(Action(ActionType.START_PUNT, player=player))
        game.step(Action(ActionType.PUNT, position=Square(14, 5)))
        assert D6.FixedRolls == [3, 1, 3]
        game.step(Action(ActionType.USE_SKILL))
        assert D6.FixedRolls == [3]
        game.step(Action(ActionType.USE_SKILL))
    assert game.get_ball_position() == Square(16, 6)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_on_the_ball_precedes_pass_test_and_preserves_used_and_movement_state():
    game, (passer, catcher, reactor) = season3_turn([(5, 5), (8, 5)], [(16, 10)], ball=(5, 5))
    reactor.extra_skills = [Skill.ON_THE_BALL]
    reactor.state.used = True
    reactor.state.moves = 6
    with only_fixed_rolls(game, d6=[4, 3]):
        game.step(Action(ActionType.START_PASS, player=passer))
        game.step(Action(ActionType.PASS, position=catcher.position))
        assert D6.FixedRolls == [4, 3]
        game.step(Action(ActionType.SELECT_PLAYER, player=reactor))
        for x in (15, 14, 13):
            game.step(Action(ActionType.MOVE, position=Square(x, 10)))
    assert reactor.position == Square(13, 10)
    assert reactor.state.used and reactor.state.moves == 6
    assert game.get_ball_carrier() == catcher
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_failed_on_the_ball_move_stops_other_reactions_but_resumes_pass():
    game, (passer, catcher, marker, first, second) = season3_turn(
        [(5, 5), (8, 5), (16, 11)], [(16, 10), (19, 10)], ball=(5, 5))
    first.extra_skills = second.extra_skills = [Skill.ON_THE_BALL]
    with only_fixed_rolls(game, d6=[1, 1, 1, 4, 3]):
        game.step(Action(ActionType.START_PASS, player=passer))
        game.step(Action(ActionType.PASS, position=catcher.position))
        game.step(Action(ActionType.SELECT_PLAYER, player=first))
        game.step(Action(ActionType.MOVE, position=Square(16, 9)))
    assert not first.state.up
    assert second.position == Square(19, 10)
    assert game.get_ball_carrier() == catcher
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_kickoff_reaction_stays_in_receiving_half_and_does_not_pick_up_airborne_ball():
    game, (kicker, receiver) = kickoff_game([(20, 5)], [(10, 8)])
    receiver.extra_skills = [Skill.ON_THE_BALL]
    ball = game.get_ball()
    ball.move_to(Square(10, 10))
    ball.is_carried = False
    with only_fixed_rolls(game):
        run_proc(game, OnTheBallReaction(game, receiver.team, ball=ball))
        game.step(Action(ActionType.SELECT_PLAYER, player=receiver))
        for y in (9, 10):
            choices = game.get_available_actions()
            assert all(game.is_team_side(p, receiver.team) for a in choices for p in a.positions)
            game.step(Action(ActionType.MOVE, position=Square(10, y)))
        game.step(Action(ActionType.END_PLAYER_TURN))
    assert not ball.is_carried
    assert not receiver.state.used


def test_touchback_prevents_kickoff_reaction():
    game, (kicker, receiver) = kickoff_game()
    receiver.extra_skills = [Skill.ON_THE_BALL]
    game.get_ball().move_to(Square(20, 10))
    with only_fixed_rolls(game):
        run_proc(game, OnTheBallReaction(game, receiver.team, ball=game.get_ball()))
    assert all(a.skill != Skill.ON_THE_BALL for a in game.get_available_actions())
