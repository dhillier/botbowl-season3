"""Season 3 roster catalog, independent of match-rule certification.

This module contains no rule approximations: skill names, parameters and roster
limits are retained exactly, including mechanics awaiting engine validation.
"""
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path


ALIASES = {'chaos': 'chaos-chosen', 'undead': 'shambling-undead',
           'necromantic': 'necromantic-horror', 'khemri': 'tomb-kings'}
SKILL_ALIASES = {'SIDESTEP': 'SIDE_STEP', 'BLOODLUST': 'BLOOD_LUST',
                 'BALL_&_CHAIN': 'BALL_AND_CHAIN', 'TIMMM_BER!': 'TIMMMBER'}


def skill_spec(label):
    """Return the canonical enum name and optional parameter without losing either."""
    match = re.fullmatch(r'(.+?)(?: \((.+)\))?', label)
    if not match:
        raise ValueError('Invalid skill label: ' + label)
    name, parameter = match.groups()
    name = name.upper().replace('-', '_').replace(' ', '_')
    return SKILL_ALIASES.get(name, name), parameter


@lru_cache(maxsize=1)
def _catalog():
    path = Path(__file__).resolve().parents[1] / 'data' / 'rules' / 'BB2025-rosters.json'
    with path.open(encoding='utf-8') as source:
        return json.load(source)


def load_team_catalog():
    """Return a fresh copy of all supplied team data, including unvalidated skills."""
    return deepcopy(_catalog())


def get_team_profile(name):
    key = name.lower().replace('_', '-').replace(' ', '-')
    key = ALIASES.get(key, key)
    for team in _catalog()['teams']:
        if team['id'] == key:
            return deepcopy(team)
    raise ValueError('Unknown Season 3 team: ' + name)


def validate_roster_selection(name, positions, minimum=11, maximum=16):
    """Validate positional/shared limits; return player cost, excluding staff.

    ``positions`` maps positional IDs to counts. This checks roster composition,
    not rules implementation, team budget, league eligibility or team strength.
    """
    team = get_team_profile(name)
    roles = {p['id']: p for p in team['positions']}
    total, cost = 0, 0
    for position, count in positions.items():
        if position not in roles:
            raise ValueError('Unknown positional for ' + team['name'] + ': ' + position)
        if type(count) is not int or count < 0:
            raise ValueError('Roster counts must be non-negative integers')
        role = roles[position]
        if not role['min'] <= count <= role['max']:
            raise ValueError(f'{role["name"]}: count {count} exceeds positional limits')
        total += count
        cost += count * role['cost']
    if not minimum <= total <= maximum:
        raise ValueError(f'Roster must contain {minimum}-{maximum} players; found {total}')
    insignificant = sum(count for position, count in positions.items()
                        if 'Insignificant' in roles[position]['skills'])
    if insignificant > total - insignificant:
        raise ValueError('Insignificant players cannot outnumber other players')
    for limit in team['shared_limits']:
        if sum(positions.get(p, 0) for p in limit['positions']) > limit['max']:
            raise ValueError(f'{team["name"]}: shared positional limit of {limit["max"]} exceeded')
    return cost
