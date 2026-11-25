# Category 2 quality scoring — results

Generated: 2026-11-25T16:39:07.758675+00:00 · answer key `2026-11-25.3` (`cat2_quality_keys.json`) · drafts: `cat2_golden_replays.json` (12 = 4 bundles × 3 rungs, n=1 per cell, no rerun).

Templated drafts are scored on their `structured_draft` rendered to Markdown by `quality_scoring.render_structured_draft`; unbounded drafts on `raw_markdown` as is. Coverage values: hits/total (rate) [Wilson 95%, %]. Cost per 1k documents = recorded input/output tokens priced by `compute_run_finops`.

Judge: `judgements.jsonl` — 60 ok calls.

## Answer key

| Bundle | Facts | Core | Detail | metric | money | deadline | owner | decision | cause |
|---|---|---|---|---|---|---|---|---|---|
| brief-01 | 18 | 8 | 10 | 4 | 6 | 2 | 1 | 3 | 2 |
| brief-02 | 18 | 8 | 10 | 3 | 6 | 2 | 1 | 6 | 0 |
| reg-01 | 18 | 8 | 10 | 6 | 4 | 2 | 0 | 3 | 3 |
| reg-02 | 18 | 8 | 10 | 7 | 4 | 1 | 1 | 3 | 2 |

## Fact coverage — per rung (pooled over the 4 bundles)

| Group | Drafts | Overall | Core | Detail | Facts / 1k output tok | Output tokens | $ / 1k docs |
|---|---|---|---|---|---|---|---|
| `sonnet_unbounded` | 4 | 72/72 (100.0%) [94.9–100.0] | 32/32 (100.0%) [89.3–100.0] | 40/40 (100.0%) [91.2–100.0] | 3.49 | 20,647 | $58.92 |
| `sonnet_templated` | 4 | 69/72 (95.8%) [88.5–98.6] | 32/32 (100.0%) [89.3–100.0] | 37/40 (92.5%) [80.1–97.4] | 9.84 | 7,013 | $27.25 |
| `haiku_templated` | 4 | 68/72 (94.4%) [86.6–97.8] | 32/32 (100.0%) [89.3–100.0] | 36/40 (90.0%) [76.9–96.0] | 9.35 | 7,269 | $1.39 |

By category (pooled):

| Rung | metric | money | deadline | owner | decision | cause |
|---|---|---|---|---|---|---|
| `sonnet_unbounded` | 20/20 | 20/20 | 7/7 | 3/3 | 15/15 | 7/7 |
| `sonnet_templated` | 19/20 | 19/20 | 7/7 | 3/3 | 15/15 | 6/7 |
| `haiku_templated` | 20/20 | 19/20 | 7/7 | 2/3 | 14/15 | 6/7 |

### Per rung × bundle

| Group | Drafts | Overall | Core | Detail | Facts / 1k output tok | Output tokens | $ / 1k docs |
|---|---|---|---|---|---|---|---|
| `sonnet_unbounded` brief-01 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 3.00 | 6,000 | $67.75 |
| `sonnet_unbounded` brief-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 3.83 | 4,698 | $54.59 |
| `sonnet_unbounded` reg-01 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 3.60 | 5,001 | $56.96 |
| `sonnet_unbounded` reg-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 3.64 | 4,948 | $56.40 |
| `sonnet_templated` brief-01 | 1 | 17/18 (94.4%) [74.2–99.0] | 8/8 (100.0%) [67.6–100.0] | 9/10 (90.0%) [59.6–98.2] | 9.17 | 1,853 | $28.68 |
| `sonnet_templated` brief-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 10.24 | 1,757 | $27.58 |
| `sonnet_templated` reg-01 | 1 | 16/18 (88.9%) [67.2–96.9] | 8/8 (100.0%) [67.6–100.0] | 8/10 (80.0%) [49.0–94.3] | 9.44 | 1,695 | $26.32 |
| `sonnet_templated` reg-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 10.54 | 1,708 | $26.41 |
| `haiku_templated` brief-01 | 1 | 16/18 (88.9%) [67.2–96.9] | 8/8 (100.0%) [67.6–100.0] | 8/10 (80.0%) [49.0–94.3] | 8.41 | 1,902 | $1.46 |
| `haiku_templated` brief-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 9.54 | 1,887 | $1.44 |
| `haiku_templated` reg-01 | 1 | 16/18 (88.9%) [67.2–96.9] | 8/8 (100.0%) [67.6–100.0] | 8/10 (80.0%) [49.0–94.3] | 9.13 | 1,752 | $1.34 |
| `haiku_templated` reg-02 | 1 | 18/18 (100.0%) [82.4–100.0] | 8/8 (100.0%) [67.6–100.0] | 10/10 (100.0%) [72.2–100.0] | 10.42 | 1,728 | $1.33 |

## Unsupported numbers (measure C) — per rung

| Group | Tokens extracted | Ignored | Numeric tokens | In source | Not in source | Share not in source | Ignored by rule |
|---|---|---|---|---|---|---|---|
| `sonnet_unbounded` | 897 | 114 | 783 | 737 | 46 | 5.9% | date_in_source 31, document_id 5, list_numbering 75, own_label 3 |
| `sonnet_templated` | 306 | 33 | 273 | 267 | 6 | 2.2% | date_in_source 8, in_title 8, own_label 17 |
| `haiku_templated` | 329 | 34 | 295 | 287 | 8 | 2.7% | date_in_source 13, in_title 5, own_label 16 |

### Per rung × bundle

| Group | Tokens extracted | Ignored | Numeric tokens | In source | Not in source | Share not in source | Ignored by rule |
|---|---|---|---|---|---|---|---|
| `sonnet_unbounded` brief-01 | 256 | 19 | 237 | 218 | 19 | 8.0% | date_in_source 1, document_id 1, list_numbering 15, own_label 2 |
| `sonnet_unbounded` brief-02 | 213 | 24 | 189 | 174 | 15 | 7.9% | date_in_source 7, document_id 1, list_numbering 15, own_label 1 |
| `sonnet_unbounded` reg-01 | 215 | 44 | 171 | 164 | 7 | 4.1% | date_in_source 21, document_id 1, list_numbering 22 |
| `sonnet_unbounded` reg-02 | 213 | 27 | 186 | 181 | 5 | 2.7% | date_in_source 2, document_id 2, list_numbering 23 |
| `sonnet_templated` brief-01 | 90 | 4 | 86 | 86 | 0 | 0.0% | in_title 1, own_label 3 |
| `sonnet_templated` brief-02 | 80 | 11 | 69 | 69 | 0 | 0.0% | date_in_source 4, in_title 2, own_label 5 |
| `sonnet_templated` reg-01 | 72 | 11 | 61 | 60 | 1 | 1.6% | date_in_source 4, in_title 4, own_label 3 |
| `sonnet_templated` reg-02 | 64 | 7 | 57 | 52 | 5 | 8.8% | in_title 1, own_label 6 |
| `haiku_templated` brief-01 | 97 | 6 | 91 | 89 | 2 | 2.2% | date_in_source 2, in_title 1, own_label 3 |
| `haiku_templated` brief-02 | 83 | 8 | 75 | 74 | 1 | 1.3% | date_in_source 4, in_title 1, own_label 3 |
| `haiku_templated` reg-01 | 78 | 12 | 66 | 64 | 2 | 3.0% | date_in_source 7, in_title 2, own_label 3 |
| `haiku_templated` reg-02 | 71 | 8 | 63 | 60 | 3 | 4.8% | in_title 1, own_label 7 |

### Judge review of not-in-source numbers (majority of the rubric repeats)

| Group | Reviewed | derived_correct | derived_incorrect | not_in_source_unverifiable | not_a_claim | no_majority | Not unanimous |
|---|---|---|---|---|---|---|---|
| `sonnet_unbounded` | 46 | 44 | 1 | 0 | 1 | 0 | 1 |
| `sonnet_templated` | 6 | 1 | 0 | 5 | 0 | 0 | 0 |
| `haiku_templated` | 8 | 2 | 0 | 6 | 0 | 0 | 0 |
| brief-01|haiku_templated | 2 | 1 | 0 | 1 | 0 | 0 | 0 |
| brief-01|sonnet_templated | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| brief-01|sonnet_unbounded | 19 | 18 | 1 | 0 | 0 | 0 | 0 |
| brief-02|haiku_templated | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| brief-02|sonnet_templated | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| brief-02|sonnet_unbounded | 15 | 15 | 0 | 0 | 0 | 0 | 0 |
| reg-01|haiku_templated | 2 | 1 | 0 | 1 | 0 | 0 | 0 |
| reg-01|sonnet_templated | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| reg-01|sonnet_unbounded | 7 | 7 | 0 | 0 | 0 | 0 | 1 |
| reg-02|haiku_templated | 3 | 0 | 0 | 3 | 0 | 0 | 0 |
| reg-02|sonnet_templated | 5 | 0 | 0 | 5 | 0 | 0 | 0 |
| reg-02|sonnet_unbounded | 5 | 4 | 0 | 0 | 1 | 0 | 0 |

Numbers on which the repeats disagree (1):

| Draft | Id | Number | Verdicts (by repeat) | Majority |
|---|---|---|---|---|
| reg-01|sonnet_unbounded | N02 | `04:22 IST` | r0:not_in_source_unverifiable, r1:derived_correct, r2:derived_correct | derived_correct |

Per-draft list of not-in-source numbers (id · number · context):

