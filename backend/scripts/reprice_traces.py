"""Re-price stored traces in backend/traces/ after a rate-card change in app/core/pricing.py.

Only the `finops` block of each trace (and `cost_per_1k_usd` in index.jsonl) is rewritten; trace ids,
timestamps, source modes, requests and responses are left untouched.

How each trace gets its new finops:
  1. reference  - the same run is regenerated from the golden replays into a temporary directory
                  (seed script + replay-mode calls to every /run endpoint) and matched by
                  (category, use_case, model, pattern, item_id, token counts). Covers rollups
                  (Cat 3 sessions, Cat 4 audits, Cat 5/6 multi-step runs) whose cost is modelled.
  2. single-call - no reference match, but the stored cost equals the OLD rate card applied to the
                  stored tokens, so it is a plain billed call and is re-priced with compute_run_finops.
  3. skipped    - error traces with no tokens, or traces that fit neither rule (reported, left as-is).

Usage (from backend/):
    .venv/bin/python scripts/reprice_traces.py                      # dry run: report only
    .venv/bin/python scripts/reprice_traces.py --apply              # back up traces/ then rewrite
    .venv/bin/python scripts/reprice_traces.py --old-sonnet-cache-read 0.20   # previous rate (default)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

TRACES_DIR = BACKEND_DIR / "traces"
COST_FIELDS = ("input_cost_usd", "output_cost_usd", "total_cost_usd", "cost_per_1k_usd")


def _key(rec: dict) -> tuple:
    p, f = rec["partition"], rec.get("finops") or {}
    return (
        p["category"], p["use_case"], p["model"], p["pattern"], rec["item_id"],
        f.get("input_tokens"), f.get("output_tokens"), f.get("cache_creation_tokens"), f.get("cache_read_tokens"),
    )


def _load(dir_: Path) -> dict[Path, dict]:
    out = {}
    for fp in dir_.rglob("*.json"):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(rec, dict) and "partition" in rec and "finops" in rec:
            out[fp] = rec
    return out


def build_reference(tmp: Path) -> dict[tuple, dict]:
    """Regenerate every canonical run into `tmp` with the current rate card; return key -> finops."""
    os.environ["NOVAMART_TRACES_DIR"] = str(tmp)
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415
    from scripts.seed_traces_from_replays import seed_all  # noqa: PLC0415

    seed_all()
    client = TestClient(app)
    calls = [("/api/cat1/batch", {"sub_task": "mixed", "mode": "replay"})]
    for cat, path in (("cat1", "/api/cat1"), ("cat2", "/api/cat2"), ("cat3", "/api/cat3"),
                      ("cat4", "/api/cat4"), ("cat5", "/api/cat5"), ("cat6", "/api/cat6")):
        presets = client.get(f"{path}/presets").json()["presets"]
        for pr in presets:
            body = {"preset_id": pr["id"], "mode": "replay"}
            if cat in ("cat1", "cat2") and pr.get("sub_task"):
                body["sub_task"] = pr["sub_task"]
            calls.append((f"{path}/run", body))
    for url, body in calls:
        r = client.post(url, json=body)
        if r.status_code != 200:
            print(f"  ! reference call {url} {body} -> {r.status_code}")

    ref: dict[tuple, dict] = {}
    conflicts: set[tuple] = set()
    for rec in _load(tmp).values():
        k = _key(rec)
        fin = rec["finops"]
        if k in ref and any(abs((ref[k].get(c) or 0) - (fin.get(c) or 0)) > 1e-9 for c in COST_FIELDS):
            conflicts.add(k)
        ref.setdefault(k, fin)
    for k in conflicts:
        ref.pop(k, None)
    if conflicts:
        print(f"  ! {len(conflicts)} reference keys had conflicting costs and were dropped")
    return ref


def _old_card_total(fin: dict, old_sonnet_cache_read: float) -> float | None:
    from app.core.pricing import LEGACY_MODEL_RATES, MODEL_RATES  # noqa: PLC0415

    rate = MODEL_RATES.get(fin.get("model_id")) or LEGACY_MODEL_RATES.get(fin.get("model_id"))
    if rate is None:
        return None
    cr = old_sonnet_cache_read if rate.model_id == "claude-sonnet-5-5" else rate.cache_read_per_1m_usd
    return (
        (fin.get("input_tokens") or 0) * rate.input_per_1m_usd
        + (fin.get("output_tokens") or 0) * rate.output_per_1m_usd
        + (fin.get("cache_creation_tokens") or 0) * rate.cache_write_per_1m_usd
        + (fin.get("cache_read_tokens") or 0) * cr
    ) / 1e6


def plan(old_sonnet_cache_read: float) -> tuple[dict[Path, dict], Counter, dict]:
    from app.core.pricing import compute_run_finops  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="novamart_reprice_") as tmp:
        print("Regenerating reference traces from golden replays (current rate card)...")
        ref = build_reference(Path(tmp))
        os.environ.pop("NOVAMART_TRACES_DIR", None)
    print(f"  {len(ref)} reference runs")

    updates: dict[Path, dict] = {}
    stats: Counter = Counter()
    changed_by_cat: dict = defaultdict(Counter)
    for fp, rec in _load(TRACES_DIR).items():
        fin = rec.get("finops") or {}
        cat = rec["partition"]["category"]
        if rec["response"].get("status") == "error" or not (fin.get("input_tokens") or fin.get("output_tokens")):
            stats["skipped: error / no tokens"] += 1
            continue
        new = ref.get(_key(rec))
        how = "reference"
        if new is None:
            old_total = _old_card_total(fin, old_sonnet_cache_read)
            if old_total is not None and abs(old_total - (fin.get("total_cost_usd") or 0)) <= 1e-7:
                new = compute_run_finops(
                    model_id=fin["model_id"], input_tokens=fin.get("input_tokens") or 0,
                    output_tokens=fin.get("output_tokens") or 0,
                    cache_creation_tokens=fin.get("cache_creation_tokens") or 0,
                    cache_read_tokens=fin.get("cache_read_tokens") or 0,
                ).model_dump()
                how = "single-call"
            else:
                stats["skipped: no reference and not a plain billed call"] += 1
                print(f"  ? left as-is: {fp.relative_to(TRACES_DIR)}")
                continue
        differs = any(abs((fin.get(c) or 0) - (new.get(c) or 0)) > 1e-9 for c in COST_FIELDS) or \
            (fin.get("output_cost_share_pct") != new.get("output_cost_share_pct"))
        stats[f"{how}: {'changed' if differs else 'unchanged'}"] += 1
        if differs:
            changed_by_cat[cat][how] += 1
            updates[fp] = new
    return updates, stats, changed_by_cat


def apply(updates: dict[Path, dict]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = TRACES_DIR / "_backups"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / f"traces_pre_reprice_{stamp}.tar.gz"
    with tarfile.open(backup, "w:gz") as tar:
        for fp in TRACES_DIR.rglob("*"):
            if fp.is_file() and "_backups" not in fp.parts:
                tar.add(fp, arcname=str(fp.relative_to(TRACES_DIR)))

    new_cost_by_rel: dict[str, float] = {}
    for fp, fin in updates.items():
        rec = json.loads(fp.read_text(encoding="utf-8"))
        rec["finops"] = fin
        fp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        new_cost_by_rel[str(fp.relative_to(TRACES_DIR))] = fin["cost_per_1k_usd"]

    index = TRACES_DIR / "index.jsonl"
    if index.is_file():
        lines_out, touched = [], 0
        for line in index.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            rel = entry.get("relative_path")
            if rel in new_cost_by_rel:
                entry["cost_per_1k_usd"] = new_cost_by_rel[rel]
                touched += 1
            lines_out.append(json.dumps(entry))
        index.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
        print(f"  index.jsonl: {touched} entries updated")
    return backup


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="back up traces/ and rewrite finops (default: dry run)")
    ap.add_argument("--old-sonnet-cache-read", type=float, default=0.20,
                    help="Sonnet 5.5 cache-read $/MTok the existing traces were priced with (default 0.20)")
    args = ap.parse_args()

    updates, stats, by_cat = plan(args.old_sonnet_cache_read)
    print("\nPlan:")
    for k, v in sorted(stats.items()):
        print(f"  {k:<55} {v:>5}")
    for cat, c in sorted(by_cat.items()):
        print(f"  changed in {cat:<40} {dict(c)}")
    if not args.apply:
        print(f"\nDry run: {len(updates)} trace files would be rewritten. Re-run with --apply.")
        return
    backup = apply(updates)
    print(f"\nRewrote {len(updates)} trace files. Backup: {backup}")


if __name__ == "__main__":
    main()
