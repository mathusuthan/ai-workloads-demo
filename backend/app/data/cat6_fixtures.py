"""NovaMart Category 6 (Multi-Agent Swarms & Auto Eng) fixtures and shared monorepo corpus."""

from __future__ import annotations

from typing import Any

# >= 20,000 chars (~6,200-7,000 tokens) so Anthropic Prefix Caching (>4,096-tok floor)
# caches cleanly on both Claude Haiku 5.5 and Claude Sonnet 5.5 across Swarm Sub-Agents.
SHARED_REPO_PREFIX_MARKDOWN = """# NOVAMART INDIA COMMERCE MONOREPO — ARCHITECTURE, DOMAIN CONTRACTS & ENGINEERING STANDARDS (REV 2026.11)

This canonical repository guide is injected as a byte-identical shared prefix for all NovaMart autonomous software engineering swarm agents (`Lead Orchestrator`, `CI/CD Triager`, `Code & Patch Author`, and `Security & Test Critic`). Never quote unrelated services or introduce unpinned third-party dependencies.

---

## MODULE 1: MONOREPO SERVICE TOPOLOGY & DEPLOYMENT MAP

1.1 **Platform Footprint (`services/commerce-core/`):**
- `services/checkout-pricing-svc/src/gst_cart_tax.py` (Tier-0 Critical Path): Computes line subtotals, coupon caps, taxable value, CGST/SGST/IGST splits under CGST Act Sec 15(3), and prepaid wallet tender allocation in Indian Rupees and paise.
- `services/upi-webhook-svc/src/upi_webhook_auth.py` (Tier-0 Payment Perimeter): Verifies NPCI UPI AutoPay & refund settlement webhooks, enforces HMAC-SHA256 constant-time digests, symmetric timestamp replay windows, `event_id` idempotency, and DPDP Act 2023 log masking.
- `services/inventory-lock-svc/src/inventory_reservation.py` (Tier-0 Fulfillment Concurrency): Coordinates atomic multi-fulfillment-center (`FC-BLR-01`, `FC-BOM-02`, `FC-DEL-03`) split-cart stock holds and idempotent release rollbacks without cross-thread lock-order deadlocks.
- `services/cart-orchestrator-svc/src/cart_facade.py`: Upstream BFF calling pricing and reservation gRPC stubs with strict `120ms` p99 SLA.
- `services/ledger-settlement-svc/src/razorpay_reconcile.py`: Nightly settlement consumer comparing committed `gst_cart_tax` breakdowns against gateway settlement CSVs at exact 1-paise tolerance.

1.2 **Runtime Constraints (Python 3.12 · FastAPI · Zero-External-Dep Pure Modules):**
- Core domain modules (`gst_cart_tax.py`, `upi_webhook_auth.py`, `inventory_reservation.py`) MUST depend strictly on the Python standard library (`dataclasses`, `decimal`, `hashlib`, `hmac`, `threading`, `time`, `typing`) so they execute inside hardened `-I` isolated verification sandboxes.
- Prohibitions enforced by static AST CI gate (`AST-SAFE-02`): Never import or invoke `subprocess`, `socket`, `shutil`, `eval`, `exec`, `__import__`, `os.system`, or `open` inside these domain modules.

1.3 **Shared Financial Precision Convention Across Services:**
- All monetary columns in NovaMart's PostgreSQL settlement ledger use `NUMERIC(14, 2)` representing INR exact to 2 decimal places (paise precision).
- Python callers and internal tests may instantiate `CartLine` or `CouponSpec` with `Decimal`, `str`, `int`, or legacy `float` values during rolling upgrades; service boundaries MUST normalize inputs cleanly using `Decimal(str(val))` rather than mutating caller floats into binary IEEE-754 drift.
- Banker's rounding (`ROUND_HALF_EVEN`) is strictly banned on customer-facing invoices and GST tax schedules by NovaMart Statutory Tax Circular `FIN-IND-GST-09`. Always quantize to `Decimal("0.01")` using `decimal.ROUND_HALF_UP`.

1.4 **Warehouse Hub Registry & HSN Slab Codes:**
- `FC-BLR-01` (Karnataka, `KA`): Electronics & Small Appliances, intra-state buyer GST code `29`.
- `FC-BOM-02` (Maharashtra, `MH`): Consumer Electronics & Power Backup, intra-state buyer GST code `27`.
- `FC-DEL-03` (Delhi NCR, `DL`): Audio & Smart Home Accessories, intra-state buyer GST code `07`.
- `FC-HYD-04` (Telangana, `TG`): Split-fulfillment overflow node, intra-state buyer GST code `36`.
- Standard NovaMart GST slabs referenced in pricing tests: `5.00%` (essential peripherals), `12.00%` (cables/adapters), `18.00%` (electronics, power banks, UPS), and `28.00%` (luxury appliances).

1.5 **CI/CD Pipeline & Cost per Verified Outcome (`CpO`) Governance:**
- Traditional swarm dashboards track Cost per Run (`CpR`), hiding wasted retries when unverified patches break staging tests or fail security scans.
- NovaMart Engineering FinOps measures **Cost per Verified Outcome (`CpO`)**:
  `CpO = (Sum of all swarm agent API spend, including failed attempts & retries) / (PRs passing all 10/10 Sandbox CI Unit + Adversarial Security + Static AST Checks)`.
- If a swarm burns `$0.25` per PR and only passes `33%` of adversarial checks (`CpO = $0.75` per verified merge), it is 3x more expensive than advertised.

---

## MODULE 2: ENG-STD-04 — CHECKOUT PRICING & CGST SEC 15(3) PAISE STANDARD

Applies to: `services/checkout-pricing-svc/src/gst_cart_tax.py`

2.1 **Public Module Interface Contract (MUST Preserve Exact Signatures & Field Names):**
```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

PAISE = Decimal("0.01")

@dataclass(frozen=True)
class CartLine:
    sku: str
    unit_price_inr: Decimal
    qty: int
    gst_rate_pct: Decimal = Decimal("18.00")

@dataclass(frozen=True)
class CouponSpec:
    code: str
    discount_pct: Decimal
    max_discount_inr: Decimal
    active: bool = True

@dataclass(frozen=True)
class CartTaxBreakdown:
    gross_subtotal_inr: Decimal
    discount_inr: Decimal
    taxable_subtotal_inr: Decimal
    cgst_inr: Decimal
    sgst_inr: Decimal
    igst_inr: Decimal
    total_gst_inr: Decimal
    wallet_applied_inr: Decimal
    net_payable_inr: Decimal

def compute_checkout_totals(
    lines: list[CartLine],
    coupons: list[CouponSpec],
    wallet_credit_inr: Decimal = Decimal("0.00"),
    inter_state: bool = False,
) -> CartTaxBreakdown: ...
```

2.2 **Mandatory Step-by-Step Invariants for `compute_checkout_totals`:**
1. **Input Conversion & Validation:**
   - Convert numeric inputs safely via `_d(v) = v if isinstance(v, Decimal) else Decimal(str(v))`.
   - Raise `ValueError` if `lines` is empty, or if any line has `int(line.qty) <= 0` or `_d(line.unit_price_inr) < Decimal("0.00")` or `_d(line.gst_rate_pct) < Decimal("0.00")`.
   - Raise `ValueError` if `_d(wallet_credit_inr) < Decimal("0.00")`.
2. **Gross Subtotal (Decimal Paise Precision — Zero Float / Zero `round()`):**
   - For each line: `line_gross = (_d(line.unit_price_inr) * Decimal(int(line.qty))).quantize(PAISE, rounding=ROUND_HALF_UP)`.
   - `gross_subtotal = sum((line_gross for ...), Decimal("0.00")).quantize(PAISE, rounding=ROUND_HALF_UP)`.
   - Static AST policy `AST-DEC-01` explicitly rejects any call to Python's built-in `round(...)` function and requires `Decimal` + `ROUND_HALF_UP`.
3. **Coupon Filtering, Per-Coupon Caps & 50% Stack Ceiling:**
   - Only evaluate coupons where `coupon.active` is `True` (ignore `active=False` coupons). Also raise `ValueError` if `_d(c.discount_pct) < Decimal("0")` or `_d(c.max_discount_inr) < Decimal("0")`.
   - For each active coupon, compute raw percentage discount on `gross_subtotal`:
     `raw_disc = (gross_subtotal * (_d(c.discount_pct) / Decimal("100"))).quantize(PAISE, rounding=ROUND_HALF_UP)`
   - Clamp each coupon by its individual rupee ceiling:
     `capped_disc = min(raw_disc, _d(c.max_discount_inr).quantize(PAISE, rounding=ROUND_HALF_UP))`
   - Sum individual capped discounts into `stacked_discount`, then clamp the total stacked discount across the cart to **50% of `gross_subtotal`**:
     `max_stack_cap = (gross_subtotal * Decimal("0.50")).quantize(PAISE, rounding=ROUND_HALF_UP)`
     `total_discount = min(stacked_discount, max_stack_cap).quantize(PAISE, rounding=ROUND_HALF_UP)`
4. **Taxable Value Before Prepaid Wallet (CGST Act Sec 15(3) Compliance):**
   - Under India GST Section 15(3), commercial promo coupons lower transaction taxable value, whereas prepaid wallet balance (`NovaPay Wallet` / stored-value tender) is a post-tax **payment tender**, NEVER a pre-tax trade discount.
   - `taxable_subtotal = max(Decimal("0.00"), gross_subtotal - total_discount).quantize(PAISE, rounding=ROUND_HALF_UP)`.
   - Deducting `wallet_credit_inr` before GST calculation under-remits statutory GST and triggers GSTR-1/3B reconciliation penalties.
5. **CGST / SGST / IGST Split (`total_gst` on `taxable_subtotal`):**
   - Compute `total_gst` over `taxable_subtotal`:
     - If `gross_subtotal == Decimal("0.00")` or `taxable_subtotal == Decimal("0.00")`: `total_gst = Decimal("0.00")`.
     - If all lines share a single GST slab rate `r`: `total_gst = (taxable_subtotal * r / Decimal("100")).quantize(PAISE, rounding=ROUND_HALF_UP)`.
     - If mixed slab rates exist across lines: allocate `taxable_subtotal` proportionally per line `line_taxable = line_gross * taxable_subtotal / gross_subtotal`, quantize each `(line_taxable * _d(line.gst_rate_pct) / Decimal("100")).quantize(PAISE, rounding=ROUND_HALF_UP)`, and sum into `total_gst`.
   - Split tax cleanly to exact paise conservation (`cgst + sgst + igst == total_gst`):
     - If `inter_state` is `True`: `igst = total_gst`, `cgst = Decimal("0.00")`, `sgst = Decimal("0.00")`.
     - If `inter_state` is `False`: `cgst = (total_gst / Decimal("2")).quantize(PAISE, rounding=ROUND_HALF_UP)`, `sgst = (total_gst - cgst).quantize(PAISE, rounding=ROUND_HALF_UP)`, `igst = Decimal("0.00")`. (Note: assigning `sgst = total_gst - cgst` guarantees odd-paise tax like `₹0.03` splits into `₹0.02 + ₹0.01` with zero 1-paise leak!)
6. **Prepaid Wallet Application & Final Net Payable:**
   - `gross_total = (taxable_subtotal + total_gst).quantize(PAISE, rounding=ROUND_HALF_UP)`
   - `wallet_applied = min(gross_total, _d(wallet_credit_inr).quantize(PAISE, rounding=ROUND_HALF_UP)).quantize(PAISE, rounding=ROUND_HALF_UP)`
   - `net_payable = (gross_total - wallet_applied).quantize(PAISE, rounding=ROUND_HALF_UP)`

---

## MODULE 3: SEC-STD-02 — NPCI UPI AUTOPAY WEBHOOK AUTH & DPDP ACT 2023 REDACTION

Applies to: `services/upi-webhook-svc/src/upi_webhook_auth.py`

3.1 **Public Module Interface Contract (MUST Preserve Exact Signatures & Attributes):**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class WebhookResult:
    accepted: bool
    reason: str
    refund_id: str | None = None

class UpiWebhookProcessor:
    def __init__(self, webhook_secret: str, replay_window_seconds: int = 300) -> None: ...
    # Required public instance attributes:
    # self.webhook_secret: str
    # self.replay_window_seconds: int
    # self.processed_events: set[str]
    # self.refund_ledger: list[dict[str, object]]
    # self.audit_log: list[str]

    def verify_and_process(
        self,
        *,
        event_id: str,
        raw_body: str,
        signature_header: str,
        timestamp: int,
        now_ts: int,
        payer_vpa: str,
        mobile: str,
        amount_paise: int,
    ) -> WebhookResult: ...
```

3.2 **Mandatory Security & Privacy Invariants for `UpiWebhookProcessor`:**
1. **DPDP Act 2023 Redaction Helper (Applied BEFORE Every `audit_log.append` & `refund_ledger` Entry):**
   - Never log raw `payer_vpa` or raw `mobile` anywhere in `self.audit_log` or `self.refund_ledger` (neither on accepted webhooks nor on rejected/invalid attempts!).
   - `_mask_vpa(vpa)`: split on `"@"`; for `local@handle`, preserve at most the first 2 characters (`prefix = local[:2] if len(local) > 2 else local[:1]`), mask the remainder as `"***"`, yielding `f"{prefix}***@{handle}"` (e.g., `rahul.sharma@okicici` -> `ra***@okicici`). Never expose `rahul.sharma` in logs.
   - `_mask_mobile(mobile)`: strip non-digits or inspect tail digits, keep only the last 4 digits visible and replace all earlier digits with `*` (e.g., `"+919876543210"` -> `"******3210"` or `"+91******3210"`). Never leave 6+ contiguous mobile digits unmasked in logs.
2. **Symmetric Replay Timestamp Freshness Check (`abs(now_ts - timestamp) <= replay_window_seconds`):**
   - Reject both expired/stale replays (`now_ts - timestamp > replay_window_seconds`) AND future clock-skew forged timestamps (`timestamp - now_ts > replay_window_seconds`).
   - On failure: append masked audit entry to `self.audit_log` and return `WebhookResult(accepted=False, reason="STALE_OR_FUTURE_TIMESTAMP", refund_id=None)` without touching `processed_events` or `refund_ledger`.
3. **Canonical HMAC-SHA256 Binding (`f"{int(timestamp)}.{raw_body}"`) & Constant-Time Comparison:**
   - Normalize `signature_header`: strip whitespace, strip optional leading `"sha256="` prefix case-insensitively, convert to lowercase ASCII.
   - Compute expected HMAC digest over timestamp-bound canonical payload:
     `canonical = f"{int(timestamp)}.{raw_body}"`
     `expected = hmac.new(self.webhook_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()`
   - Static AST rule `AST-SEC-01` **mandates** calling `hmac.compare_digest(expected, provided_hex)` and **forbids** using `==` or `!=` to compare signatures/digests (prevents CWE-208 timing side channels).
   - Verify `provided_hex` is non-empty 64-char hex (if non-ASCII or mismatched length, `hmac.compare_digest` cleanly returns `False` when typed `str` ASCII is enforced; guard `.isascii()` before `compare_digest`).
   - On signature mismatch: append masked audit entry to `self.audit_log` and return `WebhookResult(accepted=False, reason="INVALID_SIGNATURE", refund_id=None)`.
4. **Positive Paise Guard (`amount_paise > 0`):**
   - Reject `int(amount_paise) <= 0` BEFORE marking `event_id` processed or creating ledger rows. Append masked audit entry and return `WebhookResult(accepted=False, reason="INVALID_AMOUNT", refund_id=None)`.
5. **`event_id` Idempotency & Single Refund Execution:**
   - Reject empty `event_id` or `event_id in self.processed_events`. On duplicate: append masked audit entry and return `WebhookResult(accepted=False, reason="DUPLICATE_EVENT_REPLAY", refund_id=None)`.
   - On valid new event: add `event_id` to `self.processed_events`, create `refund_id = f"REF-{event_id}"`, append structured redacted record to `self.refund_ledger`, append masked audit log line, and return `WebhookResult(accepted=True, reason="PROCESSED", refund_id=refund_id)`.

---

## MODULE 4: CONC-STD-07 — DEADLOCK-FREE ATOMIC SPLIT-CART INVENTORY RESERVATION

Applies to: `services/inventory-lock-svc/src/inventory_reservation.py`

4.1 **Public Module Interface Contract (MUST Preserve Exact Signatures & Classes):**
```python
from dataclasses import dataclass

class InsufficientStockError(Exception):
    pass

@dataclass(frozen=True)
class CartItemReq:
    fc_id: str
    sku_id: str
    qty: int

@dataclass(frozen=True)
class ReservationReceipt:
    reservation_id: str
    idempotency_key: str
    items: tuple[tuple[str, str, int], ...]

class InventoryReservationManager:
    def __init__(self, initial_stock: dict[tuple[str, str], int]) -> None: ...
    def get_stock(self, fc_id: str, sku_id: str) -> int: ...
    def reserve_split_cart(self, idempotency_key: str, lines: list[CartItemReq]) -> ReservationReceipt: ...
    def release_reservation(self, reservation_id: str) -> bool: ...
```

4.2 **Mandatory Concurrency & Atomicity Invariants for `InventoryReservationManager`:**
1. **Fail-Fast Input Validation (Before Locking or Mutation):**
   - Raise `ValueError` if `not idempotency_key` or `not lines` or any line has `int(line.qty) <= 0` or empty `fc_id`/`sku_id`.
2. **Idempotent Retry Short-Circuit:**
   - Check `idempotency_key` under `self._meta_lock`: if previously reserved, immediately return the stored `ReservationReceipt` without deducting inventory a second time!
3. **Intra-Cart `(fc_id, sku_id)` Aggregation (No Self-Deadlock on Duplicate SKUs):**
   - Before computing locks, aggregate line quantities into `agg: dict[tuple[str, str], int] = {}` (`agg[(line.fc_id, line.sku_id)] = agg.get(key, 0) + int(line.qty)`).
   - Otherwise, if a single cart contains two separate `CartItemReq` entries for `("FC-BLR-01", "NM-UPS-2200")` (e.g., main unit + bundle add-on), acquiring the non-reentrant `threading.Lock` twice in one thread causes an immediate self-deadlock AND mischecks combined stock!
4. **Canonical Global Lock Ordering (`sorted(keys)`) — Zero AB-BA Deadlocks:**
   - Maintain one `threading.Lock` per `(fc_id, sku_id)` key in `self._locks`, accessed safely via `self._meta_lock`.
   - Static AST rule `AST-CONC-01` enforces `sorted(...)` lock ordering across acquired keys:
     `ordered_keys = sorted(agg.keys())`
   - Acquire each lock sequentially in `ordered_keys` order, tracking `acquired: list[threading.Lock]`, wrapped in `try: ... finally:` releasing `for lk in reversed(acquired): lk.release()`.
5. **All-or-Nothing Atomic Stock Verification & Deduction:**
   - While holding all `ordered_keys` locks, verify EVERY `self._stock.get(key, 0) >= qty` BEFORE deducting ANY key!
   - If any SKU has insufficient stock, raise `InsufficientStockError` cleanly without mutating any SKU count and without storing `idempotency_key` (so a subsequent valid attempt or restock can succeed).
   - If all SKUs pass: deduct `self._stock[k] -= q` for every key, build `receipt = ReservationReceipt(reservation_id=f"RES-{idempotency_key}", idempotency_key=idempotency_key, items=tuple((k[0], k[1], agg[k]) for k in ordered_keys))`, store receipt and active allocation map under `self._meta_lock`, and return `receipt`.
6. **Idempotent `release_reservation(reservation_id: str) -> bool`:**
   - Look up `reservation_id` in `self._active_reservations`; if not found or already in `self._released_ids`, return `False` cleanly (double-release MUST NOT double-increment stock!).
   - Otherwise acquire the reservation's `(fc_id, sku_id)` locks in `sorted(...)` order, re-verify not yet released under lock/meta_lock, mark `reservation_id` in `self._released_ids`, increment `self._stock[k] += q`, and return `True`.

---

## MODULE 5: REFERENCE NEIGHBOR INTERFACES & SANDBOX CHECK RULES

5.1 **`services/cart-orchestrator-svc/src/cart_facade.py` Contract Summary:**
- Expects `CartTaxBreakdown` fields `gross_subtotal_inr`, `discount_inr`, `taxable_subtotal_inr`, `cgst_inr`, `sgst_inr`, `igst_inr`, `total_gst_inr`, `wallet_applied_inr`, `net_payable_inr` to ALL be `Decimal` instances quantized to `0.01`.
- Expects `InventoryReservationManager.get_stock(fc_id, sku_id)` to return `int`.

5.2 **`services/ledger-settlement-svc/src/razorpay_reconcile.py` Contract Summary:**
- Expects `UpiWebhookProcessor.refund_ledger` entries to include `"event_id"`, `"refund_id"`, and `"amount_paise"`, with zero unmasked VPA local parts or raw 10-digit mobile numbers.

5.3 **AST & Security Policies Checked Automatically by `PR-SANDBOX-GATE-01`:**
- `AST-SAFE-02`: Zero unsafe dynamic execution or OS/network imports (`subprocess`, `socket`, `shutil`, `eval`, `exec`, `__import__`, `os.system`, `open`).
- `AST-DEC-01`: Checkout pricing module imports `Decimal` & `ROUND_HALF_UP` from `decimal` and calls built-in `round()` zero times.
- `AST-SEC-01`: UPI webhook auth module invokes `hmac.compare_digest` and contains zero equality (`==`/`!=`) comparisons involving variables named `sig*`, `hmac*`, or `digest*`.
- `AST-CONC-01`: Inventory reservation module uses `sorted(...)` to order `(fc_id, sku_id)` lock keys consistently prior to lock acquisition and uses `threading.Lock` cleanup.

---

## MODULE 6: SWARM ROLE PROTOCOL & TOKENOMICS GOVERNANCE

6.1 **Orchestrator Plan Agent:** Produce a crisp 5-bullet root-cause hypothesis and remediation plan referencing the exact standard (`ENG-STD-04`, `SEC-STD-02`, or `CONC-STD-07`) and failure mode.
6.2 **CI/CD Triager Agent:** Map exact stack traces/assertions to the broken invariant lines in the target file. Keep handoff concise (`<= 180` words) without repeating sibling logs.
6.3 **Code & Patch Author Agent:** Output the **complete, self-contained corrected Python file** inside a single fenced ```python code block preserving all public class/function names and dataclass fields verbatim. Zero placeholders or `# ...` ellipses allowed.
6.4 **Security & Test Critic Agent:** Audit the proposed patch against every edge case (`Decimal` half-up, GST Sec 15(3) before wallet, `hmac.compare_digest`, timestamp skew bounds, DPDP log redaction, sorted lock order + duplicate-SKU aggregation + rollback idempotency) and approve or specify exact line defects.
6.5 **Lead Orchestrator Merge Gate Agent:** Verify `PR-SANDBOX-GATE-01` (`10/10` pass) and issue the final PR merge sign-off memo with Verified `CpO` telemetry.
"""


