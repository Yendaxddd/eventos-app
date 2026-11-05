"""Generates eventos_app/resources/icon.ico + icon.png.  Run: python packaging/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "eventos_app" / "resources"
SIZE = 1024


def render() -> Image.Image:
    # diagonal gradient, deep indigo -> violet
    base = Image.new("RGB", (SIZE, SIZE))
    px = base.load()
    top, bottom = (38, 28, 92), (124, 92, 255)
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x + y) / (2 * SIZE)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=230, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(base, mask=mask)

    bolt = [(612, 96), (252, 580), (478, 580), (400, 928), (780, 424), (548, 424)]
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x + 14, y + 22) for x, y in bolt], fill=(10, 6, 40, 150))
    icon = Image.alpha_composite(icon, shadow.filter(ImageFilter.GaussianBlur(22)))
    ImageDraw.Draw(icon).polygon(bolt, fill=(255, 255, 255, 255))
    return icon


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = render()
    icon.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    icon.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", OUT / "icon.ico", OUT / "icon.png")


if __name__ == "__main__":
    main()
