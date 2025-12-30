# Hierarchical Image Memory & Agent Orchestration — Single-File Spec (v1.1)

> A single-file, implementation-ready spec combining memory layout, delta/branching, tiered storage, semantic index/prefetch, deterministic replay, integrity, agent orchestration, OS interaction, tool autonomy, ops, and a 90-day plan.

---

## 0) Objectives & SLOs

**Primary goal:** Retrieve, update, and replay large model state/skills as an image pyramid—fast, deterministic, and cost-efficient.

**SLO defaults (tunable):**

* **p95 query latency (coarse→fine):** ≤ **150 ms** local / ≤ **350 ms** cross-AZ for ≤K=8 high-res tiles.
* **Warm NVMe cache hit rate:** ≥ **95 %** for the top 10% most-referenced tiles.
* **Prefetch coverage:** ≥ **90 %** of tiles needed for a batch of M queries.
* **Deterministic replay fidelity:** **Byte-for-byte** identical outputs under a pinned environment.
* **Indexer freshness:** New/updated tiles searchable in **<10 s**.

---

## 1) Hierarchical Image Memory (HIM)

### 1.1 Multiresolution Layout

* **Pyramid:** Levels `L0…Ln`, each downsampled by powers of two. Tiles are **512×512** with optional **16-px halo** to prevent seam artifacts.
* **Streams (bands):** `kv_cache`, `emb`, `skills`, `logs`, `audit` (optional). Each has its own codec, lifecycle, and tiering policy.
* **Content addressing:**

  ```
  tile_id = blake3(stream | snapshot_id | level | x | y | payload_bytes)
  key     = {stream}/{snapshot_id}/{level}/{x}/{y}/{tile_id[:12]}
  ```
* **Recommended formats/codecs:**

  * `kv_cache`: Zarr v3 or TileDB, chunk = 512×512×C, dtype **fp8/int8** (per-channel scales), fallback **fp16**; compression **zstd**.
  * `emb`: 256–1024 dims, **fp16** or **int8** with product quantization (PQ).
  * `skills`: JSON or WASM modules; signed releases.
  * `logs/audit`: Parquet, ~64 MB row groups for efficient scans.
* **Overhead:** Full pyramid overhead ≈ **4/3** of base if all levels kept; truncate low levels to cap overhead.

**Coarse→Fine Retrieval (fixed-latency path):**

1. **Coarse scan:** At most **3** tiles at top levels (`L(n), L(n-1)`), using in-RAM centroids/embeddings only.
2. **Localize:** Form ROIs via nearest-neighbors in `emb` plus optional text-to-tile cross-attention.
3. **Refine:** Load ≤ **K** high-res tiles (`L0…L2`) from NVMe; fuse into working buffer.
4. **Accept:** Stop when acceptance target (e.g., recall≥0.98 or confidence≥τ) is hit or budget **T** expires.

### 1.2 Delta Images & Branching

* **Sparse deltas:** Delta tiles reference a `parent_tile_id`; payload uses block-sparse patches (XOR+RLE/zstd-delta for numeric arrays; rabin-chunking for text/code).
* **Branch DAG:**

  * Nodes = **snapshots**; edges carry `{parent_snapshot_id, merge_policy}`.
  * **Conflict resolution:** default **LWW** (Lamport timestamp). Domain-specific CRDTs for numeric bands; AST-aware merges for `skills`.
* **Snapshot tagging:** `{task_id, owner, semantic_summary}` + full provenance (model, code SHA, seed, env hashes). Tags are signed.

### 1.3 Storage Tiers

* **Warm:** NVMe on ZFS (recordsize=1M, compression=zstd) or btrfs (zstd:6). Keep top-K% hottest tiles (by access + semantic pins).
* **Cold:** S3/MinIO; store bundles as **packfiles** (CAR-like, 128–512 MB) to amortize GET overhead; lifecycle to IA/Glacier.
* **Tiering policy:** LRU + pins (**critical skills**, **recent deltas**, **planner hints**). Coalesce tiny deltas before warm admission.
* **Async prefetch:** Planner consumes **Hint** events (Kafka/NATS) and stages cold→warm ahead of use.

### 1.4 Semantic Index & Prefetch

* **Vector store:** FAISS **HNSW** in RAM for top levels, **IVF-PQ** on SSD for deep levels; text side uses **BM25/Lucene** over tags/logs.
* **Rerank:** Cross-encoder (mini-LM) on top-50 candidates.
* **Batch target:** For **M** queries, stage enough tiles so ≥ **P%** are warm **before** decode.
* **Hint schema:**

  ```json
  {"query_id":"…","snapshot_id":"…","stream":"kv_cache",
   "level_range":[2,0],"bboxes":[[x,y,w,h],…],"confidence":0.8}
  ```

### 1.5 Deterministic Replays

* **Trace capture:** RNG seeds, CUDA/cuDNN/cuBLAS hashes, driver, model/weights digest, kernel flags, exact IO order.
* **Environment pinning:** OCI image (SHA) + driver ABI pin or Nix flake lock; startup self-check rejects drift.
* **Replay mode:** `--deterministic` disables async nondeterminism; outputs are **bitwise identical** for same inputs.

