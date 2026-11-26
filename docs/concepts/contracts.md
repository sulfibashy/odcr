# What odcr checks

odcr reads [ODCS v3](https://bitol-io.github.io/open-data-contract-standard/) contracts. Fields it does not use
are kept and ignored, so any valid ODCS contract works.

## Schema checks (always on)

| Check id | Fails when | Severity |
| --- | --- | --- |
| `<object>.exists` | the table, collection or file is missing | error |
| `<object>.<column>.exists` | a contract column is missing | error |
| `<object>.<column>.type` | the physical type does not fit `logicalType` | error |
| `<object>.no_extra_columns` | columns not in the contract appeared | warning |

`logicalType` families: `integer`, `number`, `string`, `date`, `timestamp`, `boolean`.

## Property flags

| Flag | Check |
| --- | --- |
| `required: true` | no NULL / missing values |
| `unique: true` | no duplicate values |
| `primaryKey: true` | both |

## Quality rules

| `type` | `metric` | ODCS 3.0 name | Counts |
| --- | --- | --- | --- |
| library | `rowCount` | | rows in the table or batch |
| library | `nullValues` | `nullCheck` | NULL values |
| library | `missingValues` | | NULL or values in `arguments.missingValues` |
| library | `duplicateValues` | `duplicateCount` | duplicate rows (column, or `arguments.properties`) |
| library | `invalidValues` | `validValues` | values not in `arguments.validValues` |
| sql | | | the number `query` returns; `{object}` is the table or batch, `{property}` the column |
| custom | | | platform-specific rule: `engine: mongodb` (JSON filter) or `engine: cosmosdb` (condition) |
| text | | | documentation only |

Comparators: `mustBe`, `mustNotBe`, `mustBeGreaterThan`, `mustBeGreaterOrEqualTo`, `mustBeLessThan`,
`mustBeLessOrEqualTo`, `mustBeBetween`, `mustNotBeBetween`. Without a comparator a count of bad rows must be 0.
`unit: percent` compares as a percentage of rows. `severity: warning` notifies without failing.

```yaml
quality:
  - type: sql
    query: SELECT COUNT(*) FROM {object} WHERE amount < 0
    mustBe: 0
  - type: custom                 # MongoDB
    engine: mongodb
    implementation: '{"amount": {"$lt": 0}}'
    mustBe: 0
```

A rule written for another engine is **skipped** (not failed) on platforms that cannot run it, so one contract
can carry rules for several platforms.
