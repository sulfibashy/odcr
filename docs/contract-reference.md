# Contract reference: what odcr checks

odcr reads [ODCS v3](https://bitol-io.github.io/open-data-contract-standard/) contracts. Fields it does not use are kept and ignored, so any valid ODCS contract can be used.

## Schema checks (always on)

| Check id | Fails when | Severity |
| --- | --- | --- |
| `<object>.exists` | the table or view is missing | error |
| `<object>.<column>.exists` | a contract column is missing | error |
| `<object>.<column>.type` | the physical type does not fit `logicalType` | error |
| `<object>.no_extra_columns` | the table has columns not in the contract | warning |

`logicalType` families: `integer`, `number`, `string`, `date`, `timestamp`, `boolean`. Other types are not type-checked.

## Property flags

| Flag | Check |
| --- | --- |
| `required: true` | no NULL values |
| `unique: true` | no duplicate values |
| `primaryKey: true` | both of the above |

## Quality rules

| `type` | `metric` (ODCS 3.1) | Also accepted (ODCS 3.0 `rule`) | Counts |
| --- | --- | --- | --- |
| library | `rowCount` | | rows in the table or batch |
| library | `nullValues` | `nullCheck` | NULL values in the column |
| library | `missingValues` | | NULL or values listed in `arguments.missingValues` |
| library | `duplicateValues` | `duplicateCount` | duplicate rows (column, or `arguments.properties` on an object) |
| library | `invalidValues` | `validValues` | values not in `arguments.validValues` |
| sql | | | the number returned by `query`; `{object}` is the table or batch, `{property}` the column |
| text, custom | | | documented only, not executed |

Comparators: `mustBe`, `mustNotBe`, `mustBeGreaterThan`, `mustBeGreaterOrEqualTo`, `mustBeLessThan`, `mustBeLessOrEqualTo`, `mustBeBetween`, `mustNotBeBetween`. Without a comparator, a count of bad rows must be 0.

`unit: percent` compares the count as a percentage of rows. `severity: warning` (or `warn`, `info`) notifies without failing; anything else is an error.

## Notifications

Entries in `support` with `tool: slack | teams | webhook` and a `url`, or `tool: email`, are the source team. URLs may use `${ENV_VAR}` so secrets stay out of Git.
