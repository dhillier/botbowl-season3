"""Season 3 RL contract, coach ownership, completeness and engine round trips."""
from copy import deepcopy

import gym
import numpy as np
import pytest

import botbowl
from botbowl.ai.season3_actions import (
    SIMPLE_ACTIONS, POSITION_ACTIONS, PLAYER_ACTIONS, Season3ActionCodec, SQUARES)
from botbowl.ai.season3_env import (
    Season3Adapter, Season3Env, PLAYER_FEATURES, SPATIAL_FEATURES, GLOBAL_FEATURES, ROLL_FEATURES)
from tests.game.test_season3 import season3_turn, pass_ball
from tests.game.test_season3_flow import full_setup_game, run_proc
from tests.util import only_fixed_rolls
from botbowl.core.procedure import (
    Action, ActionChoice, ActionType, Square, Skill, WeatherType, Reroll, Interception,
    SolidDefence, Turn, KickoffSelection, Casualty, Apothecary, BBDieResult)


def wrap(game):
    env = Season3Env(pathfinding=game.config.pathfinding_enabled)
    env.game, env.adapter = game, Season3Adapter(game)
    env.game_seed, env.decisions, env._finished = 0, 0, False
    return env


def step_action(env, kind, player=None, position=None):
    index = env.adapter.codec().encode(Action(kind, player=player, position=position))
    return env.step(index)


def at(observation, name, player, codec):
    return observation['players'][codec.players.index(player), PLAYER_FEATURES.index(name)]


@pytest.mark.parametrize('name', ['botbowl-s3-v1', 'botbowl-s3-pathfinding-v1'])
def test_registered_spaces_seed_and_gym026_returns(name):
    env = gym.make(name)
    observation, info = env.reset(seed=12)
    assert env.action_space.n == len(observation['action_mask']) == 10256
    assert env.observation_space.contains(observation)
    assert info['actor'] == 1  # Away coach starts/chooses coin face.
    expected = deepcopy(observation)
    first = deepcopy(info)
    observation, info = env.reset(seed=12)
    for key in observation:
        np.testing.assert_array_equal(observation[key], expected[key])
    assert info == first
    for _ in range(4):
        result = env.step(env.action_space.sample(mask=observation['action_mask']))
        assert len(result) == 5
        observation, reward, terminated, truncated, info = result
        assert env.observation_space.contains(observation)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool) and isinstance(truncated, bool)
    env.close()


def test_legacy_environment_stays_on_its_existing_contract():
    env = botbowl.BotBowlEnv(botbowl.EnvConf(size=1), seed=5)
    assert env.ruleset.name == 'BB2016'
    assert len(env.reset()) == 3
    assert ActionType.START_SECURE_BALL not in env.env_conf.action_types
    with pytest.raises(ValueError, match='BB2025'):
        Season3Adapter(env.game)
    legacy_conf = botbowl.EnvConf()
    legacy_conf.config.ruleset = 'BB2025'
    with pytest.raises(ValueError, match='Legacy v4'):
        botbowl.BotBowlEnv(legacy_conf)


@pytest.mark.parametrize('away', [False, True])
def test_every_index_round_trips_including_off_pitch_roster_slots(away):
    game, _ = season3_turn([(5, 5)], [(7, 5)])
    team = game.state.away_team if away else game.state.home_team
    codec = Season3ActionCodec(game, team)
    for index in range(codec.size):
        assert codec.encode(codec.decode(index)) == index
    reserve = next(p for p in team.players if p.position is None)
    for position in (None, Square(3, 4)):
        action = Action(ActionType.PLACE_PLAYER, player=reserve, position=position)
        decoded = codec.decode(codec.encode(action))
        assert decoded.player == reserve and decoded.position == position


@pytest.mark.parametrize('invalid', [-1, 10256, 1.5, '0', True, np.bool_(False), None])
def test_invalid_or_masked_indices_fail_without_changing_game(invalid):
    env = Season3Env()
    env.reset(seed=5)
    before = env.game.state.to_json(ignore_clocks=True)
    rng_before = env.game.rng.get_state()
    with pytest.raises(ValueError):
        env.step(invalid)
    assert env.game.state.to_json(ignore_clocks=True) == before
    np.testing.assert_equal(env.game.rng.get_state(), rng_before)
    with pytest.raises(ValueError, match='Masked'):
        env.step(SIMPLE_ACTIONS.index(ActionType.END_TURN))
    assert env.decisions == 0


