param(
    [ValidateRange(30, 1800)][int]$DurationSeconds = 600,
    [ValidatePattern('^[A-Za-z]{1,3}\d{3,4}$')][string]$Symbol,
    [switch]$CheckConfig,
    [string]$PythonPath = 'C:\veighna_studio\python.exe',
    [string]$CredentialPath
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $CredentialPath) { $CredentialPath = Join-Path $workspaceRoot '.simnow_private/credentials.dpapi' }
if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
    throw 'No local encrypted SimNow configuration. Run scripts/simnow/configure.ps1 first.'
}
$protectedConfiguration = Get-Content -LiteralPath $credentialPath -Raw | ConvertTo-SecureString
try {
    $configurationJson = [System.Net.NetworkCredential]::new('', $protectedConfiguration).Password
    $configuration = $configurationJson | ConvertFrom-Json
}
finally {
    $protectedConfiguration.Dispose()
    $configurationJson = $null
}
if ($configuration.brokerid -ne '9999' -or $configuration.md_address -ne 'tcp://182.254.243.31:30011') {
    throw 'This launcher only accepts its configured SimNow market-data endpoint.'
}
if ($configuration.userid -notmatch '^\d{6}$' -or [string]::IsNullOrWhiteSpace($configuration.password)) {
    throw 'The decrypted configuration is incomplete.'
}
if ($configuration.symbol -notmatch '^[A-Za-z]{1,3}\d{3,4}$') { throw 'Invalid contract code.' }
$configuredSymbol = $configuration.symbol
if (-not [string]::IsNullOrWhiteSpace($Symbol)) { $configuration.symbol = $Symbol }
if ($CheckConfig) {
    @{ configured = $true; credentials_decryptable = $true; symbol = $configuration.symbol; sends_orders = $false } | ConvertTo-Json -Compress
    $configuration = $null
    return
}

$runDirectory = Join-Path (Join-Path $workspaceRoot 'data/simnow_checks') ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$capturePath = Join-Path $PSScriptRoot 'capture.py'
$argumentText = '-B -u "{0}" --output "{1}" --symbol "{2}" --duration {3}' -f $capturePath, $runDirectory, $configuration.symbol, $DurationSeconds
$previousUser = [Environment]::GetEnvironmentVariable('SIMNOW_USERID', 'Process')
$previousPassword = [Environment]::GetEnvironmentVariable('SIMNOW_PASSWORD', 'Process')
try {
    $env:SIMNOW_USERID = $configuration.userid
    $env:SIMNOW_PASSWORD = $configuration.password
    $captureProcess = Start-Process -FilePath $pythonPath -ArgumentList $argumentText -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDirectory 'stdout.log') -RedirectStandardError (Join-Path $runDirectory 'stderr.log') -PassThru
    $launchInfo = @{ pid = $captureProcess.Id; output = $runDirectory; symbol = $configuration.symbol; configured_symbol = $configuredSymbol; duration_seconds = $DurationSeconds; sends_orders = $false }
    $launchInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDirectory 'process.json') -Encoding UTF8
    $launchInfo | ConvertTo-Json -Compress
}
finally {
    [Environment]::SetEnvironmentVariable('SIMNOW_USERID', $previousUser, 'Process')
    [Environment]::SetEnvironmentVariable('SIMNOW_PASSWORD', $previousPassword, 'Process')
    $configuration = $null
}
