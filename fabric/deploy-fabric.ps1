<#
  Deploys the Fabric side of the POC with the Fabric REST API:
    workspace (on the POC capacity) -> lakehouse -> ADLS connections -> OneLake shortcuts
    -> notebook -> run it -> gold table shortcuts (SQL endpoint) -> optional daily schedule

  Prereqs: ./infra/deploy.ps1 (with the capacity) and ./infra/upload-data.ps1 have run,
           and the tenant is signed up for Fabric.
  Usage:   ./fabric/deploy-fabric.ps1 [-AuthMode WorkspaceIdentity|Key] [-Schedule] [-SkipRun]
#>
param(
  [string]$WorkspaceName = 'care-insights-poc',
  [string]$LakehouseName = 'lh_care',
  [string]$NotebookName  = 'nb_care_medallion',
  [ValidateSet('WorkspaceIdentity','Key')][string]$AuthMode = 'WorkspaceIdentity',
  [string]$AsOfDate = '2026-10-18',
  [switch]$Schedule,
  [switch]$SkipRun
)
$ErrorActionPreference = 'Continue'   # az writes warnings to stderr; failures are thrown explicitly
$env:AZURE_CORE_ONLY_SHOW_ERRORS = 'true'
$root  = Split-Path $PSScriptRoot -Parent
$state = Get-Content (Join-Path $root '.poc-state.json') -Raw | ConvertFrom-Json
$acct  = $state.storageAccountName
$dfs   = "https://$acct.dfs.core.windows.net"
$api   = 'https://api.fabric.microsoft.com/v1'
& az account set --subscription $state.subscriptionId

$token = & az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv 2>$null
if (-not $token) { throw 'Could not get a Fabric token. Is the tenant signed up for Fabric (Power BI Service app enabled)?' }
$headers = @{ Authorization = "Bearer $token"; 'Content-Type' = 'application/json' }

function Fabric([string]$Method, [string]$Path, $Body = $null) {
  $uri = if ($Path -like 'http*') { $Path } else { "$api$Path" }
  $req = @{ Method = $Method; Uri = $uri; Headers = $headers; UseBasicParsing = $true }
  if ($null -ne $Body) { $req.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 20)) }
  try { $r = Invoke-WebRequest @req }
  catch {
    $msg = $_.ErrorDetails.Message; if (-not $msg) { $msg = $_.Exception.Message }
    throw "Fabric $Method $Path failed: $msg"
  }
  if ($r.StatusCode -eq 202 -and $r.Headers['Location']) {
    # long-running operation: poll until done, then fetch the result if there is one
    $loc = $r.Headers['Location']
    do {
      $wait = 5; if ($r.Headers['Retry-After']) { $wait = [int](@($r.Headers['Retry-After'])[0]) }
      Start-Sleep -Seconds $wait
      $r = Invoke-WebRequest -Uri $loc -Headers $headers -UseBasicParsing
      $op = $r.Content | ConvertFrom-Json
    } while ($op.status -in @('NotStarted','Running','Undefined'))
    if ($op.status -ne 'Succeeded') { throw "Operation $Path ended as $($op.status): $($r.Content)" }
    try { return (Invoke-WebRequest -Uri "$loc/result" -Headers $headers -UseBasicParsing).Content | ConvertFrom-Json } catch { return $op }
  }
  if ($r.Content) { return $r.Content | ConvertFrom-Json }
}

function B64([string]$s) { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($s)) }

# ---------- capacity ----------
$cap = (Fabric GET '/capacities').value | Where-Object { $_.displayName -eq $state.capacityName } | Select-Object -First 1
if (-not $cap) { throw "Capacity '$($state.capacityName)' not visible to you in Fabric. Did ./infra/deploy.ps1 create it?" }
if ($cap.state -ne 'Active') {
  Write-Host 'Resuming capacity...'
  & az resource invoke-action --action resume --ids $state.capacityResourceId -o none
  Start-Sleep -Seconds 20
}

# ---------- workspace ----------
$ws = (Fabric GET '/workspaces').value | Where-Object { $_.displayName -eq $WorkspaceName } | Select-Object -First 1
if (-not $ws) {
  Write-Host "Creating workspace $WorkspaceName"
  $ws = Fabric POST '/workspaces' @{ displayName = $WorkspaceName; capacityId = $cap.id; description = 'Care Insights POC - Support at Home budget, visit and invoice monitoring' }
} elseif ($ws.capacityId -ne $cap.id) {
  Fabric POST "/workspaces/$($ws.id)/assignToCapacity" @{ capacityId = $cap.id } | Out-Null
}
$wsId = $ws.id

# ---------- lakehouse ----------
$lh = (Fabric GET "/workspaces/$wsId/lakehouses").value | Where-Object { $_.displayName -eq $LakehouseName } | Select-Object -First 1
if (-not $lh) { Write-Host "Creating lakehouse $LakehouseName"; $lh = Fabric POST "/workspaces/$wsId/lakehouses" @{ displayName = $LakehouseName } }
$lhId = $lh.id

