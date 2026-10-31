"""Selected Season 3 kick-off, weather, injury and drive-flow scenarios."""
import pytest
from tests.util import *
from tests.game.test_season3 import season3_turn


def run_proc(game, proc):
    proc.start()
    proc.started = True
    top = game.get_procedure()
    if not top.started:
        top.start()
        top.started = True
    game.set_available_actions()
    if not game.get_available_actions():
        game.step()


def kickoff_game(positions=None, opponents=None):
    game, players = season3_turn(positions or [(20, 5)], opponents or [(10, 5)], ball=(10, 10))
    game.state.kicking_this_drive = players[0].team
    game.state.receiving_this_drive = game.get_opp_team(players[0].team)
    game.get_ball().on_ground = False
    return game, players


@pytest.mark.parametrize('sum_,expected', [(2, WeatherType.SWELTERING_HEAT), (3, WeatherType.VERY_SUNNY),
    (4, WeatherType.NICE), (10, WeatherType.NICE), (11, WeatherType.POURING_RAIN), (12, WeatherType.BLIZZARD)])
def test_weather_table_boundaries(sum_, expected):
    game, _ = kickoff_game()
    with only_fixed_rolls(game, d6=[max(1, sum_ - 6), min(6, sum_ - 1)]):
        run_proc(game, WeatherTable(game))
    assert game.state.weather == expected


def test_fans_use_d3_plus_prepared_dedicated_fans_not_fame():
    game, _ = kickoff_game()
    with only_fixed_rolls(game, d3=[1, 3]):
        run_proc(game, Fans(game))
    assert [t.state.fan_factor for t in game.state.teams] == [4, 6]
    assert game.state.spectators == 10000
    assert all(t.state.fame == 0 for t in game.state.teams)


@pytest.mark.parametrize('marker,effect', [(0, 1), (5, 1), (6, -1), (7, -1), (8, -1)])
def test_time_out_has_no_extra_roll_and_uses_kicking_marker(marker, effect):
    game, _ = kickoff_game()
    for team in game.state.teams:
        team.state.turn = marker
    with only_fixed_rolls(game):
        run_proc(game, TimeOut(game))
    assert all(t.state.turn == marker + effect for t in game.state.teams)


@pytest.mark.parametrize('tie', [False, True])
def test_cheering_fans_grants_assist_not_reroll(tie):
    game, (player, opponent) = kickoff_game()
    for t in game.state.teams:
        t.state.fame = 99  # Not used in Season 3.
        t.cheerleaders = 0
    with only_fixed_rolls(game, d6=[6, 6 if tie else 1]):
        run_proc(game, CheeringFans(game))
    assert game.state.home_team.state.cheering_fans
    assert game.state.away_team.state.cheering_fans == tie
    assert all(t.state.rerolls == 0 for t in game.state.teams)


def test_cheering_assist_is_consumed_by_first_performed_block_including_blitz():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)])
    attacker.team.state.cheering_fans = True
    assert game.num_block_dice(attacker, defender) == 2
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH] * 2):
        game.step(Action(ActionType.START_BLITZ, player=attacker))
        game.step(Action(ActionType.SELECT_PLAYER, player=defender))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.SELECT_PUSH))
    assert not attacker.team.state.cheering_fans
    assert isinstance(game.get_procedure(), Push)


def test_cheering_expires_at_end_of_next_turn_even_if_no_block():
    game, (player,) = season3_turn([(10, 5)])
    player.team.state.cheering_fans = True
    game.step(Action(ActionType.END_TURN))
    assert not player.team.state.cheering_fans


@pytest.mark.parametrize('use_free', [False, True])
def test_brilliant_coaching_reroll_is_spent_first_or_expires_with_drive(use_free):
    game, (player, _) = kickoff_game()
    for team in game.state.teams:
        team.state.rerolls = 2
    with only_fixed_rolls(game, d6=[6, 1]):
        run_proc(game, BrilliantCoaching(game))
    team = game.state.home_team
    assert team.state.rerolls == 3 and team.state.drive_rerolls == 1
    if use_free:
        team.state.use_reroll()
    with only_fixed_rolls(game):
        run_proc(game, EndDrive(game))
    assert team.state.rerolls == 2
    assert team.state.drive_rerolls == 0


