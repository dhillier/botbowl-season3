"""Stalling, Forego Activation, recovery timing and selected Human skills."""
import pytest

from tests.game.test_season3 import season3_turn
from tests.util import *
from botbowl.core.pathfinding import python_pathfinding


def carrier_game(turn=4, rerolls=0):
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5), rerolls=rerolls)
    player.team.state.turn = turn
    assert game.get_opp_endzone_x(player.team) == 1
    return game, player


@pytest.mark.parametrize('turn,roll,hit', [(1, 1, True), (4, 3, False), (4, 4, True),
                                         (6, 6, True), (7, 6, False), (8, 6, False)])
@pytest.mark.parametrize('forego', [False, True])
def test_stalling_crowd_threshold_and_turnover(turn, roll, hit, forego):
    game, player = carrier_game(turn, rerolls=3)
    with only_fixed_rolls(game, d6=[roll] + ([1, 1] if hit else []), d8=[8] if hit else []):
        if forego:
            game.step(Action(ActionType.FOREGO_ACTIVATION, player=player))
        else:
            game.step(Action(ActionType.START_MOVE, player=player))
            game.step(Action(ActionType.END_PLAYER_TURN))
    expected = OutcomeType.CROWD_TAKES_ACTION if hit else OutcomeType.CROWD_MISSES
    report = next(r for r in game.state.reports if r.outcome_type == expected)
    assert report.rolls[0].target == turn
    assert report.rolls[0].roll_type == RollType.STALLING_ROLL
    assert not report.rolls[0].highest_succeed
    assert player.state.up != hit
    assert game.has_report_of_type(OutcomeType.TURNOVER) == hit
    assert player.team.state.rerolls == 3
    assert not isinstance(game.get_procedure(), Reroll)
    if hit:
        assert game.get_ball_carrier() is None
        assert game.has_report_of_type(OutcomeType.ARMOR_NOT_BROKEN)
    else:
        assert player.state.used
        assert game.get_ball_carrier() == player


def test_stalling_snapshot_is_not_recomputed_at_end_of_activation():
    game, player = carrier_game()
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        for x in (6, 7, 8):
            game.step(Action(ActionType.MOVE, position=Square(x, 5)))
        assert not game.can_score_without_dice(player)
        game.step(Action(ActionType.END_PLAYER_TURN))
    assert game.has_report_of_type(OutcomeType.CROWD_MISSES)


def test_moving_into_scoring_range_does_not_make_player_stalling():
    game, (player,) = season3_turn([(9, 5)], ball=(9, 5))
    with only_fixed_rolls(game):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(8, 5)))
        game.step(Action(ActionType.MOVE, position=Square(7, 5)))
        game.step(Action(ActionType.END_PLAYER_TURN))
    assert not game.has_report_of_type(OutcomeType.CROWD_MISSES)
    assert not game.has_report_of_type(OutcomeType.CROWD_TAKES_ACTION)


def test_ending_team_turn_with_unactivated_carrier_is_not_stalling():
    game, _ = carrier_game()
    with only_fixed_rolls(game):
        game.step(Action(ActionType.END_TURN))
    assert not game.has_report_of_type(OutcomeType.CROWD_TAKES_ACTION)
    assert not game.has_report_of_type(OutcomeType.CROWD_MISSES)


@pytest.mark.parametrize('action', [ActionType.START_PASS, ActionType.START_HANDOFF])
def test_declaring_pass_or_handoff_but_retaining_ball_still_stalls(action):
    game, player = carrier_game()
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(action, player=player))
        game.step(Action(ActionType.END_PLAYER_TURN))
    assert game.has_report_of_type(OutcomeType.CROWD_MISSES)


@pytest.mark.parametrize('handoff', [False, True])
def test_successful_pass_or_handoff_is_exempt(handoff):
    game, (player, receiver) = season3_turn([(5, 5), (6, 5)], ball=(5, 5))
    with only_fixed_rolls(game, d6=[3] if handoff else [4, 3]):
        game.step(Action(ActionType.START_HANDOFF if handoff else ActionType.START_PASS, player=player))
        game.step(Action(ActionType.HANDOFF if handoff else ActionType.PASS, position=receiver.position))
    assert game.get_ball_carrier() == receiver
    assert not any(r.outcome_type in (OutcomeType.CROWD_MISSES, OutcomeType.CROWD_TAKES_ACTION)
                   for r in game.state.reports)


def test_touchdown_does_not_trigger_stalling():
    game, player = carrier_game()
    game.step(Action(ActionType.START_MOVE, player=player))
    # The engine stops at the next setup decision after scoring.
    for x in (4, 3, 2):
        game.step(Action(ActionType.MOVE, position=Square(x, 5)))
    with only_fixed_rolls(game):
        game.step(Action(ActionType.MOVE, position=Square(1, 5)))
    assert player.team.state.score == 1
    assert not game.has_report_of_type(OutcomeType.CROWD_TAKES_ACTION)
    assert not game.has_report_of_type(OutcomeType.CROWD_MISSES)


