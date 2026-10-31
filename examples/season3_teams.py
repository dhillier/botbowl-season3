"""Legal coverage squads for incremental Season 3 integration validation.

These squads exercise every positional, including alternatives under shared
limits. They are not tactical recommendations or part of the fixed Human RL API.
"""
from itertools import combinations, product
from uuid import uuid4

import botbowl


def coverage_squads(name, budget=1000000):
    """Build coverage squads; Snotlings carry reserves to exercise Swarming."""
    profile = botbowl.get_team_profile(name)
    roles = {p['id']: p for p in profile['positions']}
    size = 16 if 'Swarming' in profile.get('special_rules', []) else 11
    shared = profile['shared_limits']
    alternatives = [list(combinations(limit['positions'], limit['max'])) for limit in shared]
    excluded = {p for limit in shared for p in limit['positions']}
    for selected in product(*alternatives):
        included = set(roles) - excluded
        included.update(p for group in selected for p in group)
        counts = {p: 1 for p in roles if p in included}
        # Cover each positional once, then fill with affordable players. Keep
        # enough non-Insignificant slots for a legal eleven-player roster.
        while sum(counts.values()) < size:
            insignificant = sum(n for p, n in counts.items() if 'Insignificant' in roles[p]['skills'])
            candidates = [p for p in included if counts[p] < roles[p]['max'] and
                          ('Insignificant' not in roles[p]['skills'] or insignificant < size // 2) and
                          all(p not in limit['positions'] or
                              sum(counts.get(q, 0) for q in limit['positions']) < limit['max']
                              for limit in shared)]
            if not candidates:
                raise ValueError('Cannot fill coverage squad: ' + profile['id'])
            counts[min(candidates, key=lambda p: (roles[p]['cost'], p))] += 1
        cost = botbowl.validate_roster_selection(name, counts)
        if cost > budget:
            raise ValueError('Coverage squad exceeds budget: ' + profile['id'])
        rerolls = min(2, (budget - cost) // profile['reroll_cost'])
        apothecaries = int(profile['apothecary'] and budget - cost - rerolls * profile['reroll_cost'] >= 50000)
        suffix = '-'.join(p for group in selected for p in group)
        yield {'id': profile['id'] + ('--' + suffix if suffix else ''),
               'team': profile['id'], 'positions': counts, 'rerolls': rerolls,
               'apothecaries': apothecaries, 'budget': budget,
               'spent': cost + rerolls * profile['reroll_cost'] + apothecaries * 50000}


def build_team(squad, rules=None, team_id=None):
    """Create a fresh playable team from one explicit coverage-squad record."""
    profile = botbowl.get_team_profile(squad['team'])
    cost = botbowl.validate_roster_selection(profile['id'], squad['positions'])
    for field, maximum in (('rerolls', 8), ('apothecaries', int(profile['apothecary']))):
        if type(squad[field]) is not int or not 0 <= squad[field] <= maximum:
            raise ValueError('Invalid ' + field)
    spent = cost + squad['rerolls'] * profile['reroll_cost'] + squad['apothecaries'] * 50000
    if spent > squad['budget']:
        raise ValueError('Squad exceeds budget')
    rules = rules or botbowl.load_rule_set('BB2025')
    if rules.name != 'BB2025':
        raise ValueError('Season 3 squads require BB2025 rules')
    team = botbowl.Team(team_id or str(uuid4()), profile['name'] + ' coverage', profile['name'],
                        treasury=squad['budget'] - spent, rerolls=squad['rerolls'],
                        apothecaries=squad['apothecaries'])
    for positional in profile['positions']:
        role = rules.get_role(positional['name'], profile['name'])
        for _ in range(squad['positions'].get(positional['id'], 0)):
            nr = len(team.players) + 1
            team.players.append(botbowl.Player(str(uuid4()), role, role.name + ' ' + str(nr), nr, team))
    if 'Team Captain' in profile.get('special_rules', []):
        candidates = [p for p in team.players if 'Big Guy' not in p.role.keywords]
        captain = next((p for p in candidates if 'Blitzer' in p.role.keywords), candidates[0])
        team.nominate_captain(captain)
    return team