### 1.6 Integrity (optional but recommended)

* **Digests:** blake3 per tile, per-packfile Merkle.
* **ECC:** Reed–Solomon across packfiles (k+m) tuned to media failure.
* **Self-heal:** Verifier rehydrates bad tiles from cold or parity.

---

## 2) Public API (REST/gRPC Sketch)

### 2.1 Schemas

**Snapshot**

```json
{
  "snapshot_id":"snp_01HZX…",
  "parents":["snp_01HZW…"],
  "created_at":"2025-09-18T12:34:56Z",
  "tags":{"task_id":"TX-423","summary":"UI flows v3 fine-tune"},
  "provenance":{"model":"llama-X-70b-fp8","code_sha":"f2ab…","cuda":"12.4.1","driver":"555.42","seed":133742},
  "merge_policy":"lww"
}
```

**TileMeta**

```json
{
  "tile_id":"tl_b3c7…",
  "stream":"kv_cache",
  "snapshot_id":"snp_01HZX…",
  "level":2,"x":104,"y":33,
  "shape":[512,512,64],"dtype":"fp8",
  "parent_tile_id":"tl_aa91…",
  "halo":16,
  "checksum":"b3a1…","size_bytes":32768
}
```

### 2.2 Endpoints

* `GET /v1/snapshots/:id`
* `POST /v1/snapshots/:id/merge`
* `POST /v1/query` → `QueryPlan{tile_ids, acceptance, budget_ms}`
* `POST /v1/prefetch` with `Hints[]`
* `GET /v1/tiles/:stream/:snapshot/:level/:x/:y`
* `POST /v1/tiles` (bulk ingest; supports deltas)
* `POST /v1/replay` with `{snapshot_id, trace_id}`

### 2.3 Client Query Flow

```python
# pseudocode
plan = query_api.plan(goal="find button 'Submit'", snapshot_id="snp_…", budget_ms=150)
ids  = plan.tile_ids
tiles = tile_api.fetch(ids)
state = fuse(tiles)
result = locate(state, goal)  # bbox, confidence
```

---

## 3) Agent Orchestration

### 3.1 Roles & Contracts

* **Planner:** goal → plan (`tile_ids`, tools, constraints).
* **Executor:** plan → actions (read tiles, run tools).
* **Critic:** evaluate acceptance; emit `FixIt` deltas or approve.
* **Memory-Keeper:** persist minimal deltas; promote snapshots.
* **Toolsmith:** build/install tools; update registry.

All role I/O is JSON-schema’d. Agents may assume roles dynamically; a router binds tasks to roles.

### 3.2 Planning Loop

`Plan → Act → Observe → Critique → Update` with bias to **reuse** tiles and record **block-sparse** updates only.

### 3.3 Model Routing

* Router maintains cost/latency curves per model/tool; selects via **bandit** with regret bounds. Logs counterfactuals to prove win vs single-model baseline.

---

## 4) OS Interaction

### 4.1 Perception

* **Pipeline:** screenshot → OCR (Tesseract/TrOCR) → UI detector (ViLT/DETR) → scene graph.
* **Scene Graph:**

```json
{"nodes":[{"id":"btn_12","type":"button","text":"Submit","bbox":[x,y,w,h],"state":{"enabled":true}}],
 "edges":[{"from":"dlg_1","to":"btn_12","rel":"contains"}],
 "confidence":0.97}
```

* Target detection accuracy **R ≥ 97%** on benchmark; if confidence < τ, request more tiles or alternate model.

### 4.2 Action

* Mouse/keyboard/clipboard/files via host agent (Windows UIA, macOS AX, Linux X11/Wayland).
* **Guardrails:** RBAC + OPA/Rego; kill switch; time-boxed leases; signed playbooks; untrusted tools in microVMs (Firecracker) by default.

### 4.3 Playbook Auto-Learning

* From ≥ **K=20** demonstrations (screen+input traces), distill skills with pre/postconditions and action graph. Store in `skills` stream; index by UI/text embeddings, app version, and OS. Version with semantic diffs and attach deterministic tests.

---

## 5) Tool Autonomy

### 5.1 Registry & ABI

**Manifest**

```json
{"name":"ocr","version":"1.2.3","stdin_schema":{…},"stdout_schema":{…},
 "caps":["ocr","pdf"],"binary_sha":"…","sandbox":"microvm"}
```

* Health checks + conformance tests; signed by Toolsmith.

### 5.2 Discovery & Adoption

* Agents propose new tools; build in isolated builder; run spec tests; policy-gate; publish to registry. Adoption via scorecards (latency, accuracy, safety).

---

## 6) Ops, Observability, Safety

**Metrics (Prometheus/Otel):** tile I/O hits/misses; warm→cold latency; bytes/s by stream; planner coverage %; stale hint rate; query latency by level/K; determinism failures; DAG conflicts; S3 cost/egress; NVMe write amp.

**Backpressure:** If warm free <10%, demote low-value tiles and throttle promotions. If S3 5xx spikes, degrade: lower P, increase TTLs, bias to local compute.

