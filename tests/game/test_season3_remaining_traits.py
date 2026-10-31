import pytest

from botbowl import (Action, ActionType, Skill, Square, OutcomeType, Casualty, Touchback,
                     Foul, BBDieResult, Player)
from tests.game.test_season3 import season3_turn
from tests.game.test_season3_flow import run_proc
from tests.game.test_season3_pathfinding import pf  # noqa: F401
from tests.util import only_fixed_rolls


@pytest.mark.parametrize('pathfinding', [False, True])
def test_fumblerooski_drops_at_departure_without_turnover(pathfinding):
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    player.extra_skills = [Skill.FUMBLEROOSKI]
    game.config.pathfinding_enabled = pathfinding
    with only_fixed_rolls(game):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.MOVE, position=Square(6, 5)))
        game.step(Action(ActionType.FUMBLEROOSKI, position=Square(7, 5)))
    assert game.get_ball_position() == Square(6, 5)
    assert not game.get_ball().is_carried
    assert player.position == Square(7, 5)
    assert not player.state.used
    assert not game.has_report_of_type(OutcomeType.TURNOVER)


def test_fumblerooski_cannot_override_my_ball():
    game, (player,) = season3_turn([(5, 5)], ball=(5, 5))
    player.extra_skills = [Skill.FUMBLEROOSKI, Skill.MY_BALL]
    game.step(Action(ActionType.START_MOVE, player=player))
    assert all(a.action_type != ActionType.FUMBLEROOSKI for a in game.get_available_actions())


def test_fumblerooski_held_by_tentacles_retains_ball():
    game, (player, holder) = season3_turn([(5, 5)], [(5, 6)], ball=(5, 5))
    player.extra_skills = [Skill.FUMBLEROOSKI]
    holder.extra_skills = [Skill.TENTACLES]
    with only_fixed_rolls(game, d6=[6]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.FUMBLEROOSKI, position=Square(6, 5)))
        game.step(Action(ActionType.USE_SKILL, player=holder))
    assert game.get_ball_carrier() == player
    assert player.position == Square(5, 5)
    assert player.state.used


def test_fumblerooski_failed_dodge_leaves_ball_at_departure():
    game, (player, marker) = season3_turn([(5, 5)], [(5, 6)], ball=(5, 5))
    player.extra_skills = [Skill.FUMBLEROOSKI]
    with only_fixed_rolls(game, d6=[1, 1, 1]):
        game.step(Action(ActionType.START_MOVE, player=player))
        game.step(Action(ActionType.FUMBLEROOSKI, position=Square(6, 5)))
    assert game.get_ball_position() == Square(5, 5)
    assert player.position == Square(6, 5)
    assert not player.state.up


def test_no_ball_cannot_be_given_touchback():
    game, (player, receiver) = season3_turn([(15, 5), (16, 5)])
    player.extra_skills = [Skill.NO_BALL]
    game.state.receiving_this_drive = player.team
    run_proc(game, Touchback(game, game.get_ball()))
    assert game.get_available_actions()[0].players == [receiver]


def test_no_ball_pickup_probability_is_zero_in_both_pathfinders(pf):
    game, (player,) = season3_turn([(5, 5)], ball=(6, 5), rerolls=2)
    player.extra_skills = [Skill.NO_BALL, Skill.SURE_HANDS]
    path = pf.Pathfinder(game, player, trr=True).get_path(Square(6, 5))
    assert path is None or path.prob == 0


def test_leader_reroll_expires_only_after_last_leader_permanently_leaves():
    game, (first, second) = season3_turn([(5, 5), (6, 5)])
    first.extra_skills = second.extra_skills = [Skill.LEADER]
    first.team.state.leader_reroll = True
    game.pitch_to_casualties(first)
    assert first.team.state.leader_reroll
    game.pitch_to_kod(second)
    assert first.team.state.leader_reroll
    game.pitch_to_dungeon(second)
    assert not first.team.state.leader_reroll


@pytest.mark.parametrize('save', [False, True])
def test_plague_ridden_waits_for_apothecary_and_adds_registered_lineman(save):
    game, (player, victim) = season3_turn([(5, 5)], [(6, 5)])
    player.team.race = 'Nurgle'
    player.extra_skills = [Skill.PLAGUE_RIDDEN]
    victim.team.state.apothecaries = 1
    original_count = len(player.team.players)
    with only_fixed_rolls(game, d16=[16] + ([1] if save else [])):
        run_proc(game, Casualty(game, victim, player, block=True, casualty_credit=True))
        assert all(a.skill != Skill.PLAGUE_RIDDEN for a in game.get_available_actions())
        game.step(Action(ActionType.USE_APOTHECARY if save else ActionType.DONT_USE_APOTHECARY))
        if save:
            game.step(Action(ActionType.SELECT_SECOND_ROLL))
        else:
            assert game.get_available_actions()[0].skill == Skill.PLAGUE_RIDDEN
            game.step(Action(ActionType.USE_SKILL))
    assert len(player.team.players) == original_count + (0 if save else 1)
    assert player.team.state.plague_ridden_used == (not save)
    if not save:
        recruit = player.team.players[-1]
        assert 'Lineman' in recruit.role.keywords
        assert recruit.role in next(r for r in game.ruleset.races if r.name == 'Nurgle').roles
        assert recruit in game.get_reserves(player.team)
        assert game.get_player(recruit.player_id) == recruit
        assert game.state.team_by_player_id[recruit.player_id] == player.team
    assert player.state.spp_earned == 2


