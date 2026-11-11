# Git Commit & Verification Guidelines

Generate structured Conventional Commit messages only after local verification passes.

## 1. Pre-Commit Verification (Mandatory)

```bash
./venv/bin/ruff check --select F,E9 .
./venv/bin/python manage.py check --fail-level WARNING
./venv/bin/python manage.py test --keepdb
codegraph sync
```

## 2. Commit Structure

```text
<type>(<scope>): <concise imperative subject in lowercase, max 72 chars>

<Motivation and context explaining why this change was made and what changed.>

- Bullet points detailing modified files, components, and invariants
- Any migration, configuration, or test coverage updates
```

## 3. Types & Scopes

- **Types**: `feat`, `fix`, `refactor`, `perf`, `test`, `chore`, `docs`
- **Scopes**: `pftracker`, `tracker`, `portfolio`, `expenses`, `jewellery`, `mcp`, `ui`, `agents`, `docs`
- **Quality**: Use imperative mood ("add stage timeout guard", not "added..."), never write vague one-line messages, and always include a descriptive body.
