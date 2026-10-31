import pytest

from botbowl import Action, ActionType, Skill, OutcomeType, Season3Escape, Shadowing, Turn
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('strength,die,held', [(3, 5, False), (3, 6, True), (5, 4, True),
                                            (5, 3, False), (8, 1, False), (1, 6, True)])
@pytest.mark.parametrize('jump', [False, True])
def test_tentacles_one_holder_roll_and_ends_activation(strength, die, held, jump):
    game, (player, holder, unused) = season3_turn([(10, 5)], [(9, 5), (9, 6)], ball=(20, 12))
    holder.extra_st = strength - holder.get_st()
    holder.extra_skills = unused.extra_skills = [Skill.TENTACLES]
    game.state.active_player = player
    target = game.get_square(12 if jump else 11, 5)
    with only_fixed_rolls(game, d6=[die] if held else [die, 6]):
        run_proc(game, Season3Escape(game, player, target, jump=jump))
        assert set(game.get_available_actions()[0].players) == {holder, unused}
        game.step(Action(ActionType.USE_SKILL, player=holder))
    assert player.state.used == held
    assert player.position == (game.get_square(10, 5) if held else target)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('strength,die', [(3, 2), (4, 2), (5, 2)])
def test_break_tackle_adds_strength_dependent_modifier_after_roll(strength, die):
    game, (player, marker) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    player.extra_st = strength - player.get_st()
    player.extra_ag = -({3: 3, 4: 4, 5: 5}[strength] - player.get_ag())
    player.extra_skills = [Skill.BREAK_TACKLE]
    with only_fixed_rolls(game, d6=[die]):
        run_proc(game, Season3Escape(game, player, game.get_square(11, 5)))
        assert game.get_available_actions()[0].skill == Skill.BREAK_TACKLE
        game.step(Action(ActionType.USE_SKILL))
    assert player.position.x == 11
    assert player.has_used_skill(Skill.BREAK_TACKLE)
    assert not player.can_use_skill(Skill.BREAK_TACKLE)


def test_diving_tackle_is_chosen_after_dodge_reroll_and_cannot_be_rerolled_again():
    game, (player, diver) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12), rerolls=1)
    player.extra_skills = [Skill.DODGE]
    diver.extra_skills = [Skill.DIVING_TACKLE]
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[1, 3, 1, 1]):
        run_proc(game, Season3Escape(game, player, game.get_square(11, 5)))
        assert game.get_available_actions()[0].skill == Skill.DIVING_TACKLE
        assert player.has_used_skill(Skill.DODGE)
        game.step(Action(ActionType.USE_SKILL, player=diver))
    assert not player.state.up
    assert not diver.state.up
    assert diver.position == game.get_square(10, 5)
    assert player.team.state.rerolls == 1


@pytest.mark.parametrize('die,moved', [(3, False), (4, True)])
def test_shadowing_uses_single_four_plus_roll_and_limits_attempts(die, moved):
    game, (player, shadower) = season3_turn([(11, 5)], [(9, 5)], ball=(20, 12))
    shadower.extra_skills = [Skill.SHADOWING]
    shadower.state.shadowing_uses = shadower.get_ma() - 1
    with only_fixed_rolls(game, d6=[die]):
        run_proc(game, Shadowing(game, player, game.get_square(10, 5), [shadower]))
        game.step(Action(ActionType.USE_SKILL, player=shadower))
    assert shadower.position.x == (10 if moved else 9)
    with only_fixed_rolls(game):
        run_proc(game, Shadowing(game, player, game.get_square(10, 6), [shadower]))
    assert isinstance(game.get_procedure(), Turn)