# >= 45,000 chars (~14,000+ tokens) of unfiltered sibling files, build logs, and OTel span JSON dumps
# injected into Rung 1's shared uncached omnibus bus so 5 turns exceed 100k+ Band 5 prompt tokens.
_OTEL_LINES = "\n".join(
    f'{{"ts":"2026-11-17T14:{10 + (i // 60):02d}:{i % 60:02d}.{100 + (i * 7) % 899}Z","svc":"{"checkout-pricing-svc" if i % 3 == 0 else "upi-webhook-svc" if i % 3 == 1 else "inventory-lock-svc"}","pod":"novamart-prod-ap-south-1-{chr(97 + (i % 3))}-{1000 + i}","trace_id":"nm992a000{i:04d}f8c2e1","span":"{"grpc.CalculateTotals" if i % 3 == 0 else "http.POST /hooks/npci/upi" if i % 3 == 1 else "lock.ReserveMultiFC"}","fc_hub":"{"FC-BLR-01" if i % 3 == 0 else "FC-BOM-02" if i % 3 == 1 else "FC-DEL-03"}","latency_ms":{12 + (i * 19) % 185},"status":"{"WARN_RETRY" if i % 11 == 0 else "OK"}","mem_mb":{240 + (i * 3) % 190},"worker_tid":{40000 + i}}}'
    for i in range(185)
)

