"""Live team special rules from The Teams, supplied PDF pages 6-8."""
import pytest

from botbowl import (Action, ActionType, Agent, Casualty, Ejection, Game, OutcomeType,
                     Player, RaiseDead, Setup, Skill, Swarming, Team, load_config, load_rule_set)
from examples.season3_teams import build_team, coverage_squads
from examples.scripted_bot_example import MyScriptedBot
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.util import only_fixed_rolls


@pytest.mark.parametrize('race', ['Black Orc', 'Dwarf', 'Goblin', 'Snotling', 'Underworld Denizens'])
@pytest.mark.parametrize('reroll', [1, 6])
def test_bribery_retries_natural_one_once_without_spending_a_team_reroll(race, reroll):
    game, (player,) = season3_turn([(10, 5)], rerolls=2)
    player.team.race = race
    with only_fixed_rolls(game, d6=[1, reroll]):
        run_proc(game, Ejection(game, player))
        game.step(Action(ActionType.ARGUE_CALL))
        assert player.team.state.can_argue and not player.state.ejected
        assert {a.action_type for a in game.get_available_actions()} == {
            ActionType.USE_REROLL, ActionType.DONT_USE_REROLL}
        game.step(Action(ActionType.USE_REROLL))
    assert player.team.state.rerolls == 2
    assert player.team.state.bribery_used
    assert player.state.ejected == (reroll == 1)
    assert player.team.state.can_argue == (reroll == 6)


@pytest.mark.parametrize('used,decline', [(False, True), (True, False)])
def test_bribery_cannot_repeat_or_force_a_declined_reroll(used, decline):
    game, (player,) = season3_turn([(10, 5)])
    player.team.race = 'Goblin'
    player.team.state.bribery_used = used
    with only_fixed_rolls(game, d6=[1]):
        run_proc(game, Ejection(game, player))
        game.step(Action(ActionType.ARGUE_CALL))
        if decline:
            game.step(Action(ActionType.DONT_USE_REROLL))
    assert player.state.ejected and not player.team.state.can_argue
    assert player.team.state.bribery_used == used


@pytest.mark.parametrize('race,choice,role', [
    ('Necromantic Horror', ActionType.RAISE_ZOMBIE, 'Zombie Lineman'),
    ('Shambling Undead', ActionType.RAISE_ZOMBIE, 'Zombie Lineman'),
    ('Shambling Undead', ActionType.RAISE_SKELETON, 'Skeleton Lineman'),
    ('Tomb Kings', ActionType.RAISE_SKELETON, 'Skeleton Lineman'),
    ('Vampire', ActionType.RAISE_THRALL, 'Thrall Lineman')])
def test_masters_raises_the_selected_lineman_from_a_non_block_death(race, choice, role):
    game, (player, victim) = season3_turn([(10, 5)], [(11, 5)])
    player.team.race = race
    count = len(player.team.players)
    with only_fixed_rolls(game, d16=[16]):
        run_proc(game, Casualty(game, victim))
        assert isinstance(game.get_procedure(), RaiseDead)
        game.step(Action(choice))
    recruit = player.team.players[-1]
    assert len(player.team.players) == count + 1
    assert recruit.role.name == role and 'Lineman' in recruit.role.keywords
    assert recruit in game.get_reserves(player.team)
    assert game.get_player(recruit.player_id) is recruit
    assert game.state.team_by_player_id[recruit.player_id] is player.team
    assert player.team.state.raised_dead


@pytest.mark.parametrize('restriction', ['strong', 'stunty', 'used', 'saved'])
def test_masters_exclusions_and_apothecary_resolution(restriction):
    game, (player, victim) = season3_turn([(10, 5)], [(11, 5)])
    player.team.race = 'Vampire'
    victim.extra_st = 2 if restriction == 'strong' else 1  # ST4 is eligible.
    victim.extra_skills = [Skill.STUNTY] if restriction == 'stunty' else []
    player.team.state.raised_dead = restriction == 'used'
    victim.team.state.apothecaries = int(restriction == 'saved')
    with only_fixed_rolls(game, d16=[16, 1] if restriction == 'saved' else [16]):
        run_proc(game, Casualty(game, victim))
        if restriction == 'saved':
            game.step(Action(ActionType.USE_APOTHECARY))
            game.step(Action(ActionType.SELECT_SECOND_ROLL))
    assert not isinstance(game.get_procedure(), RaiseDead)


def test_masters_can_decline_then_exceed_sixteen_and_revert_recruitment():
    game, (player, first, second) = season3_turn([(10, 5)], [(11, 5), (12, 5)])
    player.team.race = 'Vampire'
    while len(player.team.players) < 16:
        number = len(player.team.players) + 1
        player.team.players.append(Player('reserve-' + str(number), player.role, 'Reserve', number, player.team))
    with only_fixed_rolls(game, d16=[16, 16]):
        run_proc(game, Casualty(game, first))
        game.step(Action(ActionType.SELECT_NONE))
        assert not player.team.state.raised_dead
        run_proc(game, Casualty(game, second))
    game.enable_forward_model()
    before = game.get_step()
    game.step(Action(ActionType.RAISE_THRALL))
    recruit = player.team.players[-1]
    assert len(player.team.players) == 17
    changes = game.revert(before)
    assert len(player.team.players) == 16 and not player.team.state.raised_dead
    assert recruit.player_id not in game.state.player_by_id
    assert recruit.player_id not in game.state.team_by_player_id
    assert recruit not in game.get_reserves(player.team)
    game.forward(changes)
    assert len(player.team.players) == 17 and player.team.state.raised_dead
    assert game.get_player(recruit.player_id) is recruit
    assert game.state.team_by_player_id[recruit.player_id] is player.team
    assert recruit in game.get_reserves(player.team)


