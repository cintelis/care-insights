// Care Insights POC - Azure side
// ADLS Gen2 (system of record for every lake layer) + Fabric capacity (compute).
targetScope = 'resourceGroup'

@description('Azure region. Australia East keeps data onshore.')
param location string = resourceGroup().location

@description('Globally unique storage account name (3-24 lowercase letters/numbers).')
param storageAccountName string

@description('Fabric capacity name (lowercase letters/numbers).')
param capacityName string = 'fcarepoc'

@description('Fabric capacity SKU. F2 is the smallest; pause it when idle.')
param capacitySku string = 'F2'

@description('UPN of the Fabric capacity admin.')
param capacityAdminUpn string

@description('Object ID of the user who uploads data and runs the dashboard.')
param userObjectId string

@description('Create the Fabric capacity. Needs the tenant to be signed up for Fabric.')
param deployCapacity bool = true

@description('Allow storage account keys. Only needed if Fabric connects with a key instead of workspace identity.')
param allowSharedKeyAccess bool = true

var containers = [
  'raw'   // landing zone: files exactly as source systems send them
  'lake'  // bronze / silver / gold Delta tables written by Fabric
]

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true // ADLS Gen2
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: allowSharedKeyAccess
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
  tags: { project: 'care-insights-poc' }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource cont 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for c in containers: {
  parent: blobSvc
  name: c
}]

// Storage Blob Data Contributor for the POC user (data upload + dashboard reads)
var blobContributorRole = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
resource userBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, userObjectId, blobContributorRole)
  properties: {
    principalId: userObjectId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRole)
  }
}

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = if (deployCapacity) {
  name: capacityName
  location: location
  sku: { name: capacitySku, tier: 'Fabric' }
  properties: {
    administration: { members: [ capacityAdminUpn ] }
  }
  tags: { project: 'care-insights-poc' }
}

output storageAccountName string = storage.name
output dfsEndpoint string = storage.properties.primaryEndpoints.dfs
output capacityName string = deployCapacity ? capacity.name : ''
output capacityId string = deployCapacity ? capacity.id : ''

