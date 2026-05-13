# Utility Scripts

This folder contains professional utility scripts for managing and testing your Django application. All scripts support command-line arguments and include built-in help.

## Quick Reference

```bash
# Delete User
python scripts/delete_user.py -e user@example.com           # Preview (safe)
python scripts/delete_user.py -e user@example.com --no-dry-run  # Actually delete

# Redis Check
python scripts/redis_check.py                               # Test from .env settings
python scripts/redis_check.py -H redis.example.com -p 6379  # Test specific instance

# Email Test
python scripts/email_test.py --dry-run                      # Preview (safe)
python scripts/email_test.py -t your@email.com              # Send test emails
```

---

## 🗑️ delete_user.py

Safely deletes a user and all related objects using Django's cascade deletion rules.

### Features
- Preview mode by default (dry-run)
- Shows all objects that will be deleted
- Requires explicit confirmation
- Atomic transaction (all-or-nothing)
- Detailed deletion summary

### Usage

```bash
# Preview what would be deleted (safe, default)
python scripts/delete_user.py --email user@example.com
python scripts/delete_user.py -e user@example.com

# Actually delete the user (requires confirmation)
python scripts/delete_user.py -e user@example.com --no-dry-run

# Delete without confirmation prompt (dangerous!)
python scripts/delete_user.py -e user@example.com --no-dry-run --yes
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--email EMAIL` | `-e` | Email address of user to delete (required) |
| `--dry-run` | | Preview deletion without executing (default) |
| `--no-dry-run` | | Actually perform the deletion |
| `--yes` | `-y` | Skip confirmation prompt (use with caution) |
| `--help` | `-h` | Show help message |

### Example Output

```
Delete User Script
==================
Email: test@example.com
Mode: DRY RUN (preview only)

User: id=42 username=test@example.com email=test@example.com

Objects to be deleted
=====================
users.loginhistory: 15
users.profile: 1
auth.user: 1

Dry run complete. No data was deleted.
To actually delete, run with --no-dry-run
```

### Safety Features

- **Dry-run by default**: Must explicitly use `--no-dry-run` to delete
- **Confirmation required**: Must type exact confirmation string
- **Shows preview**: Always shows what will be deleted first
- **Atomic transaction**: Either all objects are deleted or none

---

## 🔌 redis_check.py

Validates Redis configuration and tests connectivity for external Redis instances.

### Features
- Tests DNS resolution and TCP connectivity
- Validates Redis PING, SET, GET, TTL operations
- Tests Django cache backend
- Works with .env settings or CLI overrides
- Detailed diagnostics for troubleshooting

### Usage

```bash
# Test using settings from .env
python scripts/redis_check.py

# Test specific Redis instance
python scripts/redis_check.py --host redis.example.com --port 6379
python scripts/redis_check.py -H redis.example.com -p 6379

# Test with password
python scripts/redis_check.py -H redis.example.com -P mypassword

# Test localhost Redis (for development)
python scripts/redis_check.py -H localhost --allow-localhost

# Skip Django cache test
python scripts/redis_check.py --skip-cache
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--host HOST` | `-H` | Redis host (default: from settings) |
| `--port PORT` | `-p` | Redis port (default: from settings) |
| `--password PASS` | `-P` | Redis password (default: from settings) |
| `--allow-localhost` | | Allow testing localhost Redis |
| `--skip-cache` | | Skip Django cache backend test |
| `--help` | `-h` | Show help message |

### Example Output

```
Redis Connection Test
=====================
Validating Redis configuration
Redis host: redis.example.com
Redis configuration check passed.

DNS / TCP diagnostics
Target host: redis.example.com
Target port: 6379
DNS resolved 1 address(es): 203.0.113.50
TCP connect ok: 203.0.113.50:6379 (45ms)

Redis PING ok (52ms)
SET/GET ok. key=redis_check:test:1702567890 value=b'ok' ttl=30

Testing Django cache backend
Cache backend: django_redis.cache.RedisCache
Django cache set/get ok.

Redis Connection Test Complete
```

### Use Cases

