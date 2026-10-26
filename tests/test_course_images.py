"""Catálogo/publicación automática: archivos temporales, sin GitHub ni Supabase."""
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generate_course_images import catalogue, generate
from build_static_site import build


def picture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new('RGB', (240, 160), '#173456')
    ImageDraw.Draw(im).rectangle((60, 10, 190, 145), fill='#e9b553')
    im.save(path)


class CourseImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        (self.root / 'images').mkdir(parents=True)
        (self.root / 'portal').mkdir()

    def test_new_photo_is_included_without_editing_code(self):
        picture(self.root / 'images' / 'primera.jpg')
        self.assertEqual(len(catalogue(self.root)[0]), 1)
        picture(self.root / 'images' / 'otra-foto-nueva.png')
        self.assertEqual({p['src'] for p in catalogue(self.root)[0]},
                         {'images/primera.jpg', 'images/otra-foto-nueva.png'})

    def test_deleted_photo_disappears_and_order_is_stable(self):
        for name in ['c.jpg', 'a.jpg', 'b.jpg']:
            picture(self.root / 'images' / name)
        first = catalogue(self.root)[0]
        self.assertEqual(first, catalogue(self.root)[0])
        (self.root / 'images' / 'b.jpg').unlink()
        self.assertEqual([p['src'] for p in catalogue(self.root)[0]], ['images/a.jpg', 'images/c.jpg'])

    def test_recursive_paths_and_special_characters_are_valid_urls(self):
        picture(self.root / 'images' / 'nuevas' / 'José #1 %.PNG')
        self.assertEqual(catalogue(self.root)[0][0]['src'], 'images/nuevas/Jos%C3%A9%20%231%20%25.PNG')

    def test_shields_logos_and_hidden_images_are_not_covers(self):
        for name in ['escudo-nuevo.png', 'Logo_Diocesis.JPG', 'favicon.png', '.oculta.jpg',
                     'logos/diocesis.jpg', 'iconos/ayuda.png', 'valida.jpg']:
            picture(self.root / 'images' / name)
        self.assertEqual([p['src'] for p in catalogue(self.root)[0]], ['images/valida.jpg'])

    def test_transparent_solid_tiny_and_invalid_images_are_skipped(self):
        Image.new('RGBA', (300, 150), (0, 0, 0, 0)).save(self.root / 'images' / 'vacia.png')
        Image.new('RGB', (300, 150), 'black').save(self.root / 'images' / 'negra.png')
        Image.new('RGB', (20, 20), 'red').save(self.root / 'images' / 'mini.png')
        (self.root / 'images' / 'rota.jpg').write_text('not an image')
        picture(self.root / 'images' / 'bien.webp')
        entries, skipped = catalogue(self.root)
        self.assertEqual([p['src'] for p in entries], ['images/bien.webp'])
        self.assertEqual(len(skipped), 4)

    def test_original_photo_bytes_remain_unchanged(self):
        path = self.root / 'images' / 'original.jpg'
        picture(path)
        data = path.read_bytes()
        catalogue(self.root)
        self.assertEqual(data, path.read_bytes())

    def test_source_manifest_is_valid_deterministic_javascript_data(self):
        picture(self.root / 'images' / 'nueva.jpg')
        with contextlib.redirect_stdout(io.StringIO()):
            generate(self.root)
        result = (self.root / 'portal' / 'course-images.js').read_text()
        payload = re.search(r'Object\.freeze\((.*)\);', result, re.S).group(1)
        self.assertEqual(json.loads(payload), catalogue(self.root)[0])
        with contextlib.redirect_stdout(io.StringIO()):
            generate(self.root)
        self.assertEqual(result, (self.root / 'portal' / 'course-images.js').read_text())

    def prepare_site(self):
        (self.root / 'index.html').write_text('<h1>Seminario</h1>')
        (self.root / 'CNAME').write_text('seminariomr.org\n')
        (self.root / 'robots.txt').write_text('User-agent: *\nAllow: /\n')
        (self.root / 'favicon.ico').write_bytes(b'icon fixture')
        (self.root / 'portal' / 'panel.html').write_text('<script src="course-images.js?v=old" defer></script>')
        (self.root / 'portal' / 'supabase-config.js').write_text('/* public config fixture */')
        (self.root / 'portal' / 'course-images.js').write_text('old source catalogue')
        for name in ['supabase', 'tests', 'docs', 'scripts', '.git']:
            (self.root / name).mkdir(exist_ok=True)
            (self.root / name / 'fixture.txt').write_text('development fixture')
        picture(self.root / 'images' / 'primera.jpg')

    def test_build_preserves_site_and_regenerates_stale_catalogue(self):
        self.prepare_site()
        picture(self.root / 'images' / 'recien-agregada.jpg')
        output = Path(self.temp.name) / 'site'
        with contextlib.redirect_stdout(io.StringIO()):
            build(self.root, output)
        self.assertTrue((output / 'index.html').is_file())
        self.assertEqual((output / 'CNAME').read_bytes(), (self.root / 'CNAME').read_bytes())
        self.assertTrue((output / 'favicon.ico').is_file())
        self.assertTrue((output / 'portal' / 'supabase-config.js').is_file())
        self.assertTrue((output / '.nojekyll').is_file())
        self.assertIn('recien-agregada.jpg', (output / 'portal' / 'course-images.js').read_text())
        self.assertRegex((output / 'portal' / 'panel.html').read_text(), r'course-images\.js\?v=[a-f0-9]{16}')
        self.assertEqual((self.root / 'portal' / 'course-images.js').read_text(), 'old source catalogue')
        for name in ['supabase', 'tests', 'docs', 'scripts', '.git']:
            self.assertFalse((output / name).exists())

    def test_new_photo_changes_catalogue_cache_version(self):
        self.prepare_site()
        with contextlib.redirect_stdout(io.StringIO()):
            build(self.root, Path(self.temp.name) / 'before')
            picture(self.root / 'images' / 'otra.png')
            build(self.root, Path(self.temp.name) / 'after')
        self.assertNotEqual((Path(self.temp.name) / 'before/portal/panel.html').read_text(),
                            (Path(self.temp.name) / 'after/portal/panel.html').read_text())

    def test_build_does_not_overwrite_a_source_directory(self):
        self.prepare_site()
        with self.assertRaises(FileExistsError):
            build(self.root, self.root)
        self.assertTrue((self.root / 'index.html').is_file())


if __name__ == '__main__':
    unittest.main()
