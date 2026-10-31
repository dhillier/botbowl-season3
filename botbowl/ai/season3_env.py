"""Versioned Gym 0.26 interface for fixed-Human Season 3 decision rollouts.

No future dice, RNG state, wall clocks or opponent policy internals are observed.
Legacy BotBowlEnv / v4 policies intentionally retain their existing contract.
"""
import hashlib
import json
from copy import deepcopy

import gym
import numpy as np

from botbowl.core.game import Game
from botbowl.core.load import load_config, load_rule_set, load_team_by_filename
from botbowl.core.model import Action, Agent, DiceRoll
from botbowl.core import procedure as proc
from botbowl.core.table import ActionType, BBDieResult, PlayerActionType, RollType, Skill, Tile, WeatherType
from botbowl.ai.bots.random_bot import RandomBot
from botbowl.ai.layers import TargetPlayerLayer
from botbowl.ai.season3_actions import (
    ACTION_VERSION, HEIGHT, ROSTER_SIZE, WIDTH, Season3ActionCodec, action_manifest)


OBSERVATION_VERSION = 's3-observations-v2'
RULES_VERSION = 'BB2025-fixed-human-2026-10-28-r1'
SKILLS = (Skill.BLOCK, Skill.DODGE, Skill.TACKLE, Skill.CATCH, Skill.PASS, Skill.SURE_HANDS)
ROLES = ('Lineman', 'Thrower', 'Catcher', 'Blitzer')
PLAYER_FEATURES = (
    'on_pitch', 'x', 'y', 'standing', 'stunned', 'used', 'distracted', 'can_mark',
    'active', 'has_ball', 'ma', 'st', 'ag_target', 'pa_target', 'pa_present', 'av_target',
    'moves_spent', 'movement_left', 'rushes_left', 'has_blocked', 'stalling_snapshot',
    'stunned_at_turn_start', 'heated', 'dodgy_snack', 'snack_absent',
    'reserves', 'knocked_out', 'casualty', 'ejected', 'kickoff_selected',
    'kickoff_eligible', 'original_position_present', 'original_x', 'original_y'
) + tuple('role_' + role.lower() for role in ROLES) + tuple(
    prefix + skill.name.lower() for skill in SKILLS for prefix in ('has_', 'usable_', 'spent_'))
SPATIAL_PLAYER_FEATURES = tuple(n for n in PLAYER_FEATURES if n not in (
    'x', 'y', 'reserves', 'knocked_out', 'casualty', 'ejected', 'snack_absent',
    'original_position_present', 'original_x', 'original_y'))
SPATIAL_FEATURES = SPATIAL_PLAYER_FEATURES + (
    'own_player', 'opp_player', 'ball', 'ball_carried', 'ball_airborne',
    'own_half', 'own_endzone', 'opp_endzone', 'crowd', 'declared_target',
    'pending_player', 'test_origin', 'test_destination', 'pending_goal',
    'remaining_path', 'pass_target', 'pass_landing')
PROCEDURES = tuple(('StartGame Pregame CoinTossFlip CoinTossKickReceive Setup SolidDefence '
    'PlaceBall HighKick Touchback Half Turn Kickoff KickoffTable KickoffSelection '
    'QuickSnapMove BlitzDeclaration MoveAction SecureBallAction BlockAction BlitzAction '
    'PassAction HandoffAction FoulAction Block Push FollowUp Apothecary Season3PassAttempt '
    'Interception Intercept Reroll Ejection FoulEjection GFI Jump Dodge Pickup Catch '
    'StandUp KnockDown KnockOut Armor Injury Casualty Bounce ThrowIn Scatter '
    'TurnoverIfPossessionLost Handoff Foul BlockResolution Touchdown EndPlayerTurn '
    'CrowdTakesAction EndTurn StartDrive EndDrive PreKickoff EndGame').split())
TEAM_FEATURES = ('score', 'turn', 'rerolls_start', 'rerolls', 'drive_rerolls',
                 'fan_factor', 'bribes', 'babes', 'apothecaries', 'ass_coaches',
                 'cheerleaders', 'cheering_fans', 'can_argue', 'reroll_used', 'can_use_reroll')
