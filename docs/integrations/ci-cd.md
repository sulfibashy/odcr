# CI/CD for the contract repository

Contracts are code: every change goes through a pull request that is validated automatically. `odcr init` creates
both pipelines:

```yaml
# .github/workflows/contracts.yml
- run: pip install odcr pytest
- run: odcr lint contracts
- run: pytest -q
```

```yaml
# azure-pipelines.yml
- script: pip install odcr pytest
- script: odcr lint contracts
- script: pytest -q
```

Add `odcr lint --datacontract-cli` (with `pip install "odcr[lint]"`) to also run the official Data Contract CLI
linter. Protect `main` with required reviews from the producing and consuming teams.