- **brief-01 · `sonnet_unbounded`** — 19
  - N01 · `$374,580` (number) · …t standby fleet plus $9,800 in night-shift overtime). Against gross exposure of $374,580, this is a **15.5x mitigation ratio** on the full figure. The governance rubric…
  - N02 · `15.5x` (number) · …9,800 in night-shift overtime). Against gross exposure of $374,580, this is a **15.5x mitigation ratio** on the full figure. The governance rubric specifies a 12.9x…
  - N03 · `$62.75` (number) · …e. Order volume of 612,000 on Day 3 produced an average basket value of roughly $62.75. That figure is derived from the reported GMV and order count and is not a sepa…
  - N04 · `134%` (number) · …hours against a rated throughput of 145,000 parcels per day**, a volume roughly 134% of daily rated capacity, concentrated in under a full day. Hoskote (94.1%) and…
  - N05 · `96-minute` (number) · …ding rather than equipment failure. In parallel, the checkout stack suffered a 96-minute payments degradation (10:12Z to 11:48Z) during the HDFC and ICICI flash-sale pe…
  - N06 · `10.3-percentage` (number) · …red dispatch SLA stands at **86.2% against the 96.5% contractual guarantee**, a 10.3-percentage-point shortfall. The root cause is therefore two-part: **inbound volume well b…
  - N07 · `11.5x` (number) · …llback latency spike from a 420ms baseline to 4,850ms**, an increase of roughly 11.5x. The failure mechanism was a timing mismatch: checkout orchestration retried sy…
  - N08 · `87.4%` (number) · …00Z**. The automated reversal batch cleared **2,980 of 3,410** duplicate holds (87.4%), leaving **430 high-value holds ($61,250)** requiring manual settlement-file r…
  - N09 · `18,800` (number) · …rystallizes if backlog age crosses 16 hours, and the arithmetic implies roughly 18,800 vouchers at that threshold. The payments incident adds a reputational dimension…
  - N10 · `87.4%` (number) · …t adds a reputational dimension: 3,410 customers saw duplicate holds, and while 87.4% are already reversed, any customer still holding funds on a high-value purchase…
  - N11 · `$374,580` (number) · …efore 04:00Z T+1 \| Manual reconciliation \| \| **Gross unmitigated exposure** \| **$374,580** \| \| \| \| Proposed containment spend \| $24,200 \| $14,400 fleet + $9,800 overtim…
  - N12 · `12.95` (number) · …reconciling $313,330 against $24,200, yielding **12.9x** ($313,330 ÷ $24,200 = 12.95). Including the $61,250 UPI holds raises gross exposure to $374,580 and the rat…
  - N13 · `$374,580` (number) · …30 ÷ $24,200 = 12.95). Including the $61,250 UPI holds raises gross exposure to $374,580 and the ratio to **15.5x**. The Board should be aware of this distinction. The…
  - N14 · `15.5x` (number) · …ding the $61,250 UPI holds raises gross exposure to $374,580 and the ratio to **15.5x**. The Board should be aware of this distinction. The UPI holds are temporary a…
  - N15 · `$12.95` (number) · …eturn. **Commentary.** Every dollar of the $24,200 spend is protecting roughly $12.95 of contractual loss. Even if containment only partially succeeds, the break-eve…
  - N16 · `3.2x` (number) · …threshold is low: preventing just the $77,330 surcharge alone would return over 3.2x. The two largest components, the rebate and vouchers, are probabilistic, so rea…
  - N17 · `12.95x` (number) · …\| $14,400 + $9,800 \| = $24,200 ✔ \| \| Mitigation ratio \| $313,330 ÷ $24,200 \| = 12.95x ✔ \| \| UPI holds cleared \| 2,980 ÷ 3,410 \| = 87.4% ✔ \| \| Remaining holds \| 3,410…
  - N18 · `87.4%` (number) · …tio \| $313,330 ÷ $24,200 \| = 12.95x ✔ \| \| UPI holds cleared \| 2,980 ÷ 3,410 \| = 87.4% ✔ \| \| Remaining holds \| 3,410 − 2,980 \| = 430 ✔ \| \| SLA gap, Bhiwandi \| 96.5% −…
  - N19 · `10.3` (number) · …ining holds \| 3,410 − 2,980 \| = 430 ✔ \| \| SLA gap, Bhiwandi \| 96.5% − 86.2% \| = 10.3 pts ✔ \| **Data caveats.** All figures reflect the 15:00Z snapshot. The $142,00…
- **brief-01 · `sonnet_templated`** — 0
- **brief-01 · `haiku_templated`** — 2
  - N01 · `5,000` (number) · …orter Lane 4 to manual pallet staging. - **Verification:** Staged backlog below 5,000 cages and Bhiwandi SLA attainment at or above 96.5% by 23:59Z. ### Meera Subra…
  - N02 · `17 Nov 2026` (date) · …Meera Subramanian, Principal SRE Checkout and Payments — Complete before 04:00Z 17 Nov 2026 T+1 settlement batch - **Milestone:** Manually settle the 430 remaining duplic…
- **brief-02 · `sonnet_unbounded`** — 15
  - N01 · `2.8` (number) · …t Assured \| Delta \| \|---\|---\|---\|---\| \| Delivery speed \| 4.1 days \| 1.3 days \| -2.8 days \| \| Return rate (benchmark cohort) \| 7.8% (AetherSonic); 7.4% (Sony/JBL co…
  - N02 · `$30.7155M` (number) · ….75% referral and $3.65 FBO. **Reconciliation note:** these four lines sum to **$30.7155M**, well above the **$18.0M** Year-1 inventory allocation and projected GMV in t…
  - N03 · `62%` (number) · …Q1 launch GMV (32,000 × $349) is a launch-quarter figure that would constitute ~62% of the $18M annual total. We recommend Finance confirm whether $18.0M represent…
  - N04 · `25bps` (number) · …nt's stated "150bps" request and "175bps" concession differ; NovaMart is giving 25bps more than the CFO's stated ask, which should be validated as intentional. ###…
  - N05 · `40bps` (number) · …return rates holding at or below **2.5%**, against a modeled 2.1%, leaving only 40bps of buffer. --- ## 4. Financial Exposure vs. Mitigation ROI Deep-Dive \| Item…
  - N06 · `$1,755,000` (number) · …\| Rolling, 90 days \| \| Base commission on $18M at 9.75% \| NovaMart revenue \| **$1,755,000** \| Computed \| **Commentary.** Commission revenue of ~$1.755M plus $480,000 in…
  - N07 · `$1.755M` (number) · …t revenue \| **$1,755,000** \| Computed \| **Commentary.** Commission revenue of ~$1.755M plus $480,000 in ads yields approximately **$2.235M**, or about **12.4%** of $1…
  - N08 · `$2.235M` (number) · …y.** Commission revenue of ~$1.755M plus $480,000 in ads yields approximately **$2.235M**, or about **12.4%** of $18M, consistent with the model's **12.42%** net take…
  - N09 · `12.4%` (number) · …e of ~$1.755M plus $480,000 in ads yields approximately **$2.235M**, or about **12.4%** of $18M, consistent with the model's **12.42%** net take rate. The $315,000 c…
  - N10 · `$165,000` (number) · …e $315,000 concession is therefore covered by the $480,000 ad commitment with **$165,000** of net cushion before FBO subsidy costs. The FBO subsidy is the unquantified…
  - N11 · `124,500` (number) · …subsidy costs. The FBO subsidy is the unquantified variable: at the schedule's 124,500 annual units, a $0.75 subsidy implies roughly **$93,375**, though unit volume d…
  - N12 · `$93,375` (number) · …able: at the schedule's 124,500 annual units, a $0.75 subsidy implies roughly **$93,375**, though unit volume depends on the GMV reconciliation flagged in Section 2.4.…
  - N13 · `$30.7M` (number) · …IN mismatches; establish the $250,000 rolling reserve; reconcile the $18.0M vs. $30.7M figures. - **Retail Media:** Configure 4.8x ROAS tracking and the 15% bonus-imp…
  - N14 · `$2.235M` (number) · …✔ \| \| Commission concession \| 175bps × $18M \| = $315,000 ✔ \| \| Net take rate \| ~$2.235M / $18M \| ≈ 12.42% ✔ \| \| UN38.3 status \| 26/28 uploaded \| 2 open ⚠ \| \| SKU sched…
  - N15 · `$30.7155M` (number) · …\| UN38.3 status \| 26/28 uploaded \| 2 open ⚠ \| \| SKU schedule total \| 4 lines \| $30.7155M vs. $18M ⚠ reconcile \| \| FBO tier \| $4.40 → $3.65 \| $0.75/unit ✔ \| \| Commission…
- **brief-02 · `sonnet_templated`** — 0
- **brief-02 · `haiku_templated`** — 1
  - N01 · `100%` (number) · …k the $3.65 FBO tier. - **Verification:** 65% safety stock confirmed at 4 hubs; 100% outbound serial scan capture ### Siddharth Rao (NovaMart VP Category Partnersh…
- **reg-01 · `sonnet_unbounded`** — 7
  - N01 · `04:20 IST` (time) · …IR thermal cameras detect temperature rise from 47°C to 118°C in 9 minutes \| \| ~04:20 IST \| Smoke/off-gas sensors trigger within 110 seconds of detection \| \| ~04:22 IST…
  - N02 · `04:22 IST` (time) · …~04:20 IST \| Smoke/off-gas sensors trigger within 110 seconds of detection \| \| ~04:22 IST \| Night-shift ERT completes isolation of the steel mesh pallet into the externa…
  - N03 · `$35,760` (number) · …e Nov 30, 2026 \| ### 4.2 Commentary Direct realized costs total approximately $35,760 ($4,860 + $12,400 + $18,500), with a further $58,220 booked as a refund reserve…
  - N04 · `$76,720` (number) · …8,220 booked as a refund reserve. Combined refund reserve and forensic testing ($76,720) are fully covered by the $184,000 frozen escrow, leaving $107,280 of surplus e…
  - N05 · `$107,280` (number) · …nsic testing ($76,720) are fully covered by the $184,000 frozen escrow, leaving $107,280 of surplus escrow headroom against additional statutory liability. Stated diffe…
  - N06 · `2.4` (number) · …d differently, the escrow covers the identified refund and forensic obligations 2.4 times over. The $42,000 FLIR capex is modest relative to the exposure it addre…
  - N07 · `23%` (number) · …ddresses. It is roughly 10% of one month's quarantined GMV ($412,000) and about 23% of the frozen escrow. A single uncontained thermal event at an under-screened s…
- **reg-01 · `sonnet_templated`** — 1
  - N01 · `$75,480` (number) · …s. Recall notices reached 1,420 customers. **Bottom line:** Direct costs total $75,480 against $184,000 frozen escrow; $412,000 monthly GMV quarantined; 548 recalled…
- **reg-01 · `haiku_templated`** — 2
  - N01 · `$75,480` (number) · ….4% have completed returns as of September 30. **Bottom line:** Q3 net cost of $75,480 with $184,000 escrow held as backstop; $412,000 monthly GMV quarantined. ## Ke…
  - N02 · `Q4` (identifier) · …al scan logged. ### NovaMart Legal and Seller Trust & Safety — Ongoing through Q4 FY2026 audit checkpoint - **Milestone:** Maintain $184,000 escrow hold, track…
- **reg-02 · `sonnet_unbounded`** — 5
  - N01 · `75.7%` (number) · …ion risk) \| 31 \| $1,030,000 \| 14.5% \| Roughly three-quarters of held balances (75.7% by share) were resolved within the contractual window, but nearly one quarter (…
  - N02 · `24.3%` (number) · …by share) were resolved within the contractual window, but nearly one quarter (24.3%) breached or approached breach, with $1.03 million sitting in the highest-risk…
  - N03 · `95` (number) · …ying the 65% target reduction to the 146 false-positive holds implies roughly **95 fewer erroneous holds** over a comparable period, with a corresponding reductio…
  - N04 · `$590,000` (number) · …primary cause. Over a four-quarter horizon, unmitigated exposure approximates **$590,000** (4 × $147,500). We note that precise implementation cost figures were not in…
  - N05 · `4` (number) · …e. Over a four-quarter horizon, unmitigated exposure approximates **$590,000** (4 × $147,500). We note that precise implementation cost figures were not include…
