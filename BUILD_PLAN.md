# Community Season 3 roadmap

This repository maintains the reusable BotBowl Season 3 framework. Agent training and experimental policies belong in downstream projects.

## Implemented scope

The fixed match uses two Human teams with two Blitzers, one Thrower, two Catchers and seven Linemen each, on the normal full pitch. Season 3 characteristics, applicable starting skills, core match rules, pathfinding and web/agent interfaces are implemented for this selection. See [coverage](docs/season3-migration.md) and [acceptance](docs/season3-acceptance.md).

## Release gates

1. Representative coach playtesting of the declared fixed-roster scope.
2. Review the documented whole-square digital interception ruler and other project interpretations.
3. Keep engine, native/Python pathfinders, observations, legal masks and scripted opponents consistent under regression tests and complete-match smoke checks.
4. Document remaining limitations before changing defaults or tagging a release.

League play, progression, other rosters, optional player types, team building, graphical redesign and a strong learned opponent are outside the initial scope. New content needs its own rule coverage and interaction tests.

## Contribution order

Contribute engine and generic interface corrections here first, then update downstream engine pins. Keep policies, teaching heuristics, curricula, machine-specific launch scripts and study reports outside this repository. Changing a rule or observation requires reviewing the interface version and downstream compatibility.
