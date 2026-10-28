"""Season 3 ball boundaries, scoring and supplied passing-chart scenarios."""
import pytest

from tests.util import *
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_season3_flow import run_proc


def reports(game, outcome):
    return [r for r in game.state.reports if r.outcome_type == outcome]


@pytest.mark.parametrize('origin,vectors', [
    ((10, 1), [(1, 1), (0, 1), (-1, 1)]),
    ((10, 15), [(-1, -1), (0, -1), (1, -1)]),
    ((1, 8), [(1, -1), (1, 0), (1, 1)]),
    ((26, 8), [(-1, 1), (-1, 0), (-1, -1)]),
])
@pytest.mark.parametrize('direction', range(1, 7))
def test_sideline_throw_in_uses_d6_and_counts_origin_as_first_square(origin, vectors, direction):
    game, _ = season3_turn([(20, 10)], ball=origin)
    dx, dy = vectors[(direction - 1) // 2]
    with only_fixed_rolls(game, d6=[direction, 1, 1], d8=[7]):
        run_proc(game, ThrowIn(game, game.get_ball(), Square(*origin)))
    landed = reports(game, OutcomeType.THROW_IN)[0]
    assert landed.position == Square(origin[0] + dx, origin[1] + dy)
    assert landed.rolls[0].dice[0].get_value() == direction
    assert game.get_ball().position == Square(origin[0] + dx, origin[1] + dy + 1)
    assert not game.get_ball().is_carried
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('origin,vectors', [
    ((1, 1), [(1, 0), (1, 1), (0, 1)]),
    ((26, 1), [(0, 1), (-1, 1), (-1, 0)]),
    ((26, 15), [(-1, 0), (-1, -1), (0, -1)]),
    ((1, 15), [(0, -1), (1, -1), (1, 0)]),
])
@pytest.mark.parametrize('direction', [1, 2, 3])
def test_corner_throw_in_template(origin, vectors, direction):
    game, _ = season3_turn([(20, 10)], ball=origin)
    dx, dy = vectors[direction - 1]
    # Bounce towards the pitch interior, including throws along the edge.
    bounce = 2 if origin[1] == 15 else 7
    with only_fixed_rolls(game, d3=[direction], d6=[1, 1], d8=[bounce]):
        run_proc(game, ThrowIn(game, game.get_ball(), Square(*origin)))
    landed = reports(game, OutcomeType.THROW_IN)[0]
    assert landed.position == Square(origin[0] + dx, origin[1] + dy)
    assert not game.get_ball().position.out_of_bounds


def test_repeated_throw_in_starts_at_last_in_bounds_square_and_flies_over_players():
    game, (overflown,) = season3_turn([(1, 2)], ball=(2, 1))
    with only_fixed_rolls(game, d6=[5, 6, 6, 3, 1, 1], d8=[7]):
        run_proc(game, ThrowIn(game, game.get_ball(), Square(2, 1)))
    assert reports(game, OutcomeType.THROW_IN_OUT_OF_BOUNDS)[0].position == Square(0, 3)
    assert reports(game, OutcomeType.THROW_IN)[0].position == Square(2, 2)
    assert game.get_ball().position == Square(2, 3)
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_CATCH)
    assert not game.has_ball(overflown)


@pytest.mark.parametrize('friendly', [False, True])
def test_pass_out_of_bounds_resolves_throw_in_catch_before_turnover(friendly):
    game, players = season3_turn([(3, 5), (10, 2)] if friendly else [(3, 5)],
                                [] if friendly else [(10, 2)], ball=(3, 5))
    passer, catcher = players
    with only_fixed_rolls(game, d6=[5, 3, 1, 1, 4], d8=[2, 2, 2]):
        pass_ball(game, passer, Square(10, 1))
    assert game.get_ball_carrier() == catcher
    assert reports(game, OutcomeType.SUCCESSFUL_CATCH)[0].rolls[0].modifiers == -1
    assert game.has_report_of_type(OutcomeType.TURNOVER) == (not friendly)
    if not friendly:
        outcomes = [r.outcome_type for r in game.state.reports]
        assert outcomes.index(OutcomeType.SUCCESSFUL_CATCH) < outcomes.index(OutcomeType.TURNOVER)


def test_throw_in_clears_old_carrier_even_when_ball_lands_under_ineligible_player():
    game, (player,) = season3_turn([(10, 2)], ball=(10, 2))
    player.state.distracted = True
    with only_fixed_rolls(game, d6=[3, 1, 1], d8=[7]):
        run_proc(game, ThrowIn(game, game.get_ball(), Square(10, 1)))
    assert not game.get_ball().is_carried
    assert game.get_ball_carrier() is None
    assert game.get_ball().position == Square(10, 3)
    assert len(reports(game, OutcomeType.FAILED_CATCH)) == 1


