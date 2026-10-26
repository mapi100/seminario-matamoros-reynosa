#!/usr/bin/env python3
"""Genera el catálogo público desde los archivos de images/, sin modificar fotos."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif'}
RESERVED_PREFIXES = ('escudo', 'logo', 'favicon', 'apple-touch-icon')
RESERVED_FOLDERS = {'logos', 'escudos', 'icons', 'iconos', 'favicons'}
# Estos encuadres son opcionales: cualquier fotografía nueva entra al catálogo
# aunque su nombre no aparezca aquí.
FOCAL_POINTS = {
    'blessed_sacrament.jpg': '50% 36%',
    'blessed_sacrament_angels.jpg': '50% 15%',
    'espiritu_santo_oleo.jpg': '50% 22%',
    'jesus_cordero_2_icon.jpg': '50% 24%',
    'jesus_cordero_icon.jpg': '50% 35%',
    'jesus_misericordia_oleo.jpg': '50% 9%',
    'jesus_orthodox.jpg': '50% 41%',
    'jesus_y_maria.jpg': '50% 40%',
    'maria_oleo.jpg': '50% 15%',
    'sagrado_corazon_1.jpg': '50% 50%',
    'st_augustine.jpg': '50% 18%',
    'st_rita.jpg': '50% 20%',
}


def catalogue(root: Path) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    images = root / 'images'
    found: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(images.rglob('*'), key=lambda p: p.as_posix()):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
            continue
        parts = path.relative_to(images).parts
        if any(part.startswith('.') for part in parts):
            continue
        if path.stem.casefold().startswith(RESERVED_PREFIXES) or any(p.casefold() in RESERVED_FOLDERS for p in parts[:-1]):
            skipped.append((relative, 'escudo, logotipo o icono'))
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    preview = ImageOps.exif_transpose(im)
                    width, height = preview.size
                    if min(width, height) < 64:
                        skipped.append((relative, 'imagen demasiado pequeña'))
                        continue
                    preview.thumbnail((160, 160))
                    rgba = preview.convert('RGBA')
                    if rgba.getchannel('A').getbbox() is None:
                        skipped.append((relative, 'imagen completamente transparente'))
                        continue
                    opaque = Image.new('RGBA', rgba.size, 'white')
                    opaque.alpha_composite(rgba)
                    if all(low == high for low, high in opaque.convert('RGB').getextrema()):
                        skipped.append((relative, 'imagen de un solo color'))
                        continue
            position = FOCAL_POINTS.get(path.name.casefold(), '50% 30%' if height > width else '50% 50%')
            found.append({'src': quote(relative, safe='/'), 'position': position})
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            skipped.append((relative, f'archivo de imagen no utilizable ({type(error).__name__})'))
    return found, skipped


def generate(root: Path = ROOT, output: Path | None = None) -> list[dict[str, str]]:
    output = output or root / 'portal' / 'course-images.js'
    entries, skipped = catalogue(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(entries, ensure_ascii=True, indent=2)
    output.write_text('// Generado desde images/. No editar a mano.\n"use strict";\n'
                      'window.PortalCourseImages = Object.freeze(' + data + ');\n', encoding='utf-8')
    print(f'Catálogo: {len(entries)} portadas disponibles.')
    for name, reason in skipped:
        print(f'Omitida: {name}: {reason}')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    generate(output=args.output)
