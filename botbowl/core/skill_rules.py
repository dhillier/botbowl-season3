"""Season 3 skill metadata. Availability is separate from effect implementation."""
import json
from pathlib import Path

from botbowl.core.table import Skill


with (Path(__file__).resolve().parents[1] / 'data/rules/BB2025-skills.json').open(encoding='utf-8') as source:
    SKILL_RULES = {Skill[row['id']]: row for row in json.load(source)['skills']}

ACTIVE_SKILLS = frozenset(skill for skill, row in SKILL_RULES.items() if row['availability'] == 'active')
PRONE_SKILLS = frozenset((Skill.JUMP_UP,))


def target_parameter(player, skill, default):
    value = player.skill_parameter(skill)
    if value is None:
        return default
    if not isinstance(value, str) or not value.endswith('+') or not value[:-1].isdigit():
        raise ValueError(f'{skill.name} requires a target-number parameter, got {value!r}')
    result = int(value[:-1])
    if not 2 <= result <= 6:
        raise ValueError(f'{skill.name} target must be between 2+ and 6+')
    return result