def test_setup_mask_has_real_player_square_pairs_and_requires_legal_formation():
    env = Season3Env()
    env.reset(seed=1)
    for kind in (ActionType.START_GAME, ActionType.HEADS, ActionType.KICK):
        step_action(env, kind)
    codec = env.adapter.codec()
    observation = env.adapter.observe()
    assert not observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.END_SETUP)]
    reserve = codec.team.players[0]
    destination = env.game.get_team_side(codec.team)[0]
    index = codec.encode(Action(ActionType.PLACE_PLAYER, player=reserve, position=destination))
    assert observation['action_mask'][index]
    env.step(index)
    assert reserve.position == destination
    codec = env.adapter.codec()
    other = next(p for p in codec.team.players if p.position is None)
    blocked = codec.encode(Action(ActionType.PLACE_PLAYER, player=other, position=destination))
    assert not env.adapter.observe()['action_mask'][blocked]
    to_bench = codec.encode(Action(ActionType.PLACE_PLAYER, player=reserve))
    assert env.adapter.observe()['action_mask'][to_bench]
    env.step(to_bench)
    assert reserve.position is None
    step_action(env, ActionType.SETUP_FORMATION_ZONE)
    assert env.adapter.observe()['action_mask'][SIMPLE_ACTIONS.index(ActionType.END_SETUP)]
    step_action(env, ActionType.END_SETUP)


def test_masks_merge_duplicate_choices_and_exclude_disabled_actions():
    game, (player, second) = season3_turn([(5, 5), (7, 5)])
    team = player.team
    game.state.available_actions = [
        ActionChoice(ActionType.START_MOVE, team, players=[player]),
        ActionChoice(ActionType.START_MOVE, team, players=[second]),
        ActionChoice(ActionType.END_TURN, team, disabled=True)]
    codec = Season3ActionCodec(game)
    legal, _ = codec.legal_actions()
    assert set(legal) == {codec.encode(Action(ActionType.START_MOVE, player=p)) for p in (player, second)}


def test_unknown_or_ambiguous_decisions_fail_instead_of_returning_partial_mask():
    game, (player, opponent) = season3_turn([(5, 5)], [(7, 5)])
    codec = Season3ActionCodec(game)
    game.state.available_actions = [ActionChoice(ActionType.LEAP, player.team, positions=[Square(7, 5)])]
    with pytest.raises(ValueError, match='Unencoded'):
        codec.legal_actions()
    game.state.available_actions = [ActionChoice(ActionType.END_TURN, opponent.team)]
    with pytest.raises(ValueError, match='different coaches'):
        codec.legal_actions()


@pytest.mark.parametrize('pathfinding', [False, True])
def test_secure_and_jump_actions_previews_and_resolution(pathfinding):
    game, (player, downed) = season3_turn([(5, 5), (6, 5)], ball=(7, 5))
    game.config.pathfinding_enabled = pathfinding
    game.state.weather = WeatherType.POURING_RAIN
    downed.state.up = False
    env = wrap(game)
    observation = env.adapter.observe()
    start = env.adapter.codec().encode(Action(ActionType.START_SECURE_BALL, player=player))
    assert observation['action_mask'][start]
    env.step(start)
    codec = env.adapter.codec()
    jump = codec.encode(Action(ActionType.JUMP, position=Square(7, 5)))
    observation = env.adapter.observe()
    assert observation['action_mask'][jump]
    assert observation['action_features'][jump, 0] == pytest.approx((4 / 6) ** 2)
    with only_fixed_rolls(game, d6=[3, 3]):
        observation, *_ = env.step(jump)
    assert game.has_ball(player) and player.state.used
    assert not observation['global'][GLOBAL_FEATURES.index('secure_ball_available')]


