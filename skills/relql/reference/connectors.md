# Connecting a data source to RelativeDB retrievers

RelativeDB ships **no** bundled connectors — retrievers are small callbacks the
application owns. That is the point: the same query runs on Snowflake, Postgres,
a DataFrame, or a test double. This file gives a connection snippet per common
source plus the one retriever pattern they all share.

**Golden rule — temporal correctness.** Every retriever receives a `bound`
(`bound.as_of` / `bound.asOf()`). Push it into the SQL `WHERE` on the table's
**time column** so you never return rows newer than the anchor. Link retrievers
return children **newest-first**, capped at `limit`.

**Credentials** live in the user's environment (env vars, `~/.snowflake`,
`gcloud` ADC, `.pgpass`, etc.). Read them from there. Never hardcode, print, or
commit a secret.

## The retriever pattern (Python, source-agnostic)

Given any DB-API cursor, the three callbacks look like this. Only the
connection differs per source.

```python
from relativedb import Row

TIME_COL = {"orders": "order_date", "transactions": "txn_ts"}   # event tables

def make_wiring(conn):
    def entities(table, ids, bound):
        if not ids:
            return []
        q = f"SELECT * FROM {table} WHERE {PK[table]} IN ({placeholders(ids)})"
        return [row_from(table, r) for r in run(conn, q, ids)]

    def links(link, parent_id, bound, limit):
        child, fk, tcol = link.child, link.fk_column, TIME_COL[link.child]
        q = (f"SELECT * FROM {child} WHERE {fk} = %s "
             f"AND {tcol} <= %s "                # <-- temporal bound
             f"ORDER BY {tcol} DESC LIMIT %s")   # <-- newest-first, capped
        return [row_from(child, r) for r in run(conn, q, [parent_id, bound.as_of, limit])]

    def scan(table, bound):                       # enables bare FOR EACH
        for r in run(conn, f"SELECT {PK[table]} FROM {table}"):
            yield Row(table, r[PK[table]], {})

    from relativedb import RetrieverWiring
    return (RetrieverWiring.new_wiring()
        .entities("customers", entities)
        .entities("orders", entities)
        .default_links(links)
        .scanner("customers", scan)
        .build())

def row_from(table, r):
    # Map DB columns -> typed cells. Exclude the PK and any FK columns
    # (they become identity + parent edges, set via the link, not cells).
    cells = {c: coerce(v) for c, v in r.items() if c not in NON_CELL[table]}
    return Row(table, r[PK[table]], cells)
```

Keep `PK`, `TIME_COL`, `NON_CELL` (pk + fk columns) as small maps derived from
the schema you mapped in step 4.

## Snowflake

```python
import os, snowflake.connector
conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    authenticator="externalbrowser",     # or password / key-pair from env
    warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
    database=os.environ["SNOWFLAKE_DATABASE"],
    schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
)
# cur.execute(sql, params); cur.fetchall() with DictCursor-style access.
```
Inspect schema: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ORDERS'`.

## Postgres

```python
import os, psycopg2, psycopg2.extras
conn = psycopg2.connect(os.environ["DATABASE_URL"])   # or discrete PG* env vars
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
```
Inspect schema: `\d table` in psql, or `information_schema.columns`. Placeholder
is `%s`.

## BigQuery

```python
from google.cloud import bigquery      # uses Application Default Credentials
client = bigquery.Client(project="my-project")
rows = client.query(sql, job_config=bigquery.QueryJobConfig(
    query_parameters=[bigquery.ScalarQueryParameter(None, "STRING", parent_id)])).result()
```
Parameterize with `@name` or positional `?`. Time bound: `WHERE order_date <= @bound`.

## MySQL / MariaDB

```python
import os, mysql.connector
conn = mysql.connector.connect(
    host=os.environ["MYSQL_HOST"], user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DB"])
cur = conn.cursor(dictionary=True)
```
Placeholder is `%s`.

## Databricks / Spark SQL

```python
import os
from databricks import sql
conn = sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"])
```
DB-API compatible; the same cursor pattern applies.

## CSV / pandas (fastest first result)

No warehouse — load frames and close over them. Great for a first run or a
backtest on an export.

```python
import pandas as pd
from relativedb import Row, RetrieverWiring

customers = pd.read_csv("customers.csv", parse_dates=["signup_date"])
orders    = pd.read_csv("orders.csv",    parse_dates=["order_date"])

cust_rows = {r.customer_id: Row("customers", r.customer_id, {"age": float(r.age)})
             for r in customers.itertuples()}

def entities(table, ids, bound):
    return [cust_rows[i] for i in ids if i in cust_rows]

def links(link, parent_id, bound, limit):
    df = orders[(orders.customer_id == parent_id) & (orders.order_date <= bound.as_of)]
    df = df.sort_values("order_date", ascending=False).head(limit)
    return [Row("orders", r.order_id, {"qty": float(r.qty)},) for r in df.itertuples()]

def scan(table, bound):
    return list(cust_rows.values())

wiring = (RetrieverWiring.new_wiring()
    .entities("customers", entities)
    .default_links(links)
    .scanner("customers", scan)
    .build())
```

## Java / Rust sources

Same contract, different plumbing: back the retrievers with your existing DAOs /
a JDBC `DataSource` (Java) or an `sqlx`/`postgres` pool (Rust). Java retrievers
are async (`CompletionStage`); apply the `bound` in the SQL `WHERE` exactly as
above. See `api-java.md` / `api-rust.md` for the callback signatures.
