"""Rebuild the tracked web bundle without the legacy Node/Gulp dependencies.

Equivalent to the gulpfile's scripts task: sorted source files joined by a
newline. Run from any directory; use --check to detect a stale bundle.
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    static = Path(__file__).resolve().parents[1] / 'botbowl' / 'web' / 'static'
    bundle = static / 'dist' / 'js' / 'botbowl.js'
    content = b'\n'.join(path.read_bytes() for path in sorted((static / 'js').glob('*.js')))
    if args.check:
        if bundle.read_bytes() != content:
            raise SystemExit('Web bundle is stale; run python scripts/build_web_js.py')
        print('Web bundle matches the JavaScript sources.')
    else:
        bundle.write_bytes(content)
        print('Rebuilt botbowl/web/static/dist/js/botbowl.js')


if __name__ == '__main__':
    main()
