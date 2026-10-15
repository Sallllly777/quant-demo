param(
    [switch]$ExecuteSimNow, [string]$ReferenceContract,
    [string]$PythonPath = 'C:\veighna_studio\python.exe',
    [string]$CredentialPath,
    [ValidateRange(1,1800)][int]$DurationSeconds = 300,
    [switch]$ShowReferenceWindow,
    [double]$Trigger = 0
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $CredentialPath) { $CredentialPath = Join-Path $workspaceRoot '.simnow_private/credentials.dpapi' }
$protectedConfiguration = Get-Content -LiteralPath $credentialPath -Raw | ConvertTo-SecureString
try { $configuration = [System.Net.NetworkCredential]::new('', $protectedConfiguration).Password | ConvertFrom-Json }
finally { $protectedConfiguration.Dispose() }
if ($configuration.brokerid -ne '9999' -or $configuration.md_address -ne 'tcp://182.254.243.31:30011') { throw 'SimNow configuration required.' }
$runDirectory = Join-Path (Join-Path $workspaceRoot 'data/simnow_checks') ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-acceptance-' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$scriptPath = Join-Path $PSScriptRoot 'acceptance.py'
$argumentText = '-B -u "{0}" --output "{1}"' -f $scriptPath, $runDirectory
if ($ExecuteSimNow) { $argumentText += ' --execute-simnow' }
if ($Trigger -gt 0) { $argumentText += ' --trigger ' + $Trigger.ToString([Globalization.CultureInfo]::InvariantCulture) }
if ($ReferenceContract) {
    if ($ExecuteSimNow) { throw 'Reference client is read-only.' }
    $contractPath = (Resolve-Path -LiteralPath $ReferenceContract).Path
    $scriptPath = Join-Path $PSScriptRoot 'reference_client.py'
    $argumentText = '-B -u "{0}" --output "{1}" --contract "{2}"' -f $scriptPath, $runDirectory, $contractPath
    $argumentText += ' --duration ' + $DurationSeconds
    if (-not $ShowReferenceWindow) { $argumentText += ' --headless' }
}
$previousUser = [Environment]::GetEnvironmentVariable('SIMNOW_USERID', 'Process')
$previousPassword = [Environment]::GetEnvironmentVariable('SIMNOW_PASSWORD', 'Process')
$windowStyle = 'Hidden'
if ($ReferenceContract -and $ShowReferenceWindow) { $windowStyle = 'Normal' }
try {
    $env:SIMNOW_USERID = $configuration.userid
    $env:SIMNOW_PASSWORD = $configuration.password
    $process = Start-Process -FilePath $PythonPath -ArgumentList $argumentText -WorkingDirectory $workspaceRoot -WindowStyle $windowStyle -RedirectStandardOutput (Join-Path $runDirectory 'stdout.log') -RedirectStandardError (Join-Path $runDirectory 'stderr.log') -PassThru
    $info = @{pid=$process.Id; output=$runDirectory; symbol='ag2612'; simulation=$true; execute=[bool]$ExecuteSimNow}
    $info | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runDirectory 'process.json') -Encoding UTF8
    $info | ConvertTo-Json -Compress
}
finally {
    [Environment]::SetEnvironmentVariable('SIMNOW_USERID', $previousUser, 'Process')
    [Environment]::SetEnvironmentVariable('SIMNOW_PASSWORD', $previousPassword, 'Process')
    $configuration = $null
}