@pytest.mark.parametrize('die,free', [(1, False), (5, False), (6, True)])
@pytest.mark.parametrize('prone', [False, True])
def test_captain_on_pitch_can_save_a_team_reroll_even_when_prone(die, free, prone):
    game, (captain,) = season3_turn([(10, 5)], rerolls=2)
    captain.team.nominate_captain(captain)
    captain.state.up = not prone
    assert captain.has_skill(Skill.PRO)
    with only_fixed_rolls(game, d6=[die]):
        game.use_team_reroll(captain.team)
    assert captain.team.state.rerolls == (2 if free else 1)
    assert captain.team.state.reroll_used
    assert game.has_report_of_type(OutcomeType.TEAM_CAPTAIN_ROLL)


def test_captain_in_reserves_cannot_save_a_reroll_and_big_guys_are_ineligible():
    game, (captain, ogre) = season3_turn([(10, 5), (11, 5)], rerolls=2)
    ogre.role = game.ruleset.get_role('Ogre', 'Human')
    with pytest.raises(ValueError, match='eligible'):
        captain.team.nominate_captain(ogre)
    captain.team.nominate_captain(captain)
    game.pitch_to_reserves(captain)
    with only_fixed_rolls(game):
        game.use_team_reroll(captain.team)
    assert captain.team.state.rerolls == 1


def test_captain_free_reroll_preserves_leader_pool_and_reverses():
    game, (captain,) = season3_turn([(10, 5)], rerolls=0)
    captain.team.nominate_captain(captain)
    captain.extra_skills.append(Skill.LEADER)
    captain.team.state.leader_reroll = True
    game.enable_forward_model()
    before = game.get_step()
    with only_fixed_rolls(game, d6=[6, 5]):
        game.use_team_reroll(captain.team)
        assert captain.team.state.leader_reroll
        game.use_team_reroll(captain.team)
        assert not captain.team.state.leader_reroll
    changes = game.revert(before)
    assert captain.team.state.leader_reroll
    assert not captain.team.state.reroll_used
    game.forward(changes)
    assert not captain.team.state.leader_reroll
    assert captain.team.state.reroll_used


def make_setup_game(team):
    rules = load_rule_set('BB2025')
    other = build_team(next(coverage_squads('human')), rules)
    game = Game('team-rule-setup', team, other, Agent('home', human=True), Agent('away', human=True),
                load_config('season3-preview'), ruleset=rules)
    game.state.receiving_this_drive = game.state.home_team
    game.state.kicking_this_drive = game.state.away_team
    for side in game.state.teams:
        game.get_reserves(side).extend(side.players)
    return game, game.state.home_team


def test_formation_must_field_an_available_captain_among_sixteen_players():
    rules = load_rule_set('BB2025')
    team = Team('captain-test', 'Captain test', 'Human')
    role = rules.get_role('Human Lineman', 'Human')
    for i in range(16):
        team.players.append(Player(str(i), role, str(i), i + 1, team))
    team.nominate_captain(team.players[-1])
    team.players[-1].extra_st = -2
    team.players[-1].extra_ma = -2
    game, team = make_setup_game(team)
    setup = Setup(game, team)
    setup.start()
    coach = MyScriptedBot('setup')
    for action in coach.off_formation.actions(game, team):
        setup.step(action)
    captain = game.get_player(team.captain_id)
    assert captain.position is not None and game.is_setup_legal(team)
    position = captain.position
    game.pitch_to_reserves(captain)
    replacement = next(p for p in game.get_reserves(team) if p != captain)
    game.reserves_to_pitch(replacement, position)
    assert not game.is_setup_legal(team)
    captain.state.heated = True
    assert game.is_setup_legal(team)


@pytest.mark.parametrize('die', [1, 2, 3])
def test_swarming_adds_only_reserve_linemen_after_eleven_and_preserves_wing_limits(die):
    game, team = make_setup_game(build_team(next(coverage_squads('snotling'))))
    players = sorted(team.players, key=lambda p: 'Lineman' in p.role.keywords)
    squares = [(14, y) for y in (6, 7, 8)] + [(20, y) for y in (2, 3, 6, 7, 8, 9, 10, 11)]
    for player, (x, y) in zip(players, squares):
        game.reserves_to_pitch(player, game.get_square(x, y))
    assert game.is_setup_legal(team)
    proc = Swarming(game, team)
    with only_fixed_rolls(game, d3=[die]):
        proc.start()
    for _ in range(die):
        choice = proc.available_actions()[0]
        assert all('Lineman' in p.role.keywords for p in choice.players)
        assert all(s.y not in (1, 2, 3, 4) for s in choice.positions)
        player, square = choice.players[0], choice.positions[0]
        proc.step(Action(ActionType.PLACE_PLAYER, player=player, position=square))
    assert len(game.get_players_on_pitch(team)) == 11 + die
    assert game.is_setup_legal_wings(team)
    assert proc.available_actions() == []


def test_swarming_can_be_declined_and_ignores_unavailable_reserves():
    game, team = make_setup_game(build_team(next(coverage_squads('snotling'))))
    proc = Swarming(game, team)
    with only_fixed_rolls(game, d3=[3]):
        proc.start()
    assert proc.step(Action(ActionType.END_SETUP))
    assert not game.get_players_on_pitch(team)
    for player in team.players:
        player.state.heated = True
    unavailable = Swarming(game, team)
    with only_fixed_rolls(game):
        unavailable.start()
    assert not unavailable.available_actions()
