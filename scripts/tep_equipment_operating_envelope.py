#!/usr/bin/env python3
"""Summarize a fault-free TEP XMEAS/XMV CSV export for equipment screening.

This script analyzes an existing simulator export; it does NOT run the TEP simulator.
Usage:
  python3 scripts/tep_equipment_operating_envelope.py data/tep_fault_free.csv \
      --time-column time --steady-start 10 --out docs/tep_operating_envelope.csv

Input: header row with XMEAS(7), XMEAS_7, xmeas7 (likewise XMV), and a numeric
time column. --steady-start is expressed in the input time column's units.
"""

# Created: 2026-10-21
# Author: Harish
import argparse
import csv
import math
import re
from pathlib import Path

SIGNALS = {
    "XMEAS(5)": ("Recycle flow", "kscmh"),
    "XMEAS(7)": ("Reactor pressure", "kPa(g)"),
    "XMEAS(8)": ("Reactor level", "%"),
    "XMEAS(9)": ("Reactor temperature", "degC"),
    "XMEAS(11)": ("Separator temperature", "degC"),
    "XMEAS(12)": ("Separator level", "%"),
    "XMEAS(13)": ("Separator pressure", "kPa(g)"),
    "XMEAS(14)": ("Separator underflow", "m3/h"),
    "XMEAS(15)": ("Stripper level", "%"),
    "XMEAS(16)": ("Stripper pressure", "kPa(g)"),
    "XMEAS(17)": ("Stripper underflow", "m3/h"),
    "XMEAS(18)": ("Stripper temperature", "degC"),
    "XMEAS(19)": ("Stripper steam flow", "kg/h"),
    "XMEAS(20)": ("Compressor work", "kW"),
    "XMEAS(21)": ("Reactor cooling water outlet", "degC"),
    "XMEAS(22)": ("Separator cooling water outlet", "degC"),
    "XMV(5)": ("Compressor recycle valve", "model control units"),
    "XMV(9)": ("Stripper steam valve", "model control units"),
    "XMV(11)": ("Condenser cooling water valve", "model control units"),
    "XMV(12)": ("Agitator speed manipulation", "model control units"),
}

def normalized(name):
    match = re.fullmatch(r"\s*(XMEAS|XMV)[\s_\[(]*(\d+)[\s_\])] *", name, re.I)
    return f"{match.group(1).upper()}({int(match.group(2))})" if match else None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--time-column", default="time")
    parser.add_argument("--steady-start", type=float, required=True,
                        help="Start of steady-state window in input time units")
    parser.add_argument("--out", type=Path, default=Path("out/tep_operating_envelope.csv"))
    args = parser.parse_args()
    with args.csv_file.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            parser.error("CSV is empty or lacks a header")
        columns = {normalized(name): name for name in reader.fieldnames if normalized(name)}
        if args.time_column not in reader.fieldnames:
            parser.error(f"Time column {args.time_column!r} not present")
        if not columns:
            parser.error("No XMEAS/XMV columns found")
        values = {name: [] for name in columns if name in SIGNALS}
        row_count = 0
        for line, row in enumerate(reader, start=2):
            try:
                timestamp = float(row[args.time_column])
            except (ValueError, TypeError):
                parser.error(f"Invalid time at CSV line {line}")
            if not math.isfinite(timestamp):
                parser.error(f"Non-finite time at CSV line {line}")
            if timestamp < args.steady_start:
                continue
            row_count += 1
            for signal in values:
                raw = row.get(columns[signal], "")
                if raw is None or not raw.strip():
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    parser.error(f"Invalid {signal} at CSV line {line}: {raw!r}")
                if not math.isfinite(value):
                    parser.error(f"Non-finite {signal} at CSV line {line}")
                values[signal].append(value)
    if not row_count:
        parser.error("No samples in selected steady-state window")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["signal", "description", "unit", "sample_count", "mean", "minimum", "maximum", "status"])
        for signal, (description, unit) in SIGNALS.items():
            samples = values.get(signal, [])
            if samples:
                writer.writerow([signal, description, unit, len(samples),
                                 f"{sum(samples)/len(samples):.9g}",
                                 f"{min(samples):.9g}", f"{max(samples):.9g}", "observed"])
            else:
                writer.writerow([signal, description, unit, 0, "", "", "", "not exported"])
    print(f"Wrote {args.out} ({row_count} rows in window; {len(values)} recognized signals)")
    print("Warning: descriptive statistics only; not mechanical design ratings or stability certification.")

if __name__ == "__main__":
    main()
