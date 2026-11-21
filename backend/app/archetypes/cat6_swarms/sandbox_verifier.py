"""Isolated Python (-I) Sandbox + Static AST Verifier (PR-SANDBOX-GATE-01) for Category 6."""

from __future__ import annotations

import ast
import difflib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any

from app.data.cat6_fixtures import CAT6_PRESETS

BLOCKED_MODULES = {
    "subprocess",
    "socket",
    "shutil",
    "urllib",
    "http",
    "requests",
    "ctypes",
    "importlib",
    "pty",
    "os",
    "pathlib",
    "sys",
}
BLOCKED_CALL_NAMES = {"eval", "exec", "__import__", "open", "compile"}
BLOCKED_ATTR_NAMES = {"system", "popen", "Popen"}


def extract_python_code(raw_text: str) -> str:
    """Extract the largest valid Python fenced block from LLM output, falling back to raw text."""
    text = (raw_text or "").strip()
    if not text:
        return ""

    blocks = re.findall(r"```(?:python|py)?\s*\n([\s\S]*?)```", text, flags=re.IGNORECASE)
    if blocks:
        valid_blocks: list[str] = []
        for blk in blocks:
            candidate = blk.strip()
            if not candidate:
                continue
            try:
                ast.parse(candidate)
                valid_blocks.append(candidate)
            except SyntaxError:
                continue
        if valid_blocks:
            return max(valid_blocks, key=len)
        return max((b.strip() for b in blocks if b.strip()), key=len, default=text)

    try:
        ast.parse(text)
        return text
    except SyntaxError:
        return text


def _contains_sig_identifier(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            low = child.id.lower()
            if any(tok in low for tok in ("sig", "digest", "hmac")):
                return True
        elif isinstance(child, ast.Attribute):
            low = child.attr.lower()
            if any(tok in low for tok in ("sig", "digest", "hmac")):
                return True
    return False


def verify_ast_policies(code: str, preset_id: str) -> tuple[bool, list[dict[str, Any]]]:
    """Run AST-SAFE-02 and preset-specific static AST policy gates."""
    checks: list[dict[str, Any]] = []
    if not code.strip():
        return False, [
            {
                "check_id": "AST-SAFE-02",
                "category": "ast",
                "name": "Static AST parse & unsafe API guard",
                "passed": False,
                "detail": "Empty patch output; cannot parse AST.",
            },
            {
                "check_id": "AST-PRESET-RULE",
                "category": "ast",
                "name": "Standard-specific static invariant",
                "passed": False,
                "detail": "Skipped due to empty patch.",
            },
        ]

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, [
            {
                "check_id": "AST-SAFE-02",
                "category": "ast",
                "name": "Static AST parse & unsafe API guard",
                "passed": False,
                "detail": f"SyntaxError at line {exc.lineno}: {exc.msg}",
            },
            {
                "check_id": "AST-PRESET-RULE",
                "category": "ast",
                "name": "Standard-specific static invariant",
                "passed": False,
                "detail": "Skipped due to SyntaxError.",
            },
        ]

    unsafe_hits: list[str] = []
    imported_names: set[str] = set()
    bare_calls: set[str] = set()
    attr_calls: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                imported_names.add(alias.name)
                if root_mod in BLOCKED_MODULES:
                    unsafe_hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root_mod = mod.split(".")[0]
            if root_mod in BLOCKED_MODULES:
                unsafe_hits.append(f"from {mod} import ...")
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                bare_calls.add(node.func.id)
                if node.func.id in BLOCKED_CALL_NAMES:
                    unsafe_hits.append(f"call {node.func.id}()")
            elif isinstance(node.func, ast.Attribute):
                attr_calls.add(node.func.attr)
                if node.func.attr in BLOCKED_ATTR_NAMES:
                    unsafe_hits.append(f"attr call .{node.func.attr}()")

    safe_ok = len(unsafe_hits) == 0
    checks.append(
        {
            "check_id": "AST-SAFE-02",
            "category": "ast",
            "name": "Sandbox static AST safety guard",
            "passed": safe_ok,
            "detail": (
                "Clean stdlib-only module AST; zero blocked OS/eval/network symbols."
                if safe_ok
                else f"Blocked unsafe constructs detected: {', '.join(sorted(set(unsafe_hits)))}"
            ),
        }
    )

    if preset_id == "inc-01":
        has_dec = "Decimal" in imported_names or "decimal" in imported_names
        has_half_up = "ROUND_HALF_UP" in imported_names or "ROUND_HALF_UP" in code
        uses_builtin_round = "round" in bare_calls
        rule_ok = has_dec and has_half_up and not uses_builtin_round
        detail = (
            "Confirmed Decimal + ROUND_HALF_UP and zero calls to built-in round()."
            if rule_ok
            else f"Violation (Decimal={has_dec}, ROUND_HALF_UP={has_half_up}, builtin_round={uses_builtin_round})."
        )
        checks.append(
            {
                "check_id": "AST-DEC-01",
                "category": "ast",
                "name": "ENG-STD-04 Decimal + ROUND_HALF_UP (No float round())",
                "passed": rule_ok,
                "detail": detail,
            }
        )
    elif preset_id == "inc-02":
        has_compare_digest = "compare_digest" in attr_calls or "compare_digest" in bare_calls
        non_const_sig_eq = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                has_eq_op = any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops)
                if not has_eq_op:
                    continue
                exprs = [node.left, *node.comparators]
                has_const = any(isinstance(e, ast.Constant) for e in exprs)
                if not has_const and any(_contains_sig_identifier(e) for e in exprs):
                    non_const_sig_eq = True
                    break
        rule_ok = has_compare_digest and not non_const_sig_eq
        detail = (
            "Confirmed constant-time hmac.compare_digest() with zero direct signature == comparisons."
            if rule_ok
            else f"Violation (compare_digest={has_compare_digest}, non_const_sig_eq={non_const_sig_eq})."
        )
        checks.append(
            {
                "check_id": "AST-SEC-01",
                "category": "ast",
                "name": "SEC-STD-02 constant-time hmac.compare_digest (CWE-208)",
                "passed": rule_ok,
                "detail": detail,
            }
        )
    else:
        has_sorted = "sorted" in bare_calls
        has_threading = "threading" in imported_names or "Lock" in imported_names
        rule_ok = has_sorted and has_threading
        detail = (
            "Confirmed sorted() global lock ordering with threading.Lock."
            if rule_ok
            else f"Violation (sorted={has_sorted}, threading={has_threading})."
        )
        checks.append(
            {
                "check_id": "AST-CONC-01",
                "category": "ast",
                "name": "CONC-STD-07 sorted() canonical lock-order acquisition",
                "passed": rule_ok,
                "detail": detail,
            }
        )

    return safe_ok, checks


