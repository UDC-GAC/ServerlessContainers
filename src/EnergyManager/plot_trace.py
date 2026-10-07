#!/usr/bin/env python3
"""
Auxiliar script to plot the decisions of the EnergyManager over time, from its trace (energy_manager_trace.jsonl).

For each container (one column of panels per container, time on the x axis):
  * power: energy usage seen by the controller (mean of the last MIN_ENERGY_POINTS samples), budget and budget band
    (+/- ALLOWED_ERROR/2), with the decision of each iteration (SCALE up/down, EVENTS, HOLD, WAIT);
  * CPU: CPU quota (allocation) and CPU usage (user + kernel) seen by the controller; also including the CPU
    demand (usage + wait) and the CPU pressure (share of the demand waiting for a CPU, right axis);
  * events: accumulated up/down events and required events (only with decisions traced by the built-in controller).
On top, the host power (RAPL - sensor) and the age of the data used in each iteration (data lag).

Usage:
    python3 plot_trace.py energy_manager_trace.jsonl [-o plot.png] [-c CONTAINER ...] [--start S] [--end S]
                          [--allowed-error 0.05] [--data-time] [--show]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COLORS = {"power": "#1f77b4", "budget": "#d62728", "quota": "#2ca02c", "usage": "#ff7f0e", "up": "#2ca02c",
          "down": "#d62728", "required": "#7f7f7f", "hold": "#9e9e9e", "wait": "#bcbd22", "events": "#9467bd",
          "demand": "#8c564b", "pressure": "#e377c2"}


def load_trace(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return sorted(entries, key=lambda e: e["ts"])


def collect(entries, t0, data_time):
    """Per container and per host time series."""
    containers = defaultdict(lambda: defaultdict(list))
    hosts = defaultdict(lambda: defaultdict(list))
    for e in entries:
        t = e["ts"] - t0
        decisions = e.get("controller_trace") or {}
        applied = e.get("applied") or {}
        for hostname, host in e.get("hosts", {}).items():
            power = host.get("power") or {}
            if power.get("global") is not None:
                hosts[hostname]["t"].append(t)
                hosts[hostname]["global"].append(power["global"])
                hosts[hostname]["budgets"].append(sum(c.get("budget", 0) for c in host["containers"].values()))
            for name, c in host.get("containers", {}).items():
                s = containers[name]
                usages = c.get("usages") or {}
                x = (c["energy_ts"] - t0) if data_time and c.get("energy_ts") else t
                s["t"].append(x)
                s["budget"].append(c.get("budget"))
                s["quota"].append(c.get("cpu_alloc"))
                s["power"].append(usages.get("structure.energy.usage"))
                s["cpu"].append(usages.get("structure.cpu.usage"))
                wait = usages.get("structure.cpu.wait")
                s["demand"].append(usages["structure.cpu.usage"] + wait if wait is not None else None)
                s["pressure"].append(100 * usages["structure.cpu.pressure"] if wait is not None else None)
                s["lag"].append(e["ts"] - c["energy_ts"] if c.get("energy_ts") else None)
                d = decisions.get(name, {})
                outcome = d.get("outcome", "")
                if name in applied and applied[name]:
                    outcome = "SCALE up" if applied[name] > 0 else "SCALE down"
                s["outcome"].append(outcome)
                s["reason"].append(d.get("reason", ""))
                s["up"].append(d.get("up"))
                s["down"].append(d.get("down"))
                s["required"].append(d.get("required"))
    return containers, hosts


def points(ts, values, keep=lambda i: True):
    pairs = [(t, v) for i, (t, v) in enumerate(zip(ts, values)) if v is not None and keep(i)]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def plot_container(axes, name, s, allowed_error):
    ax_p, ax_c, ax_e = axes
    t = s["t"]
    # Power, budget and band
    tb, b = points(t, s["budget"])
    ax_p.step(tb, b, where="post", color=COLORS["budget"], lw=1.5, label="budget")
    ax_p.fill_between(tb, [x * (1 - allowed_error / 2) for x in b], [x * (1 + allowed_error / 2) for x in b],
                      step="post", color=COLORS["budget"], alpha=0.12, label=f"band ±{allowed_error / 2:.1%}")
    tp, p = points(t, s["power"])
    ax_p.plot(tp, p, color=COLORS["power"], lw=1, label="power (controller)")
    for outcome, marker, color, size in [("SCALE up", "^", COLORS["up"], 70), ("SCALE down", "v", COLORS["down"], 70),
                                         ("HOLD", ".", COLORS["hold"], 25), ("WAIT", "x", COLORS["wait"], 25)]:
        to, po = points(t, s["power"], lambda i: s["outcome"][i].startswith(outcome))
        if to:
            ax_p.scatter(to, po, marker=marker, color=color, s=size, zorder=5, label=outcome)
    ax_p.set_ylabel("Power (W)")
    ax_p.set_title(name, loc="left", fontsize=10, fontweight="bold")
    ax_p.legend(loc="upper left", fontsize=7, ncol=4, framealpha=0.8)

    # CPU quota and usage
    tq, q = points(t, s["quota"])
    ax_c.step(tq, q, where="post", color=COLORS["quota"], lw=1.5, label="CPU quota")
    tu, u = points(t, s["cpu"])
    ax_c.plot(tu, u, color=COLORS["usage"], lw=1, label="CPU usage (user + kernel)")
    for outcome, marker, color in [("SCALE up", "^", COLORS["up"]), ("SCALE down", "v", COLORS["down"])]:
        to, qo = points(t, s["quota"], lambda i: s["outcome"][i].startswith(outcome))
        if to:
            ax_c.scatter(to, qo, marker=marker, color=color, s=50, zorder=5)
    td, d = points(t, s["demand"])
    lines = []
    if td:
        ax_c.plot(td, d, color=COLORS["demand"], lw=0.8, ls="--", label="CPU demand (usage + wait)")
        ax_pr = ax_c.twinx()
        tpr, pr = points(t, s["pressure"])
        lines = ax_pr.plot(tpr, pr, color=COLORS["pressure"], lw=0.8, alpha=0.8, label="CPU pressure (%)")
        ax_pr.set_ylim(0, 100)
        ax_pr.set_ylabel("CPU pressure (%)", color=COLORS["pressure"])
    ax_c.set_ylabel("CPU (shares)")
    handles, labels = ax_c.get_legend_handles_labels()
    ax_c.legend(handles + lines, labels + [l.get_label() for l in lines], loc="upper left", fontsize=7, ncol=2,
                framealpha=0.8)

    # Events
    if any(v is not None for v in s["required"]):
        for key, color in [("up", COLORS["up"]), ("down", COLORS["down"])]:
            te, ev = points(t, s[key])
            ax_e.step(te, ev, where="post", color=color, lw=1.2, label=f"{key} events")
        tr, r = points(t, s["required"])
        ax_e.step(tr, r, where="post", color=COLORS["required"], lw=1, ls="--", label="required")
        ax_e.legend(loc="upper left", fontsize=7, ncol=3, framealpha=0.8)
    else:
        ax_e.text(0.5, 0.5, "no decisions in the trace (built-in controller traces them)", ha="center",
                  va="center", transform=ax_e.transAxes, fontsize=8, color="gray")
    ax_e.set_ylabel("Events")


def main():
    parser = argparse.ArgumentParser(description="Plot EnergyManager decisions from its trace")
    parser.add_argument("trace", help="energy_manager_trace.jsonl")
    parser.add_argument("-o", "--output", help="output image (default: <trace>.png)")
    parser.add_argument("-c", "--containers", nargs="+", help="containers to plot (default: all)")
    parser.add_argument("--start", type=float, default=None, help="first second to plot (from the trace start)")
    parser.add_argument("--end", type=float, default=None, help="last second to plot (from the trace start)")
    parser.add_argument("--allowed-error", type=float, default=0.05, help="ALLOWED_ERROR of the controller (band)")
    parser.add_argument("--data-time", action="store_true", help="plot usages at the time of their data (energy_ts)")
    parser.add_argument("--show", action="store_true", help="show the figure instead of only saving it")
    args = parser.parse_args()

    if not args.show:
        matplotlib.use("Agg")
    entries = load_trace(args.trace)
    if not entries:
        sys.exit(f"No entries in {args.trace}")
    t0 = entries[0]["ts"]
    entries = [e for e in entries if (args.start is None or e["ts"] - t0 >= args.start)
               and (args.end is None or e["ts"] - t0 <= args.end)]
    containers, hosts = collect(entries, t0, args.data_time)
    names = [n for n in sorted(containers) if not args.containers or n in args.containers]
    if not names:
        sys.exit("No containers to plot")

    n = len(names)
    fig, axes = plt.subplots(4, n, figsize=(max(9, 7 * n), 11), sharex=True, squeeze=False,
                             gridspec_kw={"height_ratios": [1.2, 2, 1.6, 1.2]})
    # Host power and data lag (first row)
    for j, name in enumerate(names):
        ax = axes[0][j]
        for hostname, h in hosts.items():
            ax.plot(h["t"], h["global"], color="black", lw=1, label=f"{hostname} power (RAPL - sensor)")
            ax.step(h["t"], h["budgets"], where="post", color=COLORS["budget"], lw=1, ls=":", label="sum of budgets")
        ax.set_ylabel("Host (W)")
        ax2 = ax.twinx()
        tl, lag = points(containers[name]["t"], containers[name]["lag"])
        ax2.plot(tl, lag, color=COLORS["events"], lw=0.8, alpha=0.7, label="data lag")
        ax2.set_ylabel("Data lag (s)", color=COLORS["events"])
        lines = ax.get_legend_handles_labels()[0] + [Line2D([], [], color=COLORS["events"], lw=0.8)]
        labels = ax.get_legend_handles_labels()[1] + ["data lag (s)"]
        ax.legend(lines, labels, loc="upper left", fontsize=7, ncol=3, framealpha=0.8)
        plot_container([axes[1][j], axes[2][j], axes[3][j]], name, containers[name], args.allowed_error)
        axes[3][j].set_xlabel("Time (s)" + (" (data time)" if args.data_time else ""))
        for ax in axes[:, j]:
            ax.grid(alpha=0.3)

    start = datetime.fromtimestamp(t0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    controllers = sorted({e.get("controller") for e in entries if e.get("controller")})
    fig.suptitle(f"EnergyManager decisions — {os.path.basename(args.trace)} (start {start}, controller "
                 f"{', '.join(controllers)})", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    output = args.output or os.path.splitext(args.trace)[0] + ".png"
    fig.savefig(output, dpi=130)
    print(f"Saved {output}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
