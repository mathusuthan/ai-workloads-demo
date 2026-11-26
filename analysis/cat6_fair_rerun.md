# Category 6 fair rerun — results

Generated: 2026-11-26T05:02:58.111650+00:00

Records read: 60 · ok runs used (latest ok per key): 60 · superseded ok records: 0 · error records: 0 · expected matrix: 4 arms × 3 presets × 5 repeats = 60 runs (complete, balanced).

## Arms

| Arm | Context | Role instructions | Models | Sandbox gate + 1 retry | Output caps |
|---|---|---|---|---|---|
| `shared_bus_original` | Shared growing thread, repo manual + noise, uncached | Today's unisolated_broadcast_swarm prompts | Sonnet all turns | no (scored once, no retry) | all roles 16000 |
| `shared_bus_matched_gate` | Shared growing thread, repo manual + noise, uncached | Governed per-role prompts (same as arms 3-4) | Sonnet all turns | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |
| `isolated_cached_gate` | Isolated narrow thread per agent + per-run cached repo prefix | Governed per-role prompts | Sonnet all turns | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |
| `tiered_gate` | Isolated narrow thread per agent + per-run cached repo prefix | Governed per-role prompts | Haiku except patch_author (Sonnet) | yes | patch_author 16000; orchestrator_plan 4000, ci_triager 4000, security_critic 4000, orchestrator_merge 4000 |

## Main results (per arm)

| Arm | Runs (ok) | Errors | First-attempt verified | 95% CI | Final verified | 95% CI | Checks first | Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | CpO billed | CpO cold | CpO warm | Mean model latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `shared_bus_original` | 15 | 0 | 12/15 (80.0%) | 54.8–93.0% | 12/15 (80.0%) | 54.8–93.0% | 147/150 | 147/150 | 0 (0) | $696.10 | $696.10 | $696.10 | $0.8701 | $0.8701 | $0.8701 | 154.7 |
| `shared_bus_matched_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $469.02 | $469.02 | $469.02 | $0.4690 | $0.4690 | $0.4690 | 30.8 |
| `isolated_cached_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $99.91 | $99.91 | $77.50 | $0.0999 | $0.0999 | $0.0775 | 38.8 |
| `tiered_gate` | 15 | 0 | 15/15 (100.0%) | 79.6–100.0% | 15/15 (100.0%) | 79.6–100.0% | 150/150 | 150/150 | 0 (0) | $56.20 | $56.20 | $32.71 | $0.0562 | $0.0562 | $0.0327 | 28.4 |

CpO = total spend across all ok runs in the arm ÷ final-verified runs (n/a when zero verified).
CpO using first-attempt verification instead:

| Arm | CpO billed (first attempt) | CpO cold (first attempt) | CpO warm (first attempt) |
|---|---|---|---|
| `shared_bus_original` | $0.8701 | $0.8701 | $0.8701 |
| `shared_bus_matched_gate` | $0.4690 | $0.4690 | $0.4690 |
| `isolated_cached_gate` | $0.0999 | $0.0999 | $0.0775 |
| `tiered_gate` | $0.0562 | $0.0562 | $0.0327 |

### Tokens per run (mean, min–max)

| Arm | Uncached input | Cache write | Cache read | Output | Thinking |
|---|---|---|---|---|---|
| `shared_bus_original` | 246,633 (228,556–257,785) | 0 (0–0) | 0 (0–0) | 20,283 (12,035–25,663) | 0 (0–0) |
| `shared_bus_matched_gate` | 214,112 (212,868–216,003) | 0 (0–0) | 0 (0–0) | 4,079 (3,851–4,392) | 0 (0–0) |
| `isolated_cached_gate` | 9,792 (9,203–10,477) | 9,337 (9,335–9,340) | 37,350 (37,340–37,360) | 5,325 (4,725–5,958) | 461 (0–1,072) |
| `tiered_gate` | 10,095 (9,186–11,009) | 18,675 (18,668–18,682) | 28,013 (28,002–28,023) | 5,408 (4,345–6,563) | 263 (0–1,205) |

## Per incident