- **Before deployment**: Verify Redis connectivity to production instance
- **Development**: Test localhost Redis with `--allow-localhost`
- **Troubleshooting**: Get detailed diagnostics on connection failures
- **CI/CD**: Validate Redis in automated pipelines

---

## 📧 email_test.py

Renders and optionally sends all email templates with dummy data for testing.

### Features
- Auto-discovers all email templates
- Renders with realistic dummy data
- Supports dry-run mode (render without sending)
- Filter templates by name
- Tests both HTML and text alternatives
- Custom sender/recipient support

### Usage

```bash
# Dry run (preview only, safe)
python scripts/email_test.py --dry-run

# Send test emails to yourself
python scripts/email_test.py --to your@email.com
python scripts/email_test.py -t your@email.com

# Test only password-related templates
python scripts/email_test.py -t your@email.com --only password

# Test specific template
python scripts/email_test.py -t your@email.com --only "ip_changed"

# Custom sender and recipient
python scripts/email_test.py -t recipient@example.com -f sender@example.com
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--to EMAIL` | `-t` | Recipient email (required unless --dry-run) |
| `--from EMAIL` | `-f` | Sender email (default: from settings) |
| `--dry-run` | | Render only (do not send emails) |
| `--only SUBSTRING` | | Filter templates by name substring |
| `--help` | `-h` | Show help message |

### Example Output

```
Email Template Test
===================
Renders email templates with dummy context and optionally sends them.

Templates to test
=================
account/email/email_confirmation_message.html
account/email/password_reset_key_message.html
accounts/ip_changed.html

Mode: LIVE (emails will be sent to your@email.com)

Rendering: account/email/email_confirmation_message.html
Render ok
HTML length: 2456
Text length: 342
Sent to your@email.com

Email Template Test Complete
```

### Use Cases

- **After template changes**: Verify templates render correctly
- **Before production**: Test SMTP configuration
- **Development**: Preview email designs without sending
- **QA**: Send test emails to verify end-to-end flow

---

## Common Workflows

### Testing Email Configuration

After setting up SMTP settings in `.env`:

```bash
# Step 1: Preview templates (safe)
python scripts/email_test.py --dry-run

# Step 2: Send test to yourself
python scripts/email_test.py -t your@email.com

# Step 3: Test specific template if issues
python scripts/email_test.py -t your@email.com --only "password_reset"
```

### Testing Redis Connection

Before deploying to production:

```bash
# Test production Redis
python scripts/redis_check.py -H prod-redis.example.com -p 6379 -P $REDIS_PASSWORD

# Or use settings from .env
export REDIS_HOST=prod-redis.example.com
export REDIS_PORT=6379
export REDIS_PASSWORD=yourpassword
python scripts/redis_check.py
```

### Cleaning Up Test Users

After testing registration flow:

```bash
# Step 1: Preview what will be deleted
python scripts/delete_user.py -e test@example.com

# Step 2: Review the output, then delete
python scripts/delete_user.py -e test@example.com --no-dry-run

# For automation (skip confirmation)
python scripts/delete_user.py -e test@example.com --no-dry-run --yes
```

---

## Script Features

### Professional CLI Interface

All scripts support:
- **Short and long options**: `-e` or `--email`
- **Built-in help**: `--help` or `-h`
- **Exit codes**: 0 for success, non-zero for errors
- **Proper error handling**: Keyboard interrupts, exceptions
- **Colorized output**: Using `utils.text_output` helpers

### Example Help Output

```bash
$ python scripts/delete_user.py --help

usage: delete_user.py [-h] -e EMAIL [--dry-run] [--no-dry-run] [-y]

Safely delete a user and all related objects using Django cascade deletion.

options:
  -h, --help            show this help message and exit
  -e EMAIL, --email EMAIL
                        Email address of the user to delete
  --dry-run            Preview deletion without executing (default)
  --no-dry-run         Actually perform the deletion
  -y, --yes            Skip confirmation prompt (use with caution)

Examples:
  # Preview what would be deleted (safe)
  python scripts/delete_user.py --email user@example.com

  # Actually delete the user
  python scripts/delete_user.py --email user@example.com --no-dry-run

  # Delete without confirmation (dangerous!)
  python scripts/delete_user.py -e user@example.com --no-dry-run --yes
```

