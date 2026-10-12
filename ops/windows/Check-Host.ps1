# Read-only prerequisites. No account, feature, service or notification registration.
$ErrorActionPreference = 'Stop'
foreach ($Name in @('wsl.exe','docker.exe')) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name unavailable; install/enable it on your PC only with authorization."
    }
}
& wsl.exe --status
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ServerOS = & docker.exe info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($ServerOS.Trim() -ne 'linux') { throw 'Select Linux containers in Docker Desktop.' }
& docker.exe compose version
exit $LASTEXITCODE
