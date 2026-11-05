"""Run inside GIMP's python-fu-eval batch interpreter to start the MCP service."""
from gi.repository import Gimp

procedure = Gimp.get_pdb().lookup_procedure('plug-in-mcp-server')
if procedure is None:
    raise RuntimeError('MCP plug-in is not installed in this GIMP profile')
config = procedure.create_config()
config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
result = procedure.run(config)
if result.index(0) != Gimp.PDBStatusType.SUCCESS:
    raise RuntimeError('MCP persistent service did not start successfully')