| Arm | Preset | Runs (ok) | Errors | First-attempt verified | Final verified | Checks first | Checks final | Retries (fail→pass) | Billed $/1k runs | Cold $/1k runs | Warm $/1k runs | CpO billed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `shared_bus_original` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $709.27 | $709.27 | $709.27 | $0.7093 |
| `shared_bus_original` | inc-02 | 5 | 0 | 2/5 | 2/5 | 47/50 | 47/50 | 0 (0) | $721.54 | $721.54 | $721.54 | $1.8039 |
| `shared_bus_original` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $657.49 | $657.49 | $657.49 | $0.6575 |
| `shared_bus_matched_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $471.73 | $471.73 | $471.73 | $0.4717 |
| `shared_bus_matched_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $466.93 | $466.93 | $466.93 | $0.4669 |
| `shared_bus_matched_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $468.38 | $468.38 | $468.38 | $0.4684 |
| `isolated_cached_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $99.63 | $99.63 | $77.22 | $0.0996 |
| `isolated_cached_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $99.68 | $99.68 | $77.27 | $0.0997 |
| `isolated_cached_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $100.43 | $100.43 | $78.02 | $0.1004 |
| `tiered_gate` | inc-01 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $53.63 | $53.63 | $30.14 | $0.0536 |
| `tiered_gate` | inc-02 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $55.57 | $55.57 | $32.08 | $0.0556 |
| `tiered_gate` | inc-03 | 5 | 0 | 5/5 | 5/5 | 50/50 | 50/50 | 0 (0) | $59.40 | $59.40 | $35.92 | $0.0594 |

## Runs whose final patch was not verified

| Arm | Final-failed runs | Runs failing ci_unit | Runs failing adversarial | Runs failing ast | Failing checks ci_unit / adversarial / ast | Patch author stopped on max_tokens | No fenced patch |
|---|---|---|---|---|---|---|---|
| `shared_bus_original` | 3 | 0 | 0 | 3 | 0 / 0 / 3 | 0 | 0 |
| `shared_bus_matched_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |
| `isolated_cached_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |
| `tiered_gate` | 0 | 0 | 0 | 0 | 0 / 0 / 0 | 0 | 0 |

## Data quality

- Error records: 0 (billed $0.0000, excluded from CpO).
- Matrix: complete, balanced (0 missing keys).
- Turns stopped on `max_tokens` (ok runs):

| Arm | Stopped / total turns | By role (stopped/total) |
|---|---|---|
| `shared_bus_original` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `shared_bus_matched_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `isolated_cached_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |
| `tiered_gate` | 0/75 | orchestrator_plan 0/15, ci_triager 0/15, patch_author 0/15, security_critic 0/15, orchestrator_merge 0/15 |

- Individual turns stopped on `max_tokens` (ok runs used + error records): 0.

- Turns where the returned model differs from the intended model: 0.

## Re-scored with the current sandbox

Sandbox verdicts re-computed offline on each used record's recorded patched_code_first / patched_code_final. Turns, tokens, spend and retry decisions are as recorded. The as-recorded tables above are unchanged.

| Arm | Runs | First-attempt verified (recorded → re-scored) | Final verified (recorded → re-scored) | Final checks re-scored | CpO billed | CpO cold | CpO warm |
|---|---|---|---|---|---|---|---|
| `shared_bus_original` | 15 | 12 → 15 | 12 → 15 | 150/150 | $0.6961 | $0.6961 | $0.6961 |
| `shared_bus_matched_gate` | 15 | 15 → 15 | 15 → 15 | 150/150 | $0.4690 | $0.4690 | $0.4690 |
| `isolated_cached_gate` | 15 | 15 → 15 | 15 → 15 | 150/150 | $0.0999 | $0.0999 | $0.0775 |
| `tiered_gate` | 15 | 15 → 15 | 15 → 15 | 150/150 | $0.0562 | $0.0562 | $0.0327 |

Records whose verdict or passed-check count changed: 6.
- `shared_bus_original` inc-02 r0 (first_attempt): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS
- `shared_bus_original` inc-02 r0 (final): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS
- `shared_bus_original` inc-02 r2 (first_attempt): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS
- `shared_bus_original` inc-02 r2 (final): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS
- `shared_bus_original` inc-02 r4 (first_attempt): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS
- `shared_bus_original` inc-02 r4 (final): 9/10 (verified=False) → 10/10 (verified=True); flipped: AST-SEC-01 FAIL→PASS

## How to read the cost views

- **Billed**: each turn priced from the tokens the API reported (uncached input, cache write, cache read, output) at the returned model's rates in `app/core/pricing.py`. Output tokens include any thinking tokens.
- **Cold**: for the cached arms, the repo prefix on a turn is cache_creation + cache_read tokens; the first call per model in a run is priced as writing the whole prefix and later calls as reading it. This is the same rule as `runner._compute_step_cold_warm`. Uncached arms: cold = billed.
- **Warm**: every call in a cached arm is priced as reading the prefix (a cache already warmed by earlier traffic). Uncached arms: warm = billed.
- Each cached-arm run uses a fresh nonce in its prefix, so billed should be close to cold; any difference comes from how the API reported cache writes/reads within the run.
- $/1k runs = mean cost per run × 1,000. CpO is in $ per verified outcome.
