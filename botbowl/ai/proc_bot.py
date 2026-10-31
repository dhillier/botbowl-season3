"""
==========================
Author: Niels Justesen
Year: 2018
==========================
This module contains an example bot that takes random actions.
Modified for the Season 3 Blitz declaration decision, October 2026.
"""
from botbowl.core.model import Agent, Action
from botbowl.core.game import Game, InvalidActionError
from botbowl.core.procedure import *


class ProcBot(Agent):

    def __init__(self, name):
        super().__init__(name)

    def act(self, game: Game):

        # Get current procedure
        proc = game.get_procedure()
        # print(type(proc))
        
        action: Optional[Action] = None

        # New Season 3 decisions have a legal default for existing ProcBot
        # subclasses. Bots can override this hook to plan the skills tactically.
        if game.is_season3 and (
                isinstance(proc, (SpecialAction, ThrowTeamMateAction, PuntAction, BallAndChainAction)) or
                isinstance(proc, ThrowBombAction) and proc.rethrow or
                isinstance(proc, Reroll) and (proc.block_skills or proc.pro is not None) or
                isinstance(proc, Block) and proc.waiting_dump_off or
                isinstance(proc, FollowUp) and any(a.skill is not None for a in game.get_available_actions())):
            return self.season3_skill_decision(game)
        
        # Call private function
        if isinstance(proc, CoinTossFlip):
            action = self.coin_toss_flip(game)
        elif isinstance(proc, CoinTossKickReceive):
            action = self.coin_toss_kick_receive(game)
        elif isinstance(proc, Setup):
            if proc.reorganize:
                action = self.perfect_defense(game)
            else:
                action = self.setup(game)
        elif isinstance(proc, Ejection):
            if game.is_season3 and any(a.action_type == ActionType.ARGUE_CALL for a in game.get_available_actions()):
                action = Action(ActionType.ARGUE_CALL)
            else:
                action = self.use_bribe(game)
        elif isinstance(proc, KickoffSelection):
            action = Action(ActionType.SELECT_NONE)
        elif isinstance(proc, Reroll):
            if proc.can_use_pro:
                action = self.use_pro(game)
            else:
                action = self.reroll(game)
        elif isinstance(proc, PlaceBall):
            action = self.place_ball(game)
        elif isinstance(proc, HighKick):
            action = self.high_kick(game)
        elif isinstance(proc, Touchback):
            if game.is_season3 and game.get_available_actions()[0].action_type == ActionType.PLACE_BALL:
                action = Action(ActionType.PLACE_BALL, position=game.get_available_actions()[0].positions[0])
            else:
                action = self.touchback(game)
        elif isinstance(proc, Turn) and proc.quick_snap:
            action = self.quick_snap(game)
        elif isinstance(proc, Turn) and proc.blitz:
            action = self.blitz(game)
        elif isinstance(proc, Turn):
            action = self.turn(game)
        elif isinstance(proc, MoveAction):
            action = self.player_action(game)
        elif isinstance(proc, MoveAction):
            action = self.player_action(game)
        elif isinstance(proc, BlockAction):
            action = self.player_action(game)
        elif isinstance(proc, PassAction):
            action = self.player_action(game)
        elif isinstance(proc, HandoffAction):
            action = self.player_action(game)
        elif isinstance(proc, BlitzAction):
            action = self.player_action(game)
        elif isinstance(proc, FoulAction):
            action = self.player_action(game)
        elif isinstance(proc, ThrowBombAction):
            action = self.player_action(game)
        elif isinstance(proc, Block):
            if proc.waiting_juggernaut:
                action = self.use_juggernaut(game)
            elif proc.waiting_wrestle_attacker or proc.waiting_wrestle_defender:
                action = self.use_wrestle(game)
            else:
                action = self.block(game)
        elif isinstance(proc, Push):
            if proc.waiting_stand_firm:
                action = self.use_stand_firm(game)
            else:
                action = self.push(game)
        elif isinstance(proc, FollowUp):
            action = self.follow_up(game)
        elif isinstance(proc, Apothecary):
            if game.is_season3 and proc.waiting_apothecary:
                action = Action(ActionType.SELECT_FIRST_ROLL if proc.effect_first.value <= proc.effect_second.value
                                else ActionType.SELECT_SECOND_ROLL)
            else:
                action = self.apothecary(game)
        elif isinstance(proc, Interception):
            action = self.interception(game)
        elif isinstance(proc, BlitzDeclaration):
            action = self.blitz_target(game)
        elif isinstance(proc, BloodLustBlockOrMove):
            action = self.blood_lust_block_or_move(game)
        elif isinstance(proc, EatThrall):
            action = self.eat_thrall(game)
        else:
            if game.is_season3:
                return self.season3_skill_decision(game)
            raise Exception("Unknown procedure")

        if action is None:
            assert action is not None

        # handle illegal action. if handle_illegal_action() returns a new legal action, return that.
        if not game._is_action_allowed(action):
            new_action = self.handle_illegal_action(game, action)
            assert isinstance(new_action, Action)
            assert game._is_action_allowed(new_action)
            return new_action

        return action

    def season3_skill_decision(self, game):
        """Conservative legal decisions; this is not a team-specific strategy."""
        choices = [a for a in game.get_available_actions() if not a.disabled]
        priority = {ActionType.USE_SKILL: 0, ActionType.DONT_USE_SKILL: 1,
                    ActionType.END_PLAYER_TURN: 2, ActionType.SELECT_NONE: 3}
        choice = min(choices, key=lambda a: priority.get(a.action_type, 4))
        return Action(choice.action_type,
                      player=choice.players[0] if choice.players else None,
                      position=choice.positions[0] if choice.positions else None)

    def blitz_target(self, game):
        """Default for Season 3 clients that have not added target planning yet."""
        return Action(ActionType.SELECT_PLAYER, player=game.get_available_actions()[0].players[0])

    def use_pro(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def use_juggernaut(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def use_wrestle(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def use_stand_firm(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def coin_toss_flip(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def coin_toss_kick_receive(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def setup(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def reroll(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def use_bribe(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def place_ball(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def high_kick(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def touchback(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def turn(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def quick_snap(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def blitz(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def player_action(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def block(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def push(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def follow_up(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def apothecary(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def interception(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def gfi(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def dodge(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def pickup(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def blood_lust_block_or_move(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def eat_thrall(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def perfect_defense(self, game):
        raise NotImplementedError("This method must be overridden by non-human subclasses")

    def handle_illegal_action(self, game: Game, action: Action) -> Optional[Action]:
        """
        :param game: current game object
        :param action: action that was illegal
        :return: this particular implementation does not return, it raises an error with some
        helpful debug information. But if you override it in a subclass you may return a safe action
        e.g. pick a random action for the list of available action or used game._forced_action()
        """

        error_message = f"{action} is not allowed. "
        allowed_action_types = {action_choice.action_type for action_choice in game.get_available_actions()}
        if action.action_type not in allowed_action_types:
            allowed_action_types_names = ", ".join(action_type.name for action_type in allowed_action_types)
            error_message += f"Allowed action types are: {allowed_action_types_names}"
            raise InvalidActionError(error_message)

        # Find the relevant action choice
        target_action_choice: Optional[ActionChoice] = None
        for action_choice in game.get_available_actions():
            if action_choice.action_type == action.action_type:
                target_action_choice = action_choice
                break

        if len(target_action_choice.positions) > 0:
            allowed_positions = ', '.join(map(str, target_action_choice.positions))
            if action.position is None and None not in target_action_choice.positions:
                error_message += f"position=None not allowed! Available positions are {allowed_positions}"
            elif action.position not in target_action_choice.positions:
                error_message += f"wrong position. Available positions are {allowed_positions}"
        else:
            error_message += "Other error, no details, sorry"

        raise InvalidActionError(error_message)
