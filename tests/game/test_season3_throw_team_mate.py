import pytest

from botbowl import Action, ActionType, Skill, Square, OutcomeType, PassDistance
from tests.game.test_season3 import season3_turn
from tests.util import only_fixed_rolls


def throwing_game(opponents=None, ball=(20, 12)):
    game, players = season3_turn([(5, 5), (6, 5)], opponents, ball=ball)
    thrower, passenger = players[:2]
    thrower.extra_skills = [Skill.THROW_TEAM_MATE]
    passenger.extra_skills = [Skill.RIGHT_STUFF]
    game.set_available_actions()
    return game, players


def throw(game, thrower, passenger, target=Square(8, 5), kick=False):
    game.step(Action(ActionType.START_KICK_TEAM_MATE if kick else ActionType.START_THROW_TEAM_MATE,
                     player=thrower))
    game.step(Action(ActionType.PICKUP_TEAM_MATE, position=passenger.position))
    game.step(Action(ActionType.THROW_TEAM_MATE, position=target))


def test_throw_uses_pa_and_separate_allowance():
    game, (thrower, passenger) = throwing_game()
    thrower.extra_ag = 1
    with only_fixed_rolls(game, d6=[4, 3], d8=[5, 5, 5]):
        throw(game, thrower, passenger)
    assert passenger.position == Square(11, 5)
    assert passenger.state.up and not passenger.state.used and not passenger.state.in_air
    assert thrower.state.used
    assert game.current_turn().pass_available
    assert not game.current_turn().throw_team_mate_available
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('accuracy,landing,stood', [(3, 3, False), (3, 4, True), (4, 3, True)])
def test_subpar_landing_penalty(accuracy, landing, stood):
    game, (thrower, passenger) = throwing_game()
    with only_fixed_rolls(game, d6=[accuracy, landing] + ([] if stood else [1, 1]), d8=[5, 5, 5]):
        throw(game, thrower, passenger)
    assert passenger.state.up == stood
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_fumble_bounces_from_thrower_and_has_landing_penalty():
    game, (thrower, passenger) = throwing_game()
    with only_fixed_rolls(game, d6=[1, 4], d8=[7]):
        throw(game, thrower, passenger)
    assert passenger.position == Square(5, 6)
    assert passenger.state.up
    assert game.has_report_of_type(OutcomeType.FUMBLE)


@pytest.mark.parametrize('state', ['prone', 'stunned', 'distracted'])
def test_incapacitated_right_stuff_players_auto_fail_landing(state):
    game, (thrower, passenger) = throwing_game()
    if state in ('prone', 'stunned'):
        passenger.state.up = False
    setattr(passenger.state, state if state != 'prone' else 'up', state != 'prone')
    with only_fixed_rolls(game, d6=[4, 1, 1], d8=[5, 5, 5]):
        throw(game, thrower, passenger)
    assert not passenger.state.up
    assert not passenger.state.in_air
    assert game.has_report_of_type(OutcomeType.FAILED_LAND)


def test_bullseye_can_prevent_scatter():
    game, (thrower, passenger) = throwing_game()
    thrower.extra_skills.append(Skill.BULLSEYE)
    with only_fixed_rolls(game, d6=[4, 3]):
        throw(game, thrower, passenger)
        assert game.get_available_actions()[0].skill == Skill.BULLSEYE
        game.step(Action(ActionType.USE_SKILL))
    assert passenger.position == Square(8, 5)
    assert passenger.state.up


def test_collision_bounces_then_automatically_falls_without_agility_roll():
    game, (thrower, passenger, victim) = throwing_game([(11, 5)])
    with only_fixed_rolls(game, d6=[4, 1, 1, 1, 1], d8=[5, 5, 5, 5]):
        throw(game, thrower, passenger)
    assert not victim.state.up
    assert not passenger.state.up
    assert passenger.position == Square(12, 5)
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_collision_chain_finishes_before_friendly_knockdown_turnover():
    game, (thrower, passenger) = throwing_game()
    victim = next(p for p in thrower.team.players if p.position is None)
    game.reserves_to_pitch(victim, Square(11, 5))
    with only_fixed_rolls(game, d6=[4, 1, 1, 1, 1], d8=[5, 5, 5, 5]):
        throw(game, thrower, passenger)
    assert passenger.position == Square(12, 5)
    assert not passenger.state.in_air
    assert not passenger.state.up and not victim.state.up
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_lethal_flight_breaks_armour_without_mighty_blow():
    game, (thrower, passenger, victim) = throwing_game([(11, 5)])
    passenger.extra_skills.append(Skill.LETHAL_FLIGHT)
    with only_fixed_rolls(game, d6=[4, 4, 4, 1, 2, 1, 1], d8=[5, 5, 5, 5]):
        throw(game, thrower, passenger)
    assert victim.state.stunned


def test_kick_fumble_injures_at_origin_and_retains_throw_allowance():
    game, (thrower, passenger) = throwing_game()
    thrower.extra_skills.append(Skill.KICK_TEAM_MATE)
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        throw(game, thrower, passenger, kick=True)
    assert passenger in game.get_knocked_out(passenger.team)
    assert game.current_turn().throw_team_mate_available
    assert game.current_turn().pass_available
    assert not game.current_turn().kick_team_mate_available
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_always_hungry_escape_fumbles_without_passing_test():
    game, (thrower, passenger) = throwing_game()
    thrower.extra_skills.append(Skill.ALWAYS_HUNGRY)
    with only_fixed_rolls(game, d6=[1, 2, 4], d8=[7]):
        throw(game, thrower, passenger)
    assert passenger.position == Square(5, 6)
    assert passenger.state.up
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