BASE_GLOBAL_FEATURES = (
    'half', 'round', 'actor_is_home', 'current_team_is_actor', 'kicking_first_is_actor',
    'kicking_drive_is_actor', 'drive_active', 'pathfinding', 'blitz_available',
    'pass_available', 'handoff_available', 'foul_available', 'secure_ball_available',
    'charge', 'quick_snap', 'kickoff_limit', 'kickoff_selected_count', 'solid_selecting',
    'block_favour_is_actor', 'reroll_context_already_rerolled', 'interception_inaccurate')
GLOBAL_FEATURES = BASE_GLOBAL_FEATURES + tuple('weather_' + w.name.lower() for w in WeatherType) + tuple(
    side + n for side in ('own_', 'opp_') for n in TEAM_FEATURES) + tuple(
    'action_' + a.name.lower() for a in PlayerActionType) + tuple(
    prefix + name for prefix in ('stack_', 'top_', 'reroll_') for name in PROCEDURES)
ROLL_FEATURES = ('present', 'dice_count', 'die_1', 'die_2', 'die_3', 'target', 'modifier') + tuple(
    'type_' + r.name for r in RollType)
MAX_PUBLIC_ROLLS = 8


def bounded(value):
    """Invertible signed count encoding; no clipping of accumulated resources."""
    return value / (1 + abs(value))


def observation_space():
    size = Season3ActionCodec.size
    return gym.spaces.Dict({
        'spatial': gym.spaces.Box(0, 1, (len(SPATIAL_FEATURES), HEIGHT, WIDTH), np.float32),
        'players': gym.spaces.Box(0, 1, (2 * ROSTER_SIZE, len(PLAYER_FEATURES)), np.float32),
        'global': gym.spaces.Box(0, 1, (len(GLOBAL_FEATURES),), np.float32),
        'public_rolls': gym.spaces.Box(-1, 1, (MAX_PUBLIC_ROLLS, len(ROLL_FEATURES)), np.float32),
        'action_features': gym.spaces.Box(-1, 1, (size, 3), np.float32),
        'action_mask': gym.spaces.MultiBinary(size)})


