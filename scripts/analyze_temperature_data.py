#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


WATTS_PER_C_PER_HOUR_FOR_10L = 10 * 4186 / 3600


@dataclass(frozen=True)
class Sample:
    dt: datetime
    power: bool
    current: int
    target: int
    action: str | None
    active_schedule: dict | None


def load_samples(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        samples.append(
            Sample(
                dt=datetime.fromisoformat(row["timestamp"]),
                power=bool(row["power"]),
                current=int(row["temp_current"]),
                target=int(row["temp_target"]),
                action=row.get("schedule_action"),
                active_schedule=row.get("active_schedule"),
            )
        )
    return sorted(samples, key=lambda sample: sample.dt)


def night_start_for(sample_dt: datetime) -> date:
    if sample_dt.time() < time(12, 0):
        return (sample_dt - timedelta(days=1)).date()
    return sample_dt.date()


def samples_by_night(samples: list[Sample]) -> dict[date, list[Sample]]:
    nights: dict[date, list[Sample]] = defaultdict(list)
    for sample in samples:
        nights[night_start_for(sample.dt)].append(sample)
    return dict(sorted(nights.items()))


def nearest(samples: list[Sample], target: datetime, *, max_minutes: float = 25) -> Sample | None:
    if not samples:
        return None
    sample = min(samples, key=lambda item: abs((item.dt - target).total_seconds()))
    if abs((sample.dt - target).total_seconds()) / 60 > max_minutes:
        return None
    return sample


def sample_after(samples: list[Sample], target: datetime, *, max_minutes: float = 25) -> Sample | None:
    candidates = [sample for sample in samples if sample.dt >= target]
    if not candidates:
        return None
    sample = min(candidates, key=lambda item: item.dt)
    if (sample.dt - target).total_seconds() / 60 > max_minutes:
        return None
    return sample


def rate_c_per_hour(start: Sample, end: Sample) -> float | None:
    hours = (end.dt - start.dt).total_seconds() / 3600
    if hours <= 0:
        return None
    return (end.current - start.current) / hours


def heat_watts_for_10l(c_per_hour: float | None) -> float | None:
    if c_per_hour is None:
        return None
    return c_per_hour * WATTS_PER_C_PER_HOUR_FOR_10L


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def configure_time_axis(ax) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))


