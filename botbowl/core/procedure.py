# Modified for the Season 3 migration on 28 October 2026.
"""
==========================
Author: Niels Justesen
Year: 2018
==========================
This module contains all the procedures. Procedures contain the core part of the rules in botbowl. Each procedure are
responsible for an isolated part of the game. Procedures are added to a stack, and the top-most procedure must finish
before other procedures are run. Procedures can add other procedures to the stack simply by instantiating procedures.
"""


from botbowl.core.pathfinding import Pathfinder
from botbowl.core.util import compare_object
from botbowl.core.model import *
from botbowl.core.table import *

import time
from abc import abstractmethod, ABCMeta


SEASON3_SPECIAL_ACTIONS = {
    Skill.STAB: (ActionType.START_STAB, ActionType.STAB),
    Skill.HYPNOTIC_GAZE: (ActionType.START_HYPNOTIC_GAZE, ActionType.HYPNOTIC_GAZE),
    Skill.PROJECTILE_VOMIT: (ActionType.START_PROJECTILE_VOMIT, ActionType.PROJECTILE_VOMIT),
    Skill.BREATHE_FIRE: (ActionType.START_BREATHE_FIRE, ActionType.BREATHE_FIRE),
    Skill.MONSTROUS_MOUTH: (ActionType.START_CHOMP, ActionType.CHOMP),
    Skill.CHAINSAW: (ActionType.START_CHAINSAW, ActionType.CHAINSAW)}


class Procedure(Reversible):

    def __init__(self, game, context=None, ignored_keys=None):
        ignored_keys = [] if ignored_keys is None else ignored_keys

        super().__init__(ignored_keys=["game"]+ignored_keys)
        self.game = game
        self.context = context
        self.done = False
        self.started = False
        self.game.state.stack.push(self)  # Note: The stack will call this object's set_logger

    def start(self):
        """
        Is called just before step() is called the first time. The Game class will set initialized to True.
        """
        pass

    def end(self):
        """
        Is called when the procedure is done, i.e. right after step() returns True.
        """
        pass

    def step(self, action):
        """
        Is called when this procedure is on the top of the stack until the procedure is done.
        :param action: an action performed by an agent - will be None if there are no available actions.
        :return: a bool indicating whether the procedure is done.
        """
        raise Exception("Must be implemented by subclass")

    def available_actions(self):
        """
        :return: a list of available actions. This can vary based on the state of the procedure.
        """
        return []

    def compare(self, other, path=""):
        return compare_object(self, other, path, ignored_keys={"game"}, ignored_types={Procedure})

    def __repr__(self):
        return f"{self.__class__.__name__}(done={self.done}, started={self.started})"


class Regeneration(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.regenerates = False

    def step(self, action):
        if self.player.has_skill(Skill.REGENERATION):
            regen_roll = DiceRoll([D6(self.game.rng)], target=4, roll_type=RollType.REGENERATION_ROLL)
            if regen_roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_REGENERATION, player=self.player, rolls=[regen_roll]))
                # self.game.pitch_to_reserves(self.player)
                self.regenerates = True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_REGENERATION, player=self.player, rolls=[regen_roll]))
        return True


class Apothecary(Procedure):

    def __init__(self, game, player, roll, outcome, inflictor, casualty=None, effect=None, decay=False, in_crowd=False):
        super().__init__(game)
        self.player = player
        self.inflictor = inflictor
        self.decay = decay
        self.waiting_apothecary = False
        self.roll_first = roll
        self.roll_second = roll
        self.outcome = outcome
        self.casualty_first = casualty
        self.effect_first = effect
        self.casualty_second = None
        self.effect_second = None
        self.regeneration = None
        self.effect = None
        self.casualty = None
        self.roll = None
        self.in_crowd = in_crowd

    def start(self):
        if self.game.state.current_team != self.player.team:
            self.game.add_secondary_clock(self.player.team)

    def end(self):
        if self.game.state.current_team != self.player.team:
            self.game.remove_secondary_clocks()

    def step(self, action):

        if self.game.is_season3:
            return self._step_season3(action)

        if self.outcome == OutcomeType.KNOCKED_OUT:

            if action.action_type == ActionType.USE_APOTHECARY:

                # Player is moved to reserves
                self.player.team.state.apothecaries -= 1
                self.player.state.stunned = True
                self.player.place_prone()
                self.game.report(Outcome(OutcomeType.APOTHECARY_USED_KO, player=self.player, team=self.player.team))

            else:

                # Player is KO
                self.game.pitch_to_kod(self.player)
                self.game.report(Outcome(OutcomeType.APOTHECARY_USED_KO, player=self.player, team=self.player.team))

            return True

        elif self.outcome == OutcomeType.CASUALTY:

            if action.action_type == ActionType.USE_APOTHECARY:

                self.roll_second = DiceRoll([D6(self.game.rng), D8(self.game.rng)], roll_type=RollType.CASUALTY_ROLL)
                result = self.roll_second.get_sum()
                n = min(61, max(38, result))
                self.casualty_second = CasualtyType(n)
                self.effect_second = Rules.casualty_effect[self.casualty_second]
                self.player.team.state.apothecaries -= 1
                self.game.report(Outcome(OutcomeType.CASUALTY_APOTHECARY, player=self.player, team=self.player.team,
                                         rolls=[self.roll_first, self.roll_second]))
                self.waiting_apothecary = True

                return False

            if action.action_type == ActionType.SELECT_FIRST_ROLL or ActionType.SELECT_SECOND_ROLL:

                self.effect = self.effect_first if action.action_type == ActionType.SELECT_FIRST_ROLL else self.effect_second
                self.casualty = self.casualty_first if action.action_type == ActionType.SELECT_FIRST_ROLL else self.casualty_second
                self.roll = self.roll_first if action.action_type == ActionType.SELECT_FIRST_ROLL else self.roll_second

                # Regeneration
                if self.player.has_skill(Skill.REGENERATION) and not self.regeneration:
                    self.regeneration = Regeneration(self.game, self.player)
                    return False

                if self.regeneration and self.regeneration.regenerates:
                    self.game.pitch_to_reserves(self.player)
                    return True

                # Apply casualty
                self.game.apply_casualty(self.player, self.inflictor, self.casualty, self.effect, self.roll)

                # Decay
                if self.decay:
                    Casualty(self.game, self.player)

        return True

    def available_actions(self):
        if self.regeneration:
            return []
        elif not self.waiting_apothecary and self.player.team.state.apothecaries > 0:
            return [ActionChoice(ActionType.USE_APOTHECARY, team=self.player.team),
                    ActionChoice(ActionType.DONT_USE_APOTHECARY, team=self.player.team)]
        elif self.waiting_apothecary:
            return [ActionChoice(ActionType.SELECT_FIRST_ROLL, team=self.player.team),
                    ActionChoice(ActionType.SELECT_SECOND_ROLL, team=self.player.team)]
        return []

    def _step_season3(self, action):
        if self.outcome == OutcomeType.KNOCKED_OUT:
            if action.action_type == ActionType.USE_APOTHECARY:
                self.player.team.state.apothecaries -= 1
                if self.in_crowd:
                    self.game.pitch_to_reserves(self.player)
                else:
                    self.player.place_prone()
                    self.player.state.stunned = True
                self.game.report(Outcome(OutcomeType.APOTHECARY_USED_KO, player=self.player))
            else:
                self.game.pitch_to_kod(self.player)
            return True
        if action.action_type == ActionType.USE_APOTHECARY:
            self.roll_second = DiceRoll([D16(self.game.rng)],
                                       modifiers=self.player.num_niggling_injuries() + int(self.player.has_skill(Skill.DECAY)),
                                       roll_type=RollType.CASUALTY_ROLL)
            self.casualty_second, self.effect_second = _season3_casualty_result(self.roll_second)
            self.player.team.state.apothecaries -= 1
            self.waiting_apothecary = True
            self.game.report(Outcome(OutcomeType.CASUALTY_APOTHECARY, player=self.player,
                                     rolls=[self.roll_first, self.roll_second]))
            return False
        second = action.action_type == ActionType.SELECT_SECOND_ROLL
        casualty = self.casualty_second if second else self.casualty_first
        effect = self.effect_second if second else self.effect_first
        roll = self.roll_second if second else self.roll_first
        if self.waiting_apothecary and effect == CasualtyEffect.NONE:
            self.game.pitch_to_reserves(self.player)
            self.game.report(Outcome(OutcomeType.BADLY_HURT, player=self.player, rolls=[roll]))
        else:
            self.game.apply_casualty(self.player, self.inflictor, casualty, effect, roll)
        return True


class Armor(Procedure):

    def __init__(self, game, player, modifiers=0, inflictor=None, foul=False, foul_check=None,
                 damage_skill=None, claws=False, lone_fouler=False, knockdown_on_break=False,
                 casualty_credit=False, block=False):
        super().__init__(game)
        self.player = player
        self.modifiers = modifiers
        self.inflictor = inflictor
        self.skip_armor = False
        self.armor_rolled = False
        self.foul = foul
        self.inflictor = inflictor
        self.ejected = False
        self.foul_check = foul_check
        self.damage_skill = damage_skill
        self.claws = claws
        self.lone_fouler = lone_fouler
        self.lone_fouler_used = False
        self.knockdown_on_break = knockdown_on_break
        self.casualty_credit = casualty_credit
        self.block = block
        self.roll = None
        self.dirty_choice = None
        self.waiting_skill = None

    def step(self, action):

        # Roll
        if self.waiting_skill == Skill.DIRTY_PLAYER:
            self.dirty_choice = action.action_type == ActionType.USE_SKILL
            self.waiting_skill = None
        elif self.waiting_skill == Skill.LONE_FOULER:
            self.lone_fouler_used = True
            self.waiting_skill = None
            if action.action_type == ActionType.USE_SKILL:
                self.roll = None
                self.dirty_choice = None
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.ARMOR_ROLL)
        roll = self.roll
        iron_skin = (self.game.is_season3 and self.player.has_skill(Skill.IRON_HARD_SKIN)
                     and self.inflictor is not None and self.inflictor.team != self.player.team)
        roll.modifiers = 0 if iron_skin else self.modifiers
        roll.target = self.player.get_armor_target()
        result = roll.get_result()
        self.armor_rolled = True

        armor_broken = False
        mighty_blow_used = False
        dirty_player_used = False

        if not self.foul:
            # Armor broken - Claws
            if roll.sum >= 8 and not iron_skin and (self.claws if self.game.is_season3 else
                    self.inflictor is not None and self.inflictor.has_skill(Skill.CLAWS)):
                armor_broken = True

            # Armor broken
            if result >= roll.target:
                armor_broken = True
            elif not iron_skin and not armor_broken and result == roll.target -1 and (
                    self.damage_skill is not None if self.game.is_season3 else
                    self.inflictor is not None and self.inflictor.has_skill(Skill.MIGHTY_BLOW)):
                # only use mighty_blow if it makes the armour break
                roll.modifiers += 1
                armor_broken = True
                mighty_blow_used = True
        else:

            # Armor broken - Dirty player
            if not iron_skin and self.inflictor is not None and self.inflictor.has_usable_skill(Skill.DIRTY_PLAYER) \
                    and result == self.player.get_armor_target() - 1:
                if (self.game.is_season3 and roll.same() and self.inflictor.has_usable_skill(Skill.SNEAKY_GIT)
                        and self.dirty_choice is None):
                    self.waiting_skill = Skill.DIRTY_PLAYER
                    return False
                if self.dirty_choice is not False:
                    roll.modifiers += 1
                    armor_broken = True
                    dirty_player_used = True

            # Armor broken
            if result >= roll.target:
                armor_broken = True

        if self.game.is_season3 and not armor_broken and self.lone_fouler and not self.lone_fouler_used:
            if self.inflictor.has_usable_skill(Skill.SNEAKY_GIT):
                self.waiting_skill = Skill.LONE_FOULER
                return False
            self.lone_fouler_used = True
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.inflictor,
                                     skill=Skill.LONE_FOULER, rolls=[roll]))
            self.roll = None
            self.dirty_choice = None
            return False

        # EJECTION?
        if self.foul and roll.same():
            # Sneaky git
            if not self.inflictor.has_skill(Skill.SNEAKY_GIT) or armor_broken:
                self.ejected = True

        # Break armor - roll injury
        if self.ejected and self.foul_check is not None:
            self.foul_check.caught = True
        if armor_broken:
            if self.knockdown_on_break:
                KnockDown(self.game, self.player, armor_roll=False, inflictor=self.inflictor,
                          turnover=self.player.team == self.game.state.current_team,
                          casualty_credit=self.casualty_credit, block=self.block)
            else:
                Injury(self.game, self.player, self.inflictor, foul=self.foul,
                       mighty_blow_used=mighty_blow_used, dirty_player_used=dirty_player_used,
                       foul_check=self.foul_check, damage_skill=self.damage_skill,
                       casualty_credit=self.casualty_credit, block=self.block)
            self.game.report(Outcome(OutcomeType.ARMOR_BROKEN, player=self.player, opp_player=self.inflictor,
                                     rolls=[roll]))
        else:
            self.game.report(Outcome(OutcomeType.ARMOR_NOT_BROKEN, player=self.player, opp_player=self.inflictor,
                                     rolls=[roll]))

        return True

    def end(self):
        if self.ejected and self.foul_check is None:
            Ejection(self.game, self.inflictor)

    def available_actions(self):
        if self.waiting_skill is not None:
            return [ActionChoice(kind, team=self.inflictor.team, skill=self.waiting_skill)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        return []


class Stab(Procedure):

    def __init__(self, game, attacker, defender, blitz=False, gfi=False):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.roll = None
        self.reroll = None
        self.blitz = blitz
        self.gfi = gfi

    def end(self):
        self.attacker.state.has_blocked = True

    def step(self, action):
        # GfI
        if self.gfi:
            self.gfi = False
            GFI(self.game, self.attacker, self.attacker.position)
            return False

        if self.game.is_season3:
            SpecialAttack(self.game, self.attacker, self.defender, Skill.STAB)
            return True

        # Stab!
        self.roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], lowest_fail=False, highest_succeed=False)
        self.roll.target = self.defender.get_av()
        if self.attacker.has_skill(Skill.STAKES) and self.defender.team.race in \
                ['Khemri', 'Necromantic', 'Undead', 'Vampire']:
            self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.STAB, player=self.attacker))
            self.roll.modifiers += 1
        if self.roll.is_d6_success():
            KnockDown(self.game, player=self.defender, armor_roll=False, inflictor=self.attacker)
        self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.STAB, player=self.attacker, rolls=[self.roll]))
        return True


class FoulAppearance(Procedure):

    def __init__(self, game, attacker, defender):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.roll = None
        self.reroll = None
        self.revolted = False

    def step(self, action):
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)])
            self.roll.target = 2
            self.game.report(
                Outcome(OutcomeType.SKILL_USED, skill=Skill.FOUL_APPEARANCE, player=self.attacker, rolls=[self.roll]))
            if self.roll.is_d6_success():
                return True
            else:
                self.revolted = True
                self.reroll = Reroll(self.game, self.attacker, self)
                return False

        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.reroll = None
            self.roll = None
            self.revolted = False
            return False
        return True


class Dauntless(Procedure):
    def __init__(self, game, player, defender):
        super().__init__(game)
        self.player = player
        self.defender = defender
        self.roll = None
        self.reroll = None
        self.success = False

    def step(self, action):
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.STRENGTH_ROLL)
            self.success = self.roll.get_sum() + self.player.get_st() > self.defender.get_st()
            self.game.report(Outcome(OutcomeType.DAUNTLESS_USED, player=self.player, rolls=[self.roll], n=self.success))
            if not self.success:
                self.reroll = Reroll(self.game, self.player, context=self)
                return False
        elif self.reroll is not None and self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        return True


class Block(Procedure):

    def __init__(self, game, attacker, defender, blitz=False, frenzy_block=False, gfi=False, ball_and_chain=False):
        super().__init__(game)
        assert attacker != defender
        self.attacker = attacker
        self.defender = defender
        self.roll = None
        self.reroll = None
        self.blitz = blitz
        self.gfi = gfi
        self.ball_and_chain = ball_and_chain
        self.frenzy_block = frenzy_block
        self.waiting_wrestle_attacker = False
        self.waiting_wrestle_defender = False
        self.waiting_juggernaut = False
        self.juggernaut_checked = False
        self.selected_die = None
        self.favor = None
        self.dauntless_roll = None
        self.dauntless_success = False
        self.dauntless = None
        self.strength_modifier = 0
        self.frenzy_checked = False
        self.previous_block = None
        self.waiting_dump_off = False
        self.waiting_foul_appearance = False
        self.foul_appearance = None
        self.cheering_assist = None
        self.trickster = None
        self.trickster_checked = not game.is_season3 or ball_and_chain
        self.reactions_ready = not game.is_season3

    def skill_available(self, player, skill):
        return player.has_usable_skill(skill)

    def knock_down(self, player, **kwargs):
        KnockDown(self.game, player, **kwargs)

    def push(self, **kwargs):
        Push(self.game, self.attacker, self.defender, **kwargs)

    def start(self):
        if self.frenzy_block and not self.frenzy_eligible():
            return
        self.waiting_dump_off = self.game.get_ball_carrier() == self.defender and self.skill_available(self.defender, Skill.DUMP_OFF) and not self.frenzy_block and not (self.game.is_season3 and self.skill_available(self.defender, Skill.MY_BALL))
        self.waiting_foul_appearance = self.skill_available(self.defender, Skill.FOUL_APPEARANCE) and not self.ball_and_chain

    def end(self):
        self.attacker.state.has_blocked = True
        if self.game.is_season3 and self.selected_die is not None:
            AfterBlock(self.game, self.attacker, self.defender,
                       knocked_down=self.selected_die in (BBDieResult.DEFENDER_DOWN,
                                                          BBDieResult.DEFENDER_STUMBLES,
                                                          BBDieResult.BOTH_DOWN))
        if self.trickster is not None and self.trickster.used and self.game.is_touchdown(self.defender):
            Touchdown(self.game, self.defender)

    def step(self, action):

        if self.frenzy_block and not self.frenzy_checked:
            if not self.frenzy_eligible():
                return True
            self.frenzy_checked = True
            if self.game.is_season3 and self.blitz:
                self.attacker.state.moves += 1
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.FRENZY))
            self.attacker.use_skill(Skill.FRENZY)

        # GfI
        if self.gfi:
            self.gfi = False
            GFI(self.game, self.attacker, self.attacker.position)
            return False

        # Foul appearance
        if self.waiting_foul_appearance:
            if not self.foul_appearance:
                self.foul_appearance = FoulAppearance(self.game, self.attacker, self.defender)
                return False
            elif self.foul_appearance.revolted:
                if self.game.is_season3:
                    EndPlayerTurn(self.game, self.attacker)
                return True
            else:
                self.waiting_foul_appearance = False
                self.foul_appearance = None

        # Foul Appearance must be settled before reactive movement can roll a
        # pickup or Dump-off can roll a pass.
        if not self.reactions_ready:
            if not self.trickster_checked:
                self.trickster_checked = True
                if self.skill_available(self.defender, Skill.TRICKSTER):
                    self.trickster = Trickster(self.game, self.attacker, self.defender)
                    return False
            self.reactions_ready = True
            self.waiting_dump_off = (self.game.has_ball(self.defender) and not self.frenzy_block
                                     and self.skill_available(self.defender, Skill.DUMP_OFF)
                                     and not self.defender.has_skill(Skill.MY_BALL))
            if self.waiting_dump_off:
                return False

        # Dump-off
        if self.waiting_dump_off:
            if action.action_type == ActionType.USE_SKILL:
                PassAction(self.game, self.defender, dump_off=True)
            self.waiting_dump_off = False
            return False

        # Juggernaut
        if self.waiting_juggernaut:
            if action.action_type == ActionType.USE_SKILL:
                self.selected_die = BBDieResult.PUSH
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.JUGGERNAUT))
            self.waiting_juggernaut = False
            self.juggernaut_checked = True
            return self.handle_block_die(ActionType.SELECT_PUSH if self.selected_die == BBDieResult.PUSH
                                         else ActionType.SELECT_BOTH_DOWN)

        # Attacker wrestle action
        if self.waiting_wrestle_attacker:
            self.waiting_wrestle_attacker = False
            if action.action_type == ActionType.USE_SKILL:
                self.knock_down(self.attacker, armor_roll=False, injury_roll=False, inflictor=self.defender)
                self.knock_down(self.defender, armor_roll=False, injury_roll=False, inflictor=self.attacker)
                self.waiting_wrestle_defender = False
                return True
            elif self.waiting_wrestle_defender:
                return False
            else:
                return self.both_down()

        # Defender wrestle action
        if self.waiting_wrestle_defender:
            self.waiting_wrestle_defender = False
            if action.action_type == ActionType.USE_SKILL:
                self.knock_down(self.defender, armor_roll=False, injury_roll=False,
                          inflictor=self.attacker)
                self.knock_down(self.attacker, armor_roll=False, injury_roll=False,
                          inflictor=self.defender)
                return True
            else:
                return self.both_down()

        # Roll
        if self.roll is None:

            # Assists
            if self.defender.get_st() > self.attacker.get_st() and self.skill_available(self.attacker, Skill.DAUNTLESS) \
                    and self.dauntless_roll is None:
                if self.game.is_season3:
                    if self.dauntless is None:
                        self.dauntless = Dauntless(self.game, self.attacker, self.defender)
                        return False
                    self.dauntless_roll = self.dauntless.roll
                    self.dauntless_success = self.dauntless.success
                else:
                    self.dauntless_roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.STRENGTH_ROLL)
                    self.dauntless_success = self.dauntless_roll.get_sum() + self.attacker.get_st() > self.defender.get_st()
                    self.game.report(Outcome(OutcomeType.DAUNTLESS_USED, team=self.attacker.team, player=self.attacker,
                                             rolls=[self.dauntless_roll], n=True))
                    return False

            # Report Horns
            if self.blitz and self.skill_available(self.attacker, Skill.HORNS):
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.HORNS))

            if self.cheering_assist is None:
                self.cheering_assist = self.game.cheering_assist_available(self.attacker.team)
                if self.cheering_assist:
                    self.attacker.team.state.cheering_fans = False
                    self.game.report(Outcome(OutcomeType.CHEERING_ASSIST_USED, team=self.attacker.team))
            dice = self.game.num_block_dice(self.attacker, self.defender, blitz=self.blitz,
                                            dauntless_success=self.dauntless_success,
                                            extra_assists=int(self.cheering_assist), strength_modifier=self.strength_modifier)
            self.favor = self.attacker.team if dice > 0 else self.defender.team

            # Roll
            self.roll = DiceRoll([], roll_type=RollType.BLOCK_ROLL)

            for i in range(abs(dice)):
                self.roll.dice.append(BBDie(self.game.rng))

            self.game.report(Outcome(OutcomeType.BLOCK_ROLL, player=self.attacker, opp_player=self.defender,
                                     rolls=[self.roll]))

            # check for re-roll
            self.reroll = Reroll(self.game, self.attacker, context=self)
            return False

        # If re-roll decision is made
        elif self.reroll is not None:
            if self.reroll.use_reroll:
                # reroll!
                self.roll = None
                self.reroll = None
                return False
            elif self.reroll.block_action:
                # If block die was selected in Reroll
                action = self.reroll.block_action
            else:
                # Add secondary clock if opponent has the favor
                if self.favor == self.defender.team:
                    self.game.add_secondary_clock(self.favor)
                self.reroll = None
                return False

        return self.handle_block_die(action.action_type)

    def frenzy_eligible(self):
        return (self.attacker.position is not None and self.attacker.state.up and
                self.defender.position is not None and self.defender.state.up and
                self.defender in self.game.get_adjacent_opponents(self.attacker) and
                (self.previous_block is None or self.previous_block.selected_die in
                 (BBDieResult.PUSH, BBDieResult.DEFENDER_STUMBLES, BBDieResult.DEFENDER_DOWN)))

    def handle_block_die(self, action_type):

        # Select die
        if action_type == ActionType.SELECT_ATTACKER_DOWN:
            self.selected_die = BBDieResult.ATTACKER_DOWN
        elif action_type == ActionType.SELECT_BOTH_DOWN:
            self.selected_die = BBDieResult.BOTH_DOWN
        elif action_type == ActionType.SELECT_PUSH:
            self.selected_die = BBDieResult.PUSH
        elif action_type == ActionType.SELECT_DEFENDER_STUMBLES:
            self.selected_die = BBDieResult.DEFENDER_STUMBLES
        elif action_type == ActionType.SELECT_DEFENDER_DOWN:
            self.selected_die = BBDieResult.DEFENDER_DOWN

        # Remove secondary clocks
        assert self.selected_die is not None

        BBDie.FixedRolls.append(self.selected_die)
        die = BBDie(None)
        self.game.report(Outcome(OutcomeType.ACTION_SELECT_DIE, team=self.favor, rolls=[DiceRoll([die])]))

        self.game.remove_secondary_clocks()

        if self.game.is_season3:
            # Effects run above this boundary; scoring/turnover cannot purge
            # unresolved knockdowns, chain pushes, injuries or treatment.
            BlockResolution(self.game)

        # Dice result
        if self.selected_die == BBDieResult.ATTACKER_DOWN:
            # Turnover(self.game)
            self.knock_down(self.attacker, inflictor=self.defender, turnover=True, block=True)
            return True

        elif self.selected_die == BBDieResult.BOTH_DOWN:

            if self.blitz and self.skill_available(self.attacker, Skill.JUGGERNAUT) and not self.juggernaut_checked:
                self.waiting_juggernaut = True
                return False

            # Attacker wrestle - Don't use if only one with Block skill
            if self.skill_available(self.attacker, Skill.WRESTLE) and (self.game.is_season3 or not (self.skill_available(self.attacker, Skill.BLOCK) and not self.skill_available(self.defender, Skill.BLOCK))):
                self.waiting_wrestle_attacker = True

            # Defender wrestle - Don't use if only one with Block skill
            if self.skill_available(self.defender, Skill.WRESTLE) and (self.game.is_season3 or not (self.skill_available(self.defender, Skill.BLOCK) and not self.skill_available(self.attacker, Skill.BLOCK))):
                if self.blitz and self.skill_available(self.attacker, Skill.JUGGERNAUT):
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.JUGGERNAUT))
                else:
                    self.waiting_wrestle_defender = True

            if self.waiting_wrestle_attacker or self.waiting_wrestle_defender:
                return False

            return self.both_down()

        elif self.selected_die == BBDieResult.DEFENDER_DOWN:
            self.push(knock_down=True, blitz=self.blitz)
            return True

        elif self.selected_die == BBDieResult.DEFENDER_STUMBLES:
            self.push(knock_down=(not self.skill_available(self.defender, Skill.DODGE)) or self.skill_available(self.attacker, Skill.TACKLE),
                 blitz=self.blitz)
            return True

        elif self.selected_die == BBDieResult.PUSH:
            self.push(knock_down=False, blitz=self.blitz)
            return True

        return False

    def both_down(self):
        falling = []
        # Attacker down
        if not self.skill_available(self.attacker, Skill.BLOCK):
            self.knock_down(self.attacker, inflictor=self.defender, turnover=True, block=True)
            falling.append(self.attacker)
        else:
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.BLOCK))
        # Defender down
        if not self.skill_available(self.defender, Skill.BLOCK):
            self.knock_down(self.defender, inflictor=self.attacker, block=True,
                      turnover=self.game.is_season3 and self.defender.team == self.game.state.current_team)
            falling.append(self.defender)
        else:
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.defender, skill=Skill.BLOCK))
        if self.game.is_season3:
            # Snapshot skill eligibility in KnockDown before both become Prone.
            for player in falling:
                player.place_prone()
        return True

    def available_actions(self):
        if not self.attacker.state.up and not isinstance(self, MultipleBlockEffect):
            return []
        if not self.reactions_ready:
            return []
        if self.waiting_dump_off:
            return [
                ActionChoice(ActionType.USE_SKILL, skill=Skill.DUMP_OFF, players=[self.defender],
                             team=self.defender.team),
                ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.DUMP_OFF, players=[self.defender],
                             team=self.defender.team)
            ]
        if self.roll is None:
            return []
        if self.reroll is not None and self.reroll.done:
            return []
        if self.waiting_juggernaut:
            return [
                ActionChoice(ActionType.USE_SKILL, self.attacker.team, skill=Skill.JUGGERNAUT),
                ActionChoice(ActionType.DONT_USE_SKILL, self.attacker.team, skill=Skill.JUGGERNAUT)
            ]
        if self.waiting_wrestle_attacker:
            return [
                ActionChoice(ActionType.USE_SKILL, self.attacker.team, skill=Skill.WRESTLE),
                ActionChoice(ActionType.DONT_USE_SKILL, self.attacker.team, skill=Skill.WRESTLE)
            ]
        if self.waiting_wrestle_defender:
            return [
                ActionChoice(ActionType.USE_SKILL, self.defender.team, skill=Skill.WRESTLE),
                ActionChoice(ActionType.DONT_USE_SKILL, self.defender.team, skill=Skill.WRESTLE)
            ]
        assert self.selected_die is None
        disable_dice_pick = False
        if self.reroll is not None and self.reroll.use_reroll is None and self.favor != self.attacker.team:
            disable_dice_pick = True
        actions = []
        for die in self.roll.dice:
            if die.get_value() == BBDieResult.ATTACKER_DOWN:
                actions.append(ActionChoice(ActionType.SELECT_ATTACKER_DOWN, self.favor, disabled=disable_dice_pick))
            if die.get_value() == BBDieResult.BOTH_DOWN:
                actions.append(ActionChoice(ActionType.SELECT_BOTH_DOWN, self.favor, disabled=disable_dice_pick))
            if die.get_value() == BBDieResult.PUSH:
                actions.append(ActionChoice(ActionType.SELECT_PUSH, self.favor, disabled=disable_dice_pick))
            if die.get_value() == BBDieResult.DEFENDER_STUMBLES:
                actions.append(ActionChoice(ActionType.SELECT_DEFENDER_STUMBLES, self.favor, disabled=disable_dice_pick))
            if die.get_value() == BBDieResult.DEFENDER_DOWN:
                actions.append(ActionChoice(ActionType.SELECT_DEFENDER_DOWN, self.favor, disabled=disable_dice_pick))
        return actions


class MultipleBlockRoll(Block):
    """Select dice for both simultaneous blocks before applying either result."""

    def __init__(self, game, attacker, defender):
        super().__init__(game, attacker, defender)
        self.chosen_action = None
        self.strength_modifier = -2
        self.skills = {p.player_id: {s for s in p.get_skills() if p.has_usable_skill(s)}
                       for p in (attacker, defender)}

    def handle_block_die(self, action_type):
        self.chosen_action = action_type
        return True

    def end(self):
        pass


class MultipleBlockEffect(Block):
    def __init__(self, game, source, origin):
        super().__init__(game, source.attacker, source.defender)
        self.source = source
        self.origin = origin
        self.roll = source.roll
        self.favor = source.favor
        self.initial = True
        self.reactions_ready = True
        self.trickster_checked = True

    def start(self):
        pass  # Reactions and all dice choices already ran during the roll phase.

    def skill_available(self, player, skill):
        return skill in self.source.skills.get(player.player_id, ())

    def knock_down(self, player, **kwargs):
        # A simultaneous result cannot knock an already removed/prone player
        # down again. A successful Steady Footing roll leaves them eligible.
        if player.position is None or not player.state.up:
            return
        inflictor = kwargs.get('inflictor')
        if kwargs.get('block') and inflictor is not None and self.skill_available(inflictor, Skill.MIGHTY_BLOW):
            kwargs['damage_skill'] = Skill.MIGHTY_BLOW
        proc = KnockDown(self.game, player, **kwargs)
        if kwargs.get('block') and inflictor is not None:
            proc.claws = self.skill_available(inflictor, Skill.CLAWS)

    def push(self, **kwargs):
        if self.defender.position is not None:
            Push(self.game, self.attacker, self.defender, block_context=self, **kwargs)

    def step(self, action):
        if self.initial:
            self.initial = False
            action = Action(self.source.chosen_action)
        return super().step(action)

    def available_actions(self):
        return [] if self.initial else super().available_actions()

    def end(self):
        self.attacker.state.has_blocked = True


class MultipleBlock(Procedure):
    def __init__(self, game, attacker):
        super().__init__(game)
        self.attacker = attacker
        self.origin = attacker.position
        self.targets = []
        self.rolls = []
        self.effects = []
        self.reduced = False
        self.turnover = False
        self.scorers = ()
        self.activation_ended = False

    def step(self, action):
        if len(self.targets) < 2:
            self.targets.append(action.player)
            return False
        if not self.reduced:
            self.reduced = True
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.MULTIPLE_BLOCK))
        if len(self.rolls) < 2:
            self.rolls.append(MultipleBlockRoll(self.game, self.attacker, self.targets[len(self.rolls)]))
            return False
        if len(self.effects) < 2:
            source = self.rolls[len(self.effects)]
            effect = MultipleBlockEffect(self.game, source, self.origin) if source.chosen_action is not None else None
            self.effects.append(effect)
            return False
        if self.turnover:
            Turnover(self.game)
        for player in self.scorers:
            if self.game.is_touchdown(player):
                Touchdown(self.game, player)
        for effect in reversed(self.effects):
            if effect is not None:
                AfterBlock(self.game, self.attacker, effect.defender,
                           knocked_down=effect.selected_die in (BBDieResult.DEFENDER_DOWN,
                                                                BBDieResult.DEFENDER_STUMBLES, BBDieResult.BOTH_DOWN))
        return True

    def available_actions(self):
        if len(self.targets) >= 2:
            return []
        players = [p for p in self.game.get_adjacent_opponents(self.attacker, down=False) if p not in self.targets]
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.attacker.team, players=players, skill=Skill.MULTIPLE_BLOCK)]


