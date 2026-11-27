# Notifications

Two audiences are notified when a contract fails (and on warnings, if `notify_on` includes `warn`):

- **the source team**, from the contract's `support` section — whoever owns the data;
- **the platform team**, from `odcr.yaml` — told about every failure on every contract.

| Channel (`tool` / `type`) | Target | Notes |
| --- | --- | --- |
| `slack` | incoming webhook URL | |
| `teams` | Teams Workflows / Power Automate webhook URL | Adaptive Card |
| `email` | address (`mailto:` or `to:` list) | sent with the configured mail provider (below) |
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
  mail: {provider: microsoft365, from: odcr-alerts@acme.com}   # see "Email without passwords"
  ca_bundle: /etc/ssl/certs/corporate-ca.pem     # optional
  proxy: http://proxy.example.com:8080           # optional
```

A failed notification never breaks the run; every attempt (sent or failed) is in the `notifications` meta
table, with webhook secrets masked.

## Email without passwords

`odcr init` asks how email is sent. Most options need no stored password:

| Provider | How it authenticates | Configuration |
| --- | --- | --- |
| `smtp-relay` | the company mail relay trusts the server (IP / network) | `host`, `port`, `from` |
| `microsoft365` | Microsoft Graph `sendMail` with Entra ID: managed identity, workload identity, `az login` | `from` (a mailbox the identity may send as); `pip install "odcr[microsoft365]"` |
| `aws-ses` | the machine's IAM role / SSO profile | `region`, `from` (verified identity); `pip install "odcr[aws-ses]"` |
| `smtp` / `gmail` | user + password **from the OS keychain** | `odcr secret set SMTP_PASSWORD`, then `password: ${keyring:SMTP_PASSWORD}` |

```yaml
notifications:
  mail:
    provider: microsoft365
    from: odcr-alerts@acme.com
    # client_id: ${AZURE_MANAGED_IDENTITY_CLIENT_ID}   # user-assigned managed identity
```

For Microsoft 365, grant the identity the Graph application permission **Mail.Send** and restrict it to the
alerts mailbox with an Exchange application access policy.
