"""Source-based Season 3 skill status, probability and resolution scenarios."""
from copy import deepcopy

import pytest

from botbowl import Action, ActionType, OutcomeType, PassDistance, Player, Role, Skill, WeatherType
from botbowl.core.skill_rules import SKILL_RULES, target_parameter
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_season3_pathfinding import pf
from tests.util import only_fixed_rolls


@pytest.mark.parametrize('skill', list(SKILL_RULES), ids=lambda s: s.name)
@pytest.mark.parametrize('status', ['standing', 'prone', 'stunned', 'distracted'])
def test_skill_possession_and_availability_are_distinct(skill, status):
    role = Role('test', ['test'], 6, 3, 3, 9, [skill], 0, False, pa=4, target_characteristics=True)
    player = Player('test', role, 'test', 1, None)
    player.state.up = status not in ('prone', 'stunned')
    player.state.stunned = status == 'stunned'
    player.state.distracted = status == 'distracted'
    assert player.has_skill(skill)
    expected = SKILL_RULES[skill]['availability'] == 'passive' or status == 'standing'
    expected |= skill == Skill.JUMP_UP and status == 'prone'
    assert player.has_usable_skill(skill) == expected


@pytest.mark.parametrize('distance,base', [
    (PassDistance.QUICK_PASS, 0), (PassDistance.SHORT_PASS, -1),
    (PassDistance.LONG_PASS, -2), (PassDistance.LONG_BOMB, -3),
    (PassDistance.HAIL_MARY, -3)])
def test_range_specific_passing_skills(distance, base):
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.ACCURATE]
    assert game.get_pass_modifiers(player, distance) == base + int(distance in (PassDistance.QUICK_PASS, PassDistance.SHORT_PASS))
    player.extra_skills = [Skill.CANNONEER]
    assert game.get_pass_modifiers(player, distance) == base + int(distance not in (PassDistance.QUICK_PASS, PassDistance.SHORT_PASS))
    player.extra_skills = [Skill.STRONG_ARM]
    assert game.get_pass_modifiers(player, distance) == base
    player.extra_skills = [Skill.STUNTY]
    assert game.get_pass_modifiers(player, distance) == base


def test_interception_bonus_and_nerves_of_steel_scope():
    game, (player, _) = season3_turn([(5, 5)], [(5, 6)])
    player.extra_skills = [Skill.VERY_LONG_LEGS, Skill.NERVES_OF_STEEL, Skill.EXTRA_ARMS]
    assert game.get_catch_modifiers(player, interception=True) == -1  # -3, -1 marking, +2 legs, +1 arms
    assert game.get_catch_modifiers(player, accurate=True) == 1  # marking ignored on Catch
    player.extra_skills = [Skill.DIVING_CATCH]
    assert game.get_catch_modifiers(player, accurate=True) == 0  # +1, -1 marking
    assert game.get_catch_modifiers(player, handoff=True) == -1


def test_stunty_has_no_extra_agility_bonus_and_tails_do_not_stack():
    game, (player, tail1, tail2) = season3_turn([(5, 5)], [(5, 6), (6, 6)])
    tail1.extra_skills = tail2.extra_skills = [Skill.PREHENSILE_TAIL]
    player.extra_skills = [Skill.STUNTY]
    assert game.get_dodge_modifiers(player, game.get_square(6, 5)) == -1
    player.extra_skills.append(Skill.TITCHY)
    assert game.get_dodge_modifiers(player, game.get_square(6, 5)) == 0
    tail1.state.distracted = tail2.state.distracted = True
    assert game.get_dodge_modifiers(player, game.get_square(6, 5)) == 1


def test_big_hand_extra_arms_and_distraction_on_pickups():
    game, (player, _) = season3_turn([(5, 5)], [(5, 6)])
    game.state.weather = WeatherType.POURING_RAIN
    player.extra_skills = [Skill.BIG_HAND, Skill.EXTRA_ARMS]
    assert game.get_pickup_modifiers(player, player.position) == 1
    player.state.distracted = True
    assert game.get_pickup_modifiers(player, player.position) == -2


