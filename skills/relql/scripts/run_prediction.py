#!/usr/bin/env python3
"""Score a RelQL query against a project connector and print ranked results.

This is a thin, generic wrapper. Wire `build_engine()` to the connector you
built for this project (the module that maps the schema and retrievers), then:

    python run_prediction.py \
        --query "PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING) \
                 FOR EACH customers.customer_id \
                 WHERE EXISTS(orders.*) OVER (180 DAYS PRECEDING)" \
        --anchor now --top 20

--anchor accepts "now" or an ISO-8601 timestamp (use a past time to backtest).
Output is JSON: [{"entity_id": ..., "score": ...}, ...] sorted high to low.
"""
import argparse
import json
import sys
from datetime import datetime, timezone


def build_engine():
    """Return a ready relativedb.Engine.

    Point this at the connector module built for this project. Typical form:

        from connector import schema, wiring          # your project module
        from relativedb import Engine, RtNativeBackend
        return Engine(schema, wiring, model_backend=RtNativeBackend(schema=schema))
    """
    raise NotImplementedError(
        "Wire build_engine() to this project's connector "
        "(see reference/connectors.md and reference/api-python.md).")


def parse_anchor(value: str) -> datetime:
    if value == "now":
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value)


def main() -> None:
    ap = argparse.ArgumentParser(description="Score a RelQL query.")
    ap.add_argument("--query", required=True, help="a RelQL PREDICT statement")
    ap.add_argument("--anchor", default="now", help="'now' or an ISO-8601 time")
    ap.add_argument("--top", type=int, default=20, help="rows to print")
    args = ap.parse_args()

    from relativedb import ExecutionInput

    engine = build_engine()
    result = engine.execute(
        ExecutionInput(query=args.query, anchor_time=parse_anchor(args.anchor)))

    def score(p):
        # classification exposes .probability; regression carries a value.
        return getattr(p, "probability", getattr(p, "value", None))

    rows = sorted(
        ({"entity_id": p.id, "score": round(score(p), 4)}
         for p in result.predictions),
        key=lambda r: (r["score"] is not None, r["score"]), reverse=True,
    )[: args.top]

    json.dump(rows, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