class Bounce(Procedure):

    def __init__(self, game, piece, kick=False):
        super().__init__(game)
        self.piece = piece
        self.kick = kick

    def step(self, action):

        # Loose control
        if self.piece.is_catchable():
            self.piece.is_carried = False

        # Roll
        roll_scatter = DiceRoll([D8(self.game.rng)], roll_type=RollType.BOUNCE_ROLL)
        result = roll_scatter.get_sum()

        # Bounce
        x = 0
        y = 0
        if result in [1, 4, 6]:
            x = -1
        if result in [3, 5, 8]:
            x = 1
        if result in [1, 2, 3]:
            y = -1
        if result in [6, 7, 8]:
            y = 1

        self.game.shove(self.piece, x, y)
        if type(self.piece) is Ball:
            self.game.report(Outcome(OutcomeType.BALL_BOUNCED, position=self.piece.position, rolls=[roll_scatter]))
        elif type(self.piece) is Player:
            self.game.report(Outcome(OutcomeType.PLAYER_BOUNCED, position=self.piece.position, rolls=[roll_scatter]))

        if self.kick:
            # Touchback
            if not self.game.is_team_side(self.piece.position, self.game.get_receiving_team()):
                Touchback(self.game, self.piece)
                self.game.report(Outcome(OutcomeType.TOUCHBACK, team=self.game.get_receiving_team(),
                                         rolls=[roll_scatter]))
                return True
        else:
            # Out of bounds
            if self.game.is_out_of_bounds(self.piece.position):
                if type(self.piece) is Ball:
                    ThrowIn(self.game, self.piece, self.game.get_square(self.piece.position.x - x, self.piece.position.y - y))
                    self.game.report(Outcome(OutcomeType.BALL_OUT_OF_BOUNDS))
                elif type(self.piece) is Player:
                    KnockDown(self.game, self.piece, in_crowd=True)
                    self.game.report(Outcome(OutcomeType.PLAYER_OUT_OF_BOUNDS, player=self.piece))
                return True

        # On player -> Catch
        player_at = self.game.get_player_at(self.piece.position)
        if player_at is not None:
            if self.piece.is_catchable():
                Catch(self.game, player_at, self.piece)
            if type(self.piece) is Ball:
                self.game.report(Outcome(OutcomeType.BALL_BOUNCE_PLAYER, position=self.piece.position, player=player_at))
            elif type(self.piece) is Player:
                self.game.report(Outcome(OutcomeType.PLAYER_BOUNCE_PLAYER, position=self.piece.position, player=player_at))
                Bounce(self.game, self.piece)
            return True

        # On empty square
        if type(self.piece) is Ball:
            self.game.report(Outcome(OutcomeType.BALL_BOUNCE_GROUND, position=self.piece.position))
        elif type(self.piece) is Player:
            self.game.report(Outcome(OutcomeType.PLAYER_BOUNCE_GROUND, player=self.piece, position=self.piece.position))
            Land(self.game, self.piece)
        return True

    def available_actions(self):
        return []


class Casualty(Procedure):

    def __init__(self, game, player, inflictor=None, decay=False, blood_lust=False, always_hungry=False,
                 badly_hurt=False, casualty_credit=False, block=False):
        super().__init__(game)
        self.player = player
        self.inflictor = inflictor
        self.waiting_apothecary = False
        self.roll = None
        self.casualty = None
        self.effect = None
        self.decay = decay
        self.regeneration = None
        self.blood_lust = blood_lust
        self.always_hungry = always_hungry
        self.badly_hurt = badly_hurt
        self.casualty_credit = casualty_credit
        self.credited = False
        self.block = block

    def step(self, action):

        if self.game.is_season3:
            if self.casualty_credit and not self.credited and self.inflictor is not None and self.inflictor.team != self.player.team:
                # Credit is earned even when regeneration or an apothecary saves
                # the victim. Award once before either treatment can run.
                self.inflictor.state.spp_earned += 2
                self.credited = True
            if self.always_hungry:
                self.game.apply_casualty(self.player, self.inflictor, Season3CasualtyType.DEAD,
                                         CasualtyEffect.DEAD, DiceRoll([], roll_type=RollType.CASUALTY_ROLL))
                return True
            if self.regeneration is None and self.player.has_skill(Skill.REGENERATION):
                self.regeneration = Regeneration(self.game, self.player)
                return False
            if self.regeneration is not None and self.regeneration.regenerates:
                if self.player.position is not None:
                    self.game.pitch_to_reserves(self.player)
                return True
            if self.badly_hurt or self.blood_lust:
                self.roll = DiceRoll([], roll_type=RollType.CASUALTY_ROLL)
                self.casualty, self.effect = Season3CasualtyType.BADLY_HURT, CasualtyEffect.NONE
            else:
                self.roll = DiceRoll([D16(self.game.rng)],
                                     modifiers=self.player.num_niggling_injuries() + int(self.player.has_skill(Skill.DECAY)),
                                     roll_type=RollType.CASUALTY_ROLL)
                self.casualty, self.effect = _season3_casualty_result(self.roll)
            self.game.report(Outcome(OutcomeType.CASUALTY_RESULT, player=self.player,
                                     n=self.casualty.name, rolls=[self.roll]))
            if self.player.team.state.apothecaries:
                Apothecary(self.game, self.player, self.roll, OutcomeType.CASUALTY, self.inflictor,
                           casualty=self.casualty, effect=self.effect)
            else:
                self.game.apply_casualty(self.player, self.inflictor, self.casualty, self.effect, self.roll)
            return True

        if self.regeneration:
            if self.regeneration.regenerates:
                if self.player.position is not None:
                    self.game.pitch_to_reserves(self.player)
                return True
            self.regeneration = None

        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng), D8(self.game.rng)], d68=True, roll_type=RollType.CASUALTY_ROLL)
            cas_rolls = None
            if self.blood_lust: 
                result = 38
            elif self.always_hungry:
                result = 61
            else:
                result = self.roll.get_sum()
                cas_rolls = [self.roll]
            
            n = min(61, max(38, result))
            self.casualty = CasualtyType(n)
            self.effect = Rules.casualty_effect[self.casualty]

            self.game.report(
                Outcome(OutcomeType.CASUALTY, player=self.player, opp_player=self.inflictor, team=self.player.team,
                        n=self.effect.name,
                        rolls=cas_rolls))

            if not self.always_hungry:
                if self.player.team.state.apothecaries > 0:
                    Apothecary(self.game, self.player, roll=self.roll, outcome=OutcomeType.CASUALTY,
                               casualty=self.casualty, effect=self.effect, inflictor=self.inflictor)
                    return True
                else:
                    # Regeneration
                    if self.player.has_skill(Skill.REGENERATION) and not self.regeneration:
                        self.regeneration = Regeneration(self.game, self.player)
                        return False

        # Apply casualty
        self.game.apply_casualty(self.player, self.inflictor, self.casualty, self.effect, self.roll)

        # Decay
        if self.decay:
            self.game.report(Outcome(OutcomeType.DECAYING, player=self.player))
            Casualty(self.game, self.player)

        return True


    def end(self):
        if (self.game.is_season3 and self.block and self.inflictor is not None
                and self.inflictor.team != self.player.team
                and self.inflictor.has_skill(Skill.PLAGUE_RIDDEN)
                and not self.inflictor.team.state.plague_ridden_used
                and CasualtyEffect.DEAD in self.player.state.injuries_gained
                and 'Big Guy' not in self.player.role.keywords
                and not any(self.player.has_skill(skill) for skill in (Skill.DECAY, Skill.REGENERATION, Skill.STUNTY))):
            PlagueRidden(self.game, self.inflictor)
        if (self.game.is_season3 and self.roll is not None and
                CasualtyEffect.DEAD in self.player.state.injuries_gained and
                self.player.get_st() <= 4 and not self.player.has_skill(Skill.STUNTY)):
            team = self.game.get_opp_team(self.player.team)
            if self.game.has_team_rule(team, 'Masters of Undeath') and not team.state.raised_dead:
                RaiseDead(self.game, team)


class RaiseDead(Procedure):
    """Choose the roster's actual Lineman type after a confirmed casualty death."""

    def __init__(self, game, team):
        super().__init__(game)
        self.team = team
        self.roles = {ActionType.RAISE_ZOMBIE if 'Zombie' in role.name else
                      ActionType.RAISE_SKELETON if 'Skeleton' in role.name else ActionType.RAISE_THRALL: role.name
                      for race in game.ruleset.races if race.name == team.race
                      for role in race.roles if 'Lineman' in role.keywords}

    def step(self, action):
        if action is not None and action.action_type in self.roles:
            role = self.game.ruleset.get_role(self.roles[action.action_type], self.team.race)
            number = max((p.nr for p in self.team.players), default=0) + 1
            identity = '{}-raised-{}'.format(self.team.team_id, number)
            recruit = Player(identity, role, role.name, number, self.team)
            self.team.state.raised_dead = True
            self.team.players.append(recruit)
            self.game.state.player_by_id[identity] = recruit
            self.game.state.team_by_player_id[identity] = self.team
            self.game.get_reserves(self.team).append(recruit)
            self.game.report(Outcome(OutcomeType.RAISED_DEAD, team=self.team, player=recruit))
        return True

    def available_actions(self):
        if not self.roles or self.team.state.raised_dead:
            return []
        return [ActionChoice(kind, team=self.team) for kind in self.roles] + [
            ActionChoice(ActionType.SELECT_NONE, team=self.team)]


class PlagueRidden(Procedure):
    """Offer a replacement only after the casualty and treatment have finished."""

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.roles = [role.name for race in game.ruleset.races if race.name == player.team.race
                      for role in race.roles if 'Lineman' in role.keywords]

    def step(self, action):
        if action is not None and action.action_type == ActionType.USE_SKILL and self.roles:
            team = self.player.team
            team.state.plague_ridden_used = True
            number = max((p.nr for p in team.players), default=0) + 1
            identity = '{}-plague-{}'.format(team.team_id, number)
            while identity in self.game.state.player_by_id:
                number += 1
                identity = '{}-plague-{}'.format(team.team_id, number)
            # Every roster with this trait has one Lineman profile. Keep the
            # canonical profile, including Decay and regeneration parameters.
            role = self.game.ruleset.get_role(self.roles[0], team.race)
            recruit = Player(identity, role, role.name, number, team)
            team.players.append(recruit)
            self.game.state.player_by_id[identity] = recruit
            self.game.state.team_by_player_id[identity] = team
            self.game.get_reserves(team).append(recruit)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                     opp_player=recruit, skill=Skill.PLAGUE_RIDDEN))
        return True

    def available_actions(self):
        if not self.roles:
            return []
        return [ActionChoice(kind, team=self.player.team, skill=Skill.PLAGUE_RIDDEN)
                for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]


class Catch(Procedure):

    def __init__(self, game, player, piece, accurate=False, handoff=False, kick=False, passer=None, inaccurate=False, punt=False, target_square=None):
        super().__init__(game)
        self.player = player
        self.piece = piece
        self.accurate = accurate
        self.inaccurate = inaccurate
        self.punt = punt
        self.target_square = target_square
        self.handoff = handoff
        self.roll = None
        self.reroll = None
        self.kick = kick
        self.passer = passer
        self.diving = player.position != piece.position
        self.bomb_choice = None

    def start(self):
        if self.diving:
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.DIVING_CATCH))

    def step(self, action):

        # You can decide not to catch a bomb
        if type(self.piece) is Bomb and self.bomb_choice is None and not self.game.is_season3:
            if action.action_type == ActionType.CATCH_BOMB:
                self.bomb_choice = True
                self.game.report(Outcome(OutcomeType.WILL_CATCH_BOMB, player=self.player))
            else:
                Explode(self.game, self.piece)
                self.game.report(Outcome(OutcomeType.WONT_CATCH_BOMB, player=self.player))
                return

        # Otherwise roll if player hasn't rolled
        if self.roll is None:

            # Can player even catch ball?
            if not self.player.can_catch():
                if type(self.piece) is Ball:
                    Bounce(self.game, self.piece, kick=self.kick and self.game.is_season3)
                    self.game.report(Outcome(OutcomeType.FAILED_CATCH, player=self.player))
                elif type(self.piece) is Bomb:
                    Explode(self.game, self.piece)
                    self.game.report(Outcome(OutcomeType.FAILED_CATCH_BOMB, player=self.player))
                return True

            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.modifiers = self.game.get_catch_modifiers(
                self.player, accurate=self.accurate, kick=self.kick,
                handoff=self.handoff, inaccurate=self.inaccurate, punt=self.punt, target_square=self.target_square)
            self.roll.target = self.player.get_ag_target()
            if self.roll.is_d6_success():
                if type(self.piece) is Ball:
                    self.game.report(Outcome(OutcomeType.SUCCESSFUL_CATCH, player=self.player, rolls=[self.roll]))
                elif type(self.piece) is Bomb:
                    self.game.report(Outcome(OutcomeType.SUCCESSFUL_CATCH_BOMB, player=self.player, rolls=[self.roll]))
                    ThrowBombAction(self.game, self.player, rethrow=self.game.is_season3)
                if self.diving:
                    self.game.move(self.piece, self.player.position)
                self.piece.is_carried = True
                if self.game.is_touchdown(self.player):
                    Touchdown(self.game, self.player)
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_CATCH, player=self.player, rolls=[self.roll]))
                # Check for re-roll
                self.reroll = Reroll(self.game, self.player, context=self)
                return False

        assert self.reroll is not None

        # If re-roll used
        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        else:
            # If diving tackle was used - bounce from player's square
            if self.diving:
                self.game.move(self.piece, self.player.position)
            if self.game.is_season3 and type(self.piece) is Bomb:
                Explode(self.game, self.piece)
            else:
                Bounce(self.game, self.piece, kick=self.kick)

        return True

    def available_actions(self):
        if type(self.piece) is Bomb and self.bomb_choice is None and not self.game.is_season3:
            return [ActionChoice(ActionType.CATCH_BOMB, team=self.player.team), ActionChoice(ActionType.DONT_CATCH_BOMB, team=self.player.team)]
        return []


class Intercept(Procedure):

    def __init__(self, game, interceptor, ball, passer=None, inaccurate=False):
        super().__init__(game)
        self.interceptor = interceptor
        self.inaccurate = inaccurate
        self.ball = ball
        self.roll = None
        self.reroll = None
        self.safe_throw_roll = None
        self.safe_throw_reroll = None
        self.passer = passer
        self.waiting_safe_throw = False

    def step(self, action):

        # If waiting for interception re-roll due to Safe Throw skill
        if self.waiting_safe_throw:
            # Make agility roll for passer
            self.safe_throw_roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.safe_throw_roll.target = self.passer.get_ag_target()
            self.game.report(
                Outcome(OutcomeType.SKILL_USED, player=self.passer, skill=Skill.SAFE_THROW, rolls=[self.safe_throw_roll]))
            if self.safe_throw_roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.FAILED_INTERCEPTION, player=self.interceptor))
                return True
            else:
                # Check for re-roll
                self.safe_throw_reroll = Reroll(self.game, self.passer, context=self)
                self.waiting_safe_throw = False
                return False
                # TODO: Check for safe-throw in Reroll

        # If safe throw re-roll decision made
        if self.safe_throw_reroll is not None:
            if self.safe_throw_reroll.use_reroll:
                self.safe_throw_reroll = None
                self.waiting_safe_throw = True
                self.roll = None
                return False
            else:
                self.ball.move_to(self.interceptor.position)
                self.ball.is_carried = True
                if self.game.is_season3 and type(self.ball) is Bomb:
                    ThrowBombAction(self.game, self.interceptor, rethrow=True)
                elif self.game.is_touchdown(self.interceptor):
                    Touchdown(self.game, self.interceptor)
                else:
                    Turnover(self.game)
                return True

        # Otherwise roll if player hasn't rolled
        if self.roll is None:

            # Can player even catch ball?
            if self.interceptor.has_skill(Skill.NO_HANDS) or not self.interceptor.can_catch():
                return True

            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.modifiers = self.game.get_catch_modifiers(
                self.interceptor, interception=True, inaccurate=self.inaccurate)
            self.roll.target = self.interceptor.get_ag_target()
            if self.roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.INTERCEPTION, player=self.interceptor, rolls=[self.roll]))
                if self.passer is not None and self.passer.has_skill(Skill.SAFE_THROW):
                    if self.interceptor.has_skill(Skill.VERY_LONG_LEGS):
                        self.game.report(
                            Outcome(OutcomeType.SKILL_USED, player=self.passer, skill=Skill.SAFE_THROW))
                        self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.interceptor, skill=Skill.VERY_LONG_LEGS))
                    else:
                        self.waiting_safe_throw = True
                        return False
                self.ball.move_to(self.interceptor.position)
                self.ball.is_carried = True
                if self.game.is_season3 and type(self.ball) is Bomb:
                    ThrowBombAction(self.game, self.interceptor, rethrow=True)
                elif self.game.is_touchdown(self.interceptor):
                    Touchdown(self.game, self.interceptor)
                else:
                    Turnover(self.game)
                return True

            else:

                self.game.report(Outcome(OutcomeType.FAILED_INTERCEPTION, player=self.interceptor, rolls=[self.roll]))

                # Check for re-roll
                self.reroll = Reroll(self.game, self.interceptor, context=self)
                return False

        assert self.reroll is not None

        # If re-roll used
        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False

        return True


class CoinTossFlip(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def start(self):
        self.game.add_secondary_clock(self.game.state.away_team)

    def step(self, action):
        if action.action_type == ActionType.HEADS:
            if self.game.rng.rand(1)[0] >= 0.5:
                self.game.state.coin_toss_winner = self.game.state.away_team
                self.game.report(Outcome(OutcomeType.HEADS_WON))
            else:
                self.game.state.coin_toss_winner = self.game.state.home_team
                self.game.report(Outcome(OutcomeType.TAILS_LOSS))
        elif action.action_type == ActionType.TAILS:
            if self.game.rng.rand(1)[0] >= 0.5:
                self.game.state.coin_toss_winner = self.game.state.away_team
                self.game.report(Outcome(OutcomeType.TAILS_WON))
            else:
                self.game.state.coin_toss_winner = self.game.state.home_team
                self.game.report(Outcome(OutcomeType.HEADS_LOSS))

        CoinTossKickReceive(self.game)
        self.game.remove_clocks()
        return True

    def available_actions(self):
        return [ActionChoice(ActionType.HEADS, team=self.game.state.away_team),
                   ActionChoice(ActionType.TAILS, team=self.game.state.away_team)]


class CoinTossKickReceive(Procedure):

    def __init__(self, game):
        super().__init__(game)
        self.aa = [ActionChoice(ActionType.KICK,
                                team=self.game.state.coin_toss_winner),
                   ActionChoice(ActionType.RECEIVE,
                                team=self.game.state.coin_toss_winner)]

    def start(self):
        self.game.add_secondary_clock(self.game.state.coin_toss_winner)

    def step(self, action):
        kicking = None
        receiving = None
        if action.action_type == ActionType.KICK:
            kicking = self.game.state.coin_toss_winner
            receiving = self.game.get_opp_team(self.game.state.coin_toss_winner)
        elif action.action_type == ActionType.RECEIVE:
            kicking = self.game.get_opp_team(self.game.state.coin_toss_winner)
            receiving = self.game.state.coin_toss_winner
        self.game.state.kicking_first_half = kicking
        self.game.state.kicking_this_drive = kicking
        self.game.state.receiving_first_half = receiving
        self.game.state.receiving_this_drive = receiving
        if receiving == self.game.state.home_team:
            self.game.report(Outcome(OutcomeType.HOME_RECEIVE, team=receiving))
        else:
            self.game.report(Outcome(OutcomeType.AWAY_RECEIVE, team=receiving))
        self.game.remove_clocks()
        return True

    def available_actions(self):
        return self.aa


class Ejection(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.awaiting_bribe = False
        self.argue_resolved = False
        self.argue_roll = None
        self.corruption_choice = False

    def start(self):
        self.awaiting_bribe = self.player.team.state.bribes > 0

    def step(self, action):
        if self.game.is_season3:
            return self._step_season3(action)
        # Check if already ejected
        if self.player.state.ejected:
            return True
        if self.awaiting_bribe:
            if action.action_type == ActionType.USE_BRIBE:
                self.player.team.state.bribes -= 1
                self.game.report(Outcome(OutcomeType.BRIBE_USED, team=self.player.team, player=self.player))
                die = D6(self.game.rng)
                roll = DiceRoll([die], roll_type=RollType.BRIBE_ROLL)
                roll.target = 2
                if roll.is_d6_success():
                    self.game.report(Outcome(OutcomeType.SUCCESSFUL_BRIBE, team=self.player.team, player=self.player, rolls=[roll]))
                    return True
                else:
                    self.game.report(Outcome(OutcomeType.FAILED_BRIBE, team=self.player.team, player=self.player, rolls=[roll]))
                    # Allow team to use another bribe
                    self.awaiting_bribe = self.player.team.state.bribes > 0
                    if self.awaiting_bribe:
                        return False

        # Turnover
        Turnover(self.game)

        # Drop ball
        ball = self.game.get_ball_at(self.player.position)
        if ball is not None:
            Bounce(self.game, ball)

        # Eject player
        self.game.pitch_to_dungeon(self.player)
        self.game.report(Outcome(OutcomeType.PLAYER_EJECTED, player=self.player))

        return True

    def available_actions(self):
        if self.game.is_season3:
            if self.corruption_choice:
                return [ActionChoice(kind, team=self.player.team)
                        for kind in (ActionType.USE_REROLL, ActionType.DONT_USE_REROLL)]
            if not self.argue_resolved and self.player.team.state.can_argue:
                return [ActionChoice(ActionType.ARGUE_CALL, team=self.player.team),
                        ActionChoice(ActionType.DONT_ARGUE_CALL, team=self.player.team)]
            if self.player.team.state.bribes:
                return [ActionChoice(ActionType.USE_BRIBE, team=self.player.team),
                        ActionChoice(ActionType.DONT_USE_BRIBE, team=self.player.team)]
            return []
        if self.awaiting_bribe:
            return [ActionChoice(ActionType.USE_BRIBE, team=self.player.team),
                    ActionChoice(ActionType.DONT_USE_BRIBE, team=self.player.team)]
        return []

    def _step_season3(self, action):
        if self.player.state.ejected:
            return True
        if not self.argue_resolved:
            if self.corruption_choice:
                self.corruption_choice = False
                if action.action_type == ActionType.USE_REROLL:
                    self.player.team.state.bribery_used = True
                    self.game.report(Outcome(OutcomeType.BRIBERY_AND_CORRUPTION, team=self.player.team,
                                             rolls=[self.argue_roll]))
                    self.argue_roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.ARGUE_CALL_ROLL)
            elif action is not None and action.action_type == ActionType.ARGUE_CALL:
                self.argue_roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.ARGUE_CALL_ROLL)
                if (self.argue_roll.get_sum() == 1 and not self.player.team.state.bribery_used and
                        self.game.has_team_rule(self.player.team, 'Bribery and Corruption')):
                    self.corruption_choice = True
                    return False
            self.argue_resolved = True
            if self.argue_roll is not None:
                roll = self.argue_roll
                if roll.get_sum() == 6:
                    self.game.report(Outcome(OutcomeType.ARGUE_CALL_SUCCESS, player=self.player, rolls=[roll]))
                    if self.game.state.current_team == self.player.team:
                        Turnover(self.game)
                    return True
                if roll.get_sum() == 1:
                    self.player.team.state.can_argue = False
                    self.game.report(Outcome(OutcomeType.COACH_EJECTED, team=self.player.team, rolls=[roll]))
                else:
                    self.game.report(Outcome(OutcomeType.ARGUE_CALL_FAILED, player=self.player, rolls=[roll]))
            return False
        if action is not None and action.action_type == ActionType.USE_BRIBE:
            self.player.team.state.bribes -= 1
            roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.BRIBE_ROLL, target=2)
            self.game.report(Outcome(OutcomeType.BRIBE_USED, player=self.player))
            if roll.get_sum() >= 2:
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_BRIBE, player=self.player, rolls=[roll]))
                return True
            self.game.report(Outcome(OutcomeType.FAILED_BRIBE, player=self.player, rolls=[roll]))
            if self.player.team.state.bribes:
                return False
        if self.game.state.current_team == self.player.team:
            Turnover(self.game)
        if self.game.has_ball(self.player):
            Bounce(self.game, self.game.get_ball())
        self.game.pitch_to_dungeon(self.player)
        self.game.report(Outcome(OutcomeType.PLAYER_EJECTED, player=self.player))
        return True


class Foul(Procedure):

    def __init__(self, game, fouler, defender):
        super().__init__(game)
        self.fouler = fouler
        self.defender = defender
        self.saw_choice = not (game.is_season3 and fouler.has_usable_skill(Skill.CHAINSAW))
        self.use_saw = False
        self.roll = None
        self.reroll = None
        self.assist_candidates = (game.get_assisting_players(fouler, defender, foul=True)
                                  if game.is_season3 and fouler.has_usable_skill(Skill.SNEAKY_GIT) else [])
        self.selected_assists = []
        self.assists_chosen = not self.assist_candidates

    def step(self, action):
        if not self.saw_choice:
            self.saw_choice = True
            self.use_saw = action.action_type == ActionType.USE_SKILL
        if self.use_saw:
            if self.reroll is not None and self.reroll.use_reroll:
                self.roll = self.reroll = None
            if self.roll is None:
                self.roll = DiceRoll([D6(self.game.rng)], target=2)
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.fouler,
                                         skill=Skill.CHAINSAW, rolls=[self.roll]))
                if not self.roll.is_d6_success():
                    self.reroll = Reroll(self.game, self.fouler, self)
                    return False
            if not self.roll.is_d6_success():
                KnockDown(self.game, self.fouler, turnover=True)
                return True

        if not self.assists_chosen:
            if action is None or action.action_type not in (ActionType.SELECT_PLAYER, ActionType.SELECT_NONE):
                return False
            if action.action_type == ActionType.SELECT_PLAYER:
                self.selected_assists.append(action.player)
            if action.action_type == ActionType.SELECT_NONE or len(self.selected_assists) == len(self.assist_candidates):
                self.assists_chosen = True
            else:
                return False

        # Assists
        assists_from = (self.selected_assists if self.assist_candidates else
                        self.game.get_assisting_players(self.fouler, self.defender, foul=True))
        assists_to = self.game.get_assisting_players(self.defender, self.fouler, foul=True)
        modifier = len(assists_from) - len(assists_to) + (3 if self.use_saw else 0)

        self.game.report(Outcome(OutcomeType.FOUL, player=self.fouler, opp_player=self.defender))

        # Armor roll
        check = FoulEjection(self.game, self.fouler) if self.game.is_season3 else None
        Armor(self.game, self.defender, modifiers=modifier, inflictor=self.fouler, foul=True, foul_check=check,
              lone_fouler=self.game.is_season3 and not assists_from and not assists_to and
              self.fouler.has_usable_skill(Skill.LONE_FOULER))

        return True

    def available_actions(self):
        if not self.saw_choice:
            return [ActionChoice(kind, team=self.fouler.team, skill=Skill.CHAINSAW)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        if not self.assists_chosen:
            return [ActionChoice(ActionType.SELECT_PLAYER, team=self.fouler.team,
                                 players=[p for p in self.assist_candidates if p not in self.selected_assists],
                                 skill=Skill.SNEAKY_GIT),
                    ActionChoice(ActionType.SELECT_NONE, team=self.fouler.team, skill=Skill.SNEAKY_GIT)]
        return []


class ResetHalf(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        for team in self.game.state.teams:
            team.state.rerolls = team.rerolls
            team.state.turn = 0
            if self.game.is_season3:
                team.state.drive_rerolls = 0
                team.state.cheering_fans = False
                team.state.leader_reroll = False
        return True

    def available_actions(self):
        return []


class Half(Procedure):

    def __init__(self, game, half):
        super().__init__(game)
        self.half = half
        self.kicked_off = False
        self.prepared = False
        self.next_team = None

    def step(self, action):

        if self.game.is_season3:
            return self._step_season3()

        # If second half
        if not self.prepared and self.half > 1:
            PreKickoff(self.game, self.game.get_kicking_team(self.half))
            PreKickoff(self.game, self.game.get_receiving_team(self.half))
            self.prepared = True
            return False

        # Kickoff
        if not self.kicked_off:
            self.game.state.half = self.half
            self.game.state.round = 0
            self.game.state.kicking_this_drive = self.game.get_kicking_team(self.half)
            self.game.state.receiving_this_drive = self.game.get_receiving_team(self.half)
            self.kicked_off = True
            self.game.set_turn_order_from(self.game.get_receiving_team(self.half))
            Kickoff(self.game)
            Setup(self.game, team=self.game.get_receiving_team(self.half))
            Setup(self.game, team=self.game.get_kicking_team(self.half))
            ResetHalf(self.game)
            ClearBoard(self.game)
            return False

        # Add turn in round
        if self.game.state.round < self.game.config.rounds:
            self.game.state.round += 1
            for team in reversed(self.game.state.turn_order):
                Turn(self.game, team, self.half, self.game.state.round)
            return False

        if self.half == 1:
            self.game.report(Outcome(OutcomeType.END_OF_FIRST_HALF))
        elif self.half == 2:
            self.game.report(Outcome(OutcomeType.END_OF_SECOND_HALF))

        return True

    def available_actions(self):
        return []

    def _step_season3(self):
        if not self.kicked_off:
            self.kicked_off = True
            self.game.state.half = self.half
            self.game.state.round = 0
            self.game.state.kicking_this_drive = self.game.get_kicking_team(self.half)
            self.game.state.receiving_this_drive = self.game.get_receiving_team(self.half)
            self.next_team = self.game.state.receiving_this_drive
            self.game.set_turn_order_from(self.next_team)
            StartDrive(self.game)
            ResetHalf(self.game)
            return False
        for _ in range(2):
            team = self.next_team
            self.next_team = self.game.get_opp_team(team)
            if team.state.turn < self.game.config.rounds:
                number = team.state.turn + 1
                self.game.state.round = number
                Turn(self.game, team, self.half, number)
                return False
        if self.game.state.drive_active:
            EndDrive(self.game)
            return False
        self.game.report(Outcome(OutcomeType.END_OF_FIRST_HALF if self.half == 1 else
                                 OutcomeType.END_OF_SECOND_HALF))
        return True


class Injury(Procedure):

    def __init__(self, game, player, inflictor=None, foul=False, mighty_blow_used=False, dirty_player_used=False, in_crowd=False, blood_lust=False, foul_check=None, damage_skill=None, stunned_is_ko=False, casualty_credit=False, block=False):
        super().__init__(game)
        self.player = player
        self.inflictor = inflictor
        self.injury_rolled = False
        self.foul = foul
        self.mighty_blow_used = mighty_blow_used
        self.dirty_player_used = dirty_player_used
        self.ejected = False
        self.in_crowd = in_crowd
        self.blood_lust = blood_lust
        self.foul_check = foul_check
        self.damage_skill = damage_skill
        self.stunned_is_ko = stunned_is_ko
        self.casualty_credit = casualty_credit
        self.block = block

    def step(self, action):

        # TODO: Necromancer

        # Roll
        roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.INJURY_ROLL)
        self.injury_rolled = True

        # Skill modifiers
        thick_skull = -1 if self.player.has_skill(Skill.THICK_SKULL) else 0
        stunty = 1 if self.player.has_skill(Skill.STUNTY) else 0
        mighty_blow = 0
        dirty_player = 0
        niggling = 0 if self.game.is_season3 else self.player.num_niggling_injuries()
        if self.inflictor is not None:
            dirty_player = 1 if self.inflictor.has_skill(Skill.DIRTY_PLAYER) and not self.dirty_player_used and \
                                self.foul else 0
            mighty_blow = 1 if self.inflictor.has_skill(Skill.MIGHTY_BLOW) and not self.mighty_blow_used and not \
                self.foul else 0
        if self.game.is_season3:
            mighty_blow = int(self.damage_skill is not None and not self.mighty_blow_used and not self.foul)

        # EJECTION
        if self.foul and roll.same() and (self.game.is_season3 or not self.inflictor.has_skill(Skill.SNEAKY_GIT)):
            self.ejected = True
            if self.foul_check is not None:
                self.foul_check.caught = True

        # CASUALTY
        roll.modifiers = (0 if self.game.is_season3 else stunty) + mighty_blow + dirty_player + niggling
        if self.game.is_season3 and stunty and roll.get_result() == 9:
            self.game.report(Outcome(OutcomeType.CASUALTY, player=self.player, opp_player=self.inflictor, rolls=[roll]))
            Casualty(self.game, self.player, inflictor=self.inflictor, badly_hurt=True,
                     blood_lust=self.blood_lust, casualty_credit=self.casualty_credit, block=self.block)
            return True
        if roll.get_result() >= 10:
            roll.modifiers = stunty + mighty_blow + dirty_player
            self.game.report(Outcome(OutcomeType.CASUALTY, player=self.player, opp_player=self.inflictor, rolls=[roll]))
            Casualty(self.game, self.player, inflictor=self.inflictor, decay=self.player.has_skill(Skill.DECAY),
                     blood_lust=self.blood_lust, casualty_credit=self.casualty_credit, block=self.block)
            return True

        # KOD
        roll.modifiers = thick_skull + stunty + mighty_blow + dirty_player + niggling
        if roll.get_result() >= 8:
            KnockOut(self.game, self.player, roll=roll, inflictor=self.inflictor, in_crowd=self.in_crowd)
            return True

        # STUNNED
        roll.modifiers = thick_skull + stunty + mighty_blow + dirty_player + niggling
        if (self.player.has_skill(Skill.BALL_AND_CHAIN) and not (self.game.is_season3 and self.in_crowd)) or self.stunned_is_ko:
            KnockOut(self.game, self.player, roll=roll, inflictor=self.inflictor)
        else:
            self.game.report(Outcome(OutcomeType.STUNNED, player=self.player, opp_player=self.inflictor,
                                     rolls=[roll]))
            if self.in_crowd:
                self.game.pitch_to_reserves(self.player)
            else:
                self.player.place_prone()
                self.player.state.stunned = True

        return True

    def end(self):
        if self.ejected and self.foul_check is None:
            Ejection(self.game, self.inflictor)

    def available_actions(self):
        return []


class Interception(Procedure):

    def __init__(self, game, team, ball, interceptors, passer, inaccurate=False):
        super().__init__(game)
        self.team = team
        self.passer = passer
        self.ball = ball
        self.interceptors = interceptors
        self.inaccurate = inaccurate

    def start(self):
        self.game.add_secondary_clock(self.team)

    def step(self, action):
        if action.action_type == ActionType.SELECT_PLAYER:
            Intercept(self.game, action.player, self.ball, passer=self.passer, inaccurate=self.inaccurate)
        self.game.remove_secondary_clocks()
        return True

    def available_actions(self):
        rolls = []
        for interceptor in self.interceptors:
            modifier = self.game.get_catch_modifiers(interceptor, interception=True, inaccurate=self.inaccurate)
            rolls.append([max(2, min(6, interceptor.get_ag_target() - modifier))])
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.team,
                             players=self.interceptors, rolls=rolls),
                ActionChoice(ActionType.SELECT_NONE, team=self.team)]


