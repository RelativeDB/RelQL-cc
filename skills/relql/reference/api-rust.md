# RelativeDB — Rust API

**Install.** crates.io package `relationdb`; the crate API is `relativedb`.
Edition 2021, depends only on `chrono` and `libloading`.

```bash
cargo add relationdb
```

## 1. Schema

```rust
use relativedb::{Schema, TableDef, LinkDef, ValueType};

let schema = Schema::new_schema()
    .table(TableDef::new_table("customers")
        .column("age", ValueType::Number)
        .column("signup_date", ValueType::Datetime)
        .primary_key("customer_id").build())
    .table(TableDef::new_table("orders")
        .column("qty", ValueType::Number)
        .column("order_date", ValueType::Datetime)
        .primary_key("order_id")
        .time_column("order_date").build())
    .link(LinkDef::link("orders", "customer_id", "customers"))   // child, fk_col, parent
    .build();
```

## 2. Retriever wiring

Closures implement the retriever traits; synchronous, infallible, return plain
`Vec`s. Honor the temporal `bound`; children newest-first within `limit`.

```rust
use relativedb::RetrieverWiring;

let wiring = RetrieverWiring::new_wiring()
    .entities("customers", entity_lookup)      // (table, ids, bound) -> Vec<Row>
    .default_links(newest_first_children)      // (link, parent, bound, limit) -> Vec<Row>
    .scanner("customers", customer_scan)       // (table, bound) -> rows; enables FOR EACH + CSC
    .build();
```

## 3. Engine + native backend + execute

```rust
use relativedb::{Engine, ExecutionInput, RtNativeBackend};

let mut engine = Engine::new(schema, wiring)
    .model_backend(RtNativeBackend::new(&schema)?);   // required; runs RT-J

let result = engine.execute(
    ExecutionInput::query(
        "PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING) \
         FOR EACH customers.customer_id")
    .anchor_time(anchor))?;                            // chrono DateTime

for p in result.predictions.iter() {
    println!("{} {:.4}", p.id, p.probability);
}
```

`ExecutionInput::query("...").anchor_time(t0)` is a builder; `execute(...)`
returns `relativedb::Result`. An alternate backend form seen in docs:
`.model_backend(Box::new(RtNativeBackend::new(&schema)?))`.

## 4. Modules & errors

Modules: `schema`, `retrieve`, `pql` (decodes the native `librt_c` parser's JSON
AST), `engine`, `model`, `native`, `csc`. Errors via `relativedb::Result` /
`relativedb::Error`. `native::RtNativeBackend` binds `librt_c` via `libloading`,
discovered from `RELATIVEDB_RT_LIB` or a sibling `cpp/build/`.
