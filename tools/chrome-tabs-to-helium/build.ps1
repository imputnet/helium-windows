param([string]$OutputPath = (Join-Path $PSScriptRoot 'dist\Chrome-Tabs-to-Helium.zip'))
$ErrorActionPreference = 'Stop'
$extensionRoot = Join-Path $PSScriptRoot 'extension'
$manifest = Get-Content -LiteralPath (Join-Path $extensionRoot 'manifest.json') -Raw | ConvertFrom-Json
foreach ($asset in @($manifest.action.default_popup, 'popup.js', 'popup.css', 'core.mjs', 'launcher.ps1.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $extensionRoot $asset) -PathType Leaf)) { throw ('Missing asset: ' + $asset) }
}
$outputFull = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $outputFull) -Force | Out-Null
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$staging = Join-Path $temporaryRoot ('helium-tab-package-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
try {
    foreach ($file in (Get-ChildItem -LiteralPath $extensionRoot -File)) {
        Copy-Item -LiteralPath $file.FullName -Destination $staging
    }
    foreach ($file in @('README.md', 'guide.html')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $staging
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'docs') -Destination $staging -Recurse
    $files = @(Get-ChildItem -LiteralPath $staging | Select-Object -ExpandProperty FullName)
    Compress-Archive -LiteralPath $files -DestinationPath $outputFull -Force
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($outputFull)
    try {
        if (-not $archive.GetEntry('manifest.json')) { throw 'Package manifest is not at the ZIP root.' }
    } finally { $archive.Dispose() }
    Write-Output ('Created: ' + $outputFull)
} finally {
    $resolvedStaging = (Resolve-Path -LiteralPath $staging).ProviderPath
    if ([IO.Path]::GetDirectoryName($resolvedStaging) -ne $temporaryRoot -or
        -not [IO.Path]::GetFileName($resolvedStaging).StartsWith('helium-tab-package-')) {
        throw 'Refusing to remove a staging directory outside the expected temporary root.'
    }
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
}