def test_plague_ridden_recruitment_reverts_and_replays_all_registrations():
    game, (player, victim) = season3_turn([(5, 5)], [(6, 5)])
    player.team.race = 'Nurgle'
    player.extra_skills = [Skill.PLAGUE_RIDDEN]
    with only_fixed_rolls(game, d16=[16]):
        run_proc(game, Casualty(game, victim, player, block=True))
    game.enable_forward_model()
    before = game.get_step()
    game.step(Action(ActionType.USE_SKILL))
    recruit = player.team.players[-1]
    changes = game.revert(before)
    assert not player.team.state.plague_ridden_used
    assert recruit not in player.team.players and recruit not in game.get_reserves(player.team)
    assert recruit.player_id not in game.state.player_by_id
    assert recruit.player_id not in game.state.team_by_player_id
    game.forward(changes)
    assert player.team.state.plague_ridden_used
    assert recruit in player.team.players and recruit in game.get_reserves(player.team)
    assert game.get_player(recruit.player_id) is recruit
    assert game.state.team_by_player_id[recruit.player_id] is player.team


@pytest.mark.parametrize('restriction', ['big-guy', 'stunty', 'decay', 'regeneration', 'non-block', 'already-used'])
def test_plague_ridden_restrictions(restriction):
    game, (player, victim) = season3_turn([(5, 5)], [(6, 5)])
    player.extra_skills = [Skill.PLAGUE_RIDDEN]
    if restriction == 'big-guy':
        victim.role = game.ruleset.get_role('Ogre', 'Human')
    if restriction in ('stunty', 'decay', 'regeneration'):
        victim.extra_skills = [Skill[restriction.upper()]]
    player.team.state.plague_ridden_used = restriction == 'already-used'
    with only_fixed_rolls(game, d6=[1] if restriction == 'regeneration' else [], d16=[16]):
        run_proc(game, Casualty(game, victim, player, block=restriction != 'non-block'))
    assert all(a.skill != Skill.PLAGUE_RIDDEN for a in game.get_available_actions())


def test_plague_ridden_can_exceed_sixteen_players_and_is_once_per_game():
    game, (player, first, second) = season3_turn([(5, 5)], [(6, 5), (7, 5)])
    player.extra_skills = [Skill.PLAGUE_RIDDEN]
    while len(player.team.players) < 16:
        count = len(player.team.players)
        extra = Player('extra-{}'.format(count), player.role, 'Reserve', count + 1, player.team)
        player.team.players.append(extra)
    with only_fixed_rolls(game, d16=[16, 16]):
        run_proc(game, Casualty(game, first, player, block=True))
        game.step(Action(ActionType.USE_SKILL))
        player.state.reset()
        run_proc(game, Casualty(game, second, player, block=True))
    assert len(player.team.players) == 17
    assert all(a.skill != Skill.PLAGUE_RIDDEN for a in game.get_available_actions())


@pytest.mark.parametrize('kickback', [False, True])
def test_chainsaw_foul_is_optional_and_rolls_for_kickback(kickback):
    game, (fouler, victim) = season3_turn([(5, 5)], [(6, 5)], ball=(20, 12))
    fouler.extra_skills = [Skill.CHAINSAW]
    victim.state.up = False
    with only_fixed_rolls(game, d6=[1 if kickback else 2, 4, 2, 1, 2]):
        run_proc(game, Foul(game, fouler, victim))
        game.step(Action(ActionType.USE_SKILL))
    assert fouler.state.stunned == kickback
    assert victim.state.stunned == (not kickback)
    assert game.has_report_of_type(OutcomeType.TURNOVER) == kickback


@pytest.mark.parametrize('ejected', [False, True])
def test_pile_driver_full_block_then_foul_and_prone_or_ejection(ejected):
    game, (player, victim) = season3_turn([(5, 5)], [(6, 5)], ball=(20, 12))
    player.extra_skills = [Skill.PILE_DRIVER]
    with only_fixed_rolls(game, block_dice=[BBDieResult.DEFENDER_DOWN],
                          d6=[1, 2, 1, 1 if ejected else 2]):
        game.step(Action(ActionType.START_BLOCK, player=player))
        game.step(Action(ActionType.BLOCK, position=victim.position))
        game.step(Action(ActionType.SELECT_DEFENDER_DOWN))
        game.step(Action(ActionType.PUSH, position=Square(7, 5)))
        game.step(Action(ActionType.FOLLOW_UP, position=Square(6, 5)))
        assert game.get_available_actions()[0].skill == Skill.PILE_DRIVER
        game.step(Action(ActionType.USE_SKILL))
        if ejected:
            game.step(Action(ActionType.DONT_ARGUE_CALL))
    assert player.state.ejected == ejected
    assert (player.position is None) == ejected
    if not ejected:
        assert not player.state.up
        assert player.state.used
    assert game.has_report_of_type(OutcomeType.FOUL)