- **reg-02 · `sonnet_templated`** — 5
  - N01 · `Q1` (identifier) · …UBO and IBAN cases. ## Action Plan ### Engineering and Treasury Operations — Q1 2027 - **Milestone:** Deploy entity-resolution fuzzy canonicalizer normalizing…
  - N02 · `2027` (number) · …O and IBAN cases. ## Action Plan ### Engineering and Treasury Operations — Q1 2027 - **Milestone:** Deploy entity-resolution fuzzy canonicalizer normalizing lega…
  - N03 · `60` (number) · …te falls from 68.2% by targeted 65% reduction ### Treasury Operations — Within 60 days of committee approval - **Milestone:** Stand up a dedicated 12-hour fast-…
  - N04 · `Q1` (identifier) · …eding 72 hours ### Information Security — Ongoing, first quarterly attestation Q1 2027 - **Milestone:** Sustain zero-PII ticket vault with ingestion-level regex…
  - N05 · `2027` (number) · …ng 72 hours ### Information Security — Ongoing, first quarterly attestation Q1 2027 - **Milestone:** Sustain zero-PII ticket vault with ingestion-level regex mask…
- **reg-02 · `haiku_templated`** — 3
  - N01 · `30` (number) · …and GSTIN clustering blocks. ## Action Plan ### Payments Engineering — Within 30 days - **Milestone:** Deploy legal-suffix entity-resolution canonicalizer with…
  - N02 · `45` (number) · …least 65% from 68.2% baseline ### Treasury Operations and Compliance — Within 45 days - **Milestone:** Activate 12-hour SLA fast-lane for Platinum sellers with…
  - N03 · `60` (number) · …holds exceeding 72 hours ### Information Security and Privacy Office — Within 60 days - **Milestone:** Complete tokenized FIPS-140-3 KMS tax-document vault rol…

## Rubric scores (judge)

Mean (min–max) over repeats × bundles. Agreement = share of draft × dimension cells whose 3 repeat scores are all within 1 point.

| Rung | factual_accuracy | coverage | clarity | actionability | concision | Agreement (within 1) |
|---|---|---|---|---|---|---|
| `sonnet_unbounded` | 3.92 (3–4) | 4.92 (4–5) | 4.00 (4–4) | 3.75 (3–4) | 2.83 (2–3) | 20/20 |
| `sonnet_templated` | 3.08 (2–4) | 4.00 (4–4) | 4.92 (4–5) | 3.75 (3–5) | 4.17 (4–5) | 20/20 |
| `haiku_templated` | 2.58 (2–4) | 3.50 (3–4) | 4.42 (4–5) | 3.25 (3–4) | 4.08 (4–5) | 20/20 |

Overall inter-repeat agreement: 60/60 cells (100.0%).

### Per draft (scores by repeat)

| Draft | factual_accuracy | coverage | clarity | actionability | concision |
|---|---|---|---|---|---|
| brief-01|haiku_templated | 3.33 [3,4,3] | 3.00 [3,3,3] | 4.00 [4,4,4] | 3.00 [3,3,3] | 4.00 [4,4,4] |
| brief-01|sonnet_templated | 4.00 [4,4,4] | 4.00 [4,4,4] | 5.00 [5,5,5] | 4.33 [4,4,5] | 4.00 [4,4,4] |
| brief-01|sonnet_unbounded | 4.00 [4,4,4] | 5.00 [5,5,5] | 4.00 [4,4,4] | 4.00 [4,4,4] | 2.33 [2,3,2] |
| brief-02|haiku_templated | 2.00 [2,2,2] | 3.67 [4,4,3] | 4.00 [4,4,4] | 3.00 [3,3,3] | 4.00 [4,4,4] |
| brief-02|sonnet_templated | 3.33 [4,3,3] | 4.00 [4,4,4] | 4.67 [5,4,5] | 3.67 [4,3,4] | 4.67 [5,4,5] |
| brief-02|sonnet_unbounded | 4.00 [4,4,4] | 5.00 [5,5,5] | 4.00 [4,4,4] | 4.00 [4,4,4] | 3.00 [3,3,3] |
| reg-01|haiku_templated | 3.00 [3,3,3] | 3.33 [3,3,4] | 4.67 [5,4,5] | 4.00 [4,4,4] | 4.00 [4,4,4] |
| reg-01|sonnet_templated | 3.00 [3,3,3] | 4.00 [4,4,4] | 5.00 [5,5,5] | 4.00 [4,4,4] | 4.00 [4,4,4] |
| reg-01|sonnet_unbounded | 3.67 [3,4,4] | 4.67 [4,5,5] | 4.00 [4,4,4] | 4.00 [4,4,4] | 3.00 [3,3,3] |
| reg-02|haiku_templated | 2.00 [2,2,2] | 4.00 [4,4,4] | 5.00 [5,5,5] | 3.00 [3,3,3] | 4.33 [4,5,4] |
| reg-02|sonnet_templated | 2.00 [2,2,2] | 4.00 [4,4,4] | 5.00 [5,5,5] | 3.00 [3,3,3] | 4.00 [4,4,4] |
| reg-02|sonnet_unbounded | 4.00 [4,4,4] | 5.00 [5,5,5] | 4.00 [4,4,4] | 3.00 [3,3,3] | 3.00 [3,3,3] |

## Factual errors (judge; de-duplicated across repeats by claim-quote similarity)

| Rung | Drafts | Distinct errors | Material | Minor | Raw reports |
|---|---|---|---|---|---|
| `sonnet_unbounded` | 4 | 22 | 1 | 21 | 51 |
| `sonnet_templated` | 4 | 24 | 6 | 18 | 60 |
| `haiku_templated` | 4 | 28 | 10 | 18 | 69 |

| Draft | Repeats | Distinct | Material | Minor | Reported by 1 / 2 / 3 repeats |
|---|---|---|---|---|---|
| brief-01|haiku_templated | 3 | 7 | 2 | 5 | 3 / 0 / 4 |
| brief-01|sonnet_templated | 3 | 4 | 0 | 4 | 2 / 0 / 2 |
| brief-01|sonnet_unbounded | 3 | 6 | 0 | 6 | 1 / 2 / 3 |
| brief-02|haiku_templated | 3 | 8 | 5 | 3 | 1 / 3 / 4 |
| brief-02|sonnet_templated | 3 | 5 | 2 | 3 | 1 / 2 / 2 |
| brief-02|sonnet_unbounded | 3 | 4 | 0 | 4 | 3 / 0 / 1 |
| reg-01|haiku_templated | 3 | 8 | 1 | 7 | 3 / 0 / 5 |
| reg-01|sonnet_templated | 3 | 6 | 1 | 5 | 1 / 0 / 5 |
| reg-01|sonnet_unbounded | 3 | 6 | 1 | 5 | 0 / 3 / 3 |
| reg-02|haiku_templated | 3 | 5 | 2 | 3 | 1 / 0 / 4 |
| reg-02|sonnet_templated | 3 | 9 | 3 | 6 | 1 / 3 / 5 |
| reg-02|sonnet_unbounded | 3 | 6 | 0 | 6 | 1 / 0 / 5 |