UNFILTERED_REPO_AND_TELEMETRY_NOISE = f"""
### UNFILTERED MONOREPO SIBLING SERVICES & CI CONTAINER DUMPS (NO CONTEXT ISOLATION)

#### File 1: `services/catalog-sync-worker/src/hsn_catalog_indexer.py` (Unrelated Batch Sync)
```python
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable

HSN_CHAPTER_OVERRIDES = {{
    "8504": {{"slab_pct": 18, "cess_pct": 0, "category": "UPS & Power Conditioners", "bis_crs": True}},
    "8507": {{"slab_pct": 18, "cess_pct": 0, "category": "Li-Ion Power Banks & Cells", "un3480": True}},
    "8517": {{"slab_pct": 18, "cess_pct": 0, "category": "Enterprise Routers & Wi-Fi 7", "wpc_eta": True}},
    "8518": {{"slab_pct": 18, "cess_pct": 0, "category": "Smart Speakers & Soundbars", "bis_crs": True}},
    "8528": {{"slab_pct": 18, "cess_pct": 0, "category": "4K QLED & OLED Televisions", "bis_crs": True}},
    "8544": {{"slab_pct": 12, "cess_pct": 0, "category": "Braided Type-C & HDMI Cables", "bis_crs": False}},
    "8415": {{"slab_pct": 28, "cess_pct": 0, "category": "Inverter Split Air Conditioners", "bee_star": True}},
}}

@dataclass
class CatalogSyncBatch:
    batch_id: str
    seller_gstin: str
    fc_hub: str
    sku_payloads: list[dict[str, str]] = field(default_factory=list)
    rejected_skus: list[str] = field(default_factory=list)

def compute_catalog_fingerprint(payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

def normalize_seller_sku_feed(batch: CatalogSyncBatch) -> dict[str, dict[str, object]]:
    normalized: dict[str, dict[str, object]] = {{}}
    for row in batch.sku_payloads:
        sku = row.get("sku_id", "").strip().upper()
        hsn = row.get("hsn_code", "8504")[:4]
        rule = HSN_CHAPTER_OVERRIDES.get(hsn, HSN_CHAPTER_OVERRIDES["8504"])
        if not sku or len(batch.seller_gstin) != 15:
            batch.rejected_skus.append(sku or "EMPTY_SKU")
            continue
        normalized[sku] = {{
            "sku": sku,
            "hsn": hsn,
            "gst_slab": rule["slab_pct"],
            "fingerprint": compute_catalog_fingerprint(row),
            "fc_hub": batch.fc_hub,
        }}
    return normalized
```

#### File 2: `services/loyalty-points-cron/src/novacoins_expiry_job.py` (Unrelated Nightly Loyalty Job)
```python
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass
class NovaCoinLedgerRow:
    customer_id: str
    tier: str
    earned_coins: int
    redeemed_coins: int
    credited_on: date

def project_monthly_coin_breakage(rows: list[NovaCoinLedgerRow], as_of: date) -> dict[str, int]:
    expiry_cutoff = as_of - timedelta(days=365)
    active_balance = 0
    expiring_next_30d = 0
    warn_cutoff = expiry_cutoff + timedelta(days=30)
    for row in rows:
        net = max(0, row.earned_coins - row.redeemed_coins)
        if row.credited_on <= expiry_cutoff or net == 0:
            continue
        active_balance += net
        if row.credited_on <= warn_cutoff:
            expiring_next_30d += net
    return {{"active_coins": active_balance, "expiring_30d": expiring_next_30d}}
```

#### File 3: `services/invoice-pdf-renderer/src/irn_qr_layout.py` (Unrelated PDF Layout Engine)
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TaxInvoiceHeaderSpec:
    supplier_gstin: str
    buyer_gstin: str
    irn_hash: str
    ack_no: str
    place_of_supply_code: str
    reverse_charge: bool = False

def build_e_invoice_qr_banner(header: TaxInvoiceHeaderSpec) -> str:
    lines = [
        f"SUPPLIER_GSTIN={{header.supplier_gstin}}",
        f"BUYER_GSTIN={{header.buyer_gstin}}",
        f"POS={{header.place_of_supply_code}}",
        f"RCM={{'Y' if header.reverse_charge else 'N'}}",
        f"IRN={{header.irn_hash}}",
        f"ACK={{header.ack_no}}",
    ]
    return " | ".join(lines)
```

#### Raw GitHub Actions CI Runner Setup & Dependency Lock Transcript (Verbose Unfiltered Build Log)
```text
[runner ap-south-1b] Pulling ghcr.io/novamart/py312-ci-base:2026.11.17...
[runner ap-south-1b] digest: sha256:9c8a1f3d00e1bc45210a0841c3fe1210aa9b3e4f82c10e10002d91e23af120bc
[runner ap-south-1b] Collecting fastapi==0.135.2 / pydantic==2.12.5 / sqlalchemy==2.0.48 / grpcio==1.72.0 / opentelemetry-sdk==1.32.0
[runner ap-south-1b] Running ruff check services/ --statistics
[runner ap-south-1b] Running mypy --strict services/cart-orchestrator-svc services/catalog-sync-worker
[runner ap-south-1b] Running bandit -ll -r services/upi-webhook-svc/
[runner ap-south-1b] [WARN] bandit B324/CWE-208 skipped in legacy CI profile -- manual critic required
[runner ap-south-1b] Launching ephemeral pytest container with PYTHONHASHSEED=20261117...
```

#### Production OpenTelemetry Span Dump (135 Unfiltered Lines Forwarded to Swarm Omnibus Bus)
```jsonlines
{_OTEL_LINES}
```
"""


