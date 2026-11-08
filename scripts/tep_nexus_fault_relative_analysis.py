"""Deterministic fault-relative statistics and self-contained timeline report.

Input is the existing evidence JSON. No DB access and no LLM-generated values.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def _stats(samples):
    if not samples:
        return {"count": 0, "mean": None, "minimum": None, "maximum": None,
                "first": None, "last": None, "endpointChange": None,
                "standardDeviation": None}
    vals = [float(x["value"]) for x in samples]
    return {
        "count": len(vals), "mean": statistics.fmean(vals),
        "minimum": min(vals), "maximum": max(vals),
        "first": vals[0], "last": vals[-1],
        "endpointChange": vals[-1] - vals[0] if len(vals) >= 2 else None,
        "standardDeviation": statistics.pstdev(vals) if len(vals) >= 2 else None,
    }


def analyze(evidence):
    """Classify each window relative to its own command center.

    Boundary is half-open: samples exactly at injection are post-command.
    This is a temporal comparison, NOT a causal effect estimate.
    """
    result = []
    for window in evidence["windows"]:
        center = float(window["centerSimulationHours"])
        samples = window["samples"]
        before = [s for s in samples if float(s["simulationTimeHours"]) < center]
        after = [s for s in samples if float(s["simulationTimeHours"]) >= center]
        a, b = _stats(before), _stats(after)
        result.append({
            "centerSimulationHours": center,
            "centerSimulationSeconds": center * 3600,
            "sampleCount": len(samples),
            "truncated": bool(window["truncated"]),
            "before": a, "atOrAfter": b,
            "meanDifferenceAfterMinusBefore": (
                b["mean"] - a["mean"] if a["count"] and b["count"] else None
            ),
            "relationCounts": dict(Counter(
                item["relation"] for s in samples
                for item in s.get("temporalRelations", [])
            )),
            "interpretation": (
                "Descriptive comparison around a recorded fault command; "
                "not evidence of physical fault causation."
            ),
        })
    return result


def _fmt(value):
    return "N/A" if value is None else f"{value:.6g}"


def _svg(window, *, width=960, height=330):
    samples = window["samples"]
    if not samples:
        return "<p>No measurements in this event window.</p>"
    coords = [(float(s["simulationTimeHours"]) * 3600, float(s["value"])) for s in samples]
    if not all(math.isfinite(t) and math.isfinite(v) for t, v in coords):
        raise ValueError("Non-finite sample")
    times, vals = zip(*coords)
    center = float(window["centerSimulationHours"]) * 3600
    tmin = min(min(times), center)
    tmax = max(max(times), center)
    vmin, vmax = min(vals), max(vals)
    if tmin == tmax:
        tmin -= 1
        tmax += 1
    if vmin == vmax:
        vmin -= 1
        vmax += 1
    left, right, top, bottom = 65, 20, 20, 55
    pw, ph = width - left - right, height - top - bottom
    x = lambda t: left + (t - tmin) / (tmax - tmin) * pw
    y = lambda v: top + (vmax - v) / (vmax - vmin) * ph
    points = " ".join(f"{x(t):.2f},{y(v):.2f}" for t, v in coords)
    marker = x(center)
    return f"""<svg viewBox="0 0 {width} {height}" role="img"
        aria-label="Recorded signal measurements with fault command marker">
      <rect x="{left}" y="{top}" width="{pw}" height="{ph}" fill="#f8fafc"/>
      <line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#64748b"/>
      <line x1="{left}" y1="{top}" x2="{left}" y2="{top+ph}" stroke="#64748b"/>
      <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2"/>
      <line x1="{marker:.2f}" y1="{top}" x2="{marker:.2f}" y2="{top+ph}"
            stroke="#dc2626" stroke-width="2" stroke-dasharray="6 4"/>
      <text x="{marker:.2f}" y="14" text-anchor="middle" font-size="12"
            fill="#b91c1c">Injection command: {center:.3f} s</text>
      <text x="{left}" y="{height-18}" font-size="12">Simulation time (s): {tmin:.2f} to {tmax:.2f}</text>
      <text x="{left+pw}" y="{height-18}" text-anchor="end" font-size="12">Signal value (unit not asserted)</text>
      <text x="5" y="{top+12}" font-size="12">{vmax:.5g}</text>
      <text x="5" y="{top+ph}" font-size="12">{vmin:.5g}</text>
    </svg>"""


def render_html(report):
    evidence = report["temporalEvidence"]
    summaries = analyze(evidence)
    latest = evidence.get("latestPersisted")
    function = html.escape(report["validatedPlan"]["engineering_function"])
    signal = html.escape(evidence["signal"])
    sections = []
    for window, summary in zip(evidence["windows"], summaries):
        a, b = summary["before"], summary["atOrAfter"]
        rows = "".join(
            f"<tr><th>{name}</th><td>{_fmt(a[key])}</td><td>{_fmt(b[key])}</td></tr>"
            for name, key in [
                ("Samples", "count"), ("Mean", "mean"), ("Minimum", "minimum"),
                ("Maximum", "maximum"), ("Endpoint change", "endpointChange"),
                ("Std. deviation", "standardDeviation"),
            ]
        )
        sections.append(f"""<section><h2>Command at {summary["centerSimulationSeconds"]:.3f} simulation seconds</h2>
          {_svg(window)}
          <table><thead><tr><th>Metric</th><th>Before</th><th>At/after command</th></tr></thead>
          <tbody>{rows}</tbody></table>
          <p>Mean difference (after − before): {_fmt(summary["meanDifferenceAfterMinusBefore"])}</p>
          <p>Samples truncated: {str(summary["truncated"]).lower()}. Temporal relations:
          {html.escape(json.dumps(summary["relationCounts"]))}</p></section>""")
    freshness = ("No persisted sample" if latest is None else
                 f'Latest persisted: {latest["value"]:.6g} at {html.escape(latest["observedAt"])} '
                 f'(age at query: {latest["recordAgeSeconds"]:.1f} seconds)')
    statuses = ", ".join(html.escape(x["status"]) for x in evidence["faultCommandIntervals"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>TEP NEXUS — fault-relative evidence</title>
    <style>body{{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}
    section{{margin:2rem 0;padding:1rem;border:1px solid #cbd5e1;border-radius:12px}}
    svg{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}
    th,td{{padding:.6rem;border-bottom:1px solid #e2e8f0;text-align:left}}
    .note{{background:#f1f5f9;padding:1rem;border-radius:8px}}</style></head>
    <body><h1>TEP NEXUS — fault-relative temporal evidence</h1>
    <p>Engineering function: <strong>{function}</strong> → signal <strong>{signal}</strong></p>
    <p>Run: {html.escape(evidence["runId"])}. Fault interval status: {statuses or "none"}.</p>
    <p>{freshness}</p>
    <p class="note">GraphDB mapping is provisional; run provenance and physical sensor binding are
    unverified. Intervals describe recorded operator commands, not verified fault states.
    The latest persisted record may be stale. All comparisons are descriptive, not causal.</p>
    {"".join(sections) if sections else "<p>No matching fault commands or windows.</p>"}
    </body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="reports/tep_nexus_fault_relative_query.json")
    parser.add_argument("--html", default="reports/tep_nexus_fault_relative_timeline.html")
    parser.add_argument("--analysis", default="reports/tep_nexus_fault_relative_analysis.json")
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    analysis = analyze(report["temporalEvidence"])
    Path(args.html).write_text(render_html(report), encoding="utf-8")
    Path(args.analysis).write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(json.dumps({"html": args.html, "analysis": args.analysis,
                      "windows": len(analysis)}, indent=2))


if __name__ == "__main__":
    main()
