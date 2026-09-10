"""Draw the site mark and write every icon size the browsers ask for.

Re-run after changing the design:

    python tools/make_icons.py

The mark is a coffee cup on the brand blue. It is drawn with plain shapes
rather than traced from a font so it stays crisp at 16px, where a detailed
glyph turns to mush - the cup body is a wide trapezoid and the handle a thick
ring, both of which survive the downscale.
"""

import os

from PIL import Image, ImageDraw, ImageFont

BRAND = (47, 155, 255)        # --accent-color
BRAND_DARK = (28, 126, 214)   # --accent-hover
WHITE = (255, 255, 255)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'static', 'icons')
SUPERSAMPLE = 8               # draw big, shrink down: cheap anti-aliasing


def rounded_square(draw, size, radius_ratio=0.22, fill=BRAND):
    r = int(size * radius_ratio)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=fill)


def draw_cup(draw, size, colour=WHITE, simple=False):
    """A mug seen from the side, with a handle and a saucer.

    `simple` drops the steam and fattens everything. At 16px - the size that
    actually shows in a browser tab - the steam strokes and the handle blur
    into the cup and the whole thing reads as a smudge, so the small icons
    use a bolder, plainer silhouette instead.
    """
    u = size / 100.0                      # work in percentages of the canvas

    if simple:
        # one chunky cup, nothing else competing for the few pixels available
        draw.polygon([(20 * u, 30 * u), (72 * u, 30 * u),
                      (64 * u, 72 * u), (28 * u, 72 * u)], fill=colour)
        draw.ellipse([66 * u, 36 * u, 92 * u, 62 * u], outline=colour,
                     width=max(2, int(8 * u)))
        draw.rectangle([14 * u, 78 * u, 78 * u, 88 * u], fill=colour)
        return

    # steam: three short strokes leaning the same way
    w = max(1, int(3.2 * u))
    draw.line([(38 * u, 22 * u), (34 * u, 33 * u)], fill=colour, width=w)
    draw.line([(52 * u, 20 * u), (48 * u, 31 * u)], fill=colour, width=w)
    draw.line([(66 * u, 22 * u), (62 * u, 33 * u)], fill=colour, width=w)

    # body: a trapezoid so it reads as a cup, not a box
    body = [(26 * u, 42 * u), (70 * u, 42 * u), (63 * u, 74 * u), (33 * u, 74 * u)]
    draw.polygon(body, fill=colour)

    # handle: a thick ring
    draw.ellipse([64 * u, 46 * u, 86 * u, 68 * u], outline=colour,
                 width=max(1, int(5.5 * u)))

    # saucer
    draw.rounded_rectangle([20 * u, 78 * u, 76 * u, 85 * u],
                           radius=int(3.5 * u), fill=colour)


def render(size, padding_ratio=0.0, bg=BRAND, transparent_bg=False,
           simple=None):
    """One square icon at `size` px."""
    if simple is None:
        simple = size <= 48
    big = size * SUPERSAMPLE
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if not transparent_bg:
        rounded_square(d, big, fill=bg)

    pad = int(big * padding_ratio)
    inner = big - pad * 2
    cup = Image.new('RGBA', (inner, inner), (0, 0, 0, 0))
    draw_cup(ImageDraw.Draw(cup), inner, simple=simple)
    img.alpha_composite(cup, (pad, pad))

    return img.resize((size, size), Image.LANCZOS)


# Fonts to try for the share card, in preference order. This only has to
# resolve on the machine that generates the PNG - the result is committed as
# an image, so the server never needs the font.
FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/System/Library/Fonts/Supplemental/Verdana Bold.ttf',
    '/Library/Fonts/Arial Unicode.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]


def load_font(size):
    """A bold face that can render Vietnamese diacritics."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def render_og(width=1200, height=630):
    """The card image Facebook/Zalo show when the link is shared."""
    img = Image.new('RGB', (width, height), BRAND_DARK)
    d = ImageDraw.Draw(img)

    # a soft diagonal band so it is not a flat rectangle
    d.polygon([(0, height), (width, 0), (width, height)], fill=BRAND)

    mark_size = 260
    img.paste(render(mark_size, transparent_bg=True),
              (96, 120), render(mark_size, transparent_bg=True))

    title_font = load_font(76)
    sub_font = load_font(34)
    if title_font is None:
        # No usable font: the mark alone still makes a valid card, and the
        # og:title the page supplies carries the name in the preview.
        return img

    d.text((96, 410), 'Cô Bông Cát Lái', font=title_font, fill=WHITE)
    d.text((100, 505), 'Cà phê · Đồ ăn · Căn hộ dịch vụ',
           font=sub_font, fill=(226, 240, 255))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    written = []

    # PNG favicons and app icons
    for size, name in [(16, 'favicon-16.png'), (32, 'favicon-32.png'),
                       (180, 'apple-touch-icon.png'),
                       (192, 'android-chrome-192.png'),
                       (512, 'android-chrome-512.png')]:
        p = os.path.join(OUT, name)
        render(size).save(p)
        written.append(name)

    # multi-resolution .ico for older browsers and the address bar
    ico = os.path.join(OUT, 'favicon.ico')
    render(64, simple=True).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    written.append('favicon.ico')

    # transparent mark for use on light surfaces
    p = os.path.join(OUT, 'logo-mark.png')
    render(512, transparent_bg=True, simple=False).save(p)
    written.append('logo-mark.png')

    # social card
    p = os.path.join(OUT, 'og-image.png')
    render_og().save(p, quality=90)
    written.append('og-image.png')

    for n in written:
        f = os.path.join(OUT, n)
        print(f'  {n:<26} {os.path.getsize(f):>7,} bytes')


if __name__ == '__main__':
    main()
