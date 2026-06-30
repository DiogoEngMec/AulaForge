# Quality assurance

## Required checks

- `pytest`
- `ruff check .`
- `mypy src` when type coverage is ready

## Manual review points

- Does each phase stay in scope?
- Does batch mode avoid manual prompts?
- Are errors logged without stopping the whole course?
- Are intermediate files saved?
- Are secrets excluded from Git?
- Are tests covering discovery, ordering and checkpoints?