# ---------- credentials for ADLS ----------
if ($AuthMode -eq 'WorkspaceIdentity') {
  $wsFull = Fabric GET "/workspaces/$wsId"
  if (-not $wsFull.workspaceIdentity) {
    Write-Host 'Provisioning workspace identity'
    Fabric POST "/workspaces/$wsId/provisionIdentity" | Out-Null
    $wsFull = Fabric GET "/workspaces/$wsId"
  }
  $spId = $wsFull.workspaceIdentity.servicePrincipalId
  $storageId = & az storage account show -n $acct -g $state.resourceGroup --query id -o tsv
  Write-Host "Granting workspace identity ($spId) Storage Blob Data Contributor"
  & az role assignment create --assignee-object-id $spId --assignee-principal-type ServicePrincipal `
      --role 'Storage Blob Data Contributor' --scope $storageId -o none 2>$null
  $cred = @{ credentialType = 'WorkspaceIdentity' }
  Start-Sleep -Seconds 30   # let the role assignment propagate before the connection test
} else {
  $key  = & az storage account keys list -n $acct -g $state.resourceGroup --query '[0].value' -o tsv
  $cred = @{ credentialType = 'Key'; key = $key }
}

$existingConns = (Fabric GET '/connections').value
$connIds = @{}
foreach ($container in 'raw', 'lake') {
  $name = "adls-$acct-$container"
  $c = $existingConns | Where-Object { $_.displayName -eq $name } | Select-Object -First 1
  if (-not $c) {
    Write-Host "Creating connection $name"
    $c = Fabric POST '/connections' @{
      connectivityType  = 'ShareableCloud'
      displayName       = $name
      privacyLevel      = 'Organizational'
      connectionDetails = @{
        type = 'AzureDataLakeStorage'; creationMethod = 'AzureDataLakeStorage'
        parameters = @(
          @{ dataType = 'Text'; name = 'server'; value = $dfs },
          @{ dataType = 'Text'; name = 'path';   value = "/$container" })
      }
      credentialDetails = @{ singleSignOnType = 'None'; connectionEncryption = 'NotEncrypted'; skipTestConnection = $false; credentials = $cred }
    }
  }
  $connIds[$container] = $c.id
}

function Shortcut($Path, $Name, $Container, $SubPath) {
  Fabric POST "/workspaces/$wsId/items/$lhId/shortcuts?shortcutConflictPolicy=CreateOrOverwrite" @{
    path = $Path; name = $Name
    target = @{ adlsGen2 = @{ location = $dfs; subpath = "/$Container$SubPath"; connectionId = $connIds[$Container] } }
  } | Out-Null
}
Write-Host 'Creating OneLake shortcuts Files/raw and Files/lake -> ADLS'
Shortcut 'Files' 'raw'  'raw'  ''
Shortcut 'Files' 'lake' 'lake' ''

# ---------- notebook ----------
$nbSrc = (Get-Content (Join-Path $PSScriptRoot 'nb_care_medallion.py') -Raw).
  Replace('{{LAKEHOUSE_ID}}', $lhId).Replace('{{LAKEHOUSE_NAME}}', $LakehouseName).Replace('{{WORKSPACE_ID}}', $wsId)
$definition = @{ parts = @(@{ path = 'notebook-content.py'; payload = (B64 $nbSrc); payloadType = 'InlineBase64' }) }
$nb = (Fabric GET "/workspaces/$wsId/notebooks").value | Where-Object { $_.displayName -eq $NotebookName } | Select-Object -First 1
if ($nb) {
  Write-Host 'Updating notebook definition'
  Fabric POST "/workspaces/$wsId/notebooks/$($nb.id)/updateDefinition" @{ definition = $definition } | Out-Null
} else {
  Write-Host "Creating notebook $NotebookName"
  $nb = Fabric POST "/workspaces/$wsId/notebooks" @{ displayName = $NotebookName; definition = $definition }
}
$nbId = $nb.id

# ---------- run ----------
if (-not $SkipRun) {
  Write-Host "Running notebook (as_of_date=$AsOfDate). First run includes Spark start-up, allow a few minutes..."
  $run = Invoke-WebRequest -Method POST -UseBasicParsing -Headers $headers `
    -Uri "$api/workspaces/$wsId/items/$nbId/jobs/instances?jobType=RunNotebook" `
    -Body (@{ executionData = @{ parameters = @{ as_of_date = @{ value = $AsOfDate; type = 'string' } } } } | ConvertTo-Json -Depth 10)
  $loc = $run.Headers['Location']
  do {
    Start-Sleep -Seconds 20
    $job = Invoke-RestMethod -Uri $loc -Headers $headers
    Write-Host "  job status: $($job.status)"
  } while ($job.status -in @('NotStarted','InProgress'))
  if ($job.status -ne 'Completed') { throw "Notebook run $($job.status): $($job.failureReason | ConvertTo-Json -Compress)" }

  # gold Delta folders now exist in ADLS - expose them as lakehouse tables (SQL endpoint, Direct Lake, etc.)
  foreach ($t in Get-ChildItem (Join-Path $root 'transform\sql\gold') -Filter *.sql) {
    $name = ($t.BaseName -split '_', 2)[1]
    Write-Host "Table shortcut gold_$name -> lake/gold/$name"
    Shortcut 'Tables' "gold_$name" 'lake' "/gold/$name"
  }
}

if ($Schedule) {
  Write-Host 'Adding daily 06:00 (Sydney) schedule'
  Fabric POST "/workspaces/$wsId/items/$nbId/jobs/RunNotebook/schedules" @{
    enabled = $true
    configuration = @{ type = 'Daily'; times = @('06:00'); localTimeZoneId = 'AUS Eastern Standard Time'
                       startDateTime = (Get-Date).ToString('yyyy-MM-ddT00:00:00'); endDateTime = (Get-Date).AddYears(1).ToString('yyyy-MM-ddT00:00:00') }
  } | Out-Null
}

Write-Host "`nDone. Workspace: https://app.fabric.microsoft.com/groups/$wsId"