class Touchback(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball

    def start(self):
        self.game.add_secondary_clock(self.game.state.receiving_this_drive)
        self.players_on_pitch_standing = self.game.get_players_on_pitch(self.game.state.receiving_this_drive, up=True)
        if self.game.is_season3:
            self.players_on_pitch_standing = [p for p in self.players_on_pitch_standing if not p.has_skill(Skill.NO_BALL)]

    def step(self, action):
        player = None
        if len(self.players_on_pitch_standing) == 0:
            position = action.position if self.game.is_season3 else self.game.rng.choice(self.game.get_team_side(self.game.state.receiving_this_drive))
            self.ball.is_carried = False
        else:
            player = action.player
            position = player.position
            self.ball.is_carried = True
        self.ball.move_to(position)
        self.ball.on_ground = True
        self.game.report(Outcome(OutcomeType.TOUCHBACK_BALL_PLACED, player=player, position=position))
        self.game.remove_secondary_clocks()
        return True

    def available_actions(self):
        # Only allow standing players unless no players.
        if len(self.players_on_pitch_standing) > 0:
            return [ActionChoice(ActionType.SELECT_PLAYER, team=self.game.state.receiving_this_drive,
                                 players=self.players_on_pitch_standing)]
        else:
            if self.game.is_season3:
                return [ActionChoice(ActionType.PLACE_BALL, team=self.game.state.receiving_this_drive,
                                     positions=[p for p in self.game.get_team_side(self.game.state.receiving_this_drive)
                                                if self.game.get_player_at(p) is None])]
            return []


class LandKick(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball
        self.landed = False

    def step(self, action):

        if not self.game.is_team_side(self.ball.position, self.game.get_receiving_team()):
            Touchback(self.game, self.ball)
            self.game.report(Outcome(OutcomeType.TOUCHBACK, team=self.game.get_receiving_team()))
            return True

        # Gentle gust
        if self.game.state.gentle_gust:
            if self.game.is_season3:
                KickScatterThree(self.game, self.ball)
            else:
                Scatter(self.game, self.ball, kick=True, gentle_gust=True)
            self.game.state.gentle_gust = False
            return False

        self.ball.on_ground = True
        catcher = self.game.get_catcher(self.ball.position)
        if catcher is None:
            Bounce(self.game, self.ball, kick=True)
            self.game.report(Outcome(OutcomeType.BALL_HIT_GROUND, position=self.ball.position))
            return True

        Catch(self.game, catcher, self.ball, kick=True)
        self.game.report(Outcome(OutcomeType.BALL_HIT_PLAYER, position=self.ball.position, player=catcher))

        return True

    def available_actions(self):
        return []


class Fans(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):

        if self.game.is_season3:
            spectators = 0
            for team in self.game.state.teams:
                roll = DiceRoll([D3(self.game.rng)], roll_type=RollType.FANS_ROLL)
                # Preserve the prepared roster's three fans as Dedicated Fans.
                team.state.fan_factor = max(1, team.fan_factor) + roll.get_sum()
                team.state.fame = 0
                spectators += team.state.fan_factor * 1000
                self.game.report(Outcome(OutcomeType.TEAM_SPECTATORS, n=team.state.fan_factor * 1000,
                                         team=team, rolls=[roll]))
            self.game.state.spectators = spectators
            self.game.report(Outcome(OutcomeType.SPECTATORS, n=spectators))
            return True

        # Fans
        rolls = []
        spectators = []
        for team in self.game.state.teams:
            roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.FANS_ROLL)
            rolls.append(roll)
            fans = (roll.get_sum() + team.fan_factor) * 1000
            spectators.append(fans)
            self.game.report(Outcome(OutcomeType.TEAM_SPECTATORS, n=fans, team=team, rolls=[roll]))
        self.game.state.spectators = int(np.sum(spectators))
        self.game.report(Outcome(OutcomeType.SPECTATORS, n=self.game.state.spectators))

        # FAME
        max_fans = int(np.max(spectators))
        min_fans = int(np.min(spectators))
        for i in range(len(self.game.state.teams)):
            team = self.game.state.teams[i]
            team_fans = spectators[i]
            fame = 0
            if team_fans == max_fans:
                if team_fans >= min_fans * 2:
                    fame = 2
                elif team_fans > min_fans:
                    fame = 1
            self.game.report(Outcome(OutcomeType.FAME, n=fame, team=team))
            team.state.fame = fame

        return True

    def available_actions(self):
        return []


class Kickoff(Procedure):

    def __init__(self, game):
        super().__init__(game)
        self.kickers = []

    def start(self):
        if self.game.is_season3:
            players = self.game.get_players_on_pitch(self.game.get_kicking_team())
            centre = [p for p in players if self.game.get_tile(p.position) not in (
                Tile.HOME_WING_LEFT, Tile.HOME_WING_RIGHT, Tile.AWAY_WING_LEFT, Tile.AWAY_WING_RIGHT)]
            self.kickers = [p for p in centre if not self.game.is_scrimmage(p.position)] or centre

    def step(self, action):
        self.game.state.gentle_gust = False
        kicker = None
        if self.game.is_season3:
            for team in self.game.state.teams:
                for player in self.game.get_players_on_pitch(team):
                    player.state.played_drive = True
                if team.state.leader_half_checked != self.game.state.half:
                    team.state.leader_half_checked = self.game.state.half
                    team.state.leader_reroll = any(p.has_skill(Skill.LEADER)
                                                   for p in self.game.get_players_on_pitch(team))
            if self.kickers:
                kicker = action.player if action is not None else min(self.kickers, key=lambda p: p.nr)
                self.game.report(Outcome(OutcomeType.KICKER_NOMINATED, player=kicker))
        # self.game.reset_kickoff()
        ball = Ball(None, on_ground=False)
        LandKick(self.game, ball)
        KickoffTable(self.game, ball)
        if self.game.is_season3:
            OnTheBallReaction(self.game, self.game.get_receiving_team(), ball=ball)
        Scatter(self.game, ball, kick=True, kicker=kicker)
        PlaceBall(self.game, ball)
        return True

    def available_actions(self):
        # Keep the fixed Human preview's immaterial nomination automatic.
        if any(p.has_usable_skill(Skill.KICK) for p in self.kickers):
            return [ActionChoice(ActionType.SELECT_PLAYER, team=self.game.get_kicking_team(), players=self.kickers)]
        return []


class GetTheRef(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        for team in self.game.state.teams:
            team.state.bribes += 1
            self.game.report(Outcome(OutcomeType.EXTRA_BRIBE, team=team))
        return True

    def available_actions(self):
        return []


class Riot(Procedure):

    def __init__(self, game):
        super().__init__(game)
        self.effect = 0

    def step(self, action):
        roll = None
        receiving_turn = self.game.get_receiving_team().state.turn
        if receiving_turn == 7:
            self.effect = -1
        elif receiving_turn == 0:
            self.effect = 1
        else:
            roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.RIOT_ROLL)
            if roll.get_sum() <= 3:
                self.effect = 1
            else:
                self.effect = -1

        self.game.add_or_skip_turn(self.effect)
        if self.effect == -1:
            self.game.report(Outcome(OutcomeType.TURN_ADDED, rolls=[] if roll is None else [roll]))
        if self.effect == 1:
            self.game.report(Outcome(OutcomeType.TURN_SKIPPED, rolls=[] if roll is None else [roll]))

        return True

    def available_actions(self):
        return []


class HighKick(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball
        self.receiving_team = self.game.get_receiving_team()

    def start(self):
        self.game.add_secondary_clock(self.receiving_team)
        self.available_players = []
        for player in self.game.get_players_on_pitch(self.receiving_team, up=True):
            if self.game.num_tackle_zones_in(player) == 0:
                self.available_players.append(player)

    def step(self, action):
        self.game.remove_secondary_clocks()
        if not self.game.is_team_side(self.ball.position, self.receiving_team) or \
            self.game.get_player_at(self.ball.position) is not None:
            return True
        if len(self.available_players) == 0 or action.action_type == ActionType.SELECT_NONE:
            return True
        if action.action_type == ActionType.SELECT_PLAYER:
            self.game.move(action.player, self.ball.position)
            self.game.report(Outcome(OutcomeType.PLAYER_PLACED_HIGH_KICK, position=self.game.get_ball_position(), team=self.receiving_team))
        elif action.action_type == ActionType.END_SETUP:
            self.game.report(Outcome(OutcomeType.SETUP_DONE, team=self.receiving_team))
        return True

    def available_actions(self):
        if len(self.available_players) == 0:
            return []
        if self.game.is_team_side(self.ball.position, self.receiving_team) and \
                self.game.get_player_at(self.ball.position) is None:
            return [ActionChoice(ActionType.SELECT_PLAYER, team=self.receiving_team, players=self.available_players),
                    ActionChoice(ActionType.SELECT_NONE, team=self.receiving_team)]
        return []


class CheeringFans(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        rolls = []
        cheers = []
        for team in self.game.state.teams:
            roll = DiceRoll([D6(self.game.rng) if self.game.is_season3 else D3(self.game.rng)], roll_type=RollType.CHEERING_FANS_ROLL)
            rolls.append(roll)
            roll.modifiers = (0 if self.game.is_season3 else team.state.fame) + team.cheerleaders
            cheers.append(roll.get_result())
            self.game.report(Outcome(OutcomeType.CHEERING_FANS_ROLL, team=team, rolls=[roll]))

        max_cheers = np.max(cheers)
        for i in range(len(self.game.state.teams)):
            team = self.game.state.teams[i]
            if max_cheers == cheers[i]:
                if self.game.is_season3:
                    team.state.cheering_fans = True
                    self.game.report(Outcome(OutcomeType.CHEERING_ASSIST, team=team))
                else:
                    team.state.rerolls += 1
                    self.game.report(Outcome(OutcomeType.EXTRA_REROLL, team=team))

        return True

    def available_actions(self):
        return []


class BrilliantCoaching(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):

        rolls = []
        brilliant_coaches = []
        for team in self.game.state.teams:
            roll = DiceRoll([D6(self.game.rng) if self.game.is_season3 else D3(self.game.rng)], roll_type=RollType.BRILLIANT_COACHING_ROLL)
            rolls.append(roll)
            roll.modifiers = (0 if self.game.is_season3 else team.state.fame) + team.ass_coaches
            brilliant_coaches.append(roll.get_result())
            self.game.report(Outcome(OutcomeType.BRILLIANT_COACHING_ROLL, team=team, rolls=[roll]))

        max_cheers = np.max(brilliant_coaches)
        for i in range(len(self.game.state.teams)):
            team = self.game.state.teams[i]
            if max_cheers == brilliant_coaches[i]:
                team.state.rerolls += 1
                if self.game.is_season3:
                    team.state.drive_rerolls += 1
                self.game.report(Outcome(OutcomeType.EXTRA_REROLL, team=team))

        return True

    def available_actions(self):
        return []


class ThrowARock(Procedure):

    def __init__(self, game):
        super().__init__(game)
        self.rolled = False

    def step(self, action):

        rolls = []
        for team in self.game.state.teams:
            roll = DiceRoll([D3(self.game.rng)], roll_type=RollType.THROW_A_ROCK_ROLL)
            roll.modifiers = team.state.fame
            rolls.append(roll.get_result())
            self.game.report(Outcome(OutcomeType.THROW_A_ROCK_ROLL, team=team, rolls=[roll]))

        for i in range(len(self.game.state.teams)):
            team = self.game.state.teams[i]
            if rolls[i] == np.min(rolls):
                players = self.game.get_players_on_pitch(team)
                if len(players) > 0:
                    player = self.game.rng.choice(players)
                    KnockDown(self.game, player, armor_roll=False)
                    self.game.report(Outcome(OutcomeType.HIT_BY_ROCK, player=player))

        return True

    def available_actions(self):
        return []


class PitchInvasionRoll(Procedure):

    def __init__(self, game, team, player):
        super().__init__(game)
        self.team = team
        self.player = player

    def step(self, action):
        roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.PITCH_INVASION_ROLL)
        roll.modifiers = self.game.get_opp_team(self.team).state.fame
        if roll.get_result() >= 6 and roll.get_sum() != 1:
            if self.player.has_skill(Skill.BALL_AND_CHAIN):
                self.game.report(Outcome(OutcomeType.KNOCKED_OUT, rolls=[roll], player=self.player, team=self.team))
                KnockOut(self.game, self.player, roll=roll)
            else:
                self.player.place_prone()
                self.player.state.stunned = True
                self.game.report(Outcome(OutcomeType.STUNNED, rolls=[roll], player=self.player, team=self.team))
        else:
            self.game.report(Outcome(OutcomeType.PLAYER_READY, rolls=[roll], player=self.player, team=self.team))

        return True

    def available_actions(self):
        return []


class KickoffTable(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball
        self.rolled = False

    def step(self, action):

        roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.KICKOFF_ROLL)
        result = roll.get_result()

        if self.game.is_season3:
            events = {
                2: (GetTheRef, OutcomeType.KICKOFF_GET_THE_REF),
                3: (TimeOut, OutcomeType.KICKOFF_TIME_OUT),
                4: (SolidDefence, OutcomeType.KICKOFF_SOLID_DEFENCE),
                5: (lambda g: HighKick(g, self.ball), OutcomeType.KICKOFF_HIGH_KICK),
                6: (CheeringFans, OutcomeType.KICKOFF_CHEERING_FANS),
                7: (BrilliantCoaching, OutcomeType.KICKOFF_BRILLIANT_COACHING),
                8: (lambda g: WeatherTable(g, kickoff=True), OutcomeType.KICKOFF_CHANGING_WHEATHER),
                9: (lambda g: Turn(g, g.get_receiving_team(), None, None, quick_snap=True), OutcomeType.KICKOFF_QUICK_SNAP),
                10: (lambda g: Turn(g, g.get_kicking_team(), None, None, blitz=True), OutcomeType.KICKOFF_CHARGE),
                11: (DodgySnack, OutcomeType.KICKOFF_DODGY_SNACK),
                12: (Season3PitchInvasion, OutcomeType.KICKOFF_PITCH_INVASION),
            }
            factory, outcome = events[result]
            factory(self.game)
            self.game.report(Outcome(outcome, rolls=[roll]))
            return True

        if result == 2:  # Get the ref!
            GetTheRef(self.game)
            self.game.report(Outcome(OutcomeType.KICKOFF_GET_THE_REF, rolls=[roll]))
        elif result == 3:  # Riot!
            Riot(self.game)
            self.game.report(Outcome(OutcomeType.KICKOFF_RIOT, rolls=[roll]))
        elif result == 4:  # Perfect defense
            Setup(self.game, team=self.game.get_kicking_team(), reorganize=True)
            self.game.report(Outcome(OutcomeType.KICKOFF_PERFECT_DEFENSE, team=self.game.get_kicking_team(),
                                     rolls=[roll]))
        elif result == 5:  # High Kick
            HighKick(self.game, self.ball)
            self.game.report(Outcome(OutcomeType.KICKOFF_HIGH_KICK, rolls=[roll]))
        elif result == 6:  # Cheering fans
            CheeringFans(self.game)
            self.game.report(Outcome(OutcomeType.KICKOFF_CHEERING_FANS, rolls=[roll]))
        elif result == 7:  # Changing Weather
            WeatherTable(self.game, kickoff=True)
            self.game.report(Outcome(OutcomeType.KICKOFF_CHANGING_WHEATHER, rolls=[roll]))
        elif result == 8:  # Brilliant Coaching
            BrilliantCoaching(self.game)
            self.game.report(Outcome(OutcomeType.KICKOFF_BRILLIANT_COACHING, rolls=[roll]))
        elif result == 9:  # Quick Snap
            Turn(self.game, self.game.get_receiving_team(), None, None, quick_snap=True)
            self.game.report(Outcome(OutcomeType.KICKOFF_QUICK_SNAP, rolls=[roll]))
        elif result == 10:  # Blitz
            Turn(self.game, self.game.get_kicking_team(), None, None, blitz=True)
            self.game.report(Outcome(OutcomeType.KICKOFF_BLITZ, rolls=[roll]))
        elif result == 11:  # Throw a Rock
            ThrowARock(self.game)
            self.game.report(Outcome(OutcomeType.KICKOFF_THROW_A_ROCK, rolls=[roll]))
        elif result == 12:  # Pitch Invasion
            for team in reversed(self.game.state.teams):
                for player in sorted(self.game.get_players_on_pitch(team), key=lambda p: p.nr, reverse=True):
                    PitchInvasionRoll(self.game, team, player)
            self.game.report(Outcome(OutcomeType.KICKOFF_PITCH_INVASION, rolls=[roll]))

        return True

    def available_actions(self):
        return []


class SteadyFooting(Procedure):
    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.roll = None
        self.reroll = None
        self.success = False

    def step(self, action):
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], target=6)
            self.success = self.roll.is_d6_success()
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                     skill=Skill.STEADY_FOOTING, rolls=[self.roll]))
            if not self.success:
                self.reroll = Reroll(self.game, self.player, self)
                return False
        elif self.reroll is not None and self.reroll.use_reroll:
            self.roll = self.reroll = None
            return False
        return True


class KnockDown(Procedure):

    def __init__(self, game, player, armor_roll=True, injury_roll=True, modifiers=0, inflictor=None,
                 in_crowd=False, modifiers_opp=0, turnover=False, blood_lust=False, block=False,
                 damage_skill=None, casualty_credit=False):
        super().__init__(game)
        self.player = player
        self.armor_roll = armor_roll
        self.injury_roll = injury_roll
        if game.is_season3 and player.has_skill(Skill.BALL_AND_CHAIN):
            self.armor_roll = False
            self.injury_roll = True
        self.modifiers = modifiers
        self.modifiers_opp = modifiers_opp
        self.inflictor = inflictor
        self.in_crowd = in_crowd
        self.turnover = turnover or (game.is_season3 and game.has_ball(player) and
                                     player.team == game.state.current_team)
        self.blood_lust = blood_lust
        self.damage_skill = damage_skill
        self.block = block
        self.casualty_credit = casualty_credit or block or damage_skill in (Skill.ARM_BAR, Skill.LETHAL_FLIGHT)
        if block and inflictor is not None and inflictor.has_usable_skill(Skill.MIGHTY_BLOW):
            self.damage_skill = Skill.MIGHTY_BLOW
        self.claws = block and inflictor is not None and inflictor.has_skill(Skill.CLAWS)
        if game.is_season3 and armor_roll and player.has_usable_skill(Skill.CHAINSAW):
            self.modifiers += 3
        self.steady_footing = (game.is_season3 and armor_roll and not in_crowd and
                              player.has_usable_skill(Skill.STEADY_FOOTING))
        self.steady_checked = False
        self.steady_test = None
        self.safe_hands = (game.is_season3 and player.has_usable_skill(Skill.SAFE_PAIR_OF_HANDS)
                           and not player.has_skill(Skill.MY_BALL) and game.has_ball(player))
        self.safe_hands_checked = False
        self.saboteur = game.is_season3 and block and player.has_usable_skill(Skill.SABOTEUR)
        self.saboteur_checked = False
        self.saboteur_roll = None

    def step(self, action):
        if self.steady_footing and not self.steady_checked:
            if self.steady_test is None:
                self.steady_test = SteadyFooting(self.game, self.player)
                return False
            self.steady_checked = True
            if self.steady_test.success:
                self.player.state.up = True
                escape = self.game.get_proc(Season3Escape)
                if self.player == self.game.get_active_player() and not (
                        escape is not None and escape.player == self.player):
                    ball = self.game.get_ball_at(self.player.position)
                    if ball is not None and not ball.is_carried:
                        Pickup(self.game, ball, self.player)
                    elif self.game.has_ball(self.player) and self.game.is_touchdown(self.player):
                        Touchdown(self.game, self.player)
                return True
            return False
        if self.saboteur and not self.saboteur_checked:
            self.saboteur_checked = True
            if action.action_type == ActionType.USE_SKILL:
                self.saboteur_roll = DiceRoll([D6(self.game.rng)], target=4)
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                         skill=Skill.SABOTEUR, rolls=[self.saboteur_roll]))
            return False
        if self.safe_hands and not self.safe_hands_checked:
            self.safe_hands_checked = True
            if action is not None and action.action_type == ActionType.PLACE_BALL:
                ball = self.game.get_ball_at(self.player.position)
                if ball is not None:
                    ball.is_carried = False
                    ball.move_to(action.position)
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                             skill=Skill.SAFE_PAIR_OF_HANDS, position=action.position))

        # Knock down player
        self.player.place_prone()
        if self.player == self.game.get_active_player():
            self.player.state.used = True

        self.game.report(Outcome(OutcomeType.KNOCKED_DOWN, player=self.player, opp_player=self.inflictor))

        # Turnover
        if self.turnover:
            Turnover(self.game)

        # Check fumble - does not handle throw-in
        ball = self.game.get_ball_at(self.player.position)
        if ball is not None:
            if not self.player.position.out_of_bounds:
                Bounce(self.game, ball)
            self.game.report(Outcome(OutcomeType.FUMBLE, player=self.player, opp_player=self.inflictor))

        # If armor roll should be made. Injury is also nested in armor.
        if self.saboteur_roll is not None and self.saboteur_roll.is_d6_success():
            KnockOut(self.game, self.player, self.saboteur_roll, inflictor=self.inflictor)
            if self.inflictor is not None and self.inflictor.position is not None:
                KnockDown(self.game, self.inflictor, turnover=self.game.has_ball(self.inflictor))
        elif self.injury_roll and not self.armor_roll:
            Injury(self.game, self.player, inflictor=self.inflictor if not self.in_crowd else None,
                   in_crowd=self.in_crowd, blood_lust=self.blood_lust,
                   casualty_credit=self.casualty_credit, block=self.block)
        elif self.armor_roll:
            Armor(self.game, self.player, modifiers=self.modifiers, inflictor=self.inflictor,
                  damage_skill=self.damage_skill, claws=self.claws,
                  casualty_credit=self.casualty_credit, block=self.block)

        return True

    def available_actions(self):
        if self.steady_footing and not self.steady_checked:
            return []
        if self.saboteur and not self.saboteur_checked:
            return [ActionChoice(kind, team=self.player.team, skill=Skill.SABOTEUR)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        if self.safe_hands and not self.safe_hands_checked:
            squares = self.game.get_adjacent_squares(self.player.position, occupied=False)
            if squares:
                return [ActionChoice(ActionType.PLACE_BALL, team=self.player.team, positions=squares),
                        ActionChoice(ActionType.DONT_USE_SKILL, team=self.player.team,
                                     skill=Skill.SAFE_PAIR_OF_HANDS)]
        return []


class KnockOut(Procedure):

    def __init__(self, game, player, roll, inflictor=None, in_crowd=False):
        super().__init__(game)
        self.player = player
        self.inflictor = inflictor
        self.roll = roll
        self.in_crowd = in_crowd

    def step(self, action):
        if self.player.team.state.apothecaries > 0:
            Apothecary(self.game, self.player, roll=self.roll, outcome=OutcomeType.KNOCKED_OUT,
                       inflictor=self.inflictor, in_crowd=self.in_crowd)
            return True
        else:
            # Knock out player
            self.game.pitch_to_kod(self.player)
            self.game.report(Outcome(OutcomeType.KNOCKED_OUT, rolls=[self.roll], player=self.player,
                                     opp_player=self.inflictor))

        return True


class Jump(Procedure):
    """Season 3 jump: Rushes first; a natural 1 falls at take-off."""

    def __init__(self, game, player, position, gfis, drop_ball=False):
        super().__init__(game)
        self.player = player
        self.position = position
        self.origin = player.position
        self.drop_ball = drop_ball
        self.roll = None
        self.reroll = None
        self.gfis = gfis

    def step(self, action):
        Season3Escape(self.game, self.player, self.position, jump=True, drop_ball=self.drop_ball, gfis=self.gfis)
        return True


class Season3Escape(Procedure):
    """Dodge/jump tests: modifiers, re-rolls, then one Diving Tackle decision."""

    def __init__(self, game, player, position, jump=False, drop_ball=False, gfis=0):
        super().__init__(game)
        self.player = player
        self.position = position
        self.origin = player.position
        self.jump = jump
        self.gfis = gfis
        self.moved = False
        self.modifiers = (game.get_jump_modifiers(player, self.origin, position) if jump
                          else game.get_dodge_modifiers(player, position))
        self.drop_ball = drop_ball
        self.roll = None
        self.reroll = None
        self.phase = 'tentacles'
        self.holders = [p for p in game.get_adjacent_opponents(player)
                        if p.has_usable_skill(Skill.TENTACLES)]
        self.divers = [p for p in game.get_adjacent_opponents(player)
                       if p.has_usable_skill(Skill.DIVING_TACKLE)]
        self.diver = None
        self.break_bonus = 0
        self.break_checked = False
        self.arm_bars = [p for p in game.get_adjacent_opponents(player) if p.has_usable_skill(Skill.ARM_BAR)]
        self.shadowers = [p for p in game.get_adjacent_opponents(player) if p.has_usable_skill(Skill.SHADOWING)]

    def step(self, action):
        if self.phase == 'tentacles':
            self.phase = 'rush'
            if self.holders and action.action_type == ActionType.USE_SKILL:
                holder = action.player or self.holders[0]
                roll = DiceRoll([D6(self.game.rng)], target=6,
                                modifiers=holder.get_st() - self.player.get_st())
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=holder,
                                         skill=Skill.TENTACLES, rolls=[roll]))
                if roll.is_d6_success():
                    EndPlayerTurn(self.game, self.player)
                    return True
            return False

        if self.phase == 'rush':
            if self.gfis:
                self.gfis -= 1
                GFI(self.game, self.player, self.origin if self.jump else self.position, drop_ball=self.drop_ball)
                return False
            self.phase = 'roll'

        if self.phase == 'break_tackle':
            self.break_checked = True
            if action.action_type == ActionType.USE_SKILL:
                self.player.use_skill(Skill.BREAK_TACKLE)
                self.break_bonus = 1 if self.player.get_st() <= 3 else 2 if self.player.get_st() == 4 else 3
                self.roll.modifiers += self.break_bonus
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.BREAK_TACKLE))
            self.phase = 'rolled'

        if self.phase == 'diving_tackle':
            if action.action_type == ActionType.USE_SKILL:
                self.diver = action.player or self.divers[0]
                if not (self.jump and self.player.has_usable_skill(Skill.POGO)):
                    self.roll.modifiers -= 2
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.diver, skill=Skill.DIVING_TACKLE))
            return self.resolve()

        if self.reroll is not None:
            if self.reroll.use_reroll:
                self.roll = None
                self.reroll = None
                self.break_checked = bool(self.break_bonus)
            else:
                return self.resolve()

        if self.roll is None:
            if not self.jump and not self.moved:
                if self.player.position != self.position:
                    self.game.move(self.player, self.position, drop_ball=self.drop_ball)
                self.moved = True
            self.roll = DiceRoll([D6(self.game.rng)],
                                roll_type=RollType.JUMP_ROLL if self.jump else RollType.AGILITY_ROLL)
            self.roll.target = self.player.get_ag_target()
            self.roll.modifiers = self.modifiers + self.break_bonus
        if not self.roll.is_d6_success():
            if not self.jump and not self.break_checked and self.player.can_use_skill(Skill.BREAK_TACKLE):
                bonus = 1 if self.player.get_st() <= 3 else 2 if self.player.get_st() == 4 else 3
                if self.roll.get_sum() != 1 and self.roll.get_result() + bonus >= self.roll.target:
                    self.phase = 'break_tackle'
                    return False
            self.game.report(Outcome(OutcomeType.FAILED_JUMP if self.jump else OutcomeType.FAILED_DODGE,
                                     player=self.player, rolls=[self.roll]))
            self.reroll = Reroll(self.game, self.player, self)
            return False
        if self.divers:
            self.phase = 'diving_tackle'
            return False
        return self.resolve()

    def resolve(self):
        success = self.roll.is_d6_success()
        shadowers = self.shadowers if success and not self.jump else []
        if self.player.position != self.position and (success or not self.jump or self.roll.get_sum() != 1):
            self.game.move(self.player, self.position, drop_ball=self.drop_ball)
        if self.diver is not None:
            self.game.move(self.diver, self.origin)
        if success:
            self.game.report(Outcome(OutcomeType.SUCCESSFUL_JUMP if self.jump else OutcomeType.SUCCESSFUL_DODGE,
                                     player=self.player, position=self.position, rolls=[self.roll]))
            ball = self.game.get_ball_at(self.position)
            if ball is not None and not ball.is_carried and ball.on_ground:
                Pickup(self.game, ball, self.player,
                       secure=self.game.state.player_action_type == PlayerActionType.SECURE_BALL)
            elif self.game.has_ball(self.player) and self.game.is_touchdown(self.player):
                Touchdown(self.game, self.player)
                shadowers = []
        else:
            KnockDown(self.game, self.player, turnover=True,
                      inflictor=self.arm_bars[0] if self.arm_bars else None,
                      damage_skill=Skill.ARM_BAR if self.arm_bars else None)
        if shadowers:
            Shadowing(self.game, self.player, self.origin, shadowers)
        if self.diver is not None:
            KnockDown(self.game, self.diver, armor_roll=False, injury_roll=False)
        return True

    def available_actions(self):
        players, skill = [], None
        if self.phase == 'tentacles':
            players, skill = self.holders, Skill.TENTACLES
        elif self.phase == 'diving_tackle':
            players, skill = self.divers, Skill.DIVING_TACKLE
        elif self.phase == 'break_tackle':
            players, skill = [self.player], Skill.BREAK_TACKLE
        if players:
            return [ActionChoice(ActionType.USE_SKILL, team=players[0].team, players=players, skill=skill),
                    ActionChoice(ActionType.DONT_USE_SKILL, team=players[0].team, skill=skill)]
        return []


class Leap(Procedure):

    def __init__(self, game, player, position, gfis):
        super().__init__(game)
        self.player = player
        self.position = position
        self.roll = None
        self.reroll = None
        for i in range(gfis):
            GFI(game, player, position)

    def start(self):
        assert Skill.LEAP not in self.player.state.used_skills
        self.player.state.used_skills.add(Skill.LEAP)

    def step(self, action):

        if self.roll is None:

            # Agility roll
            self.roll = DiceRoll([D6(self.game.rng)])
            self.roll.target = self.player.get_ag_target()
            self.roll.modifiers = self.game.get_leap_modifiers(self.player)

            if self.roll.is_d6_success():
                self.game.move(self.player, self.position)
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_LEAP, player=self.player, rolls=[self.roll]))
                # Check if player moved onto the ball
                ball = self.game.get_ball_at(self.player.position)
                if ball is not None and not ball.is_carried:
                    # Attempt to pick up the ball - unless no hands
                    if self.player.has_skill(Skill.NO_HANDS):
                        Bounce(self.game, ball)
                    else:
                        Pickup(self.game, ball, self.player)
                elif self.game.has_ball(self.player) and self.game.is_touchdown(self.player):
                    # Touchdown if player had the ball with him/her
                    Touchdown(self.game, self.player)
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_LEAP, player=self.player, rolls=[self.roll]))
                self.reroll = Reroll(self.game, self.player, self)
                return False

        if self.reroll is not None:
            if self.reroll.use_reroll:
                self.roll = None
                self.reroll = None
                return False
            else:
                self.game.report(Outcome(OutcomeType.FAILED_LEAP))
                self.game.move(self.player, self.position)
                KnockDown(self.game, self.player, turnover=True)
        return True


