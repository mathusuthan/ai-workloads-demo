# Category 2 follow-up: may the template say "Not stated in source"?

Arms: `template_original` (the app's templated prompt and schema) vs `template_not_stated` (the same prompt plus one instruction; schema unchanged). Models: Sonnet 5.5 and Haiku 5.5 via the app's templated call. 3 drafts per bundle × model × arm.

Added instruction: "For each action-plan item, give the owner and the time window only if the source states them. If the source does not name an owner, or gives no date or time window, write exactly `Not stated in source` in that field. Never supply an owner, team, date or deadline the source does not give."

Drafts: 48 of 48 planned (0 error records); truncated (stop_reason `max_tokens`): 0; JSON not parsed: 0; stop reasons {'end_turn': 48}; models returned {'claude-haiku-5-5': 24, 'claude-sonnet-5-5': 24}.

Judge: `claude-opus-5-5` with the baseline rubric and pairwise prompts and settings, one rubric pass per draft. 112 ok calls, 0 error records, models returned {'claude-opus-5-5': 112}, billed ≈ $6.33 at the assumed rate.

## Action-item fields (deterministic)

Counts are supported / not stated / unsupported over all action items. Rules:
- not_stated: the field, lowercased with every non-letter run collapsed to one space, is exactly 'not stated in source' (so case, backticks, quotes, hyphens and a trailing period do not matter); anything longer that merely contains the phrase is not 'not_stated'.
- Owner supported: the whole owner string occurs in the source, or after splitting it on , ; / ( ) [ ] + and ' - ', every piece (leading 'the' dropped) contains a capital letter and occurs verbatim, case-sensitive, as a whole-word phrase in the source. A piece joined by 'and' / '&' / 'or' is split further only if every part has at least two words (two names or two teams); otherwise it must occur whole, with 'and' and '&' interchangeable. A piece without a capital letter, or not found, makes the owner unsupported.
- Time window supported: the whole window string occurs in the source (case-insensitive), or every date/time expression in it is found in the source after canonicalisation — dates as (month, day, year; a missing year on either side matches), month names, quarters/halves/fiscal years (Q1 FY2027 != Q1 2027), durations ('30 days' = '30-day'), clock times (hh:mm, zone ignored), T+N, week numbers, years, and any other token containing a digit verbatim. A window with no such expression ('Ongoing', 'Pre-launch') is unsupported.
- 'supported' only means the name or date occurs in the source; it does not check that the source assigns this action to that owner or date (the judge's errors cover attribution). When unsure the rule says unsupported.

| Arm | Model | Drafts | Items | Owner (sup / not stated / unsup) | Time window (sup / not stated / unsup) | Grader-flagged items per draft | Serious errors per draft | Minor errors per draft |
|---|---|---:|---:|---|---|---:|---:|---:|
| template_original | sonnet | 12 | 36 | 14 / 0 / 22 | 23 / 0 / 13 | 2.08 (0–3) | 1.25 (0–3) | 3.00 (1–5) |
| template_original | haiku | 12 | 36 | 10 / 0 / 26 | 17 / 0 / 19 | 2.25 (1–3) | 2.25 (0–4) | 3.42 (1–6) |
| template_not_stated | sonnet | 12 | 36 | 8 / 28 / 0 | 21 / 15 / 0 | 0.33 (0–3) | 0.00 | 1.92 (0–4) |
| template_not_stated | haiku | 12 | 36 | 0 / 36 / 0 | 22 / 14 / 0 | 0.50 (0–3) | 0.25 (0–1) | 2.58 (1–5) |

Per bundle (mean over repeats, range in brackets):

| Arm | Model | Bundle | Drafts | Owner (sup / ns / unsup) | Window (sup / ns / unsup) | Flagged items | Serious | Minor |
|---|---|---|---:|---|---|---:|---:|---:|
| template_original | sonnet | brief-01 | 3 | 7 / 0 / 2 | 9 / 0 / 0 | 0.67 (0–1) | 0.33 (0–1) | 3.67 (3–4) |
| template_original | sonnet | brief-02 | 3 | 4 / 0 / 5 | 8 / 0 / 1 | 2.33 (2–3) | 1.00 | 2.67 (2–3) |
| template_original | sonnet | reg-01 | 3 | 0 / 0 / 9 | 6 / 0 / 3 | 2.33 (2–3) | 1.33 (1–2) | 1.67 (1–2) |
| template_original | sonnet | reg-02 | 3 | 3 / 0 / 6 | 0 / 0 / 9 | 3.00 | 2.33 (1–3) | 4.00 (3–5) |
| template_original | haiku | brief-01 | 3 | 3 / 0 / 6 | 5 / 0 / 4 | 1.00 | 1.33 (0–2) | 2.00 (1–4) |
| template_original | haiku | brief-02 | 3 | 5 / 0 / 4 | 6 / 0 / 3 | 2.67 (2–3) | 3.33 (3–4) | 3.00 (2–4) |
| template_original | haiku | reg-01 | 3 | 2 / 0 / 7 | 6 / 0 / 3 | 2.33 (2–3) | 2.00 (1–3) | 3.67 (3–4) |
| template_original | haiku | reg-02 | 3 | 0 / 0 / 9 | 0 / 0 / 9 | 3.00 | 2.33 (2–3) | 5.00 (3–6) |
| template_not_stated | sonnet | brief-01 | 3 | 4 / 5 / 0 | 9 / 0 / 0 | 0.33 (0–1) | 0.00 | 2.00 |
| template_not_stated | sonnet | brief-02 | 3 | 3 / 6 / 0 | 6 / 3 / 0 | 0.00 | 0.00 | 0.67 (0–2) |
| template_not_stated | sonnet | reg-01 | 3 | 0 / 9 / 0 | 6 / 3 / 0 | 0.00 | 0.00 | 2.00 (1–3) |
| template_not_stated | sonnet | reg-02 | 3 | 1 / 8 / 0 | 0 / 9 / 0 | 1.00 (0–3) | 0.00 | 3.00 (1–4) |
| template_not_stated | haiku | brief-01 | 3 | 0 / 9 / 0 | 9 / 0 / 0 | 0.00 | 0.00 | 2.33 (2–3) |
| template_not_stated | haiku | brief-02 | 3 | 0 / 9 / 0 | 7 / 2 / 0 | 2.00 (0–3) | 0.33 (0–1) | 3.00 (2–4) |
| template_not_stated | haiku | reg-01 | 3 | 0 / 9 / 0 | 6 / 3 / 0 | 0.00 | 0.67 (0–1) | 1.67 (1–2) |
| template_not_stated | haiku | reg-02 | 3 | 0 / 9 / 0 | 0 / 9 / 0 | 0.00 | 0.00 | 3.33 (1–5) |

## Rubric (blind judge, 1–5; mean over drafts, range in brackets)

| Arm | Model | Judged | Accuracy | Coverage | Clarity | Actionability | Concision |
|---|---|---:|---:|---:|---:|---:|---:|
| template_original | sonnet | 12 | 3.25 (2–4) | 3.75 (3–4) | 5.00 | 3.67 (2–4) | 4.33 (4–5) |
| template_original | haiku | 12 | 2.67 (2–4) | 3.58 (3–4) | 4.42 (4–5) | 3.25 (2–4) | 4.08 (4–5) |
| template_not_stated | sonnet | 12 | 4.17 (4–5) | 3.42 (3–4) | 4.17 (4–5) | 3.08 (3–4) | 4.00 |
| template_not_stated | haiku | 12 | 3.83 (3–4) | 3.58 (3–4) | 4.08 (4–5) | 2.67 (2–3) | 4.08 (4–5) |

Per bundle:

| Arm | Model | Bundle | Accuracy | Coverage | Clarity | Actionability | Concision |
|---|---|---|---:|---:|---:|---:|---:|
| template_original | sonnet | brief-01 | 3.67 (3–4) | 4.00 | 5.00 | 4.00 | 4.00 |
| template_original | sonnet | brief-02 | 3.67 (3–4) | 4.00 | 5.00 | 4.00 | 4.67 (4–5) |
| template_original | sonnet | reg-01 | 3.33 (3–4) | 3.00 | 5.00 | 4.00 | 4.67 (4–5) |
| template_original | sonnet | reg-02 | 2.33 (2–3) | 4.00 | 5.00 | 2.67 (2–3) | 4.00 |
| template_original | haiku | brief-01 | 3.67 (3–4) | 4.00 | 4.33 (4–5) | 4.00 | 4.00 |
| template_original | haiku | brief-02 | 2.00 | 3.33 (3–4) | 4.00 | 3.00 | 4.00 |
| template_original | haiku | reg-01 | 3.00 | 3.00 | 4.33 (4–5) | 3.67 (3–4) | 4.00 |
| template_original | haiku | reg-02 | 2.00 | 4.00 | 5.00 | 2.33 (2–3) | 4.33 (4–5) |
| template_not_stated | sonnet | brief-01 | 4.00 | 3.67 (3–4) | 4.67 (4–5) | 3.33 (3–4) | 4.00 |
| template_not_stated | sonnet | brief-02 | 4.67 (4–5) | 3.00 | 4.00 | 3.00 | 4.00 |
| template_not_stated | sonnet | reg-01 | 4.00 | 3.00 | 4.00 | 3.00 | 4.00 |
| template_not_stated | sonnet | reg-02 | 4.00 | 4.00 | 4.00 | 3.00 | 4.00 |
| template_not_stated | haiku | brief-01 | 4.00 | 4.00 | 4.33 (4–5) | 3.00 | 4.00 |
| template_not_stated | haiku | brief-02 | 3.67 (3–4) | 3.33 (3–4) | 4.00 | 2.33 (2–3) | 4.00 |
| template_not_stated | haiku | reg-01 | 3.67 (3–4) | 3.00 | 4.00 | 3.00 | 4.00 |
| template_not_stated | haiku | reg-02 | 4.00 | 4.00 | 4.00 | 2.33 (2–3) | 4.33 (4–5) |

## Facts, numbers, tokens and cost

| Arm | Model | Core facts | Detail facts | Numbers not in source | …judge verdicts (derived correct / derived wrong / unverifiable / not a claim) | Output tokens | $ / 1k docs | Truncated | JSON not parsed |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| template_original | sonnet | 96/96 | 110/120 | 14 | 4 / 0 / 9 / 1 | 1748 (1693–1848) | 27.19 (26.30–28.63) | 0 | 0 |
| template_original | haiku | 93/96 | 104/120 | 34 | 11 / 2 / 19 / 2 | 1808 (1661–1937) | 1.39 (1.30–1.48) | 0 | 0 |
| template_not_stated | sonnet | 94/96 | 94/120 | 2 | 2 / 0 / 0 / 0 | 1694 (1586–1839) | 26.82 (25.39–28.70) | 0 | 0 |
| template_not_stated | haiku | 92/96 | 92/120 | 9 | 7 / 1 / 0 / 1 | 1723 (1569–1892) | 1.36 (1.26–1.45) | 0 | 0 |

## Head-to-head (blind judge, both presentation orders)

| Comparison | Scope | Calls | Overall: not stated – other – tie | Accuracy | Usefulness to reader | Position-consistent units | Share of decisive picks for position A |
|---|---|---:|---|---|---|---:|---:|
| template_not_stated vs template_original (same bundle, model, repeat) | all | 48 | 47 – 1 – 0 | 47 – 1 – 0 | 40 – 8 – 0 | 23/24 | 0.48 |
| template_not_stated vs template_original (same bundle, model, repeat) | sonnet | 24 | 23 – 1 – 0 | 23 – 1 – 0 | 20 – 4 – 0 | 11/12 | 0.46 |
| template_not_stated vs template_original (same bundle, model, repeat) | haiku | 24 | 24 – 0 – 0 | 24 – 0 – 0 | 20 – 4 – 0 | 12/12 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | sonnet · brief-01 | 6 | 5 – 1 – 0 | 5 – 1 – 0 | 3 – 3 – 0 | 2/3 | 0.33 |
| template_not_stated vs template_original (same bundle, model, repeat) | sonnet · brief-02 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 5 – 1 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | sonnet · reg-01 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 6 – 0 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | sonnet · reg-02 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 6 – 0 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | haiku · brief-01 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 4 – 2 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | haiku · brief-02 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 5 – 1 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | haiku · reg-01 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 5 – 1 – 0 | 3/3 | 0.50 |
| template_not_stated vs template_original (same bundle, model, repeat) | haiku · reg-02 | 6 | 6 – 0 – 0 | 6 – 0 – 0 | 6 – 0 – 0 | 3/3 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | all | 16 | 1 – 15 – 0 | 1 – 11 – 4 | 0 – 16 – 0 | 7/8 | 0.56 |
| template_not_stated (repeat 0) vs stored unbounded draft | sonnet | 8 | 1 – 7 – 0 | 1 – 6 – 1 | 0 – 8 – 0 | 3/4 | 0.62 |
| template_not_stated (repeat 0) vs stored unbounded draft | haiku | 8 | 0 – 8 – 0 | 0 – 5 – 3 | 0 – 8 – 0 | 4/4 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | sonnet · brief-01 | 2 | 0 – 2 – 0 | 0 – 2 – 0 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | sonnet · brief-02 | 2 | 0 – 2 – 0 | 0 – 2 – 0 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | sonnet · reg-01 | 2 | 0 – 2 – 0 | 0 – 1 – 1 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | sonnet · reg-02 | 2 | 1 – 1 – 0 | 1 – 1 – 0 | 0 – 2 – 0 | 0/1 | 1.00 |
| template_not_stated (repeat 0) vs stored unbounded draft | haiku · brief-01 | 2 | 0 – 2 – 0 | 0 – 2 – 0 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | haiku · brief-02 | 2 | 0 – 2 – 0 | 0 – 2 – 0 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | haiku · reg-01 | 2 | 0 – 2 – 0 | 0 – 0 – 2 | 0 – 2 – 0 | 1/1 | 0.50 |
| template_not_stated (repeat 0) vs stored unbounded draft | haiku · reg-02 | 2 | 0 – 2 – 0 | 0 – 1 – 1 | 0 – 2 – 0 | 1/1 | 0.50 |

## Stored baseline, for context (different drafts: n=1 per cell, 3 judge passes)

Read from `backend/replays/cat2_quality_summary.json` (keys version `2026-11-25.3`, judge `claude-opus-5-5`, 3 passes per draft, 1 draft per rung per bundle). Not comparable draft-for-draft with the tables above.

| Rung | Drafts | Core facts | Detail facts | Accuracy | Coverage | Clarity | Actionability | Concision | Serious / minor errors | Grader-flagged action items | $ / 1k docs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sonnet_unbounded | 4 | 32/32 | 40/40 | 3.92 | 4.92 | 4.00 | 3.75 | 2.83 | 1 / 21 | — | 58.92 |
| sonnet_templated | 4 | 32/32 | 37/40 | 3.08 | 4.00 | 4.92 | 3.75 | 4.17 | 6 / 18 | 8/12 | 27.25 |
| haiku_templated | 4 | 32/32 | 36/40 | 2.58 | 3.50 | 4.42 | 3.25 | 4.08 | 10 / 18 | 8/12 | 1.39 |

## For lead review

### Serious errors reported by the judge (45)

| Draft | Draft words | Problem | Source words |
|---|---|---|---|
| brief-01 · haiku · template_original · repeat 0 | Staged backlog below 10,000 cages | The 10,000-cage completion threshold is not in the source, which calls for clearing the 41,800-cage backlog before 23:59Z. | ABSENT |
| brief-01 · haiku · template_original · repeat 0 | Kabir Sethi, Head of 3PL Carrier Contracts & SLA Governance — Standby confirmed by 17:00Z; waivers and audit within 7 days | The source names no owner for seller LDP waivers and the phantom-manifest audit; the transcript places this with Seller Support (Divya) and Compliance, not with carrier governance. | Our badge telemetry shows dock-in timestamps so Compliance can isolate genuine carrier/hub queues from seller stockouts. |
| brief-01 · haiku · template_original · repeat 1 | Backlog below 5,000 cages and Western SLA above 92% by 23:59Z | The 5,000-cage target is invented. The 92% threshold in the source applies to Western Zone on-time-tender, not SLA attainment, and the source calls for clearing the whole backlog. | if we do not clear the 41,800 cage backlog before 23:59Z tonight, plus an estimated $142,000 rebate forfeiture risk for Week 46 if Western Zone on-time-tender falls below 92.0% |
| brief-01 · haiku · template_original · repeat 1 | Kabir Sethi, Head of 3PL Carrier Contracts and SLA Governance — Within 7 days | The source assigns no owner for seller LDP compliance, so naming Kabir (the carrier-contracts lead) rather than seller support or Compliance is unsupported. | ABSENT |
| brief-01 · sonnet · template_original · repeat 0 | If the 41,800-cage backlog is not cleared by 23:59Z, surcharges of $77,330, rebate forfeiture of $142,000 and $94,000 vouchers materialize. | Only the $77,330 surcharge is tied to the 23:59Z deadline; the rebate forfeiture depends on Western Zone on-time-tender falling below 92.0%, and the voucher risk depends on backlog age crossing 16 hours. | plus an estimated $142,000 rebate forfeiture risk for Week 46 if Western Zone on-time-tender falls below 92.0% |
| brief-02 · haiku · template_not_stated · repeat 0 | Not stated in source — By January 10, 2027 | The draft says the owner is not stated, but the source names NovaMart Catalog Engineering as owner of the Brand Registry Lock enrollment. | NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027. |
| brief-02 · haiku · template_original · repeat 0 | AetherSonic commits $480k guaranteed co-op spend, 65% hub safety-stock prepositioning, and $1.9M co-op marketing alignment. | The $1.9M is AetherSonic's existing co-op marketing spend, which the CFO cited to argue the commission was too high; it is not a commitment under this deal. | flagged as 150bps too high given their 44% gross margin and $1.9M co-op marketing spend |
| brief-02 · haiku · template_original · repeat 0 | NovaMart Catalog Engineering (Tarun Kapoor) | The source assigns Brand Registry Lock to NovaMart Catalog Engineering and names no individual; Tarun Kapoor is the FBO Supply Chain & Pricing Architect. | Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect) |
| brief-02 · haiku · template_original · repeat 0 | AetherSonic Global Compliance (Elena Martinez) — By February 1, 2027 | The source does not assign Elena Martinez (VP Global E-Commerce & Channels) to UN38.3 or KYC/TIN work, and gives no February 1 deadline. | ABSENT |
| brief-02 · haiku · template_original · repeat 1 | Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect) — By February 10, 2027 | The source makes pre-positioning 65% of safety stock AetherSonic's obligation, not Tarun's, and gives no February 10 deadline. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs |
| brief-02 · haiku · template_original · repeat 1 | Siddharth Rao (NovaMart VP Category Partnerships) — By January 10, 2027 | The source assigns Brand Registry Lock enrollment to NovaMart Catalog Engineering, not Siddharth Rao. | NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027 |
| brief-02 · haiku · template_original · repeat 1 | approve T+3 settlement with $250k rolling return reserve | T+3 approval needs Director approval on the NovaMart Treasury side; the source does not make AetherSonic's CFO the approver. | Treasury notes T+3 requires Director approval plus zero unresolved KYC/TIN mismatches. |
| brief-02 · haiku · template_original · repeat 1 | Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller) — By January 31, 2027 | The source assigns no owner and no January 31 deadline for the UN38.3 signoff or the T+3 settlement. | ABSENT |
| brief-02 · haiku · template_original · repeat 2 | Net AetherSonic benefit: $954k return savings offsets $315k commission concession and FBO subsidy, against $480k co-op spend. | Misframes the tradeoff: the commission concession and FBO subsidy are NovaMart concessions that benefit AetherSonic, so return savings do not 'offset' them; the source frames the tradeoff as concessions versus the co-op spend plus the $18M allocation. | margin tradeoffs (175bps commission concession + $0.75/unit FBO subsidy vs. $480k guaranteed Co-Op spend + $18M Year-1 exclusive launch allocation) |
| brief-02 · haiku · template_original · repeat 2 | NovaMart Catalog Engineering (Tarun Kapoor) | Assigns Tarun Kapoor as Catalog Engineering owner, but the source lists him as FBO Supply Chain & Pricing Architect and names no individual owner for catalog enrollment. | Tarun Kapoor (NovaMart FBO Supply Chain & Pricing Architect) |
| brief-02 · haiku · template_original · repeat 2 | AetherSonic Compliance (Nadia Jenkins) | Invents Nadia Jenkins as owner of UN38.3 certification; she is CFO / MAP & Margin Controller, and the source assigns no owner for this task. | Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller) |
| brief-02 · sonnet · template_original · repeat 0 | Tarun Kapoor, NovaMart FBO Supply Chain — Before February 15, 2027 go-live | The draft makes Tarun Kapoor responsible for pre-positioning 65% of safety stock, but that is AetherSonic's condition for the fee tier, not a NovaMart owner action. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs |
| brief-02 · sonnet · template_original · repeat 1 | Tarun Kapoor, NovaMart FBO Supply Chain — Before February 15, 2027 go-live | The source assigns no owner to serial-scan deployment or safety-stock pre-positioning, so naming Tarun Kapoor as accountable invents an owner. | ABSENT |
| brief-02 · sonnet · template_original · repeat 2 | pre-position 65% of safety stock regionally | The source makes pre-positioning 65% of safety stock AetherSonic's condition for the $3.65 rate, but the draft assigns it to NovaMart's Tarun Kapoor as his milestone. | provided AetherSonic pre-positions 65% of safety stock across our 4 regional hubs |
| reg-01 · haiku · template_not_stated · repeat 1 | Net Q3 cost $79,480 | The headline cost matches no sum of source figures: damage, remediation and refund reserve total $75,480, and adding forensic testing gives $93,980. | Total physical inventory damaged: 180 units across 3 adjacent pallets ($4,860 wholesale cost); containment remediation cost: $12,400. |
| reg-01 · haiku · template_not_stated · repeat 2 | enforce 100% dock-receiving thermal scans at all facilities | The source limits 100% dock FLIR scanning to the top 12 fulfillment hubs and says 10 Tier-2 spokes still lack cameras, so 'all facilities' overstates the control. | 100% handheld FLIR thermal scan at dock receiving + random 10% carton weight/Wh density verification across top 12 fulfillment hubs |
| reg-01 · haiku · template_original · repeat 0 | Customer Recovery Operations Lead — By November 15, 2026 | The source names no such owner; the recall commitment is attributed only to 'Management'. | ABSENT |
| reg-01 · haiku · template_original · repeat 0 | Tier-2 Facilities Engineering Director — By November 30, 2026 | This owner title is invented; the source assigns the FLIR rollout to 'Management' generally. | ABSENT |
| reg-01 · haiku · template_original · repeat 0 | Marketplace Trust & Seller Compliance Head — Continuous through Q4 FY2026 | Both the owner and the Q4 FY2026 time window are invented; the source states an ongoing zero-tolerance commitment with no named owner or end period. | ABSENT |
| reg-01 · haiku · template_original · repeat 1 | Net Q3 cost $79,480 absorbed | No source figure or combination of source figures yields $79,480 (inventory + remediation + recall reserve is $75,480), and the source states that only $12,400 was absorbed in Q3 Safety OpEx. | ($12,400 absorbed in Q3 Safety OpEx) |
| reg-01 · haiku · template_original · repeat 2 | Customer Recall Operations — By November 15, 2026 | The draft names an owning team that the source never mentions; the source attributes the commitment only to 'Management'. | ABSENT |
| reg-01 · haiku · template_original · repeat 2 | NovaMart Legal and Seller Trust — Continuous through Q4 FY2026 | The owner assignment for zero-tolerance delisting and the end date of Q4 FY2026 are both invented; the source sets the commitment as ongoing with no end date and no named owner. | maintaining zero tolerance auto-delisting for any seller attempting UN38.3 / BIS document tampering |
| reg-01 · sonnet · template_original · repeat 0 | Customer Trust and Safety Operations — By November 15, 2026 | The source assigns the recall-closure commitment only to 'Management'; this owning team is invented. | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026 |
| reg-01 · sonnet · template_original · repeat 1 | Customer Trust & Recall Operations — By November 15, 2026 | The owner team names in the action plan are invented; the source assigns these commitments to 'Management', NovaMart Safety Engineering and NovaMart Legal. | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026 |
| reg-01 · sonnet · template_original · repeat 2 | Marketplace Trust & Safety Recall Lead — By November 15, 2026 | The source assigns recall closure only to 'Management' and names no such owner, so this owner is invented. | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026 |
| reg-01 · sonnet · template_original · repeat 2 | Fulfillment Operations & Safety Engineering — By November 30, 2026 | The source names no owner for the FLIR rollout beyond 'Management', so this owner is invented. | Management commits to ... deploying FLIR handheld imaging across all remaining 10 Tier-2 regional sortation spokes ($42,000 approved capex) by November 30, 2026 |
| reg-02 · haiku · template_original · repeat 0 | Payments Engineering Lead — Within 30 days of audit issuance | The source names no owner and sets no deadline for the canonicalizer milestone; both are invented. | ABSENT |
| reg-02 · haiku · template_original · repeat 0 | 68 genuine compliance gaps including 8 velocity-flagged bank swaps and 14 circular shell-ring accounts | The draft counts the 14 shell-ring accounts as part of the 68 genuine compliance gaps, but the source reports them as a separate detection. | Device-Graph + GSTIN clustering flagged 14 interconnected seller shells |
| reg-02 · haiku · template_original · repeat 1 | Payments Engineering Lead — Within 30 days | The source names no owner or deadline for the canonicalizer milestone, so both are invented. | ABSENT |
| reg-02 · haiku · template_original · repeat 1 | Treasury Operations Director — Within 45 days | The source names no owner or deadline for the fast-lane milestone, so both are invented. | ABSENT |
| reg-02 · haiku · template_original · repeat 1 | Information Security & Compliance Officer — Within 60 days | The source names no owner or deadline for the UBO refresh or PII vault milestone, so both are invented. | ABSENT |
| reg-02 · haiku · template_original · repeat 2 | residual exposure exists during legacy ticket threads | The source says every historical raw token was purged, so claiming residual exposure in legacy threads contradicts the stated remediation status. | Every historical raw token was purged within 72 hours using deterministic pattern scanners |
| reg-02 · haiku · template_original · repeat 2 | Payments Engineering Lead — Within 45 days of audit closure | The owner and deadline are invented; the source names no owner or time window for the canonicalizer milestone. | ABSENT |
| reg-02 · sonnet · template_original · repeat 0 | Head of Engineering, Seller Identity Platform — Q1 2027 | The source names no owner and gives no deadline for the canonicalizer milestone, so both the owner and the Q1 2027 date are invented. | ABSENT |
| reg-02 · sonnet · template_original · repeat 0 | Chief Information Security Officer — Immediate; attestation next committee cycle | The source assigns no CISO ownership and sets no 'immediate' or next-cycle attestation deadline for the zero-PII vault. | ABSENT |
| reg-02 · sonnet · template_original · repeat 0 | Head of Treasury Operations — Within 60 days | The source sets no owner role or 60-day deadline for the fast-lane; only the 12-hour SLA design is specified. | ABSENT |
| reg-02 · sonnet · template_original · repeat 1 | Engineering and Compliance Technology — Next 90 days | The source gives no deadline or time window for deploying the legal-suffix normalizer, so the 90-day window is invented. | ABSENT |
| reg-02 · sonnet · template_original · repeat 1 | Treasury Operations — Next 60 days | The source gives no deadline for the 12-hour fast-lane, so the 60-day window is invented. | ABSENT |
| reg-02 · sonnet · template_original · repeat 1 | Information Security — Immediate; attest next quarter | The source does not give this timing or an attestation commitment for the zero-PII vault. | ABSENT |
| reg-02 · sonnet · template_original · repeat 2 | Within 60 days of Committee approval | The source gives no deadline for the canonicalizer milestone, so this 60-day window is invented. | ABSENT |

