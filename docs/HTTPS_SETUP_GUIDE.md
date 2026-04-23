# HTTPS Setup Guide (Nginx + Certbot + Subdomain)

This guide secure your BAAKI Credit Scoring API with HTTPS. Follow these steps once you are ready to move from HTTP to a production-ready secure connection.

---

## Phase 1: Coordinate with Frontend Team
Since your frontend team manages the domain, you need them to create a **subdomain** for your API.

### 1. Send this message to your Frontend Team:
> Hi Team, 
> I need a subdomain created to host our Credit Scoring API on AWS. Could you please add the following **DNS A Record**?
> - **Record Type:** A
> - **Host/Name:** api (this will make it `api.yourdomain.com`)
> - **Points to:** [INSERT_YOUR_AWS_PUBLIC_IP_HERE]
> - **TTL:** Auto

### 2. Update AWS Security Group
Go to your **AWS EC2 Dashboard** -> **Security Groups** -> **Inbound Rules**.
Ensure you have a rule for:
- **Type:** HTTPS
- **Protocol:** TCP
- **Port Range:** 443
- **Source:** 0.0.0.0/0

---

## Phase 2: Server Configuration (Run on EC2)
Once the subdomain is pointing to your IP, SSH into your server and run these commands:

### 1. Install Nginx and Certbot
```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y
```

### 2. Create Nginx Config
```bash
sudo nano /etc/nginx/sites-available/baaki-api
```
Paste this inside (Replace `api.yourdomain.com` with your actual subdomain):
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
*Save: `Ctrl+O`, `Enter`. Exit: `Ctrl+X`.*

### 3. Enable and Restart
```bash
sudo ln -s /etc/nginx/sites-available/baaki-api /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

### 4. Get the SSL Certificate
```bash
sudo certbot --nginx -d api.yourdomain.com
```
*Choose `2` to redirect all HTTP traffic to HTTPS.*

---

## Phase 3: Start the API
Now that Nginx is handling port 80 and 443, you must run FastAPI on port 8000.

### 1. Update Startup Command
```bash
tmux
source .venv/bin/activate
# Use --proxy-headers so FastAPI knows it is secure
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --proxy-headers
```

### 2. Update Environment Variables
Edit your `.env` file to allow your frontend domain in CORS:
```env
CORS_ORIGINS=https://your-frontend-domain.com,https://api.yourdomain.com
```
