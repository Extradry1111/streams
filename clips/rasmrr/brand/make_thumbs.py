"""Thumbnails for the rasmrr clips: 1280x720 (wide / YouTube) and 1080x1920 (Shorts / TikTok cover).

Usage: python3 make_thumbs.py HD_DIR OUT_DIR   (HD_DIR holds the 1080p cuts NN-slug.mp4; needs ffmpeg + Pillow)
"""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from make_brand import BLACK_FONT, GREEN, RED, WHITE, font, text_size

# slug, frame second inside the HD cut, white line, green line
CLIPS = [
    ('01-main-character', 41.0, "I'M THE", 'MAIN CHARACTER'),
    ('02-fake-soft-launch', 12.6, 'THE $50', 'SOFT LAUNCH'),
    ('03-is-it-worth-it', 24.0, 'IS BEING RICH', 'WORTH IT?'),
    ('04-captivating-character', 30.0, "I'M THE", 'GOAT'),
    ('05-didnt-want-her', 9.0, "I DIDN'T", 'WANT HER'),
]
FACE_X = 0.47  # streamer's horizontal centre in the webcam frame (share of width)


def grab(video, t, out):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(t), '-i', video,
                    '-frames:v', '1', out], check=True)
    img = Image.open(out).convert('RGB')
    W, H = img.size
    box = (int(W * 0.60), 0, W, int(H * 0.30))  # stream chat overlay: blur it out
    img.paste(img.crop(box).filter(ImageFilter.GaussianBlur(28)), box[:2])
    img = ImageEnhance.Contrast(img).enhance(1.12)
    return ImageEnhance.Color(img).enhance(1.15)


def crop_to(img, w, h, cx, zoom=1.0):
    """Crop img to aspect w:h around horizontal centre cx (0-1), with optional zoom, then resize."""
    W, H = img.size
    ch = H / zoom
    cw = ch * w / h
    if cw > W:
        cw, ch = W, W * h / w
    x0 = min(max(0, cx * W - cw / 2), W - cw)
    y0 = (H - ch) * 0.35
    return img.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((w, h), Image.LANCZOS)


def shade(size, side):
    """Black gradient for text legibility: side = 'left' or 'top'."""
    w, h = size
    g = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(g)
    n = w if side == 'left' else h
    for i in range(n):
        a = int(235 * max(0.0, 1 - i / (n * 0.62)) ** 1.3)
        if side == 'left':
            d.line((i, 0, i, h), fill=a)
        else:
            d.line((0, i, w, i), fill=a)
    return Image.composite(Image.new('RGBA', size, (0, 0, 0, 255)), Image.new('RGBA', size, (0, 0, 0, 0)), g)


def fit_font(text, max_w, start):
    size = start
    while size > 30 and text_size(font(BLACK_FONT, size), text)[0] > max_w:
        size -= 4
    return font(BLACK_FONT, size)


def outlined(d, xy, text, f, fill, stroke):
    x, y = xy
    d.text((x + stroke * 0.6, y + stroke * 0.8), text, font=f, fill=(0, 0, 0), stroke_width=stroke, stroke_fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))


def text_block(w_line, g_line, max_w, base):
    """Tilted beast text: small red RASMR tag, white line, big green line. Returns RGBA image."""
    f_tag = font(BLACK_FONT, int(base * 0.42))
    f_w = fit_font(w_line, max_w, int(base * 0.9))
    f_g = fit_font(g_line, max_w, int(base * 1.25))
    st = max(6, base // 11)
    tw, th, tl, tt = text_size(f_tag, 'RASMR')
    ww, wh, wl, wt = text_size(f_w, w_line)
    gw, gh, gl, gt = text_size(f_g, g_line)
    pad = base // 6
    W = max(tw + 2 * pad, ww, gw) + 4 * st
    H = th + 2 * pad + wh + gh + 6 * st + base // 3
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = st
    d.rounded_rectangle((st, y, st + tw + 2 * pad, y + th + 2 * pad), radius=pad // 2, fill=RED)
    d.text((st + pad - tl, y + pad - tt), 'RASMR', font=f_tag, fill=WHITE)
    y += th + 2 * pad + base // 8
    outlined(d, (2 * st - wl, y - wt), w_line, f_w, WHITE, st)
    y += wh + base // 8
    outlined(d, (2 * st - gl, y - gt), g_line, f_g, GREEN, st)
    return img.rotate(4, resample=Image.BICUBIC, expand=True)


def border(img, color, width):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, img.width - 1, img.height - 1), outline=color, width=width)


def wide_thumb(frame, w_line, g_line, out):
    W, H = 1280, 720
    bg = crop_to(frame, W, H, FACE_X - 0.20, zoom=1.35).convert('RGBA')  # him on the right, chat overlay cropped out
    bg.alpha_composite(shade((W, H), 'left'))
    tb = text_block(w_line, g_line, 600, 120)
    bg.alpha_composite(tb, (28, (H - tb.height) // 2))
    border(bg, GREEN, 10)
    bg.convert('RGB').save(out, quality=92)


def short_cover(frame, w_line, g_line, out):
    W, H = 1080, 1920
    top = 520  # text area above the streamer
    bg = crop_to(frame, W, H, FACE_X).filter(ImageFilter.GaussianBlur(30)).convert('RGBA')
    bg = Image.blend(bg, Image.new('RGBA', (W, H), (0, 0, 0, 255)), 0.45)
    person = crop_to(frame, W, H - top, FACE_X).filter(ImageFilter.UnsharpMask(radius=2, percent=60)).convert('RGBA')
    fade = Image.new('L', person.size, 255)
    fd = ImageDraw.Draw(fade)
    for i in range(160):
        fd.line((0, i, W, i), fill=int(255 * i / 160))
    bg.paste(person, (0, top), fade)
    tb = text_block(w_line, g_line, 900, 150)
    bg.alpha_composite(tb, ((W - tb.width) // 2, max(60, (top + 40 - tb.height) // 2)))
    bg.convert('RGB').save(out, quality=92)


if __name__ == '__main__':
    hd, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for slug, t, w_line, g_line in CLIPS:
        frame = grab(os.path.join(hd, slug + '.mp4'), t, os.path.join(out, f'.{slug}.png'))
        wide_thumb(frame, w_line, g_line, os.path.join(out, f'{slug}-thumb-wide.jpg'))
        short_cover(frame, w_line, g_line, os.path.join(out, f'{slug}-cover-short.jpg'))
        os.remove(os.path.join(out, f'.{slug}.png'))
        print(slug)