@pytest.mark.parametrize('snack_roll', [1, 2, 6])
def test_dodgy_snack_effect_and_expiry(snack_roll):
    game, (player, opponent) = kickoff_game()
    ma, av = player.get_ma(), player.get_av()
    with only_fixed_rolls(game, d6=[1, 6, snack_roll]):
        run_proc(game, DodgySnack(game))
    if snack_roll == 1:
        assert player.position is None and player.state.snack_absent
    else:
        assert player.get_ma() == ma - 1 and player.get_av() == av - 1
    assert not opponent.state.dodgy_snack and not opponent.state.snack_absent
    with only_fixed_rolls(game):
        run_proc(game, EndDrive(game))
    assert player.get_ma() == ma and player.get_av() == av
    assert not player.state.snack_absent


def test_end_drive_heat_removal_expires_ball_possession_without_a_bounce():
    game, (carrier,) = season3_turn([(10, 5)], ball=(10, 5))
    game.state.weather = WeatherType.SWELTERING_HEAT
    assert game.get_ball_carrier() == carrier
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, EndDrive(game))
    assert carrier.position is None and carrier.state.heated
    assert not game.get_ball().is_carried
    assert game.get_ball_carrier() is None
    assert not game.has_report_of_type(OutcomeType.BALL_BOUNCED)


def test_dodgy_snack_tie_affects_both_teams():
    game, (home, away) = kickoff_game()
    with only_fixed_rolls(game, d6=[4, 4, 2, 1]):
        run_proc(game, DodgySnack(game))
    assert home.state.dodgy_snack
    assert away.state.snack_absent


def test_pitch_invasion_uses_fan_factor_and_stuns_d3_distinct_players():
    game, (home, away) = kickoff_game()
    home.team.state.fan_factor = 1
    away.team.state.fan_factor = 5
    with only_fixed_rolls(game, d6=[1, 1], d3=[3]):
        # Home loses regardless of legacy FAME. Only one player is present, so
        # cap the sample rather than selecting the same player three times.
        run_proc(game, Season3PitchInvasion(game))
    assert home.state.stunned and not home.state.up
    assert not away.state.stunned


def test_pitch_invasion_tie_affects_both_teams():
    game, (home, away) = kickoff_game()
    with only_fixed_rolls(game, d6=[2, 2], d3=[1, 1]):
        run_proc(game, Season3PitchInvasion(game))
    assert home.state.stunned and away.state.stunned


@pytest.mark.parametrize('quick', [False, True])
def test_kickoff_selection_is_limited_to_initial_open_players(quick):
    game, (open_player, marked, opponent) = kickoff_game([(10, 5), (13, 5)], [(14, 5)])
    team = open_player.team
    if quick:
        game.state.receiving_this_drive = team
        game.state.kicking_this_drive = opponent.team
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, Turn(game, team, None, None, quick_snap=quick, blitz=not quick))
    assert isinstance(game.get_procedure(), KickoffSelection)
    selection = game.get_procedure()
    assert selection.limit == 4
    assert selection.eligible == [open_player]
    game.step(Action(ActionType.SELECT_PLAYER, player=open_player))
    turn = game.current_turn()
    assert turn.kickoff_players == [open_player]
    assert all(marked not in a.players for a in game.get_available_actions())
    types = {a.action_type for a in game.get_available_actions()}
    assert types <= {ActionType.START_MOVE, ActionType.START_BLITZ, ActionType.END_TURN}
    assert team.state.turn == 1


def test_quick_snap_moves_one_square_without_activation_or_dice_and_can_cross_half():
    game, (player, opponent) = kickoff_game([(14, 5)], [(10, 5)])
    game.state.receiving_this_drive, game.state.kicking_this_drive = player.team, opponent.team
    player.state.distracted = True
    player.extra_skills = [Skill.BONE_HEAD]
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, Turn(game, player.team, None, None, quick_snap=True))
    with only_fixed_rolls(game):
        game.step(Action(ActionType.SELECT_PLAYER, player=player))
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(13, 5)))
    assert player.position == Square(13, 5)
    assert player.state.distracted and player.state.used
    assert game.get_ball().on_ground is False
    assert all(player not in a.players for a in game.get_available_actions())


