# Security policy

Please do not report security problems in public issues.

Use GitHub's **Report a vulnerability** button (Security tab) to send a private report. We aim to reply within 7 days.

Supported versions: the latest minor release receives security fixes.

Notes for users (see also docs/security.md):
- Keep credentials and webhook URLs in environment variables (`${VAR}` in `odcr.yaml` and contracts), never in Git.
- `--where` filters and `sql` quality rules are executed as written; only trusted pipeline authors should provide them.