@pytest.mark.parametrize('case,expected', [('open', True), ('rush', False), ('marked', False),
    ('prone', False), ('prone-near', True), ('low-ma', False), ('bone-head', False),
    ('loose', False), ('blocked', False), ('distracted-marker', True), ('marked-endzone', True)])
def test_stalling_eligibility_uses_dice_free_route(case, expected):
    game, player = carrier_game()
    if case == 'rush':
        game.move(player, Square(8, 5))
    elif case in ('marked', 'distracted-marker'):
        opponent = game.get_opp_team(player.team).players[0]
        game.put(opponent, Square(5, 6))
        opponent.state.distracted = case == 'distracted-marker'
    elif case in ('prone', 'prone-near', 'low-ma'):
        player.state.up = False
        if case == 'prone-near':
            game.move(player, Square(4, 5))
        if case == 'low-ma':
            player.role.ma = 2
            game.move(player, Square(2, 5))
    elif case == 'bone-head':
        player.extra_skills = [Skill.BONE_HEAD]
    elif case == 'loose':
        game.get_ball().is_carried = False
    elif case == 'blocked':
        for y, blocker in zip(range(1, game.arena.height - 1),
                              [p for t in game.state.teams for p in t.players if p != player]):
            game.put(blocker, Square(3, y))
    elif case == 'marked-endzone':
        opponent = game.get_opp_team(player.team).players[0]
        game.put(opponent, Square(1, 6))
        game.move(player, Square(2, 4))  # Can enter (1, 4) then score; no Dodge away.
    assert game.can_score_without_dice(player) == expected


def test_forego_skips_activation_status_clear_traits_and_allowances():
    game, (player,) = season3_turn([(15, 5)])
    player.state.distracted = True
    player.extra_skills = [Skill.BONE_HEAD]
    turn = game.current_turn()
    with only_fixed_rolls(game):
        game.step(Action(ActionType.FOREGO_ACTIVATION, player=player))
    assert player.state.used and player.state.distracted
    assert game.get_active_player() is None
    assert turn.blitz_available and turn.pass_available and turn.handoff_available
    assert turn.secure_ball_available
    assert all(player not in a.players for a in game.get_available_actions())
    assert not game.has_report_of_type(OutcomeType.MOVE_ACTION_STARTED)


def start_fresh_turn(game, team, number=2):
    game.purge_stack_until(Turn, inclusive=True)
    turn = Turn(game, team, 1, number)
    turn.start()
    turn.started = True
    game.set_available_actions()
    return turn


def test_stunned_recovery_waits_for_end_and_excludes_newly_stunned_players():
    game, (old, new) = season3_turn([(15, 5), (15, 7)])
    old.state.up = False
    old.state.stunned = True
    start_fresh_turn(game, old.team)
    assert old.state.stunned
    assert all(old not in a.players for a in game.get_available_actions())
    new.state.up = False
    new.state.stunned = True
    with only_fixed_rolls(game):
        game.step(Action(ActionType.END_TURN))
    assert not old.state.stunned and not old.state.up
    assert new.state.stunned
    # The opposing turn cannot recover either player.
    with only_fixed_rolls(game):
        game.step(Action(ActionType.END_TURN))
    assert new.state.stunned
    assert all(new not in a.players for a in game.get_available_actions())
    with only_fixed_rolls(game):
        game.step(Action(ActionType.END_TURN))
    assert not new.state.stunned and not new.state.up


@pytest.mark.parametrize('skill', [Skill.BLOCK, Skill.DODGE, Skill.TACKLE, Skill.CATCH, Skill.PASS, Skill.SURE_HANDS])
@pytest.mark.parametrize('status', ['distracted', 'hypnotized', 'bone_headed', 'really_stupid', 'prone', 'stunned'])
def test_selected_active_skills_unavailable_when_down_or_distracted(skill, status):
    _, (player,) = season3_turn([(15, 5)])
    player.extra_skills = [skill]
    assert player.can_use_skill(skill)
    if status in ('prone', 'stunned'):
        player.state.up = False
        player.state.stunned = status == 'stunned'
    else:
        setattr(player.state, status, True)
    assert player.has_skill(skill)
    assert not player.has_usable_skill(skill)
    assert not player.can_use_skill(skill)


