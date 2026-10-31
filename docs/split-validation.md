# Community extraction validation

Validated on Windows with CPython 3.11 and a freshly installed, dedicated environment on 31 October 2026. The Cython extension was rebuilt from this checkout with Visual Studio C++ Build Tools. PyTorch is not required or installed in the community environment.

- Full suite: **1,429 passed**, 116 existing dependency/Gym warnings.
- New extraction coverage exercises direct/route environments with either learner side and invalid side configurations.
- The existing handoff scenarios check native/Python pathfinders, receiver Catch, marking, Rain, shared re-roll budgets, serialization and observations.
- Complete scripted-versus-scripted preview (`--seed 0`) finishes normally.
- Four complete masked-agent matches against scripted, using home/away learner and direct/route interfaces, finish without truncation. Every external decision belongs to the selected learner.
- Flask's root page returns HTTP 200; the tracked web JavaScript bundle matches its sources.
- Dependency consistency and fatal-error source lint pass.
- Original upstream commit `3e550bda3666c39efe478fb9465646af24576665` remains an ancestor. Custom-learning history is excluded from the community branch.

These counts describe the initial extraction from research snapshot `bb07205b17f6adf69eee568bdf437b9f7537523e`. A later CI run exposed an inherited player-swap rollback defect; two deterministic regressions fail before the correction and pass afterward in both editions. The correction passes all 282 forward-model and related Season 3 acceptance/action/flow checks. Current full-suite results are available in GitHub Actions. Downstream research pins the community runtime and receives this correction as an explicit update.

Test results demonstrate integration and regression coverage for the declared fixed-Human scope, not complete tabletop fidelity or agent strength. Coach playtesting and digital-ruler review remain open.

Repeat the checks with the commands in [README.md](../README.md). The repository also runs the core suite under Python 3.8, 3.9, 3.10 and 3.11 in GitHub Actions.
