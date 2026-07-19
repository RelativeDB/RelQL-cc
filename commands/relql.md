---
description: Predict the future of your relational data — churn, conversion, demand, risk — with RelQL and the RT-J model.
argument-hint: [a forward-looking question about your data]
---

The user wants a prediction over their relational data:

> $ARGUMENTS

Use the **relql** skill to handle this end to end. Follow its workflow: frame
the question as target + population + window, find out where the data lives and
how to connect (Snowflake, Postgres, BigQuery, MySQL, Databricks, CSV/pandas,
…), pick the user's language, map the schema, write the RelQL query, wire the
retrievers, build the native RT-J backend, execute, and report the ranked
results.

Read the skill's reference files (`grammar.md`, `query-cookbook.md`,
`api-<language>.md`, `connectors.md`, `native-backend.md`) for exact syntax and
APIs — do not write RelQL or engine code from memory.

If `$ARGUMENTS` is empty, ask the user what they want to predict and where their
data lives.
