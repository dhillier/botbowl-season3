import pytest

from botbowl import (Action, ActionType, Armor, KnockDown, Skill, OutcomeType,
                     Foul, Season3Escape)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('claws', [False, True])
def test_iron_hard_skin_ignores_armour_modifiers_and_claws(claws):
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.IRON_HARD_SKIN]
    defender.extra_av = 2
    with only_fixed_rolls(game, d6=[4, 4]):
        run_proc(game, Armor(game, defender, modifiers=4, inflictor=attacker,
                            damage_skill=Skill.MIGHTY_BLOW, claws=claws))
    report = next(r for r in game.state.reports if r.outcome_type == OutcomeType.ARMOR_NOT_BROKEN)
    assert report.rolls[0].modifiers == 0


def test_claws_does_not_spend_mighty_blow_when_natural_eight_already_breaks_armour():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.CLAWS, Skill.MIGHTY_BLOW]
    defender.extra_av = 0
    defender.team.state.apothecaries = 0
    with only_fixed_rolls(game, d6=[4, 4, 4, 3]):
        run_proc(game, KnockDown(game, defender, inflictor=attacker, block=True))
    assert defender.state.knocked_out


def test_arm_bar_applies_once_to_failed_dodge_injury():
    game, (player, holder, other) = season3_turn([(10, 5)], [(9, 5), (9, 6)], ball=(20, 12))
    holder.extra_skills = other.extra_skills = [Skill.ARM_BAR]
    with only_fixed_rolls(game, d6=[1, 4, 4, 1, 1]):
        run_proc(game, Season3Escape(game, player, game.get_square(11, 5)))
    armor = next(r for r in game.state.reports if r.outcome_type == OutcomeType.ARMOR_BROKEN)
    assert armor.rolls[0].modifiers == 1
    assert player.state.stunned


def test_safe_pair_of_hands_places_ball_before_falling_without_bounce():
    game, (player,) = season3_turn([(10, 5)], ball=(10, 5))
    player.extra_skills = [Skill.SAFE_PAIR_OF_HANDS]
    with only_fixed_rolls(game, d6=[1, 1]):
        run_proc(game, KnockDown(game, player, turnover=True))
        game.step(Action(ActionType.PLACE_BALL, position=game.get_square(11, 5)))
    assert not player.state.up
    assert game.get_ball().position.x == 11
    assert not game.get_ball().is_carried
    assert not game.has_report_of_type(OutcomeType.BALL_BOUNCED)
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_steady_footing_six_prevents_knockdown_and_turnover():
    game, (player,) = season3_turn([(10, 5)], ball=(10, 5))
    player.extra_skills = [Skill.STEADY_FOOTING]
    with only_fixed_rolls(game, d6=[6]):
        run_proc(game, KnockDown(game, player, turnover=True))
    assert player.state.up
    assert game.get_ball_carrier() == player
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_lone_fouler_rerolls_failed_armour_before_checking_doubles():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.LONE_FOULER]
    defender.state.up = False
    with only_fixed_rolls(game, d6=[1, 1, 5, 4, 1, 2]):
        run_proc(game, Foul(game, attacker, defender))
    assert defender.state.stunned
    assert not attacker.state.ejected
    assert not game.has_report_of_type(OutcomeType.PLAYER_EJECTED)