# ---------------- Preset 1: CI/CD Failure Triage (checkout-pricing-svc) ----------------

BUGGY_CHECKOUT_CODE = """\"\"\"NovaMart Checkout Pricing & GST Calculation Engine (Legacy Buggy Build).\"\"\"

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CartLine:
    sku: str
    unit_price_inr: Decimal
    qty: int
    gst_rate_pct: Decimal = Decimal("18.00")


@dataclass(frozen=True)
class CouponSpec:
    code: str
    discount_pct: Decimal
    max_discount_inr: Decimal
    active: bool = True


@dataclass(frozen=True)
class CartTaxBreakdown:
    gross_subtotal_inr: Decimal
    discount_inr: Decimal
    taxable_subtotal_inr: Decimal
    cgst_inr: Decimal
    sgst_inr: Decimal
    igst_inr: Decimal
    total_gst_inr: Decimal
    wallet_applied_inr: Decimal
    net_payable_inr: Decimal


def compute_checkout_totals(
    lines: list[CartLine],
    coupons: list[CouponSpec],
    wallet_credit_inr: Decimal = Decimal("0.00"),
    inter_state: bool = False,
) -> CartTaxBreakdown:
    # BUG 1: Uses IEEE-754 float and Python round() (banker's rounding / drift)
    # BUG 2: Never validates qty <= 0 or negative unit prices
    gross = sum(float(line.unit_price_inr) * line.qty for line in lines)

    # BUG 3: Applies inactive coupons, ignores per-coupon max_discount_inr and 50% stack cap
    discount = 0.0
    for c in coupons:
        discount += gross * (float(c.discount_pct) / 100.0)

    # BUG 4: Deducts prepaid wallet BEFORE calculating statutory GST (violates CGST Sec 15(3))
    wallet_used = min(gross - discount, float(wallet_credit_inr))
    taxable = max(0.0, gross - discount - wallet_used)

    avg_rate = float(lines[0].gst_rate_pct) if lines else 18.0
    total_gst = round(taxable * (avg_rate / 100.0), 2)

    if inter_state:
        igst = total_gst
        cgst = 0.0
        sgst = 0.0
    else:
        # BUG 5: Odd paise total_gst split naively via round/2 loses 1 paise conservation
        cgst = round(total_gst / 2.0, 2)
        sgst = round(total_gst / 2.0, 2)
        igst = 0.0

    net_payable = round(taxable + total_gst, 2)
    return CartTaxBreakdown(
        gross_subtotal_inr=Decimal(str(round(gross, 2))),
        discount_inr=Decimal(str(round(discount, 2))),
        taxable_subtotal_inr=Decimal(str(round(taxable, 2))),
        cgst_inr=Decimal(str(cgst)),
        sgst_inr=Decimal(str(sgst)),
        igst_inr=Decimal(str(igst)),
        total_gst_inr=Decimal(str(total_gst)),
        wallet_applied_inr=Decimal(str(round(wallet_used, 2))),
        net_payable_inr=Decimal(str(net_payable)),
    )
"""