@pytest.mark.parametrize('status', ['active', 'distracted', 'prone'])
@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_tackle_probability_agrees_across_engine_and_pathfinders(status, implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, (player, tackler, marker) = season3_turn([(10, 5)], [(10, 6), (9, 6)], ball=(20, 12))
    player.extra_skills = [Skill.DODGE]
    tackler.extra_skills = [Skill.TACKLE]
    tackler.state.distracted = status == 'distracted'
    tackler.state.up = status != 'prone'
    destination = Square(11, 4)
    probability = 4 / 6 if status == 'active' else 8 / 9
    assert game.get_dodge_prob(player, destination) == pytest.approx(probability)
    path = pf.Pathfinder(game, player).get_path(destination)
    assert path.prob == pytest.approx(probability)
    with only_fixed_rolls(game, d6=[1, 3] if status != 'active' else [1, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=destination))
    assert player.state.up == (status != 'active')


def test_dodge_block_protection_is_available_even_after_dodge_reroll_used():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)])
    defender.extra_skills = [Skill.DODGE]
    defender.use_skill(Skill.DODGE)
    assert not defender.can_use_skill(Skill.DODGE)
    assert defender.has_usable_skill(Skill.DODGE)
    with only_fixed_rolls(game, block_dice=[BBDieResult.DEFENDER_STUMBLES]):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_DEFENDER_STUMBLES))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=Square(10, 5)))
    assert defender.state.up


def test_search_reverses_forego_and_crowd_knockdown():
    game, player = carrier_game(turn=1)
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[1, 1, 1], d8=[8]):
        game.step(Action(ActionType.FOREGO_ACTIVATION, player=player))
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after


@pytest.mark.parametrize('distracted', [False, True])
def test_block_cannot_use_distracted_defenders_block(distracted):
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)])
    attacker.extra_skills = defender.extra_skills = [Skill.BLOCK]
    defender.state.distracted = distracted
    assert game.get_block_probs(attacker, defender)[:2] == pytest.approx((1 / 6, 3 / 6 if distracted else 2 / 6))
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN], d6=[1, 1] if distracted else []):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
    assert attacker.state.up
    assert defender.state.up != distracted


@pytest.mark.parametrize('distracted', [False, True])
def test_stumble_cannot_use_distracted_defenders_dodge(distracted):
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)])
    defender.extra_skills = [Skill.DODGE]
    defender.state.distracted = distracted
    with only_fixed_rolls(game, block_dice=[BBDieResult.DEFENDER_STUMBLES], d6=[1, 1] if distracted else []):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_DEFENDER_STUMBLES))
        game.step(Action(ActionType.PUSH, position=Square(12, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=Square(10, 5)))
    assert defender.state.up != distracted


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_tackle_prevents_use_without_consuming_later_dodge_reroll(implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    # Two separate marked departures in a forced corridor. The first has Tackle,
    # the second must still have the Dodge re-roll available.
    game, (player, tackler, marker) = season3_turn([(10, 1)], [(10, 2), (12, 2)], ball=(20, 12))
    player.extra_skills = [Skill.DODGE]
    tackler.extra_skills = [Skill.TACKLE]
    blockers = [p for p in player.team.players if p != player and p.position is None]
    for x, blocker in zip(range(11, 16), blockers):
        # Keep the real opposing marker at (12, 2); overwriting its board cell
        # leaves a phantom player.position and makes board/list queries disagree.
        if game.get_player_at(Square(x, 2)) is None:
            game.put(blocker, Square(x, 2))
    path = pf.Pathfinder(game, player, directly_to_adjacent=True).get_path(Square(14, 1))
    # Depart (10,1), (11,1) under Tackle: 5+ then 4+. Depart (12,1),
    # (13,1) without Tackle: 4+ then 3+, sharing the remaining Dodge re-roll.
    assert list(path.rolls) == [[5], [4], [4], [3]]
    assert path.prob == pytest.approx((2 / 6) * (3 / 6) * (3 / 6 * 4 / 6 + 3 / 6 * 3 / 6 * 4 / 6 + 3 / 6 * 2 / 6 * 4 / 6))


def test_activation_clears_distracted_and_cannot_be_undone_to_remove_status_for_free():
    game, (player,) = season3_turn([(15, 5)])
    player.state.distracted = True
    with only_fixed_rolls(game):
        game.step(Action(ActionType.START_MOVE, player=player))
    assert not player.state.distracted
    assert ActionType.UNDO not in [a.action_type for a in game.get_available_actions()]


def test_web_api_forego_uses_selected_player_and_serializes_crowd_result(monkeypatch):
    from botbowl.web import server
    from botbowl.web.host import InMemoryHost
    game, player = carrier_game()
    game.game_id = 'stalling-test'
    host = InMemoryHost()
    host.add_game(game)
    monkeypatch.setattr(server.api, 'host', host)
    with only_fixed_rolls(game, d6=[1]):
        response = server.app.test_client().post('/games/stalling-test/act', json={
            'action': {'action_type': 'FOREGO_ACTIVATION', 'player_id': player.player_id}})
    result = json.loads(response.data)
    serialized = result['state']['home_team']['players_by_id'][player.player_id]
    assert serialized['state']['used']
    assert game.has_report_of_type(OutcomeType.CROWD_MISSES)


def test_search_reverses_end_turn_stunned_recovery():
    game, (player,) = season3_turn([(15, 5)])
    player.state.up = False
    player.state.stunned = True
    turn = start_fresh_turn(game, player.team)
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game):
        game.step(Action(ActionType.END_TURN))
    assert not player.state.stunned
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert player.state.stunned and player in turn.stunned_at_start
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after
