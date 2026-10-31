import pytest

from botbowl import Action, ActionType, Skill, Square, OutcomeType, KnockDown, BBDieResult
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


def fanatic_game(friendly=False):
    game, players = season3_turn([(5, 5), (6, 5)] if friendly else [(5, 5)],
                                None if friendly else [(6, 5)], ball=(20, 12))
    players[0].extra_skills = [Skill.BALL_AND_CHAIN, Skill.NO_BALL]
    game.set_available_actions()
    return game, players


def test_ball_and_chain_is_the_only_activation_declaration():
    game, (player, victim) = fanatic_game()
    actions = [a.action_type for a in game.get_available_actions() if player in a.players]
    assert set(actions) == {ActionType.START_BALL_AND_CHAIN, ActionType.FOREGO_ACTIVATION}


def test_directional_move_ignores_marking_tentacles_shadowing_and_chomp():
    game, (player, marker) = fanatic_game()
    marker.extra_skills = [Skill.TENTACLES, Skill.SHADOWING, Skill.MONSTROUS_MOUTH]
    player.state.chomped_by = marker.player_id
    game.state.chomped_players.append(player)
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(4, 5)))
    assert player.position == Square(4, 5)
    assert player.state.moves == 1
    assert player.state.up and not player.state.used


def test_ball_and_chain_bounces_ball_without_pickup_or_turnover():
    game, (player, victim) = fanatic_game()
    game.get_ball().move_to(Square(4, 5))
    game.get_ball().is_carried = False
    with only_fixed_rolls(game, d6=[3], d8=[7]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(4, 5)))
    assert game.get_ball_position() == Square(4, 6)
    assert not game.has_report_of_type(OutcomeType.FAILED_PICKUP)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('friendly', [False, True])
def test_automatic_block_ignores_foul_appearance_and_follows_up(friendly):
    game, (player, victim) = fanatic_game(friendly)
    victim.extra_skills = [Skill.FOUL_APPEARANCE, Skill.FEND]
    with only_fixed_rolls(game, d6=[3], block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(6, 5)))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(7, 5)))
    assert player.position == Square(6, 5)
    assert victim.position == Square(7, 5)
    assert not player.state.used


def test_prone_player_is_pushed_then_armour_rolled():
    game, (player, victim) = fanatic_game()
    victim.state.up = False
    with only_fixed_rolls(game, d6=[3, 5, 4, 1, 2]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(6, 5)))
        game.step(Action(ActionType.PUSH, position=Square(7, 5)))
    assert player.position == Square(6, 5)
    assert victim.position == Square(7, 5)
    assert victim.state.stunned


def test_failed_rush_resolves_block_and_followup_before_falling():
    game, (player, victim) = fanatic_game()
    with only_fixed_rolls(game, d6=[3, 1, 1, 1], block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        player.state.moves = player.get_ma()
        game.set_available_actions()
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(6, 5)))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(7, 5)))
    assert victim.position == Square(7, 5)
    assert player in game.get_knocked_out(player.team)
    assert game.has_report_of_type(OutcomeType.FOLLOW_UP)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not any(r.player == player and r.outcome_type in (OutcomeType.ARMOR_BROKEN, OutcomeType.ARMOR_NOT_BROKEN)
                   for r in game.state.reports)


def test_friendly_knockdown_causes_turnover_after_movement_resolves():
    game, (player, victim) = fanatic_game(friendly=True)
    with only_fixed_rolls(game, d6=[3, 1, 1], block_dice=[BBDieResult.DEFENDER_DOWN]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(6, 5)))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(7, 5)))
    assert player.position == Square(6, 5)
    assert not victim.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_ball_and_chain_placed_prone_still_suffers_injury_without_armour():
    game, (player, victim) = fanatic_game()
    with only_fixed_rolls(game, d6=[1, 1]):
        run_proc(game, KnockDown(game, player, armor_roll=False, injury_roll=False))
    assert player in game.get_knocked_out(player.team)
