"""Generate /public/og-image.png (1200x630) for askadil.org link previews.

Uses the brand palette + the existing logo concept. Pure PIL — no
external API call. Idempotent.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_LOGO = ROOT / "docs" / "design" / "askadil-redesign" / "logo_concept.png"
OUT_PATH = ROOT / "adil-frontend-next" / "public" / "og-image.png"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

W, H = 1200, 630
PAPER = (244, 238, 220)  # --color-paper
PAPER_WARM = (235, 226, 201)  # --color-paper-warm
INK = (15, 62, 41)  # --color-ink
EMERALD = (31, 111, 74)  # --color-emerald
GOLD = (200, 155, 60)  # --color-gold
INK_FADED = (101, 119, 109)  # approx --color-ink-faded


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Best-effort font lookup with a Pillow fallback."""
    candidates = [
        f"C:/Windows/Fonts/{name}.ttf",
        f"C:/Windows/Fonts/{name}.TTF",
        f"/Library/Fonts/{name}.ttf",
        f"/usr/share/fonts/truetype/{name}.ttf",
    ]
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> None:
    canvas = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(canvas)

    # Subtle warm wash on the right
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(700, W):
        alpha = int(60 * (x - 700) / (W - 700))
        od.line([(x, 0), (x, H)], fill=PAPER_WARM + (alpha,))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Top-left ornament: gold rule
    draw.rectangle([(72, 72), (220, 73)], fill=GOLD)

    # Eyebrow
    eyebrow_font = _font("InterTight-Medium", 22)
    draw.text((72, 90), "ASKADIL  ·  LEGAL GUIDANCE", font=eyebrow_font, fill=GOLD)

    # Headline (serif)
    title_font = _font("constan", 58)
    draw.text((72, 150), "Free, citation-backed", font=title_font, fill=INK)
    draw.text((72, 218), "UK legal guidance", font=title_font, fill=INK)
    draw.text((72, 286), "for British Muslims.", font=title_font, fill=EMERALD)

    # Sub-line (two-line, kept short of the logo)
    body_font = _font("constan", 22)
    draw.text((72, 400), "Discrimination · Hate crime", font=body_font, fill=INK_FADED)
    draw.text((72, 432), "Mental Capacity & Court of Protection", font=body_font, fill=INK_FADED)

    # Footer rule + URL + MCB attribution
    draw.rectangle([(72, 510), (W - 72, 511)], fill=GOLD)
    foot_font = _font("InterTight-Medium", 20)
    draw.text((72, 530), "askadil.org", font=foot_font, fill=INK)
    draw.text(
        (W - 72 - 320, 530),
        "A MUSLIM COUNCIL OF BRITAIN INITIATIVE",
        font=_font("InterTight-Medium", 16),
        fill=GOLD,
    )

    # Logo on the right (sized to clear the headline text column)
    if SRC_LOGO.exists():
        logo = Image.open(SRC_LOGO).convert("RGBA")
        logo.thumbnail((280, 280))
        canvas.paste(logo, (W - 280 - 96, 170), logo)

    canvas.save(OUT_PATH, format="PNG", optimize=True)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")

    # Square brand assets derived from the logo
    pub = OUT_PATH.parent
    if SRC_LOGO.exists():
        logo_full = Image.open(SRC_LOGO).convert("RGBA")
        for size, name in [(180, "apple-touch-icon.png"), (512, "icon-512.png"), (32, "favicon-32.png")]:
            img = logo_full.copy()
            img.thumbnail((size, size))
            bg = Image.new("RGBA", (size, size), PAPER + (255,))
            bg.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
            bg.convert("RGB").save(pub / name, format="PNG", optimize=True)
            print(f"Wrote {pub / name}")


if __name__ == "__main__":
    main()
