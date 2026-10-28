"""Cross-procedure acceptance cases for fixed-Human standalone matches."""
import pytest

from tests.util import *
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_secure_ball import start_secure
from tests.game.test_season3_flow import full_setup_game, run_proc


def outcomes(game):
    return [r.outcome_type for r in game.state.reports]


def test_blitz_clears_distracted_before_target_declaration():
    game, (player, opponent) = season3_turn([(5, 5)], [(6, 5)])
    player.state.distracted = True
    game.set_available_actions()
    game.step(Action(ActionType.START_BLITZ, player=player))
    assert not player.is_distracted()
    assert isinstance(game.get_procedure(), BlitzDeclaration)
    game.step(Action(ActionType.SELECT_PLAYER, player=opponent))
    assert not player.is_distracted()


@pytest.mark.parametrize('action', ['move', 'jump', 'blitz', 'secure'])
@pytest.mark.parametrize('roll,success', [(2, False), (3, True)])
def test_blizzard_rush_resolves_before_later_action_tests(action, roll, success):
    friendly = [(5, 5), (6, 5)] if action == 'jump' else [(5, 5)]
    opponents = [(6, 5)] if action == 'blitz' else []
    ball = (6, 5) if action == 'secure' else (20, 10)
    game, players = season3_turn(friendly, opponents, ball)
    player = players[0]
    game.state.weather = WeatherType.BLIZZARD
    if action == 'jump':
        players[1].state.up = False
        player.state.moves = player.get_ma() - 1  # Two-square jump needs one Rush.
    else:
        player.state.moves = player.get_ma()
    start = {'move': ActionType.START_MOVE, 'jump': ActionType.START_MOVE,
             'blitz': ActionType.START_BLITZ, 'secure': ActionType.START_SECURE_BALL}[action]
    game.step(Action(start, player=player))
    if action == 'blitz':
        game.step(Action(ActionType.SELECT_PLAYER, player=players[-1]))
    later_rolls = [3] if success and action in ('jump', 'secure') else []
    with only_fixed_rolls(game, d6=[roll] + later_rolls + ([] if success else [1, 1]),
                          d8=[5] if not success and action == 'secure' else [],
                          block_dice=[BBDieResult.PUSH] if success and action == 'blitz' else []):
        step = {'move': ActionType.MOVE, 'jump': ActionType.JUMP,
                'blitz': ActionType.BLOCK, 'secure': ActionType.MOVE}[action]
        game.step(Action(step, position=Square(7 if action == 'jump' else 6, 5)))
    assert game.has_report_of_type(OutcomeType.TURNOVER) != success
    assert game.has_report_of_type(OutcomeType.SUCCESSFUL_GFI) == success
    later = {'jump': OutcomeType.SUCCESSFUL_JUMP, 'secure': OutcomeType.SUCCESSFUL_PICKUP,
             'blitz': OutcomeType.BLOCK_ROLL}.get(action)
    if later:
        assert game.has_report_of_type(later) == success
        if success:
            assert outcomes(game).index(OutcomeType.SUCCESSFUL_GFI) < outcomes(game).index(later)
    if action in ('jump', 'blitz') and not success:
        assert player.position == Square(5, 5)


