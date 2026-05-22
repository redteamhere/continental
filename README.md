# EscrowBot — Production Telegram Crypto Escrow

A production-grade Telegram bot for secure peer-to-peer cryptocurrency escrow transactions. Funds are held on-chain in unique per-deal wallets until the buyer confirms completion or an admin resolves a dispute.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Telegram Users                     │
└────────────────────────┬────────────────────────────┘
                         │ HTTPS webhook
                    ┌────▼────┐
                    │  Nginx  │  TLS termination
                    │  :443   │  IP allowlist (Telegram IPs)
                    └────┬────┘
                         │
                    ┌────▼────────────────┐
                    │   FastAPI + Aiogram  │  Bot logic
                    │   (uvicorn :8000)   │  FSM handlers
                    └─┬──────────┬────────┘
                      │          │
            ┌─────────▼──┐  ┌───▼──────────┐
            │ PostgreSQL  │  │    Redis      │
            │  (data)     │  │  (FSM/cache) │
            └─────────────┘  └──────────────┘
                      │
            ┌─────────▼──────────────────────┐
            │     Background Scheduler        │
            │  • Blockchain monitor (60s)     │
            │  • Deal expiry check (30m)      │
            │  • Deadline warnings (1h)       │
            │  • Payment notifications (30s)  │
            └────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
    TronGrid      Etherscan    BlockCypher
  (USDT TRC20)    (ETH)       (BTC / LTC)
```

---

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose
- A domain with HTTPS (for webhook mode)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- API keys: TronGrid, Infura/Alchemy (ETH), BlockCypher (BTC/LTC)

### 2. Generate secrets

```bash
pip install bip-utils==2.9.3
python scripts/generate_keys.py
```

Copy the output into your `.env` file.

### 3. Configure environment

```bash
cp .env.example .env
nano .env          # Fill in ALL required values
```

**Required fields:**

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `SECRET_KEY` | 64-char hex random string |
| `ENCRYPTION_KEY` | 64-char hex key for AES-256 wallet encryption |
| `MASTER_MNEMONIC` | 24-word BIP-39 mnemonic (controls all wallets) |
| `POSTGRES_PASSWORD` | Strong database password |
| `REDIS_PASSWORD` | Strong Redis password |
| `ADMIN_IDS` | Comma-separated Telegram IDs of admins |
| `BOT_WEBHOOK_URL` | Your HTTPS domain (e.g. `https://bot.example.com`) |
| `TRON_API_KEY` | TronGrid API key |
| `ETH_RPC_URL` | Infura/Alchemy RPC endpoint |
| `BLOCKCYPHER_TOKEN` | BlockCypher API token |

### 4. SSL certificates

Place your SSL certificate and key in `nginx/ssl/`:
```
nginx/ssl/fullchain.pem
nginx/ssl/privkey.pem
```

Using Let's Encrypt:
```bash
certbot certonly --standalone -d your_domain.com
cp /etc/letsencrypt/live/your_domain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/your_domain.com/privkey.pem nginx/ssl/
```

Update `nginx/nginx.conf` — replace `your_domain.com` with your actual domain.

### 5. Deploy

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Or manually:

```bash
# Start infrastructure
docker compose up -d postgres redis

# Run migrations
docker compose run --rm migrate

# Start app + nginx
docker compose up -d bot nginx

# View logs
docker compose logs -f bot
```

---

## Project Structure

```
continatial-bot/
├── app/
│   ├── main.py                  # FastAPI app + bot startup
│   ├── config.py                # Settings (pydantic-settings)
│   ├── database.py              # SQLAlchemy async engine
│   ├── models/
│   │   ├── user.py              # User model + roles
│   │   ├── deal.py              # Deal model + statuses
│   │   ├── wallet.py            # Escrow wallet model
│   │   ├── transaction.py       # On-chain transaction records
│   │   ├── dispute.py           # Dispute + resolution
│   │   └── audit.py             # AuditLog, Review, Notification
│   ├── security/
│   │   ├── encryption.py        # AES-256-GCM (private key storage)
│   │   └── pin_manager.py       # bcrypt PIN + lockout
│   ├── crypto/
│   │   ├── wallet_generator.py  # BIP-44 HD wallet derivation
│   │   ├── tron_client.py       # USDT TRC20 monitoring
│   │   ├── eth_client.py        # ETH monitoring
│   │   ├── btc_client.py        # BTC + LTC via BlockCypher
│   │   └── monitor.py           # Unified blockchain poller
│   ├── services/
│   │   ├── user_service.py      # User CRUD + PIN verification
│   │   ├── deal_service.py      # Deal lifecycle
│   │   ├── escrow_service.py    # Wallet creation + fund release
│   │   ├── notification_service.py  # Telegram notifications
│   │   └── audit_service.py     # Immutable audit trail
│   ├── bot/
│   │   ├── middleware/          # Auth + rate limiting
│   │   ├── handlers/            # start, profile, deals, payments,
│   │   │                        #   disputes, admin
│   │   ├── keyboards/           # Inline keyboard builders
│   │   └── states/              # FSM state groups
│   ├── workers/
│   │   ├── scheduler.py         # APScheduler job definitions
│   │   ├── blockchain_monitor.py # Payment notification worker
│   │   └── deal_expiry.py       # Expiry + deadline warnings
│   └── api/
│       └── routes/              # webhook.py, health.py
├── migrations/
│   ├── env.py                   # Alembic async config
│   └── versions/001_initial_schema.py
├── nginx/nginx.conf             # TLS + IP allowlist
├── scripts/
│   ├── generate_keys.py         # Generate SECRET_KEY, ENCRYPTION_KEY, mnemonic
│   ├── setup.sh                 # One-shot deployment script
│   └── backup.sh                # Daily DB backup
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Deal Flow

```
Buyer                          Bot                         Seller
  │                             │                             │
  ├─── /start ─────────────────►│                             │
  ├─── Set PIN ────────────────►│                             │
  │                             │                             │
  ├─── New Deal ───────────────►│                             │
  │    (seller, amount, desc)   │◄── Deal request ────────────┤
  │                             │                             │
  │                             │◄── Accept ──────────────────┤
  │◄── Pay to address ──────────┤                             │
  │                             │                             │
  ├─── [sends crypto] ─────────►│ (blockchain monitor polls)  │
  │                             │                             │
  │◄── Payment confirmed ───────┤──── Funds locked ──────────►│
  │                             │                             │
  │   [seller fulfils deal]     │                             │
  │                             │                             │
  ├─── Release funds ──────────►│                             │
  │    (PIN verification)       │──── Funds released ────────►│
  │                             │                             │
  ├─── Leave review ───────────►│                             │
