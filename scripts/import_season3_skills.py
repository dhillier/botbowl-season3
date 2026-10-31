"""Import skill identity/status metadata from a supplied rules PDF, not its prose."""
import argparse
import hashlib
import json
import re
from pathlib import Path


ALIASES = {'SIDESTEP': 'SIDE_STEP', 'BLOODLUST': 'BLOOD_LUST',
           'BALL_&_CHAIN': 'BALL_AND_CHAIN', 'TIMMM_BER!': 'TIMMMBER'}
CATEGORIES = {'AGILITY', 'DEVIOUS', 'GENERAL', 'MUTATION', 'PASSING', 'STRENGTH', 'TRAITS'}


def main():
    import pdfplumber

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=Path('botbowl/data/rules/BB2025-skills.json'))
    args = parser.parse_args()
    rows, category = [], None
    with pdfplumber.open(args.source) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            for line in page.extract_text().splitlines():
                line = line.strip()
                if line in CATEGORIES:
                    category = line.lower()
                match = re.fullmatch(r'([A-Z0-9 &!()\-+]+)(\*)? \((ACTIVE|PASSIVE)\)', line)
                if not match:
                    continue
                name, mandatory, availability = match.groups()
                parameter = re.search(r' \((X\+?)\)', name)
                key = re.sub(r' \(X\+?\)', '', name).replace('-', '_').replace(' ', '_')
                rows.append({'id': ALIASES.get(key, key), 'name': name.title(), 'category': category,
                             'availability': availability.lower(), 'mandatory': bool(mandatory),
                             'parameter': parameter[1] if parameter else None, 'source_page': number})
    data = {'schema_version': 1, 'ruleset': 'BB2025',
            'source': {'file': args.source.name, 'sha256': hashlib.sha256(args.source.read_bytes()).hexdigest()},
            'skills': rows}
    args.output.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(rows)} skill/trait definitions')


if __name__ == '__main__':
    main()
