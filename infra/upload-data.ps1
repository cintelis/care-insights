<#
  Uploads the synthetic source files to the ADLS 'raw' container and the pipeline SQL
  to 'lake/_pipeline'. Uses your Entra login (no keys).
  Usage: ./infra/upload-data.ps1 [-SkipRaw]
#>
param([switch]$SkipRaw)
$ErrorActionPreference = 'Continue'
$env:AZURE_CORE_ONLY_SHOW_ERRORS = 'true'
$root  = Split-Path $PSScriptRoot -Parent
$state = Get-Content (Join-Path $root '.poc-state.json') -Raw | ConvertFrom-Json
az account set --subscription $state.subscriptionId | Out-Null
$acct = $state.storageAccountName

function Upload($container, $source, $dest) {
  az storage fs directory upload --auth-mode login --account-name $acct -f $container `
     -s $source -d $dest --recursive -o none
  if ($LASTEXITCODE -ne 0) { throw "Upload of $source failed (new role assignments can take ~5 min to apply - retry)" }
}

if (-not $SkipRaw) {
  Write-Host "Uploading raw data to $acct/raw ..."
  Upload 'raw' (Join-Path $root 'data\raw\*') '.'
}
Write-Host "Uploading pipeline SQL to $acct/lake/_pipeline ..."
Upload 'lake' (Join-Path $root 'transform\sql') '_pipeline'
az storage fs file upload --auth-mode login --account-name $acct -f lake `
   -s (Join-Path $root 'transform\bronze_sources.json') -p '_pipeline/bronze_sources.json' --overwrite -o none
az storage fs file list --auth-mode login --account-name $acct -f raw --recursive false --query "[].name" -o tsv
