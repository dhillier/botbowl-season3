import pytest

from botbowl import (Action, ActionType, Skill, OutcomeType, BBDieResult, MoveAction,
                     SpecialAttack, Push, AfterBlock, KnockDown)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('innovator', [False, True])
def test_special_action_casualty_credit_requires_violent_innovator(innovator):
    game, (player, victim) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    player.extra_skills = [Skill.STAB] + ([Skill.VIOLENT_INNOVATOR] if innovator else [])
    victim.extra_skills = [Skill.REGENERATION]
    with only_fixed_rolls(game, d6=[5, 4, 6, 4, 4]):
        run_proc(game, SpecialAttack(game, player, victim, Skill.STAB))
    assert victim in game.get_reserves(victim.team)
    assert player.state.spp_earned == (2 if innovator else 0)


@pytest.mark.parametrize('skill,start,perform,dice,prone', [
    (Skill.STAB, ActionType.START_STAB, ActionType.STAB, [5, 4, 1, 2], True),
    (Skill.PROJECTILE_VOMIT, ActionType.START_PROJECTILE_VOMIT, ActionType.PROJECTILE_VOMIT, [2, 5, 4, 1, 2], True),
    (Skill.BREATHE_FIRE, ActionType.START_BREATHE_FIRE, ActionType.BREATHE_FIRE, [4], True),
    (Skill.BREATHE_FIRE, ActionType.START_BREATHE_FIRE, ActionType.BREATHE_FIRE, [6, 1, 1], True),
    (Skill.CHAINSAW, ActionType.START_CHAINSAW, ActionType.CHAINSAW, [2, 4, 2, 1, 2], True),
    (Skill.MONSTROUS_MOUTH, ActionType.START_CHOMP, ActionType.CHOMP, [3], False),
    (Skill.HYPNOTIC_GAZE, ActionType.START_HYPNOTIC_GAZE, ActionType.HYPNOTIC_GAZE, [3], False)])
def test_special_actions_can_be_declared_and_resolved(skill, start, perform, dice, prone):
    game, (player, victim) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    player.extra_skills = [skill]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=dice):
        game.step(Action(start, player=player))
        game.step(Action(perform, position=victim.position))
    assert player.state.used
    assert victim.state.up == (not prone)
    if skill == Skill.MONSTROUS_MOUTH:
        assert game.is_chomped(victim)
    if skill == Skill.HYPNOTIC_GAZE:
        assert victim.is_distracted()


def test_vomit_armour_is_unmodified_by_mighty_blow():
    game, (player, victim) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    player.extra_skills = [Skill.PROJECTILE_VOMIT, Skill.MIGHTY_BLOW, Skill.CLAWS]
    with only_fixed_rolls(game, d6=[2, 4, 4]):
        run_proc(game, SpecialAttack(game, player, victim, Skill.PROJECTILE_VOMIT))
    assert victim.state.up
    assert game.has_report_of_type(OutcomeType.ARMOR_NOT_BROKEN)


def test_chainsaw_kickback_knocks_down_with_three_armour_modifier():
    game, (player, victim) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    player.extra_skills = [Skill.CHAINSAW]
    with only_fixed_rolls(game, d6=[1, 4, 2, 1, 2]):
        run_proc(game, SpecialAttack(game, player, victim, Skill.CHAINSAW))
    assert player.state.stunned
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_chomp_prevents_moves_and_pushes_until_chomper_loses_marking():
    game, (chomper, victim, pusher) = season3_turn([(13, 5), (15, 5)], [(14, 5)], ball=(20, 12))
    # Fixture orders all friendly players before opponents.
    victim, pusher = pusher, victim
    chomper.extra_skills = [Skill.MONSTROUS_MOUTH]
    with only_fixed_rolls(game, d6=[3]):
        run_proc(game, SpecialAttack(game, chomper, victim, Skill.MONSTROUS_MOUTH))
    assert game.get_adjacent_move_actions(victim) == []
    with only_fixed_rolls(game):
        run_proc(game, Push(game, pusher, victim))
    assert victim.position == game.get_square(14, 5)
    with only_fixed_rolls(game):
        run_proc(game, KnockDown(game, chomper, armor_roll=False, injury_roll=False))
    assert victim.state.chomped_by is None
    assert game.get_adjacent_move_actions(victim)


def test_trickster_repositions_before_block_dice_and_keeps_declared_target():
    game, (attacker, defender) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.TRICKSTER]
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        assert game.get_available_actions()[0].skill == Skill.TRICKSTER
        game.step(Action(ActionType.MOVE, position=game.get_square(12, 5)))
        game.step(Action(ActionType.SELECT_PUSH))
    assert defender.position.x == 12
    assert {s.x for s in game.get_available_actions()[0].positions} == {11}


def test_hit_and_run_only_offers_unmarked_and_non_marking_squares():
    game, (attacker, defender) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.HIT_AND_RUN]
    defender.state.up = False
    run_proc(game, AfterBlock(game, attacker, defender, knocked_down=True))
    squares = game.get_available_actions()[0].positions
    assert {p.x for p in squares} == {12}
    with only_fixed_rolls(game):
        game.step(Action(ActionType.MOVE, position=game.get_square(12, 5)))
    assert attacker.state.moves == 0


def test_dump_off_does_not_spend_active_teams_pass_or_change_activation():
    game, (attacker, defender, receiver) = season3_turn([(13, 5)], [(14, 5), (16, 5)], ball=(14, 5))
    defender.extra_skills = [Skill.DUMP_OFF]
    with only_fixed_rolls(game, d6=[6, 3], block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.USE_SKILL))
        assert all(a.action_type in (ActionType.PASS, ActionType.SELECT_NONE)
                   for a in game.get_available_actions())
        game.step(Action(ActionType.PASS, position=receiver.position))
    assert game.current_turn().pass_available
    assert game.get_active_player() == attacker
    assert game.get_ball_carrier() == receiver