_HARNESS_INC_01 = textwrap.dedent(
    """
    import json
    import sys
    from decimal import Decimal
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gst_cart_tax as mod

    CartLine = mod.CartLine
    CouponSpec = mod.CouponSpec
    calc = mod.compute_checkout_totals

    results = []

    def run_check(cid, cat, name, fn):
        try:
            detail = fn()
            results.append({"check_id": cid, "category": cat, "name": name, "passed": True, "detail": str(detail)})
        except Exception as exc:
            results.append({"check_id": cid, "category": cat, "name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"})

    def t_ci_1():
        res = calc([CartLine("SKU-A", Decimal("1000.00"), 2)], [], wallet_credit_inr=Decimal("0.00"), inter_state=False)
        assert res.gross_subtotal_inr == Decimal("2000.00"), res
        assert res.cgst_inr == Decimal("180.00") and res.sgst_inr == Decimal("180.00"), res
        assert res.igst_inr == Decimal("0.00") and res.net_payable_inr == Decimal("2360.00"), res
        return f"gross={res.gross_subtotal_inr} cgst={res.cgst_inr} sgst={res.sgst_inr} net={res.net_payable_inr}"

    def t_ci_2():
        res = calc(
            [CartLine("SKU-B", Decimal("2000.00"), 1)],
            [CouponSpec("DIWALI20", Decimal("20"), Decimal("250.00"), active=True)],
            wallet_credit_inr=Decimal("0.00"),
            inter_state=False,
        )
        assert res.discount_inr == Decimal("250.00"), res
        assert res.taxable_subtotal_inr == Decimal("1750.00"), res
        assert res.total_gst_inr == Decimal("315.00") and res.net_payable_inr == Decimal("2065.00"), res
        return f"disc={res.discount_inr} taxable={res.taxable_subtotal_inr} gst={res.total_gst_inr}"

    def t_ci_3():
        res = calc([CartLine("SKU-C", 19.99, 3)], [], inter_state=True)
        assert res.gross_subtotal_inr == Decimal("59.97"), res
        assert res.cgst_inr == Decimal("0.00") and res.sgst_inr == Decimal("0.00"), res
        assert res.igst_inr == Decimal("10.79") and res.net_payable_inr == Decimal("70.76"), res
        return f"inter_state igst={res.igst_inr} net={res.net_payable_inr}"

    def t_ci_4():
        res = calc(
            [CartLine("SKU-D", Decimal("1200.00"), 2)],
            [],
            wallet_credit_inr=Decimal("500.00"),
            inter_state=False,
        )
        assert res.taxable_subtotal_inr == Decimal("2400.00"), f"Pre-GST wallet violation: {res}"
        assert res.total_gst_inr == Decimal("432.00"), res
        assert res.wallet_applied_inr == Decimal("500.00"), res
        assert res.net_payable_inr == Decimal("2332.00"), res
        return f"CGST Sec15(3) verified: taxable={res.taxable_subtotal_inr} gst={res.total_gst_inr} net={res.net_payable_inr}"

    def t_adv_1():
        res = calc(
            [CartLine("SKU-E", Decimal("1500.00"), 2)],
            [
                CouponSpec("DIWALI30", Decimal("30"), Decimal("1000.00"), active=True),
                CouponSpec("BANK35", Decimal("35"), Decimal("1000.00"), active=True),
                CouponSpec("EXPIRED50", Decimal("50"), Decimal("2000.00"), active=False),
            ],
            inter_state=False,
        )
        assert res.discount_inr == Decimal("1500.00"), f"Expected 50% stack cap 1500.00, got {res.discount_inr}"
        assert res.taxable_subtotal_inr == Decimal("1500.00") and res.total_gst_inr == Decimal("270.00"), res
        return f"stack_cap_50pct={res.discount_inr} ignored_inactive=True"

    def t_adv_2():
        res = calc([CartLine("SKU-ODD", Decimal("16.70"), 1)], [], inter_state=False)
        for field_name in (
            "gross_subtotal_inr", "discount_inr", "taxable_subtotal_inr",
            "cgst_inr", "sgst_inr", "igst_inr", "total_gst_inr",
            "wallet_applied_inr", "net_payable_inr",
        ):
            val = getattr(res, field_name)
            assert isinstance(val, Decimal), f"{field_name} not Decimal: {type(val)}"
        assert res.total_gst_inr == Decimal("3.01"), res
        assert res.cgst_inr == Decimal("1.51") and res.sgst_inr == Decimal("1.50"), res
        assert res.cgst_inr + res.sgst_inr == res.total_gst_inr, res
        return f"odd_paise cgst={res.cgst_inr} + sgst={res.sgst_inr} == {res.total_gst_inr}"

    def t_adv_3():
        res = calc([CartLine("SKU-LOW", Decimal("100.00"), 1)], [], wallet_credit_inr=Decimal("500.00"), inter_state=False)
        assert res.total_gst_inr == Decimal("18.00"), res
        assert res.wallet_applied_inr == Decimal("118.00"), res
        assert res.net_payable_inr == Decimal("0.00"), res
        return f"wallet_clamped={res.wallet_applied_inr} net_payable={res.net_payable_inr}"

    def t_adv_4():
        for bad in (
            [],
            [CartLine("BAD-QTY", Decimal("100.00"), 0)],
            [CartLine("BAD-NEG", Decimal("-5.00"), 1)],
        ):
            raised = False
            try:
                calc(bad, [])
            except ValueError:
                raised = True
            assert raised, f"Expected ValueError for {bad}"
        return "Empty/zero-qty/negative-price inputs cleanly raised ValueError"

    run_check("CI-UNIT-01", "ci_unit", "Intra-state CGST/SGST nominal checkout", t_ci_1)
    run_check("CI-UNIT-02", "ci_unit", "Active coupon per-coupon max ceiling clamp", t_ci_2)
    run_check("CI-UNIT-03", "ci_unit", "Inter-state IGST & float-safe 19.99 * 3 precision", t_ci_3)
    run_check("CI-UNIT-04", "ci_unit", "CGST Sec 15(3) wallet applied strictly post-tax", t_ci_4)
    run_check("ADV-FIN-01", "adversarial", "50% stacked coupon ceiling + inactive coupon filter", t_adv_1)
    run_check("ADV-FIN-02", "adversarial", "Odd-paise HALF_UP split & paise conservation", t_adv_2)
    run_check("ADV-FIN-03", "adversarial", "Wallet excess clamped to net_payable=0.00", t_adv_3)
    run_check("ADV-FIN-04", "adversarial", "Rejects empty cart, qty<=0 & negative unit price", t_adv_4)

    print(json.dumps(results))
    """
)

