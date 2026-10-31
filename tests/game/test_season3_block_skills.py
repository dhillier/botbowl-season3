"""Resolution tests for Season 3 assists and push-related skills."""
import pytest

from botbowl import (Action, ActionType, Skill, OutcomeType, Push, FollowUp,
                     EndPlayerTurn, FoulAppearance, Block)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('foul,skill', [(False, Skill.GUARD), (True, Skill.PUT_THE_BOOT_IN)])
@pytest.mark.parametrize('defensive', [False, True])
def test_defensive_cancels_marked_offensive_assist_skill(foul, skill, defensive):
    game, (attacker, helper, defender, marker) = season3_turn(
        [(10, 5), (11, 6)], [(11, 5), (12, 6)], ball=(20, 12))
    helper.extra_skills = [skill]
    marker.extra_skills = [Skill.DEFENSIVE] if defensive else []
    defender.state.up = not foul
    expected = [] if defensive else [helper]
    assert game.get_assisting_players(attacker, defender, foul) == expected
    assert game.num_assists_at(attacker, defender, attacker.position, foul)[0] == len(expected)
    marker.state.distracted = True
    assert game.get_assisting_players(attacker, defender, foul) == [helper]


def test_put_boot_in_does_not_allow_defensive_foul_assist():
    game, (attacker, marker, defender, helper) = season3_turn(
        [(10, 5), (9, 6)], [(11, 5), (10, 6)], ball=(20, 12))
    defender.state.up = False
    helper.extra_skills = [Skill.PUT_THE_BOOT_IN]
    assert game.get_assisting_players(defender, attacker, foul=True) == []
    assert game.num_assists_at(attacker, defender, attacker.position, foul=True)[1] == 0


def test_eye_gouge_blocks_assists_but_keeps_marking_until_activation_ends():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.EYE_GOUGE]
    with only_fixed_rolls(game):
        run_proc(game, Push(game, attacker, defender))
        game.step(Action(ActionType.PUSH, position=game.get_square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=attacker.position))
    assert defender.state.eye_gouged
    assert not defender.can_assist()
    assert defender.has_tackle_zone()
    defender.state.reset_turn()
    assert defender.state.eye_gouged
    with only_fixed_rolls(game):
        run_proc(game, EndPlayerTurn(game, defender))
    assert defender.can_assist()


@pytest.mark.parametrize('rooted', [False, True])
def test_strip_ball_requires_actual_push(rooted):
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(11, 5))
    attacker.extra_skills = [Skill.STRIP_BALL]
    defender.extra_skills = [Skill.TAKE_ROOT if rooted else Skill.STAND_FIRM]
    defender.state.taken_root = rooted
    with only_fixed_rolls(game):
        run_proc(game, Push(game, attacker, defender))
        if not rooted:
            game.step(Action(ActionType.USE_SKILL))
    assert game.get_ball_carrier() == defender
    assert not game.has_report_of_type(OutcomeType.FUMBLE)


def test_strip_ball_bounces_after_follow_up_and_before_knockdown():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(11, 5))
    attacker.extra_skills = [Skill.STRIP_BALL]
    with only_fixed_rolls(game, d6=[1, 1], d8=[5]):
        run_proc(game, Push(game, attacker, defender, knock_down=True))
        game.step(Action(ActionType.PUSH, position=game.get_square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=game.get_square(11, 5)))
    reports = [r.outcome_type for r in game.state.reports]
    assert reports.index(OutcomeType.FOLLOW_UP) < reports.index(OutcomeType.FUMBLE)
    assert reports.index(OutcomeType.BALL_BOUNCED) < reports.index(OutcomeType.KNOCKED_DOWN)
    assert not defender.state.up


@pytest.mark.parametrize('blitz', [False, True])
def test_juggernaut_overrides_fend_only_when_blitzing(blitz):
    game, (attacker, defender) = season3_turn([(10, 5)], [(12, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.JUGGERNAUT]
    defender.extra_skills = [Skill.FEND]
    with only_fixed_rolls(game):
        run_proc(game, FollowUp(game, attacker, defender, game.get_square(11, 5), blitz=blitz))
        if blitz:
            game.step(Action(ActionType.FOLLOW_UP, position=game.get_square(11, 5)))
    assert attacker.position.x == (11 if blitz else 10)


def test_taunt_lets_defender_require_follow_up():
    game, (attacker, defender) = season3_turn([(10, 5)], [(12, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.TAUNT]
    with only_fixed_rolls(game):
        run_proc(game, FollowUp(game, attacker, defender, game.get_square(11, 5)))
        assert game.get_available_actions()[0].team == defender.team
        game.step(Action(ActionType.USE_SKILL))
    assert attacker.position.x == 11


def test_grab_cancels_sidestep_during_blitz_without_free_direction():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.GRAB]
    defender.extra_skills = [Skill.SIDE_STEP]
    run_proc(game, Push(game, attacker, defender, blitz=True))
    choice = game.get_available_actions()[0]
    assert choice.team == attacker.team
    assert {p.x for p in choice.positions} == {12}


def test_foul_appearance_failure_ends_blitz_activation():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.FOUL_APPEARANCE]
    game.state.active_player = attacker
    with only_fixed_rolls(game, d6=[1]):
        run_proc(game, Block(game, attacker, defender, blitz=True))
    assert attacker.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
