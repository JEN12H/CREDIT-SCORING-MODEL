# AWS Free Tier Deployment Guide
**Project:** BAAKI Credit Scoring Model
**Architecture:** Monolith (Inference API + Scheduled Retraining)

This guide takes your exact code and puts it on the internet for free. It applies a **Swap File** trick to ensure your machine learning memory spikes do not intentionally crash your AWS Free Tier instance.

---

## Step 1: Create the AWS Server
1. Log in to your AWS Console and go to the **EC2 Dashboard**.
2. Click **Launch Instance**.
3. **Name:** `baaki-credit-api` (or any name you prefer).
4. **OS:** Choose **Ubuntu** (`Ubuntu Server 24.04 LTS`). Ensure the label says *"Free tier eligible"*.
5. **Instance Type:** Choose **t2.micro** (1 vCPU, 1 GB RAM).
6. **Key Pair:** Click **Create new key pair**, name it `aws-key`, and download the `.pem` file to your laptop.
7. **Network Settings:** Ensure you check **ALL THREE** boxes:
   - ✅ Allow SSH traffic
   - ✅ Allow HTTPS traffic from the internet
   - ✅ Allow HTTP traffic from the internet
8. **Storage:** Leave the default **8 GB** (you get up to 30 GB free, so 8 GB is perfect).
9. Click **Launch Instance**.

---

## Step 2: Connect to your Server
Wait about 2 minutes for the server to finish starting up. Get your server's Public IPv4 address from your AWS Dashboard.

Open your local terminal (Command Prompt, PowerShell, or Terminal) in the folder where your `aws-key.pem` downloaded, and run:

```bash
# Optional: Fix file permissions if you are using Mac/Linux
chmod 400 aws-key.pem 

# Connect to the server
ssh -i "aws-key.pem" ubuntu@<YOUR-AWS-PUBLIC-IP>
```

*(If it asks "Are you sure you want to continue connecting?", type `yes` and hit Enter).*

---

## Step 3: Add "Swap Memory" (Crucial for Machine Learning!)
Because your server only has 1 GB of RAM, running the monthly Random Forest training job will cause the server to crash. We must allocate 2GB of virtual memory from the SSD. 

Once logged into your Ubuntu server, paste these exact commands one by one:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
*Your server is now safe from Out-Of-Memory (OOM) crashes.*

---

## Step 4: Install Dependencies & Download Your Code
Run these commands to set up Python and pull your project:

```bash
# Update the server & install python tools
sudo apt update
sudo apt install python3-pip python3-venv git -y

# Clone your GitHub repository
git clone https://github.com/JEN12H/CREDIT-SCORING-MODEL.git
cd CREDIT-SCORING-MODEL

# Create a clean virtual environment
python3 -m venv .venv

# Activate it (you must do this every time you reconnect)
source .venv/bin/activate

# Install the Python requirements
pip install -r requirements.txt
```

---

## Step 5: Configure the Database (.env)
You need to pass your Turso credentials into the server.

```bash
nano .env
```
Paste in your credentials, exactly like your local computer:
```env
TURSO_URL=https://your-turso-database-url
TURSO_AUTH_TOKEN=your-long-turso-token
# Add your ADMIN_API_KEY and hugging face keys if you want them
```
*(To save and exit Nano: Press `Ctrl+O`, `Enter`, then `Ctrl+X`).*

---

## Step 6: Start the Server (Forever)
If you start the server normally, it will shut down the exact moment you close your laptop. We will use a tool called `tmux` to keep it running 24/7.

```bash
# 1. Open a background terminal session
tmux

# 2. Make sure you are in the project folder
cd CREDIT-SCORING-MODEL
source .venv/bin/activate

# 3. Start the FastApi application on PORT 80 (standard web port)
sudo .venv/bin/python -m uvicorn src.api.app:app --host 0.0.0.0 --port 80
```

### You're live!
Open a web browser and type in your AWS Public IP address: `http://<YOUR-AWS-PUBLIC-IP>`
You should see your health check JSON. Add `/docs` to the end of the URL to see your interactive API playground.

### How to disconnect securely:
Leave the server running by detaching from `tmux`:
1. Press `Ctrl + B`
2. Release everything.
3. Press `D`

You will return to the regular terminal, but your server will stay running forever! You can now type `exit` to close your connection.
