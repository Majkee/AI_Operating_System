# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of AIOS seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Email your findings to [security contact - update this]
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours of your report
- **Status Update**: Within 7 days with our assessment
- **Resolution**: We aim to fix critical issues within 30 days

### Safe Harbor

We consider security research conducted in good faith to be authorized. We will not pursue legal action against researchers who:

- Make a good faith effort to avoid privacy violations and data destruction
- Do not exploit vulnerabilities beyond what is necessary to demonstrate them
- Report vulnerabilities promptly and do not disclose them publicly until fixed

## Security Features

AIOS includes multiple layers of security:

### Command Filtering

- **Forbidden Commands**: Catastrophic operations are always blocked (e.g., `rm -rf /`, `mkfs`, fork bombs)
- **Dangerous Commands**: Risky operations require explicit user confirmation
- **Moderate Commands**: Potentially impactful operations are flagged and explained

### File System Protection

- **Path Sandboxing**: Operations restricted to user home directory and /tmp by default
- **Automatic Backups**: Files are backed up before modification
- **Size Limits**: Prevents reading/writing excessively large files

### Execution Safety

- **Timeout Limits**: Commands are killed after configurable timeout (default 30s)
- **Process Isolation**: Commands run in separate process groups
- **Critical Package Protection**: Prevents removal of essential system packages

### Audit Logging

- All operations are logged with timestamps
- Logs include command details, outcomes, and user context
- Configurable log retention and verbosity

## Configuration

Security settings can be customized in `~/.config/aios/config.toml`:

```toml
[safety]
require_confirmation = true     # Require confirmation for dangerous operations
# Add custom patterns to block or flag
```

## Known Limitations

1. **Sudo Operations**: When sudo is used, AIOS inherits elevated privileges. Use with caution.
2. **API Key Storage**: The Anthropic API key is stored in plaintext in config or environment variables.
3. **Network Access**: Commands with network access are not sandboxed beyond standard user permissions.

## Security Best Practices

When using AIOS:

1. **Review before confirming**: Always read what AIOS proposes before confirming dangerous operations
2. **Use least privilege**: Run AIOS as a regular user, not root
3. **Protect your API key**: Don't commit `.env` files or share your API key
4. **Monitor audit logs**: Regularly review `/var/log/aios/audit.log` or configured log path
5. **Keep updated**: Use the latest version for security patches