### Owner / time-window fields classified unsupported (80)

| Draft | Item | Field | Draft words | Rule result | Nearest source text |
|---|---:|---|---|---|---|
| brief-01 · haiku · template_original · repeat 0 | 1 | owner | Rohan Kulkarni, Director Bhiwandi & Western Hub Sortation | not found in source: ['Director Bhiwandi'] | - Rohan Kulkarni (Director, Bhiwandi & Western Hub Sortation) |
| brief-01 · haiku · template_original · repeat 0 | 2 | owner | Meera Subramanian, Principal SRE Checkout & Payments | not found in source: ['Principal SRE Checkout & Payments'] | - Meera Subramanian (Principal SRE, Checkout & Payments Gateway) |
| brief-01 · haiku · template_original · repeat 1 | 1 | owner | Rohan Kulkarni, Director Bhiwandi Hub Sortation | not found in source: ['Director Bhiwandi Hub Sortation'] | - Rohan Kulkarni (Director, Bhiwandi & Western Hub Sortation) |
| brief-01 · haiku · template_original · repeat 1 | 2 | owner | Meera Subramanian, Principal SRE Checkout and Payments | not found in source: ['Principal SRE Checkout and Payments'] | - Meera Subramanian (Principal SRE, Checkout & Payments Gateway) |
| brief-01 · haiku · template_original · repeat 1 | 2 | time_window | Before 04:00Z 17 Nov 2026 | not found in source: ['17 nov 2026'] | date_utc: 2026-11-16T15:30:00Z |
| brief-01 · haiku · template_original · repeat 1 | 3 | time_window | Within 7 days, by 23 Nov 2026 | not found in source: ['23 nov 2026'] | meeting_id: NM-WAR-2026-W46-09 |
| brief-01 · haiku · template_original · repeat 2 | 1 | owner | Ananya Deshmukh (VP Fulfillment) and Rohan Kulkarni (Bhiwandi Director) | not found in source: ['and Rohan Kulkarni', 'Bhiwandi Director'] | - Rohan Kulkarni (Director, Bhiwandi & Western Hub Sortation) |
| brief-01 · haiku · template_original · repeat 2 | 2 | time_window | Before 04:00Z 2026-11-17 | not found in source: ['2026-11-17'] | date_utc: 2026-11-16T15:30:00Z |
| brief-01 · haiku · template_original · repeat 2 | 3 | owner | Divya Nair (VP Seller Support) and Kabir Sethi (3PL Governance) | not found in source: ['and Kabir Sethi', '3PL Governance'] | - Kabir Sethi (Head of 3PL Carrier Contracts & SLA Governance) |
| brief-01 · haiku · template_original · repeat 2 | 3 | time_window | Waivers by 2026-11-17; audit complete by 2026-11-23 | not found in source: ['2026-11-17', '2026-11-23'] | date_utc: 2026-11-16T15:30:00Z |
| brief-01 · sonnet · template_original · repeat 2 | 1 | owner | Ananya Deshmukh with Rohan Kulkarni | not found in source: ['Ananya Deshmukh with Rohan Kulkarni'] | - Ananya Deshmukh (VP Fulfillment & Linehaul Operations) |
| brief-01 · sonnet · template_original · repeat 2 | 3 | owner | Divya Nair with Kabir Sethi | not found in source: ['Divya Nair with Kabir Sethi'] | - Kabir Sethi (Head of 3PL Carrier Contracts & SLA Governance) |
| brief-02 · haiku · template_original · repeat 0 | 2 | owner | AetherSonic Global Compliance (Elena Martinez) | not found in source: ['AetherSonic Global Compliance'] | - Elena Martinez (AetherSonic VP Global E-Commerce & Channels) |
| brief-02 · haiku · template_original · repeat 0 | 2 | time_window | By February 1, 2027 | not found in source: ['february 1, 2027'] | target_launch_window: Q1 FY2027 (February 15 Go-Live across Top 18 Metro Regions) |
| brief-02 · haiku · template_original · repeat 0 | 3 | owner | AetherSonic CFO / MAP Controller (Nadia Jenkins) | not found in source: ['MAP Controller'] | - Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller) |
| brief-02 · haiku · template_original · repeat 1 | 1 | time_window | By February 10, 2027 | not found in source: ['february 10, 2027'] | NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027. |
| brief-02 · haiku · template_original · repeat 1 | 3 | time_window | By January 31, 2027 | not found in source: ['january 31, 2027'] | NovaMart Catalog Engineering will enroll all 28 AetherSonic UPCs/EANs into Brand Registry Lock by January 10, 2027. |
| brief-02 · haiku · template_original · repeat 2 | 2 | owner | AetherSonic Compliance (Nadia Jenkins) | not found in source: ['AetherSonic Compliance'] | - Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller) |
| brief-02 · haiku · template_original · repeat 2 | 3 | owner | NovaMart Category Partnerships (Siddharth Rao) | not found in source: ['NovaMart Category Partnerships'] | - Siddharth Rao (NovaMart VP Category Partnerships) |
| brief-02 · sonnet · template_original · repeat 0 | 1 | owner | NovaMart Catalog Engineering (via Siddharth Rao) | not found in source: ['via Siddharth Rao'] | - Siddharth Rao (NovaMart VP Category Partnerships) |
| brief-02 · sonnet · template_original · repeat 0 | 3 | owner | Nadia Jenkins, AetherSonic CFO, with NovaMart Treasury | not found in source: ['with NovaMart Treasury'] | - Nadia Jenkins (AetherSonic CFO / MAP & Margin Controller) |
| brief-02 · sonnet · template_original · repeat 1 | 3 | owner | Siddharth Rao with Nadia Jenkins | not found in source: ['Siddharth Rao with Nadia Jenkins'] | - Siddharth Rao (NovaMart VP Category Partnerships) |
| brief-02 · sonnet · template_original · repeat 1 | 3 | time_window | Signature pre-launch; QBRs Day 30/60/90 post-launch | not found in source: ['30/60/90'] | Quarterly Business Reviews (QBRs) scheduled Day 30, Day 60, and Day 90 post-launch will audit net ROAS against the 4.8x target, monitor 14-day grey-market MAP compliance (<2.0% leakage ceiling), and validate whether rolling 60-day return r… |
| brief-02 · sonnet · template_original · repeat 2 | 1 | owner | Catalog Engineering (via Siddharth Rao) | not found in source: ['via Siddharth Rao'] | - Siddharth Rao (NovaMart VP Category Partnerships) |
| brief-02 · sonnet · template_original · repeat 2 | 3 | owner | Siddharth Rao with Nadia Jenkins | not found in source: ['Siddharth Rao with Nadia Jenkins'] | - Siddharth Rao (NovaMart VP Category Partnerships) |
| reg-01 · haiku · template_original · repeat 0 | 1 | owner | Customer Recovery Operations Lead | not found in source: ['Customer Recovery Operations Lead'] | Zero human injuries occurred, sprinklers did not need roof discharge beyond Zone-C local misting heads, and main building operations resumed by 08:30 IST. |
| reg-01 · haiku · template_original · repeat 0 | 2 | owner | Tier-2 Facilities Engineering Director | not found in source: ['Tier-2 Facilities Engineering Director'] | "tier2_regional_spokes_flir_rollout": "10 of 18 Tier-2 sortation spokes pending FLIR handheld cameras (target completion Nov 30, 2026; capex $42,000)" |
| reg-01 · haiku · template_original · repeat 0 | 3 | owner | Marketplace Trust & Seller Compliance Head | not found in source: ['Seller Compliance Head'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · haiku · template_original · repeat 0 | 3 | time_window | Continuous through Q4 FY2026 | not found in source: ['q4 fy2026'] | reporting_period: Q3 FY2026 (July 1 – September 30, 2026) |
| reg-01 · haiku · template_original · repeat 1 | 2 | owner | Safety Engineering and Fulfillment Operations | not found in source: ['Fulfillment Operations'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · haiku · template_original · repeat 1 | 3 | owner | NovaMart Legal and Trust & Safety Seller Compliance | not found in source: ['NovaMart Legal and Trust & Safety Seller Compliance'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · haiku · template_original · repeat 1 | 3 | time_window | Continuous through Q4 FY2026 audit checkpoint | not found in source: ['q4 fy2026'] | 3. Continuous Monitoring & Next Audit Checkpoint: |
| reg-01 · haiku · template_original · repeat 2 | 2 | owner | Customer Recall Operations | not found in source: ['Customer Recall Operations'] | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026, deploying FLIR handheld imaging across all remaining 10 Tier-2 regional sortation spokes ($42,000 approved capex) b… |
| reg-01 · haiku · template_original · repeat 2 | 3 | owner | NovaMart Legal and Seller Trust | not found in source: ['Seller Trust'] | NovaMart Legal referred forged BIS Certificate #BIS-R-41009912 evidence to the Bureau of Market Surveillance and Economic Offences Wing on September 18, 2026, while retaining $184,000 in terminated seller escrow accounts to backstop 100% o… |
| reg-01 · haiku · template_original · repeat 2 | 3 | time_window | Continuous through Q4 FY2026 | not found in source: ['q4 fy2026'] | reporting_period: Q3 FY2026 (July 1 – September 30, 2026) |
| reg-01 · sonnet · template_original · repeat 0 | 1 | owner | Customer Trust and Safety Operations | not found in source: ['Customer Trust', 'Safety Operations'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 0 | 2 | owner | Fulfillment Safety Engineering | not found in source: ['Fulfillment Safety Engineering'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 0 | 3 | owner | NovaMart Legal and Marketplace Integrity | not found in source: ['Marketplace Integrity'] | === NOVAMART MARKETPLACE SAFETY & DGCA/BUREAU COMPLIANCE FILING SOURCE === |
| reg-01 · sonnet · template_original · repeat 0 | 3 | time_window | Ongoing; review at next quarterly audit | no date or duration found | "quarterly_surface_vs_air_routing_audit": { |
| reg-01 · sonnet · template_original · repeat 1 | 1 | owner | Customer Trust & Recall Operations | not found in source: ['Customer Trust', 'Recall Operations'] | Management commits to closing all 548 open customer recall returns via escalated SMS + IVR follow-ups by November 15, 2026, deploying FLIR handheld imaging across all remaining 10 Tier-2 regional sortation spokes ($42,000 approved capex) b… |
| reg-01 · sonnet · template_original · repeat 1 | 2 | owner | Fulfillment Network Safety Engineering | not found in source: ['Fulfillment Network Safety Engineering'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 1 | 3 | owner | Marketplace Trust & Legal Compliance | not found in source: ['Legal Compliance'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 1 | 3 | time_window | Continuous; next audit checkpoint Q4 FY2026 | not found in source: ['q4 fy2026'] | 3. Continuous Monitoring & Next Audit Checkpoint: |
| reg-01 · sonnet · template_original · repeat 2 | 1 | owner | Marketplace Trust & Safety Recall Lead | not found in source: ['Safety Recall Lead'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 2 | 2 | owner | Fulfillment Operations & Safety Engineering | not found in source: ['Fulfillment Operations'] | preparing_entity: NovaMart Marketplace Trust, Safety & Fulfillment Compliance Office |
| reg-01 · sonnet · template_original · repeat 2 | 3 | owner | NovaMart Legal & Seller Compliance | not found in source: ['Seller Compliance'] | NovaMart Legal referred forged BIS Certificate #BIS-R-41009912 evidence to the Bureau of Market Surveillance and Economic Offences Wing on September 18, 2026, while retaining $184,000 in terminated seller escrow accounts to backstop 100% o… |
| reg-01 · sonnet · template_original · repeat 2 | 3 | time_window | Ongoing; review at Q4 FY2026 checkpoint | not found in source: ['q4 fy2026'] | reporting_period: Q3 FY2026 (July 1 – September 30, 2026) |
| reg-02 · haiku · template_original · repeat 0 | 1 | owner | Payments Engineering Lead | not found in source: ['Payments Engineering Lead'] | audit_scope: Marketplace Payments, Cross-Border Seller Verification (KYC/KYB), TIN/PAN/GST Tax Matching & Escrow Holds |
| reg-02 · haiku · template_original · repeat 0 | 1 | time_window | Within 30 days of audit issuance | not found in source: ['30 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · haiku · template_original · repeat 0 | 2 | owner | Treasury Operations Director | not found in source: ['Treasury Operations Director'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · haiku · template_original · repeat 0 | 2 | time_window | Within 45 days of audit issuance | not found in source: ['45 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · haiku · template_original · repeat 0 | 3 | owner | Information Security and Compliance Officer | not found in source: ['Compliance Officer'] | Following Audit Finding #2 (194 raw SSN, PAN, and settlement card strings pasted by frustrated sellers into general CRM support queues during >72h holds), Information Security audited all downstream Zendesk/CRM replicas. |
| reg-02 · haiku · template_original · repeat 0 | 3 | time_window | Within 60 days of audit issuance | not found in source: ['60 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · haiku · template_original · repeat 1 | 1 | owner | Payments Engineering Lead | not found in source: ['Payments Engineering Lead'] | audit_scope: Marketplace Payments, Cross-Border Seller Verification (KYC/KYB), TIN/PAN/GST Tax Matching & Escrow Holds |
| reg-02 · haiku · template_original · repeat 1 | 1 | time_window | Within 30 days | not found in source: ['30 days'] | — |
| reg-02 · haiku · template_original · repeat 1 | 2 | owner | Treasury Operations Director | not found in source: ['Treasury Operations Director'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · haiku · template_original · repeat 1 | 2 | time_window | Within 45 days | not found in source: ['45 days'] | — |
| reg-02 · haiku · template_original · repeat 1 | 3 | owner | Information Security & Compliance Officer | not found in source: ['Compliance Officer'] | Following Audit Finding #2 (194 raw SSN, PAN, and settlement card strings pasted by frustrated sellers into general CRM support queues during >72h holds), Information Security audited all downstream Zendesk/CRM replicas. |
| reg-02 · haiku · template_original · repeat 1 | 3 | time_window | Within 60 days | not found in source: ['60 days'] | — |
| reg-02 · haiku · template_original · repeat 2 | 1 | owner | Payments Engineering Lead | not found in source: ['Payments Engineering Lead'] | audit_scope: Marketplace Payments, Cross-Border Seller Verification (KYC/KYB), TIN/PAN/GST Tax Matching & Escrow Holds |
| reg-02 · haiku · template_original · repeat 2 | 1 | time_window | Within 45 days of audit closure | not found in source: ['45 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · haiku · template_original · repeat 2 | 2 | owner | Treasury Operations Director | not found in source: ['Treasury Operations Director'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · haiku · template_original · repeat 2 | 2 | time_window | Within 30 days of audit closure | not found in source: ['30 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · haiku · template_original · repeat 2 | 3 | owner | Chief Information Security Officer | not found in source: ['Chief Information Security Officer'] | Following Audit Finding #2 (194 raw SSN, PAN, and settlement card strings pasted by frustrated sellers into general CRM support queues during >72h holds), Information Security audited all downstream Zendesk/CRM replicas. |
| reg-02 · haiku · template_original · repeat 2 | 3 | time_window | Within 60 days of audit closure | not found in source: ['60 days'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · sonnet · template_original · repeat 0 | 1 | owner | Head of Engineering, Seller Identity Platform | not found in source: ['Head of Engineering', 'Seller Identity Platform'] | === NOVAMART TREASURY & RISK AUDIT · CROSS-BORDER SELLER KYC & ESCROW CONTROLS === |
| reg-02 · sonnet · template_original · repeat 0 | 1 | time_window | Q1 2027 | not found in source: ['q1 2027'] | — |
| reg-02 · sonnet · template_original · repeat 0 | 2 | owner | Chief Information Security Officer | not found in source: ['Chief Information Security Officer'] | Following Audit Finding #2 (194 raw SSN, PAN, and settlement card strings pasted by frustrated sellers into general CRM support queues during >72h holds), Information Security audited all downstream Zendesk/CRM replicas. |
| reg-02 · sonnet · template_original · repeat 0 | 2 | time_window | Immediate; attestation next committee cycle | no date or duration found | --- SECTION C: STATUTORY GOVERNANCE, PRIVACY & BOARD COMMITTEE ATTESTATION SCOPE --- |
| reg-02 · sonnet · template_original · repeat 0 | 3 | owner | Head of Treasury Operations | not found in source: ['Head of Treasury Operations'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · sonnet · template_original · repeat 0 | 3 | time_window | Within 60 days | not found in source: ['60 days'] | — |
| reg-02 · sonnet · template_original · repeat 1 | 1 | owner | Engineering and Compliance Technology | not found in source: ['Engineering and Compliance Technology'] | Synthesize the exact cohort metrics (1,850 audited sellers, 68.2% false-positive 409 rate vs 68 genuine compliance gaps totaling $1.41M), SLA slippage (83.5h observed vs 48h contractual cap), PII gate remediation (194 pre-gate vs 0 post-ga… |
| reg-02 · sonnet · template_original · repeat 1 | 1 | time_window | Next 90 days | not found in source: ['90 days'] | — |
| reg-02 · sonnet · template_original · repeat 1 | 2 | time_window | Next 60 days | not found in source: ['60 days'] | — |
| reg-02 · sonnet · template_original · repeat 1 | 3 | time_window | Immediate; attest next quarter | no date or duration found | potential statutory interest + arbitration defense costs estimated at $115,000–$180,000 per quarter if SLA slippage persists. |
| reg-02 · sonnet · template_original · repeat 2 | 1 | owner | Engineering and Treasury Operations | not found in source: ['Engineering and Treasury Operations'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · sonnet · template_original · repeat 2 | 1 | time_window | Within 60 days of Committee approval | not found in source: ['60 days'] | prepared_for: Board Risk & Audit Committee + Payments Nodal Regulator |
| reg-02 · sonnet · template_original · repeat 2 | 2 | time_window | Within 30 days of Committee approval | not found in source: ['30 days'] | prepared_for: Board Risk & Audit Committee + Payments Nodal Regulator |
| reg-02 · sonnet · template_original · repeat 2 | 3 | owner | Treasury Operations and Compliance | not found in source: ['Treasury Operations and Compliance'] | However, Treasury Operations acknowledged that failing to separate benign legal-suffix normalization mismatches (146 false-positive accounts) from high-velocity IBAN swap risk (19 cross-border accounts + 8 velocity triggers) creates avoida… |
| reg-02 · sonnet · template_original · repeat 2 | 3 | time_window | Within 45 days of Committee approval | not found in source: ['45 days'] | prepared_for: Board Risk & Audit Committee + Payments Nodal Regulator |