**DR:** Cross-region replication of cold packs; weekly restore drills; snapshot catalog RTO <1 h; full packset <12 h.

**Security:** Per-stream encryption at rest; per-snapshot KMS keys; signed snapshots/tools; provenance on every run; retention: logs 30d, skills indefinite, kv_cache per task TTL.

---

## 7) Capacity Planning (defaults)

* **Tile density:** 4k×4k base (~8×8 tiles at L0) × 5 levels ⇒ ~1.33× overhead pre-compression.
* **Warm NVMe:** Working set ~2 TB logical ⇒ provision ~3 TB NVMe.
* **Cold S3:** Plan ~10× warm capacity.
* **Indexer RAM:** top-two levels’ centroids (e.g., 16M tiles × 256 dims int8 ≈ 4 GB).
* **Network:** budget 5–8 ms per in-region S3 GET; packfiles amortize.

---

## 8) Implementation Plan (90 Days)

**Phase 1 (Weeks 1–4): Substrate**

* Tile store (Zarr/TileDB + zstd), CAS (blake3), `GET/POST /tiles`.
* Pyramid builder + delta encoder.
* Warm NVMe + S3 packfile r/w.
* Minimal FAISS HNSW over centroids.
  **Exit:** ≤K tiles in ≤150 ms p95 (local); CRUD snapshots; query→tiles path works.

**Phase 2 (Weeks 5–8): Index + Planner + Prefetch**

* Planner daemon + hint bus; batch prefetch to ≥90% coverage (synthetic).
* Reranker; BM25 over tags/logs.
* Observability baseline dashboards.
  **Exit:** p95 E2E ≤250 ms with prefetch; packfile path solid; metrics green.

**Phase 3 (Weeks 9–12): Agents + Replay + Safety**

* Planner/Executor/Critic/Memory-Keeper APIs.
* Deterministic replay with pinned OCI/Nix; failed replays block promotions.
* Policy engine with RBAC; action host adapter for one OS.
  **Exit:** Replays pass; one real playbook learned from ≥20 demos; router shows cost/latency win vs baseline.

---

## 9) Algorithms & Heuristics (defaults)

* **K selection:** `K = min(8, ceil(ROI_area / tile_area))`, cap at 16 if `T` allows.
* **Acceptance:** start `confidence ≥ 0.95` or `recall@10 ≥ 0.98`; Critic raises K or drops level if unmet.
* **Pins:** any tile touched >N times/10 min or tagged critical is non-evictable for 30 min.
* **Deltas:** promote deltas >30% of base size to full tiles; cap delta chain depth at 4.
* **Merges (skills):** AST-aware three-way; fallback LWW with conflict logs requiring review.

---

## 10) Developer Ergonomics

* **CLI:**

  ```
  him snap create --from snp_base --tag task_id=TX-423
  him tiles put --stream kv_cache --snapshot snp_… --level 0 --x 10 --y 12 tile.npy
  him query --goal "find submit button" --snapshot snp_… --budget 150
  him prefetch --plan plan.json
  him replay --snapshot snp_… --trace tr_…
  ```
* **OpenAPI + SDKs** (Py/TS/Rust) with actionable errors.
* **Web Explorer:** pyramid/branch/diff view; tile lineage, hotness, integrity, authorship.
* **Bug report button:** minimal repro (snapshot+trace), redacted.
* **Docs + notebooks:** build pyramid; query & prefetch; delta & merge; deterministic replay.

---

## 11) Risks (and mitigations)

* **Delta chains inflate latency:** cap depth; promote to full tiles aggressively.
* **Cross-AZ S3 tails:** packfiles; RAM centroids; pin critical tiles.
* **GPU determinism is brittle:** hash drivers/kernels; ban nondeterministic ops; assert and block on drift.
* **“Unsandboxed” tools risk:** policy-as-code, default-deny; sign artifacts; microVM by default.
* **Index drift:** transactional index updates with tile commits; validators compare counts/content.

---

## 12) Integration Notes

* **FAISS:** HNSW (RAM) + IVF-PQ (SSD).
* **ViLT:** per-tile UI embeddings; rerank via cross-attention for text→UI alignment.
* **LangChain/Ollama:** wrap Planner/Executor/Critic as tools; memory reads request `QueryPlan`s; Critic emits `FixIt` deltas back into HIM.

---

## 13) Acceptance Tests

* For **M=100** mixed queries on a benchmark snapshot:

  * Prefetch coverage ≥ **90%**; warm hit ≥ **95%**; p95 E2E ≤ **250 ms**.
  * Replays produce **identical bytes** for same snapshot+trace.
  * Merge two active branches with no human conflict in ≥ **95%** of cases; any conflict is localized to specific tiles and logged.

---

### Concrete Next Moves

1. Stand up **tile store + CAS** with Zarr/TileDB and REST skeleton.
2. Implement **planner daemon + hint bus**; measure prefetch coverage on synthetic load.
3. Wire **deterministic replay** harness and block promotions on drift.
4. Ship a **web explorer**; visibility is half the product.
