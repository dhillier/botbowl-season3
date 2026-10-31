import pytest

from botbowl import (Action, ActionType, Skill, OutcomeType, BloodLust, EatThrall,
                     HypnoticGaze, Animosity, MoveAction, CasualtyEffect)
from tests.util import only_fixed_rolls
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_season3_flow import run_proc


@pytest.mark.parametrize('kind,skill,dice', [(ActionType.START_HANDOFF, Skill.GIVE_AND_GO, [3]),
                                           (ActionType.START_PASS, Skill.GIVE_AND_GO, [6, 3]),
                                           (ActionType.START_FOUL, Skill.QUICK_FOUL, [1, 2])])
def test_continue_moving_after_skill_action(kind, skill, dice):
    if kind == ActionType.START_FOUL:
        game, (player, target) = season3_turn([(13, 5)], [(14, 5)], ball=(20, 12))
        target.state.up = False
    else:
        game, (player, target) = season3_turn([(13, 5), (14, 5)], ball=(13, 5))
    player.extra_skills = [skill]
    action = {ActionType.START_HANDOFF: ActionType.HANDOFF, ActionType.START_PASS: ActionType.PASS,
              ActionType.START_FOUL: ActionType.FOUL}[kind]
    with only_fixed_rolls(game, d6=dice):
        game.step(Action(kind, player=player))
        game.step(Action(action, position=target.position))
    assert isinstance(game.get_procedure(), MoveAction)
    assert not player.state.used
    game.step(Action(ActionType.MOVE, position=game.get_square(12, 5)))
    assert player.position.x == 12
    assert player.state.moves == 1


@pytest.mark.parametrize('keyword,die,refused', [('All', 1, True), ('Human', 1, True),
                                              ('Human', 2, False), ('Goblin', None, False)])
def test_animosity_only_rolls_for_named_keyword(keyword, die, refused):
    game, (player, receiver) = season3_turn([(13, 5), (14, 5)], ball=(13, 5))
    player.extra_skills = [Skill.ANIMOSITY]
    player.role.skill_parameters = {Skill.ANIMOSITY: keyword}
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[] if die is None else [die]):
        proc = Animosity(game, player, receiver)
        run_proc(game, proc)
    assert proc.failed == refused
    assert player.state.used == refused
    assert game.get_ball_carrier() == player


@pytest.mark.parametrize('die,distracted', [(1, True), (2, True), (3, False), (4, False)])
def test_unchannelled_fury_move_uses_four_plus_without_losing_tackle_zone(die, distracted):
    game, (player,) = season3_turn([(13, 5)], ball=(20, 12))
    player.extra_skills = [Skill.UNCHANNELLED_FURY]
    with only_fixed_rolls(game, d6=[die]):
        game.step(Action(ActionType.START_MOVE, player=player))
    assert player.state.used == (die < 4)
    assert player.has_tackle_zone()


def test_animal_savagery_can_knock_down_teammate_then_continue():
    game, (player, victim) = season3_turn([(13, 5), (14, 5)], ball=(20, 12))
    player.extra_skills = [Skill.ANIMAL_SAVAGERY, Skill.MIGHTY_BLOW]
    with only_fixed_rolls(game, d6=[1, 4, 4, 1, 2]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.SELECT_PLAYER, player=victim))
    assert victim.state.stunned
    assert not player.state.used
    assert isinstance(game.get_procedure(), MoveAction)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_animal_savagery_without_standing_teammate_causes_distraction():
    game, (player, victim) = season3_turn([(13, 5), (14, 5)], ball=(20, 12))
    player.extra_skills = [Skill.ANIMAL_SAVAGERY]
    victim.state.up = False
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.START_MOVE, player=player))
    assert player.state.used
    assert player.is_distracted()


@pytest.mark.parametrize('action,target', [(ActionType.START_BLOCK, 2), (ActionType.START_BLITZ, 2),
                                        (ActionType.START_MOVE, 3)])
def test_bloodlust_uses_roster_parameter_and_attack_bonus(action, target):
    game, (player,) = season3_turn([(13, 5)], ball=(20, 12))
    player.role = game.ruleset.get_role('Vampire Blitzer', 'Vampire')
    proc = BloodLust(game, player, declared_action=action)
    assert proc.get_target() == target


def test_bloodlust_without_thrall_keeps_vampire_on_pitch_distracted():
    game, (player, non_thrall) = season3_turn([(13, 5), (14, 5)], ball=(13, 5))
    player.state.blood_lust = True
    with only_fixed_rolls(game, d8=[2]):
        run_proc(game, EatThrall(game, player))
    assert player.position == game.get_square(13, 5)
    assert player.is_distracted()
    assert game.get_ball_carrier() is None
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_bloodlust_bite_can_target_stunned_thrall_and_casualty_is_badly_hurt():
    game, (player, thrall) = season3_turn([(13, 5), (14, 5)], ball=(20, 12))
    thrall.role = game.ruleset.get_role('Thrall Lineman', 'Vampire')
    thrall.state.up = False
    thrall.state.stunned = True
    with only_fixed_rolls(game, d6=[6, 6]):
        run_proc(game, EatThrall(game, player))
        game.step(Action(ActionType.SELECT_PLAYER, position=thrall.position))
    assert game.has_report_of_type(OutcomeType.BADLY_HURT)
    assert CasualtyEffect.DEAD not in thrall.state.injuries_gained
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_hypnotic_gaze_uses_fixed_three_plus_ignoring_agility_and_marking():
    game, (player, victim, marker) = season3_turn([(13, 5)], [(14, 5), (13, 6)], ball=(20, 12))
    player.extra_skills = [Skill.HYPNOTIC_GAZE]
    player.extra_ag = -2
    with only_fixed_rolls(game, d6=[3]):
        run_proc(game, HypnoticGaze(game, player, victim))
    assert victim.is_distracted()