# ---------------- Preset 2: Security Threat Hunting (upi-webhook-svc) ----------------

BUGGY_UPI_WEBHOOK_CODE = """\"\"\"NPCI UPI AutoPay & Refund Webhook Handler (Vulnerable Build).\"\"\"

from dataclasses import dataclass
import hashlib
import hmac


@dataclass(frozen=True)
class WebhookResult:
    accepted: bool
    reason: str
    refund_id: str | None = None


class UpiWebhookProcessor:
    def __init__(self, webhook_secret: str, replay_window_seconds: int = 300) -> None:
        self.webhook_secret = webhook_secret
        self.replay_window_seconds = replay_window_seconds
        self.processed_events: set[str] = set()
        self.refund_ledger: list[dict[str, object]] = []
        self.audit_log: list[str] = []

    def verify_and_process(
        self,
        *,
        event_id: str,
        raw_body: str,
        signature_header: str,
        timestamp: int,
        now_ts: int,
        payer_vpa: str,
        mobile: str,
        amount_paise: int,
    ) -> WebhookResult:
        # VULN 1 (DPDP Act 2023): Logs raw payer_vpa and 10-digit mobile into audit_log
        self.audit_log.append(f"recv event={event_id} vpa={payer_vpa} mobile={mobile} ts={timestamp}")

        # VULN 2: Signs raw_body ONLY instead of "{timestamp}.{raw_body}" and never checks timestamp window
        expected_digest = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # VULN 3 (CWE-208): Non-constant-time == comparison & breaks on sha256= prefix
        if signature_header != expected_digest:
            return WebhookResult(accepted=False, reason="INVALID_SIGNATURE", refund_id=None)

        # VULN 4: Never checks amount_paise <= 0 or duplicate event_id idempotency
        refund_id = f"REF-{event_id}"
        self.processed_events.add(event_id)
        self.refund_ledger.append(
            {
                "event_id": event_id,
                "refund_id": refund_id,
                "amount_paise": amount_paise,
                "payer_vpa": payer_vpa,
                "mobile": mobile,
            }
        )
        return WebhookResult(accepted=True, reason="PROCESSED", refund_id=refund_id)
"""


