# Native backend setup (required to score)

`RtNativeBackend` is the **only** scoring path — the engine has no model-free
default and errors if you execute without a model backend. Parsing and
validation (`relativedb.parse` / `validate`, `EXPLAIN PLAN`) work without it;
executing a query does not.

## 1. Build `librt_c` (the C++ engine)

From a checkout of the RelativeDB engine repo:

```bash
cd cpp
cmake -B build -S . && cmake --build build -j
```

Produces `cpp/build/librt_c.{dylib,so}`. All language bindings auto-discover it
at `cpp/build/`. If it lives elsewhere, point at it:

```bash
export RELATIVEDB_RT_LIB=/path/to/librt_c.dylib
```

Java precedence: system property `relativedb.rt.lib` → env `RELATIVEDB_RT_LIB` →
sibling `cpp/build/` → loader path.

## 2. Get the RT-J checkpoint

Default model routing resolves these against your **local** Hugging Face cache
(nothing downloads implicitly):

- classification → `hf://stanford-star/rt-j/classification`
- regression / forecasting → `hf://stanford-star/rt-j/regression`

Fetch the `stanford-star/rt-j` checkpoint into the HF cache ahead of time (e.g.
`huggingface-cli download stanford-star/rt-j`). `file://` paths and plain paths
also work via a custom `ModelConfig`. Override the Java cache root with
`relativedb.rt.hf.cache` / `RELATIVEDB_RT_HF_CACHE`.

## 3. Python extra

```bash
pip install "relationdb[rt]"     # sentence-transformers + huggingface_hub
```

Python computes MiniLM text embeddings itself. Java and Rust take a
`TextEncoder` (a precomputed 384-dim table for closed vocabularies).

## Behavior & limits

- Classification returns probabilities (sigmoid over logits); regression returns
  denormalized values.
- The current single-head checkpoint serves **binary classification** and
  **regression** only. Multiclass, ranking (`RANK TOP k`), and
  `RETURN QUANTILES`/`INTERVAL` raise a clear error at execution (they still
  parse and validate).
- A missing library or checkpoint raises a specific, actionable error
  (`RtNativeUnavailableError` in Python).