def save_full_timeline(samples: list[Sample], output: Path) -> None:
    t = [sample.dt for sample in samples]
    current = [sample.current for sample in samples]
    target = [sample.target for sample in samples]

    fig, ax = plt.subplots(figsize=(15, 7), dpi=180)
    fig.patch.set_facecolor("#fbfaf8")
    ax.set_facecolor("#fffefd")
    ax.step(t, current, where="post", color="#c2410c", linewidth=2.4, label="Current")
    ax.step(t, target, where="post", color="#2563eb", linewidth=1.7, label="Target", alpha=0.85)

    off_start = None
    for index, sample in enumerate(samples):
        if not sample.power and off_start is None:
            off_start = sample.dt
        if off_start and (sample.power or index == len(samples) - 1):
            off_end = sample.dt
            ax.axvspan(off_start, off_end, color="#64748b", alpha=0.10)
            off_start = None

    for sample in samples:
        if sample.action == "apply":
            ax.axvline(sample.dt, color="#1f2937", linestyle="--", linewidth=0.9, alpha=0.32)

    ax.set_title("Alpicool current vs target temperature", loc="left", fontsize=16, pad=12)
    ax.set_ylabel("Temperature (C)")
    ax.set_xlabel("Time")
    ax.grid(True, which="major", alpha=0.28)
    ax.grid(True, which="minor", alpha=0.10)
    configure_time_axis(ax)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def save_night_overlay(nights: dict[date, list[Sample]], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), dpi=180)
    fig.patch.set_facecolor("#fbfaf8")
    ax.set_facecolor("#fffefd")

    colors = ["#c2410c", "#2563eb", "#047857", "#7c3aed", "#be123c"]
    plotted = 0
    for index, (night, samples) in enumerate(nights.items()):
        start = datetime.combine(night, time(17, 0))
        end = start + timedelta(hours=19)
        window = [sample for sample in samples if start <= sample.dt <= end]
        if len(window) < 12:
            continue
        x_values = [(sample.dt - start).total_seconds() / 3600 for sample in window]
        y_values = [sample.current for sample in window]
        ax.step(
            x_values,
            y_values,
            where="post",
            linewidth=2.2,
            color=colors[index % len(colors)],
            label=f"{night} night",
        )
        plotted += 1

    for x, label in [(0, "17"), (6, "23"), (9, "02"), (11, "04"), (15, "08")]:
        ax.axvline(x, color="#1f2937", linestyle="--", linewidth=0.8, alpha=0.22)
        ax.text(x + 0.06, 15.2, label, fontsize=8, color="#4b5563")

    ax.set_title("Nightly temperature curves aligned at 17:00", loc="left", fontsize=16, pad=12)
    ax.set_xlabel("Hours since 17:00")
    ax.set_ylabel("Current temperature (C)")
    ax.set_xlim(0, 19)
    ax.set_ylim(15, 31)
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def save_post_off_overlay(nights: dict[date, list[Sample]], output: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 7), dpi=180)
    fig.patch.set_facecolor("#fbfaf8")
    ax.set_facecolor("#fffefd")

    colors = ["#c2410c", "#2563eb", "#047857", "#7c3aed", "#be123c"]
    plotted = 0
    for index, (night, samples) in enumerate(nights.items()):
        off_at = datetime.combine(night + timedelta(days=1), time(4, 0))
        end = off_at + timedelta(hours=8)
        window = [sample for sample in samples if off_at <= sample.dt <= end]
        if len(window) < 8:
            continue
        x_values = [(sample.dt - off_at).total_seconds() / 3600 for sample in window]
        y_values = [sample.current for sample in window]
        ax.step(
            x_values,
            y_values,
            where="post",
            linewidth=2.3,
            color=colors[index % len(colors)],
            label=f"{night} -> morning",
        )
        plotted += 1

    ax.set_title("Post-04:00 warmup curves", loc="left", fontsize=16, pad=12)
    ax.set_xlabel("Hours after 04:00 power-off")
    ax.set_ylabel("Current temperature (C)")
    ax.set_xlim(0, 8)
    ax.set_ylim(15, 31)
    ax.grid(True, alpha=0.25)
    if plotted:
        ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def build_report(samples: list[Sample], plots: dict[str, Path]) -> str:
    nights = samples_by_night(samples)
    gaps = [(b.dt - a.dt).total_seconds() / 60 for a, b in zip(samples, samples[1:])]
    action_counts = Counter(sample.action or "legacy" for sample in samples)
    target_counts = Counter(sample.target for sample in samples)
    power_counts = Counter(sample.power for sample in samples)

    def report_link(path: Path) -> str:
        return os.path.relpath(path, plots["report_dir"])

    lines = [
        "# Alpicool Temperature Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='minutes')}",
        f"Data range: {samples[0].dt.isoformat(timespec='minutes')} -> {samples[-1].dt.isoformat(timespec='minutes')}",
        f"Samples: {len(samples)}",
        "",
        "## Plots",
        "",
        f"![Full timeline]({report_link(plots['full'])})",
        "",
        f"![Night overlay]({report_link(plots['night_overlay'])})",
        "",
        f"![Post-off warmup overlay]({report_link(plots['post_off'])})",
        "",
        "## Data Quality",
        "",
        f"- Sample gap: min {fmt(min(gaps))} min, mean {fmt(mean(gaps))} min, max {fmt(max(gaps))} min.",
        f"- Large gaps over 20 minutes: {sum(1 for gap in gaps if gap > 20)}.",
        f"- Schedule actions: {dict(action_counts)}.",
        f"- Power states: on {power_counts[True]}, off {power_counts[False]}.",
        f"- Target counts: {dict(sorted(target_counts.items()))}.",
        "",
        "## Night Summaries",
        "",
        "| Night | Samples | Min | Max | 17:00 | 23:00 | 02:00 | 04:00 | 08:00 | 04-06 warmup | 04-10 warmup | 10L heat, early |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for night, night_samples in nights.items():
        if len(night_samples) < 12:
            continue
        start = datetime.combine(night, time(17, 0))
        checkpoints = {
            "17": nearest(night_samples, start),
            "23": nearest(night_samples, start + timedelta(hours=6)),
            "02": nearest(night_samples, start + timedelta(hours=9)),
            "04": nearest(night_samples, start + timedelta(hours=11)),
            "08": nearest(night_samples, start + timedelta(hours=15)),
            "10": nearest(night_samples, start + timedelta(hours=17)),
        }
        off = sample_after(night_samples, start + timedelta(hours=11))
        plus2 = nearest(night_samples, start + timedelta(hours=13))
        plus6 = nearest(night_samples, start + timedelta(hours=17))
        early_rate = rate_c_per_hour(off, plus2) if off and plus2 else None
        long_rate = rate_c_per_hour(off, plus6) if off and plus6 else None
        early_watts = heat_watts_for_10l(early_rate)

        def cv(key: str) -> str:
            sample = checkpoints[key]
            return "n/a" if sample is None else str(sample.current)

        lines.append(
            "| "
            + " | ".join(
                [
                    str(night),
                    str(len(night_samples)),
                    str(min(sample.current for sample in night_samples)),
                    str(max(sample.current for sample in night_samples)),
                    cv("17"),
                    cv("23"),
                    cv("02"),
                    cv("04"),
                    cv("08"),
                    f"{fmt(early_rate)} C/h",
                    f"{fmt(long_rate)} C/h",
                    f"{fmt(early_watts, 1)} W",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The schedule is now stable: the old one-shot calendar jobs are gone and the reconciler mostly reports `noop`, meaning the fridge is already in the intended state.",
            "- The compressor phase consistently pulls the system down to about 16 C. The exact timing is quantized because the fridge reports integer Celsius.",
            "- The fixed schedule already creates a morning ramp before shutdown: by 04:00 the water is usually around 22 C, because the 02:00 target is 20 C and the fridge hysteresis allows drift above target before compressor restart.",
            "- The first partial night is the cold-shutdown case: power-off from 16 C produced about 3.0 C/hour over the first two hours, roughly 35 W into 10 L of water.",
            "- The fuller nights are milder: power-off from about 22 C warms at roughly 1.5-2.0 C/hour early, equivalent to about 17-23 W into 10 L of water. The long-window warmup slows further as the water approaches room/body equilibrium.",
            "- Without a control night disconnected from the body, the data cannot separate room heat from body heat. A no-body control run would estimate room-only heat gain; the difference is the body-coupled contribution.",
            "",
            "## Practical Read",
            "",
            "- 04:00 hard-off is energy-efficient and currently lets the water drift into the high 20s by morning.",
            "- A gentler late-night strategy would be a cap rather than timed pulsing: after 04:00, only turn cooling back on if water exceeds something like 24-25 C, and stop again around 22-23 C.",
            "- Do not tune yet from one number. The useful next comparison is subjective sleep quality against the post-04:00 curve.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Alpicool temperature tracking JSONL.")
    parser.add_argument("--input", default="data/fridge-status.jsonl")
    parser.add_argument("--plots-dir", default="plots")
    parser.add_argument("--reports-dir", default="reports")
    args = parser.parse_args()

    input_path = Path(args.input)
    plots_dir = Path(args.plots_dir)
    reports_dir = Path(args.reports_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(input_path)
    if len(samples) < 2:
        raise SystemExit("need at least two samples")

    stamp = datetime.now().strftime("%Y-%m-%d")
    full_plot = plots_dir / f"temperature-full-{stamp}.png"
    night_plot = plots_dir / f"temperature-night-overlay-{stamp}.png"
    post_off_plot = plots_dir / f"temperature-post-off-warmup-{stamp}.png"

    nights = samples_by_night(samples)
    save_full_timeline(samples, full_plot)
    save_night_overlay(nights, night_plot)
    save_post_off_overlay(nights, post_off_plot)

    report_path = reports_dir / f"temperature-report-{stamp}.md"
    plots = {
        "full": full_plot.resolve(),
        "night_overlay": night_plot.resolve(),
        "post_off": post_off_plot.resolve(),
        "report_dir": report_path.resolve().parent,
    }
    report_path.write_text(build_report(samples, plots), encoding="utf-8")
    print(report_path)
    print(full_plot)
    print(night_plot)
    print(post_off_plot)


if __name__ == "__main__":
    main()
