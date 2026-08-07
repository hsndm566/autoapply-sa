#!/bin/bash
# ONE-COMMAND Azure deploy for HASSAN (Owner on 5974c845-...).
# Runs in Cloud Shell (Bash). Uses your already-signed-in session — no SP, no device code.
# Auto-tries allowed regions (UBT student subscription restricts regions).
set -e
SUB="5974c845-4443-4b80-a0cd-b83696573637"
RG="autoapply-rg"; VM="autoapply-vm"; USER="azureuser"
az account set --subscription "$SUB" >/dev/null

# SSH key
if [ ! -f ~/.ssh/autoapply_id_ed25519 ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/autoapply_id_ed25519 -N "" -q
fi
PUB=$(cat ~/.ssh/autoapply_id_ed25519.pub)

# Resource group (create once; ignore if exists)
az group create --name "$RG" --location "eastus" -o none 2>/dev/null || true

# Try allowed regions until one works
LOC=""
for CANDIDATE in eastus westeurope centralus southeastasia westus uaenorth; do
  echo "[*] Trying region: $CANDIDATE"
  if az vm create --resource-group "$RG" --name "$VM" --image Ubuntu2204 \
      --size Standard_B1s --admin-username "$USER" --ssh-key-value "$PUB" \
      --location "$CANDIDATE" -o none 2>/tmp/vmerr; then
    LOC="$CANDIDATE"
    echo "[ok] VM created in $LOC"
    break
  else
    echo "[fail $CANDIDATE]"; tail -2 /tmp/vmerr | head -c 200; echo
  fi
done

if [ -z "$LOC" ]; then
  echo "ERROR: no allowed region worked. Paste this output to Hermes."
  exit 1
fi

echo "[3/5] Auto-shutdown 23:00 UTC (free tier)..."
az vm auto-shutdown -g "$RG" -n "$VM" --time 2300 -o none
echo "[4/5] Get IP..."
IP=$(az vm show -g "$RG" -n "$VM" --show-details --query publicIps -o tsv)
echo "VM IP: $IP"
# notify Hermes (token/channel come from repo secret at deploy time; here we use a known channel)
curl -s -X POST "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN ~/.env 2>/dev/null | cut -d= -f2)/sendMessage" \
  --data-urlencode "chat_id=$(grep TELEGRAM_HOME_CHANNEL ~/.env 2>/dev/null | cut -d= -f2)" \
  --data-urlencode "text=Azure VM deployed via Cloud Shell in $LOC. IP: $IP — Hermes can SSH in now." >/dev/null
echo "[5/5] Done. IP texted to Hermes."