@pytest.mark.parametrize('standing,distracted,carried,expected', [
    (True, False, True, True), (True, True, True, True),
    (False, False, True, False), (True, False, False, False),
])
def test_touchdown_requires_standing_and_possession(standing, distracted, carried, expected):
    game, (player,) = season3_turn([(1, 5)], ball=(1, 5))
    player.state.up = standing
    player.state.distracted = distracted
    game.get_ball().is_carried = carried
    assert game.is_touchdown(player) == expected
    game.pitch_to_reserves(player)
    assert not game.is_touchdown(player)


@pytest.mark.parametrize('result,scores', [(BBDieResult.PUSH, True),
    (BBDieResult.DEFENDER_DOWN, False), (BBDieResult.DEFENDER_STUMBLES, False)])
def test_push_into_end_zone_only_scores_if_defender_remains_standing(result, scores):
    game, (attacker, defender) = season3_turn([(24, 5)], [(25, 5)], ball=(25, 5))
    team = defender.team
    with only_fixed_rolls(game, block_dice=[result]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action({BBDieResult.PUSH: ActionType.SELECT_PUSH,
                          BBDieResult.DEFENDER_DOWN: ActionType.SELECT_DEFENDER_DOWN,
                          BBDieResult.DEFENDER_STUMBLES: ActionType.SELECT_DEFENDER_STUMBLES}[result]))
        game.step(Action(ActionType.PUSH, position=Square(26, 5)))
    with only_fixed_rolls(game, d6=[] if scores else [1, 1], d8=[] if scores else [7]):
        game.step(Action(ActionType.FOLLOW_UP, position=attacker.position))
    assert team.state.score == int(scores)
    assert game.has_report_of_type(OutcomeType.TOUCHDOWN) == scores
    assert game.has_report_of_type(OutcomeType.TURN_SKIPPED) == scores
    if not scores:
        assert not defender.state.up
        assert not game.get_ball().is_carried


@pytest.mark.parametrize('carrying', [False, True])
def test_friendly_chain_surf_finishes_original_push_then_turns_over(carrying):
    game, (attacker, surfed, left, right, defender) = season3_turn(
        [(10, 3), (10, 1), (9, 1), (11, 1)], [(10, 2)],
        ball=(10, 1) if carrying else (20, 10))
    for player in (surfed, left, right):
        player.state.distracted = True  # No assists; a single block die.
    surfed.state.distracted = False if carrying else True
    dice = [BBDieResult.PUSH] * abs(game.num_block_dice(attacker, defender))
    with only_fixed_rolls(game, block_dice=dice):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=surfed.position))
    with only_fixed_rolls(game, d6=[1, 1] + ([3, 1, 1, 6] if carrying else [])):
        game.step(Action(ActionType.PUSH, position=Square(10, 0)))
    assert defender.position == Square(10, 1)  # Original push completed.
    assert isinstance(game.get_procedure(), FollowUp)
    with only_fixed_rolls(game):
        game.step(Action(ActionType.FOLLOW_UP, position=attacker.position))
    assert surfed.position is None
    assert surfed in game.get_reserves(surfed.team)
    assert len(reports(game, OutcomeType.TURNOVER)) == 1
    outcomes = [r.outcome_type for r in game.state.reports]
    assert outcomes.index(OutcomeType.KNOCKED_DOWN) < outcomes.index(OutcomeType.TURNOVER)
    if carrying:
        assert game.get_ball_carrier() == defender


@pytest.mark.parametrize('carrying', [False, True])
@pytest.mark.parametrize('follow', [False, True])
def test_opponent_surf_resolves_injury_and_throw_in_without_turnover(carrying, follow):
    game, (attacker, defender) = season3_turn([(10, 2)], [(10, 1)],
        ball=(10, 1) if carrying else (20, 10))
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(10, 0)))
    dice = [1, 1] + ([3, 1, 1] + ([] if follow else [4]) if carrying else [])
    with only_fixed_rolls(game, d6=dice, d8=[7] if carrying and follow else []):
        game.step(Action(ActionType.FOLLOW_UP, position=Square(10, 1) if follow else attacker.position))
    assert defender.position is None
    assert defender in game.get_reserves(defender.team)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
    if carrying:
        assert reports(game, OutcomeType.THROW_IN)[0].position == Square(10, 2)
        assert game.get_ball_carrier() == (None if follow else attacker)
        assert game.get_ball().position == Square(10, 3 if follow else 2)


