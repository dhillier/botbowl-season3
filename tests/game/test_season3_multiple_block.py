"""Both simultaneous blocks must finish even when the first ends the turn."""
from botbowl import Action, ActionType, BBDieResult, Skill, Square, OutcomeType
from tests.game.test_season3 import season3_turn
from tests.util import only_fixed_rolls


def multi_game(skills=()):
    game, players = season3_turn([(10, 5)], [(11, 4), (11, 6)], ball=(20, 12))
    attacker = players[0]
    attacker.extra_skills = [Skill.MULTIPLE_BLOCK, *skills]
    attacker.extra_st = 3  # ST 6 becomes ST 4; each defender receives one assist.
    game.set_available_actions()
    return game, players


def declare(game, attacker, first, second):
    game.step(Action(ActionType.START_BLOCK, player=attacker))
    game.step(Action(ActionType.USE_SKILL))
    game.step(Action(ActionType.SELECT_PLAYER, player=first))
    assert first not in game.get_available_actions()[0].players
    game.step(Action(ActionType.SELECT_PLAYER, player=second))


def test_two_pools_use_reduced_strength_and_neither_allows_followup():
    game, (attacker, first, second) = multi_game()
    with only_fixed_rolls(game, block_dice=[BBDieResult.PUSH, BBDieResult.PUSH]):
        declare(game, attacker, first, second)
        assert attacker.get_st() == 6  # The temporary penalty must not change the roster stat.
        game.step(Action(ActionType.SELECT_PUSH))
        assert first.position == Square(11, 4)  # second pool comes before any movement
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 3)))
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    assert attacker.get_st() == 6
    assert attacker.position == Square(10, 5)
    assert attacker.state.used
    assert not game.has_report_of_type(OutcomeType.FOLLOW_UP)
    rolls = [r.rolls[0] for r in game.state.reports if r.outcome_type == OutcomeType.BLOCK_ROLL]
    assert [len(r.dice) for r in rolls] == [1, 1]


def test_second_block_resolves_after_attacker_down_and_turnover_is_deferred():
    game, (attacker, first, second) = multi_game()
    with only_fixed_rolls(game, d6=[1, 1, 1, 1],
                          block_dice=[BBDieResult.ATTACKER_DOWN, BBDieResult.DEFENDER_DOWN]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.SELECT_ATTACKER_DOWN))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        assert not attacker.state.up
        assert not game.has_report_of_type(OutcomeType.TURNOVER)
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    assert not second.state.up and first.state.up
    assert attacker.get_st() == 6
    assert game.has_report_of_type(OutcomeType.TURNOVER)


def test_second_block_uses_mighty_blow_snapshot_after_attacker_is_prone():
    game, (attacker, first, second) = multi_game([Skill.MIGHTY_BLOW])
    with only_fixed_rolls(game, d6=[1, 1, 4, 4, 1, 1],
                          block_dice=[BBDieResult.ATTACKER_DOWN, BBDieResult.DEFENDER_DOWN]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.SELECT_ATTACKER_DOWN))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    assert second.state.stunned  # AV 9+ only breaks with the +1 modifier.


def test_removed_attacker_does_not_prevent_second_push():
    game, (attacker, first, second) = multi_game()
    with only_fixed_rolls(game, d6=[6, 6, 4, 4],
                          block_dice=[BBDieResult.ATTACKER_DOWN, BBDieResult.PUSH]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.SELECT_ATTACKER_DOWN))
        game.step(Action(ActionType.SELECT_PUSH))
        assert attacker.position is None
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    assert second.position == Square(12, 7)
    assert attacker.get_st() == 6


def test_double_both_down_does_not_injure_attacker_twice():
    game, (attacker, first, second) = multi_game()
    with only_fixed_rolls(game, d6=[1, 1, 1, 1, 1, 1],
                          block_dice=[BBDieResult.BOTH_DOWN, BBDieResult.BOTH_DOWN]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
        game.step(Action(ActionType.SELECT_BOTH_DOWN))
    assert all(not p.state.up for p in (attacker, first, second))
    assert sum(r.outcome_type == OutcomeType.KNOCKED_DOWN and r.player == attacker
               for r in game.state.reports) == 1


def test_brawler_rerolls_one_die_in_a_multiple_block_pool():
    game, (attacker, first, second) = multi_game([Skill.BRAWLER])
    with only_fixed_rolls(game, block_dice=[BBDieResult.BOTH_DOWN, BBDieResult.PUSH, BBDieResult.PUSH]):
        declare(game, attacker, first, second)
        game.step(Action(ActionType.USE_SKILL))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.SELECT_PUSH))
        game.step(Action(ActionType.PUSH, position=Square(12, 3)))
        game.step(Action(ActionType.PUSH, position=Square(12, 7)))
    assert attacker.state.up
    assert any(r.skill == Skill.BRAWLER for r in game.state.reports)


def test_multiple_block_unavailable_with_only_one_target():
    game, (attacker, first, second) = multi_game()
    game.move(second, Square(20, 10))
    game.step(Action(ActionType.START_BLOCK, player=attacker))
    assert not any(a.skill == Skill.MULTIPLE_BLOCK for a in game.get_available_actions())