def test_charge_rush_failure_ends_bonus_before_other_selected_players_activate():
    game, (player, other, opponent) = kickoff_game([(10, 5), (10, 7)], [(20, 5)])
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, Turn(game, player.team, None, None, blitz=True))
    game.step(Action(ActionType.SELECT_PLAYER, player=player))
    game.step(Action(ActionType.SELECT_PLAYER, player=other))
    player.state.moves = player.get_ma()
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(11, 5)))
    assert not game.current_turn().blitz
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not other.state.used
    assert not player.state.up


@pytest.mark.parametrize('starting_weather', [WeatherType.NICE, WeatherType.POURING_RAIN])
def test_changing_to_perfect_conditions_always_scatters_three_in_air(starting_weather):
    game, _ = kickoff_game()
    game.state.weather = starting_weather
    game.get_ball().move_to(Square(10, 10))
    with only_fixed_rolls(game, d6=[3, 4]):
        run_proc(game, WeatherTable(game, kickoff=True))
    assert game.state.gentle_gust
    with only_fixed_rolls(game, d8=[4, 4, 4, 7]):  # 3 scatters, then landing bounce.
        run_proc(game, LandKick(game, game.get_ball()))
    assert game.get_ball_position() == Square(7, 11)
    assert not game.state.gentle_gust


@pytest.mark.parametrize('value,classification', [(1, 'BADLY_HURT'), (8, 'BADLY_HURT'),
    (9, 'SERIOUSLY_HURT'), (10, 'SERIOUSLY_HURT'), (11, 'SERIOUS_INJURY'), (12, 'SERIOUS_INJURY'),
    (13, 'LASTING_INJURY'), (14, 'LASTING_INJURY'), (15, 'DEAD'), (16, 'DEAD')])
def test_d16_casualty_table_boundaries(value, classification):
    game, (player,) = season3_turn([(10, 5)])
    with only_fixed_rolls(game, d16=[value]):
        run_proc(game, Casualty(game, player))
    assert player in game.get_casualties(player.team)
    report = next(r for r in game.state.reports if r.outcome_type == OutcomeType.CASUALTY_RESULT)
    assert report.n == classification
    assert report.rolls[0].to_json()['dice'][0] == {'die_type': 'D16', 'result': value}


@pytest.mark.parametrize('injury,d16,outcome', [([1, 1], [], OutcomeType.STUNNED),
    ([3, 4], [], OutcomeType.STUNNED), ([4, 4], [], OutcomeType.KNOCKED_OUT),
    ([4, 5], [], OutcomeType.KNOCKED_OUT), ([5, 5], [1], OutcomeType.CASUALTY_RESULT),
    ([6, 6], [16], OutcomeType.DEAD)])
def test_standard_injury_table_boundaries(injury, d16, outcome):
    game, (player,) = season3_turn([(10, 5)])
    with only_fixed_rolls(game, d6=injury, d16=d16):
        run_proc(game, Injury(game, player))
    assert game.has_report_of_type(outcome)


def test_crowd_stun_goes_to_reserves_and_no_armour_roll():
    game, (player,) = season3_turn([(10, 5)])
    with only_fixed_rolls(game, d6=[3, 4]):
        run_proc(game, Injury(game, player, in_crowd=True))
    assert player in game.get_reserves(player.team)
    assert not game.has_report_of_type(OutcomeType.ARMOR_BROKEN)


@pytest.mark.parametrize('success', [False, True])
def test_ko_recovery_once_at_end_of_drive_before_expiring_effects(success):
    game, (player,) = season3_turn([(10, 5)])
    game.pitch_to_kod(player)
    player.team.state.rerolls = player.team.state.drive_rerolls = 1
    with only_fixed_rolls(game, d6=[4 if success else 3]):
        run_proc(game, EndDrive(game))
    assert (player in game.get_reserves(player.team)) == success
    assert (player in game.get_knocked_out(player.team)) != success
    types = [r.outcome_type for r in game.state.reports]
    assert types.index(OutcomeType.PLAYER_READY if success else OutcomeType.PLAYER_NOT_READY) < types.index(OutcomeType.DRIVE_ENDED)
    assert player.team.state.rerolls == 0
    assert not game.state.drive_active


