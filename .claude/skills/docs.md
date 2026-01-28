# Documentation and Versioning Guide

This skill explains how to write documentation and perform versioning for the AIOS project.

## Versioning

### Semantic Versioning

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** (X.0.0): Breaking changes, incompatible API changes
- **MINOR** (0.X.0): New features, backward-compatible additions
- **PATCH** (0.0.X): Bug fixes, small improvements, documentation updates

### Version Location

The single source of truth for version is in `pyproject.toml`:

```toml
[project]
version = "0.8.12"
```

### When to Bump Versions

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| New feature | Minor | 0.7.0 → 0.8.0 |
| Bug fix | Patch | 0.8.0 → 0.8.1 |
| Security fix | Patch | 0.8.1 → 0.8.2 |
| Documentation only | Patch | 0.8.2 → 0.8.3 |
| Breaking change | Major | 0.8.0 → 1.0.0 |
| Multiple features in one release | Minor | 0.7.0 → 0.8.0 |

## Changelog

### Format

The changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format in `CHANGELOG.md`.

### Structure

```markdown
## [VERSION] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes in existing functionality

### Fixed
- Bug fixes

### Removed
- Removed features

### Security
- Security-related changes

### Tests
- Test-related notes (optional)
```

### Section Guidelines

#### Added
Use for new features. Group related items under `####` subheadings:

```markdown
### Added

#### Feature Name
- Bullet points describing the feature
- Include file locations where relevant
- List new classes, methods, or functions added
```

#### Changed
Document modifications to existing code:

```markdown
### Changed
- `aios/file.py` — description of what changed
- `aios/other.py` — another change
```

#### Security
For security-related changes, use clear severity markers:

```markdown
### Security

#### Critical: Description
- **BREAKING**: Note if it's a breaking change
- Detailed explanation of what was fixed
- What the vulnerability was
```

#### Tests
Document test additions at the end:

```markdown
### Tests
- Total tests: 490 passed, 10 skipped
- New tests in `tests/test_feature.py`: 15
```

### Entry Detail Level

Each changelog entry should include:

1. **What** was added/changed/fixed
2. **Where** (file paths with line numbers for significant changes)
3. **Why** (for non-obvious changes)
4. **How** (brief technical details for complex features)

### Example Entry

```markdown
## [0.8.12] - 2026-01-28

### Added

#### Double-Tap Tab Shows All Commands
- Pressing Tab on empty input now displays all available commands with their descriptions
- Updated bottom toolbar hint: "Tab Tab show all commands"
- Enhanced discoverability of shell commands for new users
```

## Documentation Files

### Project Documentation Structure

| File | Purpose |
|------|---------|
| `README.md` | Project overview, installation, quick start |
| `CHANGELOG.md` | Version history and release notes |
| `CONTRIBUTING.md` | Contribution guidelines, code style |
| `ARCHITECTURE.md` | System design, component overview |
| `SECURITY.md` | Security policy, reporting vulnerabilities |
| `*.md` (feature docs) | Feature-specific documentation |

### Feature Documentation

For significant features, create dedicated documentation files:

- `PLUGINS.md` — Plugin system guide
- `CACHING.md` — Caching system documentation
- `SESSIONS.md` — Session management guide
- `CREDENTIALS.md` — Credential management guide

### Code Documentation

Follow Google-style docstrings:

```python
def process_command(
    command: str,
    timeout: int = 30,
    require_confirmation: bool = True
) -> CommandResult:
    """Process and execute a shell command safely.

    Args:
        command: The shell command to execute.
        timeout: Maximum execution time in seconds.
        require_confirmation: Whether to prompt user for dangerous commands.

    Returns:
        CommandResult containing output, errors, and execution metadata.

    Raises:
        CommandBlockedError: If command matches forbidden patterns.
        TimeoutError: If command exceeds timeout limit.
    """
```

## Release Checklist

When releasing a new version:

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with new version section
3. **Run tests**: `pytest tests/ -v`
4. **Rebuild Docker** (if applicable): `docker compose down && docker compose up -d --build`
5. **Verify version**: Check version displays correctly
6. **Commit**: Use format `Release vX.Y.Z: Brief description`

### Commit Message Format

```
Release v0.8.12: Double-tap Tab shows all commands

- Added double-tap Tab feature to show all commands with descriptions
- Updated toolbar hint
- Updated tests
```

## Quick Reference

### Bump Patch Version
```bash
# 1. Edit pyproject.toml version
# 2. Add changelog entry
# 3. Run tests
pytest tests/ -v
# 4. Rebuild and verify
docker compose down && docker compose up -d --build
```

### Changelog Entry Template
```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- Feature description

### Changed
- `file.py` — change description

### Fixed
- Bug fix description
```
