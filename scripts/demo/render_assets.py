#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


BG = "#0e0d0b"
PANEL = "#151412"
TEXT = "#d4cfc6"
MUTED = "#8a857b"
BORDER = "#262420"
GOLD = "#c4a055"
GREEN = "#7a9e7e"


@dataclass(frozen=True)
class Sample:
    timestamp: datetime
    power: bool
    current: int
    target: int


def load_samples(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            samples.append(
                Sample(
                    timestamp=datetime.fromisoformat(raw["timestamp"]),
                    power=bool(raw["power"]),
                    current=int(raw["temp_current"]),
                    target=int(raw["temp_target"]),
                )
            )
    if len(samples) < 4:
        raise ValueError("demo visualization needs at least four samples")
    return sorted(samples, key=lambda sample: sample.timestamp)


def select_night(samples: list[Sample]) -> list[Sample]:
    first_day = samples[0].timestamp.date()
    last_day = samples[-1].timestamp.date()
    candidates: list[list[Sample]] = []
    day = first_day
    while day <= last_day:
        start = datetime.combine(day, time(17, 0))
        end = start + timedelta(hours=17)
        night = [sample for sample in samples if start <= sample.timestamp <= end]
        if len(night) >= 8 and night[-1].timestamp >= start + timedelta(hours=11):
            candidates.append(night)
        day += timedelta(days=1)
    return candidates[-1] if candidates else samples


def contiguous_off_ranges(samples: list[Sample]) -> list[tuple[datetime, datetime]]:
    ranges: list[tuple[datetime, datetime]] = []
    start: datetime | None = None
    for sample in samples:
        if not sample.power and start is None:
            start = sample.timestamp
        elif sample.power and start is not None:
            ranges.append((start, sample.timestamp))
            start = None
    if start is not None:
        ranges.append((start, samples[-1].timestamp))
    return ranges


def render_chart(samples: list[Sample], output: Path) -> None:
    night = select_night(samples)
    times = [sample.timestamp for sample in night]
    current = [sample.current for sample in night]
    target = [sample.target for sample in night]

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 13,
            "axes.facecolor": PANEL,
            "figure.facecolor": BG,
            "axes.edgecolor": BORDER,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": TEXT,
        }
    )
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.78, bottom=0.17)

    for start, end in contiguous_off_ranges(night):
        ax.axvspan(start, end, color=TEXT, alpha=0.045, linewidth=0)

    ax.plot(times, current, color=GOLD, linewidth=3.2, label="Water temperature", zorder=3)
    ax.step(times, target, where="post", color=MUTED, linewidth=1.8, linestyle=(0, (4, 4)), label="Cooler target", zorder=2)
    ax.scatter(times[-1], current[-1], s=50, color=GOLD, edgecolor=BG, linewidth=1.5, zorder=4)

    ax.grid(axis="y", color=TEXT, alpha=0.08, linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(BORDER)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_ylabel("°C", rotation=0, labelpad=18, va="center")
    ax.set_ylim(min(min(current), min(target)) - 2, max(max(current), max(target)) + 2)

    fig.text(0.08, 0.91, "ONE REAL NIGHT", fontsize=11, color=GREEN, weight="bold")
    fig.text(0.08, 0.84, "Cooling a mattress", fontsize=30, color=TEXT, weight="bold")
    fig.text(0.08, 0.795, "with a camping fridge · 15-minute Bluetooth samples · local control", fontsize=13, color=MUTED)

    minimum = min(current)
    start_temp = current[0]
    fig.text(0.73, 0.91, f"{start_temp} → {minimum}°C", fontsize=18, color=GOLD, weight="bold", ha="left")
    fig.text(0.73, 0.872, "evening cooldown", fontsize=11, color=MUTED, ha="left")

    legend = ax.legend(loc="upper left", frameon=False, ncol=2, bbox_to_anchor=(0, 1.04), borderaxespad=0)
    for text in legend.get_texts():
        text.set_color(MUTED)

    fig.text(0.08, 0.075, "17:00  cool to 16°", fontsize=11, color=MUTED)
    fig.text(0.31, 0.075, "23:00  raise to 18°", fontsize=11, color=MUTED)
    fig.text(0.55, 0.075, "02:00  raise to 20°", fontsize=11, color=MUTED)
    fig.text(0.79, 0.075, "04:00  power off", fontsize=11, color=MUTED)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=BG)
    plt.close(fig)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def render_video(chart: Path, output: Path, terminal_video: Path | None) -> None:
    intro = output.with_name(".data-intro.mp4")
    run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(chart), "-t", "4.2",
            "-vf", "zoompan=z='min(zoom+0.00012,1.018)':d=126:s=1920x1080:fps=30,format=yuv420p",
            "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "18", str(intro),
        ]
    )

    if terminal_video is None:
        intro.replace(output)
        return

    run(
        [
            "ffmpeg", "-y", "-i", str(intro), "-i", str(terminal_video),
            "-filter_complex",
            "[0:v]fps=30,setsar=1[v0];"
            "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BG},fps=30,setsar=1[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[out]",
            "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-movflags", "+faststart", str(output),
        ]
    )
    intro.unlink(missing_ok=True)


def render_gif(video: Path, output: Path) -> None:
    palette = output.with_name(".palette.png")
    filters = "fps=12,scale=960:-2:flags=lanczos"
    run(["ffmpeg", "-y", "-i", str(video), "-vf", f"{filters},palettegen=max_colors=128:stats_mode=diff", str(palette)])
    run(["ffmpeg", "-y", "-i", str(video), "-i", str(palette), "-lavfi", f"{filters}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3", str(output)])
    palette.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render public sleep-cooling launch media.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--terminal-video", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    chart = args.output_dir / "sleep-cooling-data.png"
    poster = args.output_dir / "sleep-cooling-poster.png"
    video = args.output_dir / "sleep-cooling-demo.mp4"
    gif = args.output_dir / "sleep-cooling-demo.gif"

    render_chart(load_samples(args.data), chart)
    shutil.copyfile(chart, poster)
    render_video(chart, video, args.terminal_video)
    render_gif(video, gif)

    print(json.dumps({"chart": str(chart), "poster": str(poster), "video": str(video), "gif": str(gif)}, indent=2))


if __name__ == "__main__":
    main()