def test_heat_uses_one_shared_d3_and_excludes_only_next_drive():
    game, (player, opponent) = kickoff_game()
    game.state.weather = WeatherType.SWELTERING_HEAT
    reserve = game.get_reserves(player.team)[0]
    reserve.state.heated = True  # Has already missed this drive.
    with only_fixed_rolls(game, d3=[2]):
        run_proc(game, EndDrive(game))
    assert player.state.heated and opponent.state.heated
    assert not reserve.state.heated
    assert player in game.get_reserves(player.team)
    with only_fixed_rolls(game):
        run_proc(game, StartDrive(game))
    assert isinstance(game.get_procedure(), Setup)
    assert all(player not in a.players for a in game.get_available_actions())
    assert player.state.heated


def test_touchback_without_standing_players_is_coachs_empty_square_choice():
    game, (home, receiver) = kickoff_game()
    receiver.state.up = False
    run_proc(game, Touchback(game, game.get_ball()))
    choice = game.get_available_actions()[0]
    assert choice.action_type == ActionType.PLACE_BALL
    assert receiver.position not in choice.positions
    with only_fixed_rolls(game):
        game.step(Action(ActionType.PLACE_BALL, position=Square(10, 8)))
    assert game.get_ball_position() == Square(10, 8)
    assert not game.get_ball().is_carried


@pytest.mark.parametrize('result,proc_type,outcome', [
    (2, GetTheRef, OutcomeType.KICKOFF_GET_THE_REF), (3, TimeOut, OutcomeType.KICKOFF_TIME_OUT),
    (4, SolidDefence, OutcomeType.KICKOFF_SOLID_DEFENCE), (5, HighKick, OutcomeType.KICKOFF_HIGH_KICK),
    (6, CheeringFans, OutcomeType.KICKOFF_CHEERING_FANS), (7, BrilliantCoaching, OutcomeType.KICKOFF_BRILLIANT_COACHING),
    (8, WeatherTable, OutcomeType.KICKOFF_CHANGING_WHEATHER), (9, Turn, OutcomeType.KICKOFF_QUICK_SNAP),
    (10, Turn, OutcomeType.KICKOFF_CHARGE), (11, DodgySnack, OutcomeType.KICKOFF_DODGY_SNACK),
    (12, Season3PitchInvasion, OutcomeType.KICKOFF_PITCH_INVASION)])
def test_all_kickoff_table_results_dispatch_correct_event(result, proc_type, outcome):
    game, _ = kickoff_game()
    table = KickoffTable(game, game.get_ball())
    with only_fixed_rolls(game, d6=[max(1, result - 6), min(6, result - 1)]):
        table.step(None)
    assert isinstance(game.get_procedure(), proc_type)
    assert game.has_report_of_type(outcome)


def full_setup_game():
    config = load_config('season3-preview')
    rules = load_rule_set(config.ruleset)
    game = Game('flow-test', load_team_by_filename('human', rules), load_team_by_filename('human', rules),
                Agent('home', human=True), Agent('away', human=True), config, ruleset=rules, seed=0)
    game.init()
    game.step(Action(ActionType.START_GAME))
    game.step(Action(ActionType.HEADS))
    game.step(Action(ActionType.KICK))
    for _ in range(2):
        choice = next(a for a in game.get_available_actions() if a.action_type in (
            ActionType.SETUP_FORMATION_ZONE, ActionType.SETUP_FORMATION_WEDGE))
        game.step(Action(choice.action_type))
        game.step(Action(ActionType.END_SETUP))
    return game


