#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


BG = "#0e0d0b"
TEXT = "#d4cfc6"
MUTED = "#8a857b"
GREEN = "#7a9e7e"
GOLD = "#c4a055"
FONT = Path("/System/Library/Fonts/SFNS.ttf")


def save_photo(source: Path, output: Path) -> Image.Image:
    with Image.open(source) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    if image.size != (1280, 960):
        image.thumbnail((1280, 960), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=88, optimize=True, progressive=True, exif=b"")
    return image


def render_social_preview(photo: Image.Image, output: Path) -> None:
    canvas = Image.new("RGB", (1280, 640), BG)
    photo_panel = ImageOps.fit(photo, (820, 640), Image.Resampling.LANCZOS, centering=(0.52, 0.5))
    canvas.paste(photo_panel, (460, 0))

    draw = ImageDraw.Draw(canvas)
    small = ImageFont.truetype(str(FONT), 19)
    title = ImageFont.truetype(str(FONT), 48)
    subtitle = ImageFont.truetype(str(FONT), 24)
    detail = ImageFont.truetype(str(FONT), 18)

    draw.text((54, 64), "DIY SLEEP COOLING", font=small, fill=GREEN, stroke_width=0)
    draw.rectangle((54, 104, 112, 108), fill=GOLD)
    draw.multiline_text(
        (54, 145),
        "A camping fridge\ncooling a mattress",
        font=title,
        fill=TEXT,
        spacing=10,
    )
    draw.multiline_text(
        (54, 350),
        "Local Bluetooth control.\nReal overnight data.",
        font=subtitle,
        fill=MUTED,
        spacing=8,
    )
    draw.text((54, 544), "github.com/markschroedr", font=detail, fill=MUTED)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the real sleep-cooling launch photo.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--photo-output", required=True, type=Path)
    parser.add_argument("--preview-output", required=True, type=Path)
    args = parser.parse_args()

    photo = save_photo(args.source, args.photo_output)
    render_social_preview(photo, args.preview_output)
    print(f"photo: {args.photo_output} ({photo.width}x{photo.height})")
    print(f"social preview: {args.preview_output} (1280x640)")


if __name__ == "__main__":
    main()
