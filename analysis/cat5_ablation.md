# Category 5: 4-step budget + deterministic policy tool, without and with

Generated 2026-11-26T08:14:54.625636+00:00. Fixture version `cat5-ablation-fixtures-2026-11-26.v1`. Runs used: 144 of 144 (4 versions x 12 invoices x 3 runs).

Settings: max_tokens 4096 on every turn; with-versions step budget 4 (hard cap 5 model turns, as the app); without-version safety cap 12 model turns; call timeout 180s.

## Versions

| version | tools | cached | model | escalation | policy tool | prompt | turn cap |
|---|---|---|---|---|---|---|---|
| raw_free_sonnet | raw | False | claude-sonnet-5-5 | False | False | neutral | 12 |
| raw_free_haiku | raw | False | claude-haiku-5-5 | False | False | neutral | 12 |
| bundle_gate_sonnet_cached | governed | True | claude-sonnet-5-5 | False | True | bounded_sonnet_cached_gate | 5 |
| bundle_gate_haiku_escalate | governed | True | claude-haiku-5-5 | True | True | hybrid_haiku_sonnet_governed | 5 |

## Without and with (all invoices)

| version | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 36 | 36/36 100.0% [90.4–100.0%] | 36/36 100.0% [90.4–100.0%] | 100.0% | 100.0% | 100.0% | 17.1% | 3.9 (3–4) | 0 | 0 | 6 / 0 | 68,266 | 0 | 0 | 1,688 | $153.41 | $153.41 | $153.41 |
| raw_free_haiku | 36 | 36/36 100.0% [90.4–100.0%] | 36/36 100.0% [90.4–100.0%] | 100.0% | 100.0% | 100.0% | 17.1% | 3.9 (3–4) | 0 | 0 | 6 / 0 | 68,862 | 0 | 0 | 2,003 | $7.89 | $7.89 | $7.89 |
| bundle_gate_sonnet_cached | 36 | 36/36 100.0% [90.4–100.0%] | 36/36 100.0% [90.4–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 6 / 0 | 7,137 | 8,637 | 25,911 | 1,276 | $51.22 | $51.22 | $30.49 |
| bundle_gate_haiku_escalate | 36 | 36/36 100.0% [90.4–100.0%] | 36/36 100.0% [90.4–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 6 / 6 | 7,307 | 10,142 | 24,630 | 1,352 | $10.42 | $10.42 | $5.94 |

Field match rate per version:

| version | decision | authorized_net_principal_inr | authorized_gst_payout_inr | gst_escrow_holdback_inr | debit_note_deduction_inr |
|---|---|---|---|---|---|
| raw_free_sonnet | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| raw_free_haiku | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bundle_gate_sonnet_cached | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bundle_gate_haiku_escalate | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## By tier

### routine

| version | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 16.5% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 71,585 | 0 | 0 | 1,638 | $159.55 | $159.55 | $159.55 |
| raw_free_haiku | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 70,799 | 0 | 0 | 1,907 | $8.03 | $8.03 | $8.03 |
| bundle_gate_sonnet_cached | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,038 | 8,637 | 25,910 | 1,208 | $50.33 | $50.33 | $29.61 |
| bundle_gate_haiku_escalate | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,242 | 8,693 | 26,079 | 1,306 | $2.72 | $2.72 | $1.73 |

### dispute

| version | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 6 / 0 | 71,582 | 0 | 0 | 1,789 | $161.06 | $161.06 | $161.06 |
| raw_free_haiku | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 6 / 0 | 71,219 | 0 | 0 | 2,235 | $8.24 | $8.24 | $8.24 |
| bundle_gate_sonnet_cached | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 6 / 0 | 7,470 | 8,638 | 25,913 | 1,347 | $52.60 | $52.60 | $31.87 |
| bundle_gate_haiku_escalate | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 6 / 6 | 7,600 | 12,170 | 22,603 | 1,375 | $21.19 | $21.19 | $11.85 |

### hard_stop

| version | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 19.4% | 3.2 (3–4) | 0 | 0 | 0 / 0 | 51,677 | 0 | 0 | 1,561 | $118.97 | $118.97 | $118.97 |
| raw_free_haiku | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 19.2% | 3.5 (3–4) | 0 | 0 | 0 / 0 | 58,125 | 0 | 0 | 1,660 | $6.64 | $6.64 | $6.64 |
| bundle_gate_sonnet_cached | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,550 | 8,637 | 25,911 | 1,271 | $50.00 | $50.00 | $29.27 |
| bundle_gate_haiku_escalate | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,736 | 8,693 | 26,080 | 1,410 | $2.73 | $2.73 | $1.73 |

## By invoice

### raw_free_sonnet

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 74,615 | 0 | 0 | 1,482 | $164.05 | $164.05 | $164.05 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 75,346 | 0 | 0 | 1,972 | $170.41 | $170.41 | $170.41 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 20.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 44,516 | 0 | 0 | 1,569 | $104.72 | $104.72 | $104.72 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 75,800 | 0 | 0 | 1,599 | $167.59 | $167.59 | $167.59 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 65,524 | 0 | 0 | 1,615 | $147.20 | $147.20 | $147.20 |
| inv-06 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 66,400 | 0 | 0 | 1,721 | $150.01 | $150.01 | $150.01 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 75,105 | 0 | 0 | 1,792 | $168.13 | $168.13 | $168.13 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 15.9% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 66,574 | 0 | 0 | 1,780 | $150.95 | $150.95 | $150.95 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 65,458 | 0 | 0 | 1,591 | $146.83 | $146.83 | $146.83 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 74,537 | 0 | 0 | 1,605 | $165.13 | $165.13 | $165.13 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 18.9% | 3.3 (3–4) | 0 | 0 | 0 / 0 | 58,839 | 0 | 0 | 1,554 | $133.21 | $133.21 | $133.21 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 76,475 | 0 | 0 | 1,978 | $172.73 | $172.73 | $172.73 |

### raw_free_haiku

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 73,906 | 0 | 0 | 1,939 | $8.36 | $8.36 | $8.36 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 74,316 | 0 | 0 | 2,354 | $8.61 | $8.61 | $8.61 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 19.5% | 3.7 (3–4) | 0 | 0 | 0 / 0 | 57,237 | 0 | 0 | 1,637 | $6.54 | $6.54 | $6.54 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 74,786 | 0 | 0 | 1,754 | $8.36 | $8.36 | $8.36 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 65,881 | 0 | 0 | 1,953 | $7.56 | $7.56 | $7.56 |
| inv-06 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 66,361 | 0 | 0 | 2,072 | $7.67 | $7.67 | $7.67 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 75,241 | 0 | 0 | 2,196 | $8.62 | $8.62 | $8.62 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 65,304 | 0 | 0 | 1,927 | $7.49 | $7.49 | $7.49 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 65,208 | 0 | 0 | 2,104 | $7.57 | $7.57 | $7.57 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 73,637 | 0 | 0 | 1,845 | $8.29 | $8.29 | $8.29 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 18.9% | 3.3 (3–4) | 0 | 0 | 0 / 0 | 59,013 | 0 | 0 | 1,683 | $6.74 | $6.74 | $6.74 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 75,450 | 0 | 0 | 2,566 | $8.83 | $8.83 | $8.83 |

### bundle_gate_sonnet_cached

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,279 | 8,637 | 25,912 | 1,140 | $50.15 | $50.15 | $29.42 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 8,179 | 8,636 | 25,908 | 1,393 | $54.47 | $54.47 | $33.74 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,198 | 8,637 | 25,910 | 1,276 | $49.33 | $49.33 | $28.61 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,311 | 8,638 | 25,914 | 1,119 | $50.00 | $50.00 | $29.27 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,368 | 8,635 | 25,905 | 1,267 | $49.58 | $49.58 | $28.86 |
| inv-06 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,496 | 8,635 | 25,905 | 1,443 | $51.60 | $51.60 | $30.88 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,556 | 8,640 | 25,919 | 1,394 | $53.24 | $53.24 | $32.51 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,849 | 8,635 | 25,905 | 1,171 | $49.59 | $49.59 | $28.86 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,290 | 8,637 | 25,912 | 1,266 | $49.42 | $49.42 | $28.69 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,253 | 8,637 | 25,912 | 1,165 | $50.34 | $50.34 | $29.61 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,901 | 8,637 | 25,912 | 1,267 | $50.66 | $50.66 | $29.93 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 8,960 | 8,640 | 25,919 | 1,417 | $56.28 | $56.28 | $35.54 |

### bundle_gate_haiku_escalate

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,490 | 8,695 | 26,086 | 1,273 | $2.73 | $2.73 | $1.73 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 8,194 | 17,384 | 17,384 | 1,308 | $47.76 | $47.76 | $25.90 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,429 | 8,693 | 26,078 | 1,476 | $2.73 | $2.73 | $1.73 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,548 | 8,695 | 26,085 | 1,246 | $2.73 | $2.73 | $1.73 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,570 | 8,694 | 26,083 | 1,375 | $2.69 | $2.69 | $1.69 |
| inv-06 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,593 | 8,690 | 26,070 | 1,386 | $2.70 | $2.70 | $1.70 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,640 | 8,693 | 26,080 | 1,359 | $2.79 | $2.79 | $1.79 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,108 | 8,692 | 26,077 | 1,372 | $2.74 | $2.74 | $1.74 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,513 | 8,694 | 26,082 | 1,410 | $2.70 | $2.70 | $1.70 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,471 | 8,692 | 26,076 | 1,254 | $2.72 | $2.72 | $1.72 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,043 | 8,694 | 26,081 | 1,345 | $2.72 | $2.72 | $1.72 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 9,082 | 17,384 | 17,384 | 1,423 | $50.01 | $50.01 | $28.15 |

## Invoices: hand derivation vs the deterministic policy tool

| invoice | scenario | tier | hub | expected decision (manual) | escalation (manual 6.2) | grand total INR | policy tool agrees |
|---|---|---|---|---|---|---|---|
| inv-01 | Statutory GST escrow, MSE vendor, clean receipt (original) | routine | FC-BLR-01 | APPROVE_WITH_GST_ESCROW | False | 2,171,200.00 | True |
| inv-02 | Multi-factor dispute: DOA + amendment + unauthorised hike + freight (original) | dispute | FC-BOM-02 | APPROVE_PARTIAL_DEBIT_NOTE | True | 3,899,900.00 | True |
| inv-03 | Hard stop: cancelled IRN + phantom line (original) | hard_stop | FC-DEL-03 | BLOCK_EXCEPTION_HOLD | False | 3,127,000.00 | True |
| inv-04 | Clean full match | routine | FC-HYD-01 | APPROVE_CLEAN | False | 2,542,900.00 | True |
| inv-05 | DOA rejects only | dispute | FC-BLR-01 | APPROVE_PARTIAL_DEBIT_NOTE | False | 2,950,000.00 | True |
| inv-06 | Price variance inside the 1.5% band (standard DDP INR PO, no amendment) | routine | FC-DEL-03 | APPROVE_PARTIAL_DEBIT_NOTE | False | 4,340,984.00 | True |
| inv-07 | Price variance outside tolerance, no amendment | dispute | FC-BOM-02 | APPROVE_PARTIAL_DEBIT_NOTE | False | 3,096,320.00 | True |
| inv-08 | Authorised amendment only | routine | FC-HYD-01 | APPROVE_CLEAN | False | 3,919,370.00 | True |
| inv-09 | Freight above the PO cap | dispute | FC-DEL-03 | APPROVE_PARTIAL_DEBIT_NOTE | False | 5,318,850.00 | True |
| inv-10 | Statutory GST escrow on a non-MSE large-enterprise vendor (5% GST) | routine | FC-BOM-02 | APPROVE_WITH_GST_ESCROW | False | 3,273,900.00 | True |
| inv-11 | Hard stop: phantom unreceived line (>10%) with an active IRN and matched GSTR-2B | hard_stop | FC-BLR-01 | BLOCK_EXCEPTION_HOLD | False | 3,182,460.00 | True |
| inv-12 | Multi-factor dispute: short receipt + unauthorised hike (draft amendment only) + DOA on an amended line + freight over cap, with GSTR-2B pending | dispute | FC-HYD-01 | APPROVE_PARTIAL_DEBIT_NOTE | True | 5,981,420.00 | True |

## Vouchers that did not match

None.

## Data quality (runs used)

truncated turns 0, model mismatches 0, cache anomalies 0, cap hits 0, no voucher committed 0, disallowed tool calls 0, tool use blocks with other stop reason 1.

## Method notes

- Without: the free-choice loop over the five raw SELECT * tools (no step budget beyond a 12-turn safety cap, no policy tool, no prompt cache), on Sonnet and on Haiku; the Haiku version has no escalation path, since only the policy tool can flag one. With: a 4-step budget and the deterministic policy tool (run_policy_tolerance_gate; the commit is refused until it has run), and the with-design also uses one narrow query (fetch_3way_match_bundle) in place of the raw tables and sends the policy manual as a cached prefix, so the difference is not the budget and the tool alone.
- The policy manual (SOP-AP-3WAY-2026.v4) is the system text of every version. Both without-versions run the free-choice protocol; the with-versions run the app's rung-2 and rung-3 prompts unchanged.
- Escalation (Haiku-first version): the run switches to Sonnet from the next turn when the policy tool sets escalation_required, which it does only for a multi-factor commercial dispute (two or more of: partial DOA or short receipt, signed contract amendment, unauthorized line price rise, disallowed freight; manual 6.2). Expected escalations: inv-02 and inv-12.
- Thinking differs by model in the app's call function: Sonnet runs with thinking {type: between_tools}, Haiku with thinking disabled.
- Each cached run starts with its own nonce line, so it writes the cache on its first turn and reads it after (cold cache per run). Costs are derived from recorded tokens with app/core/pricing.py; cold/warm by the app's _compute_step_cold_warm rule.
- Loop rule: a turn cut off by max_tokens ends the run and its tool_use blocks are recorded but not executed; tool_use blocks in any other turn are executed and the loop continues, whatever the stop_reason.
- Voucher ids in the without-versions end in -UNB: they use the app session's unbounded_sonnet_loop and unbounded_haiku_loop rung ids, from which the app derives the voucher-id suffix.
- Tool precision (the app's metric) credits only the narrow query, the policy tool and the commit, so a raw SELECT * call is never counted optimal; it is not comparable between the without- and with-versions.
- The Anthropic SDK client retries failed or timed-out calls (default max_retries=2) inside one recorded turn; a retried call is not visible in the records and may have been billed.
- Limits: 12 invoices x 3 runs per version; the invoices test simple arithmetic (quantities x rates, a GST split, a debit note).
