# Contributing

Thanks for contributing to Datamosh GUI.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run app:

```bash
python3 main.py
```

Run tests:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

## Code Organization

- UI and app orchestration: `gui/`
- Core AVI manipulation engine: `mosh.py`
- Tests: `tests/`
- Historical reference code only: `legacy/`

Keep GUI logic in `gui/` and avoid changing `mosh.py` unless the change is required and validated.

## Style

- Follow PEP 8 with 4-space indentation.
- Prefer explicit types in changed/new code.
- Use `snake_case` for functions/variables, `PascalCase` for Qt classes.

## Commit Messages

Match the existing history style:

- Short, imperative subject line
- Example: `Fix timeline duration after frame duplication`

## Pull Requests

Include:

1. What changed and why
2. Validation steps you ran (commands)
3. Screenshots/video for UI changes
4. Linked issue(s), if applicable

PRs touching timeline behavior should include at least one focused test update or new test.

## Security and Privacy

Do not commit:

- API keys, tokens, credentials, private keys
- Personal machine paths or local config dumps
- Sample media that includes sensitive/private content

See `SECURITY.md` for disclosure guidance.