**brief-01|haiku_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (2/3) | 3 | Staged backlog below 5,000 cages | The source sets no 5,000-cage threshold; this completion criterion is invented. | ABSENT | True / None |
| minor (0/1) | 1 | Bhiwandi SLA attainment at or above 96.5% by 23:59Z | The source sets no target of restoring 96.5% SLA by 23:59Z; the 23:59Z deadline applies only to clearing the backlog to avoid surcharges. | if we do not clear the 41,800 cage backlog before 23:59Z tonight | True / True |
| material (2/3) | 3 | file Schedule B surcharge waiver | No surcharge waiver filing is mentioned or agreed in the source, so this invents an obligation. | ABSENT | True / None |
| minor (0/3) | 3 | $24,200 containment spend neutralizes roughly $313,330 carrier, rebate, and voucher exposure | This overstates certainty: the $313,330 is risk exposure, and the board reconciliation the source asks for also includes the $61,250 un-reversed UPI holds, which the draft leaves out. | Reconcile total unmitigated exposure ($313,330 carrier/rebate/voucher + $61,250 un-reversed UPI holds) cleanly against $24,200 immediate containment spend | True / True |
| minor (0/3) | 3 | or face customer funds and reconciliation breaks | This consequence is an embellishment that the source does not state. | ABSENT | True / None |
| minor (0/1) | 1 | $1.85 per-parcel surcharges totaling $77,330 | The draft presents $77,330 as an incurred total, but the source describes it as conditional exposure that applies only if the backlog is not cleared by 23:59Z. | That exposes $77,330 in direct carrier surcharges if we do not clear the 41,800 cage backlog before 23:59Z tonight | True / True |
| minor (0/1) | 1 | 312 Gate-3-verified sellers face real dock queue losses and buyer escalations | The source says these sellers waited 4+ hours in queues; 'losses and buyer escalations' for these sellers is not stated. | 312 verified sellers waited 4+ hours in physical Gate 3 truck queues at Bhiwandi | True / True |

**brief-01|sonnet_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| minor (0/3) | 3 | Record Diwali GMV | The source never calls Day 3 GMV a record; it only says GMV was up 34% YoY against plan. | ABSENT | True / None |
| minor (0/3) | 3 | preserving SLA and rebate eligibility | The source does not state that the containment spend will preserve SLA or rebate eligibility; the draft presents a hoped-for outcome as fact. | ABSENT | True / None |
| minor (0/1) | 1 | 47 audits completed | The source specifies placing sellers on a mandatory 7-day audit, not completing all 47 audits within the 7-day window. | placing 47 zero-inventory phantom-manifest sellers on mandatory 7-day inventory audit | True / True |
| minor (0/1) | 1 | P1 tickets surged 210%. | This omits that the +210% is measured above forecast, not as an absolute surge. | inbound P1 tickets spiked +210% above forecast (11,400 incremental tickets in 6 hours) | True / True |

**brief-01|sonnet_unbounded**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| minor (0/3) | 3 | preventing just the $77,330 surcharge alone would return over 3.2x | $77,330 ÷ $24,200 = 3.195x, which is just under 3.2x, not over it. | "unmitigated_carrier_surcharge_usd": 77330 | True / True |
| minor (0/3) | 3 | Hoskote (94.1%) and Tauru (95.8%) also sit below the 96.5% target, though the shortfall is modest and attributable to dock crowding rather than equipment failure. | The source attributes dock crowding only to Hoskote and gives no cause for Tauru's shortfall. | Hoskote South is tight at 94.1% due to dock crowding, and Tauru North is operating at 95.8%. | True / True |
| minor (0/3) | 3 | **Prepared by:** Office of the VP Chief-of-Staff | The author and office are invented; the source names no preparer. | ABSENT | True / None |
| minor (0/2) | 2 | **Distribution:** CEO, CFO, Board Operations Committee | The source mentions a CEO and CFO readout but no Board Operations Committee. | ABSENT | True / None |
| minor (0/2) | 2 | The Bhiwandi backlog (41,800 staged cages) carries time-bound contractual exposure of **$313,330**, which can be largely avoided if the backlog clears before 23:59Z tonight. | Misframes the exposure: $313,330 includes the $94,000 voucher risk, which is not contractual, and the $142,000 weekly rebate risk, which is not tied to the 23:59Z deadline (only the $77,330 surcharge is). | That exposes $77,330 in direct carrier surcharges if we do not clear the 41,800 cage backlog before 23:59Z tonight, plus an estimated $142,000 rebate forfeiture risk for Week 46 if Western Zone on-time-tender falls below 92.0%. | True / True |
| minor (0/1) | 1 | **Owner: Divya Nair.** Issue automated LDP waivers for the 312 Gate-3-verified sellers | The source names no owners for the actions (it references Compliance for the seller audit), so the named owners are inferred by role but presented as assigned. | Our badge telemetry shows dock-in timestamps so Compliance can isolate genuine carrier/hub queues from seller stockouts. | True / True |

**brief-02|haiku_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (2/2) | 2 | Pre-position 65% of launch safety stock across Bhiwandi, Dankuni, Hoskote, and Tauru hubs | The draft assigns pre-positioning of safety stock to NovaMart's Tarun Kapoor, but the source makes it AetherSonic's condition for the $3.65 tier. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs | True / True |
| material (3/3) | 3 | Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect) — Before January 10, 2027 | The source gives no January 10 deadline for stock pre-positioning or scanner deployment; the January 10 date applies only to Brand Registry enrollment. | ABSENT | True / None |
| material (2/3) | 3 | Complete pending lab signoff for the 2 SKUs before January 10, 2027 catalog gate | The source sets no January 10 deadline for UN38.3 lab signoff; the draft invents it. | ABSENT | True / None |
| material (3/4) | 3 | Clear 2 pending UN38.3 lab signoffs and validate KYC/TIN records to approve T+3 settlement | The source does not assign this work to Nadia Jenkins, and it says T+3 needs Director approval (per Treasury), not approval by AetherSonic's CFO. | Treasury notes T+3 requires Director approval plus zero unresolved KYC/TIN mismatches. | True / True |
| minor (0/1) | 1 | secure signed AetherSonic distributor tokens before StudioPulse X2 ASIN attachment | The draft misstates the token mechanism: in the source, tokens gate third-party offers at ingestion rather than being something NovaMart secures before attaching the ASIN. | Any third-party offer attempting to attach to StudioPulse X2 or ANC-Pro ASINs without a digitally signed AetherSonic Authorized Distributor Token will be auto-rejected at ingestion | True / True |
| minor (0/3) | 3 | Return rate drops from 7.4% to 2.1% | The 7.4% figure is the transit-crush return rate in the Sony/JBL benchmark cohort, not AetherSonic's return rate, which is 7.8%. | cut transit crush returns from 7.4% down to 2.1% | True / True |
| minor (0/2) | 2 | Net Year-1 commitment of $18.0M GMV against roughly $315k commission concession and $480k co-op spend. | This frames AetherSonic's $480k co-op commitment as a cost on the same side as NovaMart's concession, and it omits the $0.75/unit FBO subsidy from the tradeoff the source specifies. | 175bps commission concession + $0.75/unit FBO subsidy vs. $480k guaranteed Co-Op spend + $18M Year-1 exclusive launch allocation | True / True |
| material (1/2) | 2 | Siddharth Rao (NovaMart VP Category Partnerships) — By January 10, 2027 | The source assigns Brand Registry Lock enrollment to NovaMart Catalog Engineering, not to Siddharth Rao. | NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027. | True / True |

**brief-02|sonnet_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (1/1) | 1 | pre-position 65% of safety stock before launch | Pre-positioning 65% of safety stock is AetherSonic's condition for the $3.65 fee, but the draft assigns it to NovaMart's Tarun Kapoor as his milestone. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs | True / True |
| minor (0/3) | 3 | audit MAP compliance every 14 days at QBRs | QBRs occur at Day 30, 60 and 90; the source describes a 14-day audit window, not a 14-day audit cadence at QBRs. | Quarterly Business Reviews (QBRs) scheduled Day 30, Day 60, and Day 90 post-launch will audit net ROAS against the 4.8x target, monitor 14-day grey-market MAP compliance | True / True |
| minor (0/2) | 2 | Returns fall from 7.8% to 2.1% | This presents a benchmark comparison (the competitor rate against the Sony/JBL overbox cohort) as a committed outcome for AetherSonic. | "benchmark_return_rate_pct": {"current_competitor": 7.8, "novamart_overbox_cohort": 2.1} | True / True |
| minor (1/3) | 3 | Siddharth Rao and Nadia Jenkins — Sign-off pre-launch; QBRs Days 30/60/90 | The source assigns no owner for running the QBRs, so naming these two as owners is unsupported. | ABSENT | True / None |
| material (2/2) | 2 | Tarun Kapoor, NovaMart FBO Supply Chain — Before February 15, 2027 go-live | The draft makes Tarun the owner of pre-positioning 65% of safety stock, but that is AetherSonic's condition for the $3.65 tier; the source names no owner for deploying serial scanning. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs | True / True |

