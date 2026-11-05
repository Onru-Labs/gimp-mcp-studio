"""Exercise plugin helpers without requiring the GIMP GI runtime."""
import ast
import math
import types
import unittest
from pathlib import Path
from unittest import mock


def helper(name):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'gimp-mcp-plugin.py').read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {'Gimp': mock.Mock(), 'math': math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'plugin-helper', 'exec'), scope)
    return scope[name], scope['Gimp']


class GeglHelpers(unittest.TestCase):
    def fixture(self):
        method, gimp = helper('_apply_gegl_filter')
        filtr = gimp.DrawableFilter.new.return_value
        config = filtr.get_config.return_value
        config.list_properties.return_value = [types.SimpleNamespace(name='scale', minimum=0, maximum=10)]
        config.get_property.return_value = .3
        return method, gimp, filtr, config, mock.Mock()

    def test_requested_scale_configured_and_updated_before_merge(self):
        fn, gimp, filtr, config, drawable = self.fixture()
        calls = mock.Mock()
        calls.attach_mock(config.set_property, 'set')
        calls.attach_mock(filtr.update, 'update')
        calls.attach_mock(drawable.merge_filter, 'merge')
        fn(None, None, drawable, 'gegl:unsharp-mask', {'scale': .3})
        gimp.DrawableFilter.new.assert_called_once_with(drawable, 'gegl:unsharp-mask', 'gegl:unsharp-mask')
        self.assertEqual(calls.mock_calls, [mock.call.set('scale', .3), mock.call.update(), mock.call.merge(filtr)])

    def test_unknown_and_out_of_range_properties_fail_without_merge(self):
        for props in ({'missing': .3}, {'scale': 30}, {'scale': math.nan}):
            fn, _, filtr, _, drawable = self.fixture()
            with self.subTest(props=props), self.assertRaises(ValueError):
                fn(None, None, drawable, 'gegl:unsharp-mask', props)
            drawable.merge_filter.assert_not_called()
            filtr.delete.assert_called_once()

    def test_clamped_property_and_merge_errors_propagate(self):
        fn, _, filtr, config, drawable = self.fixture()
        config.get_property.return_value = 4
        with self.assertRaisesRegex(RuntimeError, 'not applied'):
            fn(None, None, drawable, 'gegl:unsharp-mask', {'scale': .3})
        drawable.merge_filter.assert_not_called()
        config.get_property.return_value = .3
        drawable.merge_filter.side_effect = RuntimeError('merge failed')
        with self.assertRaisesRegex(RuntimeError, 'merge failed'):
            fn(None, None, drawable, 'gegl:unsharp-mask', {'scale': .3})


if __name__ == '__main__':
    unittest.main()
