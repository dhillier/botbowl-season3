"""Season 3 Secure the Ball declarations, resolution and client integration."""
import pytest

from tests.game.test_season3 import season3_turn
from tests.util import *
from botbowl.core.pathfinding import python_pathfinding


def start_secure(game, player):
    game.set_available_actions()
    game.step(Action(ActionType.START_SECURE_BALL, player=player))


def secure_players(game):
    return [p for a in game.get_available_actions() if a.action_type == ActionType.START_SECURE_BALL
            for p in a.players]


@pytest.mark.parametrize('ag', [1, 3, 6])
@pytest.mark.parametrize('weather', [WeatherType.NICE, WeatherType.POURING_RAIN])
def test_fixed_two_plus_pickup_ends_activation(ag, weather):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    player.role.ag = ag
    game.state.weather = weather
    with only_fixed_rolls(game, d6=[2]):
        start_secure(game, player)
        assert game.state.player_action_type == PlayerActionType.SECURE_BALL
        move = next(a for a in game.get_available_actions() if a.action_type == ActionType.MOVE)
        assert move.rolls[move.positions.index(Square(6, 5))] == [2]
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.get_ball_carrier() == player
    assert player.state.used
    assert game.state.active_player is None
    assert isinstance(game.get_procedure(), Turn)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
    pickup = next(r for r in game.state.reports if r.outcome_type == OutcomeType.SUCCESSFUL_PICKUP)
    assert pickup.rolls[0].roll_type == RollType.SECURE_BALL_ROLL
    assert pickup.rolls[0].target == 2
    assert pickup.rolls[0].modifiers == 0


@pytest.mark.parametrize('sure_hands', [False, True])
def test_failed_secure_bounces_and_turns_over_without_sure_hands(sure_hands):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    if sure_hands:
        player.extra_skills = [Skill.SURE_HANDS]
    team = player.team
    with only_fixed_rolls(game, d6=[1], d8=[5]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.has_report_of_type(OutcomeType.FAILED_PICKUP)
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.SKILL_USED)
    assert game.get_ball_position() == Square(7, 5)
    assert game.state.current_team != team