def test_blitz_target_is_opponent_identity_and_forego_has_its_own_action():
    game, (player, target, other) = season3_turn([(5, 5)], [(6, 5), (8, 5)])
    env = wrap(game)
    codec = env.adapter.codec()
    forego = codec.encode(Action(ActionType.FOREGO_ACTIVATION, player=player))
    assert env.adapter.observe()['action_mask'][forego]
    step_action(env, ActionType.START_BLITZ, player=player)
    codec = env.adapter.codec()
    index = codec.encode(Action(ActionType.SELECT_PLAYER, player=target))
    assert (index - codec.player_offset) % 24 >= 12
    assert env.adapter.observe()['action_mask'][index]
    env.step(index)
    observation = env.adapter.observe()
    x = 27 - target.position.x if codec.flip else target.position.x
    assert observation['spatial'][SPATIAL_FEATURES.index('declared_target'), target.position.y, x] == 1
    block = next(a for a in game.get_available_actions() if a.action_type == ActionType.BLOCK)
    assert block.positions == [target.position]


def test_interception_changes_perspective_to_defending_coach_and_back():
    game, (passer, catcher, defender) = season3_turn([(3, 5), (10, 5)], [(6, 5)], ball=(3, 5))
    env = wrap(game)
    with only_fixed_rolls(game, d6=[6]):
        step_action(env, ActionType.START_PASS, player=passer)
        observation, _, _, _, info = step_action(env, ActionType.PASS, position=catcher.position)
    assert isinstance(game.get_procedure(), Interception)
    assert info['decision']['actor'] != info['actor']
    codec = env.adapter.codec()
    assert codec.team == defender.team and codec.players.index(defender) < 12
    assert at(observation, 'on_pitch', defender, codec) == 1
    assert observation['global'][GLOBAL_FEATURES.index('current_team_is_actor')] == 0
    x = 27 - catcher.position.x if codec.flip else catcher.position.x
    assert observation['spatial'][SPATIAL_FEATURES.index('pass_landing'), catcher.position.y, x] == 1
    assert observation['spatial'][SPATIAL_FEATURES.index('ball_airborne'), catcher.position.y, x] == 1
    with only_fixed_rolls(game, d6=[3]):
        observation, _, _, _, info = step_action(env, ActionType.SELECT_NONE)
    assert game.has_ball(catcher)
    assert env.adapter.codec().team == passer.team
    assert not observation['spatial'][SPATIAL_FEATURES.index('ball_airborne')].any()


def test_pending_reroll_observes_public_die_and_chosen_movement_destination():
    game, (player,) = season3_turn([(5, 5)], ball=(20, 10), rerolls=2)
    env = wrap(game)
    step_action(env, ActionType.START_MOVE, player=player)
    player.state.moves = player.get_ma()
    with only_fixed_rolls(game, d6=[1]):
        observation, *_ = step_action(env, ActionType.MOVE, position=Square(6, 5))
    assert isinstance(game.get_procedure(), Reroll)
    codec = env.adapter.codec()
    x = 21 if codec.flip else 6
    assert observation['spatial'][SPATIAL_FEATURES.index('test_destination'), 5, x] == 1
    assert observation['public_rolls'][0, ROLL_FEATURES.index('die_1')] == pytest.approx(1 / 16)
    assert observation['global'][GLOBAL_FEATURES.index('reroll_GFI')] == 1
    with only_fixed_rolls(game, d6=[2]):
        observation, *_ = step_action(env, ActionType.USE_REROLL)
    assert player.team.state.rerolls == 1
    assert observation['global'][GLOBAL_FEATURES.index('own_can_use_reroll')] == 1
    assert observation['global'][GLOBAL_FEATURES.index('own_reroll_used')] == 1


def test_pending_bounce_catch_is_airborne_until_caught_even_with_ground_flag_set():
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5), rerolls=1)
    game.get_ball().is_carried = False
    with only_fixed_rolls(game, d6=[1]):
        run_proc(game, botbowl.Catch(game, player, game.get_ball()))
    assert isinstance(game.get_procedure(), Reroll)
    env = wrap(game)
    observation = env.adapter.observe()
    assert observation['spatial'][SPATIAL_FEATURES.index('ball_airborne')].sum() == 1
    assert not observation['spatial'][SPATIAL_FEATURES.index('ball_carried')].any()
    with only_fixed_rolls(game, d6=[4]):
        observation, *_ = step_action(env, ActionType.USE_REROLL)
    assert observation['spatial'][SPATIAL_FEATURES.index('ball_carried')].sum() == 1
    assert not observation['spatial'][SPATIAL_FEATURES.index('ball_airborne')].any()


