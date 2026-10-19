<#
  Deploys the Azure side of the POC: resource group, ADLS Gen2, Fabric capacity.
  The capacity is paused straight after creation so it costs nothing until you need it.

  Usage:  ./infra/deploy.ps1                 (current az subscription, defaults below)
          ./infra/deploy.ps1 -SubscriptionId <guid>
          ./infra/deploy.ps1 -KeepCapacityRunning
#>
param(
  [string]$SubscriptionId = '',   # empty = the subscription 'az account show' reports
  [string]$ResourceGroup  = 'rg-care-insights-poc',
  [string]$Location       = 'australiaeast',
  [string]$CapacityName   = 'fcarepoc',
  [switch]$KeepCapacityRunning,
  [switch]$SkipCapacity      # use while the tenant is not yet signed up for Fabric
)
$ErrorActionPreference = 'Continue'   # az writes warnings to stderr; we check $LASTEXITCODE instead
$env:AZURE_CORE_ONLY_SHOW_ERRORS = 'true'
$root = Split-Path $PSScriptRoot -Parent
$stateFile = Join-Path $root '.poc-state.json'

if (-not $SubscriptionId) { $SubscriptionId = az account show --query id -o tsv }
if (-not $SubscriptionId) { throw 'Not signed in: run az login first (or pass -SubscriptionId).' }
az account set --subscription $SubscriptionId | Out-Null

# Reuse the storage name between runs (it must be globally unique)
$state = if (Test-Path $stateFile) { Get-Content $stateFile -Raw | ConvertFrom-Json } else { $null }
$existing = az storage account list -g $ResourceGroup --query "[?starts_with(name,'stcarepoc')].name | [0]" -o tsv 2>$null
$storageName = if ($state -and $state.storageAccountName) { $state.storageAccountName } elseif ($existing) { $existing } else {
  'stcarepoc' + (-join ((97..122) + (48..57) | Get-Random -Count 6 | ForEach-Object { [char]$_ }))
}

$userUpn = az account show --query user.name -o tsv
$userId  = az ad signed-in-user show --query id -o tsv

Write-Host "Resource group: $ResourceGroup ($Location)"
az group create -n $ResourceGroup -l $Location --tags project=care-insights-poc -o none

Write-Host "Deploying storage '$storageName' + Fabric capacity '$CapacityName'..."
$out = az deployment group create -g $ResourceGroup -n care-insights-poc `
  --template-file (Join-Path $PSScriptRoot 'main.bicep') `
  --parameters storageAccountName=$storageName capacityName=$CapacityName `
               capacityAdminUpn=$userUpn userObjectId=$userId deployCapacity=$(if ($SkipCapacity) {'false'} else {'true'}) `
  --query properties.outputs -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $out) { throw 'Bicep deployment failed' }

$capId = $out.capacityId.value
if ($capId -and -not $KeepCapacityRunning) {
  Write-Host 'Pausing Fabric capacity (resume it with ./infra/capacity.ps1 resume)...'
  az resource invoke-action --action suspend --ids $capId -o none 2>$null
}

[ordered]@{
  subscriptionId     = $SubscriptionId
  resourceGroup      = $ResourceGroup
  location           = $Location
  storageAccountName = $out.storageAccountName.value
  dfsEndpoint        = $out.dfsEndpoint.value
  capacityName       = $out.capacityName.value
  capacityResourceId = $capId
} | ConvertTo-Json | Set-Content $stateFile -Encoding utf8

Write-Host "Done. State written to $stateFile"