_HARNESS_INC_02 = textwrap.dedent(
    """
    import hashlib
    import hmac
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import upi_webhook_auth as mod

    proc = mod.UpiWebhookProcessor("novamart-secret-key-2026", replay_window_seconds=300)
    results = []

    def sign(ts, body, secret="novamart-secret-key-2026", prefix="sha256="):
        msg = f"{ts}.{body}".encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return f"{prefix}{digest}"

    def run_check(cid, cat, name, fn):
        try:
            detail = fn()
            results.append({"check_id": cid, "category": cat, "name": name, "passed": True, "detail": str(detail)})
        except Exception as exc:
            results.append({"check_id": cid, "category": cat, "name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"})

    def t_ci_1():
        body = '{"order":"NM-101","paise":125000}'
        ts = 1700000000
        res = proc.verify_and_process(
            event_id="EVT-101",
            raw_body=body,
            signature_header=sign(ts, body),
            timestamp=ts,
            now_ts=ts + 25,
            payer_vpa="rahul.sharma@okicici",
            mobile="+919876543210",
            amount_paise=125000,
        )
        assert res.accepted is True and res.reason == "PROCESSED" and res.refund_id, res
        assert "EVT-101" in proc.processed_events and len(proc.refund_ledger) == 1
        return f"accepted event EVT-101 -> {res.refund_id}"

    def t_ci_2():
        body = '{"order":"NM-102","paise":45000}'
        ts = 1700000100
        raw_hex = sign(ts, body, prefix="").upper()
        res = proc.verify_and_process(
            event_id="EVT-102",
            raw_body=body,
            signature_header=raw_hex,
            timestamp=ts,
            now_ts=ts + 300,
            payer_vpa="ananya.iyer@oksbi",
            mobile="9988776655",
            amount_paise=45000,
        )
        assert res.accepted is True and res.reason == "PROCESSED", res
        return f"accepted boundary 300s & uppercase digest -> {res.refund_id}"

    def t_ci_3():
        ts = 1700000200
        before = len(proc.refund_ledger)
        res = proc.verify_and_process(
            event_id="EVT-103",
            raw_body='{"tampered":true}',
            signature_header=sign(ts, '{"original":true}'),
            timestamp=ts,
            now_ts=ts + 10,
            payer_vpa="attacker@okaxis",
            mobile="+919111222333",
            amount_paise=99000,
        )
        assert res.accepted is False and res.reason == "INVALID_SIGNATURE", res
        assert len(proc.refund_ledger) == before
        return "Rejected tampered payload with INVALID_SIGNATURE"

    def t_ci_4():
        body = '{"order":"NM-104","paise":-500}'
        ts = 1700000300
        before = len(proc.refund_ledger)
        res = proc.verify_and_process(
            event_id="EVT-104",
            raw_body=body,
            signature_header=sign(ts, body),
            timestamp=ts,
            now_ts=ts + 5,
            payer_vpa="zero.test@okicici",
            mobile="+919000111222",
            amount_paise=-500,
        )
        assert res.accepted is False and res.reason == "INVALID_AMOUNT", res
        assert "EVT-104" not in proc.processed_events and len(proc.refund_ledger) == before
        return "Rejected negative amount_paise cleanly"

    def t_adv_1():
        body = '{"order":"NM-201"}'
        old_ts = 1700000000
        res = proc.verify_and_process(
            event_id="EVT-STALE",
            raw_body=body,
            signature_header=sign(old_ts, body),
            timestamp=old_ts,
            now_ts=old_ts + 900,
            payer_vpa="replay.attacker@okicici",
            mobile="+919876543210",
            amount_paise=50000,
        )
        assert res.accepted is False and res.reason == "STALE_OR_FUTURE_TIMESTAMP", res
        return "Blocked 900s stale replay attack"

    def t_adv_2():
        body = '{"order":"NM-202"}'
        future_ts = 1700005000
        res = proc.verify_and_process(
            event_id="EVT-FUTURE",
            raw_body=body,
            signature_header=sign(future_ts, body),
            timestamp=future_ts,
            now_ts=future_ts - 600,
            payer_vpa="clock.skew@okicici",
            mobile="+919876543210",
            amount_paise=50000,
        )
        assert res.accepted is False and res.reason == "STALE_OR_FUTURE_TIMESTAMP", res
        return "Blocked +600s future clock-skew attack"

    def t_adv_3():
        body = '{"order":"NM-101","paise":125000}'
        ts = 1700000400
        before = len(proc.refund_ledger)
        res = proc.verify_and_process(
            event_id="EVT-101",
            raw_body=body,
            signature_header=sign(ts, body),
            timestamp=ts,
            now_ts=ts + 10,
            payer_vpa="rahul.sharma@okicici",
            mobile="+919876543210",
            amount_paise=125000,
        )
        assert res.accepted is False and res.reason == "DUPLICATE_EVENT_REPLAY", res
        assert len(proc.refund_ledger) == before
        return "Blocked duplicate event_id EVT-101 idempotently"

    def t_adv_4():
        logs_blob = "\\n".join(str(x) for x in proc.audit_log)
        ledger_blob = json.dumps(proc.refund_ledger)
        combined = logs_blob + "\\n" + ledger_blob
        forbidden = (
            "rahul.sharma", "ananya.iyer", "replay.attacker",
            "9876543210", "9988776655", "9111222333",
        )
        for token in forbidden:
            assert token not in combined, f"DPDP Act PII leak detected for '{token}'"
        assert len(proc.audit_log) >= 7, "Audit log should still record masked events"
        return f"Verified zero unmasked VPAs or 10-digit mobiles across {len(proc.audit_log)} logs"

    run_check("CI-UNIT-01", "ci_unit", "Valid ts.body HMAC with sha256= prefix", t_ci_1)
    run_check("CI-UNIT-02", "ci_unit", "Boundary 300s timestamp & bare hex signature", t_ci_2)
    run_check("CI-UNIT-03", "ci_unit", "Rejects spoofed/tampered body HMAC cleanly", t_ci_3)
    run_check("CI-UNIT-04", "ci_unit", "Rejects non-positive amount_paise before state write", t_ci_4)
    run_check("ADV-SEC-01", "adversarial", "Blocks 900s stale timestamp replay", t_adv_1)
    run_check("ADV-SEC-02", "adversarial", "Blocks +600s future clock-skew replay", t_adv_2)
    run_check("ADV-SEC-03", "adversarial", "Enforces event_id idempotency (no double refund)", t_adv_3)
    run_check("ADV-SEC-04", "adversarial", "DPDP Act 2023 log & ledger masking (VPA + mobile)", t_adv_4)

    print(json.dumps(results))
    """
)

