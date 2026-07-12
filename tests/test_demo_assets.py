from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def test_launch_renderer_does_not_expand_controller_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert project["project"]["dependencies"] == ["bleak>=1.1.1"]
    assert "rich>=14.1.0" in project["dependency-groups"]["dev"]


def test_recorded_terminal_demo_keeps_section_titles_off_separator_lines() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.demo.recorded_demo",
            "tests/fixtures/recorded-ble-trace.json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    lines = [ANSI_ESCAPE.sub("", line).strip() for line in result.stdout.splitlines()]
    for title in ("Before", "Device confirmed", "Restored"):
        assert title in lines
        assert not any(title in line and "─" in line for line in lines)
    assert any(all(label in line for label in ("WATER", "TARGET", "POWER")) for line in lines)
    assert "OWER" not in lines
    assert max(map(len, lines)) <= 70


def test_public_demo_renderer_produces_reviewable_media(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/demo/render_assets.py",
            "--data",
            "tests/fixtures/demo-night.jsonl",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    expected = {
        "sleep-cooling-demo.mp4",
        "sleep-cooling-demo.gif",
        "sleep-cooling-poster.png",
        "sleep-cooling-data.png",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=width,height",
            "-of",
            "json",
            str(tmp_path / "sleep-cooling-demo.mp4"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    video_stream = next(stream for stream in metadata["streams"] if "width" in stream)
    duration = float(metadata["format"]["duration"])

    assert (video_stream["width"], video_stream["height"]) == (1920, 1080)
    assert 3 <= duration <= 20
    assert (tmp_path / "sleep-cooling-demo.gif").stat().st_size > 10_000
    assert (tmp_path / "sleep-cooling-data.png").stat().st_size > 10_000


def test_readme_ships_the_real_physical_setup_photo() -> None:
    photo = ROOT / "docs/assets/sleep-cooling-setup.jpg"
    readme = (ROOT / "README.md").read_text()

    assert "![Actual DIY sleep-cooling setup](docs/assets/sleep-cooling-setup.jpg)" in readme
    assert photo.stat().st_size > 100_000
    with Image.open(photo) as image:
        assert image.size == (1280, 960)
