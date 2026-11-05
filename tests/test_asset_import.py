"""Native asset import and typed references, without a live GIMP instance."""
import ast
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import traceback
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def methods(names, namespace):
    module = ast.parse((ROOT / 'gimp-mcp-plugin.py').read_text(encoding='utf-8'))
    nodes = [node for node in ast.walk(module) if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<plugin methods>', 'exec'), namespace)
    return namespace


class AssetImport(unittest.TestCase):
    def setUp(self):
        self.layer = mock.Mock()
        self.layer.get_offsets.return_value = (True, 12, -4)
        self.layer.get_width.return_value = 400
        self.layer.get_height.return_value = 300
        self.layer.get_id.return_value = 52
        self.layer.get_name.return_value = 'Accepted texture'
        self.image = mock.Mock()
        self.image.get_layers.return_value = [mock.Mock()]
        self.image.get_id.return_value = 9
        self.image.get_item_position.return_value = 1
        self.gimp = SimpleNamespace(file_load_layer=mock.Mock(return_value=self.layer),
                                    RunMode=SimpleNamespace(NONINTERACTIVE=0), displays_flush=mock.Mock())
        self.gio = SimpleNamespace(File=SimpleNamespace(new_for_path=mock.Mock(side_effect=lambda p: ('GFile', p))))
        self.namespace = methods({'_import_layer', '_pdb_reference', '_pdb_input_value'},
                                 {'Gimp': self.gimp, 'os': os, 'traceback': traceback})
        self.owner = SimpleNamespace(_get_image=mock.Mock(return_value=self.image),
                                    _pdb_value_type_name=lambda spec: spec.type_name)
        self.repository = mock.patch.dict(sys.modules, {'gi.repository': SimpleNamespace(Gio=self.gio)})
        self.repository.start()
        self.addCleanup(self.repository.stop)

    def test_import_uses_existing_target_and_reports_actual_bounds(self):
        with tempfile.NamedTemporaryFile(suffix='.png') as source:
            result = self.namespace['_import_layer'](self.owner, {
                'file_path': source.name, 'image_index': 2, 'position': 1,
                'name': 'Accepted texture', 'x': 12, 'y': -4})
        self.assertEqual(result['status'], 'success')
        self.owner._get_image.assert_called_once_with(2)
        self.gimp.file_load_layer.assert_called_once_with(0, self.image, ('GFile', os.path.abspath(source.name)))
        self.image.insert_layer.assert_called_once_with(self.layer, None, 1)
        self.assertEqual(result['results']['bounds'], {'x': 12, 'y': -4, 'width': 400, 'height': 300})
        self.image.undo_group_end.assert_called_once()

    def test_failure_is_not_reported_as_import_success(self):
        with tempfile.NamedTemporaryFile() as source:
            self.gimp.file_load_layer.return_value = None
            result = self.namespace['_import_layer'](self.owner, {'file_path': source.name})
        self.assertEqual(result['status'], 'error')
        self.image.insert_layer.assert_not_called()
        self.image.undo_group_end.assert_called_once()

    def test_mask_and_path_references_resolve_real_owned_objects(self):
        layer = mock.Mock()
        layer.get_children.return_value = []
        mask = object()
        layer.get_mask.return_value = mask
        self.image.get_layers.return_value = [layer]
        path = object()
        self.image.get_paths.return_value = [path]
        reference = self.namespace['_pdb_reference']
        for kind in ('path', 'vectors'):
            self.assertIs(reference(self.owner, SimpleNamespace(type_name='GimpPath'),
                                    {'$ref': kind, 'image_index': 2}), path)
        self.assertIs(reference(self.owner, SimpleNamespace(type_name='GimpLayerMask'),
                                {'$ref': 'mask', 'image_index': 2}), mask)
        layer.get_mask.return_value = None
        with self.assertRaisesRegex(ValueError, 'no mask'):
            reference(self.owner, SimpleNamespace(type_name='GimpLayerMask'), {'$ref': 'mask'})

    def test_gfile_conversion_is_typed_and_local(self):
        self.namespace['MCPPlugin'] = SimpleNamespace(_pdb_value_type_name=lambda spec: spec.type_name,
                                                     _pdb_enum_members=lambda spec: [])
        convert = self.namespace['_pdb_input_value']
        spec = SimpleNamespace(type_name='GFile')
        expected = ('GFile', os.path.abspath('texture.png'))
        self.assertEqual(convert(spec, {'$file': 'texture.png'}), expected)
        self.assertEqual(convert(spec, 'texture.png'), expected)
        with self.assertRaises(ValueError):
            convert(spec, 'https://example.com/texture.png')

    def test_server_forwards_owned_image_and_propagates_plugin_error(self):
        module = ast.parse((ROOT / 'gimp_mcp_server.py').read_text(encoding='utf-8'))
        node = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'import_layer')
        node.decorator_list = []
        connection = mock.Mock()
        namespace = {'Context': object, 'get_gimp_connection': lambda: connection}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<server import>', 'exec'), namespace)
        connection.send_command.return_value = {'status': 'success', 'results': {'layer_id': 52}}
        self.assertEqual(namespace['import_layer'](None, 'asset.png', image_index=2), {'layer_id': 52})
        self.assertEqual(connection.send_command.call_args.args[1]['image_index'], 2)
        connection.send_command.return_value = {'status': 'error', 'error': 'unsupported image format'}
        with self.assertRaisesRegex(RuntimeError, 'unsupported image format'):
            namespace['import_layer'](None, 'bad.png', image_index=2)


if __name__ == '__main__':
    unittest.main()