---

## Running Scripts

### From Project Root

All scripts are designed to be run from the project root:

```bash
# Good ✓
python scripts/delete_user.py -e user@example.com

# Bad ✗ (wrong working directory)
cd scripts && python delete_user.py -e user@example.com
```

### Making Executable (Unix/Linux/Mac)

Scripts include shebang lines and can be run directly:

```bash
# Make executable
chmod +x scripts/*.py

# Run directly
./scripts/delete_user.py -e user@example.com
./scripts/redis_check.py
./scripts/email_test.py --dry-run
```

### Windows

On Windows, always use Python explicitly:

```bash
python scripts/delete_user.py -e user@example.com
python scripts/redis_check.py
python scripts/email_test.py --dry-run
```

---

## Integration with CI/CD

### Testing Redis in CI

```bash
#!/bin/bash
# Run in CI pipeline before deployment

set -e  # Exit on error

echo "Testing Redis connectivity..."
python scripts/redis_check.py -H $REDIS_HOST -P $REDIS_PASSWORD

echo "Redis check passed!"
```

### Testing Email Templates in CI

```bash
#!/bin/bash
# Validate all templates render without errors

set -e

echo "Testing email templates..."
python scripts/email_test.py --dry-run

echo "All templates rendered successfully!"
```

### Cleanup Script

```bash
#!/bin/bash
# Delete test users after integration tests

TEST_USERS=(
    "test1@example.com"
    "test2@example.com"
    "test3@example.com"
)

for email in "${TEST_USERS[@]}"; do
    echo "Deleting $email..."
    python scripts/delete_user.py -e "$email" --no-dry-run --yes || true
done

echo "Cleanup complete!"
```

---

## Troubleshooting

### "No module named 'django'"
**Solution**: Activate virtual environment
```bash
source venv/bin/activate  # Unix/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### "Apps aren't loaded yet"
**Solution**: Scripts call `django.setup()` automatically. If you see this error, check that `DJANGO_SETTINGS_MODULE` is set correctly in the script.

### Email test fails to send
**Solution**: Check SMTP settings
```bash
# Verify settings
grep EMAIL_ .env

# Test with dry-run first
python scripts/email_test.py --dry-run

# Check if SMTP credentials are correct
```

### Redis check fails with DNS error
**Solution**:
- Check network connectivity
- Verify `REDIS_HOST` is correct
- Try with IP address instead of hostname
- Check VPN/firewall settings

### Delete user: "User does not exist"
**Solution**: Check the email address
```bash
# List all users in Django shell
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.values_list('email', flat=True)
```

---

## Security Notes

### delete_user.py
- ⚠️ **Deletion is permanent and irreversible**
- ✅ Always test with dry-run first
- ✅ Requires explicit confirmation (unless `--yes`)
- ✅ Uses atomic transactions (all-or-nothing)

### email_test.py
- ⚠️ Don't send to real users in production
- ✅ Use `--dry-run` for safe testing
- ✅ Test emails are clearly labeled: `[Email Test]`

### redis_check.py
- ✅ Safe to run (only performs read/write test with short TTL)
- ✅ Test keys are prefixed: `redis_check:*`
- ✅ Keys auto-expire after 30 seconds

---

## Adding New Scripts

When creating new utility scripts:

1. **Add shebang**: `#!/usr/bin/env python3`
2. **Add docstring**: Comprehensive usage documentation
3. **Use argparse**: Professional CLI interface
4. **Set up Django**:
   ```python
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
   django.setup()
   ```
5. **Use text_output**: Consistent formatting
   ```python
   from utils.text_output import header, info, success, warning, error
   ```
6. **Handle signals**: Keyboard interrupts, exceptions
7. **Return exit codes**: 0 for success, non-zero for errors
8. **Make executable**: `chmod +x scripts/your_script.py`
9. **Document**: Add to this README

---

## Related Documentation

- [Main README](../README.md) - Project overview and setup
- [Development Guide](../docs/DEVELOPMENT.md) - Development workflows
- [API Documentation](../docs/API.md) - API endpoints and usage
