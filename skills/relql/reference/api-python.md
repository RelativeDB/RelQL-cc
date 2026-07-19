# RelativeDB — Python API

**Install.** PyPI distribution is `relationdb`; the import is `relativedb`.
Python 3.10+, core depends only on numpy.

```bash
pip install relationdb          # core
pip install "relationdb[rt]"    # + native RT-J backend (sentence-transformers, huggingface_hub)
```

No bundled pandas or DB connectors — those are application-owned (see
`connectors.md`).

## 1. Schema

```python
from relativedb import Schema, TableDef, LinkDef, ValueType

schema = (Schema.new_schema()
    .table(TableDef.new_table("customers")
        .column("age", ValueType.NUMBER)
        .column("signup_date", ValueType.DATETIME)
        .primary_key("customer_id").build())
    .table(TableDef.new_table("orders")
        .column("qty", ValueType.NUMBER)
        .column("order_date", ValueType.DATETIME)
        .primary_key("order_id")
        .time_column("order_date").build())          # event table needs a time column
    .link(LinkDef("orders", "customer_id", "customers"))  # child, fk_col, parent
    .build())
```

Column types: `ValueType.NUMBER`, `ValueType.DATETIME`, text (for string cells).
`LinkDef(child_table, fk_column, parent_table)`.

## 2. Rows

```python
from relativedb import Row
Row("customers", r.customer_id, {"age": float(r.age)})   # Row(table, id, cells)
```

Cells are typed **values only**. FK values are not cells — they surface as
parent edges (`fk_column: parent_id`). A primary key is identity by default and
is *additionally* a cell when the schema declares it as a column.

> **A row with no feature cells emits no tokens**, and a token-less row that
> others link through is a dead end — nothing below it can reach the
> prediction, and every entity scores alike. The engine raises
> `ContextConnectivityWarning` when it detects this. Give the table a feature
> column, or declare its primary key as one.

## 3. Retriever wiring

Retrievers are plain callables (`typing.Protocol`), synchronous, infallible
(return plain lists). Every call carries a temporal `bound`; return nothing
newer than `bound.as_of`.

```python
from relativedb import RetrieverWiring

wiring = (RetrieverWiring.new_wiring()
    # (table, ids, bound) -> rows   : batched point lookup for seeds & parents
    .entities("customers", lambda table, ids, bound: customer_dao.by_ids(ids))
    .entities("orders",    lambda table, ids, bound: order_dao.by_ids(ids, bound))
    # (link, parent_id, bound, limit) -> rows : children NEWEST-FIRST, <= limit, <= bound
    .default_links(lambda link, parent_id, bound, limit:
                   order_dao.recent_by_customer(parent_id, bound.as_of, limit))
    # (table, bound) -> row stream : optional; enables whole-table FROM + CSC mode
    .scanner("customers", lambda table, bound: customer_dao.scan_all(bound))
    .build())
```

Wiring is validated when the engine is built — missing pieces fail fast with
`WiringError`.

## 4. Engine + native backend + execute

```python
import pandas as pd
from relativedb import Engine, ExecutionInput, RtNativeBackend

engine = Engine(schema, wiring, model_backend=RtNativeBackend(schema=schema))

result = engine.execute(ExecutionInput(
    query="PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING) "
          "FROM customers "
          "WHERE customers.customer_id IN :ids "
          "AND EXISTS(orders.*) OVER (180 DAYS PRECEDING)",
    params={"ids": ["C7", "C9"]},
    anchor_time=pd.Timestamp("2026-07-01").to_pydatetime()))   # a datetime

for p in sorted(result.predictions, key=lambda p: p.probability, reverse=True)[:20]:
    print(p.id, round(p.probability, 4))
```

`ExecutionInput(query=..., anchor_time=..., params=...)`. `anchor_time` is a
`datetime`. **There is no `entity_ids` argument** — the cohort is expressed in
the query as a primary-key predicate and bound through `params`, which also
supplies `AS OF :t` and any other `:name`. Each prediction exposes `.id` and
`.probability` (classification); regression predictions carry `.value`,
ranking `.ranked`.

## 5. Parse / validate / task type (no model needed)

```python
import relativedb
pq = relativedb.parse(q)
relativedb.validate(pq, schema)
pq.task_type()                 # e.g. relativedb.TaskType.REGRESSION
```

Use this to check a query before wiring/scoring.

## 6. Fine-tuning a task head (optional)

The released checkpoint is zero-shot. When you have history to learn from, train
a small head over the **frozen** backbone — the transformer is not updated, so
each example is encoded once and fitting is fast (a ~2 KB adapter).

```python
head = engine.finetune(
    query=Q,
    anchors=[t - timedelta(days=d) for d in (150, 120, 90, 60)],  # past cut-offs
    params={"ids": cohort},
    epochs=300, learning_rate=1e-2)

head                      # <FineTunedHead ranking on 2760 examples loss 4.10->3.65>
head.save("head.safetensors")

tuned = Engine(schema, wiring, model_backend=RtNativeBackend(
    schema=schema, wiring=wiring, head="head.safetensors"))
```

**Labels come from the query itself.** At each anchor the context is bounded
exactly as at prediction time, while the label reads the target's own window
*after* it — so the query defines its own supervision. Pass
`labels={(entity_id, anchor): value}` to override (for ranking,
`{candidate_id: relevance}`).

Choose anchors strictly **before** the evaluation anchor or you leak. Fitting
runs on Metal; inference on the trained head is CPU, so a head trained on a Mac
serves anywhere. Ranking groups with no relevant candidate in the window are
skipped (listwise loss needs a positive) and reported.

Works for all four task types. If held-out quality stalls while training loss
keeps falling, the head is data-limited — add anchors or entities rather than
epochs.

## Errors

`RelqlSyntaxError`, `RelqlValidationError`, `MissingParameterError`,
`SchemaError`, `WiringError`,
`ExecutionError`, `RtNativeUnavailableError` — all specific and actionable.
