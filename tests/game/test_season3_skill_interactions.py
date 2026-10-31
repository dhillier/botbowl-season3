"""Season 3 interactions that differ from the inherited rules engine."""
import pytest

from botbowl import (Action, ActionType, BBDieResult, Block, Catch, Skill,
                     Square, OutcomeType, Season3Escape, StandUp, GFI, Push,
                     Foul, KnockDown, Bonehead, PassDistance)
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


def test_dauntless_is_applied_before_horns_and_assists():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.DAUNTLESS, Skill.HORNS]
    defender.extra_st = 1
    with only_fixed_rolls(game, d6=[2], block_dice=[BBDieResult.PUSH, BBDieResult.PUSH]):
        run_proc(game, Block(game, attacker, defender, blitz=True))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=Square(10, 5)))
    assert len(next(r.rolls[0].dice for r in game.state.reports if r.outcome_type == OutcomeType.BLOCK_ROLL)) == 2


def test_failed_dauntless_can_use_a_team_reroll():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12), rerolls=1)
    attacker.extra_skills = [Skill.DAUNTLESS]
    defender.extra_st = 1
    with only_fixed_rolls(game, d6=[1, 2], block_dice=[BBDieResult.PUSH]):
        run_proc(game, Block(game, attacker, defender))
        game.step(Action(ActionType.USE_REROLL))
        assert attacker.team.state.rerolls == 0
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=Square(10, 5)))


def test_wrestle_remains_a_choice_when_attacker_also_has_block():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.BLOCK, Skill.WRESTLE]
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN]):
        run_proc(game, Block(game, attacker, defender))
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
        assert game.get_available_actions()[0].skill == Skill.WRESTLE
        game.step(Action(ActionType.USE_SKILL))
    assert not attacker.state.up and not defender.state.up
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('kick', [False, True])
def test_diving_catch_bonus_only_for_pass_target_not_kickoff(kick):
    game, (catcher,) = season3_turn([(10, 5)], ball=(10, 5))
    catcher.extra_skills = [Skill.DIVING_CATCH]
    game.get_ball().is_carried = False
    with only_fixed_rolls(game, d6=[2], d8=[5] if kick else []):
        run_proc(game, Catch(game, catcher, game.get_ball(), kick=kick,
                             inaccurate=not kick, target_square=None if kick else catcher.position))
    assert (game.get_ball_carrier() == catcher) == (not kick)


def test_inaccurate_pass_scattering_back_to_target_gets_diving_catch_bonus():
    game, (passer, catcher) = season3_turn([(5, 5), (8, 5)], ball=(5, 5))
    catcher.extra_skills = [Skill.DIVING_CATCH]
    with only_fixed_rolls(game, d6=[2, 2], d8=[5, 6, 2]):
        pass_ball(game, passer, catcher.position)
    assert game.has_report_of_type(OutcomeType.INACCURATE_PASS)
    assert game.get_ball_carrier() == catcher


def test_diving_catch_at_adjacent_square_does_not_get_target_bonus():
    game, (passer, catcher) = season3_turn([(5, 5), (8, 6)], ball=(5, 5))
    catcher.extra_skills = [Skill.DIVING_CATCH]
    with only_fixed_rolls(game, d6=[6, 2], d8=[5]):
        pass_ball(game, passer, Square(8, 5))
    assert game.get_ball_carrier() is None
    assert game.has_report_of_type(OutcomeType.FAILED_CATCH)


def test_distracted_diving_catcher_does_not_prevent_eligible_teammate_catching():
    game, (first, second) = season3_turn([(9, 5), (10, 6)], ball=(10, 5))
    first.extra_skills = second.extra_skills = [Skill.DIVING_CATCH]
    first.state.distracted = True
    assert game.get_catcher(Square(10, 5)) == second