**brief-02|sonnet_unbounded**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| minor (0/3) | 3 | **Prepared by:** Office of the VP Chief-of-Staff, NovaMart Enterprise \| **Audience:** AetherSonic Executive Sign-Off / NovaMart Board | The preparer and the NovaMart Board audience are invented; the source names only AetherSonic Executive Sign-Off as the reader and lists no such preparer. | ABSENT | True / None |
| minor (0/1) | 1 | all before the **February 15** go-live | The source sets a deadline only for Brand Registry Lock (January 10); applying February 15 to the other closure gates is the draft's own inference, presented as fact. | ABSENT | True / None |
| minor (0/1) | 1 | whose downside is loss of exclusivity and the associated allocation | The source grants only a 30-day exclusivity unwind right and does not say the $18M allocation is forfeited. | AetherSonic holds a 30-day exclusivity unwind right. | True / True |
| minor (0/1) | 1 | and damaging price integrity across the line | This embellishes the source, which ties MAP erosion specifically to the flagship ANC-Pro Over-Ear headphones. | eroding flagship ANC-Pro Over-Ear headphones ($299 MSRP) | True / True |

**reg-01|haiku_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (3/3) | 3 | Facility Engineering and Fulfillment Operations — By November 30, 2026 | The draft assigns the FLIR rollout to a named owner the source never mentions; the source attributes the commitments only to 'Management'. | Management commits to closing all 548 open customer recall returns | True / True |
| minor (0/3) | 3 | NovaMart Legal and Seller Trust & Safety — Ongoing through Q4 FY2026 audit checkpoint | The 'Seller Trust & Safety' owner and the 'Q4 FY2026' checkpoint timing are not in the source. | ABSENT | True / None |
| minor (0/3) | 3 | conduct operator certification for inbound lithium carton screening | Operator certification is an invented commitment; the source commits only to deploying the FLIR cameras. | deploying FLIR handheld imaging across all remaining 10 Tier-2 regional sortation spokes ($42,000 approved capex) by November 30, 2026 | True / True |
| minor (0/3) | 3 | dispatch prepaid hazardous-return kits to unresponsive buyers before the deadline | The source's closure commitment is escalated SMS and IVR follow-ups; dispatching kits to unresponsive buyers is an added commitment. | closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026 | True / True |
| minor (0/3) | 3 | expose NovaMart to statutory dangerous-goods penalties | The source states no penalty exposure and classifies the event as having zero passenger-aircraft uplift exposure. | zero passenger-aircraft Uplift Exposure (intercepted at inbound FC dock prior to carrier handoff) | True / True |
| minor (0/1) | 1 | *Source: Section A forensic findings* | The 114 blocked air shipments come from the Section C telemetry, not the Section A forensic findings. | "blocked_undeclared_air_shipments_sept": 114 | True / True |
| minor (0/1) | 1 | Marketplace Safety & Fulfillment Compliance Office | This misnames the preparing office and assigns it the recall commitment, which the source attributes only to management. | NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office | True / True |
| minor (0/1) | 1 | Q3 net cost of $75,480 | Labelling this 'net' cost is misleading: it includes the refund reserve that is backstopped by escrow and excludes the $18,500 forensic testing. | retaining $184,000 in terminated seller escrow accounts to backstop 100% of buyer recall refunds ($58,220 reserve) and third-party forensic testing ($18,500) | True / True |

**reg-01|sonnet_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (6/6) | 3 | Customer Safety Operations — By November 15, 2026 | The source assigns these commitments to 'Management' and names no accountable team, so this owner is invented. | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026 | True / True |
| minor (0/3) | 3 | Marketplace Trust & Legal — Ongoing; review at next quarterly audit | The combined owner and the quarterly review cadence are invented; the source cites NovaMart Legal only for a completed referral. | ABSENT | True / None |
| minor (0/3) | 3 | referral status reported quarterly | The source contains no commitment to report the referral status quarterly. | ABSENT | True / None |
| minor (0/1) | 1 | Forensics found forged BIS documents | The forged certificate was a document uploaded at onboarding and identified separately; the TUV tear-down found the undeclared cells, not the forgery. | Seller uploaded a forged BIS IS 16046 safety certificate PDF during April 2026 onboarding | True / True |
| minor (0/3) | 3 | using a forged BIS certificate; 114 undeclared air shipments were blocked in September | The fleet-wide count of 114 blocked shipments comes from the quarterly routing audit, but here it is placed so that it reads as attributable to seller SLR-77401. | "blocked_undeclared_air_shipments_sept": 114 | True / True |
| minor (0/3) | 3 | leaving 548 units unreturned in homes | 'In homes' is an unsupported embellishment; the source gives only the count of open, unreturned units. | "open_recall_unreturned_units": 548 | True / True |

**reg-01|sonnet_unbounded**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| minor (1/3) | 3 | HAZ-PNQ-9921 (154 intact units destroyed) | The source says the 154 units were moved into destruction custody, not that they were destroyed. | have been moved to certified hazardous-waste destruction custody under Chain-of-Custody Manifest HAZ-PNQ-9921 | True / True |
| minor (1/3) | 3 | \| Trust, Safety & Fulfillment Compliance \| Close all 548 open recall returns | Team-level owners (Trust, Safety & Fulfillment Compliance; Fulfillment Operations / Capex; Seller Operations; Logistics / TMS) are invented, because the source assigns commitments only to management. | Management commits to closing all 548 open customer recall returns | True / True |
| material (2/3) | 3 | Maintain $58,220 recall reserve; report quarterly on escrow utilization | The quarterly escrow-utilization reporting commitment, and Finance as its owner, are not in the source. | ABSENT | True / None |
| minor (0/2) | 2 | no exposure of any carrier or passenger aircraft | The source states zero passenger-aircraft uplift exposure only; extending this to 'any carrier' is an embellishment. | zero passenger-aircraft Uplift Exposure (intercepted at inbound FC dock prior to carrier handoff) | True / True |
| minor (0/2) | 2 | are effective but resource-intensive | The source gives no assessment that these controls are effective or resource-intensive. | ABSENT | True / None |
| minor (0/2) | 2 | prompt self-reporting | The source does not characterise the filing or notification as prompt self-reporting. | ABSENT | True / None |

**reg-02|haiku_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (3/3) | 3 | Payments Engineering — Within 30 days | The 30-day deadline is invented, and the source gives no owner for the canonicalizer milestone. | ABSENT | True / None |
| material (6/6) | 3 | Treasury Operations and Compliance — Within 45 days | The 45-day deadline for the fast-lane is invented; the source sets no timeframe. | ABSENT | True / None |
| minor (0/3) | 3 | quarterly audit of CRM and ticketing replicas for residual SSN, PAN, and card strings | No recurring quarterly replica audit is committed in the source; Information Security audited the replicas once and purged them. | ABSENT | True / None |
| minor (0/3) | 3 | zero holds exceeding 72 hours | This completion criterion is not stated anywhere in the source. | ABSENT | True / None |
| minor (0/1) | 1 | with zero-PII verification audits | The source's mitigation does not include verification audits. | ABSENT | True / None |

**reg-02|sonnet_templated**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| material (3/3) | 3 | Engineering and Treasury Operations — Q1 2027 | The source gives no deadline for the canonicalizer deployment, so the Q1 2027 timing is invented. | ABSENT | True / None |
| material (3/3) | 3 | Within 60 days of committee approval | The source sets no 60-day deadline for the fast-lane, and no Treasury Operations commitment to one. | ABSENT | True / None |
| material (3/3) | 3 | Ongoing, first quarterly attestation Q1 2027 | The source contains neither the Q1 2027 attestation date nor a quarterly reporting commitment. | ABSENT | True / None |
| minor (0/3) | 3 | while retaining hard holds and enhanced due diligence for stale UBO and IBAN cases | The source plans no hard-hold or enhanced due diligence control for these cases. | ABSENT | True / None |
| minor (0/3) | 3 | eliminating holds beyond 72 hours and arbitration pre-notices | The source attaches no such outcome to the fast-lane control. | ABSENT | True / None |
| minor (0/1) | 1 | False-positive hold rate falls from 68.2% by targeted 65% reduction | The source targets a 65% cut in the number of false-positive 409 holds, not in the false-positive rate. | to cut false-positive 409 holds by 65% before hold activation | True / True |
| minor (0/2) | 2 | reporting quarterly to the Board Risk and Audit Committee | No quarterly reporting commitment appears in the source. | ABSENT | True / None |
| minor (0/2) | 2 | creating regulatory and breach liability across downstream CRM replicas | This implies ongoing exposure, but the source says every historical raw token was purged within 72 hours; that remediation is omitted. | Every historical raw token was purged within 72 hours using deterministic pattern scanners | True / True |
| minor (0/2) | 2 | Median review hours at or below 48; zero holds exceeding 72 hours | This verification criterion is invented; the source sets no such target for the fast-lane. | ABSENT | True / None |

**reg-02|sonnet_unbounded**

