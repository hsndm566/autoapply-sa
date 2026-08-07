# 🔑 YOUR ONE-TIME AUTH (then I automate everything)

## Step 1: Register Cloud Shell (browser, 1 min)
portal.azure.com → Subscriptions → `5974c845-...` → Settings → Resource Providers → `Microsoft.CloudShell` → **Register**

## Step 2: Create the deploy credential (Cloud Shell, Bash — ONE command)
After Cloud Shell opens, paste this:
```
az ad sp create-for-rbac --name autoapply-deployer --role contributor --scopes /subscriptions/5974c845-4443-4b80-a0cd-b83696573637 --sdk-auth
```
It prints a **JSON blob**. Copy ALL of it.

## Step 3: Paste the JSON to me (or add as GitHub secret)
- Easiest: paste the JSON in this chat. I'll store it as the `AZURE_CREDENTIALS` repo secret via API.
- Or: GitHub repo → Settings → Secrets → `AZURE_CREDENTIALS` → paste JSON.

## Step 4: I trigger the deploy (you do nothing)
I click "Run workflow" on the `Deploy Azure Backend` action. GitHub Actions:
1. Logs in with your SP (no human)
2. Creates the B1S VM + resource group
3. Runs cloud-init (Python backend + cron + SSH key inject)
4. Texts you the VM IP via Telegram
5. I SSH in remotely to verify + wire control

## After that: fully automated, forever
- New workflows/code → I push to repo → VM syncs at reboot
- Need a redeploy → I click Run workflow (no Azure login needed)
- Cost: $0 (free tier, auto-shutdown 11pm UTC)

## Your only hands-on actions, ever:
1. Register Cloud Shell (once)
2. Run the `az ad sp create-for-rbac` command (once)
3. Paste me the JSON (once)
That's it. No more steps.
