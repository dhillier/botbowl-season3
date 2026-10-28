"""Controlled scenarios for the fixed-roster Season 3 migration preview."""
from collections import Counter

import pytest

from tests.util import *
from botbowl.core.pathfinding import python_pathfinding


def season3_turn(positions, opponents=None, ball=None, rerolls=0):
    # Reuse an upstream fixture only to skip setup/kick-off. No old profiles
    # remain in the scenario; each test gets a fresh Season 3 ruleset.
    game, players = get_custom_game_turn(positions, opponents, ball)
    game.ruleset = load_rule_set('BB2025')
    game.config.ruleset = 'BB2025'
    game.current_turn().secure_ball_available = True
    game.state.drive_active = True
    for proc in list(game.state.stack.items):
        if isinstance(proc, Turn) and proc != game.current_turn():
            game.state.stack.items.remove(proc)  # Discard a pre-scheduled legacy round partner.
        if isinstance(proc, Half) and proc.kicked_off:
            proc.next_team = game.get_opp_team(game.state.current_team)
    for team in game.state.teams:
        team.state.rerolls = rerolls
        team.state.reroll_used = False
        for player in team.players:
            player.role = game.ruleset.get_role(player.role.name, 'Human')
            if player.position is not None and player in game.get_reserves(team):
                game.get_reserves(team).remove(player)
    game.set_available_actions()
    return game, players


def pass_ball(game, passer, target):
    game.step(Action(ActionType.START_PASS, player=passer))
    game.step(Action(ActionType.PASS, position=target))


def test_fixed_human_profiles_and_serialization():
    config = load_config('season3-preview')
    rules = load_rule_set(config.ruleset)
    team = load_team_by_filename('human', rules)
    assert Counter(p.role.name for p in team.players) == {
        'Blitzer': 2, 'Thrower': 1, 'Catcher': 2, 'Lineman': 7}
    profiles = {
        'Lineman': (6, 3, 3, 4, 9, set()),
        'Thrower': (6, 3, 3, 3, 9, {Skill.PASS, Skill.SURE_HANDS}),
        'Catcher': (8, 3, 3, 4, 8, {Skill.CATCH, Skill.DODGE}),
        'Blitzer': (7, 3, 3, 4, 9, {Skill.BLOCK, Skill.TACKLE})}
    for player in team.players:
        assert (player.get_ma(), player.get_st(), player.get_ag(), player.get_pa(),
                player.get_av(), set(player.role.skills)) == profiles[player.role.name]
        data = player.to_json()
        assert data['pa'] == player.get_pa()
        assert data['target_characteristics'] is True
    game, _ = season3_turn([(5, 5)])
    assert game.to_json()['rules_status'] == 'migration-preview-incomplete'


def test_passing_uses_pa_independently_of_ag():
    game, (passer, catcher) = season3_turn([(5, 5), (8, 5)], ball=(5, 5))
    passer.extra_ag = 1  # AG2+; PA remains 4+.
    assert passer.get_ag_target() == 2
    assert passer.get_pass_target() == 4
    assert game.get_pass_prob(passer, game.get_ball(), catcher.position) == pytest.approx(3 / 6)
    assert game.get_catch_prob(catcher, accurate=True) == pytest.approx(4 / 6)
    assert game.get_dodge_prob(passer, Square(6, 5)) == 1.0  # unmarked
    with only_fixed_rolls(game, d6=[4, 3]):
        pass_ball(game, passer, catcher.position)
    assert game.get_ball_carrier() == catcher
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('distance,modifier', [
    (PassDistance.QUICK_PASS, 0), (PassDistance.SHORT_PASS, -1),
    (PassDistance.LONG_PASS, -2), (PassDistance.LONG_BOMB, -3)])
def test_pass_range_modifiers(distance, modifier):
    game, (player,) = season3_turn([(5, 5)])
    assert game.get_pass_modifiers(player, distance) == modifier


