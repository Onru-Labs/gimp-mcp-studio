[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [string]$ProfileDirectory
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'gimp-mcp-plugin.py'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Workspace GIMP plug-in source was not found: $source"
}

if (-not $ProfileDirectory) {
    $profileRoot = Join-Path $env:APPDATA 'GIMP'
    $profiles = @(Get-ChildItem -LiteralPath $profileRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+$' } |
        Sort-Object { [version]$_.Name })
    if (-not $profiles.Count) {
        throw "No GIMP 3 profile was found under $profileRoot. Open GIMP once, then rerun this script."
    }
    $ProfileDirectory = $profiles[-1].FullName
}

$targetDirectory = Join-Path $ProfileDirectory 'plug-ins\gimp-mcp-plugin'
$target = Join-Path $targetDirectory 'gimp-mcp-plugin.py'
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$targetHash = if (Test-Path -LiteralPath $target -PathType Leaf) {
    (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
} else { $null }

if ($sourceHash -eq $targetHash) {
    Write-Output "GIMP plug-in is already synchronized: $target"
    exit 0
}

if ($PSCmdlet.ShouldProcess($target, 'Install workspace GIMP MCP plug-in')) {
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    $installedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($installedHash -ne $sourceHash) {
        throw "Plug-in copy verification failed. Expected $sourceHash, got $installedHash."
    }
    Write-Output "Installed and verified: $target"
    Write-Output 'Restart GIMP, then select Tools > MCP > Start MCP Server.'
} else {
    Write-Output "Would install $source to $target"
}
