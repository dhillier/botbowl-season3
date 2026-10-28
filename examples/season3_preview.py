"""Run a standalone fixed-Human match using the incomplete Season 3 preview.

From the repository root: python -m examples.season3_preview --seed 0
This checks engine/bot integration; it is not a rules-fidelity certification.
"""
import argparse

import botbowl
from examples.scripted_bot_example import MyScriptedBot


def run_match(seed=0):
    config = botbowl.load_config('season3-preview')
    rules = botbowl.load_rule_set(config.ruleset)
    home = botbowl.load_team_by_filename('human', rules)
    away = botbowl.load_team_by_filename('human', rules)
    game = botbowl.Game(
        'season3-preview', home, away, MyScriptedBot('home'), MyScriptedBot('away'),
        config, ruleset=rules, seed=seed)
    game.init()
    return game


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    print('Season 3 migration preview: incomplete rules; see docs/season3-migration.md')
    match = run_match(args.seed)
    print(f'Finished: {match.state.game_over}; '
          f'score {match.state.home_team.state.score}–{match.state.away_team.state.score}')
