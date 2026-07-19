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
- **Multiclass classification** executes via the checkpoint's **text head**: the
  masked target cell is decoded to a 384-dim embedding, L2-normalized, and
  matched by cosine similarity to the class labels' `all-MiniLM-L12-v2`
  embeddings. It returns a predicted class (argmax cosine — reference-exact) plus
  approximate, uncalibrated class probabilities (a softmax over the cosine
  scores, not a trained softmax head). No retraining — it reuses the existing
  text head.
- **Ranking** (`LIST_DISTINCT(table.fk)` / `ARRAY_AGG(table.fk)` with
  `RANK TOP k` in the frame) executes via per-candidate existence scoring:
  distinct parent-table IDs (temporally bounded, capped at 1000) are each
  scored with the existence head, sigmoided, and the top *k* returned in the
  `ranked` field. No retraining — it reuses the existing existence/number head.
- `RETURN QUANTILES`/`INTERVAL` are not in the grammar: a single point head
  exposes no distribution, so they are rejected at parse time.
- A missing library or checkpoint raises a specific, actionable error
  (`RtNativeUnavailableError` in Python).

## Fine-tuning (optional, frozen backbone)

The same library exposes a frozen-backbone adapter path: `rt_encode_targets_device`
returns the final target-cell state `[N, 512]`, and a small task head is fitted
on those states with AdamW (`rt_finetune_head_*`). All four task types are
supported. Surfaced in Python as `Engine.finetune(...) -> FineTunedHead`, saved
as a ~2 KB safetensors adapter and served via `RtNativeBackend(head=...)`.

Fitting requires **Metal**; head inference is CPU, so an adapter trained on a
Mac serves anywhere. The transformer itself is never updated — that is what
makes each example encodable once and fitting fast.
