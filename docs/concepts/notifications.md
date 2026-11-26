# Notifications

Two audiences are notified when a contract fails (and on warnings, if `notify_on` includes `warn`):

- **the source team**, from the contract's `support` section — whoever owns the data;
- **the platform team**, from `odcr.yaml` — told about every failure on every contract.

| Channel (`tool` / `type`) | Target | Notes |
| --- | --- | --- |
| `slack` | incoming webhook URL | |
| `teams` | Teams Workflows / Power Automate webhook URL | Adaptive Card |
| `email` | address (`mailto:` or `to:` list) | SMTP with STARTTLS (587) or implicit TLS (`ssl: true`, 465) |
| `googlechat` | space webhook URL | |
| `discord` | webhook URL | |
| `pagerduty` | Events API v2 routing key | severity warning / error |
| `opsgenie` | API key | priority P3 / P2 |
| `webhook` | any HTTPS endpoint | JSON: subject, text, details (ServiceNow, Jira automation, n8n, ...) |
| `console` | | prints to the job log |

```yaml
# contract
support:
  - {channel: "#orders-alerts", tool: slack, url: "${ORDERS_SLACK_WEBHOOK}"}
  - {channel: orders, tool: teams, url: "${ORDERS_TEAMS_WEBHOOK}"}
  - {channel: orders-team@example.com, tool: email, url: "mailto:orders-team@example.com"}

# odcr.yaml
notifications:
  notify_on: [fail, warn]
  platform_team:
    - {type: teams, url: "${PLATFORM_TEAMS_WEBHOOK}"}
    - {type: pagerduty, routing_key: "${PAGERDUTY_KEY}"}
    - {type: email, to: [data-platform@example.com]}
  smtp: {host: smtp.office365.com, port: 587, starttls: true, user: "${SMTP_USER}", password: "${SMTP_PASSWORD}"}
  ca_bundle: /etc/ssl/certs/corporate-ca.pem     # optional
  proxy: http://proxy.example.com:8080           # optional
```

A failed notification never breaks the run; every attempt (sent or failed) is in the `notifications` meta
table, with webhook secrets masked.