def test_pogo_ignores_diving_tackle_negative_modifier():
    game, (player, diver) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    player.extra_skills = [Skill.POGO]
    diver.extra_skills = [Skill.DIVING_TACKLE]
    with only_fixed_rolls(game, d6=[3]):
        run_proc(game, Season3Escape(game, player, Square(12, 5), jump=True))
        game.step(Action(ActionType.USE_SKILL, player=diver))
    assert player.state.up and player.position == Square(12, 5)
    assert not diver.state.up and diver.position == Square(10, 5)


def test_timmber_counts_only_open_standing_undistracted_teammates():
    game, (player, helper, distracted, marked, marker) = season3_turn(
        [(10, 5), (9, 5), (10, 4), (11, 5)], [(12, 5)], ball=(20, 12))
    player.extra_skills = [Skill.TIMMMBER]
    player.role = game.ruleset.get_role('Athel Forest Treeman', 'Halfling')
    player.state.up = False
    distracted.state.distracted = True
    assert game.get_stand_up_modifier(player) == 1
    with only_fixed_rolls(game, d6=[3]):
        run_proc(game, StandUp(game, player))
    assert player.state.up


def test_ball_and_chain_does_not_trigger_trickster():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.TRICKSTER]
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH]):
        run_proc(game, Block(game, attacker, defender, ball_and_chain=True))
    assert game.get_available_actions()[0].action_type == ActionType.SELECT_PUSH


def test_frenzy_second_blitz_block_spends_another_movement_point():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.FRENZY]
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH, BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLITZ, player=attacker))
        game.step(Action(ActionType.SELECT_PLAYER, player=defender))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(13, 5)))
    assert attacker.position == Square(12, 5)
    assert attacker.state.moves == 2


def test_frenzy_does_not_rush_for_cancelled_second_block():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.FRENZY]
    with only_fixed_rolls(game, d6=[1, 1], block_dice=[BBDieResult.DEFENDER_DOWN]):
        game.step(Action(ActionType.START_BLITZ, player=attacker))
        game.step(Action(ActionType.SELECT_PLAYER, player=defender))
        attacker.state.moves = attacker.get_ma() - 1
        game.set_available_actions()
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
    assert attacker.state.moves == attacker.get_ma()
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_GFI)


def test_frenzy_does_not_repeat_an_attacker_down_saved_by_steady_footing():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.FRENZY, Skill.STEADY_FOOTING]
    with only_fixed_rolls(game, d6=[6], block_dice=[BBDieResult.ATTACKER_DOWN]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_ATTACKER_DOWN))
    assert attacker.state.up and attacker.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_pro_can_be_used_for_distinct_rolls_during_same_activation():
    game, (player,) = season3_turn([(10, 5)], ball=(20, 12))
    player.extra_skills = [Skill.PRO]
    game.state.active_player = player
    with only_fixed_rolls(game, d6=[1, 3, 6, 1, 3, 6]):
        for _ in range(2):
            run_proc(game, GFI(game, player, player.position))
            game.step(Action(ActionType.USE_SKILL))
    assert player.state.up
    assert sum(r.outcome_type == OutcomeType.SUCCESSFUL_PRO for r in game.state.reports) == 2


def test_sprint_grants_three_rushes_and_sure_feet_only_one_reroll():
    game, (player,) = season3_turn([(10, 5)], ball=(20, 12))
    player.extra_skills = [Skill.SPRINT, Skill.SURE_FEET]
    player.state.moves = player.get_ma()
    assert player.num_gfis_left() == 3
    with only_fixed_rolls(game, d6=[1, 2]):
        run_proc(game, GFI(game, player, player.position))
    assert player.has_used_skill(Skill.SURE_FEET)
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        run_proc(game, GFI(game, player, player.position))
    assert not player.state.up


def test_sidestepping_player_chooses_empty_square():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.SIDE_STEP]
    with only_fixed_rolls(game):
        run_proc(game, Push(game, attacker, defender))
        choice = game.get_available_actions()[0]
        assert choice.team == defender.team
        game.step(Action(ActionType.PUSH, position=Square(10, 4)))
        game.step(Action(ActionType.FOLLOW_UP, position=attacker.position))
    assert defender.position == Square(10, 4)


