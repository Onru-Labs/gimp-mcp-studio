"""Native semantic text behavior without importing the GI plugin process."""
import ast
import math
import sys
import traceback
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Font:
    def __init__(self, name): self.name = name
    def get_name(self): return self.name


class Unit:
    def get_id(self): return 0


class Color:
    def __init__(self, value): self.value = value
    def get_rgba(self): return (1., 0., 0., 1.) if self.value == "red" else (0., 0., 0., 1.)


class Text:
    def __init__(self):
        self.text, self.font, self.size, self.unit = "old", Font("Sans-serif"), 24., Unit()
        self.color, self.offsets = Color("black"), [0, 0]
    def set_text(self, value): self.text = value; return True
    def get_text(self): return self.text
    def set_font(self, value):
        assert isinstance(value, Font)
        self.font = value
        return True
    def get_font(self): return self.font
    def set_font_size(self, value, unit):
        assert isinstance(unit, Unit)
        self.size, self.unit = value, unit
        return True
    def get_font_size(self): return self.size, self.unit
    def set_color(self, value): self.color = value; return True
    def get_color(self): return self.color
    def set_offsets(self, x, y): self.offsets = [x, y]; return True
    def get_offsets(self): return (True, *self.offsets)
    def get_name(self): return "headline"
    def get_id(self): return 17
    def get_width(self): return 120
    def get_height(self): return 40
    def get_visible(self): return True
    def get_opacity(self): return 100.
    def get_mode(self): return "NORMAL"
    def has_alpha(self): return True
    def get_mask(self): return None
    @classmethod
    def new(cls, image, text, font, size, unit):
        obj = cls()
        obj.text, obj.font, obj.size, obj.unit = text, font, size, unit
        return obj


