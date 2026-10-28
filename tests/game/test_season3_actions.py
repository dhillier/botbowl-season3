"""Season 3 jump geometry/resolution and declared Blitz targets."""
import pytest

from tests.game.test_season3 import season3_turn
from tests.util import *
from botbowl.core.pathfinding import python_pathfinding
from botbowl.ai.layers import TargetPlayerLayer


def jump_game(rerolls=0):
    game, (player, downed) = season3_turn([(5, 5), (6, 5)], ball=(20, 12), rerolls=rerolls)
    downed.state.up = False
    game.set_available_actions()
    return game, player, downed


def begin_blitz(game, player, target):
    game.set_available_actions()
    game.step(Action(ActionType.START_BLITZ, player=player))
    assert isinstance(game.get_procedure(), BlitzDeclaration)
    game.step(Action(ActionType.SELECT_PLAYER, player=target))


@pytest.mark.parametrize('offset,expected', [
    ((1, 0), {(7, 4), (7, 5), (7, 6)}),
    ((1, 1), {(5, 7), (6, 7), (7, 5), (7, 6), (7, 7)})])
def test_jump_geometry_matches_both_rule_diagrams(offset, expected):
    game, player, downed = jump_game()
    if downed.position != Square(5 + offset[0], 5 + offset[1]):
        game.move(downed, Square(5 + offset[0], 5 + offset[1]))
    assert {(s.x, s.y) for s in game.get_jump_positions(player)} == expected


def test_jump_requires_downed_player_and_empty_landing():
    game, player, downed = jump_game()
    downed.state.up = True
    assert game.get_jump_positions(player) == []
    downed.state.up = False
    occupant = next(p for p in player.team.players if p.position is None)
    game.put(occupant, Square(7, 5))
    assert Square(7, 5) not in game.get_jump_positions(player)


def test_jump_positions_stay_on_pitch():
    game, player, downed = jump_game()
    game.move(player, Square(2, 2))
    game.move(downed, Square(1, 1))
    assert game.get_jump_positions(player) == []


def test_successful_jump_costs_two_and_can_be_repeated():
    game, (player, first, second) = season3_turn([(5, 5), (6, 5), (8, 5)], ball=(20, 12))
    first.state.up = second.state.up = False
    with only_fixed_rolls(game, d6=[3, 3]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
        assert player.state.moves == 2
        game.step(Action(ActionType.JUMP, position=Square(9, 5)))
    assert player.position == Square(9, 5)
    assert player.state.moves == 4
    assert player.state.up
    assert Skill.LEAP not in player.state.used_skills


@pytest.mark.parametrize('roll,position', [(1, Square(5, 5)), (2, Square(7, 5))])
def test_failed_jump_falls_at_takeoff_only_on_natural_one(roll, position):
    game, player, _ = jump_game()
    with only_fixed_rolls(game, d6=[roll, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    assert player.position == position
    assert not player.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.has_report_of_type(OutcomeType.FAILED_JUMP)


@pytest.mark.parametrize('opponents,modifier', [
    ([(4, 5)], -1), ([(8, 5)], -1),
    ([(4, 5), (4, 4), (8, 5)], -2),
    ([(4, 5), (8, 5), (8, 4), (8, 6)], -3)])
def test_jump_uses_worse_marking_at_takeoff_or_landing(opponents, modifier):
    game, (player, downed, *_) = season3_turn([(5, 5), (6, 5)], opponents, (20, 12))
    downed.state.up = False
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.START_MOVE, player=player))
        choice = next(a for a in game.get_available_actions() if a.action_type == ActionType.JUMP)
        assert choice.rolls[choice.positions.index(Square(7, 5))] == [min(6, 3 - modifier)]
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    report = next(r for r in game.state.reports if r.outcome_type == OutcomeType.SUCCESSFUL_JUMP)
    assert report.rolls[0].modifiers == modifier
    assert player.position == Square(7, 5)  # Natural 6 succeeds despite modifiers.


def test_dodge_skill_does_not_reroll_jump():
    game, player, _ = jump_game()
    player.extra_skills = [Skill.DODGE]
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.SKILL_USED)


@pytest.mark.parametrize('second,position,success', [(1, Square(5, 5), False), (2, Square(7, 5), False), (3, Square(7, 5), True)])
def test_team_reroll_uses_final_jump_result_once(second, position, success):
    game, player, _ = jump_game(rerolls=3)
    with only_fixed_rolls(game, d6=[1, second] + ([] if success else [1, 1])):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
        game.step(Action(ActionType.USE_REROLL))
    assert player.position == position
    assert player.state.up == success
    assert player.team.state.rerolls == 2


