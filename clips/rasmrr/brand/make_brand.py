"""Logo (800x800) and YouTube banner (2560x1440) for the unofficial Rasmr clips channel.

Beast caption palette: green #3CFF5A highlight, red #E63B3B title box, white caps, black outline.
Run: python3 make_brand.py  (needs Pillow; fonts come from stream-clipper/assets/fonts)
"""
import math
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, '..', '..', '..', 'stream-clipper', 'assets', 'fonts')
BLACK_FONT = os.path.join(FONTS, 'Montserrat-Black.ttf')
BOLD_FONT = os.path.join(FONTS, 'Montserrat-ExtraBold.ttf')

GREEN = (60, 255, 90)
RED = (230, 59, 59)
WHITE = (255, 255, 255)
INK = (10, 10, 12)


def font(path, size):
    return ImageFont.truetype(path, size)


def glow_bg(w, h, spots):
    """Near-black background with soft colored glows: spots = [(x, y, radius, rgb, alpha)]."""
    bg = Image.new('RGB', (w, h), INK)
    for x, y, r, rgb, a in spots:
        layer = Image.new('L', (w, h), 0)
        ImageDraw.Draw(layer).ellipse((x - r, y - r, x + r, y + r), fill=a)
        layer = layer.filter(ImageFilter.GaussianBlur(r * 0.6))
        bg = Image.composite(Image.new('RGB', (w, h), rgb), bg, layer)
    # subtle diagonal speed lines
    d = ImageDraw.Draw(bg)
    for i in range(-h, w, max(18, w // 60)):
        d.line((i, h, i + h * 0.6, 0), fill=(22, 22, 26), width=2)
    return bg


def text_size(f, s):
    l, t, r, b = f.getbbox(s)
    return r - l, b - t, l, t


def lockup(scale=1.0):
    """The tilted RASMR / CLIPS block on a transparent canvas (beast style)."""
    f_top = font(BLACK_FONT, int(150 * scale))
    f_bot = font(BLACK_FONT, int(210 * scale))
    top, bot = 'RASMR', 'CLIPS'
    tw, th, tl, tt = text_size(f_top, top)
    bw, bh, bl, bt = text_size(f_bot, bot)
    pad_x, pad_y = int(46 * scale), int(30 * scale)
    gap = int(20 * scale)
    stroke = int(14 * scale)
    W = max(tw + 2 * pad_x, bw + 2 * stroke) + int(60 * scale)
    H = th + 2 * pad_y + gap + bh + 2 * stroke + int(60 * scale)
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # red title box with RASMR
    box_w, box_h = tw + 2 * pad_x, th + 2 * pad_y
    bx, by = (W - box_w) // 2, int(30 * scale)
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((bx + 10 * scale, by + 12 * scale, bx + box_w + 10 * scale, by + box_h + 12 * scale),
                                             radius=int(18 * scale), fill=(0, 0, 0, 200))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(8 * scale)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((bx, by, bx + box_w, by + box_h), radius=int(18 * scale), fill=RED)
    d.text((bx + pad_x - tl, by + pad_y - tt), top, font=f_top, fill=WHITE)
    # big green CLIPS with heavy black outline
    cx = (W - bw) // 2 - bl
    cy = by + box_h + gap - bt + stroke
    d.text((cx + int(8 * scale), cy + int(10 * scale)), bot, font=f_bot, fill=(0, 0, 0, 230),
           stroke_width=stroke, stroke_fill=(0, 0, 0, 230))
    d.text((cx, cy), bot, font=f_bot, fill=GREEN, stroke_width=stroke, stroke_fill=(0, 0, 0))
    return img.rotate(6, resample=Image.BICUBIC, expand=True)


def play_badge(size):
    """Green circle with a black play triangle."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=GREEN, outline=(0, 0, 0), width=max(4, size // 14))
    s = size * 0.3
    c = size / 2
    d.polygon([(c - s * 0.7, c - s), (c - s * 0.7, c + s), (c + s * 1.0, c)], fill=(0, 0, 0))
    return img


def paste_center(base, img, cx, cy):
    base.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def make_logo(path):
    S = 800
    bg = glow_bg(S, S, [(S * 0.5, S * 0.45, S * 0.42, (120, 18, 18), 255),
                        (S * 0.55, S * 0.75, S * 0.30, (12, 90, 30), 200)]).convert('RGBA')
    lk = lockup(1.0)
    k = min(640 / lk.width, 560 / lk.height)  # keep inside the circle crop YouTube applies
    lk = lk.resize((int(lk.width * k), int(lk.height * k)), Image.LANCZOS)
    paste_center(bg, lk, S / 2, S / 2 + 6)
    bg.convert('RGB').save(path, quality=95)

    # preview of how it looks as a round avatar
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S, S), fill=255)
    prev = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    prev.paste(Image.open(path).convert('RGBA'), (0, 0), mask)
    return prev


def make_banner(path, logo_round):
    W, H = 2560, 1440
    bg = glow_bg(W, H, [(W * 0.32, H * 0.5, 520, (120, 18, 18), 255),
                        (W * 0.72, H * 0.52, 460, (12, 90, 30), 210)]).convert('RGBA')
    d = ImageDraw.Draw(bg)
    # safe area for all devices: 1546 x 423 centred
    sx0, sy0 = (W - 1546) // 2, (H - 423) // 2
    sx1, sy1 = sx0 + 1546, sy0 + 423
    # red accent bars above and below the safe area (visible on TV/desktop only)
    d.rectangle((0, sy0 - 60, W, sy0 - 48), fill=RED)
    d.rectangle((0, sy1 + 48, W, sy1 + 60), fill=GREEN)

    # left: round logo
    lg = logo_round.resize((360, 360), Image.LANCZOS)
    ring = Image.new('RGBA', (384, 384), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, 383, 383), fill=WHITE)
    paste_center(bg, ring, sx0 + 200, H / 2)
    paste_center(bg, lg, sx0 + 200, H / 2)

    # right: headline + tagline
    x = sx0 + 430
    f_h = font(BLACK_FONT, 118)
    f_t = font(BOLD_FONT, 40)
    f_s = font(BOLD_FONT, 30)
    line1, line2 = 'DAILY ', 'RASMR'
    w1 = text_size(f_h, line1)[0]
    y = sy0 + 34
    d.text((x, y), line1, font=f_h, fill=WHITE, stroke_width=8, stroke_fill=(0, 0, 0))
    d.text((x + w1 + 10, y), line2, font=f_h, fill=GREEN, stroke_width=8, stroke_fill=(0, 0, 0))
    hw, hh, hl, ht = text_size(f_h, line1 + line2)
    paste_center(bg, play_badge(118), x + hw + 10 + 95, y + ht + hh / 2)
    y += 150
    tag = 'CRYPTO  ·  TRENCHES  ·  MAIN CHARACTER'
    tw, th, tl, tt = text_size(f_t, tag)
    d.rounded_rectangle((x, y, x + tw + 56, y + th + 40), radius=12, fill=RED)
    d.text((x + 28 - tl, y + 20 - tt), tag, font=f_t, fill=WHITE)
    y += th + 40 + 34
    d.text((x, y), 'NEW SHORTS EVERY DAY  ·  UNOFFICIAL FAN CHANNEL', font=f_s, fill=(200, 200, 205))

    assert x + tw + 56 <= sx1, 'tagline leaves the safe area'
    bg.convert('RGB').save(path, quality=95)


if __name__ == '__main__':
    prev = make_logo(os.path.join(HERE, 'logo-800.png'))
    prev.save(os.path.join(HERE, 'logo-round-preview.png'))
    make_banner(os.path.join(HERE, 'banner-2560x1440.png'), prev)
    print('done')