def test_solid_defence_selects_before_reposition_and_keeps_others_fixed():
    game = full_setup_game()
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, SolidDefence(game))
    proc = game.get_procedure()
    team = proc.team
    initial = {p.player_id: p.position for p in game.get_players_on_pitch(team)}
    assert len(proc.eligible) > 4
    assert all(p.state.up and not game.num_tackle_zones_in(p) for p in proc.eligible)
    selected = proc.eligible[:4]
    for player in selected:
        game.step(Action(ActionType.SELECT_PLAYER, player=player))
    assert not proc.selecting
    assert all(p.position is None for p in selected)
    choices = game.get_available_actions()
    place = next(a for a in choices if a.action_type == ActionType.PLACE_PLAYER)
    assert place.players == selected
    assert not any(a.action_type in (ActionType.SETUP_FORMATION_ZONE, ActionType.SETUP_FORMATION_SPREAD) for a in choices)
    for player in selected:
        game.step(Action(ActionType.PLACE_PLAYER, player=player, position=initial[player.player_id]))
    assert game.is_setup_legal(team)
    game.step(Action(ActionType.END_SETUP))
    assert all(p.position == initial[p.player_id] for p in game.get_players_on_pitch(team))


@pytest.mark.parametrize('marker', [0, 5, 6, 7])
def test_time_out_changes_actual_remaining_turns_not_only_display(marker):
    game, _ = kickoff_game()
    game.state.weather = WeatherType.NICE
    game.purge_stack_until(Half, inclusive=False)
    half = game.get_procedure()
    half.next_team = game.get_receiving_team()
    for team in game.state.teams:
        team.state.turn = marker
    game.state.reports.clear()
    with only_fixed_rolls(game):
        run_proc(game, TimeOut(game))
        while isinstance(game.get_procedure(), Turn):
            game.step(Action(ActionType.END_TURN))
    adjustment = -1 if marker >= 6 else 1
    turns = [r for r in game.state.reports if r.outcome_type == OutcomeType.TURN_START]
    for team in game.state.teams:
        assert [r.n for r in turns if r.team == team] == list(range(marker + adjustment + 1, 9))
    assert game.state.half == 2
    assert isinstance(game.get_procedure(), Setup)


def test_halftime_recovers_ko_once_and_restores_base_rerolls():
    game, (player, opponent) = kickoff_game()
    game.state.weather = WeatherType.NICE
    game.pitch_to_kod(player)
    game.purge_stack_until(Half, inclusive=False)
    half = game.get_procedure()
    half.next_team = player.team
    for team in game.state.teams:
        team.state.turn = 7
        team.state.rerolls = 1
        team.state.drive_rerolls = 1
    with only_fixed_rolls(game, d6=[4]):
        # Start the two final turns of the half.
        game.state.available_actions = []
        game.step()
        game.step(Action(ActionType.END_TURN))
        game.step(Action(ActionType.END_TURN))
    assert game.state.half == 2
    assert player in game.get_reserves(player.team)
    assert all(t.state.rerolls == t.rerolls and t.state.drive_rerolls == 0 for t in game.state.teams)
    assert len([r for r in game.state.reports if r.outcome_type == OutcomeType.PLAYER_READY and r.player == player]) == 1
    assert game.get_kicking_team() == game.state.receiving_first_half


def test_defensive_touchdown_skips_scorers_next_turn_and_sets_next_receiver():
    game, (home, scorer) = season3_turn([(20, 5)], [(26, 5)], ball=(26, 5))
    home.team.state.turn = 5
    scorer.team.state.turn = 4
    with only_fixed_rolls(game):
        run_proc(game, Touchdown(game, scorer))
    assert scorer.team.state.score == 1
    assert scorer.team.state.turn == 5
    assert game.get_kicking_team() == scorer.team
    assert game.get_receiving_team() == home.team
    half = next(p for p in game.state.stack.items if isinstance(p, Half) and p.half == 1)
    assert half.next_team == home.team
    assert game.has_report_of_type(OutcomeType.TURN_SKIPPED)


