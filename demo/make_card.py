"""Render a 1366x854 title/outro card PNG (ffmpeg here has no drawtext)."""
import sys

from PIL import Image, ImageDraw, ImageFont

out, line1, line2, line3 = sys.argv[1:5]
W, H = 1366, 854
img = Image.new("RGB", (W, H), (14, 20, 27))  # #0E141B
d = ImageDraw.Draw(img)
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONTB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(FONT, size)


def centered(
    text: str, f: ImageFont.FreeTypeFont, y: int, fill: tuple[int, int, int]
) -> None:
    w = d.textbbox((0, 0), text, font=f)[2]
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


# accent rule
d.rectangle([(W / 2 - 26, 300), (W / 2 + 26, 306)], fill=(79, 170, 192))
centered(line1, font(FONTB, 84), 330, (232, 237, 243))   # #E8EDF3
centered(line2, font(FONT, 30), 452, (184, 194, 206))     # #B8C2CE
centered(line3, font(FONT, 22), 512, (79, 170, 192))      # #4FAAC0
img.save(out)
print("wrote", out)
