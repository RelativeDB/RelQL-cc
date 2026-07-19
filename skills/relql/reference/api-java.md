# RelativeDB — Java API

**Install.** Maven group `com.relativedb`, Java 17+.

```kotlin
dependencies {
    implementation("com.relativedb:relationdb:0.1.0")       // engine, schema, parser, retriever SPI
    implementation("com.relativedb:relationdb-rt:0.1.0")    // RtNativeBackend (JNA binding to librt_c)
}
```

Java classes are prefixed: `RelativeDbSchema`, `RelativeDbEngine` (built with
`.newSchema()` / `.newEngine(...)`).

## 1. Schema

```java
import static com.relativedb.schema.ValueType.NUMBER;
import static com.relativedb.schema.ValueType.DATETIME;

RelativeDbSchema schema = RelativeDbSchema.newSchema()
    .table(TableDef.newTable("customers").column("age", NUMBER)
        .column("signup_date", DATETIME).primaryKey("customer_id").build())
    .table(TableDef.newTable("orders").column("qty", NUMBER)
        .column("order_date", DATETIME).primaryKey("order_id")
        .timeColumn("order_date").build())
    .link(LinkDef.link("orders", "customer_id", "customers"))   // child, fk_col, parent
    .build();
```

## 2. Retriever wiring (async — returns `CompletionStage`)

Every call carries a `TemporalBound`; `bound.asOf()` returns
`Optional<Instant>`. The engine re-checks all returned rows.

```java
RetrieverWiring wiring = RetrieverWiring.newWiring()
    // (table, ids, bound) -> CompletionStage<List<Row>>
    .entities("customers", (table, ids, bound) -> customerDao.byIds(ids))
    .entities("orders",    (table, ids, bound) -> orderDao.byIds(ids, bound))
    // (link, parent, bound, limit) -> children, newest-first, <= limit
    .defaultLinks((link, parent, bound, limit) ->
        orderDao.recentByCustomer(parent, bound.asOf().orElse(Instant.MAX), limit))
    .build();
```

## 3. Engine + native backend + execute

```java
RelativeDbEngine engine = RelativeDbEngine.newEngine(schema, wiring)
    .samplerMode(SamplerMode.CSC)               // optional
    .modelBackend(new RtNativeBackend(schema))  // required; runs RT-J
    .build();

PredictionResult churn = engine.execute(ExecutionInput.newInput()
    .query("PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING) "
         + "FOR EACH customers.customer_id")
    .anchorTime(Instant.parse("2026-07-01T00:00:00Z"))
    .entityIds(ids)                             // omit + FOR EACH -> TableScanner enumerates
    .build()).toCompletableFuture().join();
```

`execute(...)` returns `CompletionStage<PredictionResult>`;
`.toCompletableFuture().join()` blocks. `anchorTime` is an `Instant`.

### Native backend with a text encoder

Text cells need MiniLM embeddings (384-dim). Provide a `TextEncoder`:

```java
TextEncoder encoder = new PrecomputedEncoder(embeddingTable);   // String -> float[384]
try (RtNativeBackend backend = new RtNativeBackend(ModelConfig.defaults(), encoder)) {
    RelativeDbEngine engine = RelativeDbEngine.newEngine(schema, wiring)
        .modelBackend(backend).build();
    // ...
}
```

Library discovery order: system property `relativedb.rt.lib` → env
`RELATIVEDB_RT_LIB` → sibling `cpp/build/` → loader path. `hf://` checkpoints
resolve from the local HF cache (override with `relativedb.rt.hf.cache` /
`RELATIVEDB_RT_HF_CACHE`).

## 4. Parse / validate

`Pql.parse(...)` / `Pql.validate(...)` in package `com.relativedb.query`.

Key packages: `com.relativedb.schema`, `.retrieve`, `.query`, `.engine`,
`.model`, `.rt`.
