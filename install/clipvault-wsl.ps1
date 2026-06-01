# ClipVault WSL hosted installer
# Downloads the CK42X shell installer and runs it inside the default WSL distro.
# Usage from Windows PowerShell:
#   iwr https://ck42x.com/install/clipvault-wsl.ps1 -OutFile $env:TEMP\clipvault-wsl.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\clipvault-wsl.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  throw "wsl.exe was not found. Install WSL first, then rerun this installer."
}

$scriptUrl = $env:CLIPVAULT_INSTALLER_URL
if ([string]::IsNullOrWhiteSpace($scriptUrl)) {
  $scriptUrl = "https://ck42x.com/install/clipvault.sh"
}

Write-Host "-> Installing ClipVault inside the default WSL distro..."
Write-Host "-> Source installer: $scriptUrl"

$bashCommand = "curl -fsSL '$scriptUrl' | bash"
wsl.exe -e bash -lc $bashCommand
if ($LASTEXITCODE -ne 0) {
  throw "ClipVault WSL install failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "[ok] ClipVault installed in WSL. Open a WSL terminal and run: clipvault"
