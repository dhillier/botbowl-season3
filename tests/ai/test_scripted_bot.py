import botbowl
from examples.scripted_bot_example import MyScriptedBot
from examples.random_bot_example import MyRandomBot

from tests.util import get_game_coin_toss

from random import randint

from pprint import pprint


def test_scripted_bot():
    game = get_game_coin_toss(seed=randint(0, 2**32))
    game.config.pathfinding_enabled = False

    scripted_bot_home = MyScriptedBot('scripted_test_bot1')
    scripted_bot_home.new_game(game, game.state.home_team)
    game.replace_home_agent(scripted_bot_home)

    scripted_bot_away = MyScriptedBot('scripted_test_bot2')
    scripted_bot_away.new_game(game, game.state.away_team)
    game.replace_away_agent(scripted_bot_away)

    game.set_available_actions()

    game.step(botbowl.Action(botbowl.ActionType.START_GAME))

def test_scripted_teacher_accepts_favourable_human_interface_block_dice():
    from tests.game.test_season3 import season3_turn
    from tests.util import only_fixed_rolls
    from botbowl import Action, ActionType, BBDieResult
    game, (attacker, defender) = season3_turn([(5, 5)], [(6, 5)], rerolls=1)
    attacker.extra_st = 3
    coach = MyScriptedBot('teacher')
    coach.new_game(game, attacker.team)
    game.step(Action(ActionType.START_BLOCK, player=attacker))
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN, BBDieResult.PUSH]):
        game.step(Action(ActionType.BLOCK, position=defender.position))
    assert not any(a.action_type == ActionType.DONT_USE_REROLL for a in game.get_available_actions())
    action = coach.act(game)
    assert action.action_type == ActionType.SELECT_PUSH
    assert game._is_action_allowed(action)
