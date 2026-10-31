"""Run the repository's CI checks on this computer without contacting GitHub."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('full', 'skills'), default='full')
    parser.add_argument('--rebuild-native', action='store_true',
                        help='Build the native extension using already-installed local dependencies')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'artifacts' / 'local-checks' / stamp
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    if args.rebuild_native:
        checks.append(('native-build', [sys.executable, 'setup.py', 'build_ext', '--inplace']))
    checks += [
        ('dependencies', [sys.executable, '-m', 'pip', 'check']),
        ('native-import', [sys.executable, '-c',
                          'from botbowl.core.pathfinding import cython_pathfinding; print(cython_pathfinding.__file__)']),
        ('fatal-lint', [sys.executable, '-m', 'flake8', '.', '--count', '--select=E9,F63,F7,F82',
                       '--extend-exclude=.venv,venv,env,artifacts,build,.git',
                       '--show-source', '--statistics']),
        ('web-bundle', [sys.executable, 'scripts/build_web_js.py', '--check'])]
    tests = [] if args.suite == 'full' else [str(p.relative_to(ROOT)) for p in
                                          sorted((ROOT / 'tests').rglob('test_season3*.py'))]
    checks.append(('pytest', [sys.executable, '-m', 'pytest', '-q',
                              '--junitxml=' + str(output / 'pytest.xml')] + tests))
    report = {'python': sys.version, 'executable': sys.executable, 'suite': args.suite,
              'started_utc': stamp, 'checks': [], 'passed': False}
    for name, command in checks:
        print('Running ' + name + ' locally...', flush=True)
        started = time.monotonic()
        log = output / (name + '.log')
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=str(ROOT), stdout=stream, stderr=subprocess.STDOUT)
        report['checks'].append({'name': name, 'exit_code': result.returncode,
                                 'seconds': round(time.monotonic() - started, 2), 'log': str(log)})
        if result.returncode:
            print(log.read_text(encoding='utf-8', errors='replace')[-10000:])
            break
    report['passed'] = len(report['checks']) == len(checks) and all(
        item['exit_code'] == 0 for item in report['checks'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(('PASS' if report['passed'] else 'FAIL') + ': ' + str(output))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
