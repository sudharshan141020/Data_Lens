"""Assemble docs/demo.gif from the frames captured by frontend/e2e/demo.spec.js.

    cd frontend
    DATALENS_DEMO=1 npx playwright test e2e/demo.spec.js
    python ../scripts/make_demo_gif.py            # needs: pip install pillow

Each frame is the real app. Frames of different sizes (a whole page, or one panel) are placed on a
common canvas with a caption, and the palette is reduced so the GIF stays small enough to load
quickly on a README page.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "frontend" / "test-results" / "demo-frames"
OUT = ROOT / "docs" / "demo.gif"

CANVAS = (960, 600)
CAPTION_H = 54
BG = (246, 249, 252)
INK = (23, 37, 62)
SECONDS = {"01-upload": 1.6, "02-dashboard": 2.2, "03-why-did-it-change": 2.6, "04-filters-follow": 2.6,
           "05-hypothesis-test": 2.8, "06-personal-data-guard": 2.6, "07-story-presentation": 2.0}
CAPTIONS = {
    "01-upload": "Drop in any CSV or Excel file",
    "02-dashboard": "A full report in seconds, no setup",
    "03-why-did-it-change": "Where a change came from, not just that it happened",
    "04-filters-follow": "Filter the data and the reports follow",
    "05-hypothesis-test": "Ask a direct question: is B different from A?",
    "06-personal-data-guard": "Stops before a share link leaks personal data",
    "07-story-presentation": "Present the story, one beat at a time",
}


def font(size):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def load(name):
    """The captured image for a frame. Frame 04 is two crops of the real page (the note, then the reports)."""
    if name == "04-filters-follow" and (FRAMES / "04a-note.png").exists():
        parts = [Image.open(FRAMES / f"{n}.png").convert("RGB") for n in ("04a-note", "04b-period", "04c-drivers-top")]
        width = max(p.width for p in parts)
        out = Image.new("RGB", (width, sum(p.height for p in parts) + 8 * (len(parts) - 1)), BG)
        y = 0
        for part in parts:
            out.paste(part, ((width - part.width) // 2, y))
            y += part.height + 8
        return out
    return Image.open(FRAMES / f"{name}.png").convert("RGB")


def has_frame(name):
    return (FRAMES / f"{name}.png").exists() or (name == "04-filters-follow" and (FRAMES / "04c-drivers-top.png").exists())


def frame(name):
    shot = load(name)
    room = (CANVAS[0] - 24, CANVAS[1] - CAPTION_H - 12)
    scale = min(room[0] / shot.width, room[1] / shot.height)
    shot = shot.resize((max(1, int(shot.width * scale)), max(1, int(shot.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", CANVAS, BG)
    canvas.paste(shot, ((CANVAS[0] - shot.width) // 2, CAPTION_H))
    d = ImageDraw.Draw(canvas)
    text, f = CAPTIONS[name], font(22)
    w = d.textlength(text, font=f)
    d.text(((CANVAS[0] - w) / 2, 14), text, fill=INK, font=f)
    return canvas


def main():
    names = [n for n in SECONDS if has_frame(n)]
    if not names:
        raise SystemExit(f"No frames in {FRAMES}. Run the capture step first (see the docstring).")
    images = [frame(n).quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for n in names]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=[int(SECONDS[n] * 1000) for n in names],
                   loop=0, optimize=True, disposal=2)
    print(f"{OUT.relative_to(ROOT)}: {len(names)} frames, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
