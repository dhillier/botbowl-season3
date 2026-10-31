"""Validate Season 3 teams sequentially, saving resumable local match evidence.

Run: python scripts/validate_season3_teams.py [--team amazon] [--resume DIRECTORY]
Each coverage squad plays a full eight-turn-per-half match on both sides against
the prepared Human baseline. A failure stops the run. No GitHub access is used.
"""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import botbowl  # noqa: E402
from botbowl.core.pathfinding import cython_pathfinding  # noqa: E402
from examples.season3_teams import build_team, coverage_squads  # noqa: E402
from examples.scripted_bot_example import MyScriptedBot  # noqa: E402


def source_fingerprint():
    digest = hashlib.sha256()
    digest.update(sys.version.encode())
    digest.update(Path(cython_pathfinding.__file__).read_bytes())
    paths = list((ROOT / 'botbowl').rglob('*.py')) + list((ROOT / 'botbowl').rglob('*.pyx'))
    paths += [p for p in (ROOT / 'botbowl/data').rglob('*') if p.suffix in ('.json', '.xml', '.txt')]
    paths += [Path(__file__), ROOT / 'examples/season3_teams.py', ROOT / 'examples/scripted_bot_example.py']
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).replace('\\', '/').encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class CheckedGame(botbowl.Game):
    """Keep the real scripted bot and fail on illegal actions or broken state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_steps = 0
        self.validation_actions = Counter()
        self.validation_seen_roles = set()
        self.validation_activated_roles = set()
        self.validation_trace = deque(maxlen=30)
        self.validation_max_players = Counter()

    def _one_step(self, action):
        self.validation_steps += 1
        if self.validation_steps > 150000:
            raise AssertionError('Procedure-step limit exceeded')
        if action is not None:
            self.validation_actions[action.action_type.name] += 1
            if action.action_type.name.startswith('START_') and action.player is not None:
                self.validation_activated_roles.add((action.player.team.team_id, action.player.role.name))
            self.validation_trace.append({'procedure': type(self.get_procedure()).__name__,
                                          'half': self.state.half,
                                          'home_turn': self.state.home_team.state.turn,
                                          'away_turn': self.state.away_team.state.turn,
                                          'action': action.to_json()})
        result = super()._one_step(action)
        # Check at every public decision. Airborne players intentionally have no
        # board occupant while a Throw Team-mate sequence is in flight.
        if self.state.available_actions or self.state.game_over:
            for team in self.state.teams:
                self.validation_max_players[team.team_id] = max(
                    self.validation_max_players[team.team_id], len(self.get_players_on_pitch(team)))
                for player in team.players:
                    if player.position is not None:
                        self.validation_seen_roles.add((team.team_id, player.role.name))
                        if not player.state.in_air:
                            assert self.get_player_at(player.position) is player, 'Player/board mismatch'
            for row in self.state.pitch.board:
                for player in row:
                    if player is not None:
                        assert player.position is not None and self.get_player_at(player.position) is player
            for ball in self.state.pitch.balls:
                if ball.is_carried:
                    assert self.get_ball_carrier() is not None, 'Carried ball without carrier: ' + str(self.get_procedure_names())
        return result


def run_match(squad, side, seed):
    rules = botbowl.load_rule_set('BB2025')
    team = build_team(squad, rules)
    baseline = botbowl.load_team_by_filename('human', rules)
    home, away = (team, baseline) if side == 'home' else (baseline, team)
    game = CheckedGame(squad['id'], home, away, MyScriptedBot('home'), MyScriptedBot('away'),
                       botbowl.load_config('season3-preview'), ruleset=rules, seed=seed)
    started = time.monotonic()
    result = {'squad': squad, 'side': side, 'seed': seed, 'passed': False}
    try:
        game.init()
        assert game.state.game_over, 'Match did not finish'
        assert game.state.half == 2, 'Match did not reach second half'
        assert all(t.state.turn == 8 for t in game.state.teams), 'Match did not finish normal turns'
        expected = {p.role.name for p in team.players}
        seen = {role for team_id, role in game.validation_seen_roles if team_id == team.team_id}
        assert expected <= seen, 'Positional never deployed: ' + str(sorted(expected - seen))
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        result['trace'] = list(game.validation_trace)
        result['procedures'] = game.get_procedure_names()
        print(result['error'], flush=True)
    result.update(seconds=round(time.monotonic() - started, 3), steps=game.validation_steps,
                  game_over=game.state.game_over,
                  score=[t.state.score for t in game.state.teams], half=game.state.half,
                  turns=[t.state.turn for t in game.state.teams], actions=dict(game.validation_actions),
                  roles_seen=sorted(role for team_id, role in game.validation_seen_roles if team_id == team.team_id),
                  roles_activated=sorted(role for team_id, role in game.validation_activated_roles if team_id == team.team_id),
                  max_players_on_pitch=game.validation_max_players[team.team_id],
                  team_rules_reported=dict(Counter(r.outcome_type.name for r in game.state.reports
                      if r.outcome_type.name in ('SWARMING', 'TEAM_CAPTAIN_ROLL', 'RAISED_DEAD', 'BRIBERY_AND_CORRUPTION'))),
                  skills_reported=dict(Counter(r.skill.name for r in game.state.reports if r.skill is not None)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--team', action='append', help='Roster ID, repeatable; defaults to all 30')
    parser.add_argument('--resume', type=Path, help='Reuse passing cases only when source fingerprint matches')
    parser.add_argument('--timeout', type=int, default=180, help='Seconds allowed per full match')
    parser.add_argument('--case', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.case:
        case = json.loads(args.case.read_text())
        result = run_match(case['squad'], case['side'], case['seed'])
        case.update(result)
        args.case.write_text(json.dumps(case, indent=2) + '\n', encoding='utf-8')
        return 0 if result['passed'] else 1
    output = args.resume or ROOT / 'artifacts/team-validation' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = source_fingerprint()
    catalog = botbowl.load_team_catalog()['teams']
    selected = set(args.team or [t['id'] for t in catalog])
    unknown = selected - {t['id'] for t in catalog}
    if unknown:
        parser.error('Unknown teams: ' + ', '.join(sorted(unknown)))
    report = {'fingerprint': fingerprint, 'python': sys.version,
              'scope': 'Scripted full-match integration; not tactical or exhaustive rule certification',
              'teams': [], 'passed': False}
    print('Reports: ' + str(output), flush=True)
    for profile in catalog:
        if profile['id'] not in selected:
            continue
        entry = {'id': profile['id'], 'cases': [], 'passed': False}
        report['teams'].append(entry)
        for squad in coverage_squads(profile['id']):
            for side, seed in (('home', 0), ('away', 1)):
                if source_fingerprint() != fingerprint:
                    report['error'] = 'Sources or runtime changed during validation; restart with the new fingerprint'
                    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                    print(report['error'], flush=True)
                    return 1
                case_id = squad['id'] + '--' + side
                path = output / (case_id + '.json')
                previous = json.loads(path.read_text()) if path.exists() else {}
                if previous.get('passed') and previous.get('fingerprint') == fingerprint:
                    result = previous
                else:
                    result = {'fingerprint': fingerprint, 'squad': squad, 'side': side, 'seed': seed, 'passed': False}
                    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                    with (output / (case_id + '.log')).open('w', encoding='utf-8') as stream:
                        try:
                            proc = subprocess.run([sys.executable, str(Path(__file__)), '--case', str(path)],
                                                  cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout)
                            result = json.loads(path.read_text())
                            result['exit_code'] = proc.returncode
                            result['passed'] = result['passed'] and proc.returncode == 0
                        except subprocess.TimeoutExpired:
                            result['error'] = 'Match timeout after {} seconds'.format(args.timeout)
                    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                if source_fingerprint() != fingerprint:
                    result['passed'] = False
                    result['error'] = 'Sources or runtime changed during this match; rerun required'
                    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                entry['cases'].append({'id': case_id, 'passed': result['passed'], 'seconds': result.get('seconds')})
                print(('PASS ' if result['passed'] else 'FAIL ') + case_id, flush=True)
                if not result['passed']:
                    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                    print('Stopped; inspect ' + str(path), flush=True)
                    return 1
        entry['passed'] = True
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    report['passed'] = all(t['passed'] for t in report['teams'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: {} teams'.format(len(report['teams'])), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