class Shadowing(Procedure):

    def __init__(self, game, player, position, shadowers):
        super().__init__(game)
        self.player = player
        self.position = position
        self.shadowers = shadowers
        self.shadower = None
        self.team = self.game.get_opp_team(player.team)
        self.roll = None
        self.reroll = None

    def start(self):
        able_players = []
        for player in self.shadowers:
            if player.has_tackle_zone() and not player.state.taken_root and (
                    not self.game.is_season3 or (player.state.shadowing_uses < player.get_ma()
                                                and self.game.get_player_at(self.position) is None)):
                able_players.append(player)
        self.shadowers = able_players
        self.shadower = self.shadowers[0] if self.shadowers else None
        self.game.add_secondary_clock(self.team)

    def step(self, action):
        if not self.shadowers:
            return True

        if self.roll is None and action.action_type == ActionType.USE_SKILL:
            if self.game.is_season3:
                self.shadower = action.player or self.shadower
                self.shadower.state.shadowing_uses += 1
                self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.SHADOWING_ROLL, target=4)
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.shadower,
                                         skill=Skill.SHADOWING, rolls=[self.roll]))
                if self.roll.is_d6_success():
                    self.game.move(self.shadower, self.position)
                return True
            self.roll = DiceRoll(dice=[D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.SHADOWING_ROLL, highest_succeed=False)
            self.roll.target = 7
            self.roll.modifiers = self.player.get_ma() - self.shadower.get_ma()
            self.roll.target_higher = False
            self.roll.target_lower = True
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.shadower, skill=Skill.SHADOWING, rolls=[self.roll]))
            if self.roll.is_d6_success():
                self.game.move(self.shadower, self.position)
                return True
            else:
                self.reroll = Reroll(self.game, self.shadower, context=self)
                return False

        if self.reroll is not None:
            if self.reroll.use_reroll:
                self.roll = None
                self.reroll = None
                return False
            return True

        # Dont use shadow
        if self.game.is_season3:
            return True
        self.shadowers.remove(self.shadower)
        self.game.remove_secondary_clocks()
        if self.shadowers:
            self.shadower = self.shadowers[0]
            self.game.add_secondary_clock(self.team)
            return False

        return True

    def end(self):
        self.game.remove_secondary_clocks()

    def available_actions(self):
        if self.shadower is None or self.reroll is not None:
            return []
        return [
            ActionChoice(ActionType.USE_SKILL, team=self.team, players=self.shadowers if self.game.is_season3 else [self.shadower], skill=Skill.SHADOWING),
            ActionChoice(ActionType.DONT_USE_SKILL, team=self.team, players=[self.shadower], skill=Skill.SHADOWING)
        ]


class Tentacles(Procedure):

    def __init__(self, game, player, position, tentacler, move_proc):
        super().__init__(game)
        self.player = player
        self.position = position
        self.tentacler = tentacler
        self.move_proc = move_proc
        self.roll = None
        self.reroll = None

    def step(self, action):

        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)])
            self.roll.target = 5
            self.roll.modifiers = self.player.get_st() - self.tentacler.get_st()
            if self.roll.is_d6_success():
                return True
            else:
                self.reroll = Reroll(self.game, self.player, self)
                return False

        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False

        self.move_proc.tentacles_used = True
        return True


class Move(Procedure):

    def __init__(self, game, player, position, gfi, dodge, drop_ball=False):
        super().__init__(game)
        self.player = player
        self.position = position
        self.dodge = dodge
        self.dodge_proc = None
        self.gfi = gfi
        self.drop_ball = drop_ball
        self.tentaclers = [] if game.is_season3 else [tentacler for tentacler in self.game.get_adjacent_opponents(self.player, skill=Skill.TENTACLES, standing=True) if tentacler.has_tackle_zone()]
        self.tentacles_used = False

    def step(self, action):

        if self.tentacles_used:
            return True

        if self.tentaclers:
            next_tentacler = self.tentaclers[0]
            Tentacles(self.game, self.player, self.position, next_tentacler, self)
            self.tentaclers.remove(next_tentacler)
            return False

        if self.game.is_season3 and self.dodge:
            Season3Escape(self.game, self.player, self.position, drop_ball=self.drop_ball, gfis=int(self.gfi))
            return True

        if self.dodge:
            self.dodge_proc = Dodge(self.game, self.player, self.position)

        if self.gfi:
            GFI(self.game, self.player, self.position, drop_ball=self.drop_ball)

        if self.dodge or self.gfi:
            self.dodge = False
            self.gfi = False
            return False

        # If this is reached then Dodge and GFI was passed

        # Shadowing
        shadowers = [] if self.game.is_season3 else self.game.get_adjacent_opponents(self.player, down=False, skill=Skill.SHADOWING)
        position = self.player.position

        self.game.move(self.player, self.position, drop_ball=self.drop_ball)
        if self.dodge_proc is not None and self.dodge_proc.diving_tackler:
            self.game.move(self.dodge_proc.diving_tackler, self.dodge_proc.from_position)
            KnockDown(self.game, self.dodge_proc.diving_tackler, armor_roll=False, injury_roll=False, turnover=False)

        # Check if player moved onto the ball
        ball = self.game.get_ball_at(self.player.position)
        if ball is not None and not ball.is_carried and ball.on_ground:

            # Attempt to pick up the ball - unless no hands
            if self.player.has_skill(Skill.NO_HANDS):
                Bounce(self.game, ball)
            else:
                Pickup(self.game, ball, self.player,
                       secure=self.game.state.player_action_type == PlayerActionType.SECURE_BALL)

        elif self.game.has_ball(self.player) and self.game.is_touchdown(self.player):

            # Touchdown if player had the ball with him/her
            Touchdown(self.game, self.player)
            shadowers = None

        # Shadowing
        if shadowers:
            Shadowing(self.game, self.player, position, shadowers)

        return True


class GFI(Procedure):

    def __init__(self, game, player, position, drop_ball=False, defer_fall=False):
        super().__init__(game)
        self.player = player
        self.position = position
        self.drop_ball = drop_ball
        self.defer_fall = defer_fall
        self.failed = False
        self.reroll = None
        self.roll = None

    def step(self, action):

        # If player hasn't rolled
        if self.roll is None:

            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.GFI_ROLL)
            self.roll.target = 2
            self.roll.modifiers = (-1 if self.game.is_season3 else 1) if self.game.state.weather == WeatherType.BLIZZARD else 0
            if self.game.is_season3:
                self.roll.modifiers = 2 - self.game.get_rush_target(self.player)

            if self.roll.is_d6_success():

                # Success
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_GFI, player=self.player, position=self.position, rolls=[self.roll]))
                return True

            else:

                # Fail
                self.game.report(Outcome(OutcomeType.FAILED_GFI, player=self.player, position=self.position, rolls=[self.roll]))

                # Check re-roll
                self.reroll = Reroll(self.game, self.player, context=self)
                return False

        assert self.reroll is not None

        # If reroll used
        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False

        if self.defer_fall:
            self.failed = True
            return True

        # Shadowing
        shadowers = [] if self.game.is_season3 else self.game.get_adjacent_opponents(self.player, down=False, skill=Skill.SHADOWING)
        shadow_position = self.player.position

        # Player trips
        if not self.player.position == self.position:
            self.game.move(self.player, self.position, drop_ball=self.drop_ball)

        KnockDown(self.game, self.player, turnover=True)

        if shadowers:
            Shadowing(self.game, self.player, shadow_position, shadowers)

        return True


class Dodge(Procedure):

    def __init__(self, game, player, position):
        super().__init__(game)
        self.player = player
        self.position = position
        self.reroll = None
        self.roll = None
        self.waiting_break_tackle = False
        self.break_tackle_target = None
        self.diving_tacklers = []
        self.diving_tackler = None
        self.from_position = self.game.state.pitch.squares[self.player.position.y][self.player.position.x]
        self.diving_tacklers = self.game.get_adjacent_opponents(self.player, down=False, skill=Skill.DIVING_TACKLE)
        if self.diving_tacklers:
            self.game.add_secondary_clock(self.diving_tacklers[0].team)

    def step(self, action):

        # Diving tackle
        if self.diving_tacklers:
            if action.action_type == ActionType.USE_SKILL:
                self.diving_tackler = self.diving_tacklers[0]
                self.diving_tacklers.clear()
            else:
                self.diving_tacklers.pop(0)
            # Time management
            if self.diving_tacklers:
                self.game.add_secondary_clock(self.diving_tacklers[0].team)
            else:
                self.game.remove_secondary_clocks()
            return False

        # Break tackle
        if self.waiting_break_tackle:
            if action.action_type == ActionType.DONT_USE_SKILL:
                # Check for re-roll
                self.reroll = Reroll(self.game, self.player, context=self)
                self.waiting_break_tackle = False
                return False
            elif action.action_type == ActionType.USE_SKILL:
                # Success
                self.player.use_skill(Skill.BREAK_TACKLE)
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.BREAK_TACKLE))
                self.roll.target = self.break_tackle_target
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_DODGE, player=self.player, position=self.position,
                                         rolls=[self.roll]))
                return True

        # If player hasn't rolled
        if self.roll is None:

            # TODO: Allow player to select if shadowing and diving tackle
            # TODO: Put diving tackle, shadowing proc or tentacles on stack
            # TODO: Auto-use other skills

            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.modifiers = self.game.get_dodge_modifiers(self.player, self.position, include_diving_tackle=(self.diving_tackler is not None))

            agility_target = self.player.get_ag_target()
            self.roll.target = agility_target
            if self.player.can_use_skill(Skill.BREAK_TACKLE) and self.player.get_st() > self.player.get_ag():
                self.break_tackle_target = Rules.agility_table[self.player.get_st()]

            if self.roll.is_d6_success():
                # Success
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_DODGE, player=self.player, position=self.position, rolls=[self.roll]))
                return True
            else:
                # Fail
                self.game.report(Outcome(OutcomeType.FAILED_DODGE, player=self.player, position=self.position, rolls=[self.roll]))
                if self.player.can_use_skill(Skill.BREAK_TACKLE) and self.player.get_st() > self.player.get_ag() and self.roll.get_result() >= self.break_tackle_target:
                    self.waiting_break_tackle = True
                    return False

                # Check for re-roll
                self.reroll = Reroll(self.game, self.player, context=self)
                return False

        assert self.reroll is not None

        # If dodge failed and re-roll decision made
        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False

        # Shadowing
        shadowers = self.game.get_adjacent_opponents(self.player, down=False, skill=Skill.SHADOWING)
        shadow_position = self.player.position

        # If dodge failed and no re-roll -> Player trips
        self.game.move(self.player, self.position)
        if self.diving_tackler:
            self.game.move(self.diving_tackler, self.from_position)
            KnockDown(self.game, self.diving_tackler, armor_roll=False, injury_roll=False, turnover=False)
        KnockDown(self.game, self.player, turnover=True)

        if shadowers:
            Shadowing(self.game, self.player, shadow_position, shadowers)

        return True

    def available_actions(self):
        if self.diving_tacklers:
            return [ActionChoice(ActionType.USE_SKILL, skill=Skill.DIVING_TACKLE, team=self.diving_tacklers[0].team, players=[self.diving_tacklers[0]]),
                    ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.DIVING_TACKLE, team=self.diving_tacklers[0].team, players=[self.diving_tacklers[0]])]
        if self.waiting_break_tackle:
            return [ActionChoice(ActionType.USE_SKILL, skill=Skill.BREAK_TACKLE, team=self.player.team, players=[self.player]),
                    ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.BREAK_TACKLE, team=self.player.team, players=[self.player])]
        return []


class TurnoverIfPossessionLost(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball

    def step(self, action):
        player_at = self.game.get_player_at(self.ball.position)
        if (player_at is None or player_at.team != self.game.state.current_team or
                (self.game.is_season3 and not self.ball.is_carried)):
            Turnover(self.game)
        return True


class Animosity(Procedure):
    def __init__(self, game, player, receiver):
        super().__init__(game)
        self.player = player
        self.receiver = receiver
        self.roll = None
        self.reroll = None
        self.failed = False

    def step(self, action):
        if self.receiver is None or self.receiver.team != self.player.team:
            return True
        keyword = self.player.skill_parameter(Skill.ANIMOSITY, 'all').casefold()
        if keyword != 'all' and keyword not in [k.casefold() for k in self.receiver.role.keywords]:
            return True
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], target=2)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                     skill=Skill.ANIMOSITY, rolls=[self.roll]))
            if self.roll.is_d6_success():
                return True
            self.reroll = Reroll(self.game, self.player, self)
            return False
        if self.reroll.use_reroll:
            self.roll = None
            return False
        self.failed = True
        EndPlayerTurn(self.game, self.player)
        return True


class Handoff(Procedure):

    def __init__(self, game, ball, player, pos_to, catcher):
        super().__init__(game)
        self.ball = ball
        self.player = player
        self.pos_to = pos_to
        self.catcher = catcher
        self.eat_thrall = None
        self.animosity = None
        
    def step(self, action):
        if self.player.state.blood_lust and self.eat_thrall is None:
            self.eat_thrall = EatThrall(self.game, self.player)
            return False 
        
        if self.eat_thrall is not None and self.eat_thrall.failed: 
            return True 

        if self.game.is_season3 and self.player.has_usable_skill(Skill.ANIMOSITY) and self.animosity is None:
            self.animosity = Animosity(self.game, self.player, self.catcher)
            return False
        
        self.ball.move_to(self.pos_to)
        TurnoverIfPossessionLost(self.game, self.ball)
        self.ball.move_to(self.catcher.position)
        Catch(self.game, self.catcher, self.ball, handoff=True)
        self.game.report(Outcome(OutcomeType.HANDOFF, player=self.player, opp_player=self.catcher))
        return True


class Explode(Procedure):

    def __init__(self, game, bomb):
        super().__init__(game)
        self.bomb = bomb
        self.player = self.game.get_player_at(bomb.position)

    def step(self, action):
        if self.game.is_season3:
            self.game.report(Outcome(OutcomeType.BOMB_EXPLODED, position=self.bomb.position, player=self.player))
            victims = [self.player] if self.player is not None else []
            for player in self.game.get_adjacent_players(self.bomb.position):
                roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.BOMB_ROLL, target=4)
                if roll.is_d6_success():
                    victims.append(player)
                    self.game.report(Outcome(OutcomeType.BOMB_HIT, player=player, rolls=[roll]))
            self.game.remove(self.bomb)
            BlockResolution(self.game)
            for player in reversed(victims):
                if player.state.up:
                    KnockDown(self.game, player, inflictor=self.bomb.thrower,
                              turnover=player.team == self.game.state.current_team,
                              casualty_credit=self.bomb.casualty_credit)
                else:
                    Armor(self.game, player, inflictor=self.bomb.thrower,
                          casualty_credit=self.bomb.casualty_credit)
            return True
        self.game.report(Outcome(OutcomeType.BOMB_EXPLODED, position=self.bomb.position, player=self.player))
        if self.player:
            self.game.report(Outcome(OutcomeType.BOMB_HIT, position=self.bomb.position, player=self.player))
            KnockDown(self.game, self.player)
        position = self.bomb.position
        self.game.remove(self.bomb)
        for player in self.game.get_adjacent_players(position):
            die = D6(self.game.rng)
            roll = DiceRoll(die, RollType.BOMB_ROLL, target=4)
            if roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.BOMB_HIT, position=self.bomb.position, player=self.player, rolls=[roll]))
                KnockDown(self.game, player)
        return True


class Land(Procedure):

    def __init__(self, game, player, penalty=0, auto_fail=False, swoop=False):
        super().__init__(game)
        self.player = player
        self.roll = None
        self.reroll = None
        self.penalty = penalty
        self.auto_fail = auto_fail
        self.swoop = swoop

    def start(self):
        self.game.put_down(self.player)

    def step(self, action):
        if self.auto_fail:
            self.game.report(Outcome(OutcomeType.FAILED_LAND, player=self.player))
            KnockDown(self.game, self.player, turnover=self.game.has_ball(self.player))
            return True
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], RollType.LAND_ROLL)
            self.roll.target = self.player.get_ag_target()
            self.roll.modifiers = self.game.get_landing_modifiers(self.player) + self.penalty
            if self.roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_LAND, position=self.player.position, player=self.player, rolls=[self.roll]))
                if self.game.is_touchdown(self.player):
                    Touchdown(self.game, self.player)
                # bounce ball if you land on the ball; this will be different in BB2020
                elif self.game.get_ball_position() == self.player.position and not self.game.has_ball(self.player):
                    Bounce(self.game, self.game.get_ball())
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_LAND, position=self.player.position, player=self.player, rolls=[self.roll]))
                self.reroll = Reroll(self.game, self.player, context=self)
                return False

        # If re-roll used
        if self.reroll.use_reroll:
            self.reroll = None
            self.roll = None
            return False

        # Failed landing
        KnockDown(self.game, self.player, turnover=self.game.has_ball(self.player))
        return True


class PassAttempt(Procedure):

    def __init__(self, game, passer, piece, position, pass_distance, dump_off=False):
        super().__init__(game)
        self.piece = piece
        self.passer = passer
        self.position = position
        self.pass_distance = pass_distance
        self.roll = None
        self.reroll = None
        self.fumble = False
        self.interception_tried = False
        self.dump_off = dump_off
        self.catcher = game.get_player_at(position)
        self.eat_thrall = None
        self.ttm = type(piece) == Player
        self.turnover = False
        self.safe_throw_used = False

    def start(self):
        if self.dump_off:
            self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.DUMP_OFF, player=self.passer))
        self.catcher = self.game.get_catcher(self.position)

    def end(self):
        if self.turnover:
            Turnover(self.game)

    def step(self, action):

        if self.passer.state.blood_lust and self.eat_thrall is None:
            self.eat_thrall = EatThrall(self.game, self.passer)
            return False 
        
        if self.eat_thrall is not None and self.eat_thrall.failed: 
            return True
        
        # Otherwise roll if player hasn't rolled
        if self.roll is None:

            if self.piece.is_catchable():
                self.piece.is_carried = False

            # Check for interception
            if not self.interception_tried and self.piece.is_catchable():
                interceptors = self.game.get_interceptors(self.passer.position, self.position, team=self.game.get_opp_team(self.passer.team))
                if len(interceptors) > 0:
                    Interception(self.game, interceptors[0].team, self.piece, interceptors, self.passer)
                    self.interception_tried = True
                    return False

            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.target = self.passer.get_ag_target()
            self.roll.modifiers = self.game.get_pass_modifiers(self.passer, self.pass_distance, ttm=self.ttm)
            result = self.roll.get_sum()
            mod_result = result + self.roll.modifiers

            if result == 6 or (result != 1 and mod_result >= self.roll.target):
                # Treat as inaccurate if throw team-mate
                if type(self.piece) is Player:
                    self.game.report(Outcome(OutcomeType.INACCURATE_PASS, player=self.passer, rolls=[self.roll]))
                    self._inaccurate_pass()
                    return True
                # Accurate pass
                self.game.report(Outcome(OutcomeType.ACCURATE_PASS, player=self.passer, rolls=[self.roll]))
                self.game.move(self.piece, self.position)
                if type(self.piece) is Ball and not self.dump_off:
                    TurnoverIfPossessionLost(self.game, self.piece)
                if self.piece.is_catchable() and self.catcher is not None:
                    Catch(self.game, self.catcher, self.piece, accurate=True)
                elif type(self.piece) is Ball:
                    Bounce(self.game, self.piece)
                elif type(self.piece) is Bomb:
                    Explode(self.game, self.piece)
                elif type(self.piece) is Player:
                    if self.catcher is not None:
                        Bounce(self.game, self.piece)
                        KnockDown(self.game, self.catcher, self.piece)
                    else:
                        Land(self.game, self.piece)
                return True

            safe_throw = self.passer.has_skill(Skill.SAFE_THROW) and type(self.piece) == Ball

            if result == 1 or (mod_result <= 1 and not safe_throw):
                # Fumble
                self.fumble = True
                self.game.report(Outcome(OutcomeType.FUMBLE, player=self.passer, rolls=[self.roll]))
            elif mod_result <= 1 and safe_throw:
                # Inaccurate pass - Safe Throw
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.passer, skill=Skill.SAFE_THROW))
                self.safe_throw_used = True
            else:
                # Inaccurate pass
                self.game.report(Outcome(OutcomeType.INACCURATE_PASS, player=self.passer, rolls=[self.roll]))

            # Treat as inaccurate pass as a success if throw team-mate
            if not self.fumble and type(self.piece) is Player:
                self._inaccurate_pass()
                return True

            # Check if re-roll available
            self.reroll = Reroll(self.game, self.passer, context=self)
            return False

        # If re-roll used
        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.reroll = None
            self.roll = None
            self.fumble = False
            return False

        if self.safe_throw_used:
            return True

        if self.fumble:
            self._fumble()
        else:
            self._inaccurate_pass()
        return True

    def _fumble(self):
        if type(self.piece) is Ball:
            if not self.dump_off:
                Turnover(self.game)
            Bounce(self.game, self.piece)
        elif type(self.piece) is Player:
            Land(self.game, self.piece)
        elif type(self.piece) is Bomb:
            Explode(self.game, self.piece)

    def _inaccurate_pass(self):
        if type(self.piece) is Ball and not self.dump_off:
            TurnoverIfPossessionLost(self.game, self.piece)
        self.game.move(self.piece, self.position)
        Scatter(self.game, self.piece, is_pass=True)


class Season3PassAttempt(PassAttempt):
    """Ball passes: PA test, scatter, interception, then landing (in that order)."""

    def __init__(self, game, passer, piece, position, pass_distance, dump_off=False):
        super().__init__(game, passer, piece, position, pass_distance, dump_off)
        self.accurate = False
        self.landing_prepared = False
        self.scatter = None
        self.animosity = None
        self.on_ball_checked = False

    def _fumble(self):
        if type(self.piece) is Bomb:
            Explode(self.game, self.piece)
        else:
            super()._fumble()

    def step(self, action):
        if type(self.piece) is Bomb and self.game.get_bomb() is not self.piece:
            # A successful interceptor may already have thrown it back and
            # resolved the entire explosion before this attempt resumes.
            return True
        if self.passer.state.blood_lust and self.eat_thrall is None:
            self.eat_thrall = EatThrall(self.game, self.passer)
            return False
        if self.eat_thrall is not None and self.eat_thrall.failed:
            return True
        if self.passer.has_usable_skill(Skill.ANIMOSITY) and self.animosity is None:
            self.animosity = Animosity(self.game, self.passer, self.game.get_player_at(self.position))
            return False
        if not self.on_ball_checked:
            self.on_ball_checked = True
            if type(self.piece) is Ball:
                OnTheBallReaction(self.game, self.game.get_opp_team(self.passer.team))
                return False
        if not self.landing_prepared:
            if self.roll is None:
                self.piece.is_carried = False
                self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.PASSING_ROLL)
                self.roll.target = self.passer.get_pass_target()
                self.roll.modifiers = self.game.get_pass_modifiers(self.passer, self.pass_distance)
                result = self.roll.get_sum()
                succeeded = self.roll.is_d6_success()
                self.accurate = succeeded and self.pass_distance != PassDistance.HAIL_MARY
                # Check success first: PA 1+ passes a modified 1, but a natural
                # 1 still fails. Failed tests at modified 1 or less fumble;
                # see the user clarification in docs/season3-acceptance.md.
                self.fumble = not succeeded and (result == 1 or result + self.roll.modifiers <= 1)
                outcome = (OutcomeType.ACCURATE_PASS if self.accurate else
                           OutcomeType.FUMBLE if self.fumble else OutcomeType.INACCURATE_PASS)
                if not (self.fumble and result == 1 and self.passer.has_usable_skill(Skill.SAFE_PASS)):
                    self.game.report(Outcome(outcome, player=self.passer, rolls=[self.roll]))
                if not succeeded:
                    self.reroll = Reroll(self.game, self.passer, context=self)
                    return False
            elif self.reroll is not None and self.reroll.use_reroll:
                self.roll = None
                self.reroll = None
                return False

            if self.fumble:
                if self.roll.get_sum() == 1 and self.passer.has_usable_skill(Skill.SAFE_PASS):
                    self.piece.is_carried = True
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.passer, skill=Skill.SAFE_PASS))
                    if self.passer == self.game.get_active_player():
                        EndPlayerTurn(self.game, self.passer)
                    return True
                self._fumble()
                return True
            self.game.move(self.piece, self.position)
            self.landing_prepared = True
            if not self.accurate:
                self.scatter = Scatter(self.game, self.piece, is_pass=True, defer_landing=True)
                return False

        if self.game.is_out_of_bounds(self.piece.position):
            if type(self.piece) is Bomb:
                self.game.remove_bomb()
                return True
            if not self.dump_off:
                TurnoverIfPossessionLost(self.game, self.piece)
            ThrowIn(self.game, self.piece, self.scatter.throw_in_position)
            return True

        if not self.interception_tried:
            self.interception_tried = True
            interceptors = self.game.get_interceptors(
                self.passer.position, self.piece.position, self.game.get_opp_team(self.passer.team))
            if self.pass_distance == PassDistance.HAIL_MARY:
                interceptors = []
            elif self.passer.has_usable_skill(Skill.CLOUD_BURSTER):
                interceptors = [p for p in interceptors if p.has_usable_skill(Skill.VERY_LONG_LEGS)]
            if interceptors:
                Interception(self.game, interceptors[0].team, self.piece, interceptors,
                             self.passer, inaccurate=not self.accurate)
                return False

        # Successful interceptions have already resolved possession and turnover.
        if self.piece.is_carried:
            return True
        if not self.dump_off and type(self.piece) is Ball:
            TurnoverIfPossessionLost(self.game, self.piece)
        catcher = self.game.get_catcher(self.piece.position)
        if catcher is not None:
            Catch(self.game, catcher, self.piece, accurate=self.accurate, inaccurate=not self.accurate,
                  target_square=self.position)
        elif type(self.piece) is Bomb:
            Explode(self.game, self.piece)
        else:
            Bounce(self.game, self.piece)
        return True


class Pickup(Procedure):

    def __init__(self, game, ball, player, secure=False, turnover=True, score=True):
        super().__init__(game)
        self.ball = ball
        self.player = player
        self.roll = None
        self.reroll = None
        self.secure = secure
        self.turnover = turnover
        self.score = score

    def step(self, action):

        if self.game.is_season3 and self.player.has_skill(Skill.NO_BALL):
            self.game.report(Outcome(OutcomeType.FAILED_PICKUP, player=self.player,
                                     position=self.player.position, skill=Skill.NO_BALL))
            if self.turnover:
                Turnover(self.game)
            Bounce(self.game, self.ball)
            return True

        # Otherwise roll if player hasn't rolled
        if self.roll is None:

            self.roll = DiceRoll([D6(self.game.rng)], roll_type=(
                RollType.SECURE_BALL_ROLL if self.secure else RollType.AGILITY_ROLL))
            self.roll.target = 2 if self.secure else self.player.get_ag_target()
            self.roll.modifiers = (self.game.get_secure_ball_modifiers() if self.secure else
                                   self.game.get_pickup_modifiers(self.player, self.ball.position))

            # Roll
            if self.roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_PICKUP, player=self.player, rolls=[self.roll]))
                self.ball.is_carried = True
                if self.secure:
                    EndPlayerTurn(self.game, self.player)
                if self.score and self.game.is_touchdown(self.player):
                    Touchdown(self.game, self.player)
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_PICKUP, player=self.player, position=self.player.position,
                                         rolls=[self.roll]))
                # Check re-roll
                self.reroll = Reroll(self.game, self.player, context=self)
                return False

        assert self.reroll is not None

        # If re-roll is used
        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False

        if self.turnover:
            Turnover(self.game)
        Bounce(self.game, self.ball)
        return True


class StandUp(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.sroll_required = False
        self.moves_required = 3
        self.reroll = None
        self.roll = None
        self.moves_required = 0 if self.player.has_skill(Skill.JUMP_UP) else 3
        self.roll_required = self.player.get_ma() < self.moves_required

    def step(self, action):
        if self.roll_required and self.roll is None:
            modifier = self.game.get_stand_up_modifier(self.player)
            self.roll = DiceRoll([D6(self.game.rng)], target=4, modifiers=modifier, roll_type=RollType.STAND_UP_ROLL)
            if self.roll.is_d6_success():
                self.player.state.up = True
                self.game.report(Outcome(OutcomeType.STAND_UP, rolls=[self.roll], player=self.player))
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_STAND_UP, rolls=[self.roll], player=self.player))
                self.reroll = Reroll(self.game, self.player, self)
                return False
        elif not self.roll_required:
            self.game.report(Outcome(OutcomeType.STAND_UP, player=self.player))
            self.player.state.up = True
            return True

        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.reroll = None
            self.roll = None
            return False
        else:
            self.player.place_prone()
            self.game.report(Outcome(OutcomeType.FAILED_STAND_UP, rolls=[self.roll], player=self.player))
            EndPlayerTurn(self.game, self.player)
        return True


class PlaceBall(Procedure):

    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball
        self.aa = None

    def start(self):
        self.game.add_secondary_clock(self.game.get_kicking_team())
        self.aa = [ActionChoice(ActionType.PLACE_BALL, team=self.game.get_kicking_team(),
                                positions=self.game.get_team_side(self.game.get_receiving_team()))]

    def step(self, action):
        self.game.state.pitch.balls.append(self.ball)
        self.ball.on_ground = False
        self.ball.move_to(action.position)
        self.game.report(Outcome(OutcomeType.BALL_PLACED, position=action.position, team=self.game.get_kicking_team()))
        self.game.remove_secondary_clocks()
        return True

    def available_actions(self):
        return self.aa


class EndPlayerTurn(Procedure):

    def __init__(self, game, player, foregone=False):
        super().__init__(game)
        self.player = player
        self.stalling_checked = False
        self.foregone = foregone

    def step(self, action):
        if self.game.is_season3:
            reaction = self.game.get_proc(OnTheBallMove)
            if reaction is not None and reaction.player == self.player:
                reaction.ended = True
                return True
            multiple = self.game.get_proc(MultipleBlock)
            if multiple is not None and not multiple.done and multiple.attacker == self.player:
                multiple.activation_ended = True
                return True
        if self.game.state.player_action_type == PlayerActionType.SECURE_BALL:
            ball = self.game.get_ball()
            if not ball.is_carried or ball.position != self.player.position:
                Turnover(self.game)
                return True
        
        if self.player.state.blood_lust and not self.foregone:
            EatThrall(self.game, self.player)
            return False

        if self.game.is_season3 and not self.stalling_checked:
            self.stalling_checked = True
            passed_ball = (self.game.state.player_action_type in (PlayerActionType.PASS, PlayerActionType.HANDOFF)
                           and not self.game.has_ball(self.player))
            if self.player.state.could_score_at_activation and not passed_ball:
                CrowdTakesAction(self.game, self.player)
                return False

        self.game.purge_stack_until(Turn, inclusive=False)
        self.player.state.used = True
        self.player.state.moves = 0
        self.game.report(Outcome(OutcomeType.END_PLAYER_TURN, player=self.player))
        self.game.state.active_player = None
        self.player.state.squares_moved.clear()
        self.game.state.player_action_type = None
        self.player.state.has_blocked = False
        self.player.state.could_score_at_activation = False
        self.player.state.eye_gouged = False
        return True


class CrowdTakesAction(Procedure):
    """A crowd roll, not a player test: no skill/team re-roll or natural-6 override."""

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player

    def step(self, action):
        roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.STALLING_ROLL,
                        highest_succeed=False, lowest_fail=False)
        roll.target = self.player.team.state.turn
        hit = roll.get_sum() >= roll.target
        self.game.report(Outcome(OutcomeType.CROWD_TAKES_ACTION if hit else OutcomeType.CROWD_MISSES,
                                 player=self.player, rolls=[roll]))
        if hit:
            KnockDown(self.game, self.player, turnover=True)
        return True


class JumpUpToBlock(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.roll = None
        self.reroll = None

    def step(self, action):

        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.target = self.player.get_ag_target()
            self.roll.modifiers = 1 if self.game.is_season3 else 2
            if self.roll.is_d6_success():
                self.player.state.up = True
                self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.JUMP_UP, player=self.player, rolls=[self.roll]))
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_JUMP_UP, player=self.player, rolls=[self.roll]))
                self.reroll = Reroll(self.game, self.player, self)
                return False

        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        EndPlayerTurn(self.game, self.player)
        return True


class EscapeBeingEaten(Procedure):

    def __init__(self, game, hungry_player, delicious_player):
        super().__init__(game)
        self.hungry_player = hungry_player
        self.delicious_player = delicious_player
        self.roll = None
        self.reroll = None

    def step(self, action):

        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)])
            self.roll.target = 2
            if self.roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_ESCAPE_BEING_EATEN, player=self.hungry_player,
                                         opp_player=self.delicious_player, rolls=[self.roll]))
                Land(self.game, self.delicious_player)
                return True
            self.game.report(Outcome(OutcomeType.FAILED_ESCAPE_BEING_EATEN, player=self.hungry_player,
                                     opp_player=self.delicious_player, rolls=[self.roll]))
            self.game.report(Outcome(OutcomeType.EATEN_DURING_ALWAYS_HUNGRY, player=self.delicious_player, opp_player=self.hungry_player))
            self.reroll = Reroll(self.game, self.delicious_player, self)
            return False

        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        else:
            EndPlayerTurn(self.game, self.hungry_player)
            ball = self.game.get_ball_at(self.delicious_player.position)
            if ball is not None:
                TurnoverIfPossessionLost(self.game, ball)
                Bounce(self.game, ball)
            Casualty(self.game, player=self.delicious_player, inflictor=self.hungry_player, always_hungry=True)
        return True


class AlwaysHungry(Procedure):

    def __init__(self, game, hungry_player, delicious_player):
        super().__init__(game)
        self.hungry_player = hungry_player
        self.delicious_player = delicious_player
        self.roll = None
        self.reroll = None

    def step(self, action):

        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)])
            self.roll.target = 2
            if self.roll.is_d6_success():
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_ALWAYS_HUNGRY, player=self.hungry_player,
                                         opp_player=self.delicious_player, rolls=[self.roll]))
                return True
            self.game.report(Outcome(OutcomeType.FAILED_ALWAYS_HUNGRY, player=self.hungry_player,
                                     opp_player=self.delicious_player, rolls=[self.roll]))
            self.reroll = Reroll(self.game, self.hungry_player, self)
            return False

        assert self.reroll is not None

        if self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        else:
            EndPlayerTurn(self.game, self.hungry_player)
            EscapeBeingEaten(self.game, self.hungry_player, self.delicious_player)
        return True