def load_bridge():
    source = Path(__file__).resolve().parents[1] / "gimp-mcp-plugin.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_text_offsets", "_text_state", "_apply_native_text", "_create_text_layer_native",
             "_edit_text", "_add_text", "_layer_semantics", "_list_layers", "_resolve_font"}
    methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    cls = ast.ClassDef(name="Bridge", bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    gimp = types.SimpleNamespace(TextLayer=Text, Unit=types.SimpleNamespace(pixel=Unit),
        Font=types.SimpleNamespace(get_by_name=lambda name: Font(name) if name != "Missing" else None),
        displays_flush=Mock())
    scope = {"Gimp": gimp, "math": math, "traceback": traceback}
    exec(compile(module, str(source), "exec"), scope)
    bridge = scope["Bridge"]()
    image = Mock()
    bridge._get_image = Mock(return_value=image)
    layer = Text()
    bridge._resolve_layer = Mock(return_value=layer)
    image.get_layers.return_value = [layer]
    image.get_paths.return_value = []
    return bridge, image, layer, gimp


class NativeTextTests(unittest.TestCase):
    def setUp(self):
        self.gi = patch.dict(sys.modules, {"gi.repository": types.SimpleNamespace(
            Gegl=types.SimpleNamespace(Color=types.SimpleNamespace(new=Color)))})
        self.gi.start()
        self.addCleanup(self.gi.stop)
        self.bridge, self.image, self.layer, self.gimp = load_bridge()

    def test_edits_use_font_and_unit_objects_and_readback(self):
        result = self.bridge._edit_text({"text": "New headline", "font": "Inter Bold", "size": 38.5, "color": "red"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["results"]["actual"]["text"], "New headline")
        self.assertEqual(result["results"]["actual"]["size"], 38.5)
        self.assertFalse(result["results"]["font_resolution"]["fallback_used"])
        self.image.undo_group_end.assert_called_once()

    def test_rejects_named_raster_text_before_mutation(self):
        self.bridge._resolve_layer.return_value = Mock()
        result = self.bridge._edit_text({"text": "New"})
        self.assertEqual(result["status"], "error")
        self.assertIn("not a native", result["error"])
        self.image.undo_group_start.assert_not_called()

    def test_false_setter_is_error_and_closes_undo(self):
        self.layer.set_text = Mock(return_value=False)
        result = self.bridge._edit_text({"text": "New"})
        self.assertEqual(result["status"], "error")
        self.assertIn("setter failed", result["error"])
        self.assertTrue(result["partial_changes_possible"])
        self.image.undo_group_end.assert_called_once()

    def test_silent_noop_detected_by_readback(self):
        self.layer.set_text = Mock(return_value=True)
        result = self.bridge._edit_text({"text": "New"})
        self.assertEqual(result["status"], "error")
        self.assertIn("readback mismatch", result["error"])

    def test_fallback_reported_and_noop_request_rejected(self):
        result = self.bridge._edit_text({"font": "Missing"})
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["results"]["font_resolution"]["fallback_used"])
        self.assertEqual(result["results"]["font_resolution"]["requested"], "Missing")
        self.assertEqual(self.bridge._edit_text({})["status"], "error")

    def test_add_native_and_explicit_font_report(self):
        result = self.bridge._add_text({"text": "Buy online", "font": "Missing", "color": "red", "x": 12, "y": 30})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["results"]["actual"]["position"], [12, 30])
        self.assertTrue(result["results"]["font_resolution"]["fallback_used"])
        self.image.insert_layer.assert_called_once()

    def test_add_failure_removes_partial_layer_without_pdb_fallback(self):
        with patch.object(Text, "set_color", return_value=False):
            result = self.bridge._add_text({"text": "Buy"})
        self.assertEqual(result["status"], "error")
        self.image.remove_layer.assert_called_once()
        self.image.undo_group_end.assert_called_once()
        self.image.insert_layer.assert_called_once()

    def test_list_preserves_fields_and_reports_native_text_mask_paths(self):
        mask = Mock()
        mask.get_id.return_value = 22
        mask.get_name.return_value = "mask"
        self.layer.get_mask = lambda: mask
        result = self.bridge._list_layers({})
        info = result["results"]["layers"][0]
        self.assertEqual(info["index"], 0)
        self.assertEqual(info["name"], "headline")
        self.assertEqual(info["semantic_type"], "text")
        self.assertEqual(info["text"]["text"], "old")
        self.assertEqual(info["mask"]["id"], 22)
        self.assertEqual(result["results"]["paths"], [])

    def test_vector_and_raster_semantics_are_distinct(self):
        class Vector(Text):
            def get_path(self): return self
        self.gimp.VectorLayer = Vector
        vector = Vector()
        info = self.bridge._layer_semantics(vector)
        self.assertTrue(info["is_vector_layer"])
        self.assertEqual(info["vector_path"]["id"], 17)
        class Raster:
            def get_mask(self): return None
        self.assertEqual(self.bridge._layer_semantics(Raster())["semantic_type"], "raster")

    def test_offsets_normalize_gi_success_tuple_and_reject_failed_readback(self):
        self.assertEqual(self.bridge._text_state(self.layer)["position"], [0, 0])
        self.layer.get_offsets = lambda: (15, 19)
        self.assertEqual(self.bridge._text_state(self.layer)["position"], [15, 19])
        self.layer.get_offsets = lambda: (False, 0, 0)
        with self.assertRaisesRegex(RuntimeError, "offset readback failed"):
            self.bridge._text_state(self.layer)

    def test_creation_mismatch_records_expected_and_observed(self):
        with patch.object(Text, "set_offsets", return_value=True):
            result = self.bridge._add_text({"text": "Buy", "x": 72, "y": 600})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["readback_mismatch"]["expected"]["position"], [72, 600])
        self.assertEqual(result["readback_mismatch"]["observed"]["position"], [0, 0])
        self.image.remove_layer.assert_called_once()

    def test_invalid_size_no_success(self):
        for size in (0, -1, float("nan")):
            self.assertEqual(self.bridge._edit_text({"size": size})["status"], "error")


if __name__ == "__main__":
    unittest.main()