class Season3Adapter:
    """Read-only observation/action adapter, also usable by an engine Agent."""
    def __init__(self, game):
        if not game.is_season3 or (game.arena.width, game.arena.height) != (WIDTH, HEIGHT):
            raise ValueError('Season 3 v1 requires BB2025 and the full 28x17 arena')
        if any(len(t.players) != ROSTER_SIZE for t in game.state.teams):
            raise ValueError('Season 3 v1 requires two prepared 12-player Human rosters')
        if any(p.role.name not in ROLES or not p.role.target_characteristics or
               any(skill not in SKILLS for skill in p.get_skills())
               for team in game.state.teams for p in team.players):
            raise ValueError('Season 3 v1 observes only the selected Human roles and six starting skills')
        self.game = game
        self.space = observation_space()
        self._last_perspective = game.active_team or game.state.home_team
        self._manifest = {
            'rules': RULES_VERSION, 'observations': OBSERVATION_VERSION,
            'actions': action_manifest(), 'player_features': list(PLAYER_FEATURES),
            'spatial_features': list(SPATIAL_FEATURES), 'global_features': list(GLOBAL_FEATURES),
            'roll_features': list(ROLL_FEATURES), 'max_public_rolls': MAX_PUBLIC_ROLLS,
            'action_features': ['test_success_preview', 'signed_block_dice_div_3', 'has_test_preview'],
            'handoff_preview': 'movement and receiver catch; shared remaining team rerolls; usable Catch; no bounce recovery',
            'ball_airborne': 'uncarried airborne kick or pending prepared pass/catch; carried takes precedence',
            'count_encoding': 'n/(1+abs(n)); profile divisors MA10 ST8 AG6 PA6 AV12',
            'pathfinding': game.config.pathfinding_enabled,
            'directly_to_adjacent': game.config.pathfinding_directly_to_adjacent,
            'rosters': [[{'role': p.role.name, 'ma': p.role.ma, 'st': p.role.st,
                         'ag': p.role.ag, 'pa': p.role.pa, 'av': p.role.av,
                         'skills': [s.name for s in p.role.skills]} for p in t.players]
                        for t in game.state.teams]}
        self._fingerprint = hashlib.sha256(json.dumps(self._manifest, sort_keys=True).encode()).hexdigest()

    def metadata(self):
        return {'fingerprint': self._fingerprint, 'contract': deepcopy(self._manifest)}

    def require_compatible(self, saved_metadata):
        if saved_metadata != self.metadata():
            raise ValueError('Incompatible Season 3 interface/checkpoint metadata; legacy v4 weights cannot be reused directly')

    def codec(self):
        team = self.game.active_team or self._last_perspective
        return Season3ActionCodec(self.game, team)

    def observe(self):
        game, codec = self.game, self.codec()
        self._last_perspective = codec.team
        actions, previews = codec.legal_actions()
        turn = game.current_turn()
        selection = next((p for p in reversed(game.state.stack.items)
                          if isinstance(p, (proc.KickoffSelection, proc.SolidDefence))), None)
        selected = selection.selected if selection is not None else getattr(turn, 'kickoff_players', None) or []
        eligible = selection.eligible if selection is not None else []
        originals = getattr(selection, 'original_positions', {})
        stunned = getattr(turn, 'stunned_at_start', [])
        players = np.zeros((24, len(PLAYER_FEATURES)), np.float32)
        spatial = np.zeros((len(SPATIAL_FEATURES), HEIGHT, WIDTH), np.float32)
        spatial_index = {n: i for i, n in enumerate(SPATIAL_FEATURES)}
        for slot, player in enumerate(codec.players):
            state, team, pos = player.state, player.team, player.position
            x = (WIDTH - 1 - pos.x if codec.flip else pos.x) if pos is not None else 0
            original = originals.get(player.player_id)
            orig_x = (WIDTH - 1 - original.x if codec.flip else original.x) if original else 0
            values = dict(on_pitch=pos is not None, x=x / (WIDTH - 1),
                y=pos.y / (HEIGHT - 1) if pos else 0, standing=state.up, stunned=state.stunned,
                used=state.used, distracted=player.is_distracted(), can_mark=pos is not None and player.has_tackle_zone(),
                active=player == game.state.active_player, has_ball=game.has_ball(player),
                ma=player.get_ma() / 10, st=player.get_st() / 8, ag_target=player.get_ag_target() / 6,
                pa_target=(player.get_pa() or 0) / 6, pa_present=player.get_pa() is not None,
                av_target=player.get_armor_target() / 12, moves_spent=bounded(state.moves),
                movement_left=max(0, player.num_moves_left()) / 10,
                rushes_left=max(0, min(2, player.num_moves_left(include_gfi=True))) / 2,
                has_blocked=state.has_blocked, stalling_snapshot=state.could_score_at_activation,
                stunned_at_turn_start=player in stunned, heated=state.heated,
                dodgy_snack=state.dodgy_snack, snack_absent=state.snack_absent,
                reserves=player in game.get_reserves(team), knocked_out=player in game.get_knocked_out(team),
                casualty=player in game.get_casualties(team), ejected=state.ejected,
                kickoff_selected=player in selected, kickoff_eligible=player in eligible,
                original_position_present=original is not None, original_x=orig_x / (WIDTH - 1),
                original_y=original.y / (HEIGHT - 1) if original else 0)
            values.update({'role_' + r.lower(): player.role.name == r for r in ROLES})
            for skill in SKILLS:
                values.update({'has_' + skill.name.lower(): player.has_skill(skill),
                               'usable_' + skill.name.lower(): player.has_usable_skill(skill),
                               'spent_' + skill.name.lower(): player.has_used_skill(skill)})
            players[slot] = [values[n] for n in PLAYER_FEATURES]
            if pos is not None:
                for name in SPATIAL_PLAYER_FEATURES:
                    spatial[spatial_index[name], pos.y, x] = values[name]
                spatial[spatial_index['own_player' if slot < 12 else 'opp_player'], pos.y, x] = 1
        for y, row in enumerate(game.arena.board):
            for raw_x, tile in enumerate(row):
                x = WIDTH - 1 - raw_x if codec.flip else raw_x
                own = game.is_team_side(game.get_square(raw_x, y), codec.team)
                spatial[spatial_index['own_half'], y, x] = own
                spatial[spatial_index['own_endzone'], y, x] = tile == (Tile.AWAY_TOUCHDOWN if codec.flip else Tile.HOME_TOUCHDOWN)
                spatial[spatial_index['opp_endzone'], y, x] = tile == (Tile.HOME_TOUCHDOWN if codec.flip else Tile.AWAY_TOUCHDOWN)
                spatial[spatial_index['crowd'], y, x] = tile == Tile.CROWD
        for ball in game.state.pitch.balls:
            if ball.position is not None:
                pos = ball.position
                x = WIDTH - 1 - pos.x if codec.flip else pos.x
                # on_ground is primarily a kick lifecycle flag in the engine;
                # passing/catching context is also needed for an airborne ball.
                in_flight = not ball.on_ground or any(
                    not p.done and getattr(p, 'piece', None) is ball and
                    (isinstance(p, proc.Catch) or isinstance(p, proc.Season3PassAttempt) and p.landing_prepared)
                    for p in game.state.stack.items)
                for name, value in [('ball', 1), ('ball_carried', ball.is_carried),
                                    ('ball_airborne', not ball.is_carried and in_flight)]:
                    spatial[spatial_index[name], pos.y, x] = value
        target = TargetPlayerLayer().get(game)
        spatial[spatial_index['declared_target']] = np.flip(target, 1) if codec.flip else target
        self._pending_positions(spatial, spatial_index, codec)
        mask = np.zeros(codec.size, np.int8)
        action_features = np.zeros((codec.size, 3), np.float32)
        for index in actions:
            mask[index] = 1
            action_features[index] = previews[index]
        return {'spatial': spatial, 'players': players,
                'global': self._global(codec, turn, selection), 'public_rolls': self._rolls(),
                'action_features': action_features, 'action_mask': mask}

    def _pending_positions(self, spatial, indices, codec):
        def mark(name, position, value=1):
            if position is not None:
                x = WIDTH - 1 - position.x if codec.flip else position.x
                spatial[indices[name], position.y, x] = value
        stack = self.game.state.stack.items
        reroll = next((p for p in reversed(stack) if isinstance(p, proc.Reroll)), None)
        context = reroll.context if reroll else stack[-1] if stack else None
        player = getattr(context, 'player', None) or getattr(context, 'passer', None) or getattr(context, 'attacker', None)
        if player is not None:
            mark('pending_player', player.position)
            mark('test_origin', getattr(context, 'origin', None) or getattr(context, 'from_position', None) or player.position)
        mark('test_destination', getattr(context, 'position', None))
        goal = next((p for p in reversed(stack) if isinstance(p, (proc.Move, proc.Jump, proc.Season3PassAttempt))), None)
        mark('pending_goal', getattr(goal, 'position', None))
        movement = next((p for p in reversed(stack) if isinstance(p, proc.MoveAction)), None)
        steps = getattr(movement, 'steps', None) or []
        for i, position in enumerate(steps):
            mark('remaining_path', position, (i + 1) / len(steps))
        passing = next((p for p in reversed(stack) if isinstance(p, proc.Season3PassAttempt)), None)
        if passing:
            mark('pass_target', passing.position)
            if passing.landing_prepared:
                mark('pass_landing', passing.piece.position)

    def _global(self, codec, turn, selection):
        game, team = self.game, codec.team
        stack = game.state.stack.items
        block = next((p for p in reversed(stack) if isinstance(p, proc.Block)), None)
        reroll = next((p for p in reversed(stack) if isinstance(p, proc.Reroll)), None)
        interception = next((p for p in reversed(stack) if isinstance(p, proc.Interception)), None)
        values = dict(half=bounded(game.state.half), round=bounded(game.state.round),
            actor_is_home=team == game.state.home_team, current_team_is_actor=game.state.current_team == team,
            kicking_first_is_actor=game.state.kicking_first_half == team,
            kicking_drive_is_actor=game.state.kicking_this_drive == team, drive_active=game.state.drive_active,
            pathfinding=game.config.pathfinding_enabled, blitz_available=game.is_blitz_available(),
            pass_available=game.is_pass_available(), handoff_available=game.is_handoff_available(),
            foul_available=game.is_foul_available(), secure_ball_available=game.is_secure_ball_available(),
            charge=bool(turn and turn.blitz), quick_snap=bool(turn and turn.quick_snap),
            kickoff_limit=bounded(getattr(selection, 'limit', 0)),
            kickoff_selected_count=bounded(len(selection.selected) if selection else 0),
            solid_selecting=isinstance(selection, proc.SolidDefence) and selection.selecting,
            block_favour_is_actor=bool(block and block.favor == team),
            reroll_context_already_rerolled=bool(reroll and reroll.context in game.state.rerolled_procs),
            interception_inaccurate=bool(interception and interception.inaccurate))
        values.update({'weather_' + w.name.lower(): game.state.weather == w for w in WeatherType})
        for prefix, current in [('own_', team), ('opp_', game.get_opp_team(team))]:
            for name in TEAM_FEATURES:
                value = game.can_use_reroll(current) if name == 'can_use_reroll' else getattr(current.state, name)
                values[prefix + name] = float(value) if isinstance(value, bool) else bounded(value)
        values.update({'action_' + a.name.lower(): game.state.player_action_type == a for a in PlayerActionType})
        top = type(stack[-1]).__name__ if stack else None
        context = type(reroll.context).__name__ if reroll else None
        types = {type(p).__name__ for p in stack}
        for name in PROCEDURES:
            values.update({'stack_' + name: name in types, 'top_' + name: top == name,
                           'reroll_' + name: context == name})
        if top and top not in PROCEDURES:
            raise ValueError('Unversioned Season 3 decision procedure: ' + top)
        return np.array([values[n] for n in GLOBAL_FEATURES], np.float32)

    def _rolls(self):
        out = np.zeros((MAX_PUBLIC_ROLLS, len(ROLL_FEATURES)), np.float32)
        seen, rolls = set(), []
        for p in reversed(self.game.state.stack.items):
            for name in ('roll', 'roll_first', 'roll_second'):
                roll = getattr(p, name, None)
                if isinstance(roll, DiceRoll) and id(roll) not in seen:
                    rolls.append(roll)
                    seen.add(id(roll))
        for row, roll in zip(out, rolls):
            dice = [d.get_value() for d in roll.dice]
            values = [1, len(dice) / 3] + [
                (v.value if isinstance(v, BBDieResult) else v) / 16 for v in dice[:3]]
            values += [0] * (5 - len(values))
            values += [(roll.target or 0) / 16, bounded(roll.modifiers)]
            values += [float(roll.roll_type == kind) for kind in RollType]
            row[:] = values
        return out