class UndoPlayerAction(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.game = game
        self.player = player

    def step(self, action):
        self.game.state.player_action_type = None
        self.game.state.active_player = None
        return True


class MoveAction(Procedure):

    def __init__(self, game, player, player_action_type=PlayerActionType.MOVE):
        super().__init__(game)
        self.player = player
        self.player_action_type = player_action_type
        self.paths = {}
        self.steps = None
        self.orig_action_type = None
        self.can_undo = False

    def start(self):
        if self.player_action_type == PlayerActionType.MOVE:
            self.game.report(Outcome(OutcomeType.MOVE_ACTION_STARTED, player=self.player))
            self.game.state.player_action_type = PlayerActionType.MOVE
        self.can_undo = not self.game.is_season3 and self.game.get_team_agent(self.player.team).human and not self.player.state.failed_nega_trait_this_turn

    def step(self, action):

        # Follow the selected path
        if action is None:
            pos = self.steps.pop(0)
            if pos == self.player.position:
                action = Action(ActionType.STAND_UP)
            else:
                action_type = ActionType.JUMP if self.game.is_season3 and pos.distance(self.player.position) == 2 else ActionType.MOVE
                action = Action(action_type, position=pos)

        if action.action_type == ActionType.UNDO:
            UndoPlayerAction(self.game, self.player)
            return True

        self.can_undo = False

        if len(self.player.state.squares_moved) == 0:
            self.player.state.squares_moved.append(self.player.position)

        if action.action_type == ActionType.END_PLAYER_TURN:
            EndPlayerTurn(self.game, self.player)
            return True

        if action.action_type == ActionType.STAND_UP:

            # if this is the last step in a path
            if self.steps is not None and len(self.steps) == 0:
                self.steps = None

            self._stand_up()
            return False

        if action.action_type == ActionType.LEAP:

            distance = self.player.position.distance(action.position)
            gfis = (self.player.state.moves + distance) - self.player.get_ma() if self.player.state.moves + distance > self.player.get_ma() else 0
            Leap(self.game, self.player, action.position, gfis)
            self.player.state.squares_moved.append(action.position)
            self.player.state.moves += distance
            return False

        if action.action_type == ActionType.FUMBLEROOSKI:
            if self.player.position.distance(action.position) == 2:
                Jump(self.game, self.player, action.position, max(0, 2 - self.player.num_moves_left()), drop_ball=True)
                self.player.state.squares_moved.append(action.position)
                self.player.state.moves += 2
            else:
                self._move(action.position, drop_ball=True)
            return False

        if action.action_type == ActionType.JUMP:
            if self.steps is not None and not self.steps:
                self.steps = None
            rushes = max(0, 2 - self.player.num_moves_left())
            Jump(self.game, self.player, action.position, rushes)
            self.player.state.squares_moved.append(action.position)
            self.player.state.moves += 2
            return False

        if action.action_type == ActionType.HYPNOTIC_GAZE and self.player_action_type == PlayerActionType.MOVE:

            EndPlayerTurn(self.game, self.player)
            target_opponent = self.game.get_player_at(action.position)
            HypnoticGaze(self.game, self.player, target_opponent)
            return True

        if not self.game.is_quick_snap() and self.game.config.pathfinding_enabled:

            # Start new path?
            if self.steps is None:
                self.steps = list(self.paths[action.position].steps)
                self.orig_action_type = action.action_type
                return False

            # if this is the last step in a path
            if self.steps is not None and len(self.steps) == 0:
                self.steps = None

        self._move(action.position)

        return False

    def _stand_up(self):
        moves = 3
        if self.player.has_skill(Skill.JUMP_UP):
            moves = 0
            self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.JUMP_UP, player=self.player))
        StandUp(self.game, self.player)
        self.player.state.moves += min(self.player.get_ma(), moves)
        for i in range(moves):
            self.player.state.squares_moved.append(self.player.position)

    def _move(self, position, drop_ball=False):
        gfi = self.player.state.moves + 1 > self.player.get_ma()
        if self.game.is_quick_snap() or self.player.has_skill(Skill.BALL_AND_CHAIN):
            dodge = False
        else:
            dodge = self.game.num_tackle_zones_in(self.player) > 0
        Move(self.game, self.player, position, gfi, dodge, drop_ball=drop_ball)
        self.player.state.squares_moved.append(position)
        self.player.state.moves += 1

    def _get_actions_from_paths(self, paths):
        paths_by_type = {
            ActionType.MOVE: [],
            ActionType.BLOCK: [],
            ActionType.STAB: [],
            ActionType.HANDOFF: [],
            ActionType.FOUL: []
        }
        for path in paths:
            if path.block_dice:
                paths_by_type[ActionType.BLOCK].append(path)
                if self.player.has_skill(Skill.STAB):
                    paths_by_type[ActionType.STAB].append(path)
            elif path.handoff_roll:
                paths_by_type[ActionType.HANDOFF].append(path)
            elif path.foul_roll:
                paths_by_type[ActionType.FOUL].append(path)
            else:
                paths_by_type[ActionType.MOVE].append(path)
        actions = []
        for action_type, action_paths in paths_by_type.items():
            if len(action_paths) > 0:
                positions = [path.get_last_step() for path in action_paths]
                rolls = []
                if action_type == ActionType.HANDOFF:
                    rolls = [path.handoff_roll for path in action_paths]
                elif action_type == ActionType.FOUL:
                    rolls = [path.foul_roll for path in action_paths]
                block_dice = []
                if action_type == ActionType.BLOCK:
                    block_dice = [path.block_dice for path in action_paths]
                actions.append(ActionChoice(action_type=action_type, team=self.player.team, positions=positions,
                                            paths=action_paths, block_dice=block_dice, rolls=rolls))
        return actions

    def available_actions(self):
        if self.steps is not None and len(self.steps) > 0:
            return []  # No actions -> Continue path
        actions = []
        if self.game.is_quick_snap() or not self.game.config.pathfinding_enabled or self.game.is_chomped(self.player):
            actions = self.game.get_adjacent_move_actions(
                self.player, secure_ball=self.player_action_type == PlayerActionType.SECURE_BALL)
        else:
            can_block = self.player_action_type == PlayerActionType.BLITZ and not self.player.state.has_blocked
            can_foul = self.player_action_type == PlayerActionType.FOUL
            can_handoff = self.player_action_type == PlayerActionType.HANDOFF and self.game.has_ball(self.player)
            pathfinder = Pathfinder(self.game,
                                    self.player,
                                    directly_to_adjacent=self.game.config.pathfinding_directly_to_adjacent,
                                    can_block=can_block,
                                    can_handoff=can_handoff,
                                    can_foul=can_foul,
                                    secure_ball=self.player_action_type == PlayerActionType.SECURE_BALL,
                                    blitz_target=self.defender if isinstance(self, BlitzAction) else None,
                                    trr=self.game.is_season3)
            paths = pathfinder.get_paths()
            self.paths = {path.get_last_step(): path for path in paths}
            actions += self._get_actions_from_paths(paths)
        actions += self.game.get_stand_up_actions(self.player)
        actions += self.game.get_leap_actions(self.player)
        actions += self.game.get_jump_actions(self.player)
        if (self.game.is_season3 and self.player.has_usable_skill(Skill.FUMBLEROOSKI)
                and self.game.has_ball(self.player) and not self.player.has_skill(Skill.MY_BALL)):
            # Make the drop and departure one decision; a standalone drop could
            # incorrectly leave possession behind without actually moving.
            movement = self.game.get_adjacent_move_actions(self.player) + self.game.get_jump_actions(self.player)
            for choice in movement:
                if choice.action_type in (ActionType.MOVE, ActionType.JUMP):
                    actions.append(ActionChoice(ActionType.FUMBLEROOSKI, team=self.player.team,
                                                positions=choice.positions, rolls=choice.rolls,
                                                skill=Skill.FUMBLEROOSKI))
        if not self.game.is_season3 and self.player.has_skill(Skill.HYPNOTIC_GAZE) and self.player_action_type == PlayerActionType.MOVE:
            actions += self.game.get_hypnotic_gaze_actions(self.player)
        actions.append(ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team))

        if self.can_undo:
            actions.append(ActionChoice(ActionType.UNDO, team=self.player.team))

        return actions


class OnTheBallReaction(Procedure):
    def __init__(self, game, team, ball=None):
        super().__init__(game)
        self.team = team
        self.ball = ball
        self.players = []
        self.failed = False

    def start(self):
        # Kick-off eligibility is evaluated after deviation, not when queued.
        touchback = self.ball is not None and (self.game.is_out_of_bounds(self.ball.position)
                                              or not self.game.is_team_side(self.ball.position, self.team))
        if not touchback:
            self.players = [p for p in self.game.get_players_on_pitch(self.team)
                            if p.has_usable_skill(Skill.ON_THE_BALL) and not p.state.taken_root
                            and not self.game.is_chomped(p) and
                            (self.ball is None or self.game.num_tackle_zones_in(p) == 0)]

    def step(self, action):
        if self.failed or not self.players or action.action_type == ActionType.SELECT_NONE:
            return True
        player = action.player
        if self.ball is not None:
            self.players = []
        else:
            self.players.remove(player)
        self.game.report(Outcome(OutcomeType.SKILL_USED, player=player, skill=Skill.ON_THE_BALL))
        OnTheBallMove(self.game, player, self)
        return False

    def available_actions(self):
        if self.failed or not self.players:
            return []
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.team, players=self.players, skill=Skill.ON_THE_BALL),
                ActionChoice(ActionType.SELECT_NONE, team=self.team, skill=Skill.ON_THE_BALL)]


class OnTheBallMove(Procedure):
    def __init__(self, game, player, reaction):
        super().__init__(game)
        self.player = player
        self.reaction = reaction
        self.moves = 0
        self.ended = False

    def step(self, action):
        if self.ended or self.reaction.failed or self.moves >= min(3, self.player.get_ma()):
            return True
        if action.action_type == ActionType.END_PLAYER_TURN:
            return True
        distance = self.player.position.distance(action.position)
        self.moves += distance
        if distance == 2:
            Jump(self.game, self.player, action.position, 0)
        else:
            Move(self.game, self.player, action.position, False,
                 self.game.num_tackle_zones_in(self.player) > 0)
        return False

    def available_actions(self):
        if self.ended or self.reaction.failed or self.moves >= min(3, self.player.get_ma()):
            return []
        actions = [ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team)]
        if self.player.state.up and not self.player.state.taken_root and not self.game.is_chomped(self.player):
            for kind, positions in (
                    (ActionType.MOVE, self.game.get_adjacent_squares(self.player.position, occupied=False)),
                    (ActionType.JUMP, self.game.get_jump_positions(self.player) if self.moves + 2 <= min(3, self.player.get_ma()) else [])):
                if self.reaction.ball is not None:
                    positions = [p for p in positions if self.game.is_team_side(p, self.player.team)]
                if positions:
                    actions.append(ActionChoice(kind, team=self.player.team, positions=positions, skill=Skill.ON_THE_BALL))
        return actions


class SpecialAction(MoveAction):
    def __init__(self, game, player, skill):
        super().__init__(game, player, player_action_type=PlayerActionType.SPECIAL)
        self.skill = skill

    def start(self):
        self.game.state.player_action_type = PlayerActionType.SPECIAL

    def step(self, action):
        if action is not None and action.action_type == SEASON3_SPECIAL_ACTIONS[self.skill][1]:
            EndPlayerTurn(self.game, self.player)
            SpecialAttack(self.game, self.player, self.game.get_player_at(action.position), self.skill)
            return True
        return super().step(action)

    def available_actions(self):
        if self.steps:
            return []
        actions = super().available_actions() if self.skill == Skill.HYPNOTIC_GAZE else [
            ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team)]
        if self.player.has_usable_skill(self.skill):
            targets = [p.position for p in self.game.get_adjacent_opponents(self.player, down=False)]
            if targets:
                actions.append(ActionChoice(SEASON3_SPECIAL_ACTIONS[self.skill][1], team=self.player.team,
                                            positions=targets, skill=self.skill))
        return actions


class SpecialAttack(Procedure):
    """Targeted Season 3 actions share reactions but retain their own dice rules."""
    def __init__(self, game, attacker, defender, skill):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.skill = skill
        self.casualty_credit = attacker.has_usable_skill(Skill.VIOLENT_INNOVATOR)
        self.appearance = None
        self.appearance_checked = False
        self.dump_checked = False
        self.roll = None
        self.reroll = None

        self.trickster = None
        self.trickster_checked = False

    def start(self):
        pass

    def end(self):
        if self.skill == Skill.STAB:
            AfterBlock(self.game, self.attacker, self.defender, knocked_down=False)
        if self.trickster is not None and self.trickster.used and self.game.is_touchdown(self.defender):
            Touchdown(self.game, self.defender)

    def step(self, action):
        if not self.appearance_checked:
            self.appearance_checked = True
            if self.defender.has_skill(Skill.FOUL_APPEARANCE):
                self.appearance = FoulAppearance(self.game, self.attacker, self.defender)
                return False
            return False
        if self.appearance is not None and self.appearance.revolted:
            EndPlayerTurn(self.game, self.attacker)
            return True
        if not self.trickster_checked:
            self.trickster_checked = True
            if self.defender.has_usable_skill(Skill.TRICKSTER):
                self.trickster = Trickster(self.game, self.attacker, self.defender)
            return False
        if not self.dump_checked:
            self.dump_checked = True
            if action is not None and action.action_type == ActionType.USE_SKILL:
                PassAction(self.game, self.defender, dump_off=True)
                return False
        if self.skill == Skill.HYPNOTIC_GAZE:
            HypnoticGaze(self.game, self.attacker, self.defender)
            return True
        if self.skill == Skill.STAB:
            Armor(self.game, self.defender, inflictor=self.attacker, knockdown_on_break=True,
                  casualty_credit=self.casualty_credit)
            return True
        if self.roll is None:
            target = 2 if self.skill in (Skill.PROJECTILE_VOMIT, Skill.CHAINSAW) else (
                3 if self.skill == Skill.MONSTROUS_MOUTH else 4)
            modifier = -1 if self.skill == Skill.BREATHE_FIRE and self.defender.get_st() >= 5 else 0
            self.roll = DiceRoll([D6(self.game.rng)], target=target, modifiers=modifier)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker,
                                     skill=self.skill, rolls=[self.roll]))
            if not self.roll.is_d6_success():
                self.reroll = Reroll(self.game, self.attacker, self)
                return False
        elif self.reroll is not None and self.reroll.use_reroll:
            self.roll = None
            self.reroll = None
            return False
        if self.skill == Skill.PROJECTILE_VOMIT:
            victim = self.defender if self.roll.is_d6_success() else self.attacker
            Armor(self.game, victim, inflictor=self.attacker, knockdown_on_break=True,
                  casualty_credit=self.casualty_credit)
        elif self.skill == Skill.CHAINSAW:
            if self.roll.is_d6_success():
                Armor(self.game, self.defender, inflictor=self.attacker, modifiers=3, knockdown_on_break=True,
                      casualty_credit=self.casualty_credit)
            else:
                KnockDown(self.game, self.attacker, turnover=True)
        elif self.skill == Skill.BREATHE_FIRE:
            if self.roll.get_sum() == 6:
                KnockDown(self.game, self.defender, inflictor=self.attacker, casualty_credit=self.casualty_credit)
            elif self.roll.get_result() <= 1:
                KnockDown(self.game, self.attacker, turnover=True)
            elif self.roll.get_result() >= 4:
                KnockDown(self.game, self.defender, armor_roll=False, injury_roll=False)
        elif self.skill == Skill.MONSTROUS_MOUTH and self.roll.is_d6_success():
            self.defender.state.chomped_by = self.attacker.player_id
            if self.defender not in self.game.state.chomped_players:
                self.game.state.chomped_players.append(self.defender)
        return True

    def available_actions(self):
        if (self.appearance_checked and self.trickster_checked and not self.dump_checked and self.game.has_ball(self.defender)
                and not (self.appearance is not None and self.appearance.revolted)
                and self.defender.has_usable_skill(Skill.DUMP_OFF) and not self.defender.has_skill(Skill.MY_BALL)):
            return [ActionChoice(kind, team=self.defender.team, players=[self.defender], skill=Skill.DUMP_OFF)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        return []


class Trickster(Procedure):
    def __init__(self, game, attacker, defender):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.used = False

    def step(self, action):
        if action is not None and action.action_type == ActionType.MOVE:
            self.used = True
            self.defender.state.chomped_by = None
            if self.defender in self.game.state.chomped_players:
                self.game.state.chomped_players.remove(self.defender)
            self.game.move(self.defender, action.position)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.defender,
                                     skill=Skill.TRICKSTER, position=action.position))
            ball = self.game.get_ball_at(action.position)
            if ball is not None and not ball.is_carried:
                Pickup(self.game, ball, self.defender,
                       turnover=self.defender.team == self.game.state.current_team, score=False)
        return True

    def available_actions(self):
        if self.defender.state.taken_root:
            return []
        squares = self.game.get_adjacent_squares(self.attacker.position, occupied=False)
        if not squares:
            return []
        return [ActionChoice(ActionType.MOVE, team=self.defender.team, positions=squares, skill=Skill.TRICKSTER),
                ActionChoice(ActionType.DONT_USE_SKILL, team=self.defender.team, skill=Skill.TRICKSTER)]


class AfterBlock(Procedure):
    def __init__(self, game, attacker, defender, knocked_down):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.knocked_down = knocked_down
        self.pile_checked = False

    def can_pile(self):
        return (not self.pile_checked and self.knocked_down and self.defender.position is not None
                and not self.defender.state.up and self.attacker.has_usable_skill(Skill.PILE_DRIVER)
                and self.attacker.position is not None and
                self.attacker.position.distance(self.defender.position) == 1)

    def hit_run_squares(self):
        if (not self.attacker.has_usable_skill(Skill.HIT_AND_RUN) or self.attacker.position is None
                or self.attacker.state.taken_root or self.game.is_chomped(self.attacker)):
            return []
        return [s for s in self.game.get_adjacent_squares(self.attacker.position, occupied=False)
                if not self.game.get_adjacent_players(s, team=self.defender.team)]

    def step(self, action):
        if self.can_pile():
            self.pile_checked = True
            if action.action_type == ActionType.USE_SKILL:
                EndPlayerTurn(self.game, self.attacker)
                BlockResolution(self.game)
                PileDriverProne(self.game, self.attacker)
                Foul(self.game, self.attacker, self.defender)
                return True
            return False
        if action is not None and action.action_type == ActionType.MOVE:
            self.game.move(self.attacker, action.position)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker,
                                     skill=Skill.HIT_AND_RUN, position=action.position))
            ball = self.game.get_ball_at(action.position)
            if ball is not None and not ball.is_carried:
                Pickup(self.game, ball, self.attacker)
            elif self.game.has_ball(self.attacker) and self.game.is_touchdown(self.attacker):
                Touchdown(self.game, self.attacker)
        return True

    def available_actions(self):
        if self.can_pile():
            return [ActionChoice(kind, team=self.attacker.team, skill=Skill.PILE_DRIVER)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        squares = self.hit_run_squares()
        if squares:
            return [ActionChoice(ActionType.MOVE, team=self.attacker.team, positions=squares, skill=Skill.HIT_AND_RUN),
                    ActionChoice(ActionType.DONT_USE_SKILL, team=self.attacker.team, skill=Skill.HIT_AND_RUN)]
        return []


class PileDriverProne(Procedure):
    def __init__(self, game, player):
        super().__init__(game)
        self.player = player

    def step(self, action):
        if self.player.position is not None:
            KnockDown(self.game, self.player, armor_roll=False, injury_roll=False)
        return True


class SecureBallAction(MoveAction):
    """A Move Action ending in a mandatory base 2+ pickup and activation end."""

    def __init__(self, game, player):
        super().__init__(game, player, player_action_type=PlayerActionType.SECURE_BALL)

    def start(self):
        self.game.state.player_action_type = PlayerActionType.SECURE_BALL
        self.game.report(Outcome(OutcomeType.SECURE_BALL_ACTION_STARTED, player=self.player))
        self.can_undo = False

    def _at_ball(self):
        ball = self.game.get_ball()
        return self.player.state.up and ball.on_ground and not ball.is_carried and ball.position == self.player.position

    def step(self, action):
        if self._at_ball():
            Pickup(self.game, self.game.get_ball(), self.player, secure=True)
            return False
        return super().step(action)

    def available_actions(self):
        if self._at_ball():
            return []  # Mandatory pickup, including when starting on the ball.
        if not self.player.state.up:
            return self.game.get_stand_up_actions(self.player) + [
                ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team)]
        return super().available_actions()