@pytest.mark.parametrize('roll,expected', [
    (1, OutcomeType.FUMBLE), (2, OutcomeType.INACCURATE_PASS),
    (3, OutcomeType.INACCURATE_PASS), (4, OutcomeType.FUMBLE),
    (5, OutcomeType.INACCURATE_PASS), (6, OutcomeType.ACCURATE_PASS)])
def test_long_bomb_natural_and_modified_results(roll, expected):
    game, (passer, catcher) = season3_turn([(3, 5), (14, 5)], ball=(3, 5))
    # Modifier -3: natural 2 and 3 produce -1 and 0. The supplied revision
    # explicitly calls a modified 1 a fumble, not every result below 2.
    d6 = [roll, 3] if expected == OutcomeType.ACCURATE_PASS else [roll]
    d8 = [] if expected == OutcomeType.ACCURATE_PASS else (
        [7] if expected == OutcomeType.FUMBLE else [7, 7, 7, 7])
    with only_fixed_rolls(game, d6=d6, d8=d8):
        pass_ball(game, passer, catcher.position)
    assert game.has_report_of_type(expected)
    if expected == OutcomeType.ACCURATE_PASS:
        assert game.get_ball_carrier() == catcher
    else:
        assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_accuracy_precedes_interception_and_catch():
    game, (passer, catcher, interceptor) = season3_turn(
        [(3, 5), (10, 5)], [(6, 5)], (3, 5))
    with only_fixed_rolls(game, d6=[6]):
        pass_ball(game, passer, catcher.position)
    assert game.has_report_of_type(OutcomeType.ACCURATE_PASS)
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_CATCH)
    assert isinstance(game.get_procedure(), Interception)
    assert game.get_available_actions()[0].rolls == [[6]]
    with only_fixed_rolls(game, d6=[5, 3]):  # interception 6+, then catch 3+
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
    assert game.get_ball_carrier() == catcher
    assert game.has_report_of_type(OutcomeType.FAILED_INTERCEPTION)


def test_fumble_has_no_interception_decision():
    game, (passer, catcher, _) = season3_turn(
        [(3, 5), (10, 5)], [(6, 5)], (3, 5))
    with only_fixed_rolls(game, d6=[1], d8=[7]):
        pass_ball(game, passer, catcher.position)
    assert game.has_report_of_type(OutcomeType.FUMBLE)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not isinstance(game.get_procedure(), Interception)


def test_scatter_precedes_interception_along_actual_flight():
    game, (passer, catcher, interceptor) = season3_turn(
        [(3, 5), (10, 5)], [(7, 7)], (3, 5))
    assert interceptor not in game.get_interceptors(passer.position, catcher.position, interceptor.team)
    with only_fixed_rolls(game, d6=[5], d8=[7, 7, 7]):
        pass_ball(game, passer, catcher.position)
    assert game.get_ball_position() == Square(10, 8)
    assert isinstance(game.get_procedure(), Interception)
    assert interceptor in game.get_procedure().interceptors
    assert game.get_available_actions()[0].rolls == [[5]]
    with only_fixed_rolls(game, d6=[5]):
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
    assert game.get_ball_carrier() == interceptor
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_pass_skill_reroll_happens_before_interception():
    game, (passer, catcher, interceptor) = season3_turn(
        [(3, 5), (10, 5)], [(6, 5)], (3, 5))
    passer.extra_skills = [Skill.PASS]
    with only_fixed_rolls(game, d6=[1, 6]):
        pass_ball(game, passer, catcher.position)
    assert isinstance(game.get_procedure(), Interception)
    assert game.has_report_of_type(OutcomeType.FUMBLE)
    assert game.has_report_of_type(OutcomeType.SKILL_USED)
    assert game.has_report_of_type(OutcomeType.ACCURATE_PASS)
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.SELECT_NONE))
    assert game.get_ball_carrier() == catcher


