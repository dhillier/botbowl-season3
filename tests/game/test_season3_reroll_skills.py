import pytest

from botbowl import (Action, ActionType, Skill, BBDieResult, Block, OutcomeType, Reroll,
                     DiceRoll, D6, Pro, GFI)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('skill,result', [(Skill.BRAWLER, BBDieResult.BOTH_DOWN),
                                         (Skill.HATRED, BBDieResult.ATTACKER_DOWN)])
def test_block_skill_rerolls_one_die_and_excludes_other_sources(skill, result):
    game, (attacker, defender) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12), rerolls=1)
    attacker.extra_st = 1
    attacker.extra_skills = [skill]
    attacker.role.skill_parameters = {Skill.HATRED: 'Human'}
    game.state.active_player = attacker
    with only_fixed_rolls(game, block_dice=[result, BBDieResult.PUSH, BBDieResult.DEFENDER_DOWN]):
        proc = Block(game, attacker, defender)
        run_proc(game, proc)
        assert game.get_available_actions()[0].skill == skill
        game.step(Action(ActionType.USE_SKILL))
    assert [d.get_value() for d in proc.roll.dice] == [BBDieResult.DEFENDER_DOWN, BBDieResult.PUSH]
    assert ActionType.USE_REROLL not in [a.action_type for a in game.get_available_actions()]
    assert attacker.team.state.rerolls == 1


def test_pro_three_plus_rerolls_selected_die_in_block_pool():
    game, (attacker, defender) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    attacker.extra_st = 1
    attacker.extra_skills = [Skill.PRO]
    game.state.active_player = attacker
    with only_fixed_rolls(game, d6=[3], block_dice=[BBDieResult.BOTH_DOWN, BBDieResult.PUSH,
                                                 BBDieResult.DEFENDER_DOWN]):
        proc = Block(game, attacker, defender)
        run_proc(game, proc)
        game.step(Action(ActionType.USE_SKILL))
        assert game.get_available_actions()[0].skill == Skill.PRO
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
    assert [d.get_value() for d in proc.roll.dice] == [BBDieResult.DEFENDER_DOWN, BBDieResult.PUSH]


def test_pro_failure_does_not_offer_team_reroll_for_original_test():
    game, (player,) = season3_turn([(13, 5)], ball=(20, 12), rerolls=1)
    player.extra_skills = [Skill.PRO]
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[1, 2, 1, 1]):
        run_proc(game, GFI(game, player, game.get_square(14, 5)))
        game.step(Action(ActionType.USE_SKILL))
    assert not player.state.up
    assert player.team.state.rerolls == 1


def test_pro_is_unavailable_outside_own_activation():
    game, (player, opponent) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    opponent.extra_skills = [Skill.PRO]
    game.state.active_player = player
    proc = Reroll(game, opponent, object())
    proc.start()
    assert not proc.can_use_pro