def test_per_action_previews_do_not_overwrite_jump_with_move_to_same_square():
    game, (player, downed) = season3_turn([(5, 5), (6, 5)])
    game.config.pathfinding_enabled = True
    downed.state.up = False
    env = wrap(game)
    step_action(env, ActionType.START_MOVE, player=player)
    codec, observation = env.adapter.codec(), env.adapter.observe()
    jump = codec.encode(Action(ActionType.JUMP, position=Square(7, 5)))
    move = codec.encode(Action(ActionType.MOVE, position=Square(7, 5)))
    assert observation['action_mask'][jump] and observation['action_mask'][move]
    assert observation['action_features'][jump, 0] == pytest.approx(4 / 6)
    assert observation['action_features'][move, 0] == 1


def test_disadvantaged_block_reroll_masks_dice_then_hands_selection_to_opponent():
    game, (attacker, defender) = season3_turn([(5, 5)], [(6, 5)], rerolls=1)
    defender.extra_st = 3
    env = wrap(game)
    step_action(env, ActionType.START_BLOCK, player=attacker)
    with only_fixed_rolls(game, block_dice=[BBDieResult.ATTACKER_DOWN, BBDieResult.DEFENDER_DOWN]):
        observation, *_ = step_action(env, ActionType.BLOCK, position=defender.position)
    assert env.adapter.codec().team == attacker.team
    assert observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.USE_REROLL)]
    assert not observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.SELECT_DEFENDER_DOWN)]
    observation, _, _, _, info = step_action(env, ActionType.DONT_USE_REROLL)
    assert env.adapter.codec().team == defender.team
    assert info['actor'] != info['decision']['actor']
    assert observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.SELECT_ATTACKER_DOWN)]
    assert observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.SELECT_DEFENDER_DOWN)]
    observation, *_ = step_action(env, ActionType.SELECT_DEFENDER_DOWN)
    assert env.adapter.codec().team == attacker.team  # Pushing remains attacker's choice.


@pytest.mark.parametrize('turn,roll,turnover', [(1, 1, True), (7, 6, False)])
def test_forego_activation_executes_stalling_through_the_rl_interface(turn, roll, turnover):
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    player.team.state.turn = turn
    env = wrap(game)
    with only_fixed_rolls(game, d6=[roll] + ([1, 1] if turnover else []), d8=[7] if turnover else []):
        step_action(env, ActionType.FOREGO_ACTIVATION, player=player)
    assert game.has_report_of_type(botbowl.OutcomeType.TURNOVER) == turnover


def test_argue_call_and_awarded_bribe_are_encoded_and_owned_by_fouling_coach():
    game, (player,) = season3_turn([(5, 5)])
    player.team.state.bribes = 1
    run_proc(game, botbowl.Ejection(game, player))
    env = wrap(game)
    assert env.adapter.codec().team == player.team
    with only_fixed_rolls(game, d6=[2, 2]):
        observation, *_ = step_action(env, ActionType.ARGUE_CALL)
        assert observation['action_mask'][SIMPLE_ACTIONS.index(ActionType.USE_BRIBE)]
        step_action(env, ActionType.USE_BRIBE)
    assert not player.state.ejected and player.team.state.bribes == 0


def test_planned_path_and_recovery_snapshot_survive_pending_rush():
    game, (player, stunned) = season3_turn([(5, 5), (10, 10)], ball=(20, 10), rerolls=1)
    game.config.pathfinding_enabled = True
    stunned.state.up = False
    stunned.state.stunned = True
    game.current_turn().stunned_at_start = [stunned]
    env = wrap(game)
    step_action(env, ActionType.START_MOVE, player=player)
    player.state.moves = player.get_ma()
    game.set_available_actions()
    with only_fixed_rolls(game, d6=[1]):
        observation, *_ = step_action(env, ActionType.MOVE, position=Square(7, 5))
    codec = env.adapter.codec()
    assert at(observation, 'stunned_at_turn_start', stunned, codec) == 1
    assert observation['spatial'][SPATIAL_FEATURES.index('remaining_path')].sum() > 0