class HandoffAction(MoveAction):

    def __init__(self, game, player):
        super().__init__(game, player, player_action_type=PlayerActionType.HANDOFF)

    def start(self):
        self.game.use_handoff_action()
        self.game.report(Outcome(OutcomeType.HANDOFF_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.HANDOFF
        super().start()

    def step(self, action):
        # Continue moving along path
        if action is None:
            player_at = self.game.get_player_at(self.steps[0])
            if player_at is None or (player_at == self.player and not player_at.state.up):
                return super().step(action)
            action = Action(ActionType.HANDOFF, position=self.steps.pop(0))
            self.steps = None

        if action.action_type is ActionType.UNDO:
            self.game.unuse_handoff_action()
            return super().step(action)

        self.can_undo = False

        if action.action_type is ActionType.HANDOFF:
            if self.player.position.distance(action.position) == 1:
                if self.game.is_season3 and self.player.has_usable_skill(Skill.GIVE_AND_GO):
                    MoveAction(self.game, self.player)
                else:
                    EndPlayerTurn(self.game, self.player)
                ball = self.game.get_ball_at(self.player.position)
                assert ball is not None
                Handoff(self.game, ball, self.player, action.position,
                        self.game.get_player_at(action.position))
                return True

        # It's a move action
        return super().step(action)

    def available_actions(self):
        # If MoveAction is following a path -> continue
        if self.steps is not None:
            return []
        # Path-assisted moves
        actions = super().available_actions()
        # If pathfinding not enabled add them
        if not self.game.config.pathfinding_enabled and self.game.has_ball(self.player):
            actions.extend(self.game.get_handoff_actions(self.player))
        return actions


class PassAction(MoveAction):

    def __init__(self, game, player, dump_off=False):
        super().__init__(game, player, player_action_type=PlayerActionType.PASS)
        self.dump_off = dump_off
        self.picked_up_teammate = None
        self.previous_action = game.state.player_action_type

    def start(self):
        if self.game.is_season3 and self.dump_off:
            return
        self.game.use_pass_action()
        self.game.report(Outcome(OutcomeType.PASS_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.PASS
        super().start()

    def step(self, action):

        if self.game.is_season3 and self.dump_off and action.action_type == ActionType.SELECT_NONE:
            return True

        # Continue moving along path
        if action is None:
            return super().step(action)

        if action.action_type is ActionType.UNDO:
            self.game.unuse_pass_action()
            return super().step(action)

        self.can_undo = False

        if action.action_type is ActionType.PASS:
            pass_distance = self.game.get_pass_distance(self.player.position, action.position)
            if not self.dump_off:
                self.game.use_pass_action()
                if (self.game.is_season3 and pass_distance == PassDistance.QUICK_PASS and
                        self.player.has_usable_skill(Skill.GIVE_AND_GO)):
                    MoveAction(self.game, self.player)
                else:
                    EndPlayerTurn(self.game, self.player)
            piece = self.game.get_ball_at(self.player.position)
            attempt = Season3PassAttempt if self.game.is_season3 and type(piece) is Ball else PassAttempt
            attempt(self.game, self.player, piece, action.position, pass_distance, dump_off=self.dump_off)
            return True

        if action.action_type == ActionType.PICKUP_TEAM_MATE:
            self.picked_up_teammate = self.game.get_player_at(action.position)
            self.game.lift(self.picked_up_teammate)
            if self.player.has_skill(Skill.ALWAYS_HUNGRY):
                AlwaysHungry(self.game, self.player, self.picked_up_teammate)
            return False

        if action.action_type == ActionType.THROW_TEAM_MATE:
            pass_distance = self.game.get_pass_distance(self.player.position, action.position)
            EndPlayerTurn(self.game, self.player)
            PassAttempt(self.game, self.player, self.picked_up_teammate, action.position, pass_distance)
            return True

        return super().step(action)

    def available_actions(self):
        if self.game.is_season3 and self.dump_off:
            return [choice for choice in self.game.get_pass_actions(self.player, self.game.get_ball(), dump_off=True)
                    if choice.action_type == ActionType.PASS] + [
                ActionChoice(ActionType.SELECT_NONE, team=self.player.team)]
        # If MoveAction is following a path -> continue
        if self.steps is not None:
            return []

        actions = []
        if not self.picked_up_teammate:
            actions.extend(super().available_actions())

        if not self.game.is_season3 and self.player.has_skill(Skill.THROW_TEAM_MATE) and self.player.state.up:
            if self.picked_up_teammate is None:
                # Pickup team-mate
                ptm_actions = self.game.get_pickup_teammate_actions(self.player)
                actions.extend(ptm_actions)
            else:
                # Throw team-mate actions
                pass_actions = self.game.get_pass_actions(self.player, self.picked_up_teammate)
                actions.extend(pass_actions)

        # Pass actions
        if self.game.has_ball(self.player) and self.picked_up_teammate is None:
            piece = self.game.get_ball_at(self.player.position)
            pass_actions = self.game.get_pass_actions(self.player, piece, dump_off=self.dump_off)
            actions.extend(pass_actions)

        return actions


class BallAndChainAction(Procedure):
    def __init__(self, game, player):
        super().__init__(game)
        self.player = player

    def start(self):
        self.game.state.player_action_type = PlayerActionType.SPECIAL

    def step(self, action):
        if self.player.position is None or not self.player.state.up or action.action_type == ActionType.END_PLAYER_TURN:
            EndPlayerTurn(self.game, self.player)
            return True
        self.player.state.moves += 1
        BlockResolution(self.game)
        BallAndChainMove(self.game, self.player, action.position)
        return False

    def available_actions(self):
        if self.player.position is None or not self.player.state.up:
            return []
        actions = [ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team)]
        if self.player.num_moves_left(include_gfi=True) > 0 and not self.player.state.taken_root:
            directions = [self.game.get_square(self.player.position.x + dx, self.player.position.y + dy)
                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            actions.append(ActionChoice(ActionType.BALL_AND_CHAIN, team=self.player.team, positions=directions,
                                        skill=Skill.BALL_AND_CHAIN))
        return actions


class BallAndChainMove(Procedure):
    def __init__(self, game, player, direction):
        super().__init__(game)
        self.player = player
        self.direction = direction
        self.destination = None
        self.rush = None
        self.phase = 'direction'
        self.prone_target = None

    def step(self, action):
        if self.phase == 'direction':
            dx, dy = self.direction.x - self.player.position.x, self.direction.y - self.player.position.y
            roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.SCATTER_ROLL)
            side = (roll.get_sum() - 1) // 2 - 1
            self.destination = self.game.get_square(self.player.position.x + dx - side * dy,
                                                     self.player.position.y + dy + side * dx)
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.BALL_AND_CHAIN,
                                     position=self.destination, rolls=[roll]))
            self.phase = 'move'
            if self.player.state.moves > self.player.get_ma():
                self.rush = GFI(self.game, self.player, self.player.position, defer_fall=True)
                return False
        if self.phase == 'move':
            self.phase = 'after_move'
            if self.game.is_out_of_bounds(self.destination):
                self.game.move(self.player, self.destination)
                Turnover(self.game)
                Injury(self.game, self.player, in_crowd=True)
                return True
            target = self.game.get_player_at(self.destination)
            if target is None:
                self.game.move(self.player, self.destination)
            elif target.state.up:
                Block(self.game, self.player, target, ball_and_chain=True)
                return False
            else:
                self.prone_target = target
                Push(self.game, self.player, target)
                return False
        if self.phase == 'after_move':
            self.phase = 'finish'
            if self.prone_target is not None and self.prone_target.position is not None:
                Armor(self.game, self.prone_target, inflictor=self.player,
                      casualty_credit=self.player.has_usable_skill(Skill.VIOLENT_INNOVATOR))
                return False
        if self.phase == 'finish':
            if self.player.position is not None:
                ball = self.game.get_ball_at(self.player.position)
                if self.rush is not None and self.rush.failed and self.player.state.up:
                    KnockDown(self.game, self.player, turnover=True)
                if ball is not None and not ball.is_carried:
                    Bounce(self.game, ball)
            return True
        return False


class PuntAction(MoveAction):
    def __init__(self, game, player):
        super().__init__(game, player, player_action_type=PlayerActionType.SPECIAL)

    def start(self):
        super().start()
        self.game.state.player_action_type = PlayerActionType.SPECIAL

    def step(self, action):
        if action is not None and action.action_type == ActionType.PUNT:
            EndPlayerTurn(self.game, self.player)
            Punt(self.game, self.player, action.position)
            return True
        return super().step(action)

    def available_actions(self):
        actions = super().available_actions()
        if self.steps is None and self.player.state.up and self.game.has_ball(self.player):
            positions = [self.game.get_square(self.player.position.x + dx, self.player.position.y + dy)
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            actions.append(ActionChoice(ActionType.PUNT, team=self.player.team, positions=positions, skill=Skill.PUNT))
        return actions


class Punt(Procedure):
    def __init__(self, game, player, direction):
        super().__init__(game)
        self.player = player
        self.dx, self.dy = direction.x - player.position.x, direction.y - player.position.y
        self.ball = game.get_ball_at(player.position)
        self.phase = 'direction'
        self.direction_roll = None
        self.distance_roll = None
        self.kick_checked = False
        self.out = False

    def step(self, action):
        if self.phase == 'resolved':
            carrier = self.game.get_ball_carrier()
            if self.out or (carrier is not None and carrier.team != self.player.team):
                Turnover(self.game)
            return True
        attribute = self.phase + '_roll'
        if getattr(self, attribute) is None:
            setattr(self, attribute, DiceRoll([D6(self.game.rng)], roll_type=(
                RollType.SCATTER_ROLL if self.phase == 'direction' else RollType.DISTANCE_ROLL)))
            if self.player.has_usable_skill(Skill.KICK):
                return False
        elif not self.kick_checked and self.player.has_usable_skill(Skill.KICK):
            self.kick_checked = True
            if action.action_type == ActionType.USE_SKILL:
                setattr(self, attribute, DiceRoll([D6(self.game.rng)], roll_type=(
                    RollType.SCATTER_ROLL if self.phase == 'direction' else RollType.DISTANCE_ROLL)))
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.KICK,
                                         rolls=[getattr(self, attribute)]))
        if self.phase == 'direction':
            self.phase = 'distance'
            self.kick_checked = False
            return False
        side = (self.direction_roll.get_sum() - 1) // 2 - 1
        dx, dy = self.dx - side * self.dy, self.dy + side * self.dx
        self.ball.is_carried = False
        last = self.player.position
        for _ in range(self.distance_roll.get_sum()):
            last = self.ball.position
            self.ball.move_to(self.game.get_square(last.x + dx, last.y + dy))
            if self.game.is_out_of_bounds(self.ball.position):
                self.out = True
                break
        self.phase = 'resolved'
        self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.PUNT,
                                 position=self.ball.position, rolls=[self.direction_roll, self.distance_roll]))
        if self.out:
            ThrowIn(self.game, self.ball, last)
        else:
            catcher = self.game.get_player_at(self.ball.position)
            if catcher is not None:
                Catch(self.game, catcher, self.ball, punt=True)
            else:
                Bounce(self.game, self.ball)
        return False

    def available_actions(self):
        if (self.phase != 'resolved' and getattr(self, self.phase + '_roll') is not None
                and not self.kick_checked and self.player.has_usable_skill(Skill.KICK)):
            return [ActionChoice(kind, team=self.player.team, skill=Skill.KICK,
                                 rolls=[[getattr(self, self.phase + '_roll').get_sum()]])
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        return []


class ThrowTeamMateAction(MoveAction):
    """Season 3 has independent pass, throw and kick allowances."""

    def __init__(self, game, player, kick=False):
        super().__init__(game, player, player_action_type=(
            PlayerActionType.KICK_TEAM_MATE if kick else PlayerActionType.THROW_TEAM_MATE))
        self.kick = kick
        self.teammate = None

    def start(self):
        super().start()
        self.game.state.player_action_type = self.player_action_type

    def step(self, action):
        if action is not None and action.action_type == ActionType.PICKUP_TEAM_MATE:
            self.teammate = self.game.get_player_at(action.position)
            return False
        if action is not None and action.action_type == ActionType.THROW_TEAM_MATE:
            EndPlayerTurn(self.game, self.player)
            # Finish every collision, injury and ball movement before a turnover.
            BlockResolution(self.game)
            Season3ThrowTeamMate(self.game, self.player, self.teammate, action.position, self.kick)
            return True
        return super().step(action)

    def available_actions(self):
        if self.steps is not None:
            return []
        if self.teammate is not None:
            return self.game.get_pass_actions(self.player, self.teammate)
        actions = super().available_actions()
        if self.player.state.up and not self.player.is_distracted():
            actions += self.game.get_pickup_teammate_actions(self.player)
        return actions


class HungerTest(Procedure):
    """Separate roll contexts ensure each of the two hunger dice can be rerolled once."""

    def __init__(self, game, player, escape=False):
        super().__init__(game)
        self.player = player
        self.escape = escape
        self.roll = None
        self.reroll = None
        self.success = False

    def step(self, action):
        if self.reroll is not None:
            if not self.reroll.use_reroll:
                return True
            self.roll = self.reroll = None
        if self.roll is None:
            self.roll = DiceRoll([D6(self.game.rng)], target=2)
            self.success = self.roll.is_d6_success()
            kind = ((OutcomeType.SUCCESSFUL_ESCAPE_BEING_EATEN if self.success else OutcomeType.FAILED_ESCAPE_BEING_EATEN)
                    if self.escape else (OutcomeType.SUCCESSFUL_ALWAYS_HUNGRY if self.success else OutcomeType.FAILED_ALWAYS_HUNGRY))
            self.game.report(Outcome(kind, player=self.player, rolls=[self.roll]))
            if not self.success:
                self.reroll = Reroll(self.game, self.player, self)
                return False
        return True


class Season3ThrowTeamMate(Procedure):
    """PA test, scatter/bounce, collisions, then a landing with the throw's modifier."""

    def __init__(self, game, thrower, player, position, kick=False):
        super().__init__(game)
        self.thrower = thrower
        self.player = player
        self.position = position
        self.kick = kick
        self.phase = 'hunger'
        self.hunger = None
        self.escape = None
        self.roll = None
        self.reroll = None
        self.superb = False
        self.fumbled = False
        self.auto_fail = not player.state.up or player.state.stunned or player.is_distracted()
        self.lethal = player.has_usable_skill(Skill.LETHAL_FLIGHT)
        self.ball = game.get_ball_at(player.position) if game.has_ball(player) else None
        self.swoop = False
        self.bullseye_checked = False
        self.swoop_checked = False
        self.last_in_bounds = player.position

    def _move_air(self, square):
        # An airborne player may share an occupied square. Move only their own
        # ball, never the ball carried by a player they have collided with.
        if not self.game.is_out_of_bounds(self.player.position):
            self.last_in_bounds = self.player.position
        self.game.remove(self.player)
        self.game.put(self.player, square)
        if self.ball is not None and self.ball.is_carried:
            self.ball.move_to(square)

    def _travel(self, dx, dy, distance):
        for _ in range(distance):
            self._move_air(self.game.get_square(self.player.position.x + dx, self.player.position.y + dy))
            if self.game.is_out_of_bounds(self.player.position):
                break

    def _bounce(self):
        roll = DiceRoll([D8(self.game.rng)], roll_type=RollType.SCATTER_ROLL)
        dx, dy = {1: (-1, -1), 2: (0, -1), 3: (1, -1), 4: (-1, 0),
                  5: (1, 0), 6: (-1, 1), 7: (0, 1), 8: (1, 1)}[roll.get_sum()]
        self._travel(dx, dy, 1)
        self.game.report(Outcome(OutcomeType.PLAYER_SCATTER, player=self.player, rolls=[roll]))

    def step(self, action):
        if self.phase == 'hunger':
            if self.thrower.has_usable_skill(Skill.ALWAYS_HUNGRY):
                if self.hunger is None:
                    self.hunger = HungerTest(self.game, self.thrower)
                    return False
                if not self.hunger.success:
                    if self.escape is None:
                        self.escape = HungerTest(self.game, self.player, escape=True)
                        return False
                    if not self.escape.success:
                        if self.ball is not None:
                            Turnover(self.game)
                            Bounce(self.game, self.ball)
                        Casualty(self.game, self.player, self.thrower, always_hungry=True)
                        self.game.report(Outcome(OutcomeType.EATEN_DURING_ALWAYS_HUNGRY,
                                                 player=self.player, opp_player=self.thrower))
                        return True
                    self.fumbled = True
            self.phase = 'accuracy'
        if self.phase == 'accuracy':
            if not self.fumbled:
                if self.reroll is not None and self.reroll.use_reroll:
                    self.roll = self.reroll = None
                if self.roll is None:
                    distance = self.game.get_pass_distance(self.thrower.position, self.position)
                    self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.PASSING_ROLL,
                                         target=self.thrower.get_pass_target(),
                                         modifiers=self.game.get_pass_modifiers(self.thrower, distance, ttm=True))
                    self.superb = self.roll.is_d6_success()
                    # Keep the same accepted modified <=1 convention as S3 passes.
                    self.fumbled = not self.superb and (self.roll.get_sum() == 1 or self.roll.get_result() <= 1)
                    self.game.report(Outcome(OutcomeType.ACCURATE_PASS if self.superb else
                                             OutcomeType.FUMBLE if self.fumbled else OutcomeType.INACCURATE_PASS,
                                             player=self.thrower, rolls=[self.roll]))
                    if not self.superb:
                        self.reroll = Reroll(self.game, self.thrower, self)
                        return False
            # A rerolled fumble must replace the original result too.
            if self.reroll is not None and self.reroll.use_reroll:
                self.roll = self.reroll = None
                self.fumbled = False
                return False
            if self.fumbled and self.kick:
                if self.ball is not None:
                    Turnover(self.game)
                    Bounce(self.game, self.ball)
                Injury(self.game, self.player, stunned_is_ko=True)
                return True
            self.game.lift(self.player)
            self._move_air(self.thrower.position if self.fumbled else self.position)
            self.phase = 'scatter'
            if self.fumbled:
                self._bounce()
                self.phase = 'landing'
        if self.phase == 'scatter':
            if self.superb and self.thrower.has_usable_skill(Skill.BULLSEYE) and not self.bullseye_checked:
                if action is None:
                    return False
                self.bullseye_checked = True
                if action.action_type == ActionType.USE_SKILL:
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.thrower, skill=Skill.BULLSEYE))
                    self.phase = 'landing'
                return False
            if self.player.has_usable_skill(Skill.SWOOP) and not self.swoop_checked:
                if action is None:
                    return False
                self.swoop_checked = True
                if action.action_type == ActionType.USE_SKILL:
                    self.swoop = True
                    self.phase = 'swoop'
                    return False
            for _ in range(3):
                self._bounce()
                if self.game.is_out_of_bounds(self.player.position):
                    break
            self.phase = 'landing'
        if self.phase == 'swoop':
            if action is None:
                return False
            dx, dy = action.position.x - self.position.x, action.position.y - self.position.y
            direction = DiceRoll([D6(self.game.rng)], roll_type=RollType.SCATTER_ROLL)
            distance = DiceRoll([D6(self.game.rng)], roll_type=RollType.DISTANCE_ROLL)
            side = (direction.get_sum() - 1) // 2 - 1
            self._travel(dx - side * dy, dy + side * dx, distance.get_sum())
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player,
                                     skill=Skill.SWOOP, rolls=[direction, distance]))
            self.phase = 'landing'
        if self.phase == 'bounce':
            self._bounce()
            self.phase = 'landing'
        if self.phase == 'landing':
            if self.game.is_out_of_bounds(self.player.position):
                self.player.state.in_air = False
                Turnover(self.game)
                if self.ball is not None:
                    self.ball.is_carried = False
                    ThrowIn(self.game, self.ball, self.last_in_bounds)
                Injury(self.game, self.player, in_crowd=True)
                self.game.report(Outcome(OutcomeType.PLAYER_OUT_OF_BOUNDS, player=self.player))
                return True
            victim = self.game.get_player_at(self.player.position)
            if victim is not None:
                self.auto_fail = True
                self.phase = 'bounce'
                self.game.report(Outcome(OutcomeType.PLAYER_HIT_PLAYER, player=self.player, opp_player=victim))
                KnockDown(self.game, victim, inflictor=self.player,
                          turnover=victim.team == self.game.state.current_team,
                          damage_skill=Skill.LETHAL_FLIGHT if self.lethal and victim.team != self.player.team else None)
                return False
            Land(self.game, self.player, penalty=0 if self.superb else -1,
                 auto_fail=self.auto_fail, swoop=self.swoop)
            return True
        return False

    def available_actions(self):
        if self.phase == 'scatter':
            player, skill = (self.thrower, Skill.BULLSEYE) if (
                self.superb and self.thrower.has_usable_skill(Skill.BULLSEYE) and not self.bullseye_checked
            ) else (self.player, Skill.SWOOP)
            if player.has_usable_skill(skill) and (skill == Skill.BULLSEYE or not self.swoop_checked):
                return [ActionChoice(kind, team=player.team, skill=skill)
                        for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        if self.phase == 'swoop':
            positions = [self.game.get_square(self.position.x + dx, self.position.y + dy)
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            return [ActionChoice(ActionType.SELECT_DIRECTION, team=self.player.team, positions=positions)]
        return []


class ThrowBombAction(Procedure):

    def __init__(self, game, player, rethrow=False):
        super().__init__(game)
        self.player = player
        self.rethrow = rethrow
        if not rethrow:
            self.game.put_bomb(Bomb(self.player.position))
        self.can_undo = False

    def start(self):
        if self.rethrow:
            return
        self.game.report(Outcome(OutcomeType.THROW_BOMB_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.THROW_BOMB
        self.can_undo = not self.game.is_season3 and self.game.get_team_agent(self.player.team).human

    def step(self, action):
        if self.game.is_season3 and self.rethrow and self.player.get_pass_target() is None:
            # A compulsory rethrow cannot manufacture a missing PA value. The
            # player cannot throw it, so the bomb is dropped and explodes here.
            bomb = self.game.get_bomb()
            bomb.move_to(self.player.position)
            bomb.is_carried = False
            self.game.report(Outcome(OutcomeType.FUMBLE, player=self.player))
            Explode(self.game, bomb)
            return True
        if action.action_type == ActionType.THROW_BOMB:
            pass_distance = self.game.get_pass_distance(self.player.position, action.position)
            if not self.rethrow:
                EndPlayerTurn(self.game, self.player)
            bomb = self.game.get_bomb()
            if self.game.is_season3:
                bomb.thrower = self.player
                bomb.casualty_credit = self.player.has_usable_skill(Skill.VIOLENT_INNOVATOR)
                Season3PassAttempt(self.game, self.player, bomb, action.position, pass_distance)
            else:
                PassAttempt(self.game, self.player, bomb, action.position, pass_distance)
            return True
        EndPlayerTurn(self.game, self.player)
        return True

    def end(self):
        if not self.rethrow and self.game.get_bomb() is not None:
            self.game.remove_bomb()

    def available_actions(self):
        actions = self.game.get_pass_actions(self.player, self.game.get_bomb())
        if not self.rethrow:
            actions.append(ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team))
        return actions


class FoulAction(MoveAction):

    def __init__(self, game, player):
        super().__init__(game, player, player_action_type=PlayerActionType.FOUL)

    def start(self):
        self.game.use_foul_action()
        self.game.report(Outcome(OutcomeType.FOUL_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.FOUL
        super().start()

    def step(self, action):
        # Continue moving along path
        if action is None:
            player_at = self.game.get_player_at(self.steps[0])
            if player_at is None or (player_at == self.player and not player_at.state.up):
                return super().step(action)
            # Last step is a foul action
            action = Action(ActionType.FOUL, position=self.steps.pop(0))
            self.steps = None

        if action.action_type is ActionType.UNDO:
            self.game.unuse_foul_action()
            return super().step(action)

        self.can_undo = False

        if action.action_type == ActionType.FOUL:
            if self.player.position.distance(action.position) == 1:
                player_to = self.game.get_player_at(action.position)
                if self.game.is_season3 and self.player.has_usable_skill(Skill.QUICK_FOUL):
                    MoveAction(self.game, self.player)
                else:
                    EndPlayerTurn(self.game, self.player)
                Foul(self.game, self.player, player_to)
                return True

        # It's a move action
        return super().step(action)

    def available_actions(self):
        # If MoveAction is following a path -> continue
        if self.steps is not None:
            return []
        # Will include foul actions if pathfinding is enabled
        actions = super().available_actions()
        # Else find them for this square
        if not self.game.config.pathfinding_enabled:
            actions += self.game.get_foul_actions(self.player)
        return actions


class BlockAction(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.can_undo = False

    def start(self):
        self.game.report(Outcome(OutcomeType.BLOCK_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.BLOCK
        self.can_undo = not self.game.is_season3 and self.game.get_team_agent(self.player.team).human

    def step(self, action):

        if action.action_type == ActionType.END_PLAYER_TURN:
            EndPlayerTurn(self.game, self.player)
            return True

        if action.action_type == ActionType.UNDO:
            UndoPlayerAction(self.game, self.player)
            return True

        self.can_undo = False

        if action.action_type == ActionType.USE_SKILL:
            EndPlayerTurn(self.game, self.player)
            MultipleBlock(self.game, self.player)
            if not self.player.state.up:
                JumpUpToBlock(self.game, self.player)
            return True

        defender = self.game.get_player_at(action.position)

        EndPlayerTurn(self.game, self.player)

        # Stab
        if action.action_type == ActionType.STAB:

            Stab(self.game, self.player, defender)

        if action.action_type == ActionType.BLOCK:
            frenzy = None
            if self.player.has_skill(Skill.FRENZY):
                # TODO: Second block can also be a stab?
                frenzy = Block(self.game, self.player, defender, frenzy_block=True)

            # Regular block
            first = Block(self.game, self.player, defender)
            if frenzy is not None:
                frenzy.previous_block = first

        if not self.player.state.up:
            JumpUpToBlock(self.game, self.player)

        return True

    def available_actions(self):
        actions = self.game.get_block_actions(self.player, blitz=False)
        if (self.game.is_season3 and self.player.has_usable_skill(Skill.MULTIPLE_BLOCK, assume_standing=True)
                and len(self.game.get_adjacent_opponents(self.player, down=False)) >= 2):
            actions.append(ActionChoice(ActionType.USE_SKILL, team=self.player.team, skill=Skill.MULTIPLE_BLOCK))
        actions.append(ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team))
        if self.can_undo:
            actions.append(ActionChoice(ActionType.UNDO, team=self.player.team))
        return actions


class BlitzDeclaration(Procedure):
    """Complete the target declaration before any activation trait is rolled."""

    def __init__(self, game, player, turn):
        super().__init__(game)
        self.player = player
        self.turn = turn
        self.targets = game.get_blitz_targets(player)

    def start(self):
        self.game.report(Outcome(OutcomeType.BLITZ_DECLARATION_STARTED, player=self.player))

    def step(self, action):
        self.game.report(Outcome(OutcomeType.BLITZ_TARGET_DECLARED, player=self.player, opp_player=action.player))
        self.turn._start_player_action(Action(ActionType.START_BLITZ, player=self.player), blitz_target=action.player)
        return True

    def available_actions(self):
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.player.team, players=self.targets)]


class BlitzAction(MoveAction):

    def __init__(self, game, player, defender=None):
        super().__init__(game, player, player_action_type=PlayerActionType.BLITZ)
        self.player = player
        self.defender = defender

    def start(self):
        self.game.report(Outcome(OutcomeType.BLITZ_ACTION_STARTED, player=self.player))
        self.game.state.player_action_type = PlayerActionType.BLITZ
        self.game.use_blitz_action()
        super().start()
        if self.game.is_season3:
            self.can_undo = False

    def step(self, action):

        # Continue moving along path
        if action is None:
            player_at = self.game.get_player_at(self.steps[0])
            if player_at is None or (player_at == self.player and not player_at.state.up):
                return super().step(action)
            # Last path step is a block or stab action
            action = Action(self.orig_action_type, position=self.steps.pop(0))
            self.steps = None

        if action.action_type is ActionType.UNDO:
            self.game.unuse_blitz_action()
            return super().step(action)

        self.can_undo = False

        if action.action_type == ActionType.END_PLAYER_TURN:
            EndPlayerTurn(self.game, self.player)
            return True

        special_skill = next((skill for skill, (_, kind) in SEASON3_SPECIAL_ACTIONS.items()
                              if kind == action.action_type and skill != Skill.HYPNOTIC_GAZE), None)
        if action.action_type == ActionType.BLOCK or action.action_type == ActionType.STAB or (
                self.game.is_season3 and special_skill is not None):
            if self.player.position.distance(action.position) == 1:
                defender = self.game.get_player_at(action.position)
                move_needed = 1
                if not self.player.state.up:
                    move_needed += 0 if self.player.has_skill(Skill.JUMP_UP) else 3

                gfi = self.player.num_moves_left() < move_needed
                gfi_frenzy = self.player.num_moves_left() < move_needed + 1
                frenzy_allowed = self.player.num_moves_left(include_gfi=True) >= move_needed + 1

                self.player.state.moves += move_needed

                if action.action_type == ActionType.BLOCK:
                    # Frenzy second block
                    frenzy = None
                    if self.player.has_skill(Skill.FRENZY) and frenzy_allowed:
                        # TODO: Option to block or stab: add second block inside block?
                        frenzy = Block(self.game, self.player, defender, blitz=True, gfi=gfi_frenzy, frenzy_block=True)
                    # Regular block
                    first = Block(self.game, self.player, defender, blitz=True, gfi=gfi)
                    if frenzy is not None:
                        frenzy.previous_block = first
                    if not self.player.state.up:
                        self._stand_up()
                    return False
                elif action.action_type == ActionType.STAB:
                    EndPlayerTurn(self.game, self.player)
                    Stab(self.game, self.player, defender, blitz=True, gfi=gfi)
                    if not self.player.state.up:
                        self._stand_up()
                    return True
                elif self.game.is_season3:
                    EndPlayerTurn(self.game, self.player)
                    SpecialAttack(self.game, self.player, defender, special_skill)
                    self.player.state.has_blocked = True
                    if gfi:
                        GFI(self.game, self.player, self.player.position)
                    if not self.player.state.up:
                        self._stand_up()
                    return True

        # It's a move action
        return super().step(action)

    def available_actions(self):
        # If MoveAction is following a path -> continue
        if self.steps is not None:
            return []
        # Move actions will include block moves if pathfinding is enabled
        actions = super().available_actions()
        # Else find them for this square
        if not self.game.config.pathfinding_enabled:
            actions += self.game.get_block_actions(self.player, blitz=True, target=self.defender)
        elif self.game.is_season3:
            actions += [a for a in self.game.get_block_actions(self.player, blitz=True, target=self.defender)
                        if a.action_type not in (ActionType.BLOCK, ActionType.STAB)]
        return actions


class StartGame(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        for team in self.game.state.teams:
            for player in team.players:
                self.game.get_reserves(team).append(player)
        self.game.start_time = time.time()
        self.game.report(Outcome(OutcomeType.GAME_STARTED))
        return True

    def available_actions(self):
        return [ActionChoice(ActionType.START_GAME, team=self.game.state.away_team)]


class EndGame(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        self.game.state.game_over = True
        winner = self.game.get_winning_team()
        if winner is not None:
            self.game.report(Outcome(OutcomeType.END_OF_GAME_WINNER, team=winner))
        else:
            self.game.report(Outcome(OutcomeType.END_OF_GAME_DRAW))
        return True


class Pregame(Procedure):

    def __init__(self, game):
        super().__init__(game)
        CoinTossFlip(self.game)
        # self.game.state.stack.push(Inducements(self.game, True))
        # self.game.state.stack.push(Inducements(self.game, False))
        # self.game.state.stack.push(GoldToPettyCash(self.game))
        Fans(self.game)
        WeatherTable(self.game)
        StartGame(self.game)

    def step(self, action):
        Half(self.game, 2)
        Half(self.game, 1)
        self.game.state.half = 1
        for team in self.game.state.teams:
            team.state.turn = 0
        return True


class PreKickoff(Procedure):

    def __init__(self, game, team):
        super().__init__(game)
        self.team = team
        self.checked = []

    def step(self, action):
        # Check KOed
        for player in self.game.get_knocked_out(self.team):
            if player not in self.checked:
                roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.KO_READY_ROLL)
                roll.modifiers = self.team.state.babes if self.game.is_season3 else 0
                roll.target = 4
                if roll.get_sum() + roll.modifiers >= 4:
                    self.game.kod_to_reserves(player)
                    self.checked = self.checked + [player]
                    self.game.report(Outcome(OutcomeType.PLAYER_READY, player=player, rolls=[roll]))
                    return False
                self.checked = self.checked + [player]
                self.game.report(Outcome(OutcomeType.PLAYER_NOT_READY, player=player, rolls=[roll]))
                return False
        return True


class StripBall(Procedure):
    """Resolve after Follow-up, but before a pushed player becomes Prone."""

    def __init__(self, game, attacker, defender):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender

    def step(self, action):
        if self.game.has_ball(self.defender):
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.attacker, skill=Skill.STRIP_BALL))
            self.game.report(Outcome(OutcomeType.FUMBLE, player=self.defender, opp_player=self.attacker))
            Bounce(self.game, self.game.get_ball_at(self.defender.position))
        return True


class FollowUp(Procedure):

    def __init__(self, game, attacker, defender, pos_to, blitz=False):
        super().__init__(game)
        self.attacker = attacker
        self.defender = defender
        self.pos_to = pos_to
        self.blitz = blitz
        self.taunt_checked = not (game.is_season3 and defender.has_usable_skill(Skill.TAUNT))
        self.taunt_used = False

    def step(self, action):
        if not self.taunt_checked and self.can_follow_up(self.attacker, self.defender):
            self.taunt_checked = True
            self.taunt_used = action.action_type == ActionType.USE_SKILL
            if self.taunt_used:
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.defender, skill=Skill.TAUNT))
            return False
        if not self.can_follow_up(self.attacker, self.defender):
            if self.attacker.state.taken_root:
                return True
            self.game.report(Outcome(OutcomeType.SKILL_USED, skill=Skill.FEND, player=self.defender))
            self.attacker.state.squares_moved.append(self.attacker.position)
        elif self.must_follow_up(self.attacker) or (action and action.position == self.pos_to):
            shadowers = [] if self.game.is_season3 else self.game.get_adjacent_opponents(self.attacker, down=False, skill=Skill.SHADOWING)
            position = self.attacker.position
            self.game.move(self.attacker, self.pos_to)
            self.attacker.state.squares_moved.append(self.pos_to)
            self.game.report(Outcome(OutcomeType.FOLLOW_UP, position=self.pos_to, player=self.attacker))
            # Touchdown?
            if self.game.has_ball(self.attacker) and self.game.is_touchdown(self.attacker):
                Touchdown(self.game, self.attacker)
                shadowers = None
            # Shadowing
            if shadowers:
                Shadowing(self.game, self.attacker, position, shadowers)
        else:
            self.attacker.state.squares_moved.append(self.attacker.position)
        return True

    def available_actions(self):
        if not self.taunt_checked and self.can_follow_up(self.attacker, self.defender):
            return [ActionChoice(kind, team=self.defender.team, players=[self.defender], skill=Skill.TAUNT)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        if self.must_follow_up(self.attacker) or not self.can_follow_up(self.attacker, self.defender):
            return []
        else:
            return [ActionChoice(ActionType.FOLLOW_UP, team=self.attacker.team,
                                 positions=[self.attacker.position, self.pos_to])]

    def can_follow_up(self, attacker, defender):
        if self.game.is_season3 and self.game.get_proc(MultipleBlock) is not None:
            return False
        fend = defender.has_usable_skill(Skill.FEND)
        if self.game.is_season3 and (attacker.has_skill(Skill.BALL_AND_CHAIN) or
                                    (self.blitz and attacker.has_usable_skill(Skill.JUGGERNAUT))):
            fend = False
        return not fend and not attacker.state.taken_root and (
            not self.game.is_chomped(attacker) or (self.game.is_season3 and attacker.has_skill(Skill.BALL_AND_CHAIN)))

    def must_follow_up(self, attacker):
        return attacker.has_usable_skill(Skill.FRENZY) or self.taunt_used or (
            self.game.is_season3 and attacker.has_usable_skill(Skill.BALL_AND_CHAIN))


class Push(Procedure):

    def __init__(self, game, pusher, player, knock_down=False, blitz=False, chain=False, block_context=None):
        super().__init__(game)
        assert pusher != player
        self.pusher = pusher
        self.block_context = block_context
        self.pusher_position = block_context.origin if block_context is not None else pusher.position
        self.player = player
        self.knock_down = knock_down
        self.blitz = blitz
        self.waiting_stand_firm = False
        self.stand_firm_used = False
        self.chain = chain
        self.waiting_for_move = False
        self.player_chain = None
        self.push_to = None
        self.follow_to = None
        self.squares = None
        self.selector = game.get_active_player()
        self.crowd = False
        self.crowd_turnover = False
        self.strip_ball_condition = self.pusher_skill(Skill.STRIP_BALL) and not self.player.has_usable_skill(Skill.SURE_HANDS) and (game.is_season3 or not self.knock_down) and not self.chain and self.game.has_ball(self.player)
        if game.is_season3 and self.player.has_usable_skill(Skill.MONSTROUS_MOUTH):
            self.strip_ball_condition = False

    def pusher_skill(self, skill):
        return (self.block_context.skill_available(self.pusher, skill) if self.block_context is not None
                else self.pusher.has_usable_skill(skill))

    def resolve_knockdown(self, player, **kwargs):
        if self.block_context is not None and not self.chain:
            self.block_context.knock_down(player, **kwargs)
        else:
            KnockDown(self.game, player, **kwargs)
        
    def step(self, action):

        # When proceeding pushes are over, move player(s)
        if self.waiting_for_move:

            # Stop secondary clocks
            self.game.remove_secondary_clocks()

            # A later player may refuse the chain push with Stand Firm, Take
            # Root or Chomp. Propagate the blocked movement up the chain while
            # still applying the original block's knockdown in place.
            if self.game.get_player_at(self.push_to) is not None:
                if self.knock_down:
                    self.resolve_knockdown(self.player, in_crowd=False, armor_roll=True,
                                           inflictor=self.pusher if self.game.is_season3 and not self.chain else None,
                                           block=not self.chain,
                                           turnover=self.game.is_season3 and self.player.team == self.game.state.current_team)
                return True

            # Move pushed player
            self.game.move(self.player, self.push_to)
            if self.game.is_season3:
                self.game.report(Outcome(OutcomeType.PUSHED_INTO_CROWD if self.crowd else OutcomeType.PUSHED,
                                         player=self.player, position=None if self.crowd else self.push_to))
            if self.game.is_season3 and not self.chain and self.pusher_skill(Skill.EYE_GOUGE):
                self.player.state.eye_gouged = True
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.pusher, skill=Skill.EYE_GOUGE))

            # A friendly player surfed by a chain push ends the active team's
            # turn even without the ball. Finish the entire push, injury and
            # ball resolution before ending the turn.
            if self.game.is_season3 and self.crowd_turnover:
                Turnover(self.game)

            # Ball
            if self.game.has_ball(self.player):
                if self.player.position.out_of_bounds:
                    ball = self.game.get_ball_at(self.player.position)
                    ThrowIn(self.game, ball, position=self.follow_to)
                elif self.strip_ball_condition and not self.game.is_season3:
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.pusher, skill=Skill.STRIP_BALL))
                    self.game.report(Outcome(OutcomeType.FUMBLE, player=self.player, opp_player=self.pusher))
                    Bounce(self.game, self.game.get_ball_at(self.player.position) )
                elif self.game.is_touchdown(self.player) and not (self.game.is_season3 and self.knock_down):
                    Touchdown(self.game, self.player)
                    
            elif self.game.get_ball_at(self.push_to) is not None:
                Bounce(self.game, self.game.get_ball_at(self.push_to))

            # Knock down
            if self.knock_down or self.crowd:
                self.resolve_knockdown(self.player, in_crowd=self.crowd, armor_roll=not self.crowd,
                          inflictor=self.pusher if self.game.is_season3 and not self.chain else None,
                          block=not self.chain,
                          turnover=self.game.is_season3 and self.player.team == self.game.state.current_team)

            if self.game.is_season3 and self.strip_ball_condition and not self.crowd:
                StripBall(self.game, self.pusher, self.player)

            # Follow up
            if not self.chain:
                FollowUp(self.game, self.pusher, self.player, self.follow_to, blitz=self.blitz)

            return True

        # Taken root players cannot be pushed
        if self.player.state.taken_root or self.game.is_chomped(self.player):
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.TAKE_ROOT))
            if self.knock_down:
                self.resolve_knockdown(self.player, in_crowd=False, armor_roll=True,
                          inflictor=self.pusher if self.game.is_season3 and not self.chain else None,
                          block=not self.chain,
                          turnover=self.game.is_season3 and self.player.team == self.game.state.current_team)
            elif self.strip_ball_condition and not self.game.is_season3:
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.pusher, skill=Skill.STRIP_BALL))
                self.game.report(Outcome(OutcomeType.FUMBLE, player=self.player, opp_player=self.pusher))
                Bounce(self.game, self.game.get_ball_at(self.player.position) )
            return True

        # Use stand firm
        if self.waiting_stand_firm:
            if action.action_type == ActionType.USE_SKILL:
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.STAND_FIRM))
                if self.knock_down:
                    self.resolve_knockdown(self.player, in_crowd=False, armor_roll=True,
                              inflictor=self.pusher if self.game.is_season3 and not self.chain else None,
                              block=not self.chain,
                              turnover=self.game.is_season3 and self.player.team == self.game.state.current_team)
                elif self.strip_ball_condition and not self.game.is_season3:
                    self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.pusher, skill=Skill.STRIP_BALL))
                    self.game.report(Outcome(OutcomeType.FUMBLE, player=self.player, opp_player=self.pusher))
                    Bounce(self.game, self.game.get_ball_at(self.player.position) )
                return True
            else:
                self.waiting_stand_firm = False
                self.stand_firm_used = True

        # Stand firm
        if self.player.has_usable_skill(Skill.STAND_FIRM) and not self.stand_firm_used:
            if self.pusher_skill(Skill.JUGGERNAUT) and self.blitz:
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.pusher, skill=Skill.JUGGERNAUT))
            else:
                self.waiting_stand_firm = True
                return False

        # Get possible squares
        if self.squares is None:
            # Sidestep and grab cancels out eachother - otherwise let the grabber or sidestepper select adjacent square
            if self.player.has_usable_skill(Skill.SIDE_STEP) and (self.chain or not self.pusher_skill(Skill.GRAB)):
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.SIDE_STEP))
                self.squares = self.game.get_adjacent_squares(self.player.position, occupied=False)
                self.selector = self.player
                if len(self.squares) > 0:
                    if self.player.team != self.game.state.current_team:
                        self.game.add_secondary_clock(self.player.team)
            elif not self.chain and self.pusher_skill(Skill.GRAB) and (
                    (self.game.is_season3 and not self.blitz) or
                    (not self.game.is_season3 and not self.player.has_skill(Skill.SIDE_STEP))):
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.GRAB))
                self.squares = self.game.get_adjacent_squares(self.player.position, occupied=False)
            # If no free squares
            if self.squares is None or len(self.squares) == 0:
                self.selector = self.pusher
                self.squares = self.game.get_push_squares(self.pusher_position, self.player.position,
                                                        ignore_skills=self.game.is_season3)
            return False

        if action.action_type == ActionType.PUSH:

            # Push to crowd?
            self.crowd = self.game.is_out_of_bounds(action.position)

            # Report
            if self.crowd:
                if not self.game.is_season3:
                    self.game.report(Outcome(OutcomeType.PUSHED_INTO_CROWD, player=self.player))
                if self.game.is_season3 and self.player.team == self.game.state.current_team:
                    root_push = next(p for p in self.game.state.stack.items if isinstance(p, Push))
                    root_push.crowd_turnover = True
            elif not self.game.is_season3:
                self.game.report(Outcome(OutcomeType.PUSHED, player=self.player, position=action.position))

            # Follow up - wait if push is delayed
            player_at = self.game.get_player_at(action.position)

            # Move players in next step - after chaining
            self.waiting_for_move = True
            self.squares = None

            # Save positions before chaining
            self.push_to = action.position
            self.follow_to = self.player.position

            assert self.push_to != self.follow_to

            # Chain push
            if player_at is not None:
                self.player_chain = player_at
                Push(self.game, self.player, self.player_chain, knock_down=False, chain=True)

            return False

        raise Exception("Unknown push sequence")

    def available_actions(self):
        actions = []
        if self.squares is not None:
            actions.append(ActionChoice(ActionType.PUSH, team=self.selector.team, positions=self.squares))
        elif self.waiting_stand_firm:
            actions.append(ActionChoice(ActionType.USE_SKILL, skill=Skill.STAND_FIRM, team=self.player.team, players=[self.player]))
            actions.append(ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.STAND_FIRM, team=self.player.team, players=[self.player]))
        return actions