@pytest.mark.parametrize('reroll', [False, True])
def test_rain_secure_two_fails_and_team_reroll_three_succeeds(reroll):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5), rerolls=int(reroll))
    player.extra_skills = [Skill.SURE_HANDS]
    game.state.weather = WeatherType.POURING_RAIN
    with only_fixed_rolls(game, d6=[2] + ([3] if reroll else []), d8=[] if reroll else [5]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        if reroll:
            assert isinstance(game.get_procedure(), Reroll)
            game.step(Action(ActionType.USE_REROLL))
    assert game.has_report_of_type(OutcomeType.FAILED_PICKUP)
    assert not game.has_report_of_type(OutcomeType.SKILL_USED)
    assert game.has_report_of_type(OutcomeType.TURNOVER) != reroll
    assert game.has_ball(player) == reroll


def test_secure_exclusion_is_not_rechecked_after_declaration_and_marking_is_not_an_ag_test():
    game, (player, opponent) = season3_turn([(5, 5)], [(10, 5)], ball=(6, 5))
    start_secure(game, player)
    game.move(opponent, Square(7, 5))  # Simulate an intervening reaction after declaration.
    with only_fixed_rolls(game, d6=[2]):
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.has_ball(player)
    pickup = next(r for r in game.state.reports if r.outcome_type == OutcomeType.SUCCESSFUL_PICKUP)
    assert pickup.rolls[0].modifiers == 0


@pytest.mark.parametrize('scoring_catcher', [False, True])
def test_both_down_players_are_prone_before_bounce_and_both_injuries_resolve(scoring_catcher):
    positions = [(1, 5), (1, 6)] if scoring_catcher else [(1, 5)]
    game, players = season3_turn(positions, [(2, 5)], ball=(2, 5))
    attacker, defender = players[0], players[-1]
    if scoring_catcher:
        players[1].state.distracted = True  # Suppress assist until after block dice.
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
    if scoring_catcher:
        players[1].state.distracted = False
    with only_fixed_rolls(game, d6=[1, 1] + ([4] if scoring_catcher else []) + [1, 1],
                          d8=[6] if scoring_catcher else [4, 5, 7]):
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
    knocked = [r.player for r in game.state.reports if r.outcome_type == OutcomeType.KNOCKED_DOWN]
    armour = [r.player for r in game.state.reports if r.outcome_type == OutcomeType.ARMOR_NOT_BROKEN]
    assert set(knocked) == {attacker, defender}
    assert set(armour) == {attacker, defender}
    assert not any(r.player == attacker for r in game.state.reports if r.outcome_type == OutcomeType.SUCCESSFUL_CATCH)
    assert attacker.team.state.score == int(scoring_catcher)
    if scoring_catcher:
        sequence = outcomes(game)
        assert max(i for i, o in enumerate(sequence) if o == OutcomeType.ARMOR_NOT_BROKEN) < sequence.index(OutcomeType.TOUCHDOWN)


@pytest.mark.parametrize('crowd', [False, True])
@pytest.mark.parametrize('injury', ['armour_holds', 'ko', 'casualty', 'apothecary'])
def test_follow_up_touchdown_resolves_defender_injury_and_treatment_first(crowd, injury):
    if crowd:
        game, (attacker, defender) = season3_turn([(2, 1)], [(1, 1)], ball=(2, 1))
        destination = Square(0, 1)
    else:
        # Home attacks toward x=1. Follow into the end zone; defender moves
        # sideways inside it and must receive the selected POW's injury check.
        game, (attacker, defender) = season3_turn([(2, 5)], [(1, 5)], ball=(2, 5))
        destination = Square(1, 4)
        # Approach diagonally so (1,4) is a legal in-pitch push destination.
        game.move(attacker, Square(2, 6))
    if injury == 'apothecary':
        defender.team.state.apothecaries = 1
    die = BBDieResult.PUSH if crowd else BBDieResult.DEFENDER_DOWN
    with only_fixed_rolls(game, block_dice=[die]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH if crowd else ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=destination))
    assert not game.has_report_of_type(OutcomeType.KNOCKED_DOWN)
    assert not game.has_report_of_type(OutcomeType.TOUCHDOWN)
    # Crowd bypasses armour. A low injury becomes stunned/reserves, then the
    # end-of-drive KO recovery must run only after scoring.
    dice = ([] if crowd else ([1, 1] if injury == 'armour_holds' else [6, 6]))
    if crowd or injury != 'armour_holds':
        dice += [6, 6] if injury == 'casualty' else [4, 4] if injury in ('ko', 'apothecary') else [1, 1]
    if injury == 'ko':
        dice += [1]  # Recovery at drive end, not before the touchdown.
    with only_fixed_rolls(game, d6=dice, d16=[1] if injury == 'casualty' else []):
        game.step(Action(ActionType.FOLLOW_UP, position=Square(1, 1) if crowd else Square(1, 5)))
        if injury == 'apothecary':
            assert isinstance(game.get_procedure(), Apothecary)
            assert not game.has_report_of_type(OutcomeType.TOUCHDOWN)
            assert game.actor == game.get_team_agent(defender.team)
            game.step(Action(ActionType.USE_APOTHECARY))
    assert attacker.team.state.score == 1
    sequence = outcomes(game)
    assert sequence.index(OutcomeType.FOLLOW_UP) < sequence.index(OutcomeType.KNOCKED_DOWN)
    assert sequence.index(OutcomeType.KNOCKED_DOWN) < sequence.index(OutcomeType.TOUCHDOWN)
    if injury == 'casualty':
        assert defender in game.get_casualties(defender.team)
    if injury == 'ko':
        assert defender in game.get_knocked_out(defender.team)
        assert sequence.index(OutcomeType.KNOCKED_OUT) < sequence.index(OutcomeType.TOUCHDOWN)
        assert sequence.index(OutcomeType.TOUCHDOWN) < sequence.index(OutcomeType.PLAYER_NOT_READY)
    assert sequence.count(OutcomeType.TOUCHDOWN) == 1


@pytest.mark.parametrize('distance,modifier,target', [
    (3, 0, 4), (6, -1, 4), (10, -2, 4), (11, -3, 4)])