# ---------------- Preset 3: Autonomous Feature Dev (inventory-lock-svc) ----------------

BUGGY_INVENTORY_CODE = """\"\"\"Multi-FC Split-Cart Inventory Reservation Manager (Incomplete Naive Stub).\"\"\"

from dataclasses import dataclass
import threading
import time


class InsufficientStockError(Exception):
    pass


@dataclass(frozen=True)
class CartItemReq:
    fc_id: str
    sku_id: str
    qty: int


@dataclass(frozen=True)
class ReservationReceipt:
    reservation_id: str
    idempotency_key: str
    items: tuple[tuple[str, str, int], ...]


class InventoryReservationManager:
    def __init__(self, initial_stock: dict[tuple[str, str], int]) -> None:
        self._stock: dict[tuple[str, str], int] = dict(initial_stock)
        self._locks: dict[tuple[str, str], threading.Lock] = {
            k: threading.Lock() for k in initial_stock
        }
        self._active_reservations: dict[str, list[CartItemReq]] = {}

    def get_stock(self, fc_id: str, sku_id: str) -> int:
        return int(self._stock.get((fc_id, sku_id), 0))

    def reserve_split_cart(
        self,
        idempotency_key: str,
        lines: list[CartItemReq],
    ) -> ReservationReceipt:
        # BUG 1: No validation for empty lines or qty <= 0, no idempotency cache,
        # no duplicate-SKU aggregation, and unsorted lock acquisition causes AB-BA deadlocks!
        for line in lines:
            key = (line.fc_id, line.sku_id)
            lock = self._locks.setdefault(key, threading.Lock())
            lock.acquire()
            time.sleep(0.002)
            # BUG 2: Partial mutation before checking later items leaks stock and locks!
            if self._stock.get(key, 0) < line.qty:
                raise InsufficientStockError(f"Short stock for {key}")
            self._stock[key] -= line.qty

        res_id = f"RES-{idempotency_key}"
        self._active_reservations[res_id] = list(lines)
        return ReservationReceipt(
            reservation_id=res_id,
            idempotency_key=idempotency_key,
            items=tuple((ln.fc_id, ln.sku_id, ln.qty) for ln in lines),
        )

    def release_reservation(self, reservation_id: str) -> bool:
        # BUG 3: Does not lock keys in canonical order or prevent double-release inflation
        items = self._active_reservations.get(reservation_id)
        if not items:
            return False
        for ln in items:
            key = (ln.fc_id, ln.sku_id)
            self._stock[key] = self._stock.get(key, 0) + ln.qty
        return True
"""


