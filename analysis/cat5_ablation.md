# Category 5 six-arm ablation — factual summary

Generated 2026-11-26T03:18:47.001291+00:00. Fixture version `cat5-ablation-fixtures-2026-11-26.v1`. Records read: 217; ok runs used (latest per key at current settings): 198; expected 198 (6 arms x 11 invoices x 3 repeats). Matrix complete: True; balanced: True.

Settings: max_tokens 4096 on every turn; gate arms step budget 4 (hard cap 5 model turns, as the app); neutral arms cap 12 model turns; call timeout 180s. Costs derived from recorded tokens with app/core/pricing.py; cold/warm by the app's `_compute_step_cold_warm` rule.

## Arms

| arm | tools | cached | model | escalation | gate | prompt | turn cap |
|---|---|---|---|---|---|---|---|
| raw_free_sonnet | raw | False | claude-sonnet-5-5 | False | False | neutral | 12 |
| raw_free_sonnet_cached | raw | True | claude-sonnet-5-5 | False | False | neutral | 12 |
| bundle_sonnet_cached | bundle | True | claude-sonnet-5-5 | False | False | neutral | 12 |
| bundle_gate_sonnet_cached | governed | True | claude-sonnet-5-5 | False | True | bounded_sonnet_cached_gate | 5 |
| bundle_haiku_cached | bundle | True | claude-haiku-5-5 | False | False | neutral | 12 |
| bundle_gate_haiku_escalate | governed | True | claude-haiku-5-5 | True | True | hybrid_haiku_sonnet_governed | 5 |

## Per arm (pooled)