def test_profiles_statuses_skills_reserves_and_resources_are_observed():
    game, (player, opponent) = season3_turn([(5, 5)], [(7, 5)], ball=(5, 5), rerolls=12)
    player.role = game.ruleset.get_role('Thrower', 'Human')
    player.state.distracted = True
    player.state.dodgy_snack = True
    game.get_ball().on_ground = False  # A carried ball must still not be labelled airborne.
    opponent.extra_skills = [Skill.DODGE, Skill.TACKLE]
    opponent.use_skill(Skill.DODGE)
    player.team.state.drive_rerolls = 2
    player.team.state.cheering_fans = True
    env = wrap(game)
    observation, codec = env.adapter.observe(), env.adapter.codec()
    assert at(observation, 'ag_target', player, codec) == pytest.approx(3 / 6)
    assert at(observation, 'pa_target', player, codec) == pytest.approx(3 / 6)
    assert at(observation, 'has_pass', player, codec) == 1
    assert at(observation, 'usable_pass', player, codec) == 0
    assert at(observation, 'can_mark', player, codec) == 0
    assert at(observation, 'dodgy_snack', player, codec) == 1
    assert at(observation, 'spent_dodge', opponent, codec) == 1
    assert at(observation, 'has_tackle', opponent, codec) == 1
    assert at(observation, 'ag_target', opponent, codec) == pytest.approx(3 / 6)
    assert at(observation, 'pa_target', opponent, codec) == pytest.approx(4 / 6)
    reserve = next(p for p in codec.team.players if p.position is None)
    assert at(observation, 'reserves', reserve, codec) == 1
    assert at(observation, 'can_mark', reserve, codec) == 0
    assert observation['global'][GLOBAL_FEATURES.index('own_rerolls')] == pytest.approx(12 / 13)
    assert observation['global'][GLOBAL_FEATURES.index('own_drive_rerolls')] == pytest.approx(2 / 3)
    assert env.observation_space.contains(observation)
    assert not observation['spatial'][SPATIAL_FEATURES.index('ball_airborne')].any()


@pytest.mark.parametrize('event', ['solid', 'quick', 'charge'])
def test_kickoff_group_selection_and_constrained_placements_are_encoded(event):
    game = full_setup_game()
    with only_fixed_rolls(game, d3=[1]):
        run_proc(game, SolidDefence(game) if event == 'solid' else
                 Turn(game, game.get_kicking_team(), 1, 1, quick_snap=event == 'quick', blitz=event == 'charge'))
    env = wrap(game)
    selection = game.get_procedure()
    assert isinstance(selection, (SolidDefence, KickoffSelection))
    selected = selection.eligible[0]
    step_action(env, ActionType.SELECT_PLAYER, player=selected)
    observation, codec = env.adapter.observe(), env.adapter.codec()
    assert at(observation, 'kickoff_selected', selected, codec) == 1
    if event == 'solid':
        original = selection.original_positions[selected.player_id]
        step_action(env, ActionType.END_SETUP)  # Finish selection; reposition phase follows.
        observation = env.adapter.observe()
        assert at(observation, 'original_position_present', selected, codec) == 1
        assert selected.position is None
        step_action(env, ActionType.PLACE_PLAYER, player=selected, position=original)
        assert selected.position == original
        step_action(env, ActionType.END_SETUP)
    else:
        step_action(env, ActionType.SELECT_NONE)
        assert selected in selection.turn.kickoff_players


def test_apothecary_alias_and_both_casualty_rolls_are_available_to_injured_coach():
    game, (attacker, defender) = season3_turn([(5, 5)], [(6, 5)])
    defender.team.state.apothecaries = 1
    with only_fixed_rolls(game, d16=[16]):
        run_proc(game, Casualty(game, defender))
    env = wrap(game)
    assert env.adapter.codec().team == defender.team
    with only_fixed_rolls(game, d16=[1]):
        observation, *_ = step_action(env, ActionType.USE_APOTHECARY)
    assert isinstance(game.get_procedure(), Apothecary)
    rolls = observation['public_rolls']
    assert set(rolls[rolls[:, 0] == 1, ROLL_FEATURES.index('die_1')]) >= {1.0, 1 / 16}
    # Enum aliases occupy the same slot but keep the procedure's own semantics.
    step_action(env, ActionType.SELECT_SECOND_ROLL)
    assert defender in game.get_reserves(defender.team)


