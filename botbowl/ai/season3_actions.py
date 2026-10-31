"""Version 1 fixed-Human Season 3 actions, independent of the legacy v4 codec."""
import operator

import numpy as np

from botbowl.core.model import Action
from botbowl.core.table import ActionType, Skill


ACTION_VERSION = 's3-actions-v1'
ROSTER_SIZE = 12
WIDTH, HEIGHT = 28, 17  # Include crowd squares, which are valid push targets.
SQUARES = WIDTH * HEIGHT

# Explicit order is part of the checkpoint contract. Enum aliases (notably
# SELECT_SECOND_ROLL / DONT_USE_REROLL) share an index, as in the engine.
SIMPLE_ACTIONS = tuple(ActionType[name] for name in (
    'START_GAME', 'HEADS', 'TAILS', 'KICK', 'RECEIVE', 'END_SETUP',
    'END_PLAYER_TURN', 'USE_REROLL', 'DONT_USE_REROLL', 'USE_SKILL',
    'DONT_USE_SKILL', 'END_TURN', 'STAND_UP', 'SELECT_ATTACKER_DOWN',
    'SELECT_BOTH_DOWN', 'SELECT_PUSH', 'SELECT_DEFENDER_STUMBLES',
    'SELECT_DEFENDER_DOWN', 'SELECT_NONE', 'USE_BRIBE', 'DONT_USE_BRIBE',
    'ARGUE_CALL', 'DONT_ARGUE_CALL', 'USE_APOTHECARY', 'DONT_USE_APOTHECARY',
    'SELECT_FIRST_ROLL', 'SETUP_FORMATION_WEDGE', 'SETUP_FORMATION_LINE',
    'SETUP_FORMATION_ZONE', 'SETUP_FORMATION_SPREAD', 'UNDO', 'CONTINUE'))
PLAYER_ACTIONS = tuple(ActionType[name] for name in (
    'START_MOVE', 'START_BLOCK', 'START_BLITZ', 'START_PASS', 'START_FOUL',
    'START_HANDOFF', 'START_SECURE_BALL', 'FOREGO_ACTIVATION', 'SELECT_PLAYER'))
POSITION_ACTIONS = tuple(ActionType[name] for name in (
    'PLACE_BALL', 'PUSH', 'FOLLOW_UP', 'MOVE', 'BLOCK', 'PASS', 'FOUL', 'HANDOFF', 'JUMP'))


