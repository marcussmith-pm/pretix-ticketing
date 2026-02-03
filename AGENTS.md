# AGENTS.md

This file contains guidelines for AI agents working in the pretix-ticketing repository.

## Project Overview

This is a pretix-based ticketing system project. Pretix is a Django-based ticket shop application for conferences, festivals, concerts, and other events. This repository uses the pretix framework and follows its coding conventions.

## Build/Lint/Test Commands

### Development Server
```bash
python manage.py runserver
```
Access the admin panel at http://localhost:8000/control/

### Running Tests
```bash
# Run all tests
py.test

# Run single test file
py.test path/to/test_file.py

# Run specific test function
py.test path/to/test_file.py::test_function

# Run tests in parallel (faster)
py.test -n NUM  # Replace NUM with number of CPU cores
```

### Code Quality Checks
```bash
# Lint Python code
flake8 .

# Check import ordering
isort -c .

# Django checks
python manage.py check

# Run all checks before committing
flake8 . && isort -c . && python manage.py check && py.test
```

### Database & Static Files
```bash
# Run database migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create migrations after model changes
python manage.py makemigrations
```

### Frontend Assets
```bash
# Install npm dependencies
make npminstall

# Update static assets
python -m pretix updateassets
```

### Translation/Localization
```bash
# Generate translation strings
make localegen

# Compile translation files
make localecompile
```

### Periodic Tasks
```bash
# Run periodic tasks (e.g., sendmail rules)
python manage.py runperiodic
```

## Code Style Guidelines

### Python Code Style
- Follow PEP 8 standard (https://www.python.org/dev/peps/pep-0008/)
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 119 characters
- Use flake8 for automatic style checking

### Imports
- Use isort to automatically sort imports
- Run `isort <directory>` to fix import ordering
- Import order: standard library → third-party → local imports
- Each group separated by blank line

### Django Conventions
- Use class-based views where appropriate
- Follow Django coding style (https://docs.djangoproject.com/en/stable/internals/contributing/writing-code/coding-style/)
- Model classes should be verbose but concise
- Use descriptive method names that indicate the action

### Internationalization (i18n)
- Mark ALL user-facing strings for translation using Django's translation functions
- Use `gettext_lazy` (imported as `_`) for class attributes
- Use `gettext` (imported as `_`) for function calls
- Example:
  ```python
  from django.utils.translation import gettext_lazy as _
  
  class MyModel(models.Model):
      name = models.CharField(verbose_name=_("Name"), max_length=100)
  
  def my_view(request):
      message = _("Welcome to our ticket shop")
  ```

### Testing
- Write tests using pytest-style test functions
- Use raw `assert` statements
- Use fixtures to prevent repetitive code
- New test files must use pytest style (not unittest)
- Tests should be isolated and not depend on execution order

### Naming Conventions
- Python classes: PascalCase (e.g., `TicketOrder`, `EventManager`)
- Functions and methods: snake_case (e.g., `process_payment`, `create_order`)
- Variables: snake_case
- Constants: UPPER_CASE (e.g., `MAX_TICKETS_PER_ORDER`)
- Model field names: snake_case, verbose enough to be self-documenting

### Error Handling
- Use Django's built-in validation where possible
- Raise appropriate Django exceptions (ValidationError, PermissionDenied)
- Log errors using Python's logging module
- Provide user-friendly error messages (always translated)

### API/Backend Code
- Use pretix's service layer for business logic
- Leverage pretix's built-in permission system
- Follow pretix's signal system for event-driven code
- Use SettingsSandbox for plugin settings

### Documentation
- Add docstrings to all non-trivial classes and methods
- Use triple-quoted strings for docstrings
- Document parameters, return values, and raised exceptions

### Commit Messages
- Capitalize subject line
- Don't end subject with period
- Use imperative mood ("Add feature", not "Added feature")
- Subject line should be short and descriptive
- Add optional body separated by blank line
- Body should explain WHAT and WHY, not HOW
- Prefix with feature name if changes are scoped (e.g., "API: Add endpoint", "Stripe: Fix bug")
- Reference GitHub issues: "Fix #1234 – Crash in order list" or "Refs #1234 – Partial fix"

### Pull Request Guidelines
- Start with a pull request (most commits should be PRs)
- Use "Squash and merge" for multiple commits unless they have value
- Use "Rebase and merge" to keep individual commits
- Avoid merge commits
- Ensure all lint checks pass before submission

### Security
- Never commit secrets, API keys, or sensitive data
- Use environment variables for configuration
- Validate all user input
- Follow Django's security best practices

### File Organization
- Main code lives in `src/pretix/` directory
- Plugins typically in `src/pretix/plugins/`
- Templates follow Django template conventions
- Static assets in appropriate static directories

### Plugin Development (if applicable)
- Follow pretix plugin structure
- Register plugin in appropriate registries
- Implement proper isolation (don't pollute global namespace)
- Mark all strings for translation
- Follow plugin quality checklist from pretix docs

### Git Workflow
- Feature branches should be created from main branch
- Rebase before merging if PR is old to avoid conflicts
- Never commit directly to main/master branch
- Run pre-commit hooks to catch style issues early

### Performance
- Use Django's select_related and prefetch_related for query optimization
- Avoid N+1 query problems
- Cache expensive operations appropriately
- Use database indexes for frequently queried fields

### Common Gotchas
- Always run migrations after model changes
- Collect static files after adding CSS/JS
- Restart dev server after Python code changes
- Test with different user permission levels
- Consider time zones when handling dates/times
- Use pretix's time_machine_now() for time-dependent tests

### Recommended Pre-commit Hook
```bash
#!/bin/bash
source ../env/bin/activate
for file in $(git diff --cached --name-only | grep -E '\.py$' | grep -Ev "migrations|testutils/settings\.py|pretix/settings\.py")
do
  git show ":$file" | flake8 - --stdin-display-name="$file" || exit 1
  git show ":$file" | isort -c - | grep ERROR && exit 1 || true
done
```

## Additional Resources
- Official pretix documentation: https://docs.pretix.eu/dev/
- Django documentation: https://docs.djangoproject.com/
- Pytest documentation: https://docs.pytest.org/
