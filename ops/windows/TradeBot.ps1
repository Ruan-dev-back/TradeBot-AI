# Dispatcher only. Does not install WSL/Docker or register tasks/services.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('setup','preflight','start','stop','status','export','backup','verify-backup','restore','verify-recovery','run-observer')]
    [string]$Action,
    [Parameter(Mandatory=$true)][string]$LinuxRoot,
    [string]$Distribution = 'Ubuntu-24.04',
    [ValidateSet('okx','kraken')][string]$Exchange = 'okx',
    [string]$Bundle,
    [string]$Target
)
$ErrorActionPreference = 'Stop'
if (-not $LinuxRoot.StartsWith('/') -or $LinuxRoot.StartsWith('/mnt/')) {
    throw 'Use a checkout in WSL Linux ext4, such as /home/usuario/TradeBot-AI.'
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL2 is missing. Installation/admin approval is required; nothing was installed.'
}
$WslArgs = @('--distribution', $Distribution, '--cd', $LinuxRoot, '--exec',
    'python3', 'scripts/paper_host.py', $Action, '--exchange', $Exchange)
if ($Bundle) { $WslArgs += @('--bundle', $Bundle) }
if ($Target) { $WslArgs += @('--target', $Target) }
& wsl.exe @WslArgs
exit $LASTEXITCODE
