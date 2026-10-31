"""Import the supplied Season 3 team sheets; requires pdfplumber for authoring only.

Usage: python scripts/import_season3_rosters.py PATH_TO_TEAMS [--output PATH]
The source PDFs and their complete extracted text are never copied into the catalog.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


# Each correction was checked against the coloured replacement and struck-out
# value on the rendered source page. Fail if a later source changes these cells.
CORRECTIONS = {
    ('Orc', 'Goblin Lineman', 5): ('3+4+', '4+'),
    ('Chaos_Renegades', 'Ogre', 7): ('Loner (4+3+)', 'Loner (3+)'),
    ('Old_World_Alliance', 'Halfling Hopeful', 0): ('0-50-3', '0-3'),
}
SHARED_LIMITS = {'Chaos_Chosen': 1, 'Chaos_Renegades': 3,
                 'Old_World_Alliance': 1, 'Underworld_Denizens': 1}
SECTIONS = {'League': 'leagues', 'Special Rules': 'special_rules',
            'Staff': 'staff', 'Star Players': 'star_players', 'Inducements': 'inducements'}


def clean(text):
    return ' '.join((text or '').replace('\u2011', '-').replace('\u2013', '-').split())


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def characteristic(value):
    if value == '-':
        return None
    if not re.fullmatch(r'\d+\+?', value):
        raise ValueError('Ambiguous characteristic: ' + value)
    return int(value.rstrip('+'))


def import_team(path):
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        texts = [p.extract_text() for p in pdf.pages]
        first = texts[0].splitlines()
        result = {'id': slug(path.stem.replace('_', ' ')), 'name': first[0],
                  'tier': int(re.search(r'TIER (\d)', texts[0]).group(1)),
                  'source': {'file': 'Teams/' + path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'url': re.search(r'https://\S+', texts[0]).group(0)},
                  'positions': [], 'shared_limits': [], 'source_corrections': []}
        shared = []
        for page_no, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                if not table or table[0][0] != 'Qty':
                    continue
                for cells in table[1:]:
                    if len(cells) != 11 or any(cell is None for cell in cells):
                        raise ValueError(f'{path.name} page {page_no}: incomplete table row {cells}')
                    cells = [clean(cell) for cell in cells]
                    match = re.fullmatch(r'(.+?)\*? \((.+)\)', cells[1])
                    if not match:
                        raise ValueError('Unknown positional syntax: ' + cells[1])
                    name, keywords = match.groups()
                    for col in (0, 5, 7):
                        key = (path.stem, name, col)
                        if key in CORRECTIONS:
                            old, new = CORRECTIONS[key]
                            if old not in cells[col]:
                                raise ValueError(f'{key}: expected correction {old!r} absent')
                            cells[col] = cells[col].replace(old, new)
                            result['source_corrections'].append(
                                {'position': name, 'page': page_no, 'column': table[0][col],
                                 'replaced': old, 'value': new})
                    qty = re.fullmatch(r'(\d+)-(\d+)', cells[0])
                    if not qty:
                        raise ValueError('Ambiguous roster limit: ' + cells[0])
                    skills = [] if cells[7] in ('', '-') else [clean(s) for s in cells[7].split('•') if clean(s)]
                    role = {'id': slug(name), 'name': name, 'min': int(qty[1]), 'max': int(qty[2]),
                            'keywords': [s.strip() for s in keywords.split(',')],
                            **{stat: characteristic(cells[i]) for i, stat in enumerate(('ma', 'st', 'ag', 'pa', 'av'), 2)},
                            'skills': skills,
                            'primary': [] if cells[8] in ('', '-') else cells[8].split(),
                            'secondary': [] if cells[9] in ('', '-') else cells[9].split(),
                            'cost': int(cells[10].rstrip('K')) * 1000, 'source_page': page_no}
                    result['positions'].append(role)
                    if '* (' in cells[1]:
                        shared.append(role['id'])
        if shared:
            result['shared_limits'].append({'positions': shared, 'max': SHARED_LIMITS[path.stem]})
        section, group = None, None
        for text in texts:
            for line in text.splitlines():
                line = clean(line).lstrip('• ').strip()
                if line in SECTIONS:
                    section, group = SECTIONS[line], None
                    result.setdefault(section, [])
                    continue
                if not section or not line or line.startswith('Blood Bowl Base'):
                    continue
                # Multi-page position tables precede the first League heading.
                if section in ('leagues', 'special_rules'):
                    if line != 'or':
                        result[section].append(line)
                else:
                    item = re.fullmatch(r'(.+?) - (\d+)K', line)
                    if item:
                        entry = {'name': item[1], 'cost': int(item[2]) * 1000}
                        if group:
                            entry['condition'] = group
                        result[section].append(entry)
                    else:
                        group = line
        staff = {entry['name']: entry['cost'] for entry in result['staff']}
        result['reroll_cost'] = staff['Re-roll']
        result['apothecary'] = 'Apothecary' in staff
        if not result['positions']:
            raise ValueError('No positionals in ' + str(path))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=Path('botbowl/data/rules/BB2025-rosters.json'))
    args = parser.parse_args()
    teams = [import_team(p) for p in sorted(args.source.glob('*.pdf'))]
    if not teams:
        parser.error('No team PDFs found')
    data = {'schema_version': 1, 'ruleset': 'BB2025',
            'status': 'data-imported-rules-validation-in-progress', 'teams': teams}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Imported {len(teams)} teams / {sum(len(t["positions"]) for t in teams)} positionals into {args.output}')


if __name__ == '__main__':
    main()
