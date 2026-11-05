"""Encoded sRGB contracts must not multiply linear GEGL channels by 255."""
import ast
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class PixelColor(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "gimp-mcp-plugin.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_get_pixel_color")
        scope = {"traceback": traceback}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "pixel-helper", "exec"), scope)
        self.run_pixel = scope["_get_pixel_color"]
        self.pixel = Mock()
        self.drawable = Mock()
        self.drawable.get_pixel.return_value = self.pixel
        self.bridge = SimpleNamespace(_get_image=Mock(return_value=object()),
                                      _resolve_layer=Mock(return_value=self.drawable))
        self.format = Mock(return_value=object())
        self.modules = patch.dict(sys.modules, {"gi.repository": SimpleNamespace(Babl=SimpleNamespace(format=self.format))})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def sample(self, channels):
        self.pixel.get_bytes.return_value.get_data.return_value = bytes(channels)
        return self.run_pixel(self.bridge, {"x": 2, "y": 3, "layer_name": "swatch"})

    def test_encoded_blue_not_linear_channels(self):
        self.pixel.get_rgba.return_value = (.003346535, .114435397, 1., 1.)
        result = self.sample([11, 95, 255, 255])
        self.assertEqual(result["results"]["color_rgb"], [11, 95, 255])
        self.assertEqual(result["results"]["color_hex"], "#0b5fff")
        self.format.assert_called_once_with("R'G'B'A u8")
        self.pixel.get_rgba.assert_not_called()
        self.assertEqual(result["results"]["color_space"], "sRGB")

    def test_midgray_encoded128_not_linear55(self):
        result = self.sample([128, 128, 128, 255])
        self.assertEqual(result["results"]["color_hex"], "#808080")

    def test_partial_alpha_does_not_premultiply_rgb(self):
        result = self.sample([11, 95, 255, 128])["results"]
        self.assertEqual(result["color_rgb"], [11, 95, 255])
        self.assertEqual(result["alpha"], 128)
        self.assertEqual(result["alpha_mode"], "straight")

    def test_transparent_rgb_not_destroyed(self):
        result = self.sample([200, 120, 40, 0])["results"]
        self.assertEqual(result["color_rgb"], [200, 120, 40])
        self.assertEqual(result["alpha"], 0)

    def test_conversion_failure_is_explicit(self):
        self.pixel.get_bytes.side_effect = RuntimeError("unsupported format")
        result = self.run_pixel(self.bridge, {})
        self.assertEqual(result["status"], "error")
        self.assertIn("unsupported format", result["error"])

    def test_invalid_byte_count_not_success(self):
        result = self.sample([11, 95, 255])
        self.assertEqual(result["status"], "error")


if __name__ == "__main__": unittest.main()