class Season3Env(gym.Env):
    """Every pending coach decision, or either learner side against a supplied bot.

    In self-play the next decision can belong to either coach, including twice
    consecutively. Reward is terminal win/draw/loss from the pre-step actor's
    perspective; info supplies both teams' terminal rewards for trajectory credit.
    """
    metadata = {'render_modes': []}

    def __init__(self, pathfinding=False, opponent=None, max_decisions=10000, learner_side=0):
        if opponent is not None:
            if isinstance(opponent, str):
                valid = opponent == 'random'
            else:
                valid = isinstance(opponent, Agent) and not opponent.human
            if not valid:
                raise ValueError('opponent must be None, random, or a non-human engine Agent')
        if not isinstance(max_decisions, int) or max_decisions <= 0:
            raise ValueError('max_decisions must be a positive integer')
        if (not isinstance(learner_side, (int, np.integer)) or
                isinstance(learner_side, (bool, np.bool_)) or learner_side not in (0, 1)):
            raise ValueError('learner_side must be 0 (home) or 1 (away)')
        if learner_side == 1 and opponent is None:
            raise ValueError('learner_side requires a supplied opponent')
        self.opponent, self.max_decisions = opponent, max_decisions
        self.learner_side = learner_side
        self.config = load_config('season3-preview')
        self.config.pathfinding_enabled = pathfinding
        self.rules = load_rule_set('BB2025')
        self.action_space = gym.spaces.Discrete(Season3ActionCodec.size)
        self.observation_space = observation_space()
        self.game = self.adapter = None
        self._finished = True

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options:
            raise ValueError('Season 3 v1 has no reset options')
        game_seed = int(self.np_random.integers(0, 2 ** 31))
        self.game_seed, self.decisions = game_seed, 0
        self.action_space.seed(seed)
        opponent = (RandomBot('opponent', seed=game_seed) if isinstance(self.opponent, str) else
                deepcopy(self.opponent) if self.opponent is not None else Agent('away learner', human=True))
        learner = Agent('home learner' if self.learner_side == 0 else 'away learner', human=True)
        home, away = (learner, opponent) if self.learner_side == 0 else (opponent, learner)
        self.game = Game('season3-rl', load_team_by_filename('human', self.rules),
                         load_team_by_filename('human', self.rules), home,
                         away, deepcopy(self.config), ruleset=self.rules, seed=game_seed)
        self.game.init()
        if self.opponent is not None and self.learner_side == 0:
            # START_GAME and the coin flip belong to away. Let a configured
            # opponent handle them before returning the home learner's choice.
            self.game.step(Action(ActionType.START_GAME))
        self.adapter = Season3Adapter(self.game)
        self._finished = False
        return self.adapter.observe(), self._info(include_contract=True)

    def step(self, action):
        if self._finished:
            raise RuntimeError('reset() is required before stepping a finished episode')
        codec = self.adapter.codec()
        codec.decode(action)  # Validate integer type/range before dictionary lookup.
        legal, _ = codec.legal_actions()
        if action not in legal:
            raise ValueError('Masked/illegal Season 3 action index: ' + str(action))
        actor = 0 if codec.team == self.game.state.home_team else 1
        selected = legal[action]
        decision = {'actor': actor, 'index': int(action), 'action_type': selected.action_type.name,
                    'player_slot': codec.players.index(selected.player) if selected.player else None,
                    'position': [selected.position.x, selected.position.y] if selected.position else None,
                    'legal_indices': sorted(legal)}
        self.game.step(selected)
        self.decisions += 1
        terminated = self.game.state.game_over
        truncated = not terminated and self.decisions >= self.max_decisions
        self._finished = terminated or truncated
        observation = self.adapter.observe()
        rewards = self._terminal_rewards() if terminated else [0.0, 0.0]
        info = self._info()
        info.update(decision=decision, terminal_rewards=rewards if terminated else None)
        return observation, rewards[actor], terminated, truncated, info

    def _terminal_rewards(self):
        difference = self.game.state.home_team.state.score - self.game.state.away_team.state.score
        home = float(np.sign(difference))
        return [home, -home]

    def _info(self, include_contract=False):
        active = self.game.active_team
        info = {'rules_version': RULES_VERSION, 'observation_version': OBSERVATION_VERSION,
                'action_version': ACTION_VERSION, 'interface_fingerprint': self.adapter._fingerprint,
                'actor': None if self.game.state.game_over else 0 if active == self.game.state.home_team else 1,
                'seed': self.game_seed, 'decisions': self.decisions,
                'score': [self.game.state.home_team.state.score, self.game.state.away_team.state.score]}
        if include_contract:
            info['interface'] = self.adapter.metadata()
        return info
