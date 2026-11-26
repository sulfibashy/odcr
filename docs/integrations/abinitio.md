# Ab Initio

Call odcr from the graph or plan that loads the data, on the Co>Operating System host.

**Run Program component** at the end of the load graph (or a *Program* task in a Conduct>It plan):

```text
Command:  /opt/odcr/venv/bin/odcr
Arguments: run --config /opt/odcr/project/odcr.yaml --contract-id orders
           --batch-id $LOAD_ID --where "load_id = '$LOAD_ID'" --pipeline orders --stage ingestion
```

A non-zero exit status fails the component, so the plan stops before downstream graphs consume a broken batch.

For file-based handoffs (landing directories, MFS outputs exported to files), use the `files` adapter and
`odcr run --for-object /data/landing/orders/<file>` or `odcr watch --once` from the plan.