def test_catch_skill_does_not_reroll_interception():
    game, (passer, catcher, interceptor) = season3_turn(
        [(3, 5), (10, 5)], [(6, 5)], (3, 5), rerolls=3)
    interceptor.extra_skills = [Skill.CATCH]
    with only_fixed_rolls(game, d6=[6, 5, 3]):
        pass_ball(game, passer, catcher.position)
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
    assert game.get_ball_carrier() == catcher
    assert not game.has_report_of_type(OutcomeType.SKILL_USED)
    assert not game.can_use_reroll(interceptor.team)


@pytest.mark.parametrize('kind,modifier', [
    ('accurate', 0), ('inaccurate', 0), ('handoff', 0), ('kick', 0), ('bounce', -1)])
def test_catch_tests(kind, modifier):
    game, (catcher,) = season3_turn([(5, 5)], ball=(5, 5))
    game.get_ball().is_carried = False
    kwargs = {} if kind == 'bounce' else {kind: True}
    proc = Catch(game, catcher, game.get_ball(), **kwargs)
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[3 - modifier]):
        game.step(None)
    assert proc.roll.modifiers == modifier
    assert game.get_ball_carrier() == catcher


def test_inaccurate_pass_catch_has_no_penalty():
    game, (passer, target, receiver) = season3_turn(
        [(3, 5), (10, 5), (10, 8)], ball=(3, 5))
    with only_fixed_rolls(game, d6=[5, 3], d8=[7, 7, 7]):
        pass_ball(game, passer, target.position)
    assert game.get_ball_carrier() == receiver
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_two_team_rerolls_in_same_turn_for_distinct_tests():
    game, (passer, catcher) = season3_turn([(5, 5), (8, 5)], ball=(5, 5), rerolls=3)
    with only_fixed_rolls(game, d6=[1, 4, 1, 3]):
        pass_ball(game, passer, catcher.position)
        assert isinstance(game.get_procedure(), Reroll)
        game.step(Action(ActionType.USE_REROLL))
        assert isinstance(game.get_procedure(), Reroll)
        game.step(Action(ActionType.USE_REROLL))
    assert game.get_ball_carrier() == catcher
    assert passer.team.state.rerolls == 1
    assert sum(r.outcome_type == OutcomeType.REROLL_USED for r in game.state.reports) == 2


@pytest.mark.parametrize('skill', [False, True])
def test_cannot_reroll_a_rerolled_pass(skill):
    game, (passer, catcher) = season3_turn([(5, 5), (8, 5)], ball=(5, 5), rerolls=3)
    if skill:
        passer.extra_skills = [Skill.PASS]
    with only_fixed_rolls(game, d6=[1, 1], d8=[7]):
        pass_ball(game, passer, catcher.position)
        if not skill:
            game.step(Action(ActionType.USE_REROLL))
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert passer.team.state.rerolls == (3 if skill else 2)


@pytest.mark.parametrize('roll,broken', [([4, 4], False), ([4, 5], True)])
def test_armor_is_a_target_number(roll, broken):
    game, (player,) = season3_turn([(5, 5)])
    proc = Armor(game, player)
    with only_fixed_rolls(game, d6=roll):
        proc.step(None)
    assert isinstance(game.get_procedure(), Injury) == broken


def test_handoff_preview_uses_receiver_agility():
    game, (passer, receiver) = season3_turn([(5, 5), (6, 5)], ball=(5, 5))
    receiver.extra_ag = 1
    assert game.get_handoff_actions(passer)[0].rolls == [[2]]