```

---

## Dispute Flow

```
Party ──► Open Dispute ──► Upload evidence
                 │
                 ▼
         Admin notified (all ADMIN_IDS)
                 │
                 ▼
         /admin → Disputes → Select dispute
                 │
                 ▼
         Admin resolves:
           • Full refund to buyer
           • Release to seller
           • Partial split (X%/Y%)
           • No action
                 │
                 ▼
         Both parties notified
         Audit log entry written
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Telegram accounts, PIN hash, reputation, stats |
| `deals` | Escrow agreements with status machine |
| `wallets` | Per-deal HD wallets (encrypted private keys) |
| `transactions` | On-chain deposit records, confirmation tracking |
| `disputes` | Dispute cases with evidence and resolution |
| `reviews` | Post-deal ratings (1–5 stars) |
| `audit_logs` | Immutable append-only action log |
| `notifications` | Notification records per user |

---

## Security Architecture

### Private Key Protection
- All private keys encrypted with **AES-256-GCM** before database storage
- Decrypted only within the signing function scope, immediately `del`-ed after
- Master mnemonic stored only in environment variable (never in DB)
- HD wallet derivation: `m/44'/<coin>'/0'/0/<deal_id>` — reproducible from mnemonic

### PIN Protection
- **bcrypt** with cost factor 12
- **5 failed attempts → 30-minute lockout**
- PIN messages deleted from chat immediately
- Required before: deal creation, fund release, dispute opening

### Rate Limiting
- Redis sliding window: 30 requests/minute per user
- Max 10 deals created per user per day
- Applied at middleware level before handler execution

### Anti-Fraud
- Duplicate transaction prevention via unique `tx_hash` index
- Partial payment detection (balance tracking per wallet)
- Anti-phishing warning in every welcome message
- Banned user check on every interaction

### Infrastructure
- Nginx IP allowlist restricts webhook to Telegram IP ranges only
- Non-root Docker user
- TLS 1.2/1.3 only, HSTS enabled
- Security headers (X-Frame-Options, CSP, etc.)
- Immutable audit log (append-only, no UPDATE/DELETE)

---

## Admin Commands

| Action | How |
|--------|-----|
| Open admin panel | `/admin` (admin/moderator only) |
| Review disputes | Admin panel → Open Disputes |
| Ban user | Admin panel → Users → Ban |
| View statistics | Admin panel → Statistics |
| Lookup deal | Admin panel → Lookup Deal |

---

## Environment Variables Reference

See [`.env.example`](.env.example) for the full list with descriptions.

---

## Backup & Recovery

**Daily backup** (add to crontab):
```bash
0 2 * * * /path/to/continatial-bot/scripts/backup.sh >> /var/log/escrow_backup.log 2>&1
```

**Restore:**
```bash
gunzip -c backups/escrow_bot/db_20240101_020000.sql.gz | \
  docker compose exec -T postgres psql -U escrow_user -d escrow_bot
```

---

## Adding New Currencies

1. Add value to `Currency` enum in `app/models/deal.py`
2. Add `Chain` mapping in `app/crypto/wallet_generator.py`
3. Create a client in `app/crypto/` (follow `btc_client.py` pattern)
4. Add a `_check_<chain>` method in `app/crypto/monitor.py`
5. Add confirmation count to `app/config.py`
6. Run `alembic revision --autogenerate -m "add_<currency>"` + `alembic upgrade head`

---

## Security Recommendations for Production

1. **Store `MASTER_MNEMONIC` in a Hardware Security Module (HSM)** or secret manager (AWS Secrets Manager, HashiCorp Vault) — not in a plain `.env` file
2. **Regular key rotation** for `ENCRYPTION_KEY` with re-encryption of stored private keys
3. **Database encryption at rest** (PostgreSQL with encrypted volumes)
4. **VPN/private network** between all Docker containers — never expose DB or Redis publicly
5. **Monitor `audit_logs`** for anomalies (unusual ban rates, high dispute frequency from one user)
6. **Set up alerts** on failed blockchain transactions and stuck deals
7. **Cold wallet architecture** — sweep escrowed funds to a cold multisig after confirmation, hold only what's needed for active deals in hot wallets
8. **Legal compliance** — consult a lawyer about escrow licensing requirements in your jurisdiction before operating