CAT6_PRESETS: list[dict[str, Any]] = [
    {
        "id": "inc-01",
        "use_case_tag": "CI/CD Failure Triage",
        "pr_id": "PR-4812",
        "service_name": "checkout-pricing-svc",
        "target_file": "services/checkout-pricing-svc/src/gst_cart_tax.py",
        "module_filename": "gst_cart_tax.py",
        "title": "Incident 1: Checkout GST Sec 15(3), Coupon Cap & Float Paise Drift",
        "subtitle": (
            "Nightly razorpay reconciliation flagged INR 1,420 GST under-remittance when customers applied "
            "NovaPay prepaid wallet + stacked Diwali coupons (`FLOAT_DRIFT` + `PRE_GST_WALLET` + `CAP_BYPASS`)."
        ),
        "severity": "P0 · Tax Compliance Break",
        "standard_ref": "ENG-STD-04",
        "buggy_code": BUGGY_CHECKOUT_CODE,
        "ci_failure_log": """=========================== short test summary info ============================
FAILED tests/test_gst_cart_tax.py::test_wallet_applied_post_gst_sec15_3 - AssertionError: taxable_subtotal reduced by wallet 500.00 (expected 2400.00, got 1900.00)
FAILED tests/test_gst_cart_tax.py::test_inactive_and_50pct_coupon_stack_cap - AssertionError: total discount 1850.00 exceeded 50% cap 1500.00 & included INACTIVE_CODE
FAILED tests/test_gst_cart_tax.py::test_decimal_half_up_odd_paise_conservation - AssertionError: cgst(1.50)+sgst(1.50) != total_gst(3.01) or float drift on 19.99*3
FAILED tests/test_gst_cart_tax.py::test_negative_qty_and_price_rejected - DID NOT RAISE ValueError for qty=0 / unit_price=-10.00""",
    },
    {
        "id": "inc-02",
        "use_case_tag": "Security Threat Hunting",
        "pr_id": "SEC-772",
        "service_name": "upi-webhook-svc",
        "target_file": "services/upi-webhook-svc/src/upi_webhook_auth.py",
        "module_filename": "upi_webhook_auth.py",
        "title": "Threat Hunt 2: NPCI UPI Spoofed Replay, CWE-208 Timing Leak & DPDP PII Exposure",
        "subtitle": (
            "Red-team audit found missing `{ts}.{body}` HMAC binding, `!=` timing oracle, absent 300s "
            "timestamp check, duplicate `event_id` double-refunds, and plain VPA/mobile strings in logs."
        ),
        "severity": "P0 · CWE-208 + DPDP Violation",
        "standard_ref": "SEC-STD-02",
        "buggy_code": BUGGY_UPI_WEBHOOK_CODE,
        "ci_failure_log": """======================== security threat-hunt reproducer =======================
EXPLOIT FAIL [SEC-01] Replayed valid webhook from 900s ago was ACCEPTED (expected STALE_OR_FUTURE_TIMESTAMP)
EXPLOIT FAIL [SEC-02] Duplicate event_id=EVT-9921 triggered 2nd refund row in refund_ledger (expected DUPLICATE_EVENT_REPLAY)
EXPLOIT FAIL [SEC-03] Plaintext 'rahul.sharma@okicici' & '+919876543210' leaked into self.audit_log (DPDP Act 2023 breach)
EXPLOIT FAIL [AST-SEC-01] Found non-constant-time comparison `signature_header != expected_digest` (CWE-208)""",
    },
    {
        "id": "inc-03",
        "use_case_tag": "Autonomous Feature Dev",
        "pr_id": "FEAT-619",
        "service_name": "inventory-lock-svc",
        "target_file": "services/inventory-lock-svc/src/inventory_reservation.py",
        "module_filename": "inventory_reservation.py",
        "title": "Feature 3: Deadlock-Free Multi-FC Split-Cart Reservation & Idempotent Rollback",
        "subtitle": (
            "Festive flash-sale feature requires atomic split-FC reservations (`FC-BLR-01` + `FC-BOM-02` + "
            "`FC-DEL-03`) with sorted locking, same-SKU aggregation, all-or-nothing abort, and 1-shot release."
        ),
        "severity": "P1 · Feature Spec + Concurrency",
        "standard_ref": "CONC-STD-07",
        "buggy_code": BUGGY_INVENTORY_CODE,
        "ci_failure_log": """====================== feature acceptance test suite ===========================
TIMEOUT [CONC-01] Concurrent reverse-order carts timed out in AB-BA lock deadlock across FC-BLR-01 <-> FC-BOM-02
FAILED  [CONC-02] Partial-stock cart deducted FC-BLR-01 before failing on FC-DEL-03 & left lock unreleased
FAILED  [CONC-03] Duplicate (fc_id, sku_id) lines in one cart self-deadlocked non-reentrant threading.Lock
FAILED  [CONC-04] Second release_reservation() call double-restored stock (expected False return)""",
    },
]
