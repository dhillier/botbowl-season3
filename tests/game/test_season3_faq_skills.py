"""Regressions for the official May 2026 Third Season FAQ."""
import pytest

from botbowl import (Action, ActionType, BBDieResult, Skill, Square, OutcomeType,
                     KnockDown, Foul, Block, Trickster, Season3Escape, Season3PitchInvasion, Move)
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.game.test_season3_multiple_block import multi_game, declare
from tests.util import only_fixed_rolls


def test_steady_footing_can_use_team_reroll_and_prevent_turnover():
    game, (player,) = season3_turn([(10, 5)], ball=(20, 12), rerolls=1)
    player.extra_skills = [Skill.STEADY_FOOTING]
    with only_fixed_rolls(game, d6=[2, 6]):
        run_proc(game, KnockDown(game, player, turnover=True))
        game.step(Action(ActionType.USE_REROLL))
    assert player.state.up and player.team.state.rerolls == 0
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_trickster_removes_chomp_even_when_relocated_adjacent_to_chomper():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.MONSTROUS_MOUTH]
    defender.extra_skills = [Skill.TRICKSTER]
    defender.state.chomped_by = attacker.player_id
    game.state.chomped_players.append(defender)
    with only_fixed_rolls(game):
        run_proc(game, Trickster(game, attacker, defender))
        game.step(Action(ActionType.MOVE, position=Square(11, 6)))
    assert defender.position == Square(11, 6)
    assert not game.is_chomped(defender)


def test_brawler_only_one_pool_per_multiple_block_activation():
    game, (attacker, first, second) = multi_game([Skill.BRAWLER, Skill.BLOCK])
    with only_fixed_rolls(game, d6=[1, 1],
                          block_dice=[BBDieResult.BOTH_DOWN, BBDieResult.PUSH, BBDieResult.BOTH_DOWN]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.USE_SKILL))
        game.step(Action(ActionType.SELECT_PUSH))
        assert not any(a.skill == Skill.BRAWLER for a in game.get_available_actions())
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(12, 3)))
    assert attacker.state.up and not second.state.up


def test_ball_chain_crowd_stunned_result_returns_to_reserves():
    game, (player,) = season3_turn([(1, 5)], ball=(20, 12))
    player.extra_skills = [Skill.BALL_AND_CHAIN, Skill.NO_BALL]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[3, 1, 1]):
        game.step(Action(ActionType.START_BALL_AND_CHAIN, player=player))
        game.step(Action(ActionType.BALL_AND_CHAIN, position=Square(0, 5)))
    assert player in game.get_reserves(player.team)
    assert not player.state.knocked_out
    assert game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('assist', [False, True])
def test_sneaky_git_can_choose_foul_assists_before_armour_roll(assist):
    game, (fouler, helper, victim) = season3_turn([(10, 5), (12, 5)], [(11, 5)], ball=(20, 12))
    fouler.extra_skills = [Skill.SNEAKY_GIT]
    victim.state.up = False
    with only_fixed_rolls(game, d6=[4, 4] + ([1, 2] if assist else [])):
        run_proc(game, Foul(game, fouler, victim))
        assert not game.has_report_of_type(OutcomeType.ARMOR_BROKEN)
        game.step(Action(ActionType.SELECT_PLAYER, player=helper) if assist else Action(ActionType.SELECT_NONE))
        if assist:
            game.step(Action(ActionType.DONT_ARGUE_CALL))
    assert fouler.state.ejected == assist
    assert victim.state.stunned == assist


@pytest.mark.parametrize('skill', [Skill.DIRTY_PLAYER, Skill.LONE_FOULER])
def test_sneaky_git_can_decline_skill_that_would_risk_ejection(skill):
    game, (fouler, victim) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    fouler.extra_skills = [Skill.SNEAKY_GIT, skill]
    victim.state.up = False
    with only_fixed_rolls(game, d6=[4, 4]):
        run_proc(game, Foul(game, fouler, victim))
        assert game.get_available_actions()[0].skill == skill
        game.step(Action(ActionType.DONT_USE_SKILL))
    assert not fouler.state.ejected and not victim.state.stunned


def test_failed_dodge_does_not_allow_shadowing():
    game, (player, marker) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    marker.extra_skills = [Skill.SHADOWING]
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        run_proc(game, Season3Escape(game, player, Square(11, 5)))
    assert not player.state.up
    assert marker.state.shadowing_uses == 0


def test_foul_appearance_failure_precedes_trickster_and_dump_off():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(11, 5))
    defender.extra_skills = [Skill.FOUL_APPEARANCE, Skill.TRICKSTER, Skill.DUMP_OFF]
    game.state.active_player = attacker
    with only_fixed_rolls(game, d6=[1]):
        run_proc(game, Block(game, attacker, defender))
    assert attacker.state.used
    assert defender.position == Square(11, 5) and game.has_ball(defender)


def test_pitch_invasion_causes_ball_chain_injury():
    game, (player,) = season3_turn([(10, 5)], ball=(20, 12))
    player.extra_skills = [Skill.BALL_AND_CHAIN]
    for team in game.state.teams:
        team.state.fan_factor = 0
    with only_fixed_rolls(game, d6=[1, 6, 1, 1], d3=[1]):
        run_proc(game, Season3PitchInvasion(game))
    assert player in game.get_knocked_out(player.team)


def test_multiple_block_reverts_and_replays_both_effects():
    game, (attacker, first, second) = multi_game()
    game.enable_forward_model()
    checkpoint = game.get_step()
    before = game.state.to_json(ignore_clocks=True)
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH, BBDieResult.PUSH]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 3)))
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(checkpoint)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after


def test_tentacles_prevents_rush_before_any_movement_roll():
    game, (player, holder) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    holder.extra_skills = [Skill.TENTACLES]
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[6]):
        run_proc(game, Move(game, player, Square(11, 5), gfi=True, dodge=True))
        game.step(Action(ActionType.USE_SKILL, player=holder))
    assert player.position == Square(10, 5) and player.state.used
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_GFI)
    assert not game.has_report_of_type(OutcomeType.FAILED_GFI)


def test_tackle_is_checked_at_origin_after_dodger_has_moved():
    game, (player, marker) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    player.extra_skills = [Skill.DODGE]
    marker.extra_skills = [Skill.TACKLE]
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        run_proc(game, Season3Escape(game, player, Square(11, 5)))
    assert not player.state.up and not player.has_used_skill(Skill.DODGE)


def test_steady_footing_after_rush_still_requires_dodge_before_pickup():
    game, (player, marker) = season3_turn([(10, 5)], [(9, 5)], ball=(11, 5))
    player.extra_skills = [Skill.STEADY_FOOTING]
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[1, 6, 3, 3]):
        run_proc(game, Move(game, player, Square(11, 5), gfi=True, dodge=True))
    reports = [r.outcome_type for r in game.state.reports]
    assert reports.index(OutcomeType.SUCCESSFUL_DODGE) < reports.index(OutcomeType.SUCCESSFUL_PICKUP)
    assert game.has_ball(player) and player.state.up
