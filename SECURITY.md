# Security policy

Please do not report security problems in public issues.

Use GitHub's **Report a vulnerability** button (Security tab) to send a private report. We aim to reply within 7 days.

Notes for users:
- Keep credentials and webhook URLs in environment variables (`${VAR}` in `odcr.yaml` and contracts), never in Git.
- `--where` filters and `sql` quality rules are executed as written; only trusted pipeline authors should provide them.
