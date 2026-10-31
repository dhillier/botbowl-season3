from botbowl import Action, ActionType, Skill, Square, OutcomeType, Bomb, Explode
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


def throw_bomb(game, player, target):
    game.step(Action(ActionType.START_THROW_BOMB, player=player))
    game.step(Action(ActionType.THROW_BOMB, position=target))


def test_bomb_throw_uses_passing_ability_and_its_own_once_per_turn_allowance():
    game, (thrower, other, victim) = season3_turn([(5, 5), (10, 10)], [(8, 6)], ball=(20, 12))
    thrower.extra_skills = other.extra_skills = [Skill.BOMBARDIER]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[4, 4, 1, 1]):
        throw_bomb(game, thrower, Square(8, 5))
    assert game.get_bomb() is None
    assert not victim.state.up
    assert thrower.state.used and not other.state.used
    assert game.current_turn().pass_available
    assert not game.current_turn().bomb_available
    assert all(a.action_type != ActionType.START_THROW_BOMB for a in game.get_available_actions())
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_bomb_catch_is_mandatory_and_rethrow_preserves_activation():
    game, (thrower, catcher) = season3_turn([(5, 5)], [(8, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER, Skill.CLOUD_BURSTER]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[4, 3, 4]):
        throw_bomb(game, thrower, catcher.position)
        assert [a.action_type for a in game.get_available_actions()] == [ActionType.THROW_BOMB]
        assert game.get_active_player() == thrower
        game.step(Action(ActionType.THROW_BOMB, position=Square(11, 5)))
    assert not catcher.state.used
    assert thrower.state.used
    assert game.get_bomb() is None
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_catcher_without_passing_ability_drops_bomb_instead_of_deadlocking():
    game, (thrower, catcher) = season3_turn([(5, 5)], [(8, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER, Skill.CLOUD_BURSTER]
    catcher.role = game.ruleset.get_role('Woodland Fox', 'Gnome')
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[4, 2, 1, 1]):
        throw_bomb(game, thrower, catcher.position)
    assert game.get_bomb() is None
    assert not catcher.state.up and not catcher.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_dropped_bomb_explodes_in_catchers_square_without_bounce():
    game, (thrower, catcher) = season3_turn([(5, 5)], [(8, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER, Skill.CLOUD_BURSTER]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[4, 1, 1, 1]):
        throw_bomb(game, thrower, catcher.position)
    assert not catcher.state.up
    assert game.get_bomb() is None
    exploded = [r for r in game.state.reports if r.outcome_type == OutcomeType.BOMB_EXPLODED]
    assert exploded[0].position == Square(8, 5)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_fumbled_bomb_explodes_at_thrower_and_turns_over():
    game, (thrower,) = season3_turn([(5, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        throw_bomb(game, thrower, Square(8, 5))
    assert not thrower.state.up
    assert game.get_bomb() is None
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_explosion_resolves_all_players_even_when_active_player_falls():
    game, (friendly, prone, standing) = season3_turn([(8, 5)], [(9, 5), (8, 6)], ball=(20, 12))
    prone.state.up = False
    bomb = Bomb(Square(8, 5))
    game.put_bomb(bomb)
    with only_fixed_rolls(game, d6=[4, 4, 1, 1, 5, 4, 1, 2, 1, 1]):
        run_proc(game, Explode(game, bomb))
    assert not friendly.state.up
    assert prone.state.stunned
    assert not standing.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_intercepted_bomb_is_thrown_back_without_interception_turnover():
    game, (thrower, interceptor) = season3_turn([(5, 5)], [(7, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[4, 6, 4]):
        throw_bomb(game, thrower, Square(8, 5))
        game.step(Action(ActionType.SELECT_PLAYER, player=interceptor))
        assert game.get_available_actions()[0].action_type == ActionType.THROW_BOMB
        game.step(Action(ActionType.THROW_BOMB, position=Square(10, 5)))
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
    assert game.get_bomb() is None
    assert thrower.state.used and not interceptor.state.used


def test_bomb_can_use_pass_skill_reroll():
    game, (thrower,) = season3_turn([(5, 5)], ball=(20, 12))
    thrower.extra_skills = [Skill.BOMBARDIER, Skill.PASS]
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[1, 4]):
        throw_bomb(game, thrower, Square(8, 5))
    assert thrower.state.up
    assert game.get_bomb() is None
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_safe_pass_ends_give_and_go_activation():
    game, (thrower, catcher) = season3_turn([(13, 5), (16, 5)], ball=(13, 5))
    thrower.extra_skills = [Skill.SAFE_PASS, Skill.GIVE_AND_GO]
    with only_fixed_rolls(game, d6=[1]):
        game.step(Action(ActionType.START_PASS, player=thrower))
        game.step(Action(ActionType.PASS, position=catcher.position))
    assert thrower.state.used
    assert game.get_ball_carrier() == thrower
    assert not game.has_report_of_type(OutcomeType.TURNOVER)