@pytest.mark.parametrize('moves,rush_results', [(5, [2]), (6, [2, 2])])
def test_all_required_rushes_resolve_before_jump(moves, rush_results):
    game, player, _ = jump_game()
    player.state.moves = moves
    with only_fixed_rolls(game, d6=rush_results + [3]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    relevant = [r.outcome_type for r in game.state.reports if r.outcome_type in (
        OutcomeType.SUCCESSFUL_GFI, OutcomeType.SUCCESSFUL_JUMP)]
    assert relevant == [OutcomeType.SUCCESSFUL_GFI] * len(rush_results) + [OutcomeType.SUCCESSFUL_JUMP]
    if moves + 2 == player.get_ma() + 2:
        assert player.state.used  # Engine ends exhausted activations and resets moves.
    else:
        assert player.state.moves == moves + 2


@pytest.mark.parametrize('rush_results', [[1], [2, 1]])
def test_failed_jump_rush_falls_at_takeoff_without_jump_roll(rush_results):
    game, player, _ = jump_game()
    player.state.moves = 6
    with only_fixed_rolls(game, d6=rush_results + [1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    assert player.position == Square(5, 5)
    assert not player.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.FAILED_JUMP)


@pytest.mark.parametrize('secure', [False, True])
def test_jump_onto_ball_uses_declared_pickup_action(secure):
    game, player, _ = jump_game()
    game.get_ball().move_to(Square(7, 5))
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[3, 2 if secure else 3]):
        game.step(Action(ActionType.START_SECURE_BALL if secure else ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    assert game.get_ball_carrier() == player
    assert player.state.used == secure


@pytest.mark.parametrize('reason', ['prone', 'no_movement', 'quick_snap', 'legacy'])
def test_jump_not_offered_when_action_is_illegal(reason):
    game, player, _ = jump_game()
    if reason == 'prone':
        player.state.up = False
    elif reason == 'no_movement':
        player.state.moves = 7  # Only one Rush square remains.
    elif reason == 'quick_snap':
        game.current_turn().quick_snap = True
    else:
        game.ruleset = load_rule_set('BB2016')
    assert game.get_jump_actions(player) == []


def wall_game():
    game, (player, *wall) = season3_turn([(5, 5), (6, 4), (6, 5), (6, 6)], ball=(20, 12))
    for downed in wall:
        downed.state.up = False
    return game, player


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_pathfinder_finds_required_jump_and_accounts_for_rushes(implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, player = wall_game()
    player.state.moves = 6
    player.extra_skills = [Skill.DODGE]
    path = pf.Pathfinder(game, player).get_path(Square(7, 5))
    assert path is not None
    assert path.steps == (Square(7, 5),)
    assert path.prob == pytest.approx((5 / 6) ** 2 * (4 / 6))
    assert tuple(tuple(r) for r in path.rolls) == ((2, 2, 3),)
    player.team.state.rerolls = 1
    with_reroll = pf.Pathfinder(game, player, trr=True).get_path(Square(7, 5))
    assert with_reroll.prob == pytest.approx(path.prob * (1 + 1 / 6 + 1 / 6 + 2 / 6))


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_pathfinder_prefers_safe_detour_over_unnecessary_jump(implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, player, _ = jump_game()
    path = pf.Pathfinder(game, player).get_path(Square(7, 5))
    assert path.prob == 1.0
    assert all(a.distance(b) == 1 for a, b in zip((player.position,) + path.steps, path.steps))


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_pathfinder_continues_after_jump_with_later_rushes(implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, player = wall_game()
    player.state.moves = 4
    path = pf.Pathfinder(game, player).get_path(Square(9, 5))
    assert path is not None
    assert player.position.distance(path.steps[0]) == 2
    assert path.prob == pytest.approx((4 / 6) * (5 / 6) ** 2)
    assert sum(player.position.distance(path.steps[0]) if i == 0 else path.steps[i - 1].distance(s)
               for i, s in enumerate(path.steps)) == 4
    game.config.pathfinding_enabled = False
    from examples.scripted_bot_example import path_to_move_actions
    actions = path_to_move_actions(game, player, path)
    with only_fixed_rolls(game, d6=[3, 2, 2]):
        game.step(Action(ActionType.START_MOVE, player=player))
        for action in actions:
            game.step(action)
    assert player.position == Square(9, 5)
    assert player.state.used


def test_movement_path_executes_jump_instead_of_walking_through_body():
    game, player = wall_game()
    player.state.moves = 6
    game.config.pathfinding_enabled = True
    with only_fixed_rolls(game, d6=[2, 2, 3]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(7, 5)))
    assert player.position == Square(7, 5)
    assert player.state.used
    assert game.has_report_of_type(OutcomeType.SUCCESSFUL_JUMP)


def test_scripted_path_translation_emits_jump_for_two_square_edge():
    from examples.scripted_bot_example import path_to_move_actions
    game, player = wall_game()
    player.state.moves = 6
    path = python_pathfinding.Pathfinder(game, player).get_path(Square(7, 5))
    actions = path_to_move_actions(game, player, path)
    assert actions[0].action_type == ActionType.JUMP


@pytest.mark.parametrize('pathfinding', [False, True])
def test_blitz_declares_target_and_cannot_attack_different_opponent(pathfinding):
    game, (player, target, other) = season3_turn([(5, 5)], [(6, 5), (5, 6)], (20, 12))
    game.config.pathfinding_enabled = pathfinding
    begin_blitz(game, player, target)
    assert not game.is_blitz_available()
    assert game.get_other_active_player_id() == target.player_id
    assert TargetPlayerLayer().produce(game)[5][6] == 1.0
    assert game._is_action_allowed(Action(ActionType.BLOCK, position=target.position))
    assert not game._is_action_allowed(Action(ActionType.BLOCK, position=other.position))
    assert not any(a.action_type == ActionType.UNDO for a in game.get_available_actions())


@pytest.mark.parametrize('x,eligible', [(13, True), (14, False)])
def test_blitz_reachability_reserves_movement_for_block(x, eligible):
    game, (player, target) = season3_turn([(5, 5)], [(x, 5)], (20, 12))
    assert (target in game.get_blitz_targets(player)) == eligible
    choices = [a for a in game.get_available_actions() if a.action_type == ActionType.START_BLITZ]
    assert any(player in a.players for a in choices) == eligible


def test_blitz_cannot_declare_prone_target():
    game, (player, target) = season3_turn([(5, 5)], [(6, 5)], (20, 12))
    target.state.up = False
    assert game.get_blitz_targets(player) == []


def test_blitz_reachability_includes_jump_route():
    game, player = wall_game()
    opponent = game.get_opp_team(player.team).players[0]
    game.put(opponent, Square(8, 5))
    player.state.moves = 5
    assert opponent in game.get_blitz_targets(player)
    begin_blitz(game, player, opponent)
    with only_fixed_rolls(game, d6=[2, 4]):  # Landing is marked by the declared target.
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    assert game._is_action_allowed(Action(ActionType.BLOCK, position=opponent.position))


def test_blitz_target_selection_precedes_trait_roll_and_consumes_allowance():
    game, (player, other, target) = season3_turn([(5, 5), (4, 5)], [(6, 5)], (20, 12))
    player.extra_skills = [Skill.BONE_HEAD]
    with only_fixed_rolls(game):
        game.step(Action(ActionType.START_BLITZ, player=player))
    assert isinstance(game.get_procedure(), BlitzDeclaration)
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.SELECT_PLAYER, player=target))
    assert player.state.used
    assert not game.is_blitz_available()
    assert isinstance(game.get_procedure(), Turn)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_abandoning_blitz_does_not_restore_allowance_or_cause_turnover():
    game, (player, target) = season3_turn([(5, 5)], [(6, 5)], (20, 12))
    begin_blitz(game, player, target)
    game.step(Action(ActionType.END_PLAYER_TURN))
    assert player.state.used
    assert not game.is_blitz_available()
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_blitz_can_continue_moving_after_block_and_cannot_block_twice():
    game, (player, target) = season3_turn([(5, 5)], [(6, 5)], (20, 12))
    player.extra_skills = target.extra_skills = [Skill.BLOCK]
    begin_blitz(game, player, target)
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN]):
        game.step(Action(ActionType.BLOCK, position=target.position))
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
    assert player.state.has_blocked
    assert player.state.moves == 1
    assert not game._is_action_allowed(Action(ActionType.BLOCK, position=target.position))
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.MOVE, position=Square(4, 5)))
    assert player.position == Square(4, 5)
    assert player.state.moves == 2


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_pathfinder_limits_blocks_to_declared_target(implementation):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, (player, target, other) = season3_turn([(5, 5)], [(6, 5), (5, 6)], (20, 12))
    paths = pf.Pathfinder(game, player, can_block=True, blitz_target=target).get_paths()
    assert {p.get_last_step() for p in paths if p.block_dice is not None} == {target.position}