@pytest.mark.parametrize('roll,success', [(1, False), (6, True)])
@pytest.mark.parametrize('risk', ['rush', 'dodge'])
def test_entering_end_zone_resolves_movement_test_before_scoring(risk, roll, success):
    game, (player, opponent) = season3_turn([(2, 5)], [(3, 5)], ball=(2, 5))
    # Move the opponent away for an unmarked Rush; leave them marking the
    # departure for a Dodge into an unmarked end-zone square.
    if risk == 'rush':
        game.move(opponent, Square(10, 10))
    game.step(Action(ActionType.START_MOVE, player=player))
    if risk == 'rush':
        player.state.moves = player.get_ma()
    with only_fixed_rolls(game, d6=[roll] + ([] if success else [1, 1]),
                          d8=[] if success else [7]):
        game.step(Action(ActionType.MOVE, position=Square(1, 5)))
    assert player.team.state.score == int(success)
    assert game.has_report_of_type(OutcomeType.TOUCHDOWN) == success


def test_forward_model_reverses_throw_in_and_catch():
    game, (player,) = season3_turn([(10, 2)], ball=(10, 2))
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[3, 1, 1, 4]):
        run_proc(game, ThrowIn(game, game.get_ball(), Square(10, 1)))
    after = game.state.to_json(ignore_clocks=True)
    assert game.get_ball_carrier() == player
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after


def test_forward_model_reverses_pending_chain_surf_turnover():
    game, (attacker, surfed, left, right, defender) = season3_turn(
        [(10, 3), (10, 1), (9, 1), (11, 1)], [(10, 2)], ball=(20, 10))
    for player in (surfed, left, right):
        player.state.up = False
    game.enable_forward_model()
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=surfed.position))
    root_push = next(p for p in game.state.stack.items if isinstance(p, Push))
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[1, 1]):
        game.step(Action(ActionType.PUSH, position=Square(10, 0)))
    after = game.state.to_json(ignore_clocks=True)
    assert root_push.crowd_turnover
    changes = game.revert(step)
    assert not root_push.crowd_turnover
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert root_push.crowd_turnover
    assert game.state.to_json(ignore_clocks=True) == after
    with only_fixed_rolls(game):
        game.step(Action(ActionType.FOLLOW_UP, position=attacker.position))
    assert len(reports(game, OutcomeType.TURNOVER)) == 1


@pytest.mark.parametrize('source', ['pass', 'handoff', 'bounce', 'throwin'])
def test_catching_in_end_zone_scores_immediately(source):
    positions = [(4 if source == 'pass' else 2, 5), (1, 5)]
    if source == 'throwin':
        positions = [(10, 10), (1, 2)]
    game, (player, scorer) = season3_turn(positions, ball=positions[0])
    if source == 'pass':
        with only_fixed_rolls(game, d6=[6, 3]):
            pass_ball(game, player, scorer.position)
    elif source == 'handoff':
        with only_fixed_rolls(game, d6=[3]):
            game.step(Action(ActionType.START_HANDOFF, player=player))
            game.step(Action(ActionType.HANDOFF, position=scorer.position))
    elif source == 'bounce':
        with only_fixed_rolls(game, d6=[4], d8=[4]):
            run_proc(game, Bounce(game, game.get_ball()))
    else:
        with only_fixed_rolls(game, d3=[3], d6=[1, 1, 4]):
            run_proc(game, ThrowIn(game, game.get_ball(), Square(1, 1)))
    assert scorer.team.state.score == 1
    assert len(reports(game, OutcomeType.TOUCHDOWN)) == 1
    assert len(reports(game, OutcomeType.DRIVE_ENDED)) == 1
    assert game.get_kicking_team() == scorer.team


def test_interception_in_end_zone_scores_and_skips_next_turn():
    game, (passer, target, scorer) = season3_turn([(22, 5), (26, 4)], [(26, 5)], ball=(22, 5))
    next_turn = scorer.team.state.turn + 1
    with only_fixed_rolls(game, d6=[6]):
        pass_ball(game, passer, target.position)
    assert isinstance(game.get_procedure(), Interception)
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.SELECT_PLAYER, player=scorer))
    assert scorer.team.state.score == 1
    assert scorer.team.state.turn == next_turn
    assert len(reports(game, OutcomeType.TURN_SKIPPED)) == 1
    assert len(reports(game, OutcomeType.TOUCHDOWN)) == 1
    assert game.get_receiving_team() == passer.team