| Severity (material votes / reports) | Repeats | Claim (draft) | Problem | Source quote | Quote found in draft / source |
|---|---|---|---|---|---|
| minor (0/3) | 3 | Roughly three-quarters of held balances (75.7% by share) were resolved within the contractual window | 75.7% is the share of held accounts, not of held balances (by dollars it is $3.11M of $4.82M, about 64.5%), and the source does not say these holds were resolved. | {"bucket": "0–24h (Within Target SLA)", "account_count": 108, "held_usd": 1920000, "share_pct": 50.5} | True / True |
| minor (0/3) | 3 | **Prepared By:** Office of the Chief Compliance & Regulatory Counsel | The source names no preparing office, so this authorship is invented. | ABSENT | True / None |
| minor (0/3) | 3 | **Classification:** Statutory Filing, Suitable for External Distribution | The source assigns no document classification or distribution status, so this is invented. | ABSENT | True / None |
| minor (0/3) | 3 | Eliminates a majority of >72h breaches | The source gives no projected effect for the fast lane on breaches longer than 72 hours. | ABSENT | True / None |
| minor (0/3) | 3 | dilutes analyst attention on real threats | This embellishes the Treasury acknowledgement, which mentions only avoidable arbitration liability. | creates avoidable Section 14.3 commercial arbitration liability | True / True |
| minor (0/1) | 1 | Move accounts into the 0–24h bucket | The source sets no 0–24h aging target for these controls. | ABSENT | True / None |

## Pairwise preference (judge)

24 ok calls. Each cell = wins of the row rung over the column rung, counting both presentation orders.

### overall

| Row beats column | `sonnet_unbounded` | `sonnet_templated` | `haiku_templated` |
|---|---|---|---|
| `sonnet_unbounded` | – | 8 | 8 |
| `sonnet_templated` | 0 | – | 7 |
| `haiku_templated` | 0 | 1 | – |

Ties: sonnet_unbounded vs sonnet_templated 0, sonnet_unbounded vs haiku_templated 0, sonnet_templated vs haiku_templated 0

Position consistency: 11/12 bundle × pair cells pick the same rung (or tie) in both orders (91.7%). Decisive calls choosing position A: 45.8% of 24.
- inconsistent: reg-02 sonnet_templated vs haiku_templated — fwd → haiku_templated, rev → sonnet_templated

| Bundle | sonnet_unbounded vs sonnet_templated | sonnet_unbounded vs haiku_templated | sonnet_templated vs haiku_templated |
|---|---|---|---|
| brief-01 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| brief-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| reg-01 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| reg-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd haiku_templated · rev sonnet_templated |

### accuracy

| Row beats column | `sonnet_unbounded` | `sonnet_templated` | `haiku_templated` |
|---|---|---|---|
| `sonnet_unbounded` | – | 7 | 8 |
| `sonnet_templated` | 1 | – | 7 |
| `haiku_templated` | 0 | 0 | – |

Ties: sonnet_unbounded vs sonnet_templated 0, sonnet_unbounded vs haiku_templated 0, sonnet_templated vs haiku_templated 1

Position consistency: 10/12 bundle × pair cells pick the same rung (or tie) in both orders (83.3%). Decisive calls choosing position A: 43.5% of 23.
- inconsistent: brief-01 sonnet_unbounded vs sonnet_templated — fwd → sonnet_templated, rev → sonnet_unbounded
- inconsistent: reg-02 sonnet_templated vs haiku_templated — fwd → tie, rev → sonnet_templated

| Bundle | sonnet_unbounded vs sonnet_templated | sonnet_unbounded vs haiku_templated | sonnet_templated vs haiku_templated |
|---|---|---|---|
| brief-01 | fwd sonnet_templated · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| brief-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| reg-01 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| reg-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd tie · rev sonnet_templated |

### usefulness_to_reader

| Row beats column | `sonnet_unbounded` | `sonnet_templated` | `haiku_templated` |
|---|---|---|---|
| `sonnet_unbounded` | – | 8 | 8 |
| `sonnet_templated` | 0 | – | 6 |
| `haiku_templated` | 0 | 2 | – |

Ties: sonnet_unbounded vs sonnet_templated 0, sonnet_unbounded vs haiku_templated 0, sonnet_templated vs haiku_templated 0

Position consistency: 10/12 bundle × pair cells pick the same rung (or tie) in both orders (83.3%). Decisive calls choosing position A: 41.7% of 24.
- inconsistent: reg-01 sonnet_templated vs haiku_templated — fwd → haiku_templated, rev → sonnet_templated
- inconsistent: reg-02 sonnet_templated vs haiku_templated — fwd → haiku_templated, rev → sonnet_templated

| Bundle | sonnet_unbounded vs sonnet_templated | sonnet_unbounded vs haiku_templated | sonnet_templated vs haiku_templated |
|---|---|---|---|
| brief-01 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| brief-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_templated · rev sonnet_templated |
| reg-01 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd haiku_templated · rev sonnet_templated |
| reg-02 | fwd sonnet_unbounded · rev sonnet_unbounded | fwd sonnet_unbounded · rev sonnet_unbounded | fwd haiku_templated · rev sonnet_templated |

## For lead review

### Material factual errors (17)

- **brief-01|haiku_templated** (reported by 3 repeat(s), material 2/3)
  - Draft: "Staged backlog below 5,000 cages" (found in draft: True)
  - Problem: The source sets no 5,000-cage threshold; this completion criterion is invented.
  - Source: "ABSENT" (found in source: None)
- **brief-01|haiku_templated** (reported by 3 repeat(s), material 2/3)
  - Draft: "file Schedule B surcharge waiver" (found in draft: True)
  - Problem: No surcharge waiver filing is mentioned or agreed in the source, so this invents an obligation.
  - Source: "ABSENT" (found in source: None)
- **brief-02|haiku_templated** (reported by 2 repeat(s), material 2/2)
  - Draft: "Pre-position 65% of launch safety stock across Bhiwandi, Dankuni, Hoskote, and Tauru hubs" (found in draft: True)
  - Problem: The draft assigns pre-positioning of safety stock to NovaMart's Tarun Kapoor, but the source makes it AetherSonic's condition for the $3.65 tier.
  - Source: "provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs" (found in source: True)
- **brief-02|haiku_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect) — Before January 10, 2027" (found in draft: True)
  - Problem: The source gives no January 10 deadline for stock pre-positioning or scanner deployment; the January 10 date applies only to Brand Registry enrollment.
  - Source: "ABSENT" (found in source: None)
- **brief-02|haiku_templated** (reported by 3 repeat(s), material 2/3)
  - Draft: "Complete pending lab signoff for the 2 SKUs before January 10, 2027 catalog gate" (found in draft: True)
  - Problem: The source sets no January 10 deadline for UN38.3 lab signoff; the draft invents it.
  - Source: "ABSENT" (found in source: None)
- **brief-02|haiku_templated** (reported by 3 repeat(s), material 3/4)
  - Draft: "Clear 2 pending UN38.3 lab signoffs and validate KYC/TIN records to approve T+3 settlement" (found in draft: True)
  - Problem: The source does not assign this work to Nadia Jenkins, and it says T+3 needs Director approval (per Treasury), not approval by AetherSonic's CFO.
  - Source: "Treasury notes T+3 requires Director approval plus zero unresolved KYC/TIN mismatches." (found in source: True)
- **brief-02|haiku_templated** (reported by 2 repeat(s), material 1/2)
  - Draft: "Siddharth Rao (NovaMart VP Category Partnerships) — By January 10, 2027" (found in draft: True)
  - Problem: The source assigns Brand Registry Lock enrollment to NovaMart Catalog Engineering, not to Siddharth Rao.
  - Source: "NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027." (found in source: True)
- **brief-02|sonnet_templated** (reported by 1 repeat(s), material 1/1)
  - Draft: "pre-position 65% of safety stock before launch" (found in draft: True)
  - Problem: Pre-positioning 65% of safety stock is AetherSonic's condition for the $3.65 fee, but the draft assigns it to NovaMart's Tarun Kapoor as his milestone.
  - Source: "provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs" (found in source: True)
- **brief-02|sonnet_templated** (reported by 2 repeat(s), material 2/2)
  - Draft: "Tarun Kapoor, NovaMart FBO Supply Chain — Before February 15, 2027 go-live" (found in draft: True)
  - Problem: The draft makes Tarun the owner of pre-positioning 65% of safety stock, but that is AetherSonic's condition for the $3.65 tier; the source names no owner for deploying serial scanning.
  - Source: "provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs" (found in source: True)
- **reg-01|haiku_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Facility Engineering and Fulfillment Operations — By November 30, 2026" (found in draft: True)
  - Problem: The draft assigns the FLIR rollout to a named owner the source never mentions; the source attributes the commitments only to 'Management'.
  - Source: "Management commits to closing all 548 open customer recall returns" (found in source: True)
- **reg-01|sonnet_templated** (reported by 3 repeat(s), material 6/6)
  - Draft: "Customer Safety Operations — By November 15, 2026" (found in draft: True)
  - Problem: The source assigns these commitments to 'Management' and names no accountable team, so this owner is invented.
  - Source: "Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026" (found in source: True)
- **reg-01|sonnet_unbounded** (reported by 3 repeat(s), material 2/3)
  - Draft: "Maintain $58,220 recall reserve; report quarterly on escrow utilization" (found in draft: True)
  - Problem: The quarterly escrow-utilization reporting commitment, and Finance as its owner, are not in the source.
  - Source: "ABSENT" (found in source: None)
