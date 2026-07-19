---
name: relql
description: >-
  Answer forward-looking ("what is likely to happen?") questions about the
  user's relational data — churn, conversion, next purchase, demand/usage
  forecasts, risk/fraud flags, missing-attribute or status prediction. Use
  whenever the user asks about the FUTURE of rows in a database (customers,
  users, accounts, orders, transactions), or asks to predict, forecast, score,
  rank, or estimate likelihood. Connects to their data source (Snowflake,
  Postgres, BigQuery, MySQL, CSV/pandas, …), maps the schema, writes a RelQL
  PREDICT query, wires retrievers in their language, and scores it with the
  RT-J relational foundation model. Not for questions about the past — use SQL
  for those.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# RelQL — predictive queries over relational data

You help the user turn a plain-English question about the **future** of their
data into a working RelativeDB program that scores it with the RT-J relational
transformer. You do the whole path: pick the task, connect the data, map the
schema, write the RelQL query, wire the retrievers in their language, build the
native model backend, run it, and report the ranked results.

Do not invent RelQL syntax or engine APIs from memory. The reference files in
`reference/` next to this file are the source of truth — read the relevant one
before writing any query or code.

## What RelQL is good at

RelativeDB scores a **RelQL** query with a pretrained relational transformer
(RT-J). The query names a **target** (what to predict), a **population** (which
rows), and a **time window** (when). Best-fit questions:

- **Churn / lapse** — "which customers are about to stop ordering?" →
  `NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING)`
- **Conversion / activation** — "which trials will convert next month?"
- **Spend / LTV / demand (regression)** — "expected revenue per account next 30 days"
- **Forecasting** — a value per step over a horizon ("daily usage, next 4 weeks")
- **Recommendation / ranking** — "top-K items a user will buy next"
- **Risk / fraud flags** — "flag accounts likely to charge back"
- **Missing attribute / status** — "which articles are missing a description",
  "will this loan's latest status end in DENIED"

