# Category 3 quality rerun — results

Generated: 2026-11-25T16:04:02.358738+00:00 · answer key `2026-11-25.2` (`cat3_quality_keys.json`)

Rerun records: 18 read from `/Users/mathu/Projects/NuSysDesPrac/novamart-ai-archetypes/backend/experiments/cat3_quality/runs.jsonl` · ok runs used (latest ok per key): 18 · superseded ok: 0 · error records: 0. Original capture: `cat3_golden_replays.json` (6 rung × session cells, n=1 each).

Run settings: turns max_tokens 4096, summariser max_tokens 1600, probes max_tokens 4096 (≤3 concurrent per run), per-call client timeout 180s, per-run nonce prepended to the system text on every rung. Values: hits/total (rate) [Wilson 95% interval, %].

## Answer key

| Session | turn/handbook | turn/session | ledger/handbook | ledger/session | probe/session |
|---|---|---|---|---|---|
| desk-01 | 34 | 1 | 17 | 8 | 6 |
| desk-02 | 30 | 4 | 18 | 6 | 6 |

## Fresh reruns — quality per rung (pooled over sessions and repeats)

Matrix: 3 rungs × 2 sessions × 3 repeats = 18 runs (complete, balanced).

Turn-fact recall (turns 1–9; each reply scored against its own turn's facts):

| Group | Sessions | Turns 1–9 | Turns 1–4 | Turns 5–9 |
|---|---|---|---|---|
| `naive_full_history` | 6 | 205/207 (99.0%) [96.5–99.7] | 94/96 (97.9%) [92.7–99.4] | 111/111 (100.0%) [96.7–100.0] |
| `prefix_cached_history` | 6 | 203/207 (98.1%) [95.1–99.2] | 92/96 (95.8%) [89.8–98.4] | 111/111 (100.0%) [96.7–100.0] |
| `prefix_cached_summarized` | 6 | 205/207 (99.0%) [96.5–99.7] | 96/96 (100.0%) [96.2–100.0] | 109/111 (98.2%) [93.7–99.5] |

Ledger recall (turn-10 reply scored against ledger facts):

| Group | Overall | Origin 1–3 | Origin 4–6 | Origin 7–9 | Source handbook | Source session |
|---|---|---|---|---|---|---|
| `naive_full_history` | 106/147 (72.1%) [64.4–78.7] | 37/51 (72.5%) [59.1–82.9] | 40/51 (78.4%) [65.4–87.5] | 29/45 (64.4%) [49.8–76.8] | 89/105 (84.8%) [76.7–90.4] | 17/42 (40.5%) [27.0–55.5] |
| `prefix_cached_history` | 110/147 (74.8%) [67.2–81.2] | 39/51 (76.5%) [63.2–86.0] | 41/51 (80.4%) [67.5–89.0] | 30/45 (66.7%) [52.1–78.6] | 88/105 (83.8%) [75.6–89.6] | 22/42 (52.4%) [37.7–66.6] |
| `prefix_cached_summarized` | 91/147 (61.9%) [53.8–69.4] | 24/51 (47.1%) [34.1–60.5] | 37/51 (72.5%) [59.1–82.9] | 30/45 (66.7%) [52.1–78.6] | 76/105 (72.4%) [63.2–80.0] | 15/42 (35.7%) [23.0–50.8] |

Probe accuracy (independent turn-11 questions after turn 10):

| Group | Overall | Origin 1–6 | Origin 7–9 |
|---|---|---|---|
| `naive_full_history` | 36/36 (100.0%) [90.4–100.0] | 24/24 (100.0%) [86.2–100.0] | 12/12 (100.0%) [75.8–100.0] |
| `prefix_cached_history` | 36/36 (100.0%) [90.4–100.0] | 24/24 (100.0%) [86.2–100.0] | 12/12 (100.0%) [75.8–100.0] |
| `prefix_cached_summarized` | 2/36 (5.6%) [1.5–18.1] | 2/24 (8.3%) [2.3–25.8] | 0/12 (0.0%) [0.0–24.2] |

### Per rung × session

Turn-fact recall (turns 1–9; each reply scored against its own turn's facts):

| Group | Sessions | Turns 1–9 | Turns 1–4 | Turns 5–9 |
|---|---|---|---|---|
| `naive_full_history` desk-01 | 3 | 105/105 (100.0%) [96.5–100.0] | 48/48 (100.0%) [92.6–100.0] | 57/57 (100.0%) [93.7–100.0] |
| `naive_full_history` desk-02 | 3 | 100/102 (98.0%) [93.1–99.5] | 46/48 (95.8%) [86.0–98.8] | 54/54 (100.0%) [93.4–100.0] |
| `prefix_cached_history` desk-01 | 3 | 101/105 (96.2%) [90.6–98.5] | 44/48 (91.7%) [80.4–96.7] | 57/57 (100.0%) [93.7–100.0] |
| `prefix_cached_history` desk-02 | 3 | 102/102 (100.0%) [96.4–100.0] | 48/48 (100.0%) [92.6–100.0] | 54/54 (100.0%) [93.4–100.0] |
| `prefix_cached_summarized` desk-01 | 3 | 105/105 (100.0%) [96.5–100.0] | 48/48 (100.0%) [92.6–100.0] | 57/57 (100.0%) [93.7–100.0] |
| `prefix_cached_summarized` desk-02 | 3 | 100/102 (98.0%) [93.1–99.5] | 48/48 (100.0%) [92.6–100.0] | 52/54 (96.3%) [87.5–99.0] |

Ledger recall (turn-10 reply scored against ledger facts):

| Group | Overall | Origin 1–3 | Origin 4–6 | Origin 7–9 | Source handbook | Source session |
|---|---|---|---|---|---|---|
| `naive_full_history` desk-01 | 63/75 (84.0%) [74.1–90.6] | 24/27 (88.9%) [71.9–96.1] | 19/24 (79.2%) [59.5–90.8] | 20/24 (83.3%) [64.1–93.3] | 50/51 (98.0%) [89.7–99.7] | 13/24 (54.2%) [35.1–72.1] |
| `naive_full_history` desk-02 | 43/72 (59.7%) [48.2–70.3] | 13/24 (54.2%) [35.1–72.1] | 21/27 (77.8%) [59.2–89.4] | 9/21 (42.9%) [24.5–63.5] | 39/54 (72.2%) [59.1–82.4] | 4/18 (22.2%) [9.0–45.2] |
| `prefix_cached_history` desk-01 | 67/75 (89.3%) [80.3–94.5] | 25/27 (92.6%) [76.6–97.9] | 21/24 (87.5%) [69.0–95.7] | 21/24 (87.5%) [69.0–95.7] | 50/51 (98.0%) [89.7–99.7] | 17/24 (70.8%) [50.8–85.1] |
| `prefix_cached_history` desk-02 | 43/72 (59.7%) [48.2–70.3] | 14/24 (58.3%) [38.8–75.5] | 20/27 (74.1%) [55.3–86.8] | 9/21 (42.9%) [24.5–63.5] | 38/54 (70.4%) [57.2–80.9] | 5/18 (27.8%) [12.5–50.9] |
| `prefix_cached_summarized` desk-01 | 59/75 (78.7%) [68.1–86.4] | 17/27 (63.0%) [44.2–78.5] | 21/24 (87.5%) [69.0–95.7] | 21/24 (87.5%) [69.0–95.7] | 47/51 (92.2%) [81.5–96.9] | 12/24 (50.0%) [31.4–68.6] |
| `prefix_cached_summarized` desk-02 | 32/72 (44.4%) [33.5–55.9] | 7/24 (29.2%) [14.9–49.2] | 16/27 (59.3%) [40.7–75.5] | 9/21 (42.9%) [24.5–63.5] | 29/54 (53.7%) [40.6–66.3] | 3/18 (16.7%) [5.8–39.2] |

Probe accuracy (independent turn-11 questions after turn 10):

| Group | Overall | Origin 1–6 | Origin 7–9 |
|---|---|---|---|
| `naive_full_history` desk-01 | 18/18 (100.0%) [82.4–100.0] | 12/12 (100.0%) [75.8–100.0] | 6/6 (100.0%) [61.0–100.0] |
| `naive_full_history` desk-02 | 18/18 (100.0%) [82.4–100.0] | 12/12 (100.0%) [75.8–100.0] | 6/6 (100.0%) [61.0–100.0] |
| `prefix_cached_history` desk-01 | 18/18 (100.0%) [82.4–100.0] | 12/12 (100.0%) [75.8–100.0] | 6/6 (100.0%) [61.0–100.0] |
| `prefix_cached_history` desk-02 | 18/18 (100.0%) [82.4–100.0] | 12/12 (100.0%) [75.8–100.0] | 6/6 (100.0%) [61.0–100.0] |
| `prefix_cached_summarized` desk-01 | 2/18 (11.1%) [3.1–32.8] | 2/12 (16.7%) [4.7–44.8] | 0/6 (0.0%) [0.0–39.0] |
| `prefix_cached_summarized` desk-02 | 0/18 (0.0%) [0.0–17.6] | 0/12 (0.0%) [0.0–24.2] | 0/6 (0.0%) [0.0–39.0] |

## Original capture (golden replays, n=1 per cell) — quality

Turn-fact recall (turns 1–9; each reply scored against its own turn's facts):

| Group | Sessions | Turns 1–9 | Turns 1–4 | Turns 5–9 |
|---|---|---|---|---|
| `naive_full_history` | 2 | 69/69 (100.0%) [94.7–100.0] | 32/32 (100.0%) [89.3–100.0] | 37/37 (100.0%) [90.6–100.0] |
| `prefix_cached_history` | 2 | 69/69 (100.0%) [94.7–100.0] | 32/32 (100.0%) [89.3–100.0] | 37/37 (100.0%) [90.6–100.0] |
| `prefix_cached_summarized` | 2 | 69/69 (100.0%) [94.7–100.0] | 32/32 (100.0%) [89.3–100.0] | 37/37 (100.0%) [90.6–100.0] |

Ledger recall (turn-10 reply scored against ledger facts):

| Group | Overall | Origin 1–3 | Origin 4–6 | Origin 7–9 | Source handbook | Source session |
|---|---|---|---|---|---|---|
| `naive_full_history` | 32/49 (65.3%) [51.3–77.1] | 11/17 (64.7%) [41.3–82.7] | 11/17 (64.7%) [41.3–82.7] | 10/15 (66.7%) [41.7–84.8] | 26/35 (74.3%) [57.9–85.8] | 6/14 (42.9%) [21.4–67.4] |
| `prefix_cached_history` | 35/49 (71.4%) [57.6–82.2] | 13/17 (76.5%) [52.7–90.4] | 11/17 (64.7%) [41.3–82.7] | 11/15 (73.3%) [48.0–89.1] | 30/35 (85.7%) [70.6–93.7] | 5/14 (35.7%) [16.3–61.2] |
| `prefix_cached_summarized` | 30/49 (61.2%) [47.2–73.6] | 6/17 (35.3%) [17.3–58.7] | 13/17 (76.5%) [52.7–90.4] | 11/15 (73.3%) [48.0–89.1] | 25/35 (71.4%) [54.9–83.7] | 5/14 (35.7%) [16.3–61.2] |

### Per rung × session

Turn-fact recall (turns 1–9; each reply scored against its own turn's facts):

| Group | Sessions | Turns 1–9 | Turns 1–4 | Turns 5–9 |
|---|---|---|---|---|
| `naive_full_history` desk-01 | 1 | 35/35 (100.0%) [90.1–100.0] | 16/16 (100.0%) [80.6–100.0] | 19/19 (100.0%) [83.2–100.0] |
| `naive_full_history` desk-02 | 1 | 34/34 (100.0%) [89.8–100.0] | 16/16 (100.0%) [80.6–100.0] | 18/18 (100.0%) [82.4–100.0] |
| `prefix_cached_history` desk-01 | 1 | 35/35 (100.0%) [90.1–100.0] | 16/16 (100.0%) [80.6–100.0] | 19/19 (100.0%) [83.2–100.0] |
| `prefix_cached_history` desk-02 | 1 | 34/34 (100.0%) [89.8–100.0] | 16/16 (100.0%) [80.6–100.0] | 18/18 (100.0%) [82.4–100.0] |
| `prefix_cached_summarized` desk-01 | 1 | 35/35 (100.0%) [90.1–100.0] | 16/16 (100.0%) [80.6–100.0] | 19/19 (100.0%) [83.2–100.0] |
| `prefix_cached_summarized` desk-02 | 1 | 34/34 (100.0%) [89.8–100.0] | 16/16 (100.0%) [80.6–100.0] | 18/18 (100.0%) [82.4–100.0] |

Ledger recall (turn-10 reply scored against ledger facts):

| Group | Overall | Origin 1–3 | Origin 4–6 | Origin 7–9 | Source handbook | Source session |
|---|---|---|---|---|---|---|
| `naive_full_history` desk-01 | 22/25 (88.0%) [70.0–95.8] | 8/9 (88.9%) [56.5–98.0] | 7/8 (87.5%) [52.9–97.8] | 7/8 (87.5%) [52.9–97.8] | 17/17 (100.0%) [81.6–100.0] | 5/8 (62.5%) [30.6–86.3] |
| `naive_full_history` desk-02 | 10/24 (41.7%) [24.5–61.2] | 3/8 (37.5%) [13.7–69.4] | 4/9 (44.4%) [18.9–73.3] | 3/7 (42.9%) [15.8–75.0] | 9/18 (50.0%) [29.0–71.0] | 1/6 (16.7%) [3.0–56.4] |
| `prefix_cached_history` desk-01 | 20/25 (80.0%) [60.9–91.1] | 8/9 (88.9%) [56.5–98.0] | 5/8 (62.5%) [30.6–86.3] | 7/8 (87.5%) [52.9–97.8] | 17/17 (100.0%) [81.6–100.0] | 3/8 (37.5%) [13.7–69.4] |
| `prefix_cached_history` desk-02 | 15/24 (62.5%) [42.7–78.8] | 5/8 (62.5%) [30.6–86.3] | 6/9 (66.7%) [35.4–87.9] | 4/7 (57.1%) [25.0–84.2] | 13/18 (72.2%) [49.1–87.5] | 2/6 (33.3%) [9.7–70.0] |
| `prefix_cached_summarized` desk-01 | 19/25 (76.0%) [56.6–88.5] | 5/9 (55.6%) [26.7–81.1] | 7/8 (87.5%) [52.9–97.8] | 7/8 (87.5%) [52.9–97.8] | 15/17 (88.2%) [65.7–96.7] | 4/8 (50.0%) [21.5–78.5] |
| `prefix_cached_summarized` desk-02 | 11/24 (45.8%) [27.9–64.9] | 1/8 (12.5%) [2.2–47.1] | 6/9 (66.7%) [35.4–87.9] | 4/7 (57.1%) [25.0–84.2] | 10/18 (55.6%) [33.7–75.4] | 1/6 (16.7%) [3.0–56.4] |

The original capture has no probes (they were not asked at capture time).

## Fresh reruns — cost, tokens and context

| Rung | Runs | Session billed $/session | Session warm $/session | Session billed $/1k | Session warm $/1k | Probe-phase billed $/run | Probe-phase warm $/run |
|---|---|---|---|---|---|---|---|
| `naive_full_history` | 6 | $0.3987 ($0.3726–$0.4332) | $0.3987 ($0.3726–$0.4332) | $398.68 | $398.68 | $0.2741 ($0.2652–$0.2832) | $0.2741 ($0.2652–$0.2832) |
| `prefix_cached_history` | 6 | $0.2397 ($0.2051–$0.2843) | $0.2160 ($0.1814–$0.2607) | $239.66 | $216.00 | $0.1573 ($0.1497–$0.1631) | $0.1573 ($0.1497–$0.1631) |
| `prefix_cached_summarized` | 6 | $0.2125 ($0.1935–$0.2301) | $0.1888 ($0.1699–$0.2064) | $212.45 | $188.78 | $0.0763 ($0.0674–$0.0926) | $0.0763 ($0.0674–$0.0926) |

| Rung | Turn prompt tok/session | Turn output tok/session | Compaction prompt tok | Compaction output tok | Probe-phase prompt tok | Probe-phase output tok | Thinking tok (all calls) | Compactions (session) | Probe-phase compactions |
|---|---|---|---|---|---|---|---|---|---|
| `naive_full_history` | 163,020 (158,671–167,679) | 7,264 (5,523–10,420) | 0 (0–0) | 0 (0–0) | 136,531 (131,901–141,069) | 105 (75–136) | 1,659 (378–4,764) | 0 (0–0) | 0 (0–0) |
| `prefix_cached_history` | 161,206 (157,957–164,307) | 8,088 (5,274–12,679) | 0 (0–0) | 0 (0–0) | 134,188 (130,101–137,361) | 130 (75–189) | 2,882 (387–7,993) | 0 (0–0) | 0 (0–0) |
| `prefix_cached_summarized` | 132,255 (129,634–134,474) | 7,954 (6,718–9,337) | 10,883 (10,168–11,678) | 1,038 (865–1,106) | 78,379 (77,083–79,549) | 3,197 (2,306–4,907) | 3,898 (1,860–6,545) | 2 (2–2) | 1 (1–1) |

Context size (prompt tokens = uncached input + cache write + cache read) at selected turns:

| Rung | Turn 1 | Turn 3 | Turn 6 | Turn 10 |
|---|---|---|---|---|
| `naive_full_history` | 10,617 (10,614–10,622) | 13,169 (12,957–13,377) | 17,054 (16,470–17,668) | 21,872 (21,152–22,626) |
| `prefix_cached_history` | 10,626 (10,622–10,629) | 13,157 (12,988–13,289) | 16,803 (16,400–17,244) | 21,496 (20,901–21,982) |
| `prefix_cached_summarized` | 10,633 (10,629–10,636) | 13,200 (12,981–13,409) | 13,783 (13,409–14,242) | 14,824 (14,499–14,976) |

Per rung × session (session billed / warm $ per session, mean):

| Rung | Session | Runs | Errors | Session billed | Session warm | Probe-phase billed |
|---|---|---|---|---|---|---|
| `naive_full_history` | desk-01 | 3 | 0 | $0.4159 ($0.3907–$0.4332) | $0.4159 ($0.3907–$0.4332) | $0.2792 ($0.2767–$0.2832) |
| `naive_full_history` | desk-02 | 3 | 0 | $0.3815 ($0.3726–$0.3871) | $0.3815 ($0.3726–$0.3871) | $0.2690 ($0.2652–$0.2742) |
| `prefix_cached_history` | desk-01 | 3 | 0 | $0.2659 ($0.2496–$0.2843) | $0.2422 ($0.2259–$0.2607) | $0.1599 ($0.1539–$0.1631) |
| `prefix_cached_history` | desk-02 | 3 | 0 | $0.2134 ($0.2051–$0.2226) | $0.1898 ($0.1814–$0.1990) | $0.1547 ($0.1497–$0.1584) |
| `prefix_cached_summarized` | desk-01 | 3 | 0 | $0.2156 ($0.2038–$0.2301) | $0.1919 ($0.1801–$0.2064) | $0.0700 ($0.0674–$0.0713) |
| `prefix_cached_summarized` | desk-02 | 3 | 0 | $0.2093 ($0.1935–$0.2195) | $0.1857 ($0.1699–$0.1958) | $0.0826 ($0.0693–$0.0926) |

Billed = recorded tokens priced at the returned model's rates (`app/core/pricing.py`). Warm = `runner.compute_warm_turn_cost` per turn/probe call (cache writes priced as cache reads); summariser calls count at billed cost in both views, as in the runner. Session = turns 1–10 plus the compactions before turns; probe phase = the probe-phase compaction plus all probe calls.

## Per-fact hit rates

Rerun columns: hits/n over ok runs. Original columns: ✓/✗ per golden cell (– = not scored). `never` = observed but hit by no rung in any run or capture.

| Fact | Session | Kind | Turn | Source | rerun `naive_full_history` | rerun `prefix_cached_history` | rerun `prefix_cached_summarized` | orig `naive_full_history` | orig `prefix_cached_history` | orig `prefix_cached_summarized` | Flag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `d1-t1-no-wipe-cs-contained` | desk-01 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t1-falconctl-heartbeat` | desk-01 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t1-queue-it-iam-fastpass` | desk-01 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t1-sla-fastpass` | desk-01 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t2-profiles-renew` | desk-01 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t2-jamf-reenroll-posture` | desk-01 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t2-queue-it-mdm-leave-unlock` | desk-01 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t2-sla-30-min` | desk-01 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t3-root-ca-v4-fingerprint` | desk-01 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t3-split-tunnel-workday-sso` | desk-01 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t3-cert-refresh-sase-v4` | desk-01 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t3-disable-ipv6-bypass` | desk-01 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t4-hr-bon-412c` | desk-01 | turn | 4 | handbook | 3/3 | 2/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t4-bonus-factor-1-00` | desk-01 | turn | 4 | handbook | 3/3 | 2/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t4-secondary-leave-12-weeks` | desk-01 | turn | 4 | handbook | 3/3 | 2/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t4-queue-hr-pay-retro` | desk-01 | turn | 4 | handbook | 3/3 | 2/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t5-cutoff-18-00-ist` | desk-01 | turn | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t5-stale-unpaid-loa-hold` | desk-01 | turn | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t5-hr-bon-412c` | desk-01 | turn | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t5-total-owed-64200` | desk-01 | turn | 5 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t6-threshold-25000` | desk-01 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t6-48-business-hours` | desk-01 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t6-queue-hr-pay-retro` | desk-01 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t6-tds-following-month` | desk-01 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t7-annual-cap-35000` | desk-01 | turn | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t7-single-claim-30000` | desk-01 | turn | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t7-direct-manager-approval` | desk-01 | turn | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t8-wd-del-09` | desk-01 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t8-24h-auto-delegation` | desk-01 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t8-reimbursement-5-business-days` | desk-01 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t8-queue-hr-ben-escalations` | desk-01 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t9-wd-access-recert` | desk-01 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t9-queue-it-iam-groups` | desk-01 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t9-sla-60-min` | desk-01 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-t9-restore-via-wd-del-09` | desk-01 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t1-ykman-fido-info` | desk-02 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t1-dual-verification-manager-id` | desk-02 | turn | 1 | handbook | 1/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t1-queue-it-iam-fido2` | desk-02 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t1-it-genius-locker` | desk-02 | turn | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t2-auth-okta-fido2` | desk-02 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t2-request-ttl-4h` | desk-02 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t2-lease-cap-240` | desk-02 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t2-cosign-l7` | desk-02 | turn | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t3-mtls-90-days` | desk-02 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t3-install-ca-v4` | desk-02 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t3-queue-it-net-registry` | desk-02 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t3-sla-20-min` | desk-02 | turn | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t4-lift-ceiling-2500` | desk-02 | turn | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t4-lift-15-30-min` | desk-02 | turn | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t4-lift-14-days` | desk-02 | turn | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t4-gstin` | desk-02 | turn | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t5-gross-363372` | desk-02 | turn | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t5-tax-113372` | desk-02 | turn | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t5-clawback-9-months-90843` | desk-02 | turn | 5 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t6-cofund-70-pct` | desk-02 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t6-cutoff-dec-16` | desk-02 | turn | 6 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t6-masked-last-4` | desk-02 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t6-workday-kms-vault` | desk-02 | turn | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t7-remaining-5200` | desk-02 | turn | 7 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t7-single-claim-30000` | desk-02 | turn | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t7-annual-cap-35000` | desk-02 | turn | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t8-hr-pay-nh-18` | desk-02 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t8-on-or-before-15th` | desk-02 | turn | 8 | handbook | 3/3 | 3/3 | 2/3 | ✓ | ✓ | ✓ |  |
| `d2-t8-combined-dec-31` | desk-02 | turn | 8 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t8-hr-pay-adv-14` | desk-02 | turn | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t9-gate-2-blocks` | desk-02 | turn | 9 | handbook | 3/3 | 3/3 | 2/3 | ✓ | ✓ | ✓ |  |
| `d2-t9-tsh-request-create` | desk-02 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t9-request-ttl-4h` | desk-02 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-t9-cosigner-siddharth` | desk-02 | turn | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l1-queue-it-iam-fastpass` | desk-01 | ledger | 1 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l1-err-device-posture` | desk-01 | ledger | 1 | handbook | 3/3 | 2/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l1-days-offline-101` | desk-01 | ledger | 1 | session | 1/3 | 2/3 | 0/3 | ✗ | ✗ | ✗ |  |
| `d1-l2-queue-it-mdm-leave-unlock` | desk-01 | ledger | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l2-profiles-renew` | desk-01 | ledger | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l2-prk-slot` | desk-01 | ledger | 2 | session | 2/3 | 3/3 | 0/3 | ✓ | ✓ | ✗ |  |
| `d1-l3-root-ca-v4-fingerprint` | desk-01 | ledger | 3 | handbook | 3/3 | 3/3 | 0/3 | ✓ | ✓ | ✗ |  |
| `d1-l3-queue-it-net-sase` | desk-01 | ledger | 3 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l3-disable-ipv6-bypass` | desk-01 | ledger | 3 | handbook | 3/3 | 3/3 | 2/3 | ✓ | ✓ | ✗ |  |
| `d1-l4-deduction-42200` | desk-01 | ledger | 4 | session | 2/3 | 3/3 | 3/3 | ✓ | ✗ | ✓ |  |
| `d1-l4-bonus-22000` | desk-01 | ledger | 4 | session | 2/3 | 3/3 | 3/3 | ✓ | ✗ | ✓ |  |
| `d1-l4-hr-bon-412c` | desk-01 | ledger | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l5-sync-lag-404` | desk-01 | ledger | 5 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l5-approval-oct-20` | desk-01 | ledger | 5 | session | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d1-l6-queue-hr-pay-retro` | desk-01 | ledger | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l6-hr-pay-bridge-48h` | desk-01 | ledger | 6 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l6-usd-770` | desk-01 | ledger | 6 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l7-prior-claim-6500` | desk-01 | ledger | 7 | session | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l7-annual-cap-35000` | desk-01 | ledger | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l7-hr-ben-ergo-26` | desk-01 | ledger | 7 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l8-reimbursement-5-business-days` | desk-01 | ledger | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l8-24h-auto-delegation` | desk-01 | ledger | 8 | handbook | 2/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l8-manager-pto-7-business-days` | desk-01 | ledger | 8 | session | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d1-l9-queue-it-iam-groups` | desk-01 | ledger | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-l9-sla-60-min` | desk-01 | ledger | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-l1-queue-it-iam-fido2` | desk-02 | ledger | 1 | handbook | 2/3 | 3/3 | 1/3 | ✗ | ✓ | ✗ |  |
| `d2-l1-mfa-bypass-24h` | desk-02 | ledger | 1 | handbook | 3/3 | 2/3 | 0/3 | ✓ | ✓ | ✗ |  |
| `d2-l2-it-sec-pam-09` | desk-02 | ledger | 2 | handbook | 2/3 | 1/3 | 1/3 | ✗ | ✗ | ✗ |  |
| `d2-l2-change-ticket` | desk-02 | ledger | 2 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-l2-locker-b4` | desk-02 | ledger | 2 | session | 0/3 | 2/3 | 1/3 | ✓ | ✓ | ✗ |  |
| `d2-l3-it-net-mtls-14` | desk-02 | ledger | 3 | handbook | 2/3 | 1/3 | 1/3 | ✗ | ✗ | ✗ |  |
| `d2-l3-queue-it-net-registry` | desk-02 | ledger | 3 | handbook | 1/3 | 2/3 | 0/3 | ✗ | ✓ | ✗ |  |
| `d2-l3-install-ca-v4` | desk-02 | ledger | 3 | handbook | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d2-l4-lift-ceiling-2500` | desk-02 | ledger | 4 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-l4-hr-concur-risk` | desk-02 | ledger | 4 | handbook | 3/3 | 3/3 | 2/3 | ✗ | ✓ | ✗ |  |
| `d2-l4-preauth-usd-1775` | desk-02 | ledger | 4 | session | 1/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ |  |
| `d2-l5-tax-113372` | desk-02 | ledger | 5 | handbook | 3/3 | 3/3 | 1/3 | ✓ | ✓ | ✓ |  |
| `d2-l5-hr-rel-518c` | desk-02 | ledger | 5 | handbook | 3/3 | 1/3 | 3/3 | ✗ | ✗ | ✓ |  |
| `d2-l5-clawback-90843` | desk-02 | ledger | 5 | session | 3/3 | 3/3 | 2/3 | ✗ | ✓ | ✓ |  |
| `d2-l6-cofund-70-pct` | desk-02 | ledger | 6 | handbook | 3/3 | 3/3 | 2/3 | ✓ | ✓ | ✓ |  |
| `d2-l6-wd-ben-30d` | desk-02 | ledger | 6 | handbook | 0/3 | 2/3 | 1/3 | ✗ | ✗ | ✗ |  |
| `d2-l6-cover-500000` | desk-02 | ledger | 6 | handbook | 2/3 | 2/3 | 2/3 | ✓ | ✓ | ✓ |  |
| `d2-l7-chair-18900` | desk-02 | ledger | 7 | session | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d2-l7-dock-10900` | desk-02 | ledger | 7 | session | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d2-l7-annual-cap-35000` | desk-02 | ledger | 7 | handbook | 1/3 | 1/3 | 1/3 | ✗ | ✓ | ✓ |  |
| `d2-l8-hr-pay-adv-14` | desk-02 | ledger | 8 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d2-l8-packet-nov-17` | desk-02 | ledger | 8 | session | 0/3 | 0/3 | 0/3 | ✗ | ✗ | ✗ | never |
| `d2-l9-tsh-request-create` | desk-02 | ledger | 9 | handbook | 2/3 | 2/3 | 2/3 | ✓ | ✓ | ✓ |  |
| `d2-l9-queue-it-pam-prod` | desk-02 | ledger | 9 | handbook | 3/3 | 3/3 | 3/3 | ✓ | ✓ | ✓ |  |
| `d1-p1-device-serial` | desk-01 | probe | 1 | session | 3/3 | 3/3 | 2/3 | – | – | – |  |
| `d1-p2-prk-slot` | desk-01 | probe | 2 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d1-p3-manager-approval-date` | desk-01 | probe | 5 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d1-p4-bank-account-last4` | desk-01 | probe | 6 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d1-p5-monitor-invoice-number` | desk-01 | probe | 7 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d1-p6-restored-jira-group` | desk-01 | probe | 9 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p1-yubikey-serial` | desk-02 | probe | 1 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p2-proposed-cosigner` | desk-02 | probe | 2 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p3-old-cert-expiry` | desk-02 | probe | 3 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p4-declined-preauth-usd` | desk-02 | probe | 4 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p5-chair-price` | desk-02 | probe | 7 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |
| `d2-p6-packet-submitted-date` | desk-02 | probe | 8 | session | 3/3 | 3/3 | 0/3 | – | – | – |  |

### Facts hit by no rung in any run (6)

- `d1-l5-approval-oct-20` (ledger, turn 5, session): Manager approval landed Oct 20 (after the Oct 18 cutoff). — any_of ['oct 20', 'october 20', '20 oct', '20 october', '2026-10-20', '20-oct', 'oct 20th', '20th oct', 'oct. 20']
- `d1-l8-manager-pto-7-business-days` (ledger, turn 8, session): Manager PTO spans 7 consecutive business days (> 3 trigger). — any_of ['7 consecutive business days', '7 business days', '7 business day', '7-business-day', 'seven business days', '7 consecutive']
- `d2-l3-install-ca-v4` (ledger, turn 3, handbook): Registry fix action --install-ca-v4. — any_of ['install-ca-v4', 'registry login']
- `d2-l7-chair-18900` (ledger, turn 7, session): Ergonomic chair 18,900 INR. — any_of ['18900']
- `d2-l7-dock-10900` (ledger, turn 7, session): CalDigit TS4 dock 10,900 INR. — any_of ['10900']
- `d2-l8-packet-nov-17` (ledger, turn 8, session): Relocation/bank packet submitted Nov 17 (after-cutoff context). — any_of ['nov 17', 'november 17', '17 nov', '17 november', '2026-11-17', '17-nov', 'nov 17th', '17th nov', 'nov. 17']

### Largest spread between rungs (top 15)

| Fact | Kind | Turn | Source | Spread | Basis | Per-rung |
|---|---|---|---|---|---|---|
| `d1-l2-prk-slot` | ledger | 2 | session | 100 pp | rerun | naive_full_history 2/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-l3-root-ca-v4-fingerprint` | ledger | 3 | handbook | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-p2-prk-slot` | probe | 2 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-p3-manager-approval-date` | probe | 5 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-p4-bank-account-last4` | probe | 6 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-p5-monitor-invoice-number` | probe | 7 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d1-p6-restored-jira-group` | probe | 9 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-l1-mfa-bypass-24h` | ledger | 1 | handbook | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 2/3, prefix_cached_summarized 0/3 |
| `d2-p1-yubikey-serial` | probe | 1 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-p2-proposed-cosigner` | probe | 2 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-p3-old-cert-expiry` | probe | 3 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-p4-declined-preauth-usd` | probe | 4 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-p5-chair-price` | probe | 7 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-p6-packet-submitted-date` | probe | 8 | session | 100 pp | rerun | naive_full_history 3/3, prefix_cached_history 3/3, prefix_cached_summarized 0/3 |
| `d2-l1-queue-it-iam-fido2` | ledger | 1 | handbook | 67 pp | rerun | naive_full_history 2/3, prefix_cached_history 3/3, prefix_cached_summarized 1/3 |

## Data quality

- Rerun error records: 0 (billed $0.0000).
- Rerun calls not ending in `end_turn`: 0.
- Rerun calls whose returned model is not `claude-sonnet-5-5`: 0.
- Original capture: turns not ending in `end_turn`: 0; model mismatches: 0.

## Misses for review — probe answers that missed (34)

### `prefix_cached_summarized` · desk-01 · r0 · `d1-p2-prk-slot` (origin turn 2)

Expected any of: ['prk-blr-8841-992']

```text
I don't have a SlotID for your escrowed FileVault recovery key, so I can't give you a value. Nothing in this session or the handbook records one. The only escrow reference I have is that the Personal Recovery Key is held in NovaMart Vault under Asset Tag `NM-MAC-BLR-8841`, and it stayed intact through re-enrollment.

To get the SlotID, ask `IT-MDM-LEAVE-UNLOCK` to look it up in Vault by that asset tag. Don't paste the recovery key itself into chat.
```

### `prefix_cached_summarized` · desk-01 · r0 · `d1-p3-manager-approval-date` (origin turn 5)

Expected any of: ['oct 20', 'october 20', '20 oct', '20 october', '2026-10-20', '20-oct', 'oct 20th', '20th oct', 'october 20th', '20th october', 'oct. 20']

```text
I can't give you that date. The session record doesn't capture when your manager approved the Return-From-Leave, so I'd only be guessing.

You can find it in Workday under case `WD-LV-2026-9912`, in the Absence approval history for the `WD-LV-*` Return-From-Leave task. If it's missing there, ask `HR-PAY-RETRO` to confirm the timestamp, since it also matters for the `LEAVE_RETURN_SYNC_LAG_404` reconciliation.
```

### `prefix_cached_summarized` · desk-01 · r0 · `d1-p4-bank-account-last4` (origin turn 6)

Expected any of: ['4419']

```text
I don't have that value. The bank account's last four digits were never recorded in this session, and I won't guess. You can confirm it under Workday Payment Elections, or ask the `HR-PAY-RETRO` team to confirm the masked account (last four digits only) on the `HR-PAY-BRIDGE-48H` wire before it releases.
```

### `prefix_cached_summarized` · desk-01 · r0 · `d1-p5-monitor-invoice-number` (origin turn 7)

Expected any of: ['dl-blr-2026-774102', '774102']

```text
I don't have the invoice number. It isn't in the session record I'm working from. The only identifier I have for that purchase is the Concur claim ID `CON-ERGO-99410`, which is not the invoice number. You can find the invoice number printed on the receipt itself or in the attachment on that Concur claim.
```

### `prefix_cached_summarized` · desk-01 · r0 · `d1-p6-restored-jira-group` (origin turn 9)

Expected any of: ['jira-planning-ro']

```text
I can't give you a group name. Neither the handbook nor my session memory records which Jira group was restored. The handbook only says `WD-REPROVISION-SLK` restores "birthright groups" within 15 minutes of your Workday status returning to `ACTIVE`, and I won't guess a name.

To confirm, check your Okta profile under Groups, or ask `IT-IAM-GROUPS` (P2, 60 min) for your group list.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p1-device-serial` (origin turn 1)

Expected any of: ['c02zn418lvdq']

```text
I don't have a hardware serial number. The Okta telemetry from this morning isn't in my compacted session memory, and the only device identifier I have is the asset tag `NM-MAC-BLR-8841`, which is not a serial number. I won't guess one.

To get it yourself, run `system_profiler SPHardwareDataType | grep "Serial Number"` in Terminal. It's also under Apple menu > About This Mac. Because the serial is a hardware identifier, not a secret, it's safe to paste into a ticket.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p2-prk-slot` (origin turn 2)

Expected any of: ['prk-blr-8841-992']

```text
I don't have a SlotID. It wasn't in the handbook or in our session memory, so I won't guess a value. The only identifier I have for your escrowed key is the asset tag `NM-MAC-BLR-8841`, which is how the PRK is filed in NovaMart Vault.

If you need the SlotID, raise it with `IT-MDM-LEAVE-UNLOCK` (P2, 30 min) and ask them to look it up by that asset tag. Don't paste the recovery key itself into chat.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p3-manager-approval-date` (origin turn 5)

Expected any of: ['oct 20', 'october 20', '20 oct', '20 october', '2026-10-20', '20-oct', 'oct 20th', '20th oct', 'october 20th', '20th october', 'oct. 20']

```text
I don't have that date. My session records show leave case `WD-LV-2026-9912` and the `LEAVE_RETURN_SYNC_LAG_404` cause, but not when Kavita approved the Return-From-Leave, so I won't guess. You can find it in the approval history of `WD-LV-2026-9912` in Workday, and the `HR-PAY-RETRO` ticket may also list it.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p4-bank-account-last4` (origin turn 6)

Expected any of: ['4419']

```text
I don't have a bank account number, or its last four digits, in this session. The compacted memory and the ticket bundle only record the ₹64,200 wire amount, not the destination account. You can check the account on file in your Workday payment elections, or ask `HR-PAY-RETRO` to confirm it before the wire is released. Please don't paste the full account number here.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p5-monitor-invoice-number` (origin turn 7)

Expected any of: ['dl-blr-2026-774102', '774102']

```text
I don't have that value. The session memory doesn't include the invoice number from your Dell monitor receipt, and I won't guess. Check the receipt itself or the attachment on Concur claim `CON-ERGO-99410`.
```

### `prefix_cached_summarized` · desk-01 · r1 · `d1-p6-restored-jira-group` (origin turn 9)

Expected any of: ['jira-planning-ro']

```text
I can't give you that name. My session memory records only that `WD-REPROVISION-SLK` restored your Slack and Jira birthright groups within `OKTA-GROUP-SYNC-15M`. It doesn't list the individual Jira group names, and I won't guess one.

You can find the exact name in either of these places:
- **Jira:** Profile -> Groups, which lists every group you're currently in.
- **Okta:** your user's Groups tab, filtered to Jira-related entries.

If something is still missing, raise it under `IT-IAM-GROUPS` (P2, 60 min). Remember that `k8s-*`, `fin-sap-write`, `seller-escrow-admin` and private `#war-room-*`
```

### `prefix_cached_summarized` · desk-01 · r2 · `d1-p2-prk-slot` (origin turn 2)

Expected any of: ['prk-blr-8841-992']

```text
I don't have a SlotID for your recovery key. Neither the handbook nor our session records contain one. The only escrow reference on file is that the key is held in NovaMart Vault under Asset Tag `NM-MAC-BLR-8841` (serial `C02ZN418LVDQ`), and I won't guess a value.

For the actual SlotID, raise it with `IT-MDM-LEAVE-UNLOCK` against that asset tag. Never paste the recovery key itself into chat.
```

### `prefix_cached_summarized` · desk-01 · r2 · `d1-p3-manager-approval-date` (origin turn 5)

Expected any of: ['oct 20', 'october 20', '20 oct', '20 october', '2026-10-20', '20-oct', 'oct 20th', '20th oct', 'october 20th', '20th october', 'oct. 20']

```text
I can't give you that date. The approval date isn't in my session record: the compacted memory from Turns 1-9 doesn't include it, and the session header only lists case `WD-LV-2026-9912` and Kavita's PTO window (Oct 28 - Nov 6).

You can find it in Workday under case `WD-LV-2026-9912` -> Process History, on the manager "Approve" step. It's worth adding to your `HR-PAY-RETRO` ticket, since an approval after the 18th 18:00 IST cutoff is what triggers `LEAVE_RETURN_SYNC_LAG_404`.
```

### `prefix_cached_summarized` · desk-01 · r2 · `d1-p4-bank-account-last4` (origin turn 6)

Expected any of: ['4419']

```text
I don't have that value. The bank account on file for the bridge wire isn't in anything I can see (session header, compacted memory, or handbook), and I won't guess at a number.

To confirm it, check Workday > Pay > Payment Elections for your masked account (last four digits only), or ask in your `HR-PAY-RETRO` ticket, where Payroll can verify it against the SAP payee record.
```

### `prefix_cached_summarized` · desk-01 · r2 · `d1-p5-monitor-invoice-number` (origin turn 7)

Expected any of: ['dl-blr-2026-774102', '774102']

```text
I don't have the invoice number. The session memory has the Concur claim ID (`CON-ERGO-99410`) and the ₹28,500 amount, but not the invoice number from the receipt. Please check the receipt PDF or your Concur claim attachment. Note that for amounts above ₹10,000 the invoice must also show your name and corporate GSTIN.
```

### `prefix_cached_summarized` · desk-01 · r2 · `d1-p6-restored-jira-group` (origin turn 9)

Expected any of: ['jira-planning-ro']

```text
I don't have a Jira group name for you. Neither the handbook nor our session memory names one. The handbook says only that the `WD-REPROVISION-SLK` SCIM connector restores birthright groups within 15 minutes of the Workday `ACTIVE` status (`OKTA-GROUP-SYNC-15M`). To see which Jira groups came back, check your Okta group memberships or your Jira profile. If one is missing, raise it with `IT-IAM-GROUPS` (P2, 60 min).
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p1-yubikey-serial` (origin turn 1)

Expected any of: ['28491044']

```text
I don't have it. The session memory only records that the keys are bound, not their serial numbers, and I won't guess one.

Plug in the primary key and run `ykman info`. The serial is on the "Serial number" line. It's also printed on the key itself.
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p2-proposed-cosigner` (origin turn 2)

Expected any of: ['rohan kulkarni', 'rohan', 'kulkarni', 'emp-in-48210']

```text
I don't have that name. My session memory from Turns 1-9 doesn't record the peer co-signer you proposed. It only says Gate 2 needs an L7 approval from Siddharth Nair (EMP-IN-11088). The name should be in the rejected request itself, which you can check with `tsh request ls` or in the original `CHG-2026-8841` ticket.
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p3-old-cert-expiry` (origin turn 3)

Expected any of: ['nov 12', 'november 12', '12 nov', '12 november', '2026-11-12', '12-nov', 'nov 12th', '12th nov', 'november 12th', '12th november', 'nov. 12']

```text
I don't have that date. My session memory only records that the mTLS expiry was fixed with `nm-cli registry login --mtls --install-ca-v4`, not when the old cert expired.

- The reissue likely overwrote the old cert, so `openssl x509 -in ~/.docker/certs.d/artifacts.novamart.internal/client.cert -noout -enddate` would now show the new 90-day cert's expiry, not the old one.
- The original `CORP_DOCKER_PROXY_MTLS_EXPIRED` ticket or error output in `IT-NET-REGISTRY` should show the old expiry date.
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p4-declined-preauth-usd` (origin turn 4)

Expected any of: ['1775']

```text
I don't have the declined pre-authorization amount in my session memory, so I can't confirm it. The only related figure is the ₹1,48,000 you cited in your last message. If that was the pre-auth, it's roughly **$1,780 USD** at the handbook's implied rate of about ₹83.2/USD. Please check the Amex decline notice or the Concur alert to confirm the exact amount.
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p5-chair-price` (origin turn 7)

Expected any of: ['18900']

```text
I don't have the chair's price. My session memory only holds the total claim of ₹29,800 (with ₹5,200 remaining of the ₹35,000 cap) and doesn't have the line items. You can see the chair amount in your Concur claim `ERGO-WFH-FY26`, or from your receipt.
```

### `prefix_cached_summarized` · desk-02 · r0 · `d2-p6-packet-submitted-date` (origin turn 8)

Expected any of: ['nov 17', 'november 17', '17 nov', '17 november', '2026-11-17', '17-nov', 'nov 17th', '17th nov', 'november 17th', '17th november', 'nov. 17']

```text
I can't give you that date. It isn't in my compacted session memory or the Turn 10 ledger snapshot. The only related fact I have is that your Nov 16-30 pay (15 days) combines with December salary under `HR-PAY-NH-18`.

To find it, check the submission timestamp on your Workday onboarding task. If you want it verified against payroll cutoff timing, `HR-PAY-RETRO` can confirm it.
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p1-yubikey-serial` (origin turn 1)

Expected any of: ['28491044']

```text
I don't have that value. No serial appears in the session memory or the handbook, and the "#B4" next to the primary key in my last table was not sourced. Please disregard it and don't send it to Siddharth.

To read the real serial, plug in the key and run:

`ykman list --serials`

or `ykman info`, which shows the serial and firmware version.

If you use the 24h `MFA-BYPASS-24H` or `IT-IAM-FIDO2` replacement flow, quote the serial from that output.
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p2-proposed-cosigner` (origin turn 2)

Expected any of: ['rohan kulkarni', 'rohan', 'kulkarni', 'emp-in-48210']

```text
I don't have that name. My compacted memory of Turns 1-9 doesn't record who you originally proposed as co-signer, only that the request is now waiting on Siddharth Nair (`EMP-IN-11088`, L7) for `CHG-2026-8841`.

If you need the original name, `tsh request ls` or the `IT-PAM-PROD` ticket history should show it. Under `IT-SEC-PAM-09`, a co-signer below L7 would have caused the `PAM_JIT_ROLE_DENIED_403` rejection.
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p3-old-cert-expiry` (origin turn 3)

Expected any of: ['nov 12', 'november 12', '12 nov', '12 november', '2026-11-12', '12-nov', 'nov 12th', '12th nov', 'november 12th', '12th november', 'nov. 12']

```text
I can't give you that date. The compacted session record only says the mTLS cert was renewed via `nm-cli`, and the handbook gives no expiry date for your old cert. I won't guess one.

The old cert may have been overwritten by the renewal. If a backup or the original error output survives, `openssl x509 -in <old_cert_path> -noout -enddate` will show it, and the original `CORP_DOCKER_PROXY_MTLS_EXPIRED` error in your terminal history may also show it.

Two details in my last ledger also weren't in the session record, so please don't pass them to Siddharth as confirmed:
- **"#B4"** next to the pr
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p4-declined-preauth-usd` (origin turn 4)

Expected any of: ['1775']

```text
I don't have the declined pre-authorization amount. My compacted session memory records only that the lodging hold was lifted under `HR-TRV-LIFT-2500`, not the figure that was declined.

If the ₹1,48,000 you mentioned was the pre-auth, it works out to about **$1,779**, using the handbook's implied rate (₹2,08,000 = $2,500, so ₹83.2/USD). That is an inference, not a confirmed number. If it was the pre-auth, my last table was wrong to label it a mistake. I treated ₹1,48,000 as the lift amount, when the lift ceiling is $2,500 / ₹2,08,000.

The Amex decline notification or the hotel folio will sho
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p5-chair-price` (origin turn 7)

Expected any of: ['18900']

```text
I can't give the chair's price. My session memory only has the total of the single Concur claim (`ERGO-WFH-FY26`), which is **₹29,800**, and no per-item breakdown. The line items are in the claim itself in Concur.
```

### `prefix_cached_summarized` · desk-02 · r1 · `d2-p6-packet-submitted-date` (origin turn 8)

Expected any of: ['nov 17', 'november 17', '17 nov', '17 november', '2026-11-17', '17-nov', 'nov 17th', '17th nov', 'november 17th', '17th november', 'nov. 17']

```text
I don't have that date. My session memory records your Nov 16 joining date but not when you submitted the tax declaration or bank packet, and I won't guess. Check the submission timestamp in Workday, or ask `HR-PAY-RETRO`.

Two corrections to my last ledger:
- **YubiKey "#B4":** that detail isn't in my records, so please disregard it. Only the dual-key binding (`OKTA_FIDO2=2`) is recorded.
- **Amex line:** I labeled your ₹1,48,000 figure a "correction," which was unfounded. ₹2,08,000 is the maximum ceiling under `HR-TRV-LIFT-2500`, not necessarily the amount lifted. Confirm the exact figure wi
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p1-yubikey-serial` (origin turn 1)

Expected any of: ['28491044']

```text
I don't have that value. The serial number was never recorded in the session memory or your header, and I won't guess one.

You can read it from the key itself:
- `ykman list --serials` prints the serial of each connected key.
- `ykman info` shows the serial, firmware and AAGUID for the key that is plugged in.

I also need to correct my last ledger. The memory only confirmed the Docker mTLS fix, the dual FIDO2 enrollment and the ergo claim being OK. These were my inference, not recorded facts:
- Gate 4 being GREEN (Workday/PagerDuty/Slack).
- The Docker pull test passing and "90 days left".
- 
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p2-proposed-cosigner` (origin turn 2)

Expected any of: ['rohan kulkarni', 'rohan', 'kulkarni', 'emp-in-48210']

```text
I don't have that name. My compacted memory of Turns 1-9 records that the PAM request was rejected with `PAM_JIT_ROLE_DENIED_403`, but it doesn't keep who you proposed as co-signer. Policy `IT-SEC-PAM-09` requires an L7+ co-signer (Principal/Staff SRE or Incident Commander), so a peer at L6 or below would have been rejected. Check the rejected request in your `tsh request ls` history or the PAM audit trail, or ask `IT-PAM-PROD`.

Before you send the status to Siddharth, two details in my ledger weren't in my session memory: "approved by Siddharth" for the ergo claim (memory only says "single c
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p3-old-cert-expiry` (origin turn 3)

Expected any of: ['nov 12', 'november 12', '12 nov', '12 november', '2026-11-12', '12-nov', 'nov 12th', '12th nov', 'november 12th', '12th november', 'nov. 12']

```text
I don't have that date. My retained session memory only records that the mTLS issue was fixed with `nm-cli registry login --mtls --install-ca-v4`. It doesn't include the old certificate's expiry date, and I won't guess.

Since the re-issue replaced `client.cert`, the old dates are probably no longer on disk. To recover them:
- Check your earlier terminal scrollback or the original `docker pull` error output, which may include the `notAfter` date.
- Ask `IT-NET-REGISTRY` for the prior certificate's issuance record. It's a P2 queue with a 20 min SLA.
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p4-declined-preauth-usd` (origin turn 4)

Expected any of: ['1775']

```text
About **$1,780 USD**, based on ₹1,48,000 at the handbook's implied rate of about ₹83.2/USD.

My session memory doesn't store the declined pre-auth amount itself. ₹1,48,000 is the only hotel figure you've given, so I'm assuming that's it. If so, I mislabeled it in my last table as the lift amount. The lift ceiling is $2,500 (₹2,08,000), and ₹1,48,000 sits under it. Please check the figure against your Amex decline notice.
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p5-chair-price` (origin turn 7)

Expected any of: ['18900']

```text
I can't give you the chair price: my session memory only holds the claim total of ₹29,800 (single claim `ERGO-WFH-FY26`), not a per-item breakdown. If the chair was the only item, that total is its price, but I can't confirm that from what I have. Check the line items in your Concur claim.
```

### `prefix_cached_summarized` · desk-02 · r2 · `d2-p6-packet-submitted-date` (origin turn 8)

Expected any of: ['nov 17', 'november 17', '17 nov', '17 november', '2026-11-17', '17-nov', 'nov 17th', '17th nov', 'november 17th', '17th november', 'nov. 17']

```text
I don't have that date. My session memory from Turns 1-9 doesn't record when you submitted your tax declaration and bank packet. I won't guess, because the date matters for `HR-PAY-NH-18`: the packet has to finalize before the 18th 18:00 IST payroll cutoff. Your Workday submission receipt or `HR-PAY-RETRO` can confirm it.

I also need to correct the ledger I just gave you, since you're about to send it to Siddharth. Some details went beyond what my memory supports:
- **Gate 4** (Workday `ACTIVE`, PagerDuty webhook, `#inc-sre-triage`) is not confirmed in my memory. Please verify it.
- **Ergo cl
```

## Scoring rules

Both the reply and every `any_of` alternative are normalised the same way before matching:

1. Lowercase.
2. Delete markdown emphasis markers and code backticks (`*`, `**`, `~~`, backticks); underscores are kept.
3. Map Unicode dashes/minus signs (‐ ‑ ‒ – — ― −) to '-', curly quotes to straight quotes.
4. Collapse all whitespace runs (incl. non-breaking spaces) to one space and trim.
5. Remove a comma between digits when exactly 2 or 3 digits follow it (64,200 -> 64200; 2,50,000 -> 250000).
6. Remove currency markers adjacent to a number: ₹, $, inr, usd, rs, rs. before it; inr, usd after it.

Matching: an alternative is hit when it occurs in the normalised reply, with a boundary guard — an alternative starting with a letter/digit must not be preceded by a letter/digit, and one ending in a digit must not be followed by a digit.

Turn facts are scored against the reply of their own turn; ledger facts against the turn-10 reply; probes against each probe's answer. Items whose reply was not recorded are omitted, not counted as misses. Rerun statistics use the latest ok record per (rung, session, repeat).