def test_last_turn_touchdown_runs_end_drive_without_another_kickoff():
    game, (player,) = season3_turn([(1, 5)], ball=(1, 5))
    game.state.stack.items.clear()
    EndGame(game)
    half = Half(game, 2)
    half.kicked_off = True
    half.next_team = game.get_opp_team(player.team)
    game.state.half = 2
    game.state.weather = WeatherType.NICE
    for team in game.state.teams:
        team.state.turn = 8
    turn = Turn(game, player.team, 2, 8)
    turn.start()
    turn.started = True
    game.state.reports.clear()
    with only_fixed_rolls(game):
        run_proc(game, Touchdown(game, player))
    assert game.state.game_over
    assert not game.state.drive_active
    assert len([r for r in game.state.reports if r.outcome_type == OutcomeType.DRIVE_ENDED]) == 1
    assert not game.has_report_of_type(OutcomeType.KICKER_NOMINATED)


@pytest.mark.parametrize('argue,bribe,spared,turnover,can_argue', [(6, None, True, True, True),
    (2, 2, True, False, True), (1, 2, True, False, False), (2, 1, False, True, True),
    (1, None, False, True, False)])
def test_argue_call_before_bribe_and_distinct_turnover_results(argue, bribe, spared, turnover, can_argue):
    game, (player,) = season3_turn([(10, 5)])
    player.team.state.bribes = int(bribe is not None)
    run_proc(game, Ejection(game, player))
    with only_fixed_rolls(game, d6=[argue] + ([bribe] if bribe is not None else [])):
        game.step(Action(ActionType.ARGUE_CALL))
        if bribe is not None:
            game.step(Action(ActionType.USE_BRIBE))
    assert (player.position is not None) == spared
    assert player.state.ejected != spared
    assert game.has_report_of_type(OutcomeType.TURNOVER) == turnover
    assert player.team.state.can_argue == can_argue


def test_double_armour_and_injury_only_offer_one_ejection_after_casualty():
    game, (fouler, victim) = season3_turn([(10, 5)], [(11, 5)])
    victim.state.up = False
    with only_fixed_rolls(game, d6=[5, 5, 5, 5], d16=[1]):
        game.step(Action(ActionType.START_FOUL, player=fouler))
        game.step(Action(ActionType.FOUL, position=victim.position))
    assert victim in game.get_casualties(victim.team)
    assert isinstance(game.get_procedure(), Ejection)
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.ARGUE_CALL))
    assert not fouler.state.ejected
    assert game.has_report_of_type(OutcomeType.TURNOVER)
    assert not isinstance(game.get_procedure(), Ejection)


@pytest.mark.parametrize('second,select_first,expected_reserves', [(1, False, True), (1, True, False), (16, False, False)])
def test_apothecary_uses_d16_and_badly_hurt_returns_to_reserves(second, select_first, expected_reserves):
    game, (player,) = season3_turn([(10, 5)])
    player.team.state.apothecaries = 1
    with only_fixed_rolls(game, d16=[15]):
        run_proc(game, Casualty(game, player))
    with only_fixed_rolls(game, d16=[second]):
        game.step(Action(ActionType.USE_APOTHECARY))
        game.step(Action(ActionType.SELECT_FIRST_ROLL if select_first else ActionType.SELECT_SECOND_ROLL))
    assert (player in game.get_reserves(player.team)) == expected_reserves
    assert player.team.state.apothecaries == 0


def test_search_reverses_dodgy_snack_and_drive_expiry():
    game, (player, _) = kickoff_game()
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[1, 6, 2]):
        run_proc(game, DodgySnack(game))
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after
    step = game.get_step()
    with only_fixed_rolls(game):
        run_proc(game, EndDrive(game))
    changes = game.revert(step)
    assert player.state.dodgy_snack
    game.forward(changes)
    assert not player.state.dodgy_snack


@pytest.mark.parametrize('implementation', ['python', 'cython'])
def test_blizzard_rush_target_and_restricted_pass_ranges(implementation):
    from botbowl.core.pathfinding import python_pathfinding
    pf = python_pathfinding if implementation == 'python' else pytest.importorskip('botbowl.core.pathfinding.cython_pathfinding')
    game, (player,) = season3_turn([(10, 5)], ball=(10, 5))
    game.state.weather = WeatherType.BLIZZARD
    player.state.moves = player.get_ma()
    path = pf.Pathfinder(game, player).get_path(Square(11, 5))
    assert list(path.rolls) == [[3]]
    assert path.prob == pytest.approx(4 / 6)
    positions, distances = game.get_pass_distances(player, game.get_ball())
    assert set(distances) == {PassDistance.QUICK_PASS, PassDistance.SHORT_PASS}
    with only_fixed_rolls(game, d6=[3]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(11, 5)))
    assert player.position == Square(11, 5)


