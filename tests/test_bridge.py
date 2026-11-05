import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from mcp import Client, StdioServerParameters
import gimp_mcp_server as server


class Protocol(unittest.TestCase):
    def test_file_operations_wait_longer_than_connection_probe(self):
        connection = server.GimpConnection()
        sock = mock.Mock()
        connection.sock = sock
        sock.recv.return_value = json.dumps({'status': 'success', 'results': {}}).encode()
        with mock.patch.dict('os.environ', {}, clear=True):
            result = connection.send_command('export_image', {'file_path': 'poster.png'})
        self.assertEqual(result['status'], 'success')
        sock.settimeout.assert_called_once_with(120)
        sock.close.assert_called_once()
        self.assertIsNone(connection.sock)

    def test_closed_connection_is_an_error(self):
        connection = server.GimpConnection()
        connection.sock = mock.Mock()
        connection.sock.recv.return_value = b''
        with self.assertRaises(Exception):
            connection.send_command('list_images')
        self.assertIsNone(connection.sock)


class Registry(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_registry_matches_in_process_registry(self):
        async with Client(server.mcp) as client:
            expected = {tool.name for tool in (await client.list_tools()).tools}
        transport = StdioServerParameters(command=sys.executable,
                                           args=[str(Path(server.__file__).resolve())])
        async with Client(transport) as client:
            actual = {tool.name for tool in (await client.list_tools()).tools}
        self.assertEqual(actual, expected)

    async def test_discovery_and_named_layer_tools_are_registered(self):
        async with Client(server.mcp) as client:
            registry = await client.list_tools()
        names = {tool.name for tool in registry.tools}
        self.assertGreaterEqual(len(names), 88)
        self.assertTrue({'pdb_search', 'pdb_describe', 'pdb_run', 'gegl_list_operations',
                         'gegl_describe_operation', 'gegl_apply_filter', 'transform_layer'} <= names)


if __name__ == '__main__':
    unittest.main()