@pytest.mark.parametrize('second,success', [(1, False), (2, True)])
def test_team_reroll_can_reroll_secure_once(second, success):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5), rerolls=3)
    player.extra_skills = [Skill.SURE_HANDS]
    with only_fixed_rolls(game, d6=[1, second], d8=[] if success else [5]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        assert isinstance(game.get_procedure(), Reroll)
        game.step(Action(ActionType.USE_REROLL))
    assert player.team.state.rerolls == 2
    assert (game.get_ball_carrier() == player) == success
    assert not game.has_report_of_type(OutcomeType.SKILL_USED)
    assert game.has_report_of_type(OutcomeType.TURNOVER) != success


def test_second_team_reroll_in_turn_can_be_used_on_secure_pickup():
    game, (player, opponent) = season3_turn([(5, 5)], [(4, 5)], (7, 5), rerolls=3)
    # Opponent is three squares from ball, but marks the starting square.
    with only_fixed_rolls(game, d6=[1, 3, 1, 2]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        game.step(Action(ActionType.USE_REROLL))  # Dodge
        game.step(Action(ActionType.MOVE, position=Square(7, 5)))
        game.step(Action(ActionType.USE_REROLL))  # Secure pickup
    assert game.get_ball_carrier() == player
    assert player.team.state.rerolls == 1


@pytest.mark.parametrize('position,eligible', [
    ((8, 5), False), ((8, 7), False), ((8, 8), True), ((9, 5), True)])
def test_opposition_exclusion_is_two_squares_including_diagonals(position, eligible):
    game, (player, _) = season3_turn([(5, 5)], [position], (6, 5))
    assert game.can_secure_ball(player) == eligible
    assert (player in secure_players(game)) == eligible


@pytest.mark.parametrize('status', ['prone', 'distracted', 'hypnotized', 'bone_headed', 'really_stupid'])
def test_prone_or_distracted_opponent_does_not_prevent_declaration(status):
    game, (player, opponent) = season3_turn([(5, 5)], [(8, 5)], (6, 5))
    if status == 'prone':
        opponent.state.up = False
    else:
        setattr(opponent.state, status, True)
    game.set_available_actions()
    assert game.can_secure_ball(player)
    assert player in secure_players(game)


def test_standing_opponent_without_tackle_zone_still_prevents_declaration():
    game, (player, opponent) = season3_turn([(5, 5)], [(8, 5)], (6, 5))
    opponent.extra_skills = [Skill.TITCHY]
    assert not opponent.has_tackle_zone()
    assert not game.can_secure_ball(player)


@pytest.mark.parametrize('reason', ['big_guy', 'no_hands', 'used', 'stunned', 'carried', 'airborne', 'too_far'])
def test_invalid_declarations_are_not_offered(reason):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    if reason == 'big_guy':
        player.role.keywords = ('Big Guy',)
    elif reason == 'no_hands':
        player.extra_skills = [Skill.NO_HANDS]
    elif reason in ('used', 'stunned'):
        setattr(player.state, reason, True)
    elif reason == 'carried':
        game.get_ball().is_carried = True
    elif reason == 'airborne':
        game.get_ball().on_ground = False
    elif reason == 'too_far':
        game.get_ball().move_to(Square(14, 5))
    game.set_available_actions()
    assert not game.can_secure_ball(player)
    assert player not in secure_players(game)
    assert not game._is_action_allowed(Action(ActionType.START_SECURE_BALL, player=player))


def test_unreachable_ball_cannot_be_declared_even_if_within_movement_range():
    game, (player, *_) = season3_turn([(5, 5), (1, 2), (2, 1), (2, 2)], ball=(1, 1))
    assert player.position.distance(game.get_ball_position()) < player.get_ma()
    assert not game.can_secure_ball(player)


def test_ending_movement_short_of_ball_causes_turnover():
    game, (player,) = season3_turn([(5, 5)], ball=(8, 5))
    team = player.team
    start_secure(game, player)
    assert not game.is_secure_ball_available()
    assert not any(a.action_type == ActionType.UNDO for a in game.get_available_actions())
    with only_fixed_rolls(game):
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        game.step(Action(ActionType.END_PLAYER_TURN))
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.state.current_team != team
    assert game.get_ball_position() == Square(8, 5)


def test_declaration_budget_spent_even_if_pre_action_trait_fails():
    game, (player, other) = season3_turn([(5, 5), (7, 5)], ball=(6, 5))
    player.extra_skills = [Skill.BONE_HEAD]
    with only_fixed_rolls(game, d6=[1]):
        start_secure(game, player)
    assert player.state.used
    assert not game.is_secure_ball_available()
    assert not game.can_secure_ball(other)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_only_one_declaration_then_allowance_resets_next_turn():
    game, (player, other) = season3_turn([(5, 5), (7, 5)], ball=(6, 5))
    team = player.team
    with only_fixed_rolls(game, d6=[2]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    game.get_ball().is_carried = False
    game.get_ball().move_to(Square(8, 5))
    assert not game.can_secure_ball(other)
    game.step(Action(ActionType.END_TURN))
    game.step(Action(ActionType.END_TURN))
    assert game.state.current_team == team
    assert game.is_secure_ball_available()
    assert game.can_secure_ball(other)


@pytest.mark.parametrize('prone', [False, True])
def test_player_already_on_loose_ball_can_secure_it(prone):
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    game.get_ball().is_carried = False
    player.state.up = not prone
    assert game.get_ball_carrier() is None
    with only_fixed_rolls(game, d6=[2]):
        start_secure(game, player)
        if prone:
            assert [a.action_type for a in game.get_available_actions()] == [ActionType.STAND_UP, ActionType.END_PLAYER_TURN]
            game.step(Action(ActionType.STAND_UP))
    assert game.get_ball_carrier() == player
    assert player.state.used


@pytest.mark.parametrize('implementation', ['python', 'cython'])
@pytest.mark.parametrize('sure_hands', [False, True])
def test_pathfinder_secure_pickup_ignores_ag_weather_and_sure_hands(implementation, sure_hands):
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip(
        'botbowl.core.pathfinding.cython_pathfinding')
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    game.state.weather = WeatherType.POURING_RAIN
    player.role.ag = 6
    if sure_hands:
        player.extra_skills = [Skill.SURE_HANDS]
    path = pf.Pathfinder(game, player, secure_ball=True).get_path(Square(6, 5))
    assert path.prob == pytest.approx(5 / 6)
    assert path.rolls[-1] == [2]
    path_with_rr = pf.Pathfinder(game, player, secure_ball=True, trr=True).get_path(Square(6, 5))
    assert path_with_rr.prob == pytest.approx(35 / 36)


@pytest.mark.parametrize('pathfinding_enabled', [False, True])
def test_prone_player_stands_and_movement_risks_still_apply(pathfinding_enabled):
    game, (player,) = season3_turn([(5, 5)], ball=(11, 5))
    player.state.up = False  # 3 to stand leaves MA3 + 2 rushes: cannot reach.
    assert not game.can_secure_ball(player)
    game.get_ball().move_to(Square(10, 5))
    game.config.pathfinding_enabled = pathfinding_enabled
    with only_fixed_rolls(game, d6=[2, 2, 2]):
        start_secure(game, player)
        game.step(Action(ActionType.STAND_UP))
        if pathfinding_enabled:
            game.step(Action(ActionType.MOVE, position=Square(10, 5)))
        else:
            for x in range(6, 11):
                game.step(Action(ActionType.MOVE, position=Square(x, 5)))
    assert game.get_ball_carrier() == player
    assert player.state.used


def test_failed_rush_prevents_pickup_and_turns_over():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    player.state.moves = player.get_ma()
    with only_fixed_rolls(game, d6=[1, 1, 1], d8=[5]):  # Rush fails, armour holds; loose ball bounces.
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not game.has_report_of_type(OutcomeType.SUCCESSFUL_PICKUP)
    assert not game.get_ball().is_carried


def test_successful_secure_in_end_zone_scores():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    end_x = game.get_opp_endzone_x(player.team)
    game.move(player, Square(end_x - 1 if end_x > 1 else 2, 5))
    game.get_ball().move_to(Square(end_x, 5))
    # Touchdown triggers drive setup with no extra dice at this point.
    with only_fixed_rolls(game, d6=[2]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(end_x, 5)))
    assert game.has_report_of_type(OutcomeType.TOUCHDOWN)
    assert player.team.state.score == 1


def test_forward_model_restores_declaration_budget_pickup_and_reroll():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5), rerolls=1)
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[1]):
        start_secure(game, player)
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert isinstance(game.get_procedure(), Reroll)
    pending = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    assert game.is_secure_ball_available()
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == pending
    assert not game.is_secure_ball_available()
    with only_fixed_rolls(game, d6=[2]):
        game.step(Action(ActionType.USE_REROLL))
    assert game.get_ball_carrier() == player
    assert player.state.used


