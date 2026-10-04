"""Draws the Scrubs "S" mark (the white tile with a navy S from the app header) as:
  desktop/installer/scrubs.ico   app, shortcut and Add/Remove Programs icon
  desktop/installer/banner.bmp   top banner of the install wizard (493 x 58)
  desktop/installer/dialog.bmp   welcome and finish pages of the wizard (493 x 312)
  app/icon.png                   favicon for the web app (Next.js picks it up)

Run after changing the colours:  backend/.venv/Scripts/python desktop/installer/make_art.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAVY = (11, 47, 78)        # --masthead
WHITE = (255, 255, 255)
TEAL = (0, 120, 138)       # --masthead-rule
FONT = "C:/Windows/Fonts/segoeuib.ttf"   # Segoe UI Bold


def font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default(size)


def tile(size: int, background=NAVY) -> Image.Image:
    """The header mark: a white rounded tile with a navy S, on the navy header colour."""
    img = Image.new("RGBA", (size, size), background)
    d = ImageDraw.Draw(img)
    inset = max(1, round(size * 0.12))
    d.rounded_rectangle([inset, inset, size - 1 - inset, size - 1 - inset], radius=max(1, size // 16), fill=WHITE)
    f = font(round(size * 0.62))
    box = d.textbbox((0, 0), "S", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), "S", font=f, fill=NAVY)
    return img


def icon() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big = tile(256)
    big.save(HERE / "scrubs.ico", sizes=[(s, s) for s in sizes])
    tile(128).save(ROOT / "app" / "icon.png")


def banner() -> None:
    img = Image.new("RGB", (493, 58), WHITE)
    img.paste(tile(46).convert("RGB"), (493 - 46 - 8, 6))
    ImageDraw.Draw(img).line([(0, 57), (493, 57)], fill=(214, 219, 225))
    img.save(HERE / "banner.bmp")


def dialog() -> None:
    img = Image.new("RGB", (493, 312), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 163, 311], fill=NAVY)        # WiX draws its text to the right of x=164
    d.rectangle([160, 0, 163, 311], fill=TEAL)
    img.paste(tile(72).convert("RGB"), (44, 60))
    f = font(26)
    box = d.textbbox((0, 0), "Scrubs", font=f)
    d.text(((160 - (box[2] - box[0])) / 2, 148), "Scrubs", font=f, fill=WHITE)
    img.save(HERE / "dialog.bmp")


if __name__ == "__main__":
    icon()
    banner()
    dialog()
    print("Wrote scrubs.ico, banner.bmp, dialog.bmp and app/icon.png")