- **reg-02|haiku_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Payments Engineering — Within 30 days" (found in draft: True)
  - Problem: The 30-day deadline is invented, and the source gives no owner for the canonicalizer milestone.
  - Source: "ABSENT" (found in source: None)
- **reg-02|haiku_templated** (reported by 3 repeat(s), material 6/6)
  - Draft: "Treasury Operations and Compliance — Within 45 days" (found in draft: True)
  - Problem: The 45-day deadline for the fast-lane is invented; the source sets no timeframe.
  - Source: "ABSENT" (found in source: None)
- **reg-02|sonnet_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Engineering and Treasury Operations — Q1 2027" (found in draft: True)
  - Problem: The source gives no deadline for the canonicalizer deployment, so the Q1 2027 timing is invented.
  - Source: "ABSENT" (found in source: None)
- **reg-02|sonnet_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Within 60 days of committee approval" (found in draft: True)
  - Problem: The source sets no 60-day deadline for the fast-lane, and no Treasury Operations commitment to one.
  - Source: "ABSENT" (found in source: None)
- **reg-02|sonnet_templated** (reported by 3 repeat(s), material 3/3)
  - Draft: "Ongoing, first quarterly attestation Q1 2027" (found in draft: True)
  - Problem: The source contains neither the Q1 2027 attestation date nor a quarterly reporting commitment.
  - Source: "ABSENT" (found in source: None)

### Numbers judged derived_incorrect / not_in_source_unverifiable by any repeat (13)

- **brief-01|haiku_templated** N01 `5,000` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …orter Lane 4 to manual pallet staging. - **Verification:** Staged backlog below 5,000 cages and Bhiwandi SLA attainment at or above 96.5% by 23:59Z. ### Meera Subra…
  - r0: The source gives no 5,000-cage threshold.
  - r1: The source contains no 5,000-cage backlog target.
  - r2: No 5,000-cage backlog threshold exists in the source; the target there is clearing the 41,800-cage backlog.
- **brief-01|sonnet_unbounded** N16 `3.2x` — majority derived_incorrect; verdicts ['derived_incorrect', 'derived_incorrect', 'derived_incorrect']
  - Context: …threshold is low: preventing just the $77,330 surcharge alone would return over 3.2x. The two largest components, the rebate and vouchers, are probabilistic, so rea…
  - r0: 77,330 / 24,200 = 3.195, which is not over 3.2x.
  - r1: 77,330 / 24,200 = 3.195x, which is just under 3.2x, not over it
  - r2: 77,330 / 24,200 = 3.195, which is not over 3.2x
- **brief-02|haiku_templated** N01 `100%` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …k the $3.65 FBO tier. - **Verification:** 65% safety stock confirmed at 4 hubs; 100% outbound serial scan capture ### Siddharth Rao (NovaMart VP Category Partnersh…
  - r0: The source requires serial pairing before carrier handoff but states no 100% capture metric; the draft invented this criterion.
  - r1: The source says scanners 'must pair' serials before handoff but states no 100% capture target; the draft set this completion criterion itself.
  - r2: The source requires serial pairing before carrier handoff, but no 100% capture metric is stated; it is a completion criterion the draft introduced.
- **reg-01|haiku_templated** N02 `Q4` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …al scan logged. ### NovaMart Legal and Seller Trust & Safety — Ongoing through Q4 FY2026 audit checkpoint - **Milestone:** Maintain $184,000 escrow hold, track…
  - r0: The source names a next audit checkpoint but gives no Q4 timing.
  - r1: The source names no Q4 FY2026 audit checkpoint.
  - r2: The source says 'Next Audit Checkpoint' with no quarter specified.
- **reg-01|sonnet_unbounded** N02 `04:22 IST` — majority derived_correct; verdicts ['not_in_source_unverifiable', 'derived_correct', 'derived_correct']
  - Context: …~04:20 IST \| Smoke/off-gas sensors trigger within 110 seconds of detection \| \| ~04:22 IST \| Night-shift ERT completes isolation of the steel mesh pallet into the externa…
  - r0: The source does not say when the 4 min 20 s isolation clock starts; from detection it would be 04:22:20, but from the sensor trigger it would be about 04:24.
  - r1: 04:18 + 4 min 20 s = 04:22:20, which is about 04:22.
  - r2: 04:18 + 4 min 20 s = 04:22:20, approximately 04:22.
- **reg-02|haiku_templated** N01 `30` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …and GSTIN clustering blocks. ## Action Plan ### Payments Engineering — Within 30 days - **Milestone:** Deploy legal-suffix entity-resolution canonicalizer with…
  - r0: The source gives no deadline for the canonicalizer deployment.
  - r1: The source gives no 30-day deadline for any milestone.
  - r2: The source gives no 30-day deadline for any milestone.
- **reg-02|haiku_templated** N02 `45` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …least 65% from 68.2% baseline ### Treasury Operations and Compliance — Within 45 days - **Milestone:** Activate 12-hour SLA fast-lane for Platinum sellers with…
  - r0: The source gives no deadline for the fast-lane.
  - r1: The source gives no 45-day deadline for any milestone.
  - r2: The source gives no 45-day deadline for any milestone.
- **reg-02|haiku_templated** N03 `60` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …holds exceeding 72 hours ### Information Security and Privacy Office — Within 60 days - **Milestone:** Complete tokenized FIPS-140-3 KMS tax-document vault rol…
  - r0: The source gives no deadline for the vault rollout.
  - r1: The source gives no 60-day deadline for any milestone.
  - r2: The source gives no 60-day deadline for any milestone.
- **reg-02|sonnet_templated** N01 `Q1` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …UBO and IBAN cases. ## Action Plan ### Engineering and Treasury Operations — Q1 2027 - **Milestone:** Deploy entity-resolution fuzzy canonicalizer normalizing…
  - r0: The source gives no milestone dates.
  - r1: The source gives no milestone dates.
  - r2: The source gives no milestone dates.
- **reg-02|sonnet_templated** N02 `2027` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …O and IBAN cases. ## Action Plan ### Engineering and Treasury Operations — Q1 2027 - **Milestone:** Deploy entity-resolution fuzzy canonicalizer normalizing lega…
  - r0: The source gives no milestone dates.
  - r1: The source gives no 2027 deadline.
  - r2: The source gives no 2027 deadline.
- **reg-02|sonnet_templated** N03 `60` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …te falls from 68.2% by targeted 65% reduction ### Treasury Operations — Within 60 days of committee approval - **Milestone:** Stand up a dedicated 12-hour fast-…
  - r0: The source has no 60-day timeline.
  - r1: The source gives no 60-day window.
  - r2: The source gives no 60-day window.
- **reg-02|sonnet_templated** N04 `Q1` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …eding 72 hours ### Information Security — Ongoing, first quarterly attestation Q1 2027 - **Milestone:** Sustain zero-PII ticket vault with ingestion-level regex…
  - r0: The source has no attestation date.
  - r1: The source gives no attestation schedule.
  - r2: The source gives no attestation date.
- **reg-02|sonnet_templated** N05 `2027` — majority not_in_source_unverifiable; verdicts ['not_in_source_unverifiable', 'not_in_source_unverifiable', 'not_in_source_unverifiable']
  - Context: …ng 72 hours ### Information Security — Ongoing, first quarterly attestation Q1 2027 - **Milestone:** Sustain zero-PII ticket vault with ingestion-level regex mask…
  - r0: The source has no attestation date.
  - r1: The source gives no 2027 date.
  - r2: The source gives no 2027 date.

## Per-fact hits across rungs