@pytest.mark.parametrize('carrying', [False, True])
def test_always_hungry_death_turnover_only_when_carrying_ball(carrying):
    game, (thrower, passenger) = throwing_game(ball=(6, 5) if carrying else (20, 12))
    thrower.extra_skills.append(Skill.ALWAYS_HUNGRY)
    passenger.extra_skills.append(Skill.REGENERATION)
    passenger.team.state.apothecaries = 1
    with only_fixed_rolls(game, d6=[1, 1], d8=[7] if carrying else []):
        throw(game, thrower, passenger)
    assert passenger in game.get_casualties(passenger.team)
    assert passenger.team.state.apothecaries == 1
    assert game.has_report_of_type(OutcomeType.TURNOVER) == carrying


def test_swoop_direction_distance_and_landing_reroll():
    game, (thrower, passenger) = throwing_game()
    passenger.extra_skills.append(Skill.SWOOP)
    with only_fixed_rolls(game, d6=[4, 3, 2, 1, 3]):
        throw(game, thrower, passenger)
        game.step(Action(ActionType.USE_SKILL))
        game.step(Action(ActionType.SELECT_DIRECTION, position=Square(9, 5)))
    assert passenger.position == Square(10, 5)
    assert passenger.state.up


def test_throw_range_and_strong_arm_modifiers():
    game, (thrower, passenger) = throwing_game()
    assert game.get_pass_modifiers(thrower, PassDistance.QUICK_PASS, ttm=True) == 0
    assert game.get_pass_modifiers(thrower, PassDistance.SHORT_PASS, ttm=True) == -1
    thrower.extra_skills += [Skill.STRONG_ARM, Skill.ACCURATE, Skill.CANNONEER]
    assert game.get_pass_modifiers(thrower, PassDistance.QUICK_PASS, ttm=True) == 1


def test_marking_penalizes_landing():
    game, (thrower, passenger, marker) = throwing_game([(12, 5)])
    with only_fixed_rolls(game, d6=[4, 3, 1, 1], d8=[5, 5, 5]):
        throw(game, thrower, passenger)
    assert not passenger.state.up


def test_throwing_is_unavailable_within_pass_action():
    game, (thrower, passenger) = throwing_game()
    game.step(Action(ActionType.START_PASS, player=thrower))
    assert ActionType.PICKUP_TEAM_MATE not in [a.action_type for a in game.get_available_actions()]


@pytest.mark.parametrize('first', [1, 3])
def test_failed_accuracy_can_use_team_reroll(first):
    game, (thrower, passenger) = throwing_game()
    thrower.team.state.rerolls = 1
    with only_fixed_rolls(game, d6=[first, 4, 3], d8=[5, 5, 5]):
        throw(game, thrower, passenger)
        game.step(Action(ActionType.USE_REROLL))
    assert passenger.position == Square(11, 5)
    assert passenger.state.up
    assert thrower.team.state.rerolls == 0


def test_bullseye_can_be_declined():
    game, (thrower, passenger) = throwing_game()
    thrower.extra_skills.append(Skill.BULLSEYE)
    with only_fixed_rolls(game, d6=[4, 3], d8=[5, 5, 5]):
        throw(game, thrower, passenger)
        game.step(Action(ActionType.DONT_USE_SKILL))
    assert passenger.position == Square(11, 5)


def test_opposing_ball_carrier_ball_does_not_follow_passenger():
    game, (thrower, passenger, victim) = throwing_game([(11, 5)], ball=(11, 5))
    with only_fixed_rolls(game, d6=[4, 1, 1, 1, 1], d8=[5, 5, 5, 7, 5]):
        throw(game, thrower, passenger)
    assert passenger.position == Square(12, 5)
    assert game.get_ball_position() == Square(11, 6)
    assert not game.get_ball().is_carried


def test_lethal_flight_casualty_credit_survives_regeneration():
    game, (thrower, passenger, victim) = throwing_game([(11, 5)])
    passenger.extra_skills.append(Skill.LETHAL_FLIGHT)
    victim.extra_skills.append(Skill.REGENERATION)
    with only_fixed_rolls(game, d6=[4, 5, 4, 5, 4, 4, 1, 1], d8=[5, 5, 5, 5]):
        throw(game, thrower, passenger)
    assert victim in game.get_reserves(victim.team)
    assert passenger.state.spp_earned == 2
    assert thrower.state.spp_earned == 0


def test_crowd_injury_causes_turnover_and_clears_airborne_state():
    game, (thrower, passenger) = throwing_game()
    with only_fixed_rolls(game, d6=[4, 1, 1], d8=[4]):
        throw(game, thrower, passenger, target=Square(1, 5))
    assert passenger in game.get_reserves(passenger.team)
    assert not passenger.state.in_air
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_throw_can_be_reverted_and_replayed_for_search():
    game, (thrower, passenger) = throwing_game()
    game.enable_forward_model()
    game.step(Action(ActionType.START_THROW_TEAM_MATE, player=thrower))
    game.step(Action(ActionType.PICKUP_TEAM_MATE, position=passenger.position))
    checkpoint = game.get_step()
    with only_fixed_rolls(game, d6=[4, 3], d8=[5, 5, 5]):
        game.step(Action(ActionType.THROW_TEAM_MATE, position=Square(8, 5)))
    after = game.state.to_json()
    steps = game.revert(checkpoint)
    assert passenger.position == Square(6, 5)
    assert game.get_player_at(Square(6, 5)) == passenger
    assert not passenger.state.in_air
    game.forward(steps)
    assert game.state.to_json() == after
