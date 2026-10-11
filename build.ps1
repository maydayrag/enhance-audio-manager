$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$addonRoot = Join-Path $projectRoot "addon"
$vendorRoot = Join-Path $addonRoot "globalPlugins\vendor"
$distRoot = Join-Path $projectRoot "dist"
$stagingRoot = Join-Path $env:TEMP "enhanceAudioManager-addon-staging"
$resolvedTempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
$resolvedStagingRoot = [System.IO.Path]::GetFullPath($stagingRoot)

if (-not $resolvedStagingRoot.StartsWith($resolvedTempRoot + [System.IO.Path]::DirectorySeparatorChar)) {
	throw "Refusing to use a staging directory outside the temporary directory."
}

$resolvedVendorRoot = [System.IO.Path]::GetFullPath($vendorRoot)
$resolvedAddonRoot = [System.IO.Path]::GetFullPath($addonRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
if (-not $resolvedVendorRoot.StartsWith($resolvedAddonRoot + [System.IO.Path]::DirectorySeparatorChar)) {
	throw "Refusing to replace a vendor directory outside the add-on source directory."
}
if (Test-Path -LiteralPath $vendorRoot) {
	Remove-Item -LiteralPath $vendorRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null
python -m pip install --disable-pip-version-check --upgrade --target $vendorRoot "comtypes==1.4.13" "pycaw==20251023" "psutil==7.2.1"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if (Test-Path -LiteralPath $stagingRoot) {
	Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
# Copy the package while excluding generated Python cache files.
& robocopy $addonRoot $stagingRoot /E /XD __pycache__ /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) {
	throw "Robocopy failed with exit code $LASTEXITCODE."
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
$zipPath = Join-Path $distRoot "enhanceAudioManager-2.0.6.zip"
$addonPath = Join-Path $distRoot "enhanceAudioManager-2.0.6.nvda-addon"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
if (Test-Path -LiteralPath $addonPath) { Remove-Item -LiteralPath $addonPath -Force }
Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath
python (Join-Path $projectRoot "verify_addon.py") $zipPath
if ($LASTEXITCODE -ne 0) { throw "ZIP verification failed." }
Move-Item -LiteralPath $zipPath -Destination $addonPath
python (Join-Path $projectRoot "verify_addon.py")
if ($LASTEXITCODE -ne 0) { throw "Add-on verification failed." }
Write-Host "Built $addonPath"