_HARNESS_INC_03 = textwrap.dedent(
    """
    import json
    import sys
    import threading
    import time
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inventory_reservation as mod

    CartItemReq = mod.CartItemReq
    InsufficientStockError = mod.InsufficientStockError
    Mgr = mod.InventoryReservationManager
    results = []

    def _run_with_timeout(fn, timeout=0.4):
        out = {}
        def _target():
            try:
                out["val"] = fn()
            except Exception as exc:
                out["exc"] = exc
        th = threading.Thread(target=_target, daemon=True)
        th.start()
        th.join(timeout=timeout)
        assert not th.is_alive(), "Deadlock / unreleased lock detected!"
        if "exc" in out:
            raise out["exc"]
        return out.get("val")

    def run_check(cid, cat, name, fn, timeout=0.45):
        try:
            detail = _run_with_timeout(fn, timeout=timeout)
            results.append({"check_id": cid, "category": cat, "name": name, "passed": True, "detail": str(detail)})
        except Exception as exc:
            results.append({"check_id": cid, "category": cat, "name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"})

    def t_ci_1():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 10, ("FC-BOM-02", "SKU-B"): 8})
        rec = mgr.reserve_split_cart("KEY-1", [CartItemReq("FC-BLR-01", "SKU-A", 2), CartItemReq("FC-BOM-02", "SKU-B", 3)])
        assert rec.reservation_id and mgr.get_stock("FC-BLR-01", "SKU-A") == 8 and mgr.get_stock("FC-BOM-02", "SKU-B") == 5
        return f"Reserved split-FC cart {rec.reservation_id} (rem 8 & 5)"

    def t_ci_2():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 10, ("FC-BOM-02", "SKU-B"): 8})
        rec = mgr.reserve_split_cart("KEY-REL", [CartItemReq("FC-BLR-01", "SKU-A", 4), CartItemReq("FC-BOM-02", "SKU-B", 2)])
        assert mgr.release_reservation(rec.reservation_id) is True
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 10 and mgr.get_stock("FC-BOM-02", "SKU-B") == 8
        assert mgr.release_reservation(rec.reservation_id) is False, "Double release must return False"
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 10
        return "Single-shot idempotent release verified"

    def t_ci_3():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 10})
        r1 = mgr.reserve_split_cart("KEY-IDEM", [CartItemReq("FC-BLR-01", "SKU-A", 3)])
        r2 = mgr.reserve_split_cart("KEY-IDEM", [CartItemReq("FC-BLR-01", "SKU-A", 3)])
        assert r1 == r2 and mgr.get_stock("FC-BLR-01", "SKU-A") == 7
        return "Idempotent retry did not double-deduct stock"

    def t_ci_4():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 10})
        for args in [
            ("KEY-EMPTY", []),
            ("", [CartItemReq("FC-BLR-01", "SKU-A", 1)]),
            ("KEY-ZERO", [CartItemReq("FC-BLR-01", "SKU-A", 0)]),
            ("KEY-NEG", [CartItemReq("FC-BLR-01", "SKU-A", -2)]),
        ]:
            raised = False
            try:
                mgr.reserve_split_cart(args[0], args[1])
            except ValueError:
                raised = True
            assert raised, f"Expected ValueError for {args}"
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 10
        return "Validated empty lines, blank keys & non-positive qty"

    def t_adv_1():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 200, ("FC-DEL-03", "SKU-Z"): 200})
        errs = []
        done_count = [0]
        count_lock = threading.Lock()

        def worker(tid, reverse):
            for i in range(25):
                lines = (
                    [CartItemReq("FC-DEL-03", "SKU-Z", 1), CartItemReq("FC-BLR-01", "SKU-A", 1)]
                    if reverse
                    else [CartItemReq("FC-BLR-01", "SKU-A", 1), CartItemReq("FC-DEL-03", "SKU-Z", 1)]
                )
                try:
                    mgr.reserve_split_cart(f"TH-{tid}-{i}", lines)
                    with count_lock:
                        done_count[0] += 1
                except Exception as exc:
                    errs.append(repr(exc))

        t1 = threading.Thread(target=worker, args=(1, False), daemon=True)
        t2 = threading.Thread(target=worker, args=(2, True), daemon=True)
        deadline = time.monotonic() + 0.8
        t1.start(); t2.start()
        t1.join(timeout=max(0.05, deadline - time.monotonic()))
        t2.join(timeout=max(0.05, deadline - time.monotonic()))
        assert not t1.is_alive() and not t2.is_alive(), "Threads deadlocked!"
        assert not errs, errs
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 200 - done_count[0]
        assert mgr.get_stock("FC-DEL-03", "SKU-Z") == 200 - done_count[0]
        return f"50 concurrent reverse-order split reservations completed deadlock-free"

    def t_adv_2():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 6, ("FC-DEL-03", "SKU-SHORT"): 1})
        failed = False
        try:
            mgr.reserve_split_cart(
                "KEY-PARTIAL-FAIL",
                [CartItemReq("FC-BLR-01", "SKU-A", 4), CartItemReq("FC-DEL-03", "SKU-SHORT", 5)],
            )
        except InsufficientStockError:
            failed = True
        assert failed, "Expected InsufficientStockError"
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 6, "First FC stock mutated despite later shortage!"
        rec = mgr.reserve_split_cart("KEY-AFTER-FAIL", [CartItemReq("FC-BLR-01", "SKU-A", 2)])
        assert rec.reservation_id and mgr.get_stock("FC-BLR-01", "SKU-A") == 4
        return "Atomic all-or-nothing rollback + clean lock release verified"

    def t_adv_3():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 5})
        failed = False
        try:
            mgr.reserve_split_cart(
                "KEY-DUP-OVER",
                [CartItemReq("FC-BLR-01", "SKU-A", 3), CartItemReq("FC-BLR-01", "SKU-A", 4)],
            )
        except InsufficientStockError:
            failed = True
        assert failed, "Duplicate SKU combined qty (3+4=7 > 5) must raise InsufficientStockError"
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 5
        r_ok = mgr.reserve_split_cart(
            "KEY-DUP-OK",
            [CartItemReq("FC-BLR-01", "SKU-A", 2), CartItemReq("FC-BLR-01", "SKU-A", 2)],
        )
        assert mgr.get_stock("FC-BLR-01", "SKU-A") == 1 and r_ok.reservation_id
        return "Same-(fc_id, sku_id) line aggregation verified without self-deadlock"

    def t_adv_4():
        mgr = Mgr({("FC-BLR-01", "SKU-A"): 4, ("FC-BOM-02", "SKU-B"): 4})
        r1 = mgr.reserve_split_cart("KEY-C1", [CartItemReq("FC-BLR-01", "SKU-A", 3), CartItemReq("FC-BOM-02", "SKU-B", 3)])
        assert mgr.release_reservation(r1.reservation_id) is True
        r2 = mgr.reserve_split_cart("KEY-C2", [CartItemReq("FC-BLR-01", "SKU-A", 4), CartItemReq("FC-BOM-02", "SKU-B", 4)])
        assert r2.reservation_id and mgr.get_stock("FC-BLR-01", "SKU-A") == 0
        return "Full reserve -> release -> re-reserve lifecycle conservation verified"

    run_check("CI-UNIT-01", "ci_unit", "Multi-FC split-cart stock reservation", t_ci_1)
    run_check("CI-UNIT-02", "ci_unit", "Idempotent release_reservation (no double increment)", t_ci_2)
    run_check("CI-UNIT-03", "ci_unit", "Idempotent reserve retry returns cached receipt", t_ci_3)
    run_check("CI-UNIT-04", "ci_unit", "Fail-fast validation on empty cart & qty<=0", t_ci_4)
    run_check("ADV-CONC-01", "adversarial", "50x concurrent reverse-order stress (no AB-BA deadlock)", t_adv_1, timeout=1.1)
    run_check("ADV-CONC-02", "adversarial", "Atomic all-or-nothing abort & clean lock release", t_adv_2)
    run_check("ADV-CONC-03", "adversarial", "Duplicate (fc_id, sku_id) line aggregation & lock dedup", t_adv_3)
    run_check("ADV-CONC-04", "adversarial", "Reserve -> release -> re-reserve stock conservation", t_adv_4)

    print(json.dumps(results))
    """
)

