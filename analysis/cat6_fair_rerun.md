# Category 6 fair rerun — results

Generated: 2026-11-26T11:15:27.431452+00:00

Records read: 60 · ok runs used (latest ok per key): 60 · superseded ok records: 0 · error records: 0 · expected matrix: 4 arms × 3 presets × 5 repeats = 60 runs (complete, balanced).

Scoring: each patch is run through PR-SANDBOX-GATE-01 (4 CI unit + 4 adversarial + 2 static AST checks, Python `-I` subprocess); a run is verified when its final patch passes 10/10. Every run starts with a cold cache (a per-run nonce in the cached prefix) and every run is kept.

## Design: with and without the deck's lever

The deck's lever for this archetype: isolate sub-agent contexts and cache the shared repo prefix, and measure cost per verified outcome (CpO). Each cell: verified runs, CpO cold / warm, mean model time per run.

| | Sonnet 5.5 | Haiku agents + Sonnet patch author |
|---|---|---|
| Without: shared bus, same instructions, sandbox check with one retry | `shared_bus_matched_gate`: 15/15 verified · CpO $0.4690 / $0.4690 · 30.8 s | `shared_bus_tiered_gate`: 15/15 verified · CpO $0.1246 / $0.1246 · 25.6 s |
| With: isolated agents + cached repo prefix, sandbox check with one retry | `isolated_cached_gate`: 15/15 verified · CpO $0.0999 / $0.0775 · 38.8 s | `tiered_gate`: 15/15 verified · CpO $0.0562 / $0.0327 · 28.4 s |

## Arms

| Arm | Context | Role instructions | Models | Sandbox gate + 1 retry | Output caps |
|---|---|---|---|---|---|
| `shared_bus_matched_gate` | Shared growing thread, repo manual + noise, uncached | Governed per-role prompts (same as the isolated arms) | Sonnet all turns | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |
| `shared_bus_tiered_gate` | Shared growing thread, repo manual + noise, uncached | Governed per-role prompts (same as the isolated arms) | Haiku except patch_author (Sonnet) | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |
| `isolated_cached_gate` | Isolated narrow thread per agent + per-run cached repo prefix | Governed per-role prompts | Sonnet all turns | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |
| `tiered_gate` | Isolated narrow thread per agent + per-run cached repo prefix | Governed per-role prompts | Haiku except patch_author (Sonnet) | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |

## Main results (per arm)

| Arm | Runs (ok) | Errors | First-attempt verified | 95% CI | Final verified | 95% CI | Checks first | Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | CpO billed | CpO cold | CpO warm | Mean model latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `shared_bus_matched_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $469.02 | $469.02 | $469.02 | $0.4690 | $0.4690 | $0.4690 | 30.8 |
| `shared_bus_tiered_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $124.61 | $124.61 | $124.61 | $0.1246 | $0.1246 | $0.1246 | 25.6 |
| `isolated_cached_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $99.91 | $99.91 | $77.50 | $0.0999 | $0.0999 | $0.0775 | 38.8 |
| `tiered_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $56.20 | $56.20 | $32.71 | $0.0562 | $0.0562 | $0.0327 | 28.4 |

CpO = total spend across all ok runs in the arm ÷ final-verified runs (n/a when zero verified).
CpO using first-attempt verification instead:

| Arm | CpO billed (first attempt) | CpO cold (first attempt) | CpO warm (first attempt) |
|---|---|---|---|
| `shared_bus_matched_gate` | $0.4690 | $0.4690 | $0.4690 |
| `shared_bus_tiered_gate` | $0.1246 | $0.1246 | $0.1246 |
| `isolated_cached_gate` | $0.0999 | $0.0999 | $0.0775 |
| `tiered_gate` | $0.0562 | $0.0562 | $0.0327 |

### Tokens per run (mean, min–max)

