# Deploy SafePassage on AWS EC2

This guide deploys the API and static UI as one Docker container. It creates AWS resources, which can incur charges. Do not start until you have set a budget and alarm.

## 1. Secure the account and set spending alerts first

1. Create/sign in to your AWS account using a unique password and MFA.
2. In **Billing and Cost Management**, create a monthly AWS Budget with a low amount that you choose, and add email alerts at early thresholds (for example, 50%, 80%, and 100%).
3. Create a billing alarm/notification as available for your account and region. Confirm the alert email address.
4. Before choosing an instance, open the AWS Free Tier/Free Plan pages in the console and verify the current offer, eligible instance types, monthly hours, region restrictions, account eligibility, and expiration. AWS offers and labels change; do not assume an instance is free for your account.

## 2. Launch a small EC2 instance

1. Choose an Ubuntu LTS AMI and an instance type shown as eligible by your account's current offer. For this 17,787-node dataset, choose enough memory for Docker and the Python process; validate actual RAM and current pricing in the console.
2. Create or select an SSH key pair and store the private key securely. Do not upload it to this repository.
3. Create a security group with inbound rules:
   - SSH (TCP 22) from **My IP** only.
   - HTTP (TCP 80) from `0.0.0.0/0` and `::/0` if serving a public website.
   - HTTPS (TCP 443) from `0.0.0.0/0` and `::/0` if using a domain and TLS.
   - Do not open port 8000 to the internet. Compose binds it to the host loopback interface.
4. Review the instance type, storage size, public IPv4 option, security group, and estimated charges before launch.

## 3. Install Docker and start the app

Connect from PowerShell using the downloaded key (replace the placeholders):

```powershell
ssh -i .\your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

On the instance, install Docker using the current official Docker Engine instructions for Ubuntu, then enable/start Docker and verify `docker --version` and `docker compose version`. Package repository instructions can change; follow Docker's official documentation for the current Ubuntu release.

Clone your GitHub repository and start SafePassage:

```bash
git clone YOUR_REPOSITORY_URL
cd SafePassage
cp .env.example .env
nano .env
sudo docker compose up --build -d
sudo docker compose ps
sudo docker compose logs --tail=100 safepassage
```

Set a suitable tile provider URL, attribution, and restricted provider key in `.env` before public use. A browser tile API key is visible to visitors, so restrict it to your domain/referrer and only the required tile APIs. Do not commit `.env`. Check the provider's current free-plan eligibility, usage limits, caching rules, attribution terms, and commercial/public-use restrictions.

For a private smoke check without opening port 8000 publicly, create an SSH tunnel from your computer:

```powershell
ssh -i .\your-key.pem -L 8000:127.0.0.1:8000 ubuntu@YOUR_EC2_PUBLIC_IP
```

Then browse to `http://127.0.0.1:8000` on your computer. For a public deployment, use the reverse proxy below.

## 4. Optional Caddy reverse proxy with HTTPS

Point a domain's DNS A record (and AAAA record only if IPv6 is configured) to the instance. Install Caddy from its official Ubuntu package instructions. Create `/etc/caddy/Caddyfile`:

```caddy
route.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Replace `route.example.com` with your domain, ensure inbound 80/443 are allowed, then validate and reload Caddy using its service commands. Caddy obtains and renews TLS certificates automatically when DNS and ports are reachable. Verify the certificate and HTTPS route before sharing the site. If serving from a different web origin, set `CORS_ORIGINS` to that exact origin; same-origin is the default.

## 5. Update the application

SSH into the instance, then run:

```bash
cd SafePassage
git pull
sudo docker compose up --build -d
sudo docker compose ps
sudo docker compose logs --tail=100 safepassage
```

Keep `.env` outside version control and review the new release notes before updating. Back up any configuration you need; this project stores no user data or route history.

## 6. Stop or terminate resources to prevent charges

To stop the app container while leaving the EC2 instance allocated:

```bash
sudo docker compose down
```

Stopping an instance does not necessarily stop charges for attached storage, allocated public IPv4 addresses, snapshots, or other resources. To stop compute charges where applicable, stop the EC2 instance in the console. To remove ongoing instance/storage charges, back up what you need and **terminate** the instance, then check and delete unattached EBS volumes, snapshots, Elastic IP addresses, load balancers, DNS zones, and any other resources you created. Verify the Billing dashboard afterward. Termination is destructive.

## Costs to check

- EC2 compute, EBS volumes and snapshots, public IPv4 addresses, data transfer, and regional differences.
- A domain name, DNS hosted zone/queries, and certificate-related services if separately billed.
- Tile provider usage beyond its free allowance.
- Email/SMS notifications and any additional cloud services.
- Taxes and charges after a free offer expires or eligibility limits are exceeded.

Always confirm current prices and free-offer terms in the AWS console before launch. No AWS resources were created for this guide.