class Scatter(Procedure):

    def __init__(self, game, piece, kick=False, is_pass=False, gentle_gust=False, defer_landing=False, kicker=None):
        super().__init__(game)
        self.piece = piece
        self.kick = kick
        self.is_pass = is_pass
        self.gentle_gust = gentle_gust
        self.defer_landing = defer_landing
        self.throw_in_position = None
        self.kicker = kicker
        self.kick_choice = not (game.is_season3 and kick and not gentle_gust and kicker is not None
                                and kicker.has_usable_skill(Skill.KICK))
        self.kick_d3 = False

    def step(self, action):
        if not self.kick_choice:
            self.kick_choice = True
            self.kick_d3 = action.action_type == ActionType.USE_SKILL

        # Don't scatter if ball is out
        if self.game.is_out_of_bounds(self.piece.position):
            return True

        n = 3 if self.is_pass else 1
        rolls = [DiceRoll([D8(self.game.rng)], roll_type=RollType.SCATTER_ROLL) for _ in range(n)]

        for s in range(n):

            # Scatter Roll
            scatter_roll = rolls[s]
            x = 0
            y = 0
            if scatter_roll.get_sum() in [1, 4, 6]:
                x = -1
            if scatter_roll.get_sum() in [3, 5, 8]:
                x = 1
            if scatter_roll.get_sum() in [1, 2, 3]:
                y = -1
            if scatter_roll.get_sum() in [6, 7, 8]:
                y = 1

            # Distance Roll
            distance = 1
            if self.kick and not self.gentle_gust:
                # D2 is a special dice with sides 0 and 1
                if self.kick_d3:
                    distance_roll = DiceRoll([D3(self.game.rng)], roll_type=RollType.DISTANCE_ROLL)
                    d2 = False
                elif self.game.config.kick_scatter_dice == 'd2':
                    distance_roll = DiceRoll.from_string('d6', rng=self.game.rng)
                    d2 = True
                else:
                    distance_roll = DiceRoll.from_string(self.game.config.kick_scatter_dice, rng=self.game.rng)
                    d2 = False
                distance_roll.roll_type = RollType.DISTANCE_ROLL
                rolls += [distance_roll]
                distance = distance_roll.get_sum()
                if d2:
                    distance = int((distance - 1) / 6)

            for i in range(distance):
                # Move ball on square
                self.game.shove(self.piece, x, y)

                if self.kick and i == 0 and not self.gentle_gust:
                    self.game.report(Outcome(OutcomeType.BALL_SCATTER, rolls=rolls))

                # Check out of bounds
                if self.kick:
                    if self.game.is_out_of_bounds(self.piece.position):
                        if self.gentle_gust:
                            # Touchback will be enforced after kick-off table when ball lands
                            self.game.report(Outcome(OutcomeType.GENTLE_GUST_OUT_OF_BOUNDS, position=self.piece.position,
                                                     rolls=rolls))
                        else:
                            # Touchback will be enforced after kick-off table when ball lands
                            self.game.report(Outcome(OutcomeType.KICK_OUT_OF_BOUNDS, position=self.piece.position,
                                                     rolls=rolls))
                        return True
                    elif self.game.is_team_side(self.piece.position, self.game.get_kicking_team()):
                        if self.gentle_gust:
                            # Touchback will be enforced after kick-off table when ball lands
                            self.game.report(Outcome(OutcomeType.GENTLE_GUST_OPP_HALF, position=self.piece.position,
                                                     rolls=rolls))
                        else:
                            # Touchback will be enforced after kick-off table when ball lands
                            self.game.report(Outcome(OutcomeType.KICK_OPP_HALF, position=self.piece.position, rolls=rolls))
                        return True
                else:
                    # Throw in
                    if self.game.is_out_of_bounds(self.piece.position):
                        if type(self.piece) is Ball:
                            self.throw_in_position = self.game.get_square(self.piece.position.x-x, self.piece.position.y-y)
                            if not self.defer_landing:
                                ThrowIn(self.game, self.piece, self.throw_in_position)
                            self.game.report(Outcome(OutcomeType.BALL_SCATTER, rolls=rolls))
                            self.game.report(Outcome(OutcomeType.BALL_OUT_OF_BOUNDS,
                                                     position=self.piece.position))
                        elif type(self.piece) is Player:
                            KnockDown(self.game, self.piece, in_crowd=True, armor_roll=False)
                            self.game.report(Outcome(OutcomeType.PLAYER_OUT_OF_BOUNDS, player=self.piece, rolls=rolls))
                        elif type(self.piece) is Bomb:
                            self.game.report(Outcome(OutcomeType.BOMB_OUT_OF_BOUNDS, rolls=rolls))
                            self.game.remove_bomb()
                        return True

                    # Passes are scattered three times
                    if self.is_pass and s < n-1:
                        continue

                    if type(self.piece) is Ball:
                        self.game.report(Outcome(OutcomeType.BALL_SCATTER, rolls=rolls))
                    elif type(self.piece) is Bomb:
                        self.game.report(Outcome(OutcomeType.BOMB_SCATTER, rolls=rolls))
                    elif type(self.piece) is Player:
                        self.game.report(Outcome(OutcomeType.PLAYER_SCATTER, player=self.piece, rolls=rolls))

                    if self.defer_landing:
                        return True

                    # On player -> Catch
                    player_at = self.game.get_player_at(self.piece.position)
                    catcher = self.game.get_catcher(self.piece.position)

                    if type(self.piece) is Player and player_at is not None:
                        self.game.report(Outcome(OutcomeType.PLAYER_HIT_PLAYER, position=self.piece.position,
                                                 player=player_at, rolls=[scatter_roll]))
                        Bounce(self.game, self.piece)
                        KnockDown(self.game, player=player_at, inflictor=self.piece)
                        if self.piece.team == player_at.team:
                            self.game.get_proc(PassAttempt).turnover = True  # Will cause a turnover after pass attempt
                        return True
                    if catcher is not None and self.piece.is_catchable():
                        Catch(self.game, catcher, self.piece)
                        self.game.report(Outcome(OutcomeType.BALL_HIT_PLAYER, position=self.piece.position,
                                                 player=catcher, rolls=[scatter_roll]))
                        return True

        if self.kick:
            if self.gentle_gust:
                # Wait for ball to land
                self.game.report(Outcome(OutcomeType.GENTLE_GUST_IN_BOUNDS, position=self.piece.position,
                                         rolls=[scatter_roll]))
            else:
                # Wait for ball to land
                self.game.report(Outcome(OutcomeType.KICK_IN_BOUNDS, position=self.piece.position,
                                         rolls=[scatter_roll, distance_roll]))
        elif type(self.piece) is Player:
            Land(self.game, player=self.piece)
        elif type(self.piece) is Bomb:
            Explode(self.game, self.piece)
        else:
            Bounce(self.game, self.piece)
        return True


    def available_actions(self):
        if not self.kick_choice:
            return [ActionChoice(kind, team=self.kicker.team, skill=Skill.KICK)
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        return []


class ClearBoard(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        self.game.state.pitch.balls.clear()
        if self.game.is_season3:
            for team in self.game.state.teams:
                for player in list(self.game.get_players_on_pitch(team)):
                    player.state.reset()
                    self.game.pitch_to_reserves(player)
                for player in self.game.get_reserves(team):
                    heated = player.state.heated
                    player.state.reset()
                    player.state.heated = heated
            return True
        for team in self.game.state.teams:
            for player in team.players:
                # If player not in reserves. move it to it
                if player.position is not None:
                    # Set to ready
                    player.state.reset()
                    player.state.up = True
                    # Remove from pitch
                    self.game.pitch_to_reserves(player)
                    # Check if heat exhausted
                    if self.game.state.weather == WeatherType.SWELTERING_HEAT:
                        roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.SWELTERING_HEAT_ROLL)
                        if roll.get_sum() == 1:
                            player.state.heated = True
                            self.game.report(Outcome(OutcomeType.PLAYER_HEATED, player=player, rolls=[roll]))
                        else:
                            self.game.report(Outcome(OutcomeType.PLAYER_NOT_HEATED, player=player, rolls=[roll]))
        return True


class Setup(Procedure):

    def __init__(self, game, team, reorganize=False):
        super().__init__(game)
        self.team = team
        self.reorganize = reorganize
        self.selected_player = None
        self.formations = game.config.defensive_formations if team == game.get_kicking_team() \
            else game.config.offensive_formations
        self.aa = []

    def start(self):
        # Set current team
        self.game.state.current_team = self.team
        # Add clock
        self.game.add_primary_clock(self.team)

    def step(self, action):
        formation = None
        if action.action_type == ActionType.SETUP_FORMATION_WEDGE:
            formation = [formation for formation in self.formations if formation.name == "Wedge"][0]
        if action.action_type == ActionType.SETUP_FORMATION_ZONE:
            formation = [formation for formation in self.formations if formation.name == "Zone"][0]
        if action.action_type == ActionType.SETUP_FORMATION_LINE:
            formation = [formation for formation in self.formations if formation.name == "Line"][0]
        if action.action_type == ActionType.SETUP_FORMATION_SPREAD:
            formation = [formation for formation in self.formations if formation.name == "Spread"][0]

        if formation is not None:
            actions = formation.actions(self.game, self.team)
            for a in actions:
                self.step(a)
            return False

        if action.action_type == ActionType.END_SETUP:
            if not self.game.is_setup_legal_count(self.team, max_players=self.game.config.pitch_max,
                                            min_players=self.game.config.pitch_min):
                self.game.report(Outcome(OutcomeType.ILLEGAL_SETUP_NUM, team=self.team))
                return False
            elif not self.game.is_setup_legal_scrimmage(self.team, min_players=self.game.config.scrimmage_min):
                self.game.report(Outcome(OutcomeType.ILLEGAL_SETUP_SCRIMMAGE, team=self.team))
                return False
            elif not self.game.is_setup_legal_wings(self.team, max_players=self.game.config.wing_max):
                self.game.report(Outcome(OutcomeType.ILLEGAL_SETUP_WINGS, team=self.team))
                return False
            self.game.state.current_team = None
            self.game.remove_clocks()
            self.game.report(Outcome(OutcomeType.SETUP_DONE, team=self.team))
            return True

        if action.action_type == ActionType.PLACE_PLAYER:
            if action.position is None:
                if action.player.position is not None:
                    self.game.pitch_to_reserves(action.player)
                else:
                    print("Ignoring PLACE_PLAYER action: Already in reserves")
            elif action.player.position is None:
                if action.position is not None:
                    self.game.reserves_to_pitch(action.player, action.position)
                else:
                    print("Ignoring PLACE_PLAYER action: Already in reserves")
            else:
                player_at = self.game.get_player_at(action.position)
                if player_at is not None:
                    self.game.swap(action.player, player_at)
                else:
                    self.game.move(action.player, action.position)
            self.game.report(Outcome(OutcomeType.PLAYER_PLACED, position=action.position, player=action.player))
            return False

    def available_actions(self):
        # Set actions
        if self.reorganize:
            positions = self.game.get_team_side(self.team)
        else:
            positions = self.game.get_team_side(self.team) + [None]

        players = self.game.get_players_on_pitch(self.team)
        if not self.reorganize:
            players += self.game.get_reserves(self.team)
        if self.game.is_season3:
            players = [p for p in players if not p.state.heated and not p.state.snack_absent]
        aa = [
            ActionChoice(ActionType.PLACE_PLAYER, team=self.team,
                         players=players,
                         positions=positions),
            ActionChoice(ActionType.END_SETUP, team=self.team)
        ]

        for formation in self.formations:
            if formation.name == "Wedge":
                aa.append(ActionChoice(ActionType.SETUP_FORMATION_WEDGE, team=self.team))
            if formation.name == "Line":
                aa.append(ActionChoice(ActionType.SETUP_FORMATION_LINE, team=self.team))
            if formation.name == "Spread":
                aa.append(ActionChoice(ActionType.SETUP_FORMATION_SPREAD, team=self.team))
            if formation.name == "Zone":
                aa.append(ActionChoice(ActionType.SETUP_FORMATION_ZONE, team=self.team))

        return aa


class ThrowIn(Procedure):

    def __init__(self, game, ball, position):
        super().__init__(game)
        self.ball = ball
        self.position = position

    def step(self, action):

        punt = self.game.get_proc(Punt)
        if self.game.is_season3 and punt is not None and punt.ball is self.ball:
            punt.out = True

        # Move ball to throw-in position
        self.ball.move_to(self.position)
        if self.game.is_season3:
            self.ball.is_carried = False
        else:
            self.ball.carried = False

        # Roll
        corner = (self.position.x in (1, self.game.arena.width - 2) and
                  self.position.y in (1, self.game.arena.height - 2))
        direction_die = D6 if self.game.is_season3 and not corner else D3
        roll_direction = DiceRoll([direction_die(self.game.rng)], roll_type=RollType.SCATTER_ROLL)
        direction = ((roll_direction.get_sum() + 1) // 2 if direction_die is D6
                     else roll_direction.get_sum())
        roll_distance = DiceRoll.from_string(self.game.config.throw_in_dice, rng=self.game.rng)
        roll_distance.roll_type = RollType.DISTANCE_ROLL

        # Scatter
        x = 0
        y = 0

        if self.ball.position.y == 1 and self.ball.position.x == 1:  # Top left corner
            y = 0 if direction == 1 else 1
            x = 0 if direction == 3 else 1
        elif self.ball.position.y == 1 and self.ball.position.x == len(self.game.arena.board[0])-2:  # Top right corner
            y = 0 if direction == 3 else 1
            x = 0 if direction == 1 else -1
        elif self.ball.position.y == len(self.game.arena.board)-2 and self.ball.position.x == len(self.game.arena.board[0])-2:  # Bottom right corner
            y = 0 if direction == 1 else -1
            x = 0 if direction == 3 else -1
        elif self.ball.position.y == len(self.game.arena.board)-2 and self.ball.position.x == 1:  # Bottom left corner
            y = 0 if direction == 3 else -1
            x = 0 if direction == 1 else 1
        elif self.ball.position.y == 1:  # Above
            y = 1
            x = 2 - direction
        elif self.ball.position.y == len(self.game.arena.board)-2:  # Below
            y = -1
            x = -2 + direction
        elif self.ball.position.x == 1:  # Right
            x = 1
            y = -2 + direction
        elif self.ball.position.x == len(self.game.arena.board[0])-2:  # Left
            x = -1
            y = 2 - direction

        # Season 3 counts the last on-pitch square itself as square one.
        distance = roll_distance.get_sum() - int(self.game.is_season3)
        for i in range(distance):
            self.ball.move(x, y)
            if self.game.is_out_of_bounds(self.ball.position):
                ThrowIn(self.game, self.ball, self.game.get_square(self.ball.position.x - x, self.ball.position.y - y))
                self.game.report(Outcome(OutcomeType.THROW_IN_OUT_OF_BOUNDS, position=self.ball.position,
                                         rolls=[roll_direction, roll_distance]))
                return True

        self.game.report(Outcome(OutcomeType.THROW_IN, position=self.ball.position, rolls=[roll_direction,  roll_distance]))

        # On player -> Catch
        catcher = self.game.get_catcher(self.ball.position)
        if catcher is not None:
            Catch(self.game, catcher, self.ball)
        else:
            Bounce(self.game, self.ball)

        return True


class Turnover(Procedure):

    def __init__(self, game):
        super().__init__(game)

    def step(self, action):
        if self.game.is_season3:
            for proc in reversed(self.game.state.stack.items):
                if isinstance(proc, OnTheBallReaction) and not proc.done:
                    proc.failed = True
                    return True
                if isinstance(proc, MultipleBlock) and not proc.done:
                    proc.turnover = True
                    return True
                if isinstance(proc, BlockResolution) and not proc.done:
                    proc.turnover = True
                    return True
        self.game.report(Outcome(OutcomeType.TURNOVER, team=self.game.state.current_team))
        self.game.state.active_player = None
        EndTurn(self.game)
        return True


class BlockResolution(Procedure):
    """Resolve mandatory block effects before scoring or ending the turn."""

    def __init__(self, game):
        super().__init__(game)
        self.scorers = ()
        self.turnover = False

    def step(self, action):
        for player in self.scorers:
            if self.game.is_touchdown(player):
                Touchdown(self.game, player)
                return True
        if self.turnover:
            Turnover(self.game)
        return True


class Touchdown(Procedure):

    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.handle_bloodlust = False 
        self.eat_thrall = None 
        
    def start(self): 
        self.handle_bloodlust = self.player == self.game.get_active_player() and self.player.state.blood_lust 

    def step(self, action):
        if self.game.is_season3:
            for proc in reversed(self.game.state.stack.items):
                if isinstance(proc, (BlockResolution, MultipleBlock)) and not proc.done:
                    if self.player not in proc.scorers:
                        proc.scorers += (self.player,)
                    return True
        if self.handle_bloodlust: 
                
            if self.eat_thrall is None: 
                self.eat_thrall = EatThrall(self.game, self.player)
                return None 
            
            if self.eat_thrall.failed: 
                return True 
        
        self.game.report(Outcome(OutcomeType.TOUCHDOWN, team=self.player.team, player=self.player))
        self.player.team.state.score += 1
        if self.game.is_season3 and self.player.team != self.game.state.current_team:
            if self.player.team.state.turn < self.game.config.rounds:
                self.player.team.state.turn += 1
                self.player.team.state.cheering_fans = False
                self.game.report(Outcome(OutcomeType.TURN_SKIPPED, team=self.player.team))
            for proc in self.game.state.stack.items:
                if isinstance(proc, Half) and proc.half == self.game.state.half:
                    proc.next_team = self.game.state.current_team
        self.game.state.kicking_this_drive = self.player.team
        self.game.state.receiving_this_drive = self.game.get_opp_team(self.player.team)
        EndTurn(self.game, kickoff=True)

        return True


class TurnStunned(Procedure):

    def __init__(self, game, team):
        super().__init__(game)
        self.team = team

    def step(self, action):
        for player in self.team.players:
            if player.state.stunned:
                player.state.stunned = False
                player.state.used = True
        self.game.report(Outcome(OutcomeType.STUNNED_TURNED))
        return True


class EndTurn(Procedure):

    def __init__(self, game, kickoff=False):
        super().__init__(game)
        self.kickoff = kickoff
        self.pick_me_up_checked = False

    def step(self, action):
        if self.game.is_season3 and not self.pick_me_up_checked:
            self.pick_me_up_checked = True
            if self.game.state.current_team is not None:
                PickMeUp(self.game, self.game.get_opp_team(self.game.state.current_team))
                return False

        # Remove all procs in the current turn - including the current turn proc.
        # In rare cases there is no Turn proc yet - e.g. during a kickoff
        turn = self.game.get_current_turn_proc()
        if turn is not None:
            if self.game.is_season3:
                if not turn.blitz and not turn.quick_snap:
                    turn.team.state.cheering_fans = False
                recovered = False
                for player in turn.stunned_at_start:
                    if player.state.stunned:
                        player.state.stunned = False
                        recovered = True
                if recovered:
                    self.game.report(Outcome(OutcomeType.STUNNED_TURNED, team=turn.team))
            self.game.purge_stack_until(Turn, inclusive=True)

        # Reset turn
        if self.game.state.current_team is not None:
            self.game.state.current_team.state.reset_turn()
            for player in self.game.state.current_team.players:
                player.state.reset_turn()

        # Add kickoff procedure - if there are more turns left
        if self.game.is_season3 and self.kickoff:
            if any(t.state.turn < self.game.config.rounds for t in self.game.state.teams):
                StartDrive(self.game)
            EndDrive(self.game)
        elif not self.game.is_season3 and self.kickoff and self.game.get_opp_team(self.game.state.current_team).state.turn < self.game.config.rounds:
            Kickoff(self.game)

            # Setup in turn order from after scoring team
            #self.game.set_turn_order_after(self.game.state.current_team)

            Setup(self.game, self.game.state.receiving_this_drive)
            Setup(self.game, self.game.state.kicking_this_drive)

            for team in self.game.state.teams:
                PreKickoff(self.game, team)

            ClearBoard(self.game)

        self.game.state.current_team = None
        self.game.remove_clocks()
        self.game.state.rerolled_procs.clear()
        self.game.state.player_action_type = None
        return True


class PickMeUp(Procedure):
    def __init__(self, game, team):
        super().__init__(game)
        self.team = team
        helpers = [p for p in game.get_players_on_pitch(team) if p.has_usable_skill(Skill.PICK_ME_UP)]
        self.players = [p for p in game.get_players_on_pitch(team) if not p.state.up and not p.state.stunned
                        and any(p.position.distance(helper.position) <= 3 for helper in helpers)]

    def step(self, action):
        for player in self.players:
            roll = DiceRoll([D6(self.game.rng)], target=5)
            if roll.is_d6_success():
                player.state.up = True
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=player,
                                     skill=Skill.PICK_ME_UP, rolls=[roll]))
        return True


class Turn(Procedure):

    def __init__(self, game, team, half, turn, blitz=False, quick_snap=False):
        super().__init__(game)
        self.team = team
        self.half = half
        self.turn = turn
        self.blitz = blitz
        self.quick_snap = quick_snap
        self.blitz_available = not quick_snap
        self.pass_available = not quick_snap
        self.handoff_available = not quick_snap
        self.foul_available = not quick_snap
        self.throw_team_mate_available = not quick_snap and not blitz
        self.kick_team_mate_available = not quick_snap and not blitz
        self.bomb_available = not quick_snap and not blitz
        self.punt_available = not quick_snap and not blitz
        self.secure_ball_available = game.is_season3 and not quick_snap and not blitz
        self.stunned_at_start = []
        self.kickoff_players = None
        if game.is_season3 and (blitz or quick_snap):
            self.pass_available = self.handoff_available = self.foul_available = False

    def start(self):
        self.game.state.current_team = self.team
        if self.game.is_season3:
            for team in self.game.state.teams:
                for player in team.players:
                    player.state.shadowing_uses = 0
        self.game.add_primary_clock(self.team)
        if self.blitz:
            self.game.report(Outcome(OutcomeType.CHARGE_START if self.game.is_season3 else OutcomeType.BLITZ_START, team=self.team))
        elif self.quick_snap:
            self.game.report(Outcome(OutcomeType.QUICK_SNAP_START, team=self.team))
        else:
            self.game.report(Outcome(OutcomeType.TURN_START, team=self.team, n=self.turn))
            self.team.state.turn = self.turn
            if self.game.is_season3:
                self.stunned_at_start = [p for p in self.team.players if p.state.stunned]
            else:
                TurnStunned(self.game, self.team)
        if self.game.is_season3 and (self.blitz or self.quick_snap):
            KickoffSelection(self.game, self)

    def step(self, action):

        # Handle End Turn action
        if action.action_type == ActionType.END_TURN:
            if self.blitz:
                self.game.report(Outcome(OutcomeType.END_OF_CHARGE if self.game.is_season3 else OutcomeType.END_OF_BLITZ, team=self.team))
            elif self.quick_snap:
                self.game.report(Outcome(OutcomeType.END_OF_QUICK_SNAP, team=self.team))
            else:
                self.game.report(Outcome(OutcomeType.END_OF_TURN, team=self.team))
            self.game.state.active_player = None
            EndTurn(self.game)
            
            return True

        if self.game.is_season3 and action.action_type == ActionType.FOREGO_ACTIVATION:
            action.player.state.could_score_at_activation = self.game.can_score_without_dice(action.player)
            self.game.report(Outcome(OutcomeType.FOREGO_ACTIVATION, player=action.player))
            EndPlayerTurn(self.game, action.player, foregone=True)
            return False

        if self.game.is_season3 and action.action_type == ActionType.START_BLITZ:
            # May 2026 FAQ: clear Distracted before the action declaration,
            # including its target-selection decision, rather than afterwards.
            action.player.state.distracted = False
            action.player.state.hypnotized = False
            self.blitz_available = False
            BlitzDeclaration(self.game, action.player, self)
            return False
        return self._start_player_action(action)

    def _start_player_action(self, action, blitz_target=None):
        if self.game.is_season3 and self.quick_snap:
            self.game.state.active_player = action.player
            QuickSnapMove(self.game, action.player)
            return False
        if self.game.is_season3:
            action.player.state.could_score_at_activation = (
                not self.quick_snap and not self.blitz and self.game.can_score_without_dice(action.player))
        action.player.state.hypnotized = False
        if self.game.is_season3:
            action.player.state.distracted = False
            action.player.state.bone_headed = False
            action.player.state.really_stupid = False
            if action.action_type == ActionType.START_PASS:
                self.pass_available = False
            if action.action_type == ActionType.START_HANDOFF:
                self.handoff_available = False
            if action.action_type == ActionType.START_FOUL:
                self.foul_available = False

        self.game.state.active_player = action.player
            
        # Start movement action
        if self.game.is_season3:
            for skill, (declaration, _) in SEASON3_SPECIAL_ACTIONS.items():
                if action.action_type == declaration:
                    SpecialAction(self.game, action.player, skill)

        if action.action_type == ActionType.START_MOVE:
            MoveAction(self.game, action.player)

        if action.action_type == ActionType.START_BALL_AND_CHAIN:
            BallAndChainAction(self.game, action.player)

        if action.action_type == ActionType.START_SECURE_BALL:
            # Spend at declaration, even if a pre-action trait ends activation.
            self.secure_ball_available = False
            SecureBallAction(self.game, action.player)

        # Start blitz action
        if action.action_type == ActionType.START_BLITZ:
            BlitzAction(self.game, action.player, defender=blitz_target)

        # Start foul action
        if action.action_type == ActionType.START_FOUL:
            FoulAction(self.game, action.player)

        # Start block action
        if action.action_type == ActionType.START_BLOCK:
            BlockAction(self.game, action.player)

        # Start pass action
        if action.action_type == ActionType.START_PASS:
            PassAction(self.game, action.player)

        if action.action_type == ActionType.START_THROW_TEAM_MATE:
            self.throw_team_mate_available = False
            ThrowTeamMateAction(self.game, action.player)

        if action.action_type == ActionType.START_KICK_TEAM_MATE:
            self.kick_team_mate_available = False
            ThrowTeamMateAction(self.game, action.player, kick=True)

        if action.action_type == ActionType.START_PUNT:
            self.punt_available = False
            PuntAction(self.game, action.player)

        # Start handoff action
        if action.action_type == ActionType.START_HANDOFF:
            HandoffAction(self.game, action.player)

        # Start handoff action
        if action.action_type == ActionType.START_THROW_BOMB:
            self.bomb_available = False
            ThrowBombAction(self.game, action.player)

        if action.player.has_skill(Skill.BONE_HEAD):
            Bonehead(self.game, action.player)
        if action.player.has_skill(Skill.REALLY_STUPID):
            ReallyStupid(self.game, action.player)
        if action.player.has_skill(Skill.WILD_ANIMAL):
            WildAnimal(self.game, action.player, is_block_or_blitz=action.action_type == ActionType.START_BLOCK or action.action_type == ActionType.START_BLITZ)
        if self.game.is_season3 and action.player.has_skill(Skill.UNCHANNELLED_FURY):
            fury = WildAnimal(self.game, action.player, is_block_or_blitz=action.action_type in
                              (ActionType.START_BLOCK, ActionType.START_BLITZ))
            fury.skill = Skill.UNCHANNELLED_FURY
        if self.game.is_season3 and action.player.has_skill(Skill.ANIMAL_SAVAGERY):
            AnimalSavagery(self.game, action.player, is_block_or_blitz=action.action_type in
                           (ActionType.START_BLOCK, ActionType.START_BLITZ))
        if action.player.has_skill(Skill.TAKE_ROOT) and not action.player.state.taken_root and (
                not self.game.is_season3 or action.player.state.up):
            TakeRoot(self.game, action.player)
        if action.player.has_skill(Skill.BLOOD_LUST):
            BloodLust(self.game, action.player, is_block=action.action_type == ActionType.START_BLOCK,
                      declared_action=action.action_type)

        return False

    def available_actions(self):
        move_players = []
        block_players = []
        blitz_players = []
        pass_players = []
        handoff_players = []
        foul_players = []
        bomb_players = []
        forego_players = []
        for player in self.game.get_players_on_pitch(self.team):
            if self.kickoff_players is not None and player not in self.kickoff_players:
                continue
            if self.game.is_season3 and player.state.stunned:
                continue
            if self.blitz and not self.game.is_season3:
                if self.game.num_tackle_zones_in(player) > 0:
                    continue
            if not player.state.used:
                forego_players.append(player)
                if self.game.is_season3 and player.has_skill(Skill.BALL_AND_CHAIN):
                    continue
                if not player.state.taken_root:
                    move_players.append(player)
                if self.blitz_available and not player.state.taken_root:
                    if not self.game.is_season3 or self.game.get_blitz_targets(player):
                        blitz_players.append(player)
                if self.pass_available and not (self.game.is_season3 and player.has_skill(Skill.MY_BALL)):
                    if not player.state.taken_root or self.game.get_ball_carrier() == player:
                        pass_players.append(player)
                if self.handoff_available and not (self.game.is_season3 and player.has_skill(Skill.MY_BALL)):
                    if not player.state.taken_root or self.game.get_ball_carrier() == player:
                        handoff_players.append(player)
                if self.foul_available:
                    if not player.state.taken_root or self.game.get_adjacent_opponents(player, down=True, standing=False):
                        foul_players.append(player)
                if not self.quick_snap and not self.blitz and (player.state.up or player.has_skill(Skill.JUMP_UP)):
                    if self.game.get_adjacent_opponents(player, down=False):
                        block_players.append(player)
                if player.state.up and player.has_skill(Skill.BOMBARDIER) and (not self.game.is_season3 or self.bomb_available):
                    bomb_players.append(player)

        actions = []
        activation_players = list(forego_players)
        if self.game.is_season3 and not self.quick_snap and not self.blitz:
            fanatics = [p for p in forego_players if p.has_skill(Skill.BALL_AND_CHAIN) and p.state.up]
            if fanatics:
                actions.append(ActionChoice(ActionType.START_BALL_AND_CHAIN, team=self.team, players=fanatics,
                                            skill=Skill.BALL_AND_CHAIN))
            forego_players = [p for p in forego_players if not p.has_skill(Skill.BALL_AND_CHAIN)]
            punters = [p for p in forego_players if p.has_skill(Skill.PUNT) and not p.has_skill(Skill.MY_BALL)]
            if self.punt_available and punters:
                actions.append(ActionChoice(ActionType.START_PUNT, team=self.team, players=punters, skill=Skill.PUNT))
            for skill, declaration, available in (
                    (Skill.THROW_TEAM_MATE, ActionType.START_THROW_TEAM_MATE, self.throw_team_mate_available),
                    (Skill.KICK_TEAM_MATE, ActionType.START_KICK_TEAM_MATE, self.kick_team_mate_available)):
                players = [p for p in forego_players if p.has_skill(skill) and p.get_pass_target() is not None]
                if available and players:
                    actions.append(ActionChoice(declaration, team=self.team, players=players, skill=skill))
            for skill, (declaration, _) in SEASON3_SPECIAL_ACTIONS.items():
                players = [p for p in forego_players if p.has_skill(skill) and (
                    skill == Skill.HYPNOTIC_GAZE or p.state.up)]
                if players:
                    actions.append(ActionChoice(declaration, team=self.team, players=players, skill=skill))
        if self.game.is_season3 and not self.quick_snap and not self.blitz and activation_players:
            actions.append(ActionChoice(ActionType.FOREGO_ACTIVATION, team=self.team, players=activation_players))
        secure_players = [p for p in move_players if self.game.can_secure_ball(p)]
        if secure_players:
            actions.append(ActionChoice(ActionType.START_SECURE_BALL, team=self.team, players=secure_players))
        if len(move_players) > 0:
            actions.append(ActionChoice(ActionType.START_MOVE, team=self.team, players=move_players))
        if len(block_players) > 0:
            actions.append(ActionChoice(ActionType.START_BLOCK, team=self.team, players=block_players))
        if len(blitz_players) > 0:
            actions.append(ActionChoice(ActionType.START_BLITZ, team=self.team, players=blitz_players))
        if len(pass_players) > 0:
            actions.append(ActionChoice(ActionType.START_PASS, team=self.team, players=pass_players))
        if len(handoff_players) > 0:
            actions.append(ActionChoice(ActionType.START_HANDOFF, team=self.team, players=handoff_players))
        if len(foul_players) > 0:
            actions.append(ActionChoice(ActionType.START_FOUL, team=self.team, players=foul_players))
        if len(bomb_players) > 0:
            actions.append(ActionChoice(ActionType.START_THROW_BOMB, team=self.team, players=bomb_players))
        actions.append(ActionChoice(ActionType.END_TURN, team=self.team))

        return actions


class WeatherTable(Procedure):

    def __init__(self, game, kickoff=False):
        super().__init__(game)
        self.kickoff = kickoff

    def step(self, action):
        roll = DiceRoll([D6(self.game.rng), D6(self.game.rng)], roll_type=RollType.WEATHER_ROLL)
        if roll.get_sum() == 2:
            self.game.state.weather = WeatherType.SWELTERING_HEAT
            self.game.report(Outcome(OutcomeType.WEATHER_SWELTERING_HEAT, rolls=[roll]))
        if roll.get_sum() == 3:
            self.game.state.weather = WeatherType.VERY_SUNNY
            self.game.report(Outcome(OutcomeType.WEATHER_VERY_SUNNY, rolls=[roll]))
        if 4 <= roll.get_sum() <= 10:
            if self.kickoff and (self.game.is_season3 or self.game.state.weather == WeatherType.NICE):
                self.game.state.gentle_gust = True
            self.game.state.weather = WeatherType.NICE
            self.game.report(Outcome(OutcomeType.WEATHER_NICE, rolls=[roll]))
        if roll.get_sum() == 11:
            self.game.state.weather = WeatherType.POURING_RAIN
            self.game.report(Outcome(OutcomeType.WEATHER_POURING_RAIN, rolls=[roll]))
        if roll.get_sum() == 12:
            self.game.state.weather = WeatherType.BLIZZARD
            self.game.report(Outcome(OutcomeType.WEATHER_BLIZZARD, rolls=[roll]))
        return True


class Negatrait(Procedure, metaclass=ABCMeta):
    def __init__(self, game, player, ends_turn=True):
        super().__init__(game)
        self.player = player
        self.waiting_reroll = False
        self.reroll_used = False
        self.rolled = False
        self.roll = None
        self.reroll = None

        self.roll_type = None
        self.skill = None
        self.success_outcome = None
        self.fail_outcome = None
        self.ends_turn = ends_turn

    @abstractmethod
    def get_target(self):
        pass

    @abstractmethod
    def apply_fail_state(self):
        pass

    @abstractmethod
    def remove_fail_state(self):
        pass

    def trigger_failure(self):
        self.apply_fail_state()
        self.player.state.failed_nega_trait_this_turn = True
        if self.ends_turn:
            self.end_turn()

    def step(self, action):
        # If player hasn't rolled
        if not self.rolled:
            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=self.roll_type)
            self.roll.target = self.get_target()
            self.rolled = True

            if self.roll.is_d6_success():
                # Success
                self.remove_fail_state()
                self.game.report(Outcome(self.success_outcome, player=self.player, rolls=[self.roll]))
                return True
            else:
                self.game.report(Outcome(self.fail_outcome, player=self.player, skill=self.skill, rolls=[self.roll]))
                # check reroll
                self.reroll = Reroll(self.game, self.player, self)
                return False

        # Is re-roll used?
        assert self.reroll is not None
        if self.reroll.use_reroll:
            # re-roll allowed
            self.rolled = False
            self.reroll = None
            return self.step(None)
        else:
            # no re-roll
            self.trigger_failure()
            return True

    def end_turn(self):
        # mark player turn as over
        EndPlayerTurn(self.game, self.player)