The shipped RT-J checkpoint executes **binary classification**, **regression**,
**multiclass classification**, and **ranking (`RANK TOP k`)**. Multiclass reuses
the checkpoint's text head — it returns a predicted class plus approximate,
uncalibrated class probabilities (cosine match of the decoded target embedding to
the class labels' MiniLM embeddings; the argmax class is reference-exact).
Ranking returns the top *k* via per-candidate existence scoring (no retraining;
both reuse existing heads). `RETURN QUANTILES`/`INTERVAL` are **not part of the
language** (the model gives a point estimate, not a distribution) and are
rejected at parse time — if the user needs an interval, say so plainly and fall
back to a regression framing.

Predictions are **point-in-time correct**: every data access is bounded by an
anchor time, so a model never sees the future it is asked to predict. Preserve
that — never widen a target window into the past or a filter window into the
future.

## Workflow

Work through these steps. Skip a step only when the user has already given you
that answer.

### 1. Frame the question → target + population + window + task type

Restate the user's question as: **target** (what), **from** (population),
**over** (window). Decide the task type from the target shape (see
`reference/grammar.md` §"Task types"). Confirm the framing with the user in one
line before building anything (e.g. *"churn = no order in the next 90 days, for
customers active in the last 180 — right?"*).

### 2. Find the data and how to connect

Ask where the data lives and pick the connector. Offer the common ones:

> Where is your data? **Snowflake · Postgres · BigQuery · MySQL · Databricks ·
> a CSV / pandas DataFrame · something else.**

Then read `reference/connectors.md` for the recommended client, credential
handling, and a fetch pattern for that source. Credentials belong to the user's
environment — read them from env vars / their existing config, never hardcode or
echo secrets. If they only have flat files or a DataFrame, the pandas/CSV path
is the fastest way to a first result.

### 3. Pick the language

Match the user's project. Detect it: a `pyproject.toml`/`requirements.txt` →
Python, `pom.xml`/`build.gradle` → Java, `Cargo.toml` → Rust. If ambiguous,
ask. Then read the matching API reference:

- Python → `reference/api-python.md`
- Java → `reference/api-java.md`
- Rust → `reference/api-rust.md`

### 4. Map the schema

Turn their tables into a RelativeDB `Schema`: for each table a primary key,
typed columns (NUMBER / DATETIME / text), and a **time column** for event
tables; declare **links** (child FK → parent). Inspect the real schema
(`INFORMATION_SCHEMA`, `\d`, a `LIMIT 1` sample, or the DataFrame's dtypes) —
don't guess column names. FK columns stay out of cells — they are edges.

Two schema rules that decide whether the model sees anything at all:

- **Every table needs at least one feature column.** A row with no cells emits
  no tokens, and a token-less row that others link through is a dead end: the
  whole subtree beneath it becomes unreachable and every entity scores
  identically. The engine raises `ContextConnectivityWarning` when it spots
  this — never ship a schema that triggers it.
- **A primary key may also be a feature.** Declare it as a column when the key
  carries meaning (a SKU, an ISBN, an airport code) — the same way
  `time_column` names a declared column. Leave synthetic autoincrement ids out:
  they track insertion order, and the model will read the id as a tenure proxy
  that breaks on a new id range.

### 5. Write the RelQL query

Using `reference/grammar.md` and `reference/query-cookbook.md`, write the
`PREDICT … OVER (…) FROM … [WHERE …]` statement. Rules:
- Target window faces the **future** (`FOLLOWING`); population filter in `WHERE`
  faces the **past** (`PRECEDING`). An aggregation with no `OVER` is unbounded
  in the direction of its clause.
- `FROM` names the **table**, not the key — the primary key comes from the
  schema. Alias it (`FROM customers c`) to shorten the rest.
- Pin the cohort with a primary-key predicate and a **bind parameter**:
  `WHERE customers.customer_id IN :ids`, supplying `params={"ids": [...]}` at
  execution. That is also what lets the engine skip enumerating the table.
- Restrict the population so you never score already-decided rows (e.g. exclude
  customers who already churned).
- Validate before executing — `relativedb.parse` / `validate` in Python, or a
  dry `EXPLAIN PLAN`.

### 6. Wire the retrievers / connector

Implement the retriever callbacks over the chosen source (entities, default
links, and a scanner if the query scores a whole table rather than a pinned
cohort). Use the exact
signatures from the language reference. Every retriever must honor the temporal
bound (`bound.as_of`) and return children newest-first within `limit`. Keep the
connector application-owned — a small module the program imports.

### 7. Build the native backend (required to score)

Scoring runs through `RtNativeBackend`, which needs the C++ library `librt_c`
and a cached `stanford-star/rt-j` checkpoint. Follow
`reference/native-backend.md` to build the library and point the engine at it.
Parsing/validation work without it; execution does not.

### 8. Execute and report

Construct the engine with the model backend, `execute` with an `anchor_time`
(default "now", or a past date for a backtest) and `params` for the query's
`:name` bindings, read `result.predictions` (`.id`, `.probability`, `.value`,
`.ranked`), sort, and present the top rows with a one-line reading of the
query. Offer a **backtest**: rerun at a past anchor and compare to what
actually happened — the engine keeps the context point-in-time correct.

### 9. Optional: fine-tune a head when zero-shot is not enough

If the backtest is weak and the user has history, `engine.finetune(query,
anchors, ...)` trains a small task head over the frozen backbone and returns a
`FineTunedHead` to `save()` and serve via `RtNativeBackend(head=...)`. Labels
are derived from the query's own target at past anchors, so nothing extra needs
labelling. See `reference/api-python.md` §6.

Judge it on **held-out** anchors, never on training loss: a falling loss with
flat held-out quality means the head is data-limited, and adding epochs will
not help — add anchors or entities instead.

## Reference files

Read these on demand — they hold the exact, authoritative syntax and APIs:

- [reference/grammar.md](reference/grammar.md) — full RelQL grammar: clauses,
  aggregations, time windows, conditions, task types.
- [reference/query-cookbook.md](reference/query-cookbook.md) — ready-to-adapt
  example queries per use case.
- [reference/api-python.md](reference/api-python.md) — Python engine API.
- [reference/api-java.md](reference/api-java.md) — Java engine API.
- [reference/api-rust.md](reference/api-rust.md) — Rust engine API.
- [reference/connectors.md](reference/connectors.md) — connecting Snowflake,
  Postgres, BigQuery, MySQL, Databricks, CSV/pandas to retrievers.
- [reference/native-backend.md](reference/native-backend.md) — building
  `librt_c` and fetching the RT-J checkpoint.

There is a runnable Python helper at `scripts/run_prediction.py` — a thin
wrapper that scores a RelQL query against a project connector and prints ranked
results. Use or adapt it for the Python path.
