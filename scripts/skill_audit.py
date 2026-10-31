"""List Season 3 skill certification gaps separately from passing unit tests."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / 'botbowl/data/rules/BB2025-skill-audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    pending = [row for row in audit['skills'] if row['status'] != 'validated']
    print('{} skills and traits; {} still require certification.'.format(len(audit['skills']), len(pending)))
    for row in pending:
        print('{}: {} — {}'.format(row['id'], row['status'], row['remaining']))
    return int(args.require_complete and bool(pending))


if __name__ == '__main__':
    raise SystemExit(main())
