"""Snapshot must show the owned full composite without clipboard/source mutation."""
import ast
import base64
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import traceback
import unittest

from PIL import Image


class Scratch:
    def __init__(self, image):
        self.image = image.copy()
        self.deleted = False

    def crop(self, width, height, x, y):
        self.image = self.image.crop((x, y, x + width, y + height))

    def scale(self, width, height):
        self.image = self.image.resize((width, height))

    def delete(self):
        self.deleted = True


class SnapshotComposite(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'gimp-mcp-plugin.py'
        module = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for node in ast.walk(module)
                      if isinstance(node, ast.FunctionDef) and node.name == '_get_current_image_bitmap')
        namespace = {'base64': base64, 'tempfile': tempfile, 'os': os, 'traceback': traceback}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        self.snapshot = namespace['_get_current_image_bitmap']
        composite = Image.new('RGBA', (100, 80), '#224466')
        composite.paste('#33CC66', (20, 30, 50, 60))  # visible lower-layer content, top layer empty here
        self.scratch = []
        self.selected_indices = []

        def duplicate():
            image = Scratch(composite)
            self.scratch.append(image)
            return image

        original = SimpleNamespace(get_width=lambda: 100, get_height=lambda: 80,
                                   get_id=lambda: 17, duplicate=duplicate)

        def target(index):
            self.selected_indices.append(index)
            return original

        self.exported = []

        def export(image, path, *args):
            self.exported.append(path)
            image.image.save(path)

        self.owner = SimpleNamespace(_get_image=target, _export_to_path=export)

    def test_detail_shows_lower_layer_composite_and_honors_image_index(self):
        result = self.snapshot(self.owner, {'image_index': 1,
            'region': {'origin_x': 20, 'origin_y': 30, 'width': 30, 'height': 30},
            'max_width': 1536, 'max_height': 1536})
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.selected_indices, [1])
        with Image.open(io.BytesIO(base64.b64decode(result['results']['image_data']))) as detail:
            self.assertEqual(detail.size, (30, 30))
            self.assertEqual(detail.getpixel((0, 0))[:3], (51, 204, 102))
        self.assertTrue(self.scratch[0].deleted)
        self.assertFalse(Path(self.exported[0]).exists())

    def test_full_snapshot_is_not_upscaled_and_keeps_all_composited_pixels(self):
        result = self.snapshot(self.owner, {'image_index': 0, 'max_width': 1536, 'max_height': 1536})
        self.assertEqual(result['status'], 'success')
        self.assertEqual([result['results']['width'], result['results']['height']], [100, 80])
        self.assertTrue(self.scratch[0].deleted)

    def test_export_error_cleans_scratch_and_temporary_file(self):
        def fail(image, path, *args):
            self.exported.append(path)
            raise RuntimeError('native PNG export failed')

        self.owner._export_to_path = fail
        result = self.snapshot(self.owner, {'image_index': 0})
        self.assertEqual(result['status'], 'error')
        self.assertIn('native PNG export failed', result['error'])
        self.assertTrue(self.scratch[0].deleted)
        self.assertFalse(Path(self.exported[0]).exists())

    def test_bad_region_is_rejected_before_creating_any_scratch(self):
        result = self.snapshot(self.owner, {'region': {'origin_x': 95, 'origin_y': 0, 'width': 30, 'height': 20}})
        self.assertEqual(result['status'], 'error')
        self.assertFalse(self.scratch)


if __name__ == '__main__':
    unittest.main()
