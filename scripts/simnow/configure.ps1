param(
    [string]$Symbol = 'rb2701'
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$privateDirectory = Join-Path $workspaceRoot '.simnow_private'
$credentialPath = Join-Path $privateDirectory 'credentials.dpapi'

Write-Host 'SimNow market data only. No orders will be submitted.'
Write-Host 'The account and password will be encrypted for this Windows user.'
$investorId = Read-Host 'SimNow InvestorID (not phone number)'
if ($investorId -notmatch '^\d{6}$') {
    throw 'Expected a six-digit SimNow InvestorID.'
}
$passwordInput = Read-Host 'SimNow password' -AsSecureString
$protectedInput = $null
try {
    if ($passwordInput.Length -eq 0) { throw 'Password is empty.' }
    $chosenSymbol = Read-Host "Current contract code (Enter for $Symbol)"
    if (-not [string]::IsNullOrWhiteSpace($chosenSymbol)) { $Symbol = $chosenSymbol.Trim() }
    if ($Symbol -notmatch '^[A-Za-z]{1,3}\d{3,4}$') { throw 'Invalid contract code.' }
    $configuration = @{
        userid = $investorId
        password = [System.Net.NetworkCredential]::new('', $passwordInput).Password
        brokerid = '9999'
        md_address = 'tcp://182.254.243.31:30011'
        symbol = $Symbol
    }
    $configurationJson = $configuration | ConvertTo-Json -Compress
    $protectedInput = ConvertTo-SecureString -String $configurationJson -AsPlainText -Force
    $encrypted = ConvertFrom-SecureString -SecureString $protectedInput
    New-Item -ItemType Directory -Path $privateDirectory -Force | Out-Null
    [System.IO.File]::WriteAllText($credentialPath, $encrypted, [System.Text.Encoding]::ASCII)
    Write-Host 'Encrypted configuration saved. Tell the assistant: configured.'
    Write-Host 'No connection has been started by this configuration step.'
}
finally {
    $passwordInput.Dispose()
    if ($null -ne $protectedInput) { $protectedInput.Dispose() }
    $configuration = $null
    $configurationJson = $null
    $investorId = $null
}
