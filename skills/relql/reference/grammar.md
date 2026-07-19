# RelQL grammar & semantics

Authoritative syntax for writing RelQL queries. Keywords are case-insensitive.
A column reference is `table.column`, `alias.column`, or a bare `column` bound
to the population; `table.*` means "rows".

## Query structure

`PREDICT` is required and comes first. The trailing clauses may appear in any
order after `FROM`, each at most once — except `WINDOW`, which may repeat.

```
[EXPLAIN [PLAN|CONTEXT|ANALYZE] [FORMAT TEXT|JSON]]
PREDICT   <target> [CLASSIFY]
[FROM      <table> [[AS] <alias>]]   -- the population; inferred if omitted
[WHERE     <condition>]        -- filter the population (past-facing)
[ASSUMING  <condition>]        -- counterfactual (applied to the context)
[AS OF     <anchor>]           -- bind the anchor time
[RETURN    <return_spec>]      -- choose the output form
[WINDOW    <name> AS (<window_spec>)]   -- reusable named frame (repeatable)
```

- `FROM <table>` names the population. You write the **table**, not the key —
  the primary key comes from the schema. There is **no** `FOR EACH` clause (it
  was removed), no `GIVEN`, and no `FORECAST`.
- An **alias** shortens the rest of the query: `FROM customers c … c.plan`.
- `FROM` may be **omitted** when the target names exactly one table and is not
  an aggregation — the population is then that table:
  `PREDICT issues.label WHERE issues.label IS NULL`. An aggregate target names
  a *linked* table, so it always needs an explicit `FROM`.
- A bare column binds to the population: `PREDICT label FROM issues WHERE label
  IS NULL` predicts `issues.label`.
- **Cohort selection**: constrain the primary key in `WHERE` —
  `WHERE customers.customer_id IN :ids`. The engine reads a primary-key
  predicate as the cohort itself and scores only those entities, so a pinned
  query needs no `TableScanner`. Scoring a whole table (no pk predicate) does
  require one. There is no `entity_ids` execution input.
- `AS OF` takes a `DATE` literal (`2026-07-01`), a bound parameter
  (`:prediction_time`), or `NOW`. A DATE/param overrides the execution anchor;
  `NOW`/absent uses the execution `anchor_time`.
- `ASSUMING` is a counterfactual: its `column = literal` assignments
  (optionally joined by `AND`) are written into the assembled context before
  scoring, so the model sees the assumed world. Conditions that name no
  concrete value — inequalities, `IN`, `OR`/`NOT`, aggregate conditions —
  describe a set of possible worlds and **raise** at execution. An assignment
  whose table has no rows in the context warns. Difference against the same
  query without `ASSUMING` to estimate an intervention's effect.

## Bind parameters

Anywhere a literal is allowed, `:name` stands in for a value supplied at
execution time. With `IN`, one parameter binds the **whole list**, so a single
query text serves any cohort size.

```sql
WHERE customers.customer_id = :id
WHERE customers.customer_id IN :ids
WHERE customers.plan LIKE :pattern AND customers.age > :min_age
```

Values come from `params` on the execution input — the same place `AS OF :t`
reads its anchor. An unsupplied `:name` is an error, never a silent NULL.

## Target expression

The target after `PREDICT` is one of:
- a static column reference — `customers.age`, `articles.description IS NULL`
- an aggregation over linked rows in an `OVER` frame (below)
- a richer expression: arithmetic, `CASE WHEN … END`, `COALESCE`, `NULLIF`,
  `ABS`/`LOG`/`EXP`/`LEAST`/`GREATEST`, column-to-column comparison
- optionally compared to a literal (`… > 100`, `… = 0`, `… NOT LIKE '%DENIED'`)

`CLASSIFY` is a target directive. Ranking is a **frame** directive —
`OVER (… RANK TOP k)` — see "Time windows" below.

## Aggregation functions

```
AGG( table.column | table.* [WHERE <row filter>] ) [OVER ( <window_spec> )]
```

Functions: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNT_DISTINCT`,
`LIST_DISTINCT`, `ARRAY_AGG`, `FIRST`, `LAST`, `EXISTS`, `NOT EXISTS`.

- `COUNT(table.*)` counts rows. `EXISTS(table.*)` / `NOT EXISTS(table.*)` are
  boolean existence tests (cleaner than the still-valid `COUNT(...) > 0`).
- `FIRST` / `LAST` pick a value by row time (good for status columns).
- `LIST_DISTINCT` predicts the **set** of values that will appear (usually FK
  IDs); duplicates collapse.
- `ARRAY_AGG` predicts the values in order and **keeps duplicates** — use it
  when "bought twice" should count twice.
- Either can be ranked with the frame's `RANK TOP K`, or turned into a
  per-value yes/no with `CLASSIFY`.
- Aggregating a **foreign key** is legal and is how ranking works:
  `ARRAY_AGG(orders.product_id)` asks which parents a row will point at.
- Inline row filter (distinct from the population `WHERE`):
  `COUNT(transactions.* WHERE transactions.amount > 10) OVER (30 DAYS FOLLOWING)`.

**`OVER` is optional.** Without it the frame is unbounded in the direction of
the clause: the future in `PREDICT`/`ASSUMING`, the past in `WHERE`.

```sql
PREDICT NOT EXISTS(orders.*)      -- (NOW, +inf]  will they ever order again?
FROM customers
WHERE COUNT(orders.*) > 5         -- (-inf, NOW]  have they ever ordered 5+ times?
```

## Time windows (the OVER frame)

Frames are relative to the anchor (`NOW`); membership is **start-exclusive,
end-inclusive**. Directions: `PRECEDING` (past) / `FOLLOWING` (future).
Durations are always positive.

```
window_spec := [frame [HORIZONS <positive-int> [STEP <positive-duration>]]]
               [RANK TOP <positive-int>]

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

**Ranking** — `RANK TOP K` keeps the K most likely values from the frame. It
lives *in the frame*, so *when* and *how many* stay independent; the frame may
be dropped entirely to rank over the whole future:
```sql
PREDICT ARRAY_AGG(transactions.article_id) OVER (30 DAYS FOLLOWING RANK TOP 12)
FROM customers

-- frame dropped entirely: rank over the whole future
PREDICT ARRAY_AGG(transactions.article_id) OVER (RANK TOP 12)
FROM customers
```

**Named windows** — declare once, reference as `OVER <name>`:
```sql
PREDICT SUM(orders.revenue) OVER w - SUM(orders.cost) OVER w
FROM customers
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
| MULTILABEL | MULTICLASS
```

`RETURN PROBABILITY` gives a calibrated score for a classification target.
`MULTICLASS` (predicted class + approximate probabilities) and `MULTILABEL`
(top-k ranking) execute on the current RT-J checkpoint. `QUANTILES` and
`INTERVAL` are **not part of the language** — the model exposes a single point
estimate, not a distribution — and are rejected at parse time.

## Task types (inferred from the target — never declared)

| Target shape | Task type | Executable now? |
|---|---|---|
| bare aggregation — `SUM(...)`, `COUNT(...)` | regression | ✅ |
| aggregation vs literal — `COUNT(...) = 0`, `SUM(...) > 100` | binary classification | ✅ |
| `EXISTS(...)` / `NOT EXISTS(...)` boolean target | binary classification | ✅ |
| static categorical column, `FIRST`/`LAST` | multiclass | ✅ (class + approx. probs, via text head) |
| `LIST_DISTINCT(...)` / `ARRAY_AGG(...)` with `RANK TOP K` in the frame | ranking | ✅ (top-k via per-candidate existence scoring) |
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
