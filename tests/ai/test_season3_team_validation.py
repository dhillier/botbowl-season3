"""Coverage squads preserve actual roster limits, profiles and budgets."""
from copy import deepcopy

import pytest

import botbowl
from examples.season3_teams import build_team, coverage_squads


@pytest.mark.parametrize('profile', botbowl.load_team_catalog()['teams'], ids=lambda p: p['id'])
def test_coverage_squads_are_legal_and_span_every_positional(profile):
    covered = set()
    for squad in coverage_squads(profile['id']):
        cost = botbowl.validate_roster_selection(profile['id'], squad['positions'])
        assert cost + squad['rerolls'] * profile['reroll_cost'] + squad['apothecaries'] * 50000 == squad['spent']
        assert squad['spent'] <= 1000000
        size = 16 if profile['id'] == 'snotling' else 11
        assert sum(squad['positions'].values()) == size
        covered.update(p for p, count in squad['positions'].items() if count)
        team = build_team(squad)
        second = build_team(squad)
        assert team.team_id != second.team_id and team.players[0].player_id != second.players[0].player_id
        assert len(team.players) == size
        assert team.race == profile['name'] and team.treasury == 1000000 - squad['spent']
        assert all(p.team is team and p.extra_skills == (
            [botbowl.Skill.PRO] if p.player_id == team.captain_id else []) for p in team.players)
    assert covered == {p['id'] for p in profile['positions']}


def test_coverage_squads_reject_wrong_ruleset_staff_or_budget():
    squad = next(coverage_squads('human'))
    with pytest.raises(ValueError, match='BB2025'):
        build_team(squad, botbowl.load_rule_set('BB2016'))
    for field, value in [('rerolls', -1), ('rerolls', True), ('apothecaries', 2), ('budget', 1)]:
        bad = deepcopy(squad)
        bad[field] = value
        with pytest.raises(ValueError):
            build_team(bad)