| arm | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 33 | 33/33 100.0% [89.6–100.0%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 100.0% | 100.0% | 17.1% | 3.8 (3–4) | 0 | 0 | 15 / 0 | 68,435 | 0 | 0 | 1,685 | $153.72 | $153.72 | $153.72 |
| raw_free_sonnet_cached | 33 | 32/33 97.0% [84.7–99.5%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 98.2% | 100.0% | 17.1% | 3.8 (3–4) | 0 | 0 | 15 / 0 | 35,241 | 8,643 | 24,620 | 1,644 | $110.99 | $110.99 | $90.25 |
| bundle_sonnet_cached | 33 | 33/33 100.0% [89.6–100.0%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 15 / 0 | 3,968 | 8,284 | 16,569 | 1,279 | $43.10 | $43.10 | $23.22 |
| bundle_gate_sonnet_cached | 33 | 33/33 100.0% [89.6–100.0%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 15 / 0 | 6,952 | 8,638 | 25,913 | 1,276 | $50.84 | $50.84 | $30.11 |
| bundle_haiku_cached | 33 | 33/33 100.0% [89.6–100.0%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 15 / 0 | 4,275 | 8,284 | 16,569 | 1,550 | $2.40 | $2.40 | $1.45 |
| bundle_gate_haiku_escalate | 33 | 33/33 100.0% [89.6–100.0%] | 33/33 100.0% [89.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 15 / 15 | 7,105 | 12,642 | 22,125 | 1,344 | $22.62 | $22.62 | $12.14 |

## Tool use

Tool calls per run by tool name (each arm's own tools listed, including zero counts), and calls to tools the arm does not have (rejected with an error result, not executed).

| arm | n | tool calls per run by tool | calls to tools the arm does not have (total; per run; by name) |
|---|---|---|---|
| raw_free_sonnet | 33 | query_invoice_raw 1.00, query_po_raw 1.00, query_grn_wms_telemetry 1.00, query_vendor_audit_history 0.88, query_contract_amendments_and_dock_logs 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |
| raw_free_sonnet_cached | 33 | query_invoice_raw 1.00, query_po_raw 1.00, query_grn_wms_telemetry 1.00, query_vendor_audit_history 0.88, query_contract_amendments_and_dock_logs 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |
| bundle_sonnet_cached | 33 | fetch_3way_match_bundle 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |
| bundle_gate_sonnet_cached | 33 | fetch_3way_match_bundle 1.00, run_policy_tolerance_gate 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |
| bundle_haiku_cached | 33 | fetch_3way_match_bundle 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |
| bundle_gate_haiku_escalate | 33 | fetch_3way_match_bundle 1.00, run_policy_tolerance_gate 1.00, commit_reconciliation_voucher 1.00 | 0; 0.00; - |

Raw arms: how often each raw SELECT * tool was called (calls per run; runs that called it at least once).

| arm | n | query_invoice_raw | query_po_raw | query_grn_wms_telemetry | query_vendor_audit_history | query_contract_amendments_and_dock_logs |
|---|---|---|---|---|---|---|
| raw_free_sonnet | 33 | 1.00; 33/33 | 1.00; 33/33 | 1.00; 33/33 | 0.88; 28/33 | 1.00; 33/33 |
| raw_free_sonnet_cached | 33 | 1.00; 33/33 | 1.00; 33/33 | 1.00; 33/33 | 0.88; 28/33 | 1.00; 33/33 |

Tool precision is not comparable between raw and bundle arms: the app's metric credits only the bundle, gate and commit tools, so a raw SELECT * call is never counted optimal. Use the counts above for raw arms.

Field match rate per arm:

| arm | decision | authorized_net_principal_inr | authorized_gst_payout_inr | gst_escrow_holdback_inr | debit_note_deduction_inr |
|---|---|---|---|---|---|
| raw_free_sonnet | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| raw_free_sonnet_cached | 100.0% | 97.0% | 100.0% | 97.0% | 97.0% |
| bundle_sonnet_cached | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bundle_gate_sonnet_cached | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bundle_haiku_cached | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bundle_gate_haiku_escalate | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## Per arm x tier

### routine

| arm | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 16.5% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 72,882 | 0 | 0 | 1,617 | $161.93 | $161.93 | $161.93 |
| raw_free_sonnet_cached | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 16.5% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 38,380 | 8,643 | 25,929 | 1,577 | $116.73 | $116.73 | $95.98 |
| bundle_sonnet_cached | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,823 | 8,285 | 16,570 | 1,124 | $41.25 | $41.25 | $21.37 |
| bundle_gate_sonnet_cached | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,932 | 8,638 | 25,912 | 1,170 | $49.75 | $49.75 | $29.02 |
| bundle_haiku_cached | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,092 | 8,285 | 16,570 | 1,361 | $2.29 | $2.29 | $1.34 |
| bundle_gate_haiku_escalate | 12 | 12/12 100.0% [75.8–100.0%] | 12/12 100.0% [75.8–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,185 | 8,693 | 26,078 | 1,316 | $2.72 | $2.72 | $1.72 |

### dispute

| arm | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 15 / 0 | 71,582 | 0 | 0 | 1,789 | $161.06 | $161.06 | $161.06 |
| raw_free_sonnet_cached | 15 | 14/15 93.3% [70.2–98.8%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 96.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 15 / 0 | 37,080 | 8,643 | 25,929 | 1,750 | $115.86 | $115.86 | $95.11 |
| bundle_sonnet_cached | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 15 / 0 | 4,193 | 8,284 | 16,568 | 1,434 | $45.10 | $45.10 | $25.22 |
| bundle_gate_sonnet_cached | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 15 / 0 | 7,235 | 8,638 | 25,913 | 1,358 | $52.24 | $52.24 | $31.50 |
| bundle_haiku_cached | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 15 / 0 | 4,562 | 8,284 | 16,568 | 1,761 | $2.54 | $2.54 | $1.59 |
| bundle_gate_haiku_escalate | 15 | 15/15 100.0% [79.6–100.0%] | 15/15 100.0% [79.6–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 15 / 15 | 7,293 | 17,382 | 17,382 | 1,331 | $46.50 | $46.50 | $24.64 |

### hard_stop

| arm | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 19.4% | 3.2 (3–4) | 0 | 0 | 0 / 0 | 51,677 | 0 | 0 | 1,561 | $118.97 | $118.97 | $118.97 |
| raw_free_sonnet_cached | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 19.4% | 3.2 (3–4) | 0 | 0 | 0 / 0 | 24,366 | 8,644 | 18,728 | 1,516 | $87.37 | $87.37 | $66.63 |
| bundle_sonnet_cached | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,697 | 8,283 | 16,567 | 1,203 | $41.79 | $41.79 | $21.91 |
| bundle_gate_sonnet_cached | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,282 | 8,637 | 25,911 | 1,280 | $49.55 | $49.55 | $28.82 |
| bundle_haiku_cached | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,925 | 8,284 | 16,569 | 1,399 | $2.29 | $2.29 | $1.34 |
| bundle_gate_haiku_escalate | 6 | 6/6 100.0% [61.0–100.0%] | 6/6 100.0% [61.0–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,477 | 8,691 | 26,074 | 1,433 | $2.71 | $2.71 | $1.71 |

## Per arm x invoice

### raw_free_sonnet

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 74,615 | 0 | 0 | 1,482 | $164.05 | $164.05 | $164.05 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 75,346 | 0 | 0 | 1,972 | $170.41 | $170.41 | $170.41 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 20.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 44,516 | 0 | 0 | 1,569 | $104.72 | $104.72 | $104.72 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 75,800 | 0 | 0 | 1,599 | $167.59 | $167.59 | $167.59 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 65,524 | 0 | 0 | 1,615 | $147.20 | $147.20 | $147.20 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 75,105 | 0 | 0 | 1,792 | $168.13 | $168.13 | $168.13 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 15.9% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 66,574 | 0 | 0 | 1,780 | $150.95 | $150.95 | $150.95 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 65,458 | 0 | 0 | 1,591 | $146.83 | $146.83 | $146.83 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 74,537 | 0 | 0 | 1,605 | $165.13 | $165.13 | $165.13 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 18.9% | 3.3 (3–4) | 0 | 0 | 0 / 0 | 58,839 | 0 | 0 | 1,554 | $133.21 | $133.21 | $133.21 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 76,475 | 0 | 0 | 1,978 | $172.73 | $172.73 | $172.73 |

### raw_free_sonnet_cached

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 40,148 | 8,643 | 25,930 | 1,466 | $119.15 | $119.15 | $98.41 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 40,749 | 8,644 | 25,932 | 1,854 | $124.24 | $124.24 | $103.50 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 20.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 18,660 | 8,645 | 17,289 | 1,525 | $75.91 | $75.91 | $55.17 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 15.9% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 41,345 | 8,642 | 25,927 | 1,526 | $122.15 | $122.15 | $101.40 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 31,061 | 8,645 | 25,935 | 1,606 | $102.39 | $102.39 | $81.64 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 40,570 | 8,640 | 25,920 | 1,638 | $121.71 | $121.71 | $100.98 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 32,007 | 8,644 | 25,932 | 1,717 | $105.39 | $105.39 | $84.64 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 30,989 | 8,644 | 25,933 | 1,607 | $102.25 | $102.25 | $81.50 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 40,020 | 8,642 | 25,927 | 1,598 | $120.22 | $120.22 | $99.48 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 18.9% | 3.3 (3–4) | 0 | 0 | 0 / 0 | 30,073 | 8,643 | 20,166 | 1,507 | $98.84 | $98.84 | $78.09 |
| inv-12 | 3 | 2/3 66.7% [20.8–93.9%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 80.0% | 100.0% | 16.7% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 42,031 | 8,642 | 25,926 | 2,043 | $128.69 | $128.69 | $107.95 |

### bundle_sonnet_cached

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,794 | 8,285 | 16,569 | 1,053 | $40.48 | $40.48 | $20.60 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 4,717 | 8,281 | 16,563 | 1,703 | $48.82 | $48.82 | $28.95 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,514 | 8,284 | 16,568 | 1,255 | $41.95 | $41.95 | $22.06 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,809 | 8,286 | 16,573 | 1,080 | $40.79 | $40.79 | $20.91 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 3,485 | 8,286 | 16,571 | 1,209 | $41.43 | $41.43 | $21.55 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 3,952 | 8,284 | 16,568 | 1,285 | $43.12 | $43.12 | $23.24 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,890 | 8,283 | 16,567 | 1,251 | $42.66 | $42.66 | $22.78 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 3,543 | 8,285 | 16,570 | 1,297 | $42.42 | $42.42 | $22.54 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,800 | 8,285 | 16,570 | 1,110 | $41.07 | $41.07 | $21.19 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,879 | 8,283 | 16,565 | 1,151 | $41.63 | $41.63 | $21.75 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 5,267 | 8,285 | 16,570 | 1,679 | $49.69 | $49.69 | $29.81 |

### bundle_gate_sonnet_cached

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,024 | 8,636 | 25,907 | 1,178 | $50.01 | $50.01 | $29.28 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 7,959 | 8,638 | 25,914 | 1,434 | $54.45 | $54.45 | $33.72 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 5,903 | 8,636 | 25,908 | 1,235 | $48.34 | $48.34 | $27.61 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,064 | 8,638 | 25,915 | 1,109 | $49.41 | $49.41 | $28.68 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 6,144 | 8,636 | 25,909 | 1,227 | $48.74 | $48.74 | $28.01 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 7,286 | 8,638 | 25,915 | 1,386 | $52.62 | $52.62 | $31.89 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,671 | 8,638 | 25,915 | 1,236 | $49.89 | $49.89 | $29.16 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 6,068 | 8,639 | 25,916 | 1,307 | $49.39 | $49.39 | $28.66 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,971 | 8,638 | 25,913 | 1,158 | $49.71 | $49.71 | $28.98 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,661 | 8,638 | 25,914 | 1,325 | $50.76 | $50.76 | $30.03 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 0 | 8,717 | 8,637 | 25,912 | 1,436 | $55.98 | $55.98 | $35.25 |

### bundle_haiku_cached

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,085 | 8,283 | 16,567 | 1,357 | $2.29 | $2.29 | $1.34 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 4,967 | 8,283 | 16,565 | 1,849 | $2.62 | $2.62 | $1.67 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 3,713 | 8,285 | 16,571 | 1,409 | $2.28 | $2.28 | $1.32 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,042 | 8,284 | 16,567 | 1,261 | $2.24 | $2.24 | $1.28 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 3,789 | 8,284 | 16,567 | 1,493 | $2.33 | $2.33 | $1.37 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 4,347 | 8,284 | 16,569 | 1,632 | $2.45 | $2.45 | $1.50 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,186 | 8,286 | 16,571 | 1,490 | $2.36 | $2.36 | $1.41 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 3,887 | 8,285 | 16,569 | 1,622 | $2.40 | $2.40 | $1.45 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,054 | 8,287 | 16,573 | 1,335 | $2.27 | $2.27 | $1.32 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 0 / 0 | 4,136 | 8,284 | 16,567 | 1,390 | $2.31 | $2.31 | $1.36 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 3.0 (3–3) | 0 | 0 | 3 / 0 | 5,822 | 8,285 | 16,571 | 2,209 | $2.89 | $2.89 | $1.94 |

### bundle_gate_haiku_escalate

| invoice | n | exact [Wilson 95%] | decision [Wilson 95%] | committed | field acc | evidence recall | tool precision | turns mean (min–max) | cap hits | truncated turns | esc expected / fired | uncached in | cache write | cache read | output | $/1k billed | $/1k cold | $/1k warm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| inv-01 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,259 | 8,692 | 26,077 | 1,278 | $2.71 | $2.71 | $1.71 |
| inv-02 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 7,960 | 17,384 | 17,384 | 1,366 | $48.02 | $48.02 | $26.16 |
| inv-03 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,169 | 8,691 | 26,074 | 1,472 | $2.70 | $2.70 | $1.70 |
| inv-04 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,273 | 8,694 | 26,082 | 1,221 | $2.69 | $2.69 | $1.69 |
| inv-05 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 6,216 | 17,386 | 17,386 | 1,251 | $44.12 | $44.12 | $22.26 |
| inv-07 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 7,305 | 17,379 | 17,379 | 1,318 | $46.44 | $46.44 | $24.59 |
| inv-08 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,917 | 8,693 | 26,079 | 1,428 | $2.75 | $2.75 | $1.75 |
| inv-09 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 6,171 | 17,381 | 17,381 | 1,239 | $43.62 | $43.62 | $21.76 |
| inv-10 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 7,289 | 8,692 | 26,076 | 1,334 | $2.74 | $2.74 | $1.74 |
| inv-11 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 0 / 0 | 6,785 | 8,691 | 26,074 | 1,393 | $2.72 | $2.72 | $1.72 |
| inv-12 | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 100.0% | 100.0% | 100.0% | 100.0% | 4.0 (4–4) | 0 | 0 | 3 / 3 | 8,812 | 17,379 | 17,379 | 1,484 | $50.30 | $50.30 | $28.44 |

## Lever table (adjacent arms)

| lever | from -> to | what changes | exact from -> to (Δ pp) | decision Δ pp | $/1k billed from -> to (x) | $/1k cold Δ | $/1k warm Δ |
|---|---|---|---|---|---|---|---|
| caching alone | raw_free_sonnet -> raw_free_sonnet_cached | cached: False -> True | 100.0% -> 97.0% (-3.0) | +0.0 | $153.72 -> $110.99 (0.722x) | $-42.73 | $-63.47 |
| narrow query | raw_free_sonnet_cached -> bundle_sonnet_cached | tool_set: raw -> bundle | 97.0% -> 100.0% (+3.0) | +0.0 | $110.99 -> $43.10 (0.388x) | $-67.90 | $-67.04 |
| deterministic gate | bundle_sonnet_cached -> bundle_gate_sonnet_cached | tool_set: bundle -> governed; gate: False -> True; prompt: neutral -> bounded_sonnet_cached_gate; turn_cap: 12 -> 5 | 100.0% -> 100.0% (+0.0) | +0.0 | $43.10 -> $50.84 (1.180x) | $7.75 | $6.90 |
| model swap without gate | bundle_sonnet_cached -> bundle_haiku_cached | start_model: claude-sonnet-5-5 -> claude-haiku-5-5 | 100.0% -> 100.0% (+0.0) | +0.0 | $43.10 -> $2.40 (0.056x) | $-40.69 | $-21.76 |
| gate + tiering | bundle_haiku_cached -> bundle_gate_haiku_escalate | tool_set: bundle -> governed; escalate: False -> True; gate: False -> True; prompt: neutral -> hybrid_haiku_sonnet_governed; turn_cap: 12 -> 5 | 100.0% -> 100.0% (+0.0) | +0.0 | $2.40 -> $22.62 (9.411x) | $20.22 | $10.69 |
| gate Sonnet -> gate Haiku escalate | bundle_gate_sonnet_cached -> bundle_gate_haiku_escalate | start_model: claude-sonnet-5-5 -> claude-haiku-5-5; escalate: False -> True; prompt: bounded_sonnet_cached_gate -> hybrid_haiku_sonnet_governed | 100.0% -> 100.0% (+0.0) | +0.0 | $50.84 -> $22.62 (0.445x) | $-28.23 | $-17.98 |

## Baseline: original scripted naive runs vs raw_free_sonnet (inv-01..03)

Golden scripted naive runs (unbounded_sonnet_loop prompt, 7-step one-tool-per-step script, max_tokens 2048), n=1 each, beside raw_free_sonnet.

| invoice | source | n | exact | decision | turns | tool calls | prompt tokens | output | billed $/1k |
|---|---|---|---|---|---|---|---|---|---|
| inv-01 | original scripted baseline | 1 | True | True | 7 | 6 | 115,246 | 1,699 | $247.48 |
| inv-01 | raw_free_sonnet | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 4.0 | 6.0 | 74,615 | 1,482 | $164.05 |
| inv-02 | original scripted baseline | 1 | True | True | 7 | 6 | 115,766 | 2,356 | $255.09 |
| inv-02 | raw_free_sonnet | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 4.0 | 6.0 | 75,346 | 1,972 | $170.41 |
| inv-03 | original scripted baseline | 1 | True | True | 3 | 2 | 29,371 | 1,307 | $71.81 |
| inv-03 | raw_free_sonnet | 3 | 3/3 100.0% [43.9–100.0%] | 3/3 100.0% [43.9–100.0%] | 3.0 | 5.0 | 44,516 | 1,569 | $104.72 |

## Fixtures: hand derivation vs deterministic gate

| invoice | scenario | tier | hub | expected decision (manual) | escalation | grand total INR | agrees with gate | group |
|---|---|---|---|---|---|---|---|---|
| inv-01 | Statutory GST escrow, MSE vendor, clean receipt (original) | routine | FC-BLR-01 | APPROVE_WITH_GST_ESCROW | False | 2,171,200.00 | True | default |
| inv-02 | Multi-factor dispute: DOA + amendment + unauthorised hike + freight (original) | dispute | FC-BOM-02 | APPROVE_PARTIAL_DEBIT_NOTE | True | 3,899,900.00 | True | default |
| inv-03 | Hard stop: cancelled IRN + phantom line (original) | hard_stop | FC-DEL-03 | BLOCK_EXCEPTION_HOLD | False | 3,127,000.00 | True | default |
| inv-04 | Clean full match | routine | FC-HYD-01 | APPROVE_CLEAN | False | 2,542,900.00 | True | default |
| inv-05 | DOA rejects only | dispute | FC-BLR-01 | APPROVE_PARTIAL_DEBIT_NOTE | True | 2,950,000.00 | True | default |
| inv-06 | Price variance inside the 1.5% band (standard DDP INR PO, no amendment) | routine | FC-DEL-03 | APPROVE_PARTIAL_DEBIT_NOTE | True | 4,340,984.00 | False | gate_disagreement |
| inv-07 | Price variance outside tolerance, no amendment | dispute | FC-BOM-02 | APPROVE_PARTIAL_DEBIT_NOTE | True | 3,096,320.00 | True | default |
| inv-08 | Authorised amendment only | routine | FC-HYD-01 | APPROVE_CLEAN | False | 3,919,370.00 | True | default |
| inv-09 | Freight above the PO cap | dispute | FC-DEL-03 | APPROVE_PARTIAL_DEBIT_NOTE | True | 5,318,850.00 | True | default |
| inv-10 | Statutory GST escrow on a non-MSE large-enterprise vendor (5% GST) | routine | FC-BOM-02 | APPROVE_WITH_GST_ESCROW | False | 3,273,900.00 | True | default |
| inv-11 | Hard stop: phantom unreceived line (>10%) with an active IRN and matched GSTR-2B | hard_stop | FC-BLR-01 | BLOCK_EXCEPTION_HOLD | False | 3,182,460.00 | True | default |
| inv-12 | Multi-factor dispute: short receipt + unauthorised hike (draft amendment only) + DOA on an amended line + freight over cap, with GSTR-2B pending | dispute | FC-HYD-01 | APPROVE_PARTIAL_DEBIT_NOTE | True | 5,981,420.00 | True | default |

## When the deterministic gate is wrong (inv-06)

These runs never enter the pooled tables. Lead ruling: the manual derivation is correct and the gate is wrong. Manual 2.1 allows the 1.5% band only when the PO currency notes specify an index-linked float; this PO is plain DDP INR with no amendment, so line 1 pays at the PO rate. The gate's WITHIN_1.5PCT_TOLERANCE branch ignores that condition.

Manual 2.1: "If `po_unit_price_inr < billed_unit_price_inr <= po_unit_price_inr * 1.015`: tiny FX/metal-surcharge rounding within `1.50%` MAY pass ONLY when PO currency notes specify index-linked float; otherwise standard landed DDP catalog POs default to PO unit rate unless amended."

Manual derivation (ground truth): APPROVE_PARTIAL_DEBIT_NOTE, net 3,656,000.00, GST payout 658,080.00, escrow 0.00, debit 22,800.00, escalation True.
  - L1 NM-CBL-1.5SQ-90M: payable = MIN(1,200, 1,200) = 1,200; billed 1,499 vs PO 1,480: 1,480 < 1,499 <= 1,480 x 1.015 = 1,502.20 (+1.28%). Manual 2.1 bullet 2: the band 'MAY pass ONLY when PO currency notes specify index-linked float; otherwise standard landed DDP catalog POs default to PO unit rate unless amended'. PO is standard DDP INR, no amendment -> rate 1,480; authorised 1,200 x 1,480 = 1,776,000; billed 1,798,800; deduction 22,800.
  - L2 NM-CBL-2.5SQ-90M: payable 800; rate 2,350 (= PO); authorised 1,880,000; deduction 0.
  - 1,776,000 + 1,880,000 + 0 = 3,656,000.00
  - 3,678,800.00 - 3,656,000.00 = 22,800.00
  - Case A: payout = ROUND(3,656,000 x 0.18, 2) = 658,080.00; escrow 0.00
  - Case A with debit note > 0 -> APPROVE_PARTIAL_DEBIT_NOTE
Gate output: APPROVE_CLEAN, net 3,678,800.00, GST payout 662,184.00, escrow 0.00, debit 0.00, escalation False.
  - L1 NM-CBL-1.5SQ-90M: 1,480 < 1,499 <= 1,502.20 -> price_rule WITHIN_1.5PCT_TOLERANCE -> rate 1,499 (billed); authorised 1,200 x 1,499 = 1,798,800; deduction 0.
  - L2 NM-CBL-2.5SQ-90M: rate 2,350 (= PO); authorised 1,880,000.
  - Net 1,798,800 + 1,880,000 = 3,678,800.00; debit 3,678,800 - 3,678,800 = 0.00; GST Case A ROUND(3,678,800 x 0.18, 2) = 662,184.00; APPROVE_CLEAN; escalation_required false.

fetch_3way_match_bundle does not return purchase_orders.currency (the PO currency notes), so bundle arms cannot check the manual's index-linked-float condition; raw arms can (query_po_raw returns it).

| arm | n | matches manual | matches gate output | neither | no commit | decisions committed | line 1 NM-CBL-1.5SQ-90M rate paid (PO 1,480 / billed 1,499 / other) |
|---|---|---|---|---|---|---|---|
| raw_free_sonnet | 3 | 3 | 0 | 0 | 0 | APPROVE_PARTIAL_DEBIT_NOTE 3 | 3 / 0 / 0 |
| raw_free_sonnet_cached | 3 | 3 | 0 | 0 | 0 | APPROVE_PARTIAL_DEBIT_NOTE 3 | 3 / 0 / 0 |
| bundle_sonnet_cached | 3 | 3 | 0 | 0 | 0 | APPROVE_PARTIAL_DEBIT_NOTE 3 | 3 / 0 / 0 |
| bundle_gate_sonnet_cached | 3 | 0 | 3 | 0 | 0 | APPROVE_CLEAN 3 | gate computes (n/a) |
| bundle_haiku_cached | 3 | 3 | 0 | 0 | 0 | APPROVE_PARTIAL_DEBIT_NOTE 3 | 3 / 0 / 0 |
| bundle_gate_haiku_escalate | 3 | 0 | 3 | 0 | 0 | APPROVE_CLEAN 3 | gate computes (n/a) |

Line-1 rate is read from the committed net principal (3,656,000 = PO rate, 3,678,800 = billed rate); line 2 and freight are the same under both truths.
- bundle_gate_sonnet_cached / r0 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **Executive AP audit summary: INV-DL-2026-4157**  Voucher **VCH-4157-BOU** is committed with decision **APPROVE_CLEAN**, and the policy gate verified it.  - **Match:** On both lines the GRN-accepted quantity equals the PO and billed quantity (1,200 and 800), with no DOA rejections. - **Price:** Line 1 was billed at INR 1,499 against a PO rate of INR 1,480 (+1.28%), which is within the 1.5% tolerance. Line 2 matches the PO rate exactly. Freight billed was 0 against a cap of 0. - **Tax status:** The IRN is ACTIVE_VERIFIED and GSTR-2B is MATCHED_VERIFIED. No hard block fired and no escalation was
- bundle_gate_sonnet_cached / r1 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **Executive AP Audit Summary: INV-DL-2026-4157**  Voucher **VCH-4157-BOU** is committed with the decision **APPROVE_CLEAN**. The gate has verified it.  - **Match:** The invoice agrees with the PO and the goods receipts. Both lines were fully accepted (1,200 and 800 units) with zero DOA rejections. - **Price:** Line 1 was billed at ₹1,499 against the PO rate of ₹1,480 (+1.28%), which is inside the 1.5% tolerance. Line 2 matches the PO exactly. - **Freight and amendments:** Claimed freight is ₹0 against a ₹0 cap, and there are no contract amendments. - **Compliance:** The IRN is ACTIVE_VERIFIED 
- bundle_gate_sonnet_cached / r2 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **AP Audit Summary: INV-DL-2026-4157 (PO-NM-DEL-4157, FC-DEL-03)**  Voucher **VCH-4157-BOU** is committed as **APPROVE_CLEAN**, and the gate verified it.  - **Evidence:** The IRN is ACTIVE_VERIFIED and GSTR-2B is MATCHED_VERIFIED. GRN accepted quantities equal PO and billed quantities (1,200 and 800), with no DOA rejections. - **Pricing:** Line 1 was billed at ₹1,499 against the PO rate of ₹1,480, a 1.28% variance inside the 1.5% tolerance band. Line 2 matches the PO exactly. There are no amendments and no freight claimed. - **Payout:** Principal ₹36,78,800.00 and GST ₹6,62,184.00, totalling ₹
- bundle_gate_haiku_escalate / r0 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **Voucher VCH-4157-HYB committed for INV-DL-2026-4157: APPROVE_CLEAN.**  - Net principal: ₹36,78,800.00 - GST payout: ₹6,62,184.00 (GSTR-2B matched; no escrow) - Debit note deduction: ₹0.00 - Total: ₹43,40,984.00, matching the claimed grand total  All 1,200 + 800 units were accepted at GRN with zero DOA. The IRN is active and verified, and freight claimed is zero.  **Flag for review:** Line 1 (NM-CBL-1.5SQ-90M) is billed at ₹1,499 against a PO rate of ₹1,480, a 1.28% overrun. The gate allowed it under the 1.5% rounding band. The SOP only permits this when the PO carries an index-linked float c
- bundle_gate_haiku_escalate / r1 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **AP Audit Summary: INV-DL-2026-4157**  The voucher is committed as **VCH-4157-HYB**, decision **APPROVE_CLEAN**. Sonnet escalation did not fire; the gate returned `escalation_required = false`.  - **Principal:** INR 3,678,800.00 (line 1: INR 1,798,800; line 2: INR 1,880,000) - **GST (18%):** INR 662,184.00 released (GSTR-2B MATCHED_VERIFIED) - **Escrow holdback:** INR 0.00 - **Debit note:** INR 0.00 - **Grand total:** INR 4,340,984.00, matching the claim  All 2,000 units were accepted at GRN with no DOA. Line 1 is billed at INR 1,499 against a PO rate of INR 1,480 (+1.28%). The gate accepted 
- bundle_gate_haiku_escalate / r2 (matches_gate_output, line 1 billed_rate): committed {"decision": "APPROVE_CLEAN", "authorized_net_principal_inr": 3678800.0, "authorized_gst_payout_inr": 662184.0, "gst_escrow_holdback_inr": 0.0, "debit_note_deduction_inr": 0.0}; tools fetch_3way_match_bundle, run_policy_tolerance_gate, commit_reconciliation_voucher; final message: **Executive AP Audit Summary: INV-DL-2026-4157**  Voucher **VCH-4157-HYB** is committed as **APPROVE_CLEAN**. Indraprastha Cables & Wires Ltd. (FC-DEL-03, PO-NM-DEL-4157) is cleared for payment.  - **Principal:** INR 36,78,800.00 | **GST (18%):** INR 6,62,184.00 | **Total:** INR 43,40,984.00 - **Debit note:** INR 0. All 2,000 units were accepted at GRN with no DOA rejections, and no freight was claimed. - **Compliance:** IRN ACTIVE_VERIFIED and GSTR-2B MATCHED_VERIFIED, so no GST escrow is needed. - **Watch item:** Line 1 is billed at ₹1,499 against a PO rate of ₹1,480 (+1.28%). It is within t

## For lead review (every non-exact run)

- **raw_free_sonnet_cached / inv-12 / r2** (run d3f1d944-701b-4af8-973d-5fb34599b81b): mismatched authorized_net_principal_inr, gst_escrow_holdback_inr, debit_note_deduction_inr; turns 4, cap hit False, truncated turns 0
  - expected: {"decision": "APPROVE_PARTIAL_DEBIT_NOTE", "authorized_net_principal_inr": 4862520.0, "authorized_gst_payout_inr": 0.0, "gst_escrow_holdback_inr": 875253.6, "debit_note_deduction_inr": 206480.0}
  - committed: {"decision": "APPROVE_PARTIAL_DEBIT_NOTE", "authorized_net_principal_inr": 3862520.0, "authorized_gst_payout_inr": 0.0, "gst_escrow_holdback_inr": 695253.6, "debit_note_deduction_inr": 1206480.0}
  - tools: t1:query_invoice_raw, t1:query_po_raw, t1:query_grn_wms_telemetry, t1:query_contract_amendments_and_dock_logs, t2:query_vendor_audit_history, t3:commit_reconciliation_voucher
  - final message: I committed voucher **VCH-3774-UNB** for INV-TS-2026-3774 as `APPROVE_PARTIAL_DEBIT_NOTE`, but the commit returned `gate_verified: false`. I never ran a deterministic policy-gate check (no such tool was available), so the arithmetic below is my own.  - **Authorized net principal:** INR 3,862,520.00, which includes the 12,000 freight cap per the policy formula. - **GST escrow holdback:** INR 695,253.60. The GST payout is 0 because GSTR-2B is pending while the IRN is active. - **Debit note:** INR 1,206,480.00, made up of:   - microwave short-shipment of 20 units: 138,000   - OTG price capped to the PO rate, because the amendment is only a draft: 31,500   - 12 induction cooktops rejected on arrival: 28,980   - freight claim of 20,000 disallowed in full against the 12,000 cap, then the 12,000 cap added back into principal per policy: 1,006,000 - **Invariant:** 3,862,520 + 1,206,480 = 5,069,000, which matches the invoice taxable total.  No circuit-breaker triggers fired. The 1,006,000 freight and cap line is derived as the remainder of the total deduction, so please have someone check it.

## Data quality

- error records (current settings): 0; their billed spend $0.0000
- truncated (max_tokens) turns: 0
- model mismatches (returned != intended): 0
- cache anomalies: 0
- cap hits: 0
- runs with no voucher committed for the invoice: 0
- tool calls outside the arm's tool set: 0
- superseded records (excluded; key re-run): 1; their billed spend $0.0207
  - superseded: harness ended the run with tool calls not executed — raw_free_sonnet / inv-05 / r0 (run bb2868c3-fe63-4b84-aad1-53d25972257e)
- turns with tool_use blocks but stop_reason other than tool_use (tools executed): 1
  - raw_free_sonnet / inv-06 / r2 turn 1: stop_reason end_turn, 4 tool calls

## Analysis notes

- The policy manual (SOP-AP-3WAY-2026.v4) is the system text of every arm, including the neutral ones. It names fetch_3way_match_bundle and run_policy_tolerance_gate, the 4-step budget (max_step_budget = 4) and says the commit is refused without the gate (5.2); raw and bundle arms do not have some of those tools.
- The deterministic gate sets escalation_required whenever the debit note is above zero (or on 2+ discrepancies), so single-factor debit notes (DOA only, freight only, one price hike) escalate in the Haiku -> Sonnet arm even though manual 6.2 describes escalation for multi-factor disputes. expected_escalation follows the gate rule.
- Thinking differs by model in the app's call function: Sonnet runs with thinking {type: between_tools}, Haiku with thinking disabled. The model-swap levers therefore also change thinking.
- Voucher ids in no-gate arms end in -UNB: those arms reuse the app session's unbounded_sonnet_loop rung id to disable the gate requirement, and the app derives the voucher-id suffix from the rung id. The model sees this id.
- Latent gate gaps not exercised by the default fixtures: the gate ignores approved_freight_waiver_inr (2.2/2.3 allow a freight-waiver amendment); it takes the GST rate from the first invoice line only; it does not implement Trigger 3 (duplicate invoice or PAYMENT_FREEZE vendor). The 1.5% band gap is exercised by inv-06 (separate section).
- The Anthropic SDK client retries failed or timed-out calls (default max_retries=2) inside one recorded turn; a retried call is not visible in the records and may have been billed.
- Tool precision (the app's metric, min(optimal, total) / total) counts only fetch_3way_match_bundle, run_policy_tolerance_gate and commit_reconciliation_voucher as optimal. A raw SELECT * tool is never credited, so a raw arm's precision is at most 1 / (number of calls) however few lookups it makes; it is not comparable between raw and bundle arms. Use the per-tool call counts instead.
- Loop rule (v2): a turn cut off by max_tokens ends the run and its tool_use blocks are recorded but not executed; tool_use blocks in any other turn are executed and the loop continues, whatever the stop_reason (the API can return end_turn together with tool_use). One v1 record that stopped on such a turn is superseded. The app's live runner follows the same rule.