def test_rain_and_marking_apply_to_native_pickup_tests():
    game, (player, _) = season3_turn([(5, 5)], [(7, 5)], (6, 5))
    game.state.weather = WeatherType.POURING_RAIN
    assert game.get_pickup_prob(player, Square(6, 5)) == pytest.approx(2 / 6)
    with only_fixed_rolls(game, d6=[5]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.get_ball_carrier() == player


def test_missing_pa_means_no_pass_action_or_probability():
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    # No such player in the selected roster; still represent PA '-' correctly.
    player.role.pa = None
    assert game.get_pass_actions(player, game.get_ball()) == []
    assert game.get_pass_prob(player, game.get_ball(), Square(8, 5)) == 0.0


def test_landing_on_prone_teammate_without_possession_is_a_turnover():
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    player.state.up = False
    game.get_ball().is_carried = False
    proc = TurnoverIfPossessionLost(game, game.get_ball())
    proc.step(None)
    assert isinstance(game.get_procedure(), Turnover)


def test_scatter_out_of_bounds_throws_in_without_interception():
    game, (passer, target, _) = season3_turn([(3, 5), (10, 1)], [(6, 3)], (3, 5))
    # Long pass 5-2=3: inaccurate, then first scatter exits north.
    # Throw-in direction straight south, distance 2; then one ground bounce.
    with only_fixed_rolls(game, d6=[5, 1, 1], d8=[2, 2, 2, 7], d3=[2]):
        pass_ball(game, passer, target.position)
    assert game.has_report_of_type(OutcomeType.BALL_OUT_OF_BOUNDS)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not isinstance(game.get_procedure(), Interception)


def test_formation_prefers_lower_native_ag_target():
    game, (ordinary, agile) = season3_turn([(5, 5), (8, 5)])
    agile.extra_ag = 1
    assert Formation('test', [])._get_player([ordinary, agile], 'a') == agile


def test_scripted_bots_complete_a_preview_match():
    from examples.season3_preview import run_match
    game = run_match(seed=0)
    assert game.state.game_over
    assert game.end_time is not None
    assert game.ruleset.is_season3
    assert all(p.role.target_characteristics for t in game.state.teams for p in t.players)


@pytest.mark.parametrize('implementation', ['python', 'cython'])
@pytest.mark.parametrize('pickup', [False, True])
def test_pathfinding_uses_native_ag_targets(implementation, pickup):
    if implementation == 'cython':
        pathfinding = pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    else:
        pathfinding = python_pathfinding
    game, (player, _) = season3_turn([(5, 5)], [(4, 5)], (6, 5) if pickup else None)
    # Consume all but one move, so the path cannot avoid this dodge via a detour.
    player.state.moves = player.get_ma() - 1
    path = pathfinding.get_safest_path(game, player, Square(6, 5))
    assert path.prob == pytest.approx((4 / 6) ** (2 if pickup else 1))


@pytest.mark.parametrize('inaccurate', [False, True])
def test_forward_model_reverses_pass_and_interception_decision(inaccurate):
    game, (passer, catcher, interceptor) = season3_turn(
        [(3, 5), (10, 5)], [(6, 5)], (3, 5))
    game.enable_forward_model()
    game.step(Action(ActionType.START_PASS, player=passer))
    # Wall clocks are deliberately excluded from the upstream forward model.
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[5 if inaccurate else 6], d8=[7, 7, 7] if inaccurate else []):
        game.step(Action(ActionType.PASS, position=catcher.position))
    pending = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == pending
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
    assert game.get_ball_carrier() == interceptor


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_pathfinding_handoff_and_foul_targets(implementation):
    pathfinding = (python_pathfinding if implementation == 'python' else
                   pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding'))
    game, (player, receiver, opponent) = season3_turn(
        [(5, 5), (6, 5)], [(5, 6)], (5, 5))
    receiver.extra_ag = 1
    opponent.state.up = False
    handoffs = [p for p in pathfinding.Pathfinder(game, player, can_handoff=True).get_paths()
                if p.handoff_roll is not None]
    fouls = [p for p in pathfinding.Pathfinder(game, player, can_foul=True).get_paths()
             if p.foul_roll is not None]
    assert len(handoffs) == len(fouls) == 1
    assert handoffs[0].handoff_roll == 2
    assert fouls[0].foul_roll == 8  # AV9+, one assist from the receiver