@pytest.mark.parametrize('weather', [WeatherType.NICE, WeatherType.VERY_SUNNY])
@pytest.mark.parametrize('marked', [False, True])
@pytest.mark.parametrize('natural', range(1, 7))
def test_project_fumble_ruling_across_ranges_sun_marking_and_natural_results(distance, modifier, target,
                                                                          weather, marked, natural):
    game, players = season3_turn([(3, 5)], [(2, 5)] if marked else [], ball=(3, 5))
    passer = players[0]
    game.state.weather = weather
    total_modifier = modifier - int(marked) - int(weather == WeatherType.VERY_SUNNY)
    accurate = natural == 6 or (natural != 1 and natural + total_modifier >= target)
    fumble = not accurate and (natural == 1 or natural + total_modifier <= 1)
    result = OutcomeType.ACCURATE_PASS if accurate else OutcomeType.FUMBLE if fumble else OutcomeType.INACCURATE_PASS
    with only_fixed_rolls(game, d6=[natural], d8=[7] if accurate or fumble else [7, 7, 7, 7]):
        pass_ball(game, passer, Square(3 + distance, 5))
    report = next(r for r in game.state.reports if r.outcome_type == result)
    assert report.rolls[0].modifiers == total_modifier
    assert not game.get_ball().is_carried
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.INTERCEPTION)


def test_interceptor_choices_exclude_endpoints_ineligible_players_and_reserves_in_roster_order():
    game, (passer, catcher, first, second, endpoint_row, no_hands, distracted) = season3_turn(
        [(5, 5), (9, 5)], [(7, 6), (7, 4), (5, 6), (6, 5), (8, 5)])
    no_hands.extra_skills = [Skill.NO_HANDS]
    distracted.state.distracted = True
    expected = [p for p in first.team.players if p in (first, second)]
    assert game.get_interceptors(passer.position, catcher.position, first.team) == expected
    assert game.get_interceptors(catcher.position, passer.position, first.team) == expected
    assert endpoint_row not in expected
    game.pitch_to_reserves(first)
    assert game.get_interceptors(passer.position, catcher.position, second.team) == [second]


def test_forward_model_reverses_scoring_candidate_pending_defensive_treatment():
    game, (attacker, defender) = season3_turn([(2, 6)], [(1, 5)], ball=(2, 6))
    defender.team.state.apothecaries = 1
    game.enable_forward_model()
    with only_fixed_rolls(game, block_dice=[BBDieResult.DEFENDER_DOWN]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(1, 4)))
    boundary = next(p for p in game.state.stack.items if isinstance(p, BlockResolution))
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[6, 6, 4, 4]):
        game.step(Action(ActionType.FOLLOW_UP, position=Square(1, 5)))
    assert isinstance(game.get_procedure(), Apothecary)
    assert list(boundary.scorers) == [attacker]
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert not boundary.scorers
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert list(boundary.scorers) == [attacker]
    assert game.state.to_json(ignore_clocks=True) == after
    with only_fixed_rolls(game):
        game.step(Action(ActionType.USE_APOTHECARY))
    assert attacker.team.state.score == 1


@pytest.mark.parametrize('skill', [False, True])
def test_modified_negative_fumble_reroll_resolves_before_flight_and_cannot_be_rerolled_twice(skill):
    game, (passer, target, interceptor) = season3_turn([(3, 5), (14, 5)], [(7, 5)],
                                                     ball=(3, 5), rerolls=3)
    if skill:
        passer.extra_skills = [Skill.PASS]
    with only_fixed_rolls(game, d6=[2, 6]):
        pass_ball(game, passer, target.position)
        if not skill:
            assert isinstance(game.get_procedure(), Reroll)
            game.step(Action(ActionType.USE_REROLL))
    assert isinstance(game.get_procedure(), Interception)
    assert outcomes(game).index(OutcomeType.FUMBLE) < outcomes(game).index(OutcomeType.ACCURATE_PASS)
    assert passer.team.state.rerolls == (3 if skill else 2)
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.SELECT_NONE))
    assert game.has_ball(target)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('event', ['solid_defence', 'quick_snap', 'charge'])
def test_search_reverses_selection_when_kickoff_procedure_was_created_after_search_enabled(event):
    game = full_setup_game()
    game.enable_forward_model()
    with only_fixed_rolls(game, d3=[1]):
        if event == 'solid_defence':
            run_proc(game, SolidDefence(game))
        else:
            run_proc(game, Turn(game, game.get_kicking_team(), 1, 1,
                                quick_snap=event == 'quick_snap', blitz=event == 'charge'))
    proc = game.get_procedure()
    assert isinstance(proc, (SolidDefence, KickoffSelection))
    selected = proc.eligible[0]
    step = game.get_step()
    before = game.state.to_json(ignore_clocks=True)
    game.step(Action(ActionType.SELECT_PLAYER, player=selected))
    assert proc.selected == [selected]
    changes = game.revert(step)
    assert not proc.selected
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert proc.selected == [selected]


def test_search_reverses_drive_end_recovery_bookkeeping_created_during_search():
    game, (player,) = season3_turn([(5, 5)])
    game.pitch_to_kod(player)
    game.enable_forward_model()
    proc = PreKickoff(game, player.team)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[4]):
        run_proc(game, proc)
    assert player in proc.checked
    changes = game.revert(step)
    assert not proc.checked
    assert player in game.get_knocked_out(player.team)
    game.forward(changes)
    assert player in proc.checked
    assert player in game.get_reserves(player.team)
