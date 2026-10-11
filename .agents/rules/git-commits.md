# Git Commit Guidelines

Antigravity agents must always generate professional, descriptive, and structured Git commit messages adhering to Conventional Commits:

## 1. Commit Structure

Every commit message must follow this structure:

```
<type>(<scope>): <concise imperative subject in lowercase, max 72 chars>

<Detailed explanation of why this change was made and what was altered.
Provide full context for reviewers and future maintainers.>

- Bullet points highlighting key file and feature modifications
- Specific additions, removals, or behavior changes
- Any migration, configuration, or testing notes
```

## 2. Commit Types

- `feat`: A new user-facing feature or enhancement
- `fix`: A bug fix
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding missing tests or correcting existing tests
- `chore`: Maintenance, dependency updates, tooling, config changes
- `docs`: Documentation updates only

## 3. Scope Guidelines

Always specify the affected module or app in parentheses:
- `portfolio`: Changes to portfolio models, emails, views, or calculators
- `tracker`: Changes to savings tracker, transactions, or core tracker views
- `expenses`: Changes to expense logging, categories, or analytics
- `jewellery`: Changes to gold/silver jewellery portfolio
- `agents`: Changes to Antigravity rules, skills, hooks, or MCP configurations
- `ui`: Global styling, base templates, or DaisyUI themes

## 4. Message Quality Requirements

- **Imperative mood**: "add liquid breakdown", not "added liquid breakdown" or "adds liquid breakdown".
- **No lazy or vague commits**: Never use single-line vague messages like "update", "fix bug", "changes", "wip", or "final commit".
- **Always include a body**: Detail *why* the change was made and list the components affected in bullet points.
