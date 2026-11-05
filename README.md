# GIMP MCP bridge

GIMP MCP Studio contains a GIMP 3 plug-in and MCP server, distributed as the standalone Python package source tree `gimp-mcp-studio`. The public source repository is [Onru-Labs/gimp-mcp-studio](https://github.com/Onru-Labs/gimp-mcp-studio). It has not been published to a package registry.

This is a modified fork of [gimp-mcp/gimp-mcp](https://github.com/gimp-mcp/gimp-mcp), distributed under GPL-3.0 with original source attribution retained. See `LICENSE` and `NOTICE`.

From this directory, install with `python -m pip install .` and launch the stdio server with `gimp-mcp-studio`. The wheel includes the companion plug-in, PowerShell installer, and batch-start script under the environment's `share/gimp-mcp-studio` directory. GIMP itself is installed separately. For tests, install `python -m pip install ".[test]"` then run `python -m unittest discover -s tests -v`; these do not substitute for live GIMP editing verification.

The server exposes **88 named MCP tools** in `gimp_mcp_server.py`. That number describes the fixed convenience tools; the live GIMP Procedure Database (PDB) and GEGL registries add operations discovered from the running GIMP installation. The bridge does not claim that every GIMP UI action or third-party plug-in is callable through the PDB.

## Runtime

- GIMP 3.x with this plug-in installed and its MCP socket started.
- Python 3.11 or later for the MCP server.
- The package declares `mcp>=2.0,<3`; `pip install .` installs its server dependency.
- A local socket on `localhost:9877` between the server and GIMP plug-in.

For a standalone checkout, `python -m pip install .` is sufficient for the MCP server.

Install or preview the plug-in copy from this checkout:

```powershell
.\install-plugin.ps1 -WhatIf
.\install-plugin.ps1
```

Restart GIMP after installation, open an image, then choose **Tools → MCP → Start MCP Server**.

Launch the MCP server through the configured client using stdio. A direct local invocation is:

```powershell
python gimp_mcp_server.py
```

## Capability map

The fixed tools cover image metadata and snapshots; layers and transforms; selections; drawing and fills; text; color, tone, blur, sharpen, and noise adjustments; crop, scale, rotate, and warp; undo/redo; export; and batch/social formats.

For operations not represented by a fixed tool, discover the running GIMP's own installed procedures:

1. `pdb_search` searches procedure names and descriptive fields with paging.
2. `pdb_describe` returns typed input/output schemas.
3. `pdb_run` executes one named procedure with typed JSON values and explicit image/layer references.
4. `gegl_list_operations` and `gegl_describe_operation` inspect available GEGL operations and properties.
5. `gegl_apply_filter`, `gegl_list_filters`, and `gegl_filter_action` apply and manage editable, non-destructive layer filters.

The PDB tools expose procedures installed in that GIMP instance. Generic JSON mapping handles common scalars, arrays, enums, colors, and supported GIMP object references; procedures requiring unsupported GObject values or UI-only interactions need a typed adapter. GIMP's own procedure browser and plug-in APIs describe what the installed application exposes.

Raw Python execution through `call_api` is disabled unless `GIMP_MCP_ALLOW_UNSAFE_PYTHON=1` is set for the MCP server and plug-in. Typed tools and PDB access should be preferred. Independently, `pdb_run` always rejects procedure names matching code-evaluation, console, and application-shutdown patterns; the raw-Python opt-in does not bypass that PDB guard.

## MCP versioning

The locally verified Python MCP SDK version is **2.3.0**. Its implementation supports the `2026-07-28` protocol revision and compatibility paths for earlier handshake-era revisions; this package has not independently tested every client/revision combination. The current `mcp.run()` transport is stdio; the bridge's separate GIMP socket is an internal local transport, not an MCP network endpoint. Protocol version, SDK major version, and the count of GIMP tools are separate concepts.

The modern protocol uses stateless requests and supports multi-round-trip replies. It does not give this plug-in arbitrary server-initiated push to a client. The Tasks extension is not implemented by the Python SDK 2.0 baseline; long GIMP operations currently return through ordinary tool calls and local logs.

## Service and verification

The service is registered as a GIMP persistent procedure, signals readiness to the host, and dispatches all GIMP API calls through the GLib main loop. File open/export/save calls have a 120-second socket timeout; other commands use 10 seconds. Set `GIMP_MCP_OPERATION_TIMEOUT` to override the operation timeout (bounded to 1–600 seconds).

For an isolated local profile, set `GIMP3_DIRECTORY` to a dedicated local directory and copy the plug-in into its `plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py`. Launch the installed `gimp-console` executable with `--new-instance --no-data --no-shm --console-messages --batch-interpreter=python-fu-eval` and a `--batch` expression that executes this folder's `batch-start.py`. Keep that process running; do not pass `--quit`.

A controlled GIMP 3.2.6 session opened a layered ORA, adjusted a named layer, exported a PNG and saved an XCF through an SDK 2.x in-process client. This verifies only that exercised edit path, not every registered tool or external stdio editing. A longer file-operation timeout addresses an observed export timeout.

The built wheel was also installed into an isolated target on 2026-11-05. Both its Python module and installed Windows `gimp-mcp-studio.exe` entry point successfully returned the same 88-tool registry over a real SDK 2 stdio connection. The wheel includes the companion plug-in, installer, batch-start script, GPL license, and notice. That transport/package probe calls discovery only and does not establish live editing coverage for every tool. On restricted Windows environments, use a writable `TEMP`/`TMP` directory when building or installing.

A separate read-only SDK 2 stdio probe of the running GIMP 3.2.6 instance on 2026-11-05 discovered **1,034 installed PDB procedures** and **182 GEGL operations**, alongside the **88 registered MCP tools**. It paged every name and inspected five representative PDB schemas, without executing any discovered procedure or filter. These counts describe the installed environment, not guaranteed execution coverage or a maximum capability limit. GEGL property description was deliberately skipped in this strictly read-only probe because its implementation constructs and deletes a temporary filter on an existing layer.

A subsequent isolated GIMP 3.2.6 helper regression probe verified that native GEGL configuration is applied and updated before merging: the sharpen fixture produced a nonzero pixel change, while an invalid blur radius and an unknown property returned explicit errors. Seven local checks include validation of requested properties, clamped values, merge-error propagation, and the SDK 2 stdio registry. This confirms the exercised helper paths only; it does not extend coverage to every installed GEGL filter.

An isolated GIMP 3.2.6 snapshot regression session subsequently captured 24 actual full/detail views while exercising native object handles, checkpoint edits and restoration. Snapshots now duplicate the explicitly selected image, render its full composite, crop/scale that owned scratch image, and delete it; they no longer select a top layer through the global clipboard. Native alpha-preserving thumbnails cover sizes up to 1024 pixels, with PNG export for larger snapshots. The source ORA remained unchanged. Four new snapshot tests bring the local suite to eleven checks; this probe did not exercise every MCP tool.

Export and geometry checks alone do not establish visual quality or product identity. Inspect the artwork before release; an unreviewed output is not an approved result.

Useful entry points:

- [`gimp_mcp_server.py`](gimp_mcp_server.py): MCP tool definitions and stdio server.
- [`gimp-mcp-plugin.py`](gimp-mcp-plugin.py): GIMP 3 plug-in, local socket commands, PDB and GEGL adapters.
- [`install-plugin.ps1`](install-plugin.ps1): profile detection, copy, and hash verification.

## Upstream status

This directory has package metadata, a GPL license and attribution notice, protocol/registry checks, and a CI workflow intended for a standalone checkout. The standalone source is published at [Onru-Labs/gimp-mcp-studio](https://github.com/Onru-Labs/gimp-mcp-studio). Eleven local unit/protocol/helper/snapshot checks pass on Python 3.13, and the standalone [Python 3.11/3.13 Linux CI matrix passed](https://github.com/Onru-Labs/gimp-mcp-studio/actions/runs/42007858113). The checks cover connection handling, file-operation timeouts, and tool registration; full MCP protocol conformance and every live GIMP operation remain unverified. Publication makes the source available; it does not establish upstream acceptance or full GIMP capability coverage.