def test_rain_modifies_ball_tests_and_sunny_modifies_pa():
    game, (player,) = season3_turn([(10, 5)], ball=(10, 5))
    game.state.weather = WeatherType.POURING_RAIN
    assert game.get_pickup_modifiers(player, player.position) == -1
    assert game.get_catch_modifiers(player, accurate=True) == -1
    assert game.get_catch_modifiers(player, interception=True, accurate=True) == -4
    game.state.weather = WeatherType.VERY_SUNNY
    assert game.get_pass_modifiers(player, PassDistance.QUICK_PASS) == -1


@pytest.mark.parametrize('crowd', [False, True])
def test_ko_apothecary_stuns_on_pitch_or_returns_crowd_victim_to_reserves(crowd):
    game, (player,) = season3_turn([(10, 5)])
    player.team.state.apothecaries = 1
    with only_fixed_rolls(game, d6=[4, 4]):
        run_proc(game, Injury(game, player, in_crowd=crowd))
    with only_fixed_rolls(game):
        game.step(Action(ActionType.USE_APOTHECARY))
    if crowd:
        assert player in game.get_reserves(player.team)
    else:
        assert player.position is not None and player.state.stunned and not player.state.up
    assert player.team.state.apothecaries == 0


def test_declining_apothecary_applies_original_casualty():
    game, (player,) = season3_turn([(10, 5)])
    player.team.state.apothecaries = 1
    with only_fixed_rolls(game, d16=[16]):
        run_proc(game, Casualty(game, player))
    with only_fixed_rolls(game):
        game.step(Action(ActionType.DONT_USE_APOTHECARY))
    assert player in game.get_casualties(player.team)
    assert game.has_report_of_type(OutcomeType.DEAD)
    assert player.team.state.apothecaries == 1


def test_search_reverses_selection_and_turn_marker_changes():
    game, (player, other, opponent) = kickoff_game([(20, 5), (20, 7)], [(10, 5)])
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, Turn(game, player.team, None, None, blitz=True))
    game.step(Action(ActionType.SELECT_PLAYER, player=player))
    game.step(Action(ActionType.SELECT_NONE))
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after
    assert game.current_turn().kickoff_players == [player]


def test_search_reverses_foul_casualty_and_argue_call():
    game, (fouler, victim) = season3_turn([(10, 5)], [(11, 5)])
    victim.state.up = False
    game.enable_forward_model()
    before = game.state.to_json(ignore_clocks=True)
    step = game.get_step()
    with only_fixed_rolls(game, d6=[5, 5, 5, 5], d16=[1]):
        game.step(Action(ActionType.START_FOUL, player=fouler))
        game.step(Action(ActionType.FOUL, position=victim.position))
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.ARGUE_CALL))
    after = game.state.to_json(ignore_clocks=True)
    changes = game.revert(step)
    assert game.state.to_json(ignore_clocks=True) == before
    game.forward(changes)
    assert game.state.to_json(ignore_clocks=True) == after


def test_cheering_assist_remains_on_a_rerolled_block_and_is_not_reused_later():
    game, (attacker, defender) = season3_turn([(10, 5)], [(11, 5)], rerolls=1)
    attacker.team.state.cheering_fans = True
    with only_fixed_rolls(game, block_dice=[BBDieResult.ATTACKER_DOWN] * 2 + [BBDieResult.PUSH] * 2):
        game.step(Action(ActionType.START_BLOCK, player=attacker))
        game.step(Action(ActionType.BLOCK, position=defender.position))
        game.step(Action(ActionType.USE_REROLL))
        game.step(Action(ActionType.SELECT_PUSH))
    rolls = [r.rolls[0] for r in game.state.reports if r.outcome_type == OutcomeType.BLOCK_ROLL]
    assert [len(r.dice) for r in rolls] == [2, 2]
    assert not attacker.team.state.cheering_fans
    assert game.num_block_dice(attacker, defender) == 1


