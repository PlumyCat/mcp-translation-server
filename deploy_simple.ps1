#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Script de déploiement Azure simplifié pour le serveur MCP de traduction

.DESCRIPTION
    Ce script déploie le serveur MCP de traduction sur Azure Container Apps
    en utilisant directement Azure CLI (sans azd)
#>

param(
    [string]$ResourceGroup = "GRChatGPT",
    [string]$ContainerApp = "translation-mcp", 
    [string]$Registry = "repodemoeric",
    [string]$Location = "francecentral"
)

Write-Host "🚀 DÉPLOIEMENT AZURE SIMPLIFIÉ - SERVEUR MCP DE TRADUCTION" -ForegroundColor Green
Write-Host "=" * 70

# Vérification des prérequis
Write-Host "🔍 Vérification des prérequis..." -ForegroundColor Yellow

# Vérifier Azure CLI
$azCheck = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCheck) {
    Write-Host "❌ Azure CLI requis" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Azure CLI trouvé" -ForegroundColor Green

# Vérifier Docker
$dockerCheck = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCheck) {
    Write-Host "❌ Docker requis" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Docker trouvé" -ForegroundColor Green

# Vérifier le fichier .env
if (-not (Test-Path ".env")) {
    Write-Host "❌ Fichier .env manquant!" -ForegroundColor Red
    Write-Host "💡 Créez le fichier .env avec vos clés Azure" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Fichier .env trouvé" -ForegroundColor Green

# Affichage de la configuration
Write-Host "`n📋 Configuration du déploiement:" -ForegroundColor Cyan
Write-Host "   🏷️  Resource Group: $ResourceGroup"
Write-Host "   📦 Container App: $ContainerApp"
Write-Host "   📋 Registry: $Registry"
Write-Host "   🌍 Location: $Location"

# Connexion Azure
Write-Host "`n🔐 Vérification de la connexion Azure..." -ForegroundColor Yellow
try {
    $account = az account show --query "user.name" --output tsv 2>$null
    if ($account) {
        Write-Host "✅ Connecté en tant que: $account" -ForegroundColor Green
    } else {
        Write-Host "🔐 Connexion requise..." -ForegroundColor Yellow
        az login
    }
} catch {
    Write-Host "❌ Erreur de connexion Azure" -ForegroundColor Red
    exit 1
}

# Lecture des variables d'environnement depuis .env
Write-Host "`n📝 Lecture des variables d'environnement..." -ForegroundColor Yellow
$envVars = @{}
Get-Content ".env" | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        $envVars[$name] = $value
        Write-Host "   ✅ Variable: $name" -ForegroundColor Green
    }
}

# Construction de l'image Docker
Write-Host "`n🔨 Construction de l'image Docker..." -ForegroundColor Yellow
$imageName = "$Registry.azurecr.io/$ContainerApp"
docker build -t $imageName .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors de la construction Docker" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Image Docker construite: $imageName" -ForegroundColor Green

# Connexion au registry
Write-Host "`n📋 Connexion au Container Registry..." -ForegroundColor Yellow
az acr login --name $Registry

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur de connexion au registry" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Connecté au registry" -ForegroundColor Green

# Push de l'image
Write-Host "`n📤 Push de l'image vers le registry..." -ForegroundColor Yellow
docker push $imageName

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors du push" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Image pushée avec succès" -ForegroundColor Green

# Vérification de l'environnement Container Apps
Write-Host "`n🏗️  Vérification de l'environnement Container Apps..." -ForegroundColor Yellow
$envName = "$ContainerApp-env"

# Créer l'environnement s'il n'existe pas
$envExists = az containerapp env show --name $envName --resource-group $ResourceGroup --query "name" --output tsv 2>$null
if (-not $envExists) {
    Write-Host "📦 Création de l'environnement Container Apps..." -ForegroundColor Yellow
    az containerapp env create --name $envName --resource-group $ResourceGroup --location $Location --logs-destination none
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Erreur lors de la création de l'environnement" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Environnement créé" -ForegroundColor Green
} else {
    Write-Host "✅ Environnement trouvé" -ForegroundColor Green
}

# Préparation des variables d'environnement pour Container Apps
$envString = ""
foreach ($key in $envVars.Keys) {
    $envString += "$key=$($envVars[$key]) "
}

# Déploiement de la Container App
Write-Host "`n🚀 Déploiement de la Container App..." -ForegroundColor Yellow

# Vérifier si l'app existe déjà
$appExists = az containerapp show --name $ContainerApp --resource-group $ResourceGroup --query "name" --output tsv 2>$null

if ($appExists) {
    Write-Host "🔄 Mise à jour de la Container App existante..." -ForegroundColor Yellow
    az containerapp update `
        --name $ContainerApp `
        --resource-group $ResourceGroup `
        --image $imageName `
        --set-env-vars $envString.Trim()
} else {
    Write-Host "📦 Création de la Container App..." -ForegroundColor Yellow
    az containerapp create `
        --name $ContainerApp `
        --resource-group $ResourceGroup `
        --environment $envName `
        --image $imageName `
        --target-port 3000 `
        --ingress external `
        --env-vars $envString.Trim() `
        --cpu 0.5 `
        --memory 1Gi `
        --min-replicas 0 `
        --max-replicas 3
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors du déploiement de la Container App" -ForegroundColor Red
    exit 1
}

# Récupération de l'URL
Write-Host "`n🌐 Récupération de l'URL..." -ForegroundColor Yellow
$appUrl = az containerapp show --name $ContainerApp --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" --output tsv

if ($appUrl) {
    Write-Host "`n🎉 DÉPLOIEMENT RÉUSSI!" -ForegroundColor Green
    Write-Host "=" * 70
    Write-Host "🌐 URL du serveur: https://$appUrl" -ForegroundColor Cyan
    Write-Host "🔍 Santé: https://$appUrl/health" -ForegroundColor Cyan
    Write-Host "🛠️  Outils MCP: https://$appUrl/tools" -ForegroundColor Cyan
    Write-Host "📊 Traductions: https://$appUrl/translations" -ForegroundColor Cyan
    Write-Host "`n💡 Pour Copilot Studio, utilisez l'endpoint MCP:"
    Write-Host "   https://$appUrl/mcp" -ForegroundColor Yellow
    
    Write-Host "`n🔍 Test rapide de l'endpoint de santé..." -ForegroundColor Yellow
    try {
        $healthResponse = Invoke-RestMethod -Uri "https://$appUrl/health" -Method Get -TimeoutSec 10
        Write-Host "✅ Serveur accessible et fonctionnel!" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Serveur déployé mais pas encore accessible (démarrage en cours...)" -ForegroundColor Yellow
        Write-Host "💡 Attendez quelques minutes et testez: https://$appUrl/health" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️  Déploiement terminé mais URL non récupérée" -ForegroundColor Yellow
    Write-Host "💡 Vérifiez dans le portail Azure" -ForegroundColor Yellow
}

Write-Host "`n✅ Script terminé!" -ForegroundColor Green 