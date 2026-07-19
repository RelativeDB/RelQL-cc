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

Cells are typed **values only**. IDs and FK values are never cells — they
surface as identity and parent edges (the link's `fk_column: parent_id`).

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
    # (table, bound) -> row stream : optional; enables bare FOR EACH + CSC mode
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
          "FOR EACH customers.customer_id "
          "WHERE EXISTS(orders.*) OVER (180 DAYS PRECEDING)",
    anchor_time=pd.Timestamp("2026-07-01").to_pydatetime()))   # a datetime

for p in sorted(result.predictions, key=lambda p: p.probability, reverse=True)[:20]:
    print(p.id, round(p.probability, 4))
```

`ExecutionInput(query=..., anchor_time=..., entity_ids=...)`. `anchor_time` is a
`datetime`. Each prediction exposes `.id` and `.probability` (classification);
regression predictions carry the value.

## 5. Parse / validate / task type (no model needed)

```python
import relativedb
pq = relativedb.parse(q)
relativedb.validate(pq, schema)
pq.task_type()                 # e.g. relativedb.TaskType.REGRESSION
```

Use this to check a query before wiring/scoring.

## Errors

`PqlSyntaxError`, `PqlValidationError`, `SchemaError`, `WiringError`,
`ExecutionError`, `RtNativeUnavailableError` — all specific and actionable.
