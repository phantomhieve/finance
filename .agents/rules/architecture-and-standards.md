# Architecture & Code Standards

1. **Python & Django Conventions**:
   - Python 3.14 + Django 6.0 compatibility.
   - Clean separation of concerns:
     - Models in `<app>/models.py` with descriptive docstrings and `__str__` methods.
     - Business logic, external API integrations, and heavy aggregations in `<app>/services.py`.
     - Forms in `<app>/forms.py` using Crispy Forms with Bootstrap 5 template pack.
     - Views in `<app>/views.py` using appropriate permission and feature decorators (`@login_required`, `_require_role`, `_require_feature`, `_vault_gate`).
     - Background commands in `<app>/management/commands/`.

2. **Database & Migration Hygiene**:
   - Always create and commit migrations when modifying Django models (`python manage.py makemigrations <app>`).
   - Use `django_cleanup` for automatic deletion of obsolete media files.
   - Use soft-delete / tombstones where external synchronization requires idempotency (e.g. `expenses.Expense.is_deleted`).

3. **MCP Tooling & Audit**:
   - Every mutation exposed via the MCP server (`mcp_server/server.py`) MUST invoke audit loggers (`log_create`, `log_update`, `log_delete`) in `mcp_server.audit`.
   - Write tools must strictly require the `write` OAuth scope and belong to the primary account holder.
