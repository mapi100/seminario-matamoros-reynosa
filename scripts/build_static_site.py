#!/usr/bin/env python3
"""Prepara el sitio estático y regenera las portadas antes de publicar Pages."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil

from generate_course_images import ROOT, generate

PUBLIC_EXTENSIONS = {'.html', '.css', '.js', '.json', '.webmanifest', '.xml', '.txt',
                     '.ico', '.png', '.jpg', '.jpeg', '.webp', '.avif', '.gif', '.svg'}


def build(root: Path, output: Path) -> None:
    # Un directorio nuevo evita arrastrar imágenes eliminadas en otro despliegue.
    output.mkdir(parents=True, exist_ok=False)
    for path in root.iterdir():
        if path.is_file() and (path.suffix.lower() in PUBLIC_EXTENSIONS or path.name == 'CNAME'):
            shutil.copy2(path, output / path.name)
    for name in ('images', 'portal'):
        shutil.copytree(root / name, output / name,
                        ignore=lambda folder, names: [n for n in names if n.startswith('.') or n in ('__pycache__', 'README.md')])
    manifest = output / 'portal' / 'course-images.js'
    generate(root, manifest)
    version = hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]
    panel = output / 'portal' / 'panel.html'
    html, count = re.subn(r'src="course-images\.js(?:\?[^"\s]*)?"',
                         f'src="course-images.js?v={version}"', panel.read_text(encoding='utf-8'))
    if count != 1:
        raise ValueError('panel.html debe cargar una sola vez course-images.js.')
    panel.write_text(html, encoding='utf-8')
    (output / '.nojekyll').touch()
    print(f'Sitio listo: {output}; catálogo {version}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    build(ROOT, args.output)
