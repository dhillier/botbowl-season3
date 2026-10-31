"""Catalog integrity and regression checks against the supplied roster sheets."""
import json
from pathlib import Path

import pytest

from botbowl.core.load import load_rule_set, load_team_by_filename
from botbowl.core.roster import get_team_profile, load_team_catalog, skill_spec, validate_roster_selection
from botbowl.core.table import Skill, SkillCategory


CATALOG = load_team_catalog()


@pytest.mark.parametrize('team', CATALOG['teams'], ids=lambda t: t['id'])
def test_all_catalog_profiles_load_without_losing_data(team):
    rules = load_rule_set('BB2025')
    race = next(r for r in rules.races if r.name == team['name'])
    assert race.reroll_cost == team['reroll_cost']
    assert len(race.roles) == len(team['positions'])
    assert len({p['id'] for p in team['positions']}) == len(team['positions'])
    for profile in team['positions']:
        role = rules.get_role(profile['name'], team['name'])
        assert (role.ma, role.st, role.ag, role.pa, role.av, role.cost) == tuple(
            profile[field] for field in ('ma', 'st', 'ag', 'pa', 'av', 'cost'))
        assert role.max_count == profile['max']
        assert role.keywords == tuple(profile['keywords'])
        assert len(role.skills) == len(profile['skills'])
        for label in profile['skills']:
            name, parameter = skill_spec(label)
            assert Skill[name] in role.skills
            assert role.skill_parameters.get(Skill[name]) == parameter
        assert all(1 <= profile[field] <= 11 for field in ('ma', 'st', 'ag', 'av'))
        assert profile['pa'] is None or 1 <= profile['pa'] <= 6
        assert set(profile['primary'] + profile['secondary']) <= set('AGSM PD'.replace(' ', ''))
        assert 1 <= profile['source_page'] <= 3


def test_complete_catalog_and_rule_identity_inventory():
    assert len(CATALOG['teams']) == 30
    assert sum(len(t['positions']) for t in CATALOG['teams']) == 159
    path = Path(__file__).resolve().parents[2] / 'botbowl/data/rules/BB2025-skills.json'
    metadata = json.loads(path.read_text(encoding='utf-8'))['skills']
    assert len(metadata) == len({s['id'] for s in metadata}) == 108
    assert all(row['id'] in Skill.__members__ for row in metadata)
    covered = {row['id'] for row in metadata}
    assert {skill_spec(label)[0] for t in CATALOG['teams'] for p in t['positions'] for label in p['skills']} <= covered


def test_visible_source_corrections_are_not_concatenated_values():
    orcs = get_team_profile('orc')
    goblin = next(p for p in orcs['positions'] if p['id'] == 'goblin-lineman')
    assert goblin['pa'] == 4
    alliance = get_team_profile('old-world-alliance')
    assert next(p['max'] for p in alliance['positions'] if p['id'] == 'halfling-hopeful') == 3
    renegades = load_rule_set('BB2025')
    assert renegades.get_role('Ogre', 'Chaos Renegades').skill_parameters[Skill.LONER] == '3+'


def test_parameters_keywords_and_devious_access_survive_loading():
    rules = load_rule_set('BB2025')
    assert rules.get_role('Vampire Blitzer', 'Vampire').skill_parameters[Skill.BLOOD_LUST] == '3+'
    assert rules.get_role('Skaven Clanrat', 'Underworld Denizens').skill_parameters[Skill.ANIMOSITY] == 'Goblin'
    assert rules.get_role('Troll Slayer', 'Dwarf').skill_parameters[Skill.HATRED] == 'Troll'
    assert rules.get_role('Deathroller', 'Dwarf').pa is None
    assert SkillCategory.Devious in rules.get_role('Sneaky Stabba', 'Chaos Dwarf').n_skill_sets


def test_catalog_is_returned_without_shared_mutable_state():
    first = get_team_profile('orc')
    first['positions'][0]['skills'].append('Made Up Skill')
    assert 'Made Up Skill' not in get_team_profile('orc')['positions'][0]['skills']


def test_shared_big_guy_limit_and_counts():
    assert validate_roster_selection('chaos-chosen', {'beastman-lineman': 10, 'ogre': 1}) == 690000
    with pytest.raises(ValueError, match='shared positional limit'):
        validate_roster_selection('chaos-chosen', {'beastman-lineman': 9, 'ogre': 1, 'troll': 1})
    for bad in (-1, 1.5, True):
        with pytest.raises(ValueError, match='integers'):
            validate_roster_selection('human', {'human-lineman': bad})
    with pytest.raises(ValueError, match='positional limits'):
        validate_roster_selection('dark-elf', {'dark-elf-lineman': 8, 'dark-elf-blitzer': 3})


def test_existing_human_team_preserves_role_names_and_composition():
    team = load_team_by_filename('human', load_rule_set('BB2025'))
    assert len(team.players) == 12
    assert [p.role.name for p in team.players[:5]] == ['Blitzer', 'Blitzer', 'Thrower', 'Catcher', 'Catcher']
    assert all(p.role.name == 'Lineman' for p in team.players[5:])


def test_insignificant_players_cannot_outnumber_other_roster_players():
    assert validate_roster_selection('snotling', {
        'snotling-lineman': 5, 'fun-hoppa': 2, 'stilty-runna': 2, 'fungus-flinga': 2}) == 215000
    with pytest.raises(ValueError, match='Insignificant'):
        validate_roster_selection('snotling', {
            'snotling-lineman': 6, 'fun-hoppa': 2, 'stilty-runna': 2, 'fungus-flinga': 1})


def test_skill_audit_accounts_for_every_skill_without_claiming_completion():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    audit = json.loads((root / 'botbowl/data/rules/BB2025-skill-audit.json').read_text())
    inventory = json.loads((root / 'botbowl/data/rules/BB2025-skills.json').read_text())
    assert {row['id'] for row in audit['skills']} == {row['id'] for row in inventory['skills']}
    assert len(audit['skills']) == len(inventory['skills']) == 108
    for row in audit['skills']:
        assert row['remaining'] or row['status'] == 'validated'
        assert all((root / path).is_file() for path in row['tests'])
    complete = all(row['status'] == 'validated' for row in audit['skills'])
    assert audit['all_skills_validated'] == complete
    assert audit['ready_for_additional_team_validation'] == complete