| Arm | Uncached input | Cache write | Cache read | Output | Thinking |
|---|---|---|---|---|---|
| `shared_bus_matched_gate` | 214,112 (212,868–216,003) | 0 (0–0) | 0 (0–0) | 4,079 (3,851–4,392) | 0 (0–0) |
| `shared_bus_tiered_gate` | 214,585 (212,606–216,666) | 0 (0–0) | 0 (0–0) | 4,416 (3,834–5,005) | 0 (0–0) |
| `isolated_cached_gate` | 9,792 (9,203–10,477) | 9,337 (9,335–9,340) | 37,350 (37,340–37,360) | 5,325 (4,725–5,958) | 461 (0–1,072) |
| `tiered_gate` | 10,095 (9,186–11,009) | 18,675 (18,668–18,682) | 28,013 (28,002–28,023) | 5,408 (4,345–6,563) | 263 (0–1,205) |

## Per incident

| Arm | Preset | Runs (ok) | Errors | First-attempt verified | Final verified | Checks first | Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | CpO billed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `shared_bus_matched_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $471.73 | $471.73 | $471.73 | $0.4717 |
| `shared_bus_matched_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $466.93 | $466.93 | $466.93 | $0.4669 |
| `shared_bus_matched_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $468.38 | $468.38 | $468.38 | $0.4684 |
| `shared_bus_tiered_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $125.44 | $125.44 | $125.44 | $0.1254 |
| `shared_bus_tiered_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $124.37 | $124.37 | $124.37 | $0.1244 |
| `shared_bus_tiered_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $124.03 | $124.03 | $124.03 | $0.1240 |
| `isolated_cached_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $99.63 | $99.63 | $77.22 | $0.0996 |
| `isolated_cached_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $99.68 | $99.68 | $77.27 | $0.0997 |
| `isolated_cached_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $100.43 | $100.43 | $78.02 | $0.1004 |
| `tiered_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $53.63 | $53.63 | $30.14 | $0.0536 |
| `tiered_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $55.57 | $55.57 | $32.08 | $0.0556 |
| `tiered_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $59.40 | $59.40 | $35.92 | $0.0594 |

## Runs whose final patch was not verified

| Arm | Final-failed runs | Runs failing ci_unit | Runs failing adversarial | Runs failing ast | Failing checks ci_unit / adversarial / ast | Patch author stopped on max_tokens | No fenced patch |
|---|---|---|---|---|---|---|---|
| `shared_bus_matched_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |
| `shared_bus_tiered_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |
| `isolated_cached_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |
| `tiered_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |

## Data quality

- Error records: 0 (billed $0.0000, excluded from CpO).
- Matrix: complete, balanced (0 missing keys).
- Turns stopped on `max_tokens` (ok runs):

| Arm | Stopped / total turns | By role (stopped/total) |
|---|---|---|
| `shared_bus_matched_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `shared_bus_tiered_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `isolated_cached_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `tiered_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |

- Individual turns stopped on `max_tokens` (ok runs used + error records): 0.

- Largest Haiku prompt: 46,108 tokens; Haiku calls over 100K prompt tokens (priced at the long-prompt rate): 0.
- Turns where the returned model differs from the intended model: 0.

## Limits of this data

- Every arm verified the same share of its runs (100.0%), so these incidents do not separate the configurations on correctness; the arms differ in tokens, cost and latency only, and CpO equals cost per run divided by that share in every arm.
- Each incident is a single-file fix handled by five agent roles; larger tasks were not measured.

## How to read the cost views

- **Billed**: each turn priced from the tokens the API reported (uncached input, cache write, cache read, output) at the returned model's rates in `app/core/pricing.py`. Output tokens include any thinking tokens.
- **Cold**: for the cached arms, the repo prefix on a turn is cache_creation + cache_read tokens; the first call per model in a run is priced as writing the whole prefix and later calls as reading it. This is the same rule as `runner._compute_step_cold_warm`. Uncached arms: cold = billed.
- **Warm**: every call in a cached arm is priced as reading the prefix (a cache already warmed by earlier traffic). Uncached arms: warm = billed.
- Each cached-arm run uses a fresh nonce in its prefix, so billed should be close to cold; any difference comes from how the API reported cache writes/reads within the run.
- $/1k runs = mean cost per run × 1,000. CpO is in $ per verified outcome.