def test_forward_model_reverses_blitz_declaration_and_target():
    game, (player, target) = season3_turn([(5, 5)], [(6, 5)], (20, 12))
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    begin_blitz(game, player, target)
    pending = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.is_blitz_available()
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert not game.is_blitz_available()
    assert game.state.to_json(ignore_clocks=True) == pending
    assert game.get_other_active_player_id() == target.player_id


def test_forward_model_reverses_pending_jump_reroll():
    game, player, _ = jump_game(rerolls=1)
    game.enable_forward_model()
    game.step(Action(ActionType.START_MOVE, player=player))
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
    pending = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == pending
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.USE_REROLL))
    assert player.position == Square(7, 5)


def test_new_report_codes_preserve_existing_names():
    added = {OutcomeType.SUCCESSFUL_JUMP, OutcomeType.FAILED_JUMP,
             OutcomeType.BLITZ_TARGET_DECLARED, OutcomeType.BLITZ_DECLARATION_STARTED}
    assert len(added) == 4
    assert OutcomeType.ACTION_SELECT_DIE not in added


def test_distinct_rush_and_jump_tests_can_both_use_team_rerolls():
    game, player, _ = jump_game(rerolls=3)
    player.state.moves = 5
    with only_fixed_rolls(game, d6=[1, 2, 1, 3]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.JUMP, position=Square(7, 5)))
        game.step(Action(ActionType.USE_REROLL))
        game.step(Action(ActionType.USE_REROLL))
    assert player.position == Square(7, 5)
    assert player.team.state.rerolls == 1


