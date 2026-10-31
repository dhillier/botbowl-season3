"""Existing scripted clients must return legal actions for new skill decisions."""
import pytest

from botbowl import (Action, ActionType, Skill, Square, Season3Escape, OnTheBallReaction,
                     KnockDown, PlagueRidden, MultipleBlock, Block, BBDieResult)
from examples.scripted_bot_example import MyScriptedBot
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


def coach_for(game, team):
    coach = MyScriptedBot('skill-test')
    coach.new_game(game, team)
    return coach


@pytest.mark.parametrize('kind', ['tentacles', 'diving-tackle', 'on-ball', 'safe-hands', 'plague', 'multiple-block'])
def test_scripted_coach_handles_new_decisions(kind):
    game, (player, other, defender) = season3_turn([(10, 5), (11, 6)], [(9, 5)], ball=(10, 5))
    coach = coach_for(game, player.team)
    with only_fixed_rolls(game, d6=[6] if kind == 'diving-tackle' else []):
        if kind in ('tentacles', 'diving-tackle'):
            defender.extra_skills = [Skill.TENTACLES if kind == 'tentacles' else Skill.DIVING_TACKLE]
            proc = Season3Escape(game, player, Square(11, 5))
        elif kind == 'on-ball':
            player.extra_skills = [Skill.ON_THE_BALL]
            proc = OnTheBallReaction(game, player.team)
        elif kind == 'safe-hands':
            player.extra_skills = [Skill.SAFE_PAIR_OF_HANDS]
            proc = KnockDown(game, player)
        elif kind == 'plague':
            proc = PlagueRidden(game, player)
        else:
            proc = MultipleBlock(game, defender)
        run_proc(game, proc)
    action = coach.act(game)
    assert game._is_action_allowed(action)


def test_scripted_coach_rerolls_one_pro_die_instead_of_trying_pro_again():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.PRO]
    game.state.active_player = attacker
    coach = coach_for(game, attacker.team)
    with only_fixed_rolls(game, d6=[3], block_dice=[BBDieResult.BOTH_DOWN]):
        run_proc(game, Block(game, attacker, defender))
        game.step(Action(ActionType.USE_SKILL))
    action = coach.act(game)
    assert action.action_type == ActionType.SELECT_BOTH_DOWN
    assert game._is_action_allowed(action)


def test_scripted_coach_handles_brawler_decision():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.BRAWLER]
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN]):
        run_proc(game, Block(game, attacker, defender))
    action = coach_for(game, attacker.team).act(game)
    assert action.action_type == ActionType.USE_SKILL
    assert game._is_action_allowed(action)


def test_scripted_fanatic_uses_its_activation_and_direction_then_stops_before_rush():
    game, (fanatic, opponent) = season3_turn([(10, 5)], [(13, 5)], ball=(20, 12))
    fanatic.extra_skills = [Skill.BALL_AND_CHAIN, Skill.NO_BALL]
    game.set_available_actions()
    coach = coach_for(game, fanatic.team)
    action = coach.act(game)
    assert action.action_type == ActionType.START_BALL_AND_CHAIN and action.player == fanatic
    game.step(action)
    action = coach.act(game)
    assert action.action_type == ActionType.BALL_AND_CHAIN and game._is_action_allowed(action)
    with only_fixed_rolls(game, d6=[3]):
        game.step(action)
    assert fanatic.state.moves == 1
    fanatic.state.moves = fanatic.get_ma()
    game.set_available_actions()
    assert coach.act(game).action_type == ActionType.END_PLAYER_TURN