_HARNESS_MAP = {
    "inc-01": ("gst_cart_tax.py", _HARNESS_INC_01),
    "inc-02": ("upi_webhook_auth.py", _HARNESS_INC_02),
    "inc-03": ("inventory_reservation.py", _HARNESS_INC_03),
}

SANDBOX_SUITE_PREVIEW_SOURCE = (
    "# === PR-SANDBOX-GATE-01 Deterministic CI Unit + Adversarial + AST Suites ===\n\n"
    + "# --- Incident 1: checkout-pricing-svc (gst_cart_tax.py) [ENG-STD-04 + AST-DEC-01] ---\n"
    + _HARNESS_INC_01
    + "\n# --- Threat Hunt 2: upi-webhook-svc (upi_webhook_auth.py) [SEC-STD-02 + AST-SEC-01] ---\n"
    + _HARNESS_INC_02
    + "\n# --- Feature 3: inventory-lock-svc (inventory_reservation.py) [CONC-STD-07 + AST-CONC-01] ---\n"
    + _HARNESS_INC_03
)


def evaluate_patch_in_sandbox(preset_id: str, patched_code: str) -> dict[str, Any]:
    """Execute static AST checks + isolated subprocess verification (10 total checks)."""
    preset = next((p for p in CAT6_PRESETS if p["id"] == preset_id), None)
    if not preset:
        raise ValueError(f"Unknown Category 6 preset_id `{preset_id}`.")

    t0 = time.perf_counter()
    safe_ok, ast_checks = verify_ast_policies(patched_code, preset_id)
    module_filename, harness_code = _HARNESS_MAP[preset_id]

    diff_lines = list(
        difflib.unified_diff(
            str(preset["buggy_code"]).splitlines(),
            (patched_code or "").splitlines(),
            fromfile=f"a/{preset['target_file']}",
            tofile=f"b/{preset['target_file']}",
            lineterm="",
        )
    )
    unified_diff = "\n".join(diff_lines) if diff_lines else "# No diff vs buggy baseline"

    runtime_checks: list[dict[str, Any]] = []
    if not safe_ok or not patched_code.strip():
        default_names = [
            ("CI-UNIT-01", "ci_unit", "Unit Check 1"),
            ("CI-UNIT-02", "ci_unit", "Unit Check 2"),
            ("CI-UNIT-03", "ci_unit", "Unit Check 3"),
            ("CI-UNIT-04", "ci_unit", "Unit Check 4"),
            ("ADV-01", "adversarial", "Adversarial / Concurrency Check 1"),
            ("ADV-02", "adversarial", "Adversarial / Concurrency Check 2"),
            ("ADV-03", "adversarial", "Adversarial / Concurrency Check 3"),
            ("ADV-04", "adversarial", "Adversarial / Concurrency Check 4"),
        ]
        for cid, cat, cname in default_names:
            runtime_checks.append(
                {
                    "check_id": cid,
                    "category": cat,
                    "name": cname,
                    "passed": False,
                    "detail": "Execution aborted by AST-SAFE-02 static parse/safety gate.",
                }
            )
    else:
        with tempfile.TemporaryDirectory(prefix="novamart_cat6_sbx_") as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / module_filename).write_text(patched_code, encoding="utf-8")
            (tmp_path / "run_checks.py").write_text(harness_code, encoding="utf-8")

            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "run_checks.py"],
                    cwd=str(tmp_path),
                    timeout=5.0,
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    parsed = json.loads(proc.stdout.strip().splitlines()[-1])
                    if isinstance(parsed, list):
                        runtime_checks = parsed
                else:
                    err_msg = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()[:350]
                    for i in range(8):
                        cat = "ci_unit" if i < 4 else "adversarial"
                        cid = f"CI-UNIT-0{i + 1}" if i < 4 else f"ADV-0{i - 3}"
                        runtime_checks.append(
                            {
                                "check_id": cid,
                                "category": cat,
                                "name": f"Sandbox Harness Check {i + 1}",
                                "passed": False,
                                "detail": f"Sandbox process error: {err_msg}",
                            }
                        )
            except subprocess.TimeoutExpired:
                for i in range(8):
                    cat = "ci_unit" if i < 4 else "adversarial"
                    cid = f"CI-UNIT-0{i + 1}" if i < 4 else f"ADV-0{i - 3}"
                    runtime_checks.append(
                        {
                            "check_id": cid,
                            "category": cat,
                            "name": f"Sandbox Harness Check {i + 1}",
                            "passed": False,
                            "detail": "Timed out after 5.0s (deadlock or infinite loop detected).",
                        }
                    )

    all_checks = runtime_checks + ast_checks
    ci_unit_passed = sum(1 for c in runtime_checks if c.get("category") == "ci_unit" and c.get("passed"))
    adv_passed = sum(1 for c in runtime_checks if c.get("category") == "adversarial" and c.get("passed"))
    ast_passed = sum(1 for c in ast_checks if c.get("passed"))
    passed_checks = sum(1 for c in all_checks if c.get("passed"))
    total_checks = len(all_checks)
    execution_ms = max(1, int((time.perf_counter() - t0) * 1000))

    return {
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "ci_unit_passed": ci_unit_passed,
        "adversarial_passed": adv_passed,
        "ast_passed": ast_passed,
        "verified_outcome": passed_checks == total_checks and total_checks == 10,
        "execution_ms": execution_ms,
        "checks": all_checks,
        "unified_diff": unified_diff,
    }