def test_blitz_reachability_can_pick_up_then_continue_to_target():
    game, (player, *_) = season3_turn([(1, 1), (1, 2), (2, 2)], [(4, 1)], (2, 1))
    target = game.get_player_at(Square(4, 1))
    # All routes must pass through the ball on (2,1), then continue to (3,1).
    assert target in game.get_blitz_targets(player)


def test_blitz_reachability_cannot_walk_through_standing_blockers():
    game, (player, *_) = season3_turn([(1, 1), (1, 2), (2, 1), (2, 2)], [(4, 1)], (20, 12))
    assert game.get_blitz_targets(player) == []


def test_prone_blitzer_stands_up_before_moving_and_accounts_for_block():
    game, (player, target) = season3_turn([(5, 5)], [(10, 5)], (20, 12))
    player.state.up = False
    # Stand 3 + move 4 + block 1 = MA6 plus two Rushes.
    assert target in game.get_blitz_targets(player)
    begin_blitz(game, player, target)
    assert not game._is_action_allowed(Action(ActionType.MOVE, position=Square(6, 5)))
    game.step(Action(ActionType.STAND_UP))
    assert player.state.up
    assert player.state.moves == 3


def test_projected_jump_geometry_does_not_jump_over_self():
    game, (player,) = season3_turn([(5, 5)], ball=(20, 12))
    player.state.up = False
    assert game.get_jump_positions(player, Square(4, 5)) == []


def test_blitz_allowance_resets_next_team_turn():
    game, (player, target) = season3_turn([(5, 5)], [(6, 5)], (20, 12))
    team = player.team
    begin_blitz(game, player, target)
    game.step(Action(ActionType.END_PLAYER_TURN))
    game.step(Action(ActionType.END_TURN))
    game.step(Action(ActionType.END_TURN))
    assert game.state.current_team == team
    assert game.is_blitz_available()


def test_web_api_declares_target_then_resolves_jump(monkeypatch):
    from botbowl.web import server
    from botbowl.web.host import InMemoryHost
    game, player = wall_game()
    opponent = game.get_opp_team(player.team).players[0]
    game.put(opponent, Square(8, 5))
    player.state.moves = 5
    game.set_available_actions()
    game.game_id = 'jump-blitz-test'
    host = InMemoryHost()
    host.add_game(game)
    monkeypatch.setattr(server.api, 'host', host)
    client = server.app.test_client()
    def act(kind, **kwargs):
        return json.loads(client.post('/games/jump-blitz-test/act', json={
            'action': {'action_type': kind, **kwargs}}).data)
    declaration = act('START_BLITZ', player_id=player.player_id)
    assert declaration['state']['available_actions'][0]['action_type'] == 'SELECT_PLAYER'
    act('SELECT_PLAYER', player_id=opponent.player_id)
    with only_fixed_rolls(game, d6=[2, 4]):
        landed = act('JUMP', position={'x': 7, 'y': 5})
    assert player.position == Square(7, 5)
    assert landed['active_other_player_id'] == opponent.player_id
    assert game.has_report_of_type(OutcomeType.SUCCESSFUL_JUMP)
