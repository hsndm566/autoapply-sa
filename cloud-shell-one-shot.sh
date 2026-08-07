#!/bin/bash
# ONE-COMMAND Azure deploy for HASSAN (Owner on 5974c845-...).
# Runs in Cloud Shell (Bash). Uses your already-signed-in session — no SP, no device code.
# After running, it prints the VM IP and texts Hermes via Telegram.
set -e
SUB="5974c845-4443-4b80-a0cd-b83696573637"
RG="autoapply-rg"; VM="autoapply-vm"; LOC="uaenorth"; USER="azureuser"
az account set --subscription "$SUB" >/dev/null
echo "[1/5] Resource group..."
az group create --name "$RG" --location "$LOC" -o none
# generate SSH key if missing
if [ ! -f ~/.ssh/autoapply_id_ed25519 ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/autoapply_id_ed25519 -N "" -q
fi
PUB=$(cat ~/.ssh/autoapply_id_ed25519.pub)
echo "[2/5] VM (B1S free)..."
az vm create --resource-group "$RG" --name "$VM" --image Ubuntu2204 --size Standard_B1s \
  --admin-username "$USER" --ssh-key-value "$PUB" --location "$LOC" -o none
echo "[3/5] Auto-shutdown 23:00 UTC (free tier)..."
az vm auto-shutdown -g "$RG" -n "$VM" --time 2300 -o none
echo "[4/5] Get IP..."
IP=$(az vm show -g "$RG" -n "$VM" --show-details --query publicIps -o tsv)
echo "VM IP: $IP"
# notify Hermes
curl -s -X POST "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN ~/.env 2>/dev/null | cut -d= -f2)/sendMessage" \
  --data-urlencode "chat_id=$(grep TELEGRAM_HOME_CHANNEL ~/.env 2>/dev/null | cut -d= -f2)" \
  --data-urlencode "text=Azure VM deployed via Cloud Shell. IP: $IP — Hermes can SSH in now." >/dev/null
echo "[5/5] Done. IP texted to Hermes."
