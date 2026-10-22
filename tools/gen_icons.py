"""Spike: genera iconos 32x32 RGBA para la GUI con Pillow (sin librerias nativas).

Cada icono se dibuja a 8x y se reduce con LANCZOS para tener bordes suaves.
Uso: python tools/gen_icons.py <carpeta_salida>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

SIZE = 32
K = 8  # factor de supersampling
C = SIZE * K
BLUE = "#2563eb"
GREEN = "#15803d"
AMBER = "#d97706"
BLACK = "#000000"
SLATE = "#1f2937"


def u(v: float) -> float:
    """Unidades de 32px -> pixeles del lienzo grande."""
    return v * K


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def finish(img: Image.Image) -> Image.Image:
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def rrect(d, box, r, outline=None, fill=None, w=2.5):
    x0, y0, x1, y1 = (u(v) for v in box)
    d.rounded_rectangle((x0, y0, x1, y1), radius=u(r), outline=outline, fill=fill, width=int(u(w)))


def copy_icon(color: str) -> Image.Image:
    """Dos hojas superpuestas, solo contorno (distinto del 'pegar' relleno)."""
    img, d = canvas()
    # hoja de atras
    rrect(d, (4, 4, 20, 22), 3, outline=color, w=2.6)
    # hoja de delante: primero se borra su zona (transparente) para tapar a la de atras
    mask = Image.new("L", (C, C), 255)
    ImageDraw.Draw(mask).rounded_rectangle((u(11), u(10), u(27), u(28)), radius=u(3), fill=0)
    img = Image.composite(img, Image.new("RGBA", (C, C), (0, 0, 0, 0)), mask)
    d = ImageDraw.Draw(img)
    rrect(d, (11, 10, 27, 28), 3, outline=color, w=2.6)
    for y in (16, 20.5):
        d.rounded_rectangle((u(15), u(y), u(23), u(y + 1.8)), radius=u(0.9), fill=color)
    return finish(img)


def play_icon() -> Image.Image:
    img, d = canvas()
    d.polygon([(u(9), u(5)), (u(26), u(16)), (u(9), u(27))], fill=GREEN)
    # esquinas suavizadas: contorno del mismo color
    d.line([(u(9), u(5)), (u(26), u(16)), (u(9), u(27)), (u(9), u(5))], fill=GREEN, width=int(u(2.2)), joint="curve")
    return finish(img)


def pause_icon(color: str = AMBER) -> Image.Image:
    img, d = canvas()
    for x0 in (8, 18.5):
        d.rounded_rectangle((u(x0), u(6), u(x0 + 5.5), u(26)), radius=u(1.6), fill=color)
    return finish(img)


def play_pause_icon() -> Image.Image:
    """Alternativa B: un solo icono con ambos simbolos (triangulo + barras)."""
    img, d = canvas()
    d.polygon([(u(3), u(6)), (u(15), u(16)), (u(3), u(26))], fill=GREEN)
    d.line([(u(3), u(6)), (u(15), u(16)), (u(3), u(26)), (u(3), u(6))], fill=GREEN, width=int(u(2)), joint="curve")
    for x0 in (19, 25):
        d.rounded_rectangle((u(x0), u(6), u(x0 + 3.6), u(26)), radius=u(1.2), fill=AMBER)
    return finish(img)


def rename_icon() -> Image.Image:
    """Campo de texto con cursor (I-beam): 'cambiar el nombre'."""
    img, d = canvas()
    rrect(d, (2.5, 8, 29.5, 24), 3.5, outline=BLUE, w=2.4)
    # texto previo (barritas)
    d.rounded_rectangle((u(7), u(14.8), u(14), u(17.2)), radius=u(1.2), fill=BLUE)
    # cursor I-beam
    d.rounded_rectangle((u(19.4), u(11), u(21.6), u(21)), radius=u(1), fill=BLUE)
    d.rounded_rectangle((u(17), u(11), u(24), u(12.8)), radius=u(0.9), fill=BLUE)
    d.rounded_rectangle((u(17), u(19.2), u(24), u(21)), radius=u(0.9), fill=BLUE)
    return finish(img)


def _lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def stories_icon() -> Image.Image:
    """Anillo degradado estilo 'story' con silueta de persona."""
    stops = [(245, 158, 11), (219, 39, 119), (124, 58, 237)]  # ambar -> magenta -> violeta
    ring = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    px = ring.load()
    for y in range(C):
        for x in range(C):
            t = (x + y) / (2 * C)
            seg = t * 2
            i = min(int(seg), 1)
            px[x, y] = (*_lerp(stops[i], stops[i + 1], seg - i), 255)
    mask = Image.new("L", (C, C), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((u(2), u(2), u(30), u(30)), fill=255)
    md.ellipse((u(5.6), u(5.6), u(26.4), u(26.4)), fill=0)
    # silueta (cabeza + hombros) con el mismo degradado, dentro del anillo
    md.ellipse((u(12.2), u(9.6), u(19.8), u(17.2)), fill=255)
    shoulders = Image.new("L", (C, C), 0)
    sd = ImageDraw.Draw(shoulders)
    sd.ellipse((u(8.6), u(18.4), u(23.4), u(34)), fill=255)
    clip = Image.new("L", (C, C), 0)
    ImageDraw.Draw(clip).ellipse((u(5.6), u(5.6), u(26.4), u(26.4)), fill=255)
    mask = ImageChops.lighter(mask, ImageChops.multiply(shoulders, clip))
    ring.putalpha(mask)
    return finish(ring)


def pull_icon() -> Image.Image:
    """Flecha hacia abajo sobre una bandeja: traer (descargar) carpetas de otra instancia."""
    img, d = canvas()
    # flecha
    d.rounded_rectangle((u(13.6), u(3.5), u(18.4), u(15)), radius=u(1.2), fill=BLUE)
    d.polygon([(u(7.5), u(13)), (u(24.5), u(13)), (u(16), u(22))], fill=BLUE)
    d.line([(u(7.5), u(13)), (u(24.5), u(13)), (u(16), u(22)), (u(7.5), u(13))], fill=BLUE, width=int(u(1.6)), joint="curve")
    # bandeja
    d.line([(u(4.5), u(21)), (u(4.5), u(27.5)), (u(27.5), u(27.5)), (u(27.5), u(21))], fill=BLUE, width=int(u(2.6)), joint="curve")
    d.ellipse((u(3.2), u(26.2), u(5.8), u(28.8)), fill=BLUE)
    d.ellipse((u(26.2), u(26.2), u(28.8), u(28.8)), fill=BLUE)
    return finish(img)


ICONS = {
    "copy.png": lambda: copy_icon(BLUE),
    "copy_black.png": lambda: copy_icon(BLACK),
    "play.png": play_icon,
    "pause.png": pause_icon,
    "play_pause.png": play_pause_icon,
    "rename.png": rename_icon,
    "stories.png": stories_icon,
    "pull.png": pull_icon,
}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, build in ICONS.items():
        build().save(out / name)
        print("ok", out / name)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
