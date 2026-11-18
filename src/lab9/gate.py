"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def _bad_number(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _graded_ids(spec: dict, base: dict) -> list[str]:
    """Spec metrics graded per row: they have a grader, or are a row column in the baseline."""
    base_cols = set().union(*(r.keys() for r in base.get("rows") or [])) if base.get("rows") else set()
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS or m["id"] in base_cols]


def _loosened(name: str, new: dict | None, old: dict, th_new: dict, th_old: dict) -> list[str]:
    if new is None:
        return [f"ratchet: {name} removed"]
    r = []
    if old.get("blocking") and not new.get("blocking"):
        r.append(f"ratchet: {name} no longer blocking")
    if "max" in th_old and ("max" not in th_new or float(th_new["max"]) > float(th_old["max"])):
        r.append(f"ratchet: {name} max loosened {th_old['max']} -> {th_new.get('max')}")
    if "min" in th_old and ("min" not in th_new or float(th_new["min"]) < float(th_old["min"])):
        r.append(f"ratchet: {name} min loosened {th_old['min']} -> {th_new.get('min')}")
    if "max_increase" in th_old and ("max_increase" not in th_new
                                     or float(th_new["max_increase"]) > float(th_old["max_increase"])):
        r.append(f"ratchet: {name} max_increase loosened {th_old['max_increase']} -> {th_new.get('max_increase')}")
    if th_old.get("no_significant_drop") and not th_new.get("no_significant_drop"):
        r.append(f"ratchet: {name} dropped no_significant_drop")
    return r


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version => thresholds may only get stricter."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []                                   # new eval-set version: thresholds start over
    out: list[str] = []
    for key in ("eval_set", "labels", "adversarial_pack"):
        if base_spec.get(key) != spec.get(key):
            out.append(f"ratchet: {key} changed ({base_spec.get(key)!r} -> {spec.get(key)!r}) on the same version")
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        out.append("ratchet: seeds changed on the same eval-set version")
    bs, bb = spec.get("bootstrap") or {}, base_spec.get("bootstrap") or {}
    if float(bs.get("confidence", 0.95)) > float(bb.get("confidence", 0.95)):
        out.append("ratchet: bootstrap confidence raised (a wider CI blocks less)")
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        n = new_m.get(m["id"])
        out += _loosened(f"metric {m['id']}", n, m, (n or {}).get("threshold") or {}, m.get("threshold") or {})
    key = lambda x: (x.get("name"), x.get("metric"))
    new_s = {key(x): x for x in spec.get("slices") or []}
    for x in base_spec.get("slices") or []:
        n = new_s.get(key(x))
        out += _loosened(f"slice {x.get('name')}/{x.get('metric')}", n, x, n or {}, x)
    return out


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)
    Also: duplicated rows, evaluator failures in the baseline, non-boolean grader values, and a
    metrics summary that does not match its own rows (hand-edited summary)."""
    problems: list[str] = []
    rows = pr.get("rows") or []
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}
    base_rows = base.get("rows") or []
    # 1. non-finite metric values (nan < min is False: a naive gate passes it)
    for k, v in (pr.get("metrics") or {}).items():
        if _bad_number(v):
            problems.append(f"metric {k} is {v} (non-finite)")
    # 2. row count vs manifest, duplicated rows
    seeds = man.get("seeds") or []
    want = int(man.get("items") or 0) * len(seeds)
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest promises {man.get('items')} items x {len(seeds)} seeds = {want}")
    pairs = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(pairs) != len(set(pairs)):
        problems.append(f"{len(pairs) - len(set(pairs))} duplicated (item_id, seed) row(s)")
    # 3. same (item, seed) set and manifest as the baseline (cherry-picked seeds / items)
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pairs) != base_pairs:
        problems.append(f"(item_id, seed) set differs from baseline: {len(base_pairs - set(pairs))} missing, "
                        f"{len(set(pairs) - base_pairs)} extra")
    if sorted(seeds) != sorted(bman.get("seeds") or []):
        problems.append(f"manifest seeds {sorted(seeds)} != baseline {sorted(bman.get('seeds') or [])}")
    if man.get("items") != bman.get("items"):
        problems.append(f"manifest items {man.get('items')} != baseline {bman.get('items')}")
    if len(base_rows) != len(base_pairs):
        problems.append("baseline has duplicated (item_id, seed) rows")
    # 4. evaluator failures, crashed graders scored as None, non-boolean grader values
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the PR run")
    if base.get("evaluator_failures"):
        problems.append(f"{len(base['evaluator_failures'])} evaluator failure(s) in the baseline run")
    graded = _graded_ids(spec, base)
    for m in graded:
        none = sum(1 for r in rows if r.get(m) is None)
        if none:
            problems.append(f"{none} row(s) have no value for graded metric {m} (missing / crashed grader)")
        odd = sum(1 for r in rows if r.get(m) is not None and not isinstance(r.get(m), bool))
        if odd:
            problems.append(f"{odd} row(s) have a non-boolean value for {m}")
    # 5. the summary must be what its rows say (an edited metric hides failing rows)
    if rows and not problems:
        cols = [m for m in graded if m in rows[0]]
        has_cost = all("cost" in r for r in rows)
        try:
            again = aggregate([{**r, "cost": float(r.get("cost") or 0.0)} for r in rows], cols,
                              k_values=spec.get("pass_k", []))
        except Exception as e:                       # malformed rows
            problems.append(f"cannot recompute metrics from rows: {e!r}")
            again = {}
        if not has_cost:
            again.pop("cost_per_success", None)
        reported = pr.get("metrics") or {}
        for k, v in again.items():
            got = reported.get(k)
            if k not in reported and k not in cols:
                continue
            if isinstance(v, (int, float)) and isinstance(got, (int, float)) and not isinstance(got, bool):
                if abs(float(got) - float(v)) > 1e-3:
                    problems.append(f"metric {k} = {got} but its rows give {v} (summary edited?)")
            elif v != got:
                problems.append(f"metric {k} = {got!r} but its rows give {v!r}")
    # 6. ratchet: same eval-set version, thresholds may only get stricter
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    # 7. slice tags must match the baseline per item (relabelling hides a slice regression)
    def tags(rs):
        return {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in rs}
    pt, bt = tags(rows), tags(base_rows)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags differ from baseline on {len(moved)} item(s): {', '.join(moved[:5])}")
    mixed = sorted({r.get("item_id") for r in rows if tuple(sorted(r.get("slices") or [])) != pt.get(r.get("item_id"))})
    if mixed:
        problems.append(f"item(s) with different slice tags across seeds: {', '.join(mixed[:5])}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict, note = "missing", "no PR rows in slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if ("min" in sl and val < float(sl["min"])) or ("max" in sl and val > float(sl["max"])):
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027),
                                                       confidence=bs.get("confidence", 0.95))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "missing", "no items shared with baseline"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
