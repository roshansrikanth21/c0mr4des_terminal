# Run the paper autopilot 24/7 for free (Oracle Cloud + Telegram alerts)

The server runs the backend all day and sends you messages on your phone:
- every paper **entry** and **exit**, with P&L after charges
- **Shock mode** on crash, VIX-spike and war/disaster-headline days
- a **daily summary** at 15:35 (per-strategy scoreboard)

Paper only. `LIVE_TRADING` stays `false`.

## 1. Telegram bot (5 minutes)
1. In Telegram, open **@BotFather**, send `/newbot`, pick a name, and copy the **token** it gives you.
2. Open your new bot and send it any message, e.g. `hi`.
3. In a browser, open `https://api.telegram.org/bot<TOKEN>/getUpdates`. Find `"chat":{"id": 123456789` and copy that number. That's your **chat id**.

## 2a. Free server for students (Azure for Students - no credit card)
1. Go to https://azure.microsoft.com/free/students and sign in with your **college email**. You get $100 credit, renewable yearly while enrolled.
2. Go to **Create a resource → Virtual machine**:
   - Region: **Central India** (or South India)
   - Image: **Ubuntu Server 24.04 LTS**
   - Size: **B1s** (1 vCPU, 1 GB). The setup script adds swap so this is enough.
   - Authentication: **SSH public key**, *Generate new key pair*, then download the `.pem` when asked.
   - Inbound ports: **SSH (22) only**.
3. After **Review + create** finishes, copy the VM's **Public IP address**. The username is the one you chose (default `azureuser`).
4. Continue at step 3 below, using `azureuser@<ip>` instead of `ubuntu@<ip>`.

## 2b. Free server (Oracle Cloud Always Free)
1. Sign up at https://www.oracle.com/cloud/free/. A card is needed for verification; Always Free resources are not charged. Pick **Mumbai** or **Hyderabad** as the home region.
2. Go to **Compute → Instances → Create instance**:
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere (VM.Standard.A1.Flex)**, 1 OCPU, 6 GB RAM. That's well inside the free limits.
   - SSH keys: download the private key it offers, or paste your own public key.
3. Don't open any extra ports. SSH (22) is all you need.
4. Connect from your PC (PowerShell): `ssh -i path\to\key ubuntu@<server-ip>`

## 3. Install (one time, on the server)
```bash
git clone -b lean-core https://github.com/roshansrikanth21/c0mr4des_terminal.git
cd c0mr4des_terminal
cp backend/.env.example backend/.env && chmod 600 backend/.env
nano backend/.env        # set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; leave LIVE_TRADING=false
bash deploy/setup_ubuntu.sh
curl -X POST http://127.0.0.1:8100/api/notify/test   # you should get a Telegram message
```
The service starts on boot and restarts itself if it crashes.

## 4. See the dashboard from your PC (private tunnel)
The API has no login, so it only listens on the server's localhost. Tunnel to it:
```bash
ssh -i path\to\key -L 8100:127.0.0.1:8100 ubuntu@<server-ip>
```
Leave that window open and browse to **http://localhost:8100**. Phone access: install **Tailscale** (free) on the server and your phone, then open `http://<tailscale-ip>:8100` after changing `--host 127.0.0.1` to the Tailscale IP in `/etc/systemd/system/c0mr4des.service`.

## Day to day
| What | Command (on the server) |
|---|---|
| Live logs | `journalctl -u c0mr4des -f` |
| Restart | `sudo systemctl restart c0mr4des` |
| Update to latest code | `git pull && npm ci && npm run build && .venv/bin/pip install -r backend/requirements.txt && sudo systemctl restart c0mr4des` |
| Paper trades file | `data/paper_trades.json` |

## Alternatives
- **Your own PC**: `start.bat` works the same, but the PC has to stay on and awake 09:10–15:40.
- **Google Cloud free e2-micro**: also always-free, but US regions only and 1 GB RAM. Workable, slower.
- **Render/Railway free tiers**: avoid. They sleep when idle and would miss trades.
