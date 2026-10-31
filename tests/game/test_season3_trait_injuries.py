"""Season 3 injury-table and treatment timing for additional roster traits."""
import pytest

from botbowl import Casualty, CasualtyEffect, Injury, OutcomeType, ReallyStupid, Skill
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


@pytest.mark.parametrize('roll', [4, 5, 6])
def test_regeneration_precedes_casualty_roll_and_apothecary(roll):
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.REGENERATION]
    player.team.state.apothecaries = 1
    with only_fixed_rolls(game, d6=[roll]):  # Any D16 or treatment roll would fail this test.
        run_proc(game, Casualty(game, player))
    assert player in game.get_reserves(player.team)
    assert player.team.state.apothecaries == 1
    assert game.has_report_of_type(OutcomeType.SUCCESSFUL_REGENERATION)
    assert not game.has_report_of_type(OutcomeType.CASUALTY_RESULT)


@pytest.mark.parametrize('roll', [1, 2, 3])
def test_failed_regeneration_continues_to_casualty_roll(roll):
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.REGENERATION]
    with only_fixed_rolls(game, d6=[roll], d16=[16]):
        run_proc(game, Casualty(game, player))
    assert game.has_report_of_type(OutcomeType.FAILED_REGENERATION)
    assert game.has_report_of_type(OutcomeType.DEAD)
    assert CasualtyEffect.DEAD in player.state.injuries_gained


@pytest.mark.parametrize('decay,dead', [(False, False), (True, True)])
def test_decay_modifies_single_casualty_roll(decay, dead):
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.DECAY] if decay else []
    with only_fixed_rolls(game, d16=[14]):
        run_proc(game, Casualty(game, player))
    assert game.has_report_of_type(OutcomeType.DEAD) == dead
    rolls = [r for r in game.state.reports if r.outcome_type == OutcomeType.CASUALTY_RESULT]
    assert len(rolls) == 1
    assert rolls[0].rolls[0].modifiers == int(decay)


def test_eaten_player_cannot_regenerate_or_use_apothecary():
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.REGENERATION]
    player.team.state.apothecaries = 1
    with only_fixed_rolls(game):
        run_proc(game, Casualty(game, player, always_hungry=True))
    assert game.has_report_of_type(OutcomeType.DEAD)
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_REGENERATION)
    assert player.team.state.apothecaries == 1


@pytest.mark.parametrize('total', range(2, 13))
@pytest.mark.parametrize('thick_skull', [False, True])
def test_stunty_injury_table_boundaries(total, thick_skull):
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.STUNTY] + ([Skill.THICK_SKULL] if thick_skull else [])
    dice = [min(6, total - 1), total - min(6, total - 1)]
    with only_fixed_rolls(game, d6=dice, d16=[8] if total >= 10 else []):
        run_proc(game, Injury(game, player))
    assert game.has_report_of_type(OutcomeType.STUNNED) == (total <= 6 or (total == 7 and thick_skull))
    assert game.has_report_of_type(OutcomeType.KNOCKED_OUT) == (total == 8 or (total == 7 and not thick_skull))
    assert game.has_report_of_type(OutcomeType.BADLY_HURT) == (total >= 9)
    if total == 9:
        assert not any(r.rolls and r.rolls[0].dice for r in game.state.reports if r.outcome_type == OutcomeType.CASUALTY_RESULT)


@pytest.mark.parametrize('status,expected', [('standing', 2), ('prone', 4), ('distracted', 4), ('stupid', 4)])
def test_really_stupid_helper_must_be_standing_and_not_distracted(status, expected):
    game, (player, helper) = season3_turn([(5, 5), (5, 6)])
    helper.state.up = status != 'prone'
    helper.state.distracted = status == 'distracted'
    helper.extra_skills = [Skill.REALLY_STUPID] if status == 'stupid' else []
    assert ReallyStupid(game, player).get_target() == expected