class Season3ActionCodec:
    """Acting-coach-relative identities; away-coach coordinates mirror in x."""
    player_offset = len(SIMPLE_ACTIONS)
    position_offset = player_offset + len(PLAYER_ACTIONS) * 2 * ROSTER_SIZE
    placement_offset = position_offset + len(POSITION_ACTIONS) * SQUARES
    size = placement_offset + ROSTER_SIZE * (SQUARES + 1)

    def __init__(self, game, perspective=None):
        if not game.is_season3 or (game.arena.width, game.arena.height) != (WIDTH, HEIGHT):
            raise ValueError('Season 3 actions require BB2025 and the full arena')
        self.game = game
        self.team = perspective if perspective is not None else game.active_team
        if self.team is None:
            raise ValueError('An acting-coach perspective is required')
        self.flip = self.team == game.state.away_team
        self.players = self.team.players + game.get_opp_team(self.team).players
        if len(self.team.players) != ROSTER_SIZE or len(self.players) != 2 * ROSTER_SIZE:
            raise ValueError('Season 3 v1 requires the prepared 12-player Human teams')

    def _square_index(self, position):
        x, y = position.x, position.y
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            raise ValueError('Position outside the versioned arena')
        return y * WIDTH + (WIDTH - 1 - x if self.flip else x)

    def _square(self, index):
        x, y = index % WIDTH, index // WIDTH
        return self.game.get_square(WIDTH - 1 - x if self.flip else x, y)

    def encode(self, action):
        kind = action.action_type
        if kind in SIMPLE_ACTIONS:
            return SIMPLE_ACTIONS.index(kind)
        if kind in PLAYER_ACTIONS:
            player = action.player
            if player is None and action.position is not None:
                player = self.game.get_player_at(action.position)
            return self.player_offset + PLAYER_ACTIONS.index(kind) * 24 + self.players.index(player)
        if kind in POSITION_ACTIONS:
            position = action.position if action.position is not None else action.player.position
            return self.position_offset + POSITION_ACTIONS.index(kind) * SQUARES + self._square_index(position)
        if kind == ActionType.PLACE_PLAYER:
            slot = self.team.players.index(action.player)
            square = SQUARES if action.position is None else self._square_index(action.position)
            return self.placement_offset + slot * (SQUARES + 1) + square
        raise ValueError('Action outside Season 3 v1 scope: ' + kind.name)

    def decode(self, index):
        """Decode structure only; the environment separately enforces legality."""
        if isinstance(index, (bool, np.bool_)):
            raise ValueError('Action index must be an integer, not a boolean')
        try:
            index = operator.index(index)
        except TypeError as exc:
            raise ValueError('Action index must be an integer') from exc
        if not 0 <= index < self.size:
            raise ValueError('Action index outside Season 3 v1 space')
        if index < self.player_offset:
            return Action(SIMPLE_ACTIONS[index])
        if index < self.position_offset:
            kind, slot = divmod(index - self.player_offset, 24)
            return Action(PLAYER_ACTIONS[kind], player=self.players[slot])
        if index < self.placement_offset:
            kind, square = divmod(index - self.position_offset, SQUARES)
            return Action(POSITION_ACTIONS[kind], position=self._square(square))
        slot, square = divmod(index - self.placement_offset, SQUARES + 1)
        return Action(ActionType.PLACE_PLAYER, player=self.team.players[slot],
                      position=None if square == SQUARES else self._square(square))

    def legal_actions(self):
        """All enabled engine choices, with setup's semantic constraints applied.

        Reading choices does not call the engine's permissive/mutating validator.
        Duplicate choices merge. Unsupported payloads fail instead of disappearing.
        """
        actions, previews = {}, {}
        if self.game.state.game_over:
            return actions, previews
        for choice in self.game.get_available_actions():
            if choice.disabled:
                continue
            if choice.team != self.team:
                raise ValueError('Enabled choices belong to different coaches')
            kind = choice.action_type
            if kind == ActionType.END_SETUP and not self.game.is_setup_legal(self.team):
                continue
            if kind == ActionType.PLACE_PLAYER:
                candidates = []
                for player in choice.players:
                    for position in choice.positions:
                        # Setup offers occupied squares even for reserve players;
                        # reserves_to_pitch requires an empty destination.
                        if player.position is None and position is not None and self.game.get_player_at(position) is not None:
                            continue
                        candidates.append((Action(kind, player=player, position=position), None))
            elif kind in PLAYER_ACTIONS:
                if choice.positions:
                    raise ValueError('Unexpected positional player choice: ' + kind.name)
                candidates = [(Action(kind, player=player), i) for i, player in enumerate(choice.players)]
            elif kind in POSITION_ACTIONS:
                if choice.players:
                    raise ValueError('Unexpected player payload: ' + kind.name)
                candidates = [(Action(kind, position=pos), i) for i, pos in enumerate(choice.positions) if pos is not None]
            elif kind in SIMPLE_ACTIONS:
                if choice.positions or len(choice.players) > 1:
                    raise ValueError('Unexpected simple-action payload: ' + kind.name)
                candidates = [(Action(kind, player=choice.players[0] if choice.players else None), None)]
            else:
                raise ValueError('Unencoded Season 3 decision: ' + kind.name)
            for action, i in candidates:
                index = self.encode(action)
                if index in actions and (actions[index].player != action.player or actions[index].position != action.position):
                    raise ValueError('Ambiguous payload for one encoded action: ' + kind.name)
                actions[index] = action
                probability, block_dice, has_preview = 0.0, 0.0, 0.0
                if i is not None:
                    if i < len(choice.paths):
                        probability, has_preview = choice.paths[i].prob, 1.0
                        if kind == ActionType.HANDOFF:
                            probability = choice.paths[i].handoff_prob
                            if probability is None:
                                raise ValueError('Handoff path lacks its catch-completion preview')
                    elif kind == ActionType.HANDOFF:
                        receiver = self.game.get_player_at(action.position)
                        probability = self.game.get_catch_prob(
                            receiver, handoff=True, allow_catch_reroll=receiver.can_use_skill(Skill.CATCH),
                            allow_team_reroll=True)
                        has_preview = 1.0
                    elif i < len(choice.rolls) and choice.rolls[i]:
                        targets = choice.rolls[i]
                        if kind == ActionType.FOUL:
                            probability = sum(a + b >= targets[0] for a in range(1, 7) for b in range(1, 7)) / 36
                        else:
                            probability = float(np.prod([(7 - max(2, min(6, t))) / 6 for t in targets]))
                        has_preview = 1.0
                    if i < len(choice.block_dice):
                        block_dice = choice.block_dice[i] / 3
                previews[index] = (probability, block_dice, has_preview)
        if not actions:
            raise ValueError('Nonterminal Season 3 decision has no encoded legal actions')
        return actions, previews


def action_manifest():
    return {'version': ACTION_VERSION, 'simple': [a.name for a in SIMPLE_ACTIONS],
            'player': [a.name for a in PLAYER_ACTIONS], 'position': [a.name for a in POSITION_ACTIONS],
            'placement': 'own roster slot * 477 + square; square 476 = reserves',
            'roster_slots': ROSTER_SIZE, 'width': WIDTH, 'height': HEIGHT,
            'size': Season3ActionCodec.size, 'perspective': 'acting coach; away mirrors x'}