class Bonehead(Negatrait):
    def __init__(self, game, player=True):
        super().__init__(game, player)
        self.roll_type = RollType.BONE_HEAD_ROLL
        self.skill = Skill.BONE_HEAD
        self.success_outcome = OutcomeType.SUCCESSFUL_BONE_HEAD
        self.fail_outcome = OutcomeType.FAILED_BONE_HEAD

    def get_target(self):
        return 2

    def apply_fail_state(self):
        self.player.state.bone_headed = True

    def remove_fail_state(self):
        self.player.state.bone_headed = False


class ReallyStupid(Negatrait):
    def __init__(self, game, player=True):
        super().__init__(game, player)
        self.roll_type = RollType.REALLY_STUPID_ROLL
        self.skill = Skill.REALLY_STUPID
        self.success_outcome = OutcomeType.SUCCESSFUL_REALLY_STUPID
        self.fail_outcome = OutcomeType.FAILED_REALLY_STUPID

    def get_target(self):
        target = 4  # default target for player alone
        team_mates = self.game.get_adjacent_teammates(self.player)
        if team_mates:
            for team_mate in team_mates:
                if not team_mate.has_skill(Skill.REALLY_STUPID) and (
                        not self.game.is_season3 or (team_mate.state.up and not team_mate.is_distracted())):
                    target = 2  # a non-stupid neighbour improves the odds
        return target

    def apply_fail_state(self):
        self.player.state.really_stupid = True

    def remove_fail_state(self):
        self.player.state.really_stupid = False


class WildAnimal(Negatrait):
    def __init__(self, game, player=True, is_block_or_blitz=False):
        super().__init__(game, player)
        self.is_block_or_blitz = is_block_or_blitz
        self.roll_type = RollType.WILD_ANIMAL_ROLL
        self.skill = Skill.WILD_ANIMAL
        self.success_outcome = OutcomeType.SUCCESSFUL_WILD_ANIMAL
        self.fail_outcome = OutcomeType.FAILED_WILD_ANIMAL

    def get_target(self):
        target = 4
        if self.is_block_or_blitz:
            target = 2
        return target

    def apply_fail_state(self):
        self.player.state.wild_animal = True

    def remove_fail_state(self):
        self.player.state.wild_animal = False


class AnimalSavagery(WildAnimal):
    def __init__(self, game, player, is_block_or_blitz=False):
        super().__init__(game, player, is_block_or_blitz)
        self.skill = Skill.ANIMAL_SAVAGERY

    def trigger_failure(self):
        self.player.state.failed_nega_trait_this_turn = True
        victims = self.game.get_adjacent_teammates(self.player, down=False)
        if victims:
            SavageryVictim(self.game, self.player, victims)
        else:
            self.player.state.distracted = True
            EndPlayerTurn(self.game, self.player)


class SavageryVictim(Procedure):
    def __init__(self, game, player, victims):
        super().__init__(game)
        self.player = player
        self.victims = victims

    def step(self, action):
        victim = action.player
        KnockDown(self.game, victim, inflictor=self.player, block=True,
                  turnover=self.game.has_ball(victim))
        return True

    def available_actions(self):
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.player.team, players=self.victims)]


class TakeRoot(Negatrait):
    def __init__(self, game, player=True):
        super().__init__(game, player, ends_turn=False)
        self.roll_type = RollType.TAKE_ROOT_ROLL
        self.skill = Skill.TAKE_ROOT
        self.success_outcome = OutcomeType.SUCCESSFUL_TAKE_ROOT
        self.fail_outcome = OutcomeType.FAILED_TAKE_ROOT

    def get_target(self):
        return 2

    def apply_fail_state(self):
        self.player.state.taken_root = True

    def remove_fail_state(self):
        pass  # taken_root is only reset upon end of drive


class BloodLustBlockOrMove(Procedure):

    def __init__(self, game, player, declared_action=ActionType.START_BLOCK):
        super().__init__(game)
        self.player = player
        self.declared_action = declared_action

    def step(self, action):
        if action.action_type == self.declared_action:
            return True
        # Cancel block action
        self.game.purge_stack_until(Turn, inclusive=False)
        # Start move action
        MoveAction(self.game, self.player)
        self.game.report(Outcome(OutcomeType.MOVE_ACTION_STARTED, player=self.player))
        return True

    def available_actions(self):
        return [ActionChoice(self.declared_action, self.player.team, players=[self.player]),
                ActionChoice(ActionType.START_MOVE, self.player.team, players=[self.player])]


class BloodLust(Negatrait):
    def __init__(self, game, player=True, is_block=False, declared_action=ActionType.START_MOVE):
        super().__init__(game, player, ends_turn=False)
        self.is_block = is_block
        self.declared_action = declared_action
        self.roll_type = RollType.BLOOD_LUST_ROLL
        self.skill = Skill.BLOOD_LUST
        self.success_outcome = OutcomeType.SUCCESSFUL_BLOOD_LUST
        self.fail_outcome = OutcomeType.FAILED_BLOOD_LUST
        
    def get_target(self):
        if self.game.is_season3:
            from botbowl.core.skill_rules import target_parameter
            return target_parameter(self.player, Skill.BLOOD_LUST, 2) - int(
                self.declared_action in (ActionType.START_BLOCK, ActionType.START_BLITZ))
        return 2

    def apply_fail_state(self):
        #set_trace()
        self.player.state.blood_lust = True
        if self.game.is_season3:
            if self.declared_action != ActionType.START_MOVE:
                BloodLustBlockOrMove(self.game, self.player, self.declared_action)
        elif self.is_block:
            BloodLustBlockOrMove(self.game, self.player)

    def remove_fail_state(self):
        pass  # blood lust is removed by EatThrall-procedure 
        

class Reroll(Procedure):

    def __init__(self, game, player, context):
        super().__init__(game, context=context)
        self.player = player
        self.use_reroll = None
        self.loner = None
        self.can_use_team_reroll = False
        self.can_use_pro = False
        self.pro = None
        self.secondary_clock = False
        self.skill = None
        self.block_actions = []
        self.block_action = None
        self.block_skills = []

    def start(self):

        # If procedure was already re-rolled, don't re-roll
        if self.context in self.game.state.rerolled_procs:
            self.can_use_pro = False
            self.can_use_team_reroll = False
            return

        # Collect block dice actions if context is block
        if isinstance(self.context, Block):
            self.block_actions.extend(self.context.available_actions())
            if self.game.is_season3:
                values = [die.get_value() for die in self.context.roll.dice]
                if (self.player.can_use_skill(Skill.BRAWLER) and not self.context.blitz and
                        BBDieResult.BOTH_DOWN in values):
                    self.block_skills.append((Skill.BRAWLER, BBDieResult.BOTH_DOWN))
                keyword = self.player.skill_parameter(Skill.HATRED, '').casefold()
                if (self.player.has_skill(Skill.HATRED) and BBDieResult.ATTACKER_DOWN in values and
                        keyword in [k.casefold() for k in self.context.defender.role.keywords]):
                    self.block_skills.append((Skill.HATRED, BBDieResult.ATTACKER_DOWN))

        # Pro skill
        if ((self.player.has_usable_skill(Skill.PRO, assume_standing=isinstance(self.context, SteadyFooting))
             if self.game.is_season3 else self.player.can_use_skill(Skill.PRO))
                and (not self.game.is_season3 or self.player == self.game.get_active_player())):
            self.can_use_pro = True

        # Determine if team re-rolls are available
        self.can_use_team_reroll = self.game.can_use_reroll(self.player.team)

        # Check for automatic skill re-rolls
        self.skill = None
        if (type(self.context) == Dodge or (isinstance(self.context, Season3Escape) and not self.context.jump)) and self.player.can_use_skill(Skill.DODGE):
            # Get players with tackle
            origin = self.context.origin if isinstance(self.context, Season3Escape) else self.player.position
            tacklers = self.game.get_adjacent_players(origin, team=self.game.get_opp_team(self.player.team),
                                                     down=False, skill=Skill.TACKLE)
            if self.game.is_season3:
                tacklers = [p for p in tacklers if p.has_tackle_zone() and p.has_usable_skill(Skill.TACKLE)]
            if len(tacklers) == 0:
                self.player.use_skill(Skill.DODGE)
                self.use_reroll = True
                self.skill = Skill.DODGE
        if isinstance(self.context, PassAttempt) and self.player.can_use_skill(Skill.PASS):
            self.use_reroll = True
            self.skill = Skill.PASS
        if type(self.context) == Intercept and not self.game.is_season3:
            # Make sure it is not a safe throw agility re-roll
            if self.context.safe_throw_reroll is None and self.player.can_use_skill(Skill.CATCH):
                self.use_reroll = True
                self.skill = Skill.CATCH
        if type(self.context) == Catch:
            if self.player.can_use_skill(Skill.CATCH):
                self.use_reroll = True
                self.skill = Skill.CATCH
        if type(self.context) == Pickup and not self.context.secure and self.player.can_use_skill(Skill.SURE_HANDS):
            self.use_reroll = True
            self.skill = Skill.SURE_HANDS
        if type(self.context) == GFI and self.player.can_use_skill(Skill.SURE_FEET):
            self.player.use_skill(Skill.SURE_FEET)
            self.use_reroll = True
            self.skill = Skill.SURE_FEET
        if isinstance(self.context, Land) and self.context.swoop:
            self.use_reroll = True
            self.skill = Skill.SWOOP

        # Add secondary clock if waiting for opponent decision
        if self.can_use_pro and self.player.team != self.game.state.current_team:
            self.game.add_secondary_clock(self.player.team)
            self.secondary_clock = True

    def step(self, action):
        if self.block_skills:
            skill, value = self.block_skills.pop(0)
            if action.action_type == ActionType.USE_SKILL:
                self._reroll_block_die(value, skill)
                return True
            return False

        # If skill
        if self.skill is not None:
            self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=self.skill))
            return True

        # If no re-rolls are available
        if not self.can_use_team_reroll and not self.can_use_pro:
            return True

        # Did use of Pro skill succeed?
        if self.pro is not None:
            if self.game.is_season3 and isinstance(self.context, Block) and self.pro.success:
                action_values = {
                    ActionType.SELECT_ATTACKER_DOWN: BBDieResult.ATTACKER_DOWN,
                    ActionType.SELECT_BOTH_DOWN: BBDieResult.BOTH_DOWN,
                    ActionType.SELECT_PUSH: BBDieResult.PUSH,
                    ActionType.SELECT_DEFENDER_STUMBLES: BBDieResult.DEFENDER_STUMBLES,
                    ActionType.SELECT_DEFENDER_DOWN: BBDieResult.DEFENDER_DOWN}
                if action is None:
                    return False
                self._reroll_block_die(action_values[action.action_type], Skill.PRO)
                return True
            self.use_reroll = self.pro.success
            # If Pro (with possible re-rolls) failed - team re-rolls are not allowed.
            return True

        # Use Pro skill?
        if self.can_use_pro:
            if action.action_type == ActionType.USE_SKILL:
                self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=Skill.PRO))
                self.pro = Pro(self.game, self.player, context=self)
                if self.game.is_season3:
                    self.game.state.rerolled_procs.add(self.context)
                return False
            elif action.action_type == ActionType.DONT_USE_SKILL:
                self.can_use_pro = False
                if self.game.is_season3 and self.can_use_team_reroll:
                    return False

        # Did Loner roll succeed?
        if self.loner is not None:
            self.use_reroll = self.loner.success
            return True

        # If action is among parent actions
        if action is not None:
            for action_choice in self.block_actions:
                if action_choice.action_type == action.action_type:
                    self.block_action = action
                    return True

        # Team re-roll
        if self.can_use_team_reroll:
            if action.action_type == ActionType.USE_REROLL:
                self.use_reroll = True
                self.game.use_team_reroll(self.player.team)
                self.game.report(Outcome(OutcomeType.REROLL_USED, team=self.player.team))
                if self.player.has_skill(Skill.LONER):
                    self.loner = Loner(self.game, self.player, context=self)
                    return False
            elif action.action_type == ActionType.DONT_USE_REROLL:
                self.use_reroll = False
            return True

        # If neither Pro or team re-rolls can be used
        self.use_reroll = False
        return True

    def _reroll_block_die(self, value, skill):
        index = next(i for i, die in enumerate(self.context.roll.dice) if die.get_value() == value)
        self.context.roll.dice[index] = BBDie(self.game.rng)
        self.game.state.rerolled_procs.add(self.context)
        if skill == Skill.BRAWLER:
            self.player.use_skill(skill)
        self.game.report(Outcome(OutcomeType.SKILL_USED, player=self.player, skill=skill,
                                 rolls=[self.context.roll]))
        self.use_reroll = False
        self.block_skills.clear()

    def end(self):
        # Stop clock ff decision is opponent's
        if self.secondary_clock:
            self.game.remove_secondary_clocks()

        # Add context to set of re-rolled procs
        if self.use_reroll:
            self.game.state.rerolled_procs.add(self.context)

    def available_actions(self):
        """
        If bot, take actions in several steps: 1. Pro, 2. Reroll, 3. Go back to context
        If human, show all actions at once, but hide uneccessary don't use/reroll actions.
        """
        actions = []
        if self.block_skills:
            return [ActionChoice(kind, team=self.player.team, skill=self.block_skills[0][0])
                    for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)]
        if self.pro is not None and self.game.is_season3:
            if self.pro.success and isinstance(self.context, Block):
                values = {die.get_value() for die in self.context.roll.dice}
                return [ActionChoice(kind, team=self.player.team, skill=Skill.PRO)
                        for kind, value in ((ActionType.SELECT_ATTACKER_DOWN, BBDieResult.ATTACKER_DOWN),
                                            (ActionType.SELECT_BOTH_DOWN, BBDieResult.BOTH_DOWN),
                                            (ActionType.SELECT_PUSH, BBDieResult.PUSH),
                                            (ActionType.SELECT_DEFENDER_STUMBLES, BBDieResult.DEFENDER_STUMBLES),
                                            (ActionType.SELECT_DEFENDER_DOWN, BBDieResult.DEFENDER_DOWN))
                        if value in values]
            return []
        if self.skill is not None or self.loner is not None:
            return actions
        if self.game.is_season3:
            if self.can_use_pro:
                actions.extend([ActionChoice(kind, team=self.player.team, skill=Skill.PRO)
                                for kind in (ActionType.USE_SKILL, ActionType.DONT_USE_SKILL)])
            if self.can_use_team_reroll:
                actions.append(ActionChoice(ActionType.USE_REROLL, team=self.player.team))
                if not (isinstance(self.context, Block) and self.context.favor == self.player.team
                        and self.game.get_team_agent(self.player.team).human):
                    actions.append(ActionChoice(ActionType.DONT_USE_REROLL, team=self.player.team))
            if actions and isinstance(self.context, Block) and self.context.favor == self.player.team:
                actions.extend(self.block_actions)
            return actions
        if not self.game.get_team_agent(self.player.team).human:  # Actor is non-human agent, action accuired from agent.act(game)
            if self.can_use_pro:
                actions = [
                    ActionChoice(ActionType.USE_SKILL, skill=Skill.PRO, team=self.game.state.current_team),
                    ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.PRO, team=self.game.state.current_team)
                ]
            elif self.can_use_team_reroll:
                actions = [
                    ActionChoice(ActionType.USE_REROLL, team=self.player.team),
                    ActionChoice(ActionType.DONT_USE_REROLL, team=self.player.team)
                ]
        else:  # actor is human agent. action supplied through game.step(action) 
            if len(self.block_actions) == 0 or self.context.favor != self.player.team: 
                if self.can_use_pro:
                    actions = [
                        ActionChoice(ActionType.USE_SKILL, skill=Skill.PRO, team=self.game.state.current_team)
                    ]
                    if not self.can_use_team_reroll:
                        actions.append(ActionChoice(ActionType.DONT_USE_SKILL, skill=Skill.PRO, team=self.game.state.current_team))
                if self.can_use_team_reroll:
                    actions = [
                        ActionChoice(ActionType.USE_REROLL, team=self.player.team),
                        ActionChoice(ActionType.DONT_USE_REROLL, team=self.player.team)
                    ]
            else: 
                if self.can_use_pro:
                    actions = [
                        ActionChoice(ActionType.USE_SKILL, skill=Skill.PRO, team=self.game.state.current_team)
                    ]
                if self.can_use_team_reroll:
                    actions = [
                        ActionChoice(ActionType.USE_REROLL, team=self.player.team)
                    ]

            if len(self.block_actions) > 0 and len(actions) > 0:
                actions.extend(self.block_actions)

        return actions


class Pro(Procedure):
    def __init__(self, game, player, context):
        super().__init__(game, context=context)
        self.success = False
        self.roll = None
        self.player = player
        self.reroll = None

    def start(self):
        assert self.player.has_skill(Skill.PRO) if self.game.is_season3 else self.player.can_use_skill(Skill.PRO)
        self.player.use_skill(Skill.PRO)

    def step(self, action):
        if self.roll is None:
            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.PRO)
            self.roll.target = 3 if self.game.is_season3 else 4

            if self.roll.is_d6_success():
                # Success
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_PRO, player=self.player, rolls=[self.roll]))
                self.success = True
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_PRO, player=self.player, rolls=[self.roll]))
                if self.game.is_season3:
                    return True
                # Team re-rolls can be used to re-roll a failed Pro roll
                self.reroll = Reroll(self.game, self.player, context=self.context)
                return False

        # If re-roll used
        assert self.reroll is not None
        if self.reroll.use_reroll:
            # re-roll
            self.roll = None
            return self.step(None)
        else:
            # no re-roll - self.success is already False
            return True


class Loner(Procedure):
    def __init__(self, game, player, context):
        super().__init__(game, context=context)
        self.success = False
        self.roll = None
        self.player = player
        self.reroll = None

    def step(self, action):
        if self.roll is None:
            # Roll
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.LONER_ROLL)
            if self.game.is_season3:
                from botbowl.core.skill_rules import target_parameter
                self.roll.target = target_parameter(self.player, Skill.LONER, 4)
            else:
                self.roll.target = 4

            if self.roll.is_d6_success():
                # Success
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_LONER, player=self.player, rolls=[self.roll]))
                self.success = True
                return True
            else:
                self.game.report(Outcome(OutcomeType.FAILED_LONER, player=self.player, skill=Skill.LONER, rolls=[self.roll]))
                # Failed loner rolls can be re-rolled if the player has the Pro skill
                self.reroll = Reroll(self.game, self.player, context=self.context)
                return False

        # If re-roll used
        assert self.reroll is not None
        if self.reroll.use_reroll:
            # re-roll
            self.roll = None
            return self.step(None)
        else:
            # no re-roll
            self.result = False
            return True


class EatThrall(Procedure): 
    def __init__(self, game, player):
        super().__init__(game)
        self.player = player 
        self.victim = None 
        self.failed = None 
        
    def start(self): 
        self.victim_pos = self.game.get_adjacent_blood_lust_victims(self.player)
        
    def step(self, action): 
        if len(self.victim_pos)==0 or (action is not None and action.action_type == ActionType.SELECT_NONE):
            Turnover(self.game)
            
            ball = self.game.get_ball_at(self.player.position)
            if ball is not None: 
                Bounce(self.game, ball)
            
            if self.game.is_season3:
                self.player.state.distracted = True
            else:
                self.game.pitch_to_reserves(self.player)
                self.game.report(Outcome(OutcomeType.EJECTED_BY_BLOOD_LUST, player=self.player))
            
            self.failed = True 
            
        else: 
            self.victim = self.game.get_player_at(action.position)  
            #set_trace() 
            self.game.report(Outcome(OutcomeType.EATEN_DURING_BLOOD_LUST, player=self.victim, opp_player=self.player))
            KnockDown(self.game, self.victim, armor_roll=False, injury_roll=True,
                      blood_lust=self.game.is_season3,
                      turnover=self.game.is_season3 and self.game.has_ball(self.victim))
            self.failed = False 
            
        return True 
        
    def end(self): 
        self.player.state.blood_lust = False
        
    def available_actions(self): 
        if len(self.victim_pos) > 0:
            actions = [ActionChoice(ActionType.SELECT_PLAYER, positions=self.victim_pos, team=self.player.team)]
            if self.game.is_season3:
                actions.append(ActionChoice(ActionType.SELECT_NONE, team=self.player.team))
            return actions
        else: 
            return [] 


class HypnoticGaze(Procedure): 
    def __init__(self, game, player, target_player): 
        super().__init__(game)
        self.player = player
        self.target_player = target_player 
        self.roll = None
        self.reroll = None 
        
    def start(self): 
        pass 
    
    def step(self, action): 
        if self.roll is None: 
            #agility roll with tz modifiers except target_player
            self.roll = DiceRoll([D6(self.game.rng)], roll_type=RollType.AGILITY_ROLL)
            self.roll.modifiers = 0 if self.game.is_season3 else self.game.get_hypno_modifier(self.player)
            self.roll.target = 3 if self.game.is_season3 else self.player.get_ag_target()
            
            if self.roll.is_d6_success(): 
                self.game.report(Outcome(OutcomeType.SUCCESSFUL_HYPNOTIC_GAZE, player=self.player, rolls=[self.roll]))
                self.target_player.state.hypnotized = True 
                return True 
            
            self.game.report(Outcome(OutcomeType.FAILED_HYPNOTIC_GAZE, player=self.player, rolls=[self.roll]))
            self.reroll = Reroll(self.game, self.player, self)
            return False
        
        assert self.reroll is not None 
        
        if self.reroll.use_reroll: 
            self.roll = None 
            self.reroll = None 
            return False 
        
        return True 



# Season 3 standalone-match flow. Legacy configurations retain their procedures.
def _random_players(game, players, count):
    players = sorted(players, key=lambda p: p.nr)
    if len(players) <= count:
        return players
    return list(game.rng.choice(players, size=count, replace=False))


class Swarming(Procedure):
    """Extra reserve Linemen after both ordinary setups, before the kick-off."""

    def __init__(self, game, team):
        super().__init__(game)
        self.team = team
        self.remaining = 0

    def eligible(self):
        return [p for p in self.game.get_reserves(self.team) if 'Lineman' in p.role.keywords
                and not p.state.heated and not p.state.snack_absent]

    def start(self):
        if self.eligible():
            roll = DiceRoll([D3(self.game.rng)], roll_type=RollType.SWARMING_ROLL)
            self.remaining = roll.get_sum()
            self.game.report(Outcome(OutcomeType.SWARMING, team=self.team, n=self.remaining, rolls=[roll]))

    def step(self, action):
        if action is None or action.action_type == ActionType.END_SETUP:
            return True
        self.game.reserves_to_pitch(action.player, action.position)
        self.remaining -= 1
        self.game.report(Outcome(OutcomeType.PLAYER_PLACED, team=self.team,
                                 player=action.player, position=action.position))
        return self.remaining == 0

    def available_actions(self):
        players = self.eligible()
        if self.remaining == 0 or not players:
            return []
        pitch_players = self.game.get_players_on_pitch(self.team)
        full_wings = [rows for rows in self.game.setup_wing_rows(self.team)
                      if sum(p.position.y in rows for p in pitch_players) >= self.game.config.wing_max]
        positions = [square for square in self.game.get_team_side(self.team)
                     if self.game.get_player_at(square) is None and
                     not any(square.y in rows for rows in full_wings)]
        if not positions:
            return []
        return [ActionChoice(ActionType.PLACE_PLAYER, team=self.team, players=players, positions=positions),
                ActionChoice(ActionType.END_SETUP, team=self.team)]


class StartDrive(Procedure):
    def step(self, action):
        self.game.state.drive_active = True
        Kickoff(self.game)
        for team in (self.game.get_receiving_team(), self.game.get_kicking_team()):
            if self.game.has_team_rule(team, 'Swarming'):
                Swarming(self.game, team)
        Setup(self.game, self.game.get_receiving_team())
        Setup(self.game, self.game.get_kicking_team())
        ClearBoard(self.game)
        return True


class EndDrive(Procedure):
    """Weather, KO recovery, then expiry; also runs at the end of each half."""
    def __init__(self, game):
        super().__init__(game)
        self.phase = 0

    def step(self, action):
        if self.phase == 0:
            self.phase = 1
            # Play has ended. Heat or Secret Weapon ejections may remove the
            # carrier before the next setup (or at full time), so possession
            # must expire before those removals without an in-play bounce.
            for ball in self.game.state.pitch.balls:
                ball.is_carried = False
            # Last drive's heat exclusions have served their one-drive duration.
            for team in self.game.state.teams:
                for player in team.players:
                    player.state.heated = False
            if self.game.state.weather == WeatherType.SWELTERING_HEAT:
                roll = DiceRoll([D3(self.game.rng)], roll_type=RollType.SWELTERING_HEAT_ROLL)
                for team in self.game.state.teams:
                    for player in _random_players(self.game, self.game.get_players_on_pitch(team), roll.get_sum()):
                        self.game.pitch_to_reserves(player)
                        player.state.heated = True
                        self.game.report(Outcome(OutcomeType.PLAYER_HEATED, player=player, rolls=[roll]))
            for team in reversed(self.game.state.teams):
                PreKickoff(self.game, team)
            for team in reversed(self.game.state.teams):
                for player in team.players:
                    if player.state.played_drive and player.has_skill(Skill.SECRET_WEAPON) and not player.state.ejected:
                        Ejection(self.game, player)
                    player.state.played_drive = False
            return False
        for team in self.game.state.teams:
            team.state.rerolls -= team.state.drive_rerolls
            team.state.drive_rerolls = 0
            team.state.cheering_fans = False
            for player in team.players:
                player.state.dodgy_snack = False
                player.state.snack_absent = False
        self.game.state.drive_active = False
        self.game.report(Outcome(OutcomeType.DRIVE_ENDED))
        return True


class TimeOut(Procedure):
    def step(self, action):
        effect = -1 if self.game.get_kicking_team().state.turn >= 6 else 1
        self.game.add_or_skip_turn(effect)
        self.game.report(Outcome(OutcomeType.TURN_ADDED if effect == -1 else OutcomeType.TURN_SKIPPED))
        return True


class KickoffSelection(Procedure):
    """Select the entire Open-player set before any bonus movement begins."""
    def __init__(self, game, turn):
        super().__init__(game)
        self.turn = turn
        self.selected = []
        self.eligible = [p for p in game.get_players_on_pitch(turn.team, up=True)
                         if not p.state.stunned and game.num_tackle_zones_in(p) == 0]
        self.limit = 0

    def start(self):
        self.limit = D3(self.game.rng).get_value() + 3

    def step(self, action):
        if action is not None and action.action_type == ActionType.SELECT_PLAYER:
            self.selected = self.selected + [action.player]
            if len(self.selected) < min(self.limit, len(self.eligible)):
                return False
        self.turn.kickoff_players = list(self.selected)
        self.game.report(Outcome(OutcomeType.KICKOFF_PLAYERS_SELECTED, team=self.turn.team, n=len(self.selected)))
        return True

    def available_actions(self):
        if not self.eligible:
            return []
        return [ActionChoice(ActionType.SELECT_PLAYER, team=self.turn.team,
                             players=[p for p in self.eligible if p not in self.selected]),
                ActionChoice(ActionType.SELECT_NONE, team=self.turn.team)]


class QuickSnapMove(MoveAction):
    """A free square of placement, not a player activation or a Dodge test."""
    def start(self):
        self.game.state.player_action_type = PlayerActionType.MOVE

    def step(self, action):
        if action.action_type == ActionType.MOVE:
            self.game.move(self.player, action.position)
            self.game.report(Outcome(OutcomeType.PLAYER_PLACED, player=self.player, position=action.position))
        EndPlayerTurn(self.game, self.player)
        return True

    def available_actions(self):
        return [ActionChoice(ActionType.MOVE, team=self.player.team,
                             positions=self.game.get_adjacent_squares(self.player.position, occupied=False)),
                ActionChoice(ActionType.END_PLAYER_TURN, team=self.player.team)]


class SolidDefence(Setup):
    def __init__(self, game):
        super().__init__(game, game.get_kicking_team(), reorganize=True)
        self.selecting = True
        self.selected = []
        self.eligible = [p for p in game.get_players_on_pitch(self.team, up=True)
                         if not p.state.stunned and game.num_tackle_zones_in(p) == 0]
        self.limit = 0
        self.original_positions = {p.player_id: p.position for p in self.eligible}

    def start(self):
        super().start()
        self.limit = D3(self.game.rng).get_value() + 3

    def step(self, action):
        if self.selecting:
            if action is not None and action.action_type == ActionType.SELECT_PLAYER:
                self.selected = self.selected + [action.player]
                if len(self.selected) < min(self.limit, len(self.eligible)):
                    return False
            if not self.selected:
                self.game.state.current_team = None
                self.game.remove_clocks()
                return True
            self.selecting = False
            for player in self.selected:
                self.game.pitch_to_reserves(player)
            return False
        return super().step(action)

    def available_actions(self):
        if self.selecting:
            if not self.eligible:
                return []
            return [ActionChoice(ActionType.SELECT_PLAYER, team=self.team,
                                 players=[p for p in self.eligible if p not in self.selected]),
                    ActionChoice(ActionType.END_SETUP, team=self.team)]
        # No substitutions, formation macros or swaps with an unselected player.
        positions = [s for s in self.game.get_team_side(self.team)
                     if self.game.get_player_at(s) is None or self.game.get_player_at(s) in self.selected]
        actions = [ActionChoice(ActionType.PLACE_PLAYER, team=self.team, players=self.selected, positions=positions)]
        if all(p.position is not None for p in self.selected) and self.game.is_setup_legal(self.team):
            actions.append(ActionChoice(ActionType.END_SETUP, team=self.team))
        return actions


class DodgySnack(Procedure):
    def step(self, action):
        teams = self.game.state.teams
        rolls = [DiceRoll([D6(self.game.rng)], roll_type=RollType.DODGY_SNACK_ROLL) for _ in teams]
        worst = min(r.get_sum() for r in rolls)
        for team, roll in zip(teams, rolls):
            if roll.get_sum() != worst:
                continue
            players = _random_players(self.game, self.game.get_players_on_pitch(team), 1)
            if not players:
                continue
            player = players[0]
            snack = DiceRoll([D6(self.game.rng)], roll_type=RollType.DODGY_SNACK_ROLL)
            if snack.get_sum() == 1:
                self.game.pitch_to_reserves(player)
                player.state.snack_absent = True
                outcome = OutcomeType.SNACK_PLAYER_REMOVED
            else:
                player.state.dodgy_snack = True
                outcome = OutcomeType.DODGY_SNACK
            self.game.report(Outcome(outcome, player=player, team=team, rolls=[roll, snack]))
        return True


class Season3PitchInvasion(Procedure):
    def step(self, action):
        teams = self.game.state.teams
        rolls = [DiceRoll([D6(self.game.rng)], modifiers=t.state.fan_factor,
                          roll_type=RollType.PITCH_INVASION_ROLL) for t in teams]
        worst = min(r.get_sum() + r.modifiers for r in rolls)
        for team, roll in zip(teams, rolls):
            if roll.get_sum() + roll.modifiers != worst:
                continue
            number = DiceRoll([D3(self.game.rng)], roll_type=RollType.PITCH_INVASION_ROLL)
            for player in _random_players(self.game, self.game.get_players_on_pitch(team), number.get_sum()):
                if player.has_skill(Skill.BALL_AND_CHAIN):
                    KnockDown(self.game, player, armor_roll=False, injury_roll=False)
                    continue
                player.place_prone()
                player.state.stunned = True
                self.game.report(Outcome(OutcomeType.STUNNED, player=player, team=team, rolls=[roll, number]))
        return True


class KickScatterThree(Procedure):
    """Changing Weather scatters an airborne kick three squares, never catches en route."""
    def __init__(self, game, ball):
        super().__init__(game)
        self.ball = ball

    def step(self, action):
        rolls = [DiceRoll([D8(self.game.rng)], roll_type=RollType.SCATTER_ROLL) for _ in range(3)]
        for roll in rolls:
            value = roll.get_sum()
            dx = -1 if value in (1, 4, 6) else 1 if value in (3, 5, 8) else 0
            dy = -1 if value in (1, 2, 3) else 1 if value in (6, 7, 8) else 0
            self.game.shove(self.ball, dx, dy)
            if self.game.is_out_of_bounds(self.ball.position) or self.game.is_team_side(self.ball.position, self.game.get_kicking_team()):
                break
        self.game.report(Outcome(OutcomeType.BALL_SCATTER, position=self.ball.position, rolls=rolls))
        return True


def _season3_casualty_result(roll):
    result = min(16, max(1, roll.get_sum() + roll.modifiers))
    casualty = next(c for c in Season3CasualtyType if result <= c.value)
    # Persistent injury generation/characteristic loss belongs to League Play.
    effect = (CasualtyEffect.NONE if casualty == Season3CasualtyType.BADLY_HURT else
              CasualtyEffect.DEAD if casualty == Season3CasualtyType.DEAD else CasualtyEffect.MNG)
    return casualty, effect


class FoulEjection(Procedure):
    """Resolve being caught once, after armour, injury and any casualty treatment."""
    def __init__(self, game, player):
        super().__init__(game)
        self.player = player
        self.caught = False

    def step(self, action):
        if self.caught:
            Ejection(self.game, self.player)
        return True
