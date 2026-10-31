"""Deterministic answer templates and the code that computes every reported number."""
from __future__ import annotations

import math

from ..tools.stats import describe_correlation, pct_change, pearson_from_sums


def fmt(value) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if value == int(value) and abs(value) >= 1:
        return f"{int(value):,}"
    if abs(value) < 1 and value != 0:
        return f"{value:.4f}"
    return f"{value:,.2f}"


def compute(plan: dict, result: dict) -> dict:
    """Compute derived numbers in code from the raw SQL result."""
    rows, kind = result["rows"], plan.get("kind")
    out: dict = {"rows_returned": len(rows)}
    if kind == "scalar" and rows:
        out["value"] = rows[0][0]
    elif kind == "grouped" and rows:
        values = [float(r[1]) for r in rows if r[1] is not None]
        if plan.get("agg") in ("sum", "count") and values and not result["truncated"] and plan.get("limit", 0) > len(rows) - 1:
            total = sum(values)
            if total:
                out["grand_total"] = total
                out["shares_pct"] = {str(r[0]): float(r[1]) / total * 100.0 for r in rows if r[1] is not None}
    elif kind == "trend" and rows:
        series = [(str(r[0]), float(r[1])) for r in rows if r[1] is not None]
        out["periods"] = len(series)
        if series:
            out["first"] = {"period": series[0][0], "value": series[0][1]}
            out["last"] = {"period": series[-1][0], "value": series[-1][1]}
            out["overall_pct_change"] = pct_change(series[0][1], series[-1][1])
            changes = []
            for (_, prev), (period, cur) in zip(series, series[1:]):
                change = pct_change(prev, cur)
                if change is not None:
                    changes.append((period, change))
            if changes:
                up = max(changes, key=lambda item: item[1])
                down = min(changes, key=lambda item: item[1])
                out["largest_increase"] = {"period": up[0], "pct": up[1]}
                out["largest_decrease"] = {"period": down[0], "pct": down[1]}
    elif kind == "correlation" and rows:
        n, sx, sy, sxy, sxx, syy = rows[0]
        out["n"] = n
        if n and n >= 3:
            try:
                r = pearson_from_sums(n, sx, sy, sxy, sxx, syy)
                out["r"] = r
                out["strength"] = describe_correlation(r)
            except (ValueError, TypeError):
                out["error"] = "Correlation is undefined for these columns."
        else:
            out["error"] = "Not enough rows to compute a correlation."
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in out.items()}


def render_template(state: dict) -> str:
    plan = state.get("plan_data") or {}
    route = state.get("route")
    if state.get("blocked"):
        return f"I can't do that: {state.get('block_reason', 'request blocked')}. I only run read-only analysis on the loaded data."
    if route == "unknown":
        note = plan.get("note") or "I couldn't match that question to the data or the documentation."
        schema = state.get("schema_summary") or {}
        tables = "; ".join(f"{t}({', '.join(cols)})" for t, cols in schema.items())
        examples = "Try: 'total revenue by region', 'top products by revenue', 'monthly revenue trend', or 'how is revenue calculated?'."
        return f"{note} {examples}" + (f" Available tables: {tables}." if tables else "")
    if route == "docs":
        docs = state.get("docs") or []
        top = docs[0]
        extra = [f"{d['doc']} > {d['heading']}" for d in docs[1:3]]
        text = f"From the {top['doc'].replace('_', ' ')} notes ({top['heading']}): {top['text']}"
        return text + (f" Related sections: {'; '.join(extra)}." if extra else "")

    result, computed = state.get("result") or {}, state.get("computed") or {}
    rows, label = result.get("rows", []), plan.get("label", "Result")
    kind = plan.get("kind")
    if not rows:
        return f"{label}: no matching rows."
    if kind == "scalar":
        value = computed.get("value")
        return f"{label}: {fmt(value)}." if value is not None else f"{label}: no matching rows."
    if kind == "correlation":
        if "error" in computed:
            return f"{label}: {computed['error']}"
        return (f"{label}: Pearson r = {computed['r']:.3f} across {fmt(computed['n'])} rows, "
                f"a {computed['strength']} relationship. Correlation does not show causation.")
    if kind == "trend":
        first, last = computed["first"], computed["last"]
        parts = [f"{label}: {fmt(first['value'])} in {first['period']} to {fmt(last['value'])} in {last['period']}"]
        change = computed.get("overall_pct_change")
        if change is not None:
            parts[0] += f" ({change:+.1f}% overall)"
        parts[0] += "."
        if "largest_increase" in computed:
            inc, dec = computed["largest_increase"], computed["largest_decrease"]
            parts.append(f"Largest month-over-month increase: {inc['pct']:+.1f}% in {inc['period']}. "
                         f"Largest decrease: {dec['pct']:+.1f}% in {dec['period']}.")
        return " ".join(parts)
    if kind == "grouped" and plan.get("limit") == 1 and plan.get("agg") in ("max", "min") and len(rows) == 1:
        word = "Highest" if plan["agg"] == "max" else "Lowest"
        return f"{word} {label.lower()}: {rows[0][0]} with {fmt(rows[0][1])}."
    shares = computed.get("shares_pct", {})
    lines = [f"{label}:"]
    for row in rows[:25]:
        suffix = f" ({shares[str(row[0])]:.1f}% of total)" if str(row[0]) in shares else ""
        lines.append(f"- {' | '.join(fmt(v) if isinstance(v, (int, float)) else str(v) for v in row)}{suffix}")
    if result.get("truncated"):
        lines.append("(Results were truncated to the row limit.)")
    return "\n".join(lines)