def test_scripted_bot_selects_and_completes_secure_ball():
    from examples.scripted_bot_example import MyScriptedBot
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    bot = MyScriptedBot('test')
    bot.new_game(game, player.team)
    action = bot.act(game)
    assert action.action_type == ActionType.START_SECURE_BALL
    assert action.player == player
    with only_fixed_rolls(game, d6=[2]):
        game.step(action)
        game.step(bot.act(game))
    assert game.get_ball_carrier() == player
    assert not bot.actions


def test_scripted_bot_prefers_safer_ordinary_pickup_by_sure_hands_teammate():
    from examples.scripted_bot_example import MyScriptedBot
    game, (lineman, thrower) = season3_turn([(5, 5), (7, 5)], ball=(6, 5))
    thrower.extra_skills = [Skill.SURE_HANDS]
    bot = MyScriptedBot('test')
    bot.new_game(game, lineman.team)
    action = bot.act(game)
    assert action.action_type == ActionType.START_MOVE
    assert action.player == thrower


def test_secure_report_does_not_alias_existing_block_report():
    assert OutcomeType.SECURE_BALL_ACTION_STARTED is not OutcomeType.ACTION_SELECT_DIE
    assert OutcomeType.ACTION_SELECT_DIE.name == 'ACTION_SELECT_DIE'


def test_distracted_clears_at_activation_before_secure_pickup():
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    player.state.distracted = True
    with only_fixed_rolls(game, d6=[2]):
        start_secure(game, player)
        assert not player.is_distracted()
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
    assert game.get_ball_carrier() == player


def test_web_api_round_trip_for_human_secure_ball(monkeypatch):
    from botbowl.web import server
    from botbowl.web.host import InMemoryHost
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
    game.game_id = 'secure-test'
    host = InMemoryHost()
    host.add_game(game)
    monkeypatch.setattr(server.api, 'host', host)
    client = server.app.test_client()
    state = json.loads(client.get('/games/secure-test').data)
    choice = next(a for a in state['state']['available_actions'] if a['action_type'] == 'START_SECURE_BALL')
    assert player.player_id in choice['player_ids']
    client.post('/games/secure-test/act', json={'action': {
        'action_type': 'START_SECURE_BALL', 'player_id': player.player_id}})
    with only_fixed_rolls(game, d6=[2]):
        response = client.post('/games/secure-test/act', json={'action': {
            'action_type': 'MOVE', 'position': {'x': 6, 'y': 5}}})
    final = json.loads(response.data)
    assert final['state']['active_player_id'] is None
    assert game.get_ball_carrier() == player
    assert player.state.used


def test_old_rules_and_kickoff_bonus_turns_do_not_offer_secure_ball():
    legacy, _ = get_custom_game_turn([(5, 5)], ball_position=(6, 5))
    assert not any(a.action_type == ActionType.START_SECURE_BALL for a in legacy.get_available_actions())
    for kind in ('blitz', 'quick_snap'):
        game, (player,) = season3_turn([(5, 5)], ball=(6, 5))
        turn = Turn(game, player.team, 1, 1, **{kind: True})
        turn.start()
        game.set_available_actions()
        assert player not in secure_players(game)
