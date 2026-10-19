<#
  Pause / resume / show the Fabric capacity. An F2 costs roughly US$0.36/hour while running.
  Usage: ./infra/capacity.ps1 status|resume|suspend
#>
param([ValidateSet('status','resume','suspend')][string]$Action = 'status')
$ErrorActionPreference = 'Continue'   # az writes warnings to stderr; we check $LASTEXITCODE instead
$env:AZURE_CORE_ONLY_SHOW_ERRORS = 'true'
$state = Get-Content (Join-Path (Split-Path $PSScriptRoot -Parent) '.poc-state.json') -Raw | ConvertFrom-Json
az account set --subscription $state.subscriptionId | Out-Null
if ($Action -ne 'status') { az resource invoke-action --action $Action --ids $state.capacityResourceId -o none }
az resource show --ids $state.capacityResourceId --query "{name:name, sku:sku.name, state:properties.state}" -o table