def test_contract_metadata_rejects_legacy_changed_rules_or_pathfinding_variant():
    env = Season3Env()
    _, info = env.reset(seed=1)
    saved = info['interface']
    assert saved['fingerprint'] == 'ec00094bec5f162d83f0f30a7197b8b3882e8a590f9a522bca6cf3ff8ccc0850'
    env.adapter.require_compatible(saved)
    for field in ('rules', 'observations'):
        incompatible = deepcopy(saved)
        incompatible['contract'][field] = 'legacy'
        with pytest.raises(ValueError, match='Incompatible'):
            env.adapter.require_compatible(incompatible)
    other = Season3Env(pathfinding=True)
    other.reset(seed=1)
    assert other.adapter.metadata()['fingerprint'] == 'e6fdb81780472fb4854f449025de8f015cfd2822e14871580ca17335762ad441'
    with pytest.raises(ValueError):
        other.adapter.require_compatible(saved)
    with pytest.raises(ValueError):
        env.adapter.require_compatible({})


def test_unobserved_roster_content_is_rejected_instead_of_silently_hidden():
    game, (player,) = season3_turn([(5, 5)])
    player.extra_skills = [Skill.PRO]
    with pytest.raises(ValueError, match='six starting skills'):
        Season3Adapter(game)


def test_observation_has_no_rng_side_effect_and_reverses_with_engine_search():
    game, (player,) = season3_turn([(5, 5)], ball=(8, 5))
    env = wrap(game)
    game.enable_forward_model()
    before, rng_before = env.adapter.observe(), game.rng.get_state()
    step = game.get_step()
    step_action(env, ActionType.START_MOVE, player=player)
    game.revert(step)
    after = env.adapter.observe()
    for key in before:
        np.testing.assert_array_equal(before[key], after[key])
    np.testing.assert_equal(rng_before, game.rng.get_state())


@pytest.mark.parametrize('pathfinding,opponent,seed', [
    (False, None, 0), (True, None, 1), (False, 'random', 2), (True, 'random', 3),
    (False, 'scripted', 4)])
def test_complete_masked_rollouts_have_valid_observations_and_correct_coaches(pathfinding, opponent, seed):
    from examples.season3_rl import run
    result = run(seed=seed, pathfinding=pathfinding, opponent=opponent)
    assert result['terminated'] and not result['truncated']
    assert result['actors'] == ([0, 1] if opponent is None else [0])
    assert result['decisions'] > 50
    home = float(np.sign(result['score'][0] - result['score'][1]))
    assert result['terminal_rewards'] == [home, -home]
    if opponent is not None:
        assert result['last_reward'] == home


@pytest.mark.parametrize('away', [False, True])
def test_truncation_and_terminal_contract_have_distinct_masks_and_rewards(away):
    env = Season3Env(max_decisions=1)
    observation, _ = env.reset(seed=1)
    observation, reward, terminated, truncated, info = env.step(int(np.flatnonzero(observation['action_mask'])[0]))
    assert truncated and not terminated and reward == 0
    assert observation['action_mask'].any()  # Bootstrap state, not a fake terminal.
    assert info['terminal_rewards'] is None
    with pytest.raises(RuntimeError):
        env.step(0)
    if away:
        game, (_, player) = season3_turn([(5, 5)], [(25, 5)], ball=(25, 5))
    else:
        game, (player,) = season3_turn([(2, 5)], ball=(2, 5))
    # End-of-match fixture: scorer's last available turn in the second half.
    game.state.stack.items.clear()
    botbowl.EndGame(game)
    half = botbowl.Half(game, 2)
    half.kicked_off = True
    half.next_team = game.get_opp_team(player.team)
    game.state.half = 2
    for team in game.state.teams:
        team.state.turn = 8
    turn = Turn(game, player.team, 2, 8)
    turn.start()
    turn.started = True
    game.set_available_actions()
    env = wrap(game)
    step_action(env, ActionType.START_MOVE, player=player)
    with only_fixed_rolls(game):
        observation, reward, terminated, truncated, info = step_action(env, ActionType.MOVE, position=Square(26 if away else 1, 5))
    assert terminated and not truncated
    assert reward == 1
    assert info['terminal_rewards'] == ([-1, 1] if away else [1, -1])
    assert info['actor'] is None and not observation['action_mask'].any()
    assert env.observation_space.contains(observation)