def test_stand_firm_does_not_prevent_knockdown():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    defender.extra_skills = [Skill.STAND_FIRM]
    with only_fixed_rolls(game, d6=[1, 1]):
        run_proc(game, Push(game, attacker, defender, knock_down=True))
        game.step(Action(ActionType.USE_SKILL))
    assert defender.position == Square(11, 5) and not defender.state.up


@pytest.mark.parametrize('armour,injury,knocked_out', [([4, 4], [1, 2], False), ([5, 4], [4, 3], True)])
def test_dirty_player_applies_to_armour_or_injury_once(armour, injury, knocked_out):
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    attacker.extra_skills = [Skill.DIRTY_PLAYER, Skill.SNEAKY_GIT]
    defender.state.up = False
    with only_fixed_rolls(game, d6=armour + injury):
        run_proc(game, Foul(game, attacker, defender))
        if armour == [4, 4]:
            game.step(Action(ActionType.USE_SKILL))
            game.step(Action(ActionType.DONT_ARGUE_CALL))
    assert defender.state.knocked_out == knocked_out
    assert attacker.state.ejected == (armour == [4, 4])


def test_disturbing_presence_stacks_even_when_prone_and_distracted():
    game, (player, first, second) = season3_turn([(10, 5)], [(12, 5), (13, 5)], ball=(20, 12))
    first.extra_skills = second.extra_skills = [Skill.DISTURBING_PRESENCE]
    first.state.up = False
    second.state.distracted = True
    assert game.get_pass_modifiers(player, PassDistance.QUICK_PASS) == -2
    assert game.get_pass_modifiers(player, PassDistance.QUICK_PASS, ttm=True) == -2
    assert game.get_catch_modifiers(player, accurate=True) == -2


def test_nerves_of_steel_does_not_ignore_marking_when_throwing_a_teammate():
    game, (player, marker) = season3_turn([(10, 5)], [(9, 5)], ball=(20, 12))
    player.extra_skills = [Skill.NERVES_OF_STEEL, Skill.THROW_TEAM_MATE]
    assert game.get_pass_modifiers(player, PassDistance.QUICK_PASS) == 0
    assert game.get_pass_modifiers(player, PassDistance.QUICK_PASS, ttm=True) == -1


@pytest.mark.parametrize('die,failed', [(1, True), (2, False)])
def test_bonehead_activation_and_tackle_zones(die, failed):
    game, (player,) = season3_turn([(10, 5)], ball=(20, 12))
    player.extra_skills = [Skill.BONE_HEAD]
    with only_fixed_rolls(game, d6=[die]):
        game.step(Action(ActionType.START_MOVE, player=player))
    assert player.is_distracted() == failed
    assert player.has_tackle_zone() != failed
    assert player.state.used == failed


def test_rooted_player_can_block_and_loses_root_when_knocked_down():
    game, (player, defender) = season3_turn([(10, 5)], [(11, 5)], ball=(20, 12))
    player.extra_skills = [Skill.TAKE_ROOT]
    with only_fixed_rolls(game, d6=[1], block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLOCK, player=player))
        assert player.state.taken_root
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
    assert player.position == Square(10, 5)
    with only_fixed_rolls(game, d6=[1, 1]):
        run_proc(game, KnockDown(game, player))
    assert not player.state.taken_root


def test_boxed_in_side_step_has_normal_push_squares_and_block_probabilities():
    game, players = season3_turn([(10, 5), (10, 4), (10, 6), (11, 4)],
                                [(11, 5), (11, 6), (12, 4), (12, 5), (12, 6)])
    attacker, defender = players[0], players[4]
    defender.extra_skills = [Skill.SIDE_STEP]
    squares = game.get_push_squares(attacker.position, defender.position)
    assert {(s.x, s.y) for s in squares} == {(12, 4), (12, 5), (12, 6)}
    assert all(0 <= p <= 1 for p in game.get_block_probs(attacker, defender))
