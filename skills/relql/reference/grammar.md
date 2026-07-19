# RelQL grammar & semantics

Authoritative syntax for writing RelQL queries. Keywords are case-insensitive.
Column references are always qualified `table.column`; `table.*` means "rows".

## Query structure

Clause order: `PREDICT` and `FOR [EACH]` are required and come first (in that
order). The trailing clauses may appear in any order after `FOR`, each at most
once — except `WINDOW`, which may repeat.

```
[EXPLAIN [PLAN|CONTEXT|ANALYZE] [FORMAT TEXT|JSON]]
PREDICT   <target> [CLASSIFY | RANK TOP <k>]
FOR [EACH] <entity_table>.<pkey> [= <literal> | IN (<list>)]
[WHERE     <condition>]        -- filter the population (past-facing)
[ASSUMING  <condition>]        -- counterfactual (parses; not yet applied)
[AS OF     <anchor>]           -- bind the anchor time
[RETURN    <return_spec>]      -- choose the output form
[WINDOW    <name> AS (<window_spec>)]   -- reusable named frame (repeatable)
```

- `FOR` and `FOR EACH` are equivalent (`EACH` optional). This is the sole
  entity clause — there is **no** `GIVEN` clause and **no** `FORECAST` clause.
- Enumerating every entity in `FOR EACH` requires a `TableScanner`. To score a
  subset, constrain the key (`WHERE table.pk IN (...)`) or pass ids at execution
  (`entity_ids`).
- `AS OF` takes a `DATE` literal (`2026-07-01`), a bound parameter
  (`:prediction_time`), or `NOW`. A DATE/param overrides the execution anchor;
  `NOW`/absent uses the execution `anchor_time`.
- `ASSUMING` is parsed and validated and carried on the query but **not yet**
  applied to context assembly.

## Target expression

The target after `PREDICT` is one of:
- a static column reference — `customers.age`, `articles.description IS NULL`
- an aggregation over linked rows in an `OVER` frame (below)
- a richer expression: arithmetic, `CASE WHEN … END`, `COALESCE`, `NULLIF`,
  `ABS`/`LOG`/`EXP`/`LEAST`/`GREATEST`, column-to-column comparison
- optionally compared to a literal (`… > 100`, `… = 0`, `… NOT LIKE '%DENIED'`)

`CLASSIFY` and `RANK TOP k` are target directives.

## Aggregation functions

```
AGG( table.column | table.* [WHERE <row filter>] ) OVER ( <window_spec> )
```

Functions: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNT_DISTINCT`,
`LIST_DISTINCT`, `FIRST`, `LAST`, `EXISTS`, `NOT EXISTS`.

- `COUNT(table.*)` counts rows. `EXISTS(table.*)` / `NOT EXISTS(table.*)` are
  boolean existence tests (cleaner than the still-valid `COUNT(...) > 0`).
- `FIRST` / `LAST` pick a value by row time (good for status columns).
- `LIST_DISTINCT` predicts a set of values (usually FK IDs); takes a directive
  `RANK TOP K` (ranking) or `CLASSIFY`.
- Inline row filter (distinct from the population `WHERE`):
  `COUNT(transactions.* WHERE transactions.amount > 10) OVER (30 DAYS FOLLOWING)`.

## Time windows (the OVER frame)

Frames are relative to the anchor (`NOW`); membership is **start-exclusive,
end-inclusive**. Directions: `PRECEDING` (past) / `FOLLOWING` (future).
Durations are always positive.

```
window_spec := frame [HORIZONS <positive-int> [STEP <positive-duration>]]

frame := RANGE BETWEEN <bound> AND <bound>
       | <duration> PRECEDING        -- (NOW - dur, NOW]
       | <duration> FOLLOWING        -- (NOW, NOW + dur]
       | UNBOUNDED PRECEDING         -- all history up to NOW

bound := NOW | <duration> PRECEDING | <duration> FOLLOWING
       | UNBOUNDED PRECEDING | UNBOUNDED FOLLOWING

duration := <positive-number> <unit>
```

Units: `SECONDS`, `MINUTES`, `HOURS`, `DAYS`, `WEEKS`, `MONTHS`, `YEARS`
(singular/plural, case-insensitive; a MONTH is a 30-day approximation).

```sql
COUNT(orders.*) OVER (30 DAYS FOLLOWING)      -- next 30 days
COUNT(orders.*) OVER (90 DAYS PRECEDING)      -- last 90 days
COUNT(orders.*) OVER (UNBOUNDED PRECEDING)    -- all history up to NOW
SUM(sales.qty)  OVER (RANGE BETWEEN 15 DAYS FOLLOWING AND 45 DAYS FOLLOWING)
```

**Target frames face the future (`FOLLOWING`); filter frames (in `WHERE`) face
the past (`PRECEDING`/`UNBOUNDED PRECEDING`).** The validator enforces this.

**Forecasting** — append `HORIZONS N` to repeat the frame N times; `STEP` sets
the stride (defaults to the frame width; use a smaller step for overlap):
```sql
SUM(usage.count) OVER (1 DAY FOLLOWING HORIZONS 28)              -- 28 daily steps
SUM(sales.qty)   OVER (30 DAYS FOLLOWING HORIZONS 6 STEP 7 DAYS) -- overlapping
```

**Named windows** — declare once, reference as `OVER <name>`:
```sql
PREDICT SUM(orders.revenue) OVER w - SUM(orders.cost) OVER w
FOR EACH customers.customer_id
WINDOW w AS (30 DAYS FOLLOWING)
```

## Conditions (WHERE / inline filter / ASSUMING / target comparison)

- Comparison: `=` `==` `!=` `>` `>=` `<` `<=`. Either side may be a literal,
  static column, aggregation over a frame, or a richer expression;
  column-to-column comparisons allowed (`orders.shipped_at > orders.ordered_at`).
- Boolean: `AND`, `OR`, `NOT`, with parentheses.
- Membership / null: `IN (...)`, `NOT IN (...)`, `IS NULL`, `IS NOT NULL`.
- String: `LIKE '%…'` (SQL `%` wildcards), `STARTS WITH`, `ENDS WITH`,
  `CONTAINS`.

```sql
WHERE customers.location IN ('NY', 'CA') AND EXISTS(orders.*) OVER (180 DAYS PRECEDING)
```

## RETURN — output form

```
EXPECTED VALUE | PROBABILITY | CLASS | DISTRIBUTION
| QUANTILES (<num>, ...) | INTERVAL <int> [%] | MULTILABEL | MULTICLASS
```

`RETURN PROBABILITY` gives a calibrated score for a classification target.
`QUANTILES`/`INTERVAL`/`MULTICLASS`/`MULTILABEL` parse and validate but are **not
executable** on the current RT-J checkpoint.

## Task types (inferred from the target — never declared)

| Target shape | Task type | Executable now? |
|---|---|---|
| bare aggregation — `SUM(...)`, `COUNT(...)` | regression | ✅ |
| aggregation vs literal — `COUNT(...) = 0`, `SUM(...) > 100` | binary classification | ✅ |
| `EXISTS(...)` / `NOT EXISTS(...)` boolean target | binary classification | ✅ |
| static categorical column, `FIRST`/`LAST` | multiclass | ❌ parses only |
| `LIST_DISTINCT(...) RANK TOP K` | ranking | ❌ parses only |
| any window with `HORIZONS > 1` | forecasting (value per horizon) | regression head |

Model routing: classification → `hf://stanford-star/rt-j/classification`;
regression/forecasting → `hf://stanford-star/rt-j/regression`.

## EXPLAIN — inspect without (necessarily) running

- `EXPLAIN PLAN` (default): normalized target, inferred task type, entity
  selector, resolved output form, normalized windows, anchor source. Parse +
  validate only.
- `EXPLAIN CONTEXT`: also assembles per-entity context (row/cell counts, links,
  time ranges, rows dropped by the bound). No scoring.
- `EXPLAIN ANALYZE`: assembles and scores.

## Lexical notes

- Aggregation/condition words (`count`, `sum`, `and`, `like`) are soft keywords
  — still usable as column names (`usage.count` parses).
- Literals: numbers, `'quoted strings'`, booleans, DATEs (`2026-07-01`).
- Comments are supported.