| Fact | Bundle | Tier | Category | `sonnet_unbounded` | `sonnet_templated` | `haiku_templated` | Flag |
|---|---|---|---|---|---|---|---|
| `b1-sla-bhiwandi-86-2` | brief-01 | core | metric | ✓ | ✓ | ✓ |  |
| `b1-backlog-41800` | brief-01 | core | metric | ✓ | ✓ | ✓ |  |
| `b1-exposure-313330` | brief-01 | core | money | ✓ | ✓ | ✓ |  |
| `b1-upi-holds-61250` | brief-01 | core | money | ✓ | ✓ | ✓ |  |
| `b1-containment-24200` | brief-01 | core | money | ✓ | ✓ | ✓ |  |
| `b1-deadline-2359z` | brief-01 | core | deadline | ✓ | ✓ | ✓ |  |
| `b1-deadline-upi-t1` | brief-01 | core | deadline | ✓ | ✓ | ✓ |  |
| `b1-decision-ldp-312-only` | brief-01 | core | decision | ✓ | ✓ | ✓ |  |
| `b1-gmv-38-4m` | brief-01 | detail | metric | ✓ | ✓ | ✓ |  |
| `b1-cause-sorter-lane-4` | brief-01 | detail | cause | ✓ | ✓ | ✓ |  |
| `b1-cause-upi-timeout` | brief-01 | detail | cause | ✓ | ✓ | ✓ |  |
| `b1-carrier-surcharge-77330` | brief-01 | detail | money | ✓ | ✓ | ✓ |  |
| `b1-rebate-142000` | brief-01 | detail | money | ✓ | ✓ | ✓ |  |
| `b1-voucher-94000` | brief-01 | detail | money | ✓ | ✓ | ✗ |  |
| `b1-bluedart-14400` | brief-01 | detail | decision | ✓ | ✓ | ✓ |  |
| `b1-phantom-47-audit` | brief-01 | detail | decision | ✓ | ✓ | ✓ |  |
| `b1-ratio-12-9x` | brief-01 | detail | metric | ✓ | ✗ | ✓ |  |
| `b1-owner-ananya` | brief-01 | detail | owner | ✓ | ✓ | ✗ |  |
| `b2-allocation-18m` | brief-02 | core | money | ✓ | ✓ | ✓ |  |
| `b2-commission-9-75` | brief-02 | core | decision | ✓ | ✓ | ✓ |  |
| `b2-fbo-3-65` | brief-02 | core | decision | ✓ | ✓ | ✓ |  |
| `b2-coop-480k` | brief-02 | core | money | ✓ | ✓ | ✓ |  |
| `b2-concession-315k` | brief-02 | core | money | ✓ | ✓ | ✓ |  |
| `b2-golive-feb-15` | brief-02 | core | deadline | ✓ | ✓ | ✓ |  |
| `b2-map-unwind` | brief-02 | core | decision | ✓ | ✓ | ✓ |  |
| `b2-settlement-t3` | brief-02 | core | decision | ✓ | ✓ | ✓ |  |
| `b2-std-commission-11-5` | brief-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `b2-fbo-standard-4-40` | brief-02 | detail | money | ✓ | ✓ | ✓ |  |
| `b2-roas-floor-4-8x` | brief-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `b2-hub-split-65` | brief-02 | detail | decision | ✓ | ✓ | ✓ |  |
| `b2-exclusivity-45-day` | brief-02 | detail | decision | ✓ | ✓ | ✓ |  |
| `b2-return-savings-954k` | brief-02 | detail | money | ✓ | ✓ | ✓ |  |
| `b2-un38-26-of-28` | brief-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `b2-registry-lock-jan-10` | brief-02 | detail | deadline | ✓ | ✓ | ✓ |  |
| `b2-reserve-250k` | brief-02 | detail | money | ✓ | ✓ | ✓ |  |
| `b2-owner-siddharth` | brief-02 | detail | owner | ✓ | ✓ | ✓ |  |
| `r1-zero-injuries` | reg-01 | core | metric | ✓ | ✓ | ✓ |  |
| `r1-cause-misdeclared-cells` | reg-01 | core | cause | ✓ | ✓ | ✓ |  |
| `r1-delisted-15-skus` | reg-01 | core | decision | ✓ | ✓ | ✓ |  |
| `r1-audit-compliant-334` | reg-01 | core | metric | ✓ | ✓ | ✓ |  |
| `r1-open-recall-548` | reg-01 | core | metric | ✓ | ✓ | ✓ |  |
| `r1-deadline-recall-nov-15` | reg-01 | core | deadline | ✓ | ✓ | ✓ |  |
| `r1-deadline-flir-nov-30` | reg-01 | core | deadline | ✓ | ✓ | ✓ |  |
| `r1-escrow-184k` | reg-01 | core | money | ✓ | ✓ | ✓ |  |
| `r1-suspended-63` | reg-01 | detail | metric | ✓ | ✓ | ✓ |  |
| `r1-recall-1420` | reg-01 | detail | metric | ✓ | ✓ | ✓ |  |
| `r1-recall-completion-61-4` | reg-01 | detail | metric | ✓ | ✓ | ✓ |  |
| `r1-recall-reserve-58220` | reg-01 | detail | money | ✓ | ✓ | ✓ |  |
| `r1-cause-forged-bis` | reg-01 | detail | cause | ✓ | ✓ | ✓ |  |
| `r1-referral-law-enforcement` | reg-01 | detail | decision | ✓ | ✓ | ✓ |  |
| `r1-flir-capex-42000` | reg-01 | detail | money | ✓ | ✓ | ✓ |  |
| `r1-remediation-12400` | reg-01 | detail | money | ✓ | ✗ | ✓ |  |
| `r1-air-block-37wh` | reg-01 | detail | decision | ✓ | ✓ | ✗ |  |
| `r1-cause-nickel-tab` | reg-01 | detail | cause | ✓ | ✗ | ✗ |  |
| `r2-false-positive-68-2` | reg-02 | core | metric | ✓ | ✓ | ✓ |  |
| `r2-true-gaps-1-41m` | reg-02 | core | money | ✓ | ✓ | ✓ |  |
| `r2-sla-observed-83-5` | reg-02 | core | metric | ✓ | ✓ | ✓ |  |
| `r2-sla-contract-48h` | reg-02 | core | deadline | ✓ | ✓ | ✓ |  |
| `r2-pii-194` | reg-02 | core | metric | ✓ | ✓ | ✓ |  |
| `r2-aml-286k` | reg-02 | core | money | ✓ | ✓ | ✓ |  |
| `r2-escrow-held-4-82m` | reg-02 | core | money | ✓ | ✓ | ✓ |  |
| `r2-dispute-cost` | reg-02 | core | money | ✓ | ✓ | ✓ |  |
| `r2-audited-1850` | reg-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `r2-holds-214` | reg-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `r2-fp-146` | reg-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `r2-arbitration-notices` | reg-02 | detail | metric | ✓ | ✓ | ✓ |  |
| `r2-cause-name-normalization` | reg-02 | detail | cause | ✓ | ✓ | ✓ |  |
| `r2-cause-iban-19` | reg-02 | detail | cause | ✓ | ✓ | ✓ |  |
| `r2-fix-canonicalizer-65` | reg-02 | detail | decision | ✓ | ✓ | ✓ |  |
| `r2-fix-fast-lane-12h` | reg-02 | detail | decision | ✓ | ✓ | ✓ |  |
| `r2-fix-pii-vault` | reg-02 | detail | decision | ✓ | ✓ | ✓ |  |
| `r2-owner-treasury-infosec` | reg-02 | detail | owner | ✓ | ✓ | ✓ |  |

Facts covered by no draft: 0 []

## Data quality

- The stored drafts' `stop_reason` was written as a constant (`end_turn`) by `scripts/capture_cat2_replays.py`, so normal completion is inferred from the text ending cleanly and output tokens being below the cap, not observed.
- There is one draft per rung per source bundle, so the judge repeats measure judge noise, not drafting variance.
- Judge: 60 records, 60 ok calls, 0 error records ({}); returned models {'claude-opus-5-5': 60}; ok stop reasons {'end_turn': 60}; tokens in 592,030 / out 97,996 (thinking 50,126); billed $4.3280 at the assumed rate (error records $0.0000); latency 14893.78 (5861–30583) ms.
- Judge settings: `claude-opus-5-5`, thinking adaptive, effort medium, max_tokens 8000; drafts labelled only Draft / Draft A / Draft B.

## Scoring rules

Fact coverage — both texts normalised identically (Category 3 normaliser):

1. Lowercase.
2. Delete markdown emphasis markers and code backticks (`*`, `**`, `~~`, backticks); underscores are kept.
3. Map Unicode dashes/minus signs (‐ ‑ ‒ – — ― −) to '-', curly quotes to straight quotes.
4. Collapse all whitespace runs (incl. non-breaking spaces) to one space and trim.
5. Remove a comma between digits when exactly 2 or 3 digits follow it (64,200 -> 64200; 2,50,000 -> 250000).
6. Remove currency markers adjacent to a number: ₹, $, inr, usd, rs, rs. before it; inr, usd after it.

Matching: an alternative is hit when it occurs in the normalised reply, with a boundary guard — an alternative starting with a letter/digit must not be preceded by a letter/digit, and one ending in a digit must not be followed by a digit.

Unsupported numbers — ignore rules (not counted as numeric tokens):

- `list_numbering`: Integer 1–99 that opens a line as a list/heading number ('1.', '2)', '## 3.', '## 3.2 ...') or is the whole first cell of a table row ('| 1 |').
- `own_label`: The draft's own ordinal label, when not present in the source: a short code (KF-1, KF-03, R-2, F2), or a small integer / dotted section number / section code directly after a label word (Finding 1, Risk 2, Section 4, Section 2.4, Section A.1, Table 1, ...).
- `in_title`: Any number on the document title line (the first '# ' heading).
- `document_id`: The source bundle's own document ID (its meeting_id / opportunity_id / filing_reference / audit_id value) quoted in the draft.
- `date_in_source`: A calendar date (ISO, 'Month D[, YYYY]', 'D Month', 'Month YYYY') whose month/day (and year, when given) also appears in the source in any date format.
- `year_in_source`: A bare year 1900–2099 (no currency/unit/separators) that appears anywhere in the source (also inside IDs/dates such as FY2027 or 2026-08-29).

- Numbers: value = digits without thousands separators (western 1,234,567 and Indian 1,48,000), times a magnitude for k/K, M/MM/mn, B/bn, 'm'/'b' only after a currency sign, and the words thousand/million/billion/lakh/crore. %, x, bps, h, ms, -day etc. are kept as the unit but do not change the value. Sign is recorded but matching uses the absolute value. In a range 'A–B' where only B carries a magnitude ($115–180K), A is also tried with B's magnitude.
- in_source: the value (rounded to 6 decimals) equals the value of any numeric token extracted from the payload the same way, or a digit run inside a payload identifier; times (HH:MM) match a payload time; identifiers match the payload case-insensitively with '-', '_' and spaces treated alike.
- not_in_source: everything else not covered by an ignore rule — including rounded or derived figures, which measure C does not try to judge.
- Not extracted: numbers written as words (three, zero); digits glued to a preceding letter are part of an identifier (Q3, FY2027, UN38.3, p99) and classified as identifiers.
