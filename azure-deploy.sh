#!/usr/bin/env bash
# AutoApply Backend — Azure Student FREE-Tier Deploy (Hermes + Azure + GitHub, NO n8n)
# ONE script: paste into shell.azure.com → Enter → done.
# B1S VM = 750 hrs/mo FREE. Python backend + cron + SSH for Hermes remote control.

set -e
RG="autoapply-rg"
VM="autoapply-vm"
LOC="uaenorth"          # CHANGE if needed (e.g. eastus2)
USER="azureuser"
SUB="5974c845-4443-4b80-a0cd-b83696573637"   # your Azure Student subscription

echo "=== targeting subscription $SUB ==="
az account set --subscription "$SUB"

echo "[1/4] Resource group $RG in $LOC ..."
az group create --name "$RG" --location "$LOC" >/dev/null
echo "ok"

echo "[2/4] Ubuntu 22.04 VM (B1S = FREE 750hrs/mo) + cloud-init ..."
az vm create \
  --resource-group "$RG" \
  --name "$VM" \
  --image "Ubuntu2204" \
  --size "Standard_B1s" \
  --admin-username "$USER" \
  --generate-ssh-keys \
  --custom-data cloud-init.txt \
  --public-ip-address-dns-name "autoapply-hsans" \
  >/dev/null
echo "ok"

echo "[3/4] Firewall: SSH(22) only (no n8n/browserless) ..."
NSG="${VM}NSG"
az network nsg rule create --resource-group "$RG" --nsg-name "$NSG" --name "ssh" --priority 1100 --source-port-ranges 22 --access Allow >/dev/null
echo "ok"

echo "[4/4] Auto-shutdown @ 11pm UTC (free tier, no overnight burn) ..."
az vm auto-shutdown --resource-group "$RG" --name "$VM" --time 2300 >/dev/null
echo "ok"

echo ""
echo "=== DEPLOY COMPLETE (~\$0/mo within free tier) ==="
az vm show --resource-group "$RG" --name "$VM" --show-details --query "[publicIps]" -o tsv | tr -d '\n' | xargs -I{} echo "VM IP: {}"
echo ""
echo "SSH:  ssh $USER@VM_IP"
echo "Cron: nightly 23:00 UTC runs orchestrator.py (python backend)"
echo "Hermes: SSH key pre-injected -> I can restart/diagnose/edit remotely"
echo "Repo: github.com/hsndm566/autoapply-sa (source of truth, auto-pulled at boot)"
