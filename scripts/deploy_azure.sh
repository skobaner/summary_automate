#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env.azure ]]; then
  echo "Missing .env.azure. Copy .env.azure.example and fill values."
  exit 1
fi

set -a
source ./.env.azure
set +a

: "${AZ_SUBSCRIPTION_ID:?missing}"
: "${AZ_RESOURCE_GROUP:?missing}"
: "${AZ_LOCATION:?missing}"
: "${AZ_ACR_NAME:?missing}"
: "${AZ_CONTAINERAPP_ENV:?missing}"
: "${AZ_CONTAINERAPP_NAME:?missing}"
: "${AZ_IMAGE_TAG:?missing}"

az account set --subscription "$AZ_SUBSCRIPTION_ID"

az group create \
  --name "$AZ_RESOURCE_GROUP" \
  --location "$AZ_LOCATION" >/dev/null

if ! az acr show --name "$AZ_ACR_NAME" --resource-group "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  az acr create \
    --name "$AZ_ACR_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --sku Basic \
    --admin-enabled true >/dev/null
fi

ACR_LOGIN_SERVER=$(az acr show --name "$AZ_ACR_NAME" --resource-group "$AZ_RESOURCE_GROUP" --query loginServer -o tsv)
IMAGE="$ACR_LOGIN_SERVER/itb-report-api:$AZ_IMAGE_TAG"

az acr login --name "$AZ_ACR_NAME"
docker build -t "$IMAGE" .
docker push "$IMAGE"

if ! az containerapp env show --name "$AZ_CONTAINERAPP_ENV" --resource-group "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  az containerapp env create \
    --name "$AZ_CONTAINERAPP_ENV" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --location "$AZ_LOCATION" >/dev/null
fi

if az containerapp show --name "$AZ_CONTAINERAPP_NAME" --resource-group "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  az containerapp update \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --image "$IMAGE" \
    --set-env-vars \
      SMTP_HOST="$SMTP_HOST" \
      SMTP_PORT="$SMTP_PORT" \
      SMTP_USE_TLS="$SMTP_USE_TLS" \
      SMTP_USERNAME="$SMTP_USERNAME" \
      SMTP_PASSWORD="$SMTP_PASSWORD" \
      EMAIL_FROM="$EMAIL_FROM" >/dev/null
else
  az containerapp create \
    --name "$AZ_CONTAINERAPP_NAME" \
    --resource-group "$AZ_RESOURCE_GROUP" \
    --environment "$AZ_CONTAINERAPP_ENV" \
    --image "$IMAGE" \
    --target-port 8000 \
    --ingress external \
    --registry-server "$ACR_LOGIN_SERVER" \
    --cpu 1.0 \
    --memory 2.0Gi \
    --env-vars \
      SMTP_HOST="$SMTP_HOST" \
      SMTP_PORT="$SMTP_PORT" \
      SMTP_USE_TLS="$SMTP_USE_TLS" \
      SMTP_USERNAME="$SMTP_USERNAME" \
      SMTP_PASSWORD="$SMTP_PASSWORD" \
      EMAIL_FROM="$EMAIL_FROM" >/dev/null
fi

FQDN=$(az containerapp show \
  --name "$AZ_CONTAINERAPP_NAME" \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

echo "Deployment complete"
echo "App URL: https://$FQDN"
echo "Health:  https://$FQDN/health"