@pytest.mark.parametrize('loner_roll,success', [(2, False), (3, True), (4, True)])
def test_loner_three_plus_uses_profile_parameter_and_spends_reroll(loner_roll, success):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5), rerolls=1)
    player.role = deepcopy(player.role)
    player.role.skills = [Skill.LONER]
    player.role.skill_parameters = {Skill.LONER: '3+'}
    game.step(Action(ActionType.START_MOVE, player=player))
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.MOVE, position=game.get_square(6, 5)))
    with only_fixed_rolls(game, d6=[loner_roll, 4] if success else [loner_roll], d8=[] if success else [3]):
        game.step(Action(ActionType.USE_REROLL))
    assert player.team.state.rerolls == 0
    assert game.has_report_of_type(OutcomeType.SUCCESSFUL_LONER) == success
    assert game.has_report_of_type(OutcomeType.FAILED_LONER) != success
    assert (game.get_ball_carrier() == player) == success


def test_invalid_trait_target_is_rejected_instead_of_guessed():
    game, (player,) = season3_turn([(5, 5)])
    player.role = deepcopy(player.role)
    player.role.skill_parameters = {Skill.LONER: '4+3+'}
    with pytest.raises(ValueError, match='target-number'):
        target_parameter(player, Skill.LONER, 4)


def test_no_ball_cannot_catch_intercept_secure_or_pick_up():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    player.extra_skills = [Skill.NO_BALL]
    assert not player.can_catch()
    assert not game.can_secure_ball(player)
    assert game.get_pickup_prob(player, game.get_square(6, 5), allow_team_reroll=True) == 0
    game.set_available_actions()
    game.step(Action(ActionType.START_MOVE, player=player))
    with only_fixed_rolls(game, d8=[3]):  # No pickup die is rolled for No Ball.
        game.step(Action(ActionType.MOVE, position=game.get_square(6, 5)))
    assert game.has_report_of_type(OutcomeType.FAILED_PICKUP)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.get_ball_carrier() is None


def test_my_ball_and_unsteady_declaration_restrictions():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    player.extra_skills = [Skill.UNSTEADY]
    assert not game.can_secure_ball(player)
    player.extra_skills = [Skill.MY_BALL]
    choices = game.current_turn().available_actions()
    assert not any(player in choice.players for choice in choices
                   if choice.action_type in (ActionType.START_PASS, ActionType.START_HANDOFF))


def test_titchy_still_marks_but_does_not_penalize_incoming_dodges():
    game, (player, opponent) = season3_turn([(5, 5)], [(5, 6)])
    opponent.extra_skills = [Skill.TITCHY]
    assert opponent.has_tackle_zone()
    assert game.num_tackle_zones_in(player) == 1
    assert game.get_dodge_modifiers(player, game.get_square(6, 5)) == 0
    assert game.get_catch_modifiers(player, handoff=True) == -1


@pytest.mark.parametrize('weather,target', [(WeatherType.NICE, 3), (WeatherType.BLIZZARD, 4)])
def test_drunkard_rush_resolution_and_action_preview(weather, target):
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12))
    game.state.weather = weather
    player.extra_skills = [Skill.DRUNKARD]
    game.step(Action(ActionType.START_MOVE, player=player))
    player.state.moves = player.get_ma()
    game.set_available_actions()
    move = next(a for a in game.get_available_actions() if a.action_type == ActionType.MOVE)
    index = move.positions.index(game.get_square(6, 5))
    assert move.rolls[index][0] == target
    with only_fixed_rolls(game, d6=[target - 1, 1, 1]):
        game.step(Action(ActionType.MOVE, position=game.get_square(6, 5)))
    assert not player.state.up
    assert game.has_report_of_type(OutcomeType.FAILED_GFI)


@pytest.mark.parametrize('skill', [Skill.LEAP, Skill.POGO])
def test_leap_and_pogo_cross_standing_players_repeatedly(skill):
    game, (player, blocker) = season3_turn([(5, 5)], [(6, 5)], ball=(20, 12))
    player.extra_skills = [skill]
    assert game.get_square(7, 5) in game.get_jump_positions(player)
    game.step(Action(ActionType.START_MOVE, player=player))
    with only_fixed_rolls(game, d6=[6, 6]):
        game.step(Action(ActionType.JUMP, position=game.get_square(7, 5)))
        game.step(Action(ActionType.JUMP, position=game.get_square(9, 5)))
    assert player.position == game.get_square(9, 5)
    assert player.state.moves == 4
    assert blocker.state.up


@pytest.mark.parametrize('skill,expected', [(Skill.LEAP, -1), (Skill.POGO, 0), (Skill.VERY_LONG_LEGS, -1)])
def test_jump_modifiers_include_skill_and_a_single_tail(skill, expected):
    game, (player, tail1, tail2) = season3_turn([(5, 5)], [(5, 6), (7, 6)], ball=(20, 12))
    tail1.extra_skills = tail2.extra_skills = [Skill.PREHENSILE_TAIL]
    player.extra_skills = [skill]
    assert game.get_jump_modifiers(player, player.position, game.get_square(7, 5)) == expected


@pytest.mark.parametrize('skill,expected', [(Skill.TITCHY, 5 / 6), (Skill.TWO_HEADS, 5 / 6),
                                            (Skill.STUNTY, 4 / 6)])
def test_pathfinders_share_dodge_skill_probabilities(pf, skill, expected):
    from botbowl import Square
    game, (player, _) = season3_turn([(5, 5)], [(4, 5)], ball=(20, 12))
    player.extra_skills = [skill]
    player.state.moves = player.get_ma() - 1
    path = pf.get_safest_path(game, player, Square(6, 5))
    assert path.prob == pytest.approx(expected)


def test_pathfinders_share_big_hand_extra_arms_pickup(pf):
    from botbowl import Square
    game, (player, _) = season3_turn([(5, 5)], [(7, 5)], ball=(6, 5))
    player.extra_skills = [Skill.BIG_HAND, Skill.EXTRA_ARMS]
    game.state.weather = WeatherType.POURING_RAIN
    path = pf.get_safest_path(game, player, Square(6, 5))
    assert path.prob == pytest.approx(5 / 6)


def test_pathfinders_share_drunkard_rush_target(pf):
    from botbowl import Square
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12))
    player.extra_skills = [Skill.DRUNKARD]
    player.state.moves = player.get_ma()
    path = pf.get_safest_path(game, player, Square(6, 5))
    assert path.prob == pytest.approx(4 / 6)


def test_safe_pass_retains_ball_on_natural_one_without_turnover():
    game, (passer, receiver) = season3_turn([(13, 5), (15, 5)], ball=(13, 5))
    passer.extra_skills = [Skill.SAFE_PASS]
    with only_fixed_rolls(game, d6=[1]):
        pass_ball(game, passer, receiver.position)
    assert game.get_ball_carrier() == passer
    assert passer.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.FUMBLE)


def test_safe_pass_does_not_protect_modified_fumble_on_natural_two():
    game, (passer, receiver) = season3_turn([(3, 5), (14, 5)], ball=(3, 5))
    passer.extra_skills = [Skill.SAFE_PASS]
    with only_fixed_rolls(game, d6=[2], d8=[3]):
        pass_ball(game, passer, receiver.position)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.has_report_of_type(OutcomeType.FUMBLE)


@pytest.mark.parametrize('long_legs', [False, True])
def test_cloud_burster_blocks_interceptors_except_very_long_legs(long_legs):
    from botbowl import Interception
    game, (passer, receiver, interceptor) = season3_turn([(3, 5), (10, 5)], [(6, 5)], (3, 5))
    passer.extra_skills = [Skill.CLOUD_BURSTER]
    interceptor.extra_skills = [Skill.VERY_LONG_LEGS] if long_legs else []
    with only_fixed_rolls(game, d6=[6] if long_legs else [6, 3]):
        pass_ball(game, passer, receiver.position)
    assert isinstance(game.get_procedure(), Interception) == long_legs
    if long_legs:
        assert interceptor in game.get_available_actions()[0].players
    else:
        assert game.get_ball_carrier() == receiver


def test_successful_hail_mary_is_inaccurate_and_does_not_use_pass_reroll():
    from botbowl import Season3PassAttempt
    from tests.game.test_season3_flow import run_proc
    game, (passer,) = season3_turn([(3, 5)], ball=(3, 5), rerolls=1)
    passer.extra_skills = [Skill.HAIL_MARY_PASS, Skill.PASS]
    with only_fixed_rolls(game, d6=[6], d8=[3, 3, 3, 3]):
        run_proc(game, Season3PassAttempt(game, passer, game.get_ball(), game.get_square(17, 5), PassDistance.HAIL_MARY))
    assert game.has_report_of_type(OutcomeType.INACCURATE_PASS)
    assert not game.has_report_of_type(OutcomeType.ACCURATE_PASS)
    assert not any(r.skill == Skill.PASS for r in game.state.reports)