def test_chain_push_can_score_for_non_active_teammate_without_skipping_own_turn():
    game, (attacker, scorer, left, right, defender) = season3_turn(
        [(4, 5), (2, 5), (2, 4), (2, 6)], [(3, 5)], ball=(2, 5))
    left.state.up = right.state.up = False
    dice = [BBDieResult.PUSH] * abs(game.num_block_dice(attacker, defender))
    with only_fixed_rolls(game, block_dice=dice):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=scorer.position))
        game.step(Action(ActionType.PUSH, position=Square(1, 5)))
    assert scorer.team.state.score == 1
    assert len(reports(game, OutcomeType.TOUCHDOWN)) == 1
    assert not game.has_report_of_type(OutcomeType.TURN_SKIPPED)


@pytest.mark.parametrize('status', ['prone', 'distracted'])
def test_ineligible_kick_catcher_bounces_to_touchback_instead_of_throw_in(status):
    game, (player,) = season3_turn([(14, 1)], ball=(14, 1))
    game.state.receiving_this_drive = player.team
    game.state.kicking_this_drive = game.get_opp_team(player.team)
    game.get_ball().is_carried = False
    player.state.up = status != 'prone'
    player.state.distracted = status == 'distracted'
    with only_fixed_rolls(game, d8=[2]):
        run_proc(game, Catch(game, player, game.get_ball(), kick=True))
    assert isinstance(game.get_procedure(), Touchback)
    assert game.has_report_of_type(OutcomeType.TOUCHBACK)
    assert not game.has_report_of_type(OutcomeType.THROW_IN)


@pytest.mark.parametrize('vertical', [False, True])
def test_ruler_overlaps_adjacent_row_as_in_supplied_interception_diagram(vertical):
    positions = [(5, 5), (5, 9)] if vertical else [(5, 5), (9, 5)]
    opponents = [(6, 7), (7, 7)] if vertical else [(7, 6), (7, 7)]
    game, (passer, catcher, interceptor, outside) = season3_turn(positions, opponents, ball=(5, 5))
    assert game.get_interceptors(passer.position, catcher.position, interceptor.team) == [interceptor]
    assert game.get_interceptors(catcher.position, passer.position, interceptor.team) == [interceptor]
    with only_fixed_rolls(game, d6=[6]):
        pass_ball(game, passer, catcher.position)
    assert isinstance(game.get_procedure(), Interception)
    assert game.actor == game.get_team_agent(interceptor.team)
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
    assert game.get_ball_carrier() == interceptor
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_ball(outside)


def test_diagonal_player_outside_ruler_in_supplied_example_cannot_intercept():
    game, (passer, catcher, interceptor) = season3_turn([(4, 3), (8, 11)], [(7, 5)])
    assert not game.get_interceptors(passer.position, catcher.position, interceptor.team)


@pytest.mark.parametrize('status', ['prone', 'stunned', 'distracted', 'ready'])
def test_interception_corridor_still_requires_standing_non_distracted_player(status):
    game, (passer, catcher, interceptor) = season3_turn([(5, 5), (9, 5)], [(7, 6)])
    interceptor.state.up = status not in ('prone', 'stunned')
    interceptor.state.stunned = status == 'stunned'
    interceptor.state.distracted = status == 'distracted'
    assert game.get_interceptors(passer.position, catcher.position, interceptor.team) == (
        [interceptor] if status == 'ready' else [])


@pytest.mark.parametrize('dy,quick,short,long,bomb', [
    (0, 3, 6, 10, 13), (1, 3, 6, 10, 13), (2, 2, 6, 10, 12),
    (3, 1, 6, 9, 12), (4, -1, 5, 9, 12), (5, -1, 4, 8, 11),
    (6, -1, 3, 8, 11), (7, -1, -1, 7, 10), (8, -1, -1, 6, 10),
    (9, -1, -1, 4, 9), (10, -1, -1, 2, 8), (11, -1, -1, -1, 6),
    (12, -1, -1, -1, 4), (13, -1, -1, -1, 1),
])
def test_supplied_passing_range_chart_in_all_directions(dy, quick, short, long, bomb):
    # Row boundaries transcribed from the chart on supplied PDF page 43.
    # Verify every cell, reflection and transpose, including range overflow.
    game, _ = season3_turn([(15, 8)])
    for dx in range(15):
        if dx == dy == 0:
            continue
        expected = next((distance for limit, distance in [
            (quick, PassDistance.QUICK_PASS), (short, PassDistance.SHORT_PASS),
            (long, PassDistance.LONG_PASS), (bomb, PassDistance.LONG_BOMB)] if dx <= limit),
            PassDistance.HAIL_MARY)
        for x, y in [(dx, dy), (dy, dx)]:
            for sx, sy in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
                assert game.get_pass_distance(Square(15, 8), Square(15 + sx*x, 8 + sy*y)) == expected
