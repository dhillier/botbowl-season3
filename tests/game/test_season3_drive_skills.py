import pytest

from botbowl import (Action, ActionType, Skill, OutcomeType, PickMeUp, EndDrive, KnockDown,
                     GFI, Kickoff, WeatherType)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


def test_pick_me_up_snapshots_helpers_and_rolls_each_target_only_once():
    game, (helper, new_helper, far_target) = season3_turn([(10, 5), (13, 5), (16, 5)], ball=(20, 12))
    helper.extra_skills = new_helper.extra_skills = [Skill.PICK_ME_UP]
    new_helper.state.up = far_target.state.up = False
    with only_fixed_rolls(game, d6=[5]):
        run_proc(game, PickMeUp(game, helper.team))
    assert new_helper.state.up
    assert not far_target.state.up


def test_leader_pool_is_available_with_no_standard_rerolls_and_consumed_separately():
    game, (leader, player) = season3_turn([(10, 5), (13, 5)], ball=(20, 12))
    leader.extra_skills = [Skill.LEADER]
    leader.team.state.leader_reroll = True
    assert game.can_use_reroll(player.team)
    with only_fixed_rolls(game, d6=[1, 2]):
        run_proc(game, GFI(game, player, game.get_square(14, 5)))
        game.step(Action(ActionType.USE_REROLL))
    assert player.team.state.rerolls == 0
    assert not player.team.state.leader_reroll


def test_leader_pool_unavailable_while_leader_is_off_pitch():
    game, (leader,) = season3_turn([(10, 5)], ball=(20, 12))
    leader.extra_skills = [Skill.LEADER]
    leader.team.state.leader_reroll = True
    game.pitch_to_reserves(leader)
    assert not game.can_use_reroll(leader.team)


def test_secret_weapon_is_sent_off_even_after_being_knocked_out():
    game, (weapon,) = season3_turn([(10, 5)], ball=(20, 12))
    weapon.extra_skills = [Skill.SECRET_WEAPON]
    weapon.state.played_drive = True
    game.pitch_to_kod(weapon)
    game.state.current_team = None
    game.state.weather = WeatherType.NICE
    with only_fixed_rolls(game):
        run_proc(game, EndDrive(game))
        game.step(Action(ActionType.DONT_ARGUE_CALL))
    assert weapon.state.ejected
    assert weapon in game.get_dungeon(weapon.team)
    assert weapon not in game.get_knocked_out(weapon.team)


def test_saboteur_knocks_out_owner_and_knocks_down_attacker_without_turnover():
    game, (attacker, owner) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    owner.extra_skills = [Skill.SABOTEUR, Skill.SECRET_WEAPON]
    owner.team.state.apothecaries = 0
    with only_fixed_rolls(game, d6=[4, 1, 2]):
        run_proc(game, KnockDown(game, owner, inflictor=attacker, block=True))
        game.step(Action(ActionType.USE_SKILL))
    assert owner.state.knocked_out
    assert not attacker.state.up
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