def test_setup_requires_all_available_players_and_excludes_heat():
    game = full_setup_game()
    team = game.get_kicking_team()
    player = game.get_players_on_pitch(team)[0]
    game.pitch_to_reserves(player)
    assert not game.is_setup_legal_count(team)
    # Eleven available from twelve still requires eleven on the pitch.
    reserve = next(p for p in game.get_reserves(team) if p != player)
    reserve.state.heated = True
    assert not game.is_setup_legal_count(team)
    player.state.heated = True  # Only ten can play now.
    assert game.is_setup_legal_count(team)


def test_web_api_exposes_selection_limit_and_keeps_charge_decision_with_kicking_coach(monkeypatch):
    from botbowl.web import server
    from botbowl.web.host import InMemoryHost
    game, (player, other, _) = kickoff_game([(20, 5), (20, 7)], [(10, 5)])
    game.game_id = 'charge-api'
    with only_fixed_rolls(game, d3=[2]):
        run_proc(game, Turn(game, player.team, None, None, blitz=True))
    host = InMemoryHost()
    host.add_game(game)
    monkeypatch.setattr(server.api, 'host', host)
    client = server.app.test_client()
    def act(kind, **kwargs):
        return json.loads(client.post('/games/charge-api/act', json={
            'action': {'action_type': kind, **kwargs}}).data)
    selected = act('SELECT_PLAYER', player_id=player.player_id)
    assert selected['kickoff_selection'] == {'event': 'Charge', 'limit': 5, 'selected': 1}
    assert selected['state']['available_actions'][0]['team_id'] == player.team.team_id
    finished = act('SELECT_NONE')
    assert finished['kickoff_selection'] is None
    assert game.current_turn().kickoff_players == [player]
    assert all(other not in a.players for a in game.get_available_actions())


@pytest.mark.parametrize('quick', [False, True])
def test_real_kickoff_initializes_nested_selection_and_lands_ball_after_bonus(quick):
    game, (player, other, opponent) = kickoff_game([(20, 5), (20, 7)], [(10, 5)])
    game.purge_stack_until(Half, inclusive=False)
    if quick:
        game.state.kicking_this_drive, game.state.receiving_this_drive = opponent.team, player.team
        game.get_ball().move_to(Square(20, 10))
    game.get_procedure().next_team = game.get_receiving_team()
    game.state.current_team = None
    for team in game.state.teams:
        team.state.turn = 0
    LandKick(game, game.get_ball())
    with only_fixed_rolls(game, d6=[3, 6] if quick else [4, 6], d3=[3]):
        run_proc(game, KickoffTable(game, game.get_ball()))
    assert isinstance(game.get_procedure(), KickoffSelection)
    assert game.get_procedure().started
    assert game.get_procedure().limit == 6
    assert not game.get_ball().on_ground
    game.step(Action(ActionType.SELECT_PLAYER, player=player))
    game.step(Action(ActionType.SELECT_NONE))
    with only_fixed_rolls(game, d8=[7]):
        game.step(Action(ActionType.END_TURN))
    assert game.get_ball().on_ground
    assert game.current_turn().team == game.get_receiving_team()
    assert game.state.current_team == game.get_receiving_team()
    assert game.current_turn().turn == 1
    assert not game.current_turn().blitz and not game.current_turn().quick_snap


def test_random_bot_can_complete_solid_defence_without_formation_macros():
    from botbowl.ai.bots.random_bot import RandomBot
    game = full_setup_game()
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, SolidDefence(game))
    proc = game.get_procedure()
    player = proc.eligible[0]
    game.step(Action(ActionType.SELECT_PLAYER, player=player))
    game.step(Action(ActionType.END_SETUP))
    assert player.position is None
    bot = RandomBot('random', seed=0)
    action = bot.act(game)
    assert action.action_type == ActionType.PLACE_PLAYER
    assert game._is_action_allowed(action)
    game.step(action)
    action = bot.act(game)
    assert action.action_type == ActionType.END_SETUP
    game.step(action)
    assert not isinstance(game.get_procedure(), SolidDefence)
