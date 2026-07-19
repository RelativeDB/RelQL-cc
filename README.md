<p align="center">
  <img src="logo.svg" alt="RelQL logo" width="96" />
</p>

# RelQL for Claude Code

A Claude Code plugin that gives your agent **predictive ability** over your
relational data. Ask a forward-looking question in plain English — *"which
customers are about to stop ordering?"* — and RelQL connects to your data,
maps the schema, writes a [RelQL](https://relql.com) `PREDICT` query, and scores
it with the RT-J relational foundation model.

## Install

In Claude Code:

```
/plugin marketplace add RelativeDB/RelQL-cc
/plugin install RelQL@RelQL
```

## Use

Either invoke the command:

```
/relql which of my customers are about to stop ordering?
```

…or just ask a predictive question and the **relql** skill activates on its own.
It walks the whole path with you:

1. **Frame** the question as target + population + time window.
2. **Connect** your data — Snowflake, Postgres, BigQuery, MySQL, Databricks, or
   a CSV / pandas DataFrame.
3. **Language** — Python, Java, or Rust, matched to your project.
4. **Map** your tables to a RelativeDB schema.
5. **Write** the RelQL query.
6. **Wire** retrievers over your storage (temporally correct by construction).
7. **Score** with the native RT-J backend and report ranked results.

## What it predicts well

Churn / lapse, conversion / activation, spend & demand (regression), usage
forecasts, recommendation ranking, and risk / status flags. The shipped RT-J
checkpoint executes **binary classification**, **regression**, **multiclass
classification** (predicted class + approximate probabilities, via the text
head), and **ranking** (top-k via per-candidate existence scoring). Quantile /
interval outputs parse and validate but are not yet executable.

## What's in here

```
.claude-plugin/
  marketplace.json      # marketplace "RelQL"
  plugin.json           # plugin "RelQL"
commands/
  relql.md              # /relql slash command
skills/relql/
  SKILL.md              # the orchestrating skill
  reference/            # RelQL grammar, query cookbook, per-language APIs,
                        #   connectors, native-backend setup
  scripts/
    run_prediction.py   # runnable Python scorer wrapper
```

## Links

- Docs & language reference: https://relql.com
- Engine & libraries: https://github.com/RelativeDB/RelQL

## License

Apache-2.0. © RelativeDB.
