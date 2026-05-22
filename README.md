# EscrowBot — Production Telegram Crypto Escrow

A production-grade Telegram bot for secure peer-to-peer cryptocurrency escrow transactions. Funds are held on-chain in unique per-deal wallets until the buyer confirms completion or an admin resolves a dispute.

---

## Features

### Core Escrow
- **Multi-currency support** — USDT (TRC20), BTC, ETH, LTC
- **HD wallet per deal** — BIP-44 derivation from master mnemonic; each deal gets a unique deposit address
- **On-chain monitoring** — Blockchain poller detects and confirms deposits automatically
- **Configurable fees** — Platform fee percentage deducted from released amount
- **Deadline enforcement** — Deals auto-expire; 24-hour expiry warning sent to both parties

### Deal Lifecycle
- Buyer creates deal → Seller accepts/declines → Buyer funds escrow wallet
- **📦 Mark as Delivered** — Seller taps this when work is done; buyer gets notified to release funds or dispute
- **✅ Release Funds** — Buyer confirms completion, funds go to seller (PIN-protected)
- **⚖️ Open Dispute** — Either party can escalate; admin reviews with evidence
- **⭐ Review system** — Buyer rates seller 1–5 stars after deal completes

### 💬 Private Deal Groups
- When a deal is funded, the bot automatically creates a **real private Telegram supergroup** for buyer and seller
- Both parties receive an invite link instantly via Telegram notification
- They can freely exchange messages, images, documents, and files inside the group
- The "💬 Deal Chat" button on any funded/active deal shows the join link
- Powered by **Telethon MTProto** — the bot creates the group using its own API credentials
- Group is named `🔒 Deal DEAL-XXXXXX` and persists for the lifetime of the deal

### Security
- **Visual PIN pad** (Trust Wallet-style) — inline numpad with dot progress indicator, or Telegram Mini App PIN screen
- **bcrypt PIN hashing** — cost factor 12; 5 failed attempts triggers 30-minute lockout
- **AES-256-GCM** encryption for all stored private keys
- PIN required for: deal creation, fund release, dispute opening
- Anti-phishing warning on every first contact
- Duplicate transaction protection via unique `tx_hash` index

### User Experience
- **Telegram Mini App PIN screen** — full-screen PIN entry (hosted on GitHub Pages); send data via `ReplyKeyboardMarkup` + `WebAppInfo`
- **Inline PIN fallback** — works without Web App URL configured
- **Bot command menu** — `/start` and `/help` for all users; `/admin` and `/sim_pay` scoped to admins only
- **Referral system** — users share a referral code on registration
- **Profile page** — shows stats: deals completed, total volume, reputation score, referral earnings

### Admin Panel
- List and resolve open disputes (full refund / release to seller / partial split / no action)
- User management — view stats, ban accounts
- Lookup any deal by number
- **`/sim_pay DEAL-XXXXXX`** — instantly simulate a crypto payment in `LOCAL_DEV` mode for testing

### Infrastructure
- **Aiogram 3** FSM with state-filtered handlers
- **FastAPI** webhook server + health endpoint
- **Nginx** TLS termination with Telegram IP allowlist
- **APScheduler** background workers for blockchain monitoring, expiry checks, deadline warnings
- **Alembic** migrations
- **Redis** FSM storage + rate limiting (falls back to MemoryStorage if unavailable)
- **Neon PostgreSQL** compatible (SSL handled via `connect_args`)

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

## Project Structure

```
continatial-bot/
├── app/
│   ├── main.py                     # FastAPI app + bot startup
│   ├── config.py                   # Settings (pydantic-settings)
│   ├── database.py                 # SQLAlchemy async engine
│   ├── models/
│   │   ├── user.py                 # User model + roles
│   │   ├── deal.py                 # Deal model + statuses + chat_group_id
│   │   ├── wallet.py               # Escrow wallet model
│   │   ├── transaction.py          # On-chain transaction records
│   │   ├── dispute.py              # Dispute + resolution
│   │   └── audit.py                # AuditLog, Review, Notification
│   ├── security/
│   │   ├── encryption.py           # AES-256-GCM (private key storage)
│   │   └── pin_manager.py          # bcrypt PIN + lockout (direct bcrypt, no passlib)
│   ├── crypto/
│   │   ├── wallet_generator.py     # BIP-44 HD wallet derivation
│   │   ├── tron_client.py          # USDT TRC20 monitoring
│   │   ├── eth_client.py           # ETH monitoring
│   │   ├── btc_client.py           # BTC + LTC via BlockCypher
│   │   └── monitor.py              # Unified blockchain poller
│   ├── services/
│   │   ├── user_service.py         # User CRUD + PIN verification
│   │   ├── deal_service.py         # Deal lifecycle
│   │   ├── escrow_service.py       # Wallet creation + fund release
│   │   ├── group_service.py        # Telegram supergroup creation (Telethon)
│   │   ├── notification_service.py # Telegram notifications
│   │   └── audit_service.py        # Immutable audit trail
│   ├── bot/
│   │   ├── middleware/             # Auth + rate limiting
│   │   ├── handlers/
│   │   │   ├── start.py            # /start, /help, registration + PIN submit
│   │   │   ├── profile.py          # Profile, stats, referrals
│   │   │   ├── deals.py            # Full deal lifecycle + PIN-protected actions
│   │   │   ├── deal_chat.py        # Deal chat group — join link handler
│   │   │   ├── payments.py         # Escrow address + QR code display
│   │   │   ├── disputes.py         # Dispute opening + evidence upload
│   │   │   ├── admin.py            # Admin panel + /sim_pay
│   │   │   └── pin_input.py        # Shared PIN pad digit/backspace + Mini App relay
│   │   ├── keyboards/
│   │   │   ├── main_menu.py        # Main menu inline keyboard
│   │   │   ├── deal_kb.py          # Deal action keyboards (incl. 💬 Deal Chat button)
│   │   │   ├── pin_kb.py           # PIN pad + Mini App button + dot indicators
│   │   │   └── admin_kb.py         # Admin panel keyboards
│   │   └── states/
│   │       ├── registration.py     # RegistrationStates
│   │       ├── deal_creation.py    # DealCreationStates
│   │       ├── deal_chat.py        # DealChatState (reserved)
│   │       └── dispute.py          # AdminResolveStates
│   ├── workers/
│   │   ├── scheduler.py            # APScheduler job definitions
│   │   ├── blockchain_monitor.py   # Payment notification worker
│   │   └── deal_expiry.py          # Expiry + deadline warnings
│   └── api/
│       └── routes/                 # webhook.py, health.py
├── migrations/
│   ├── env.py                      # Alembic async config
│   └── versions/
│       ├── 001_initial_schema.py   # Full initial schema
│       └── 002_deal_chat_group.py  # chat_group_id + chat_invite_link columns
├── webapp/
│   └── pin.html                    # Telegram Mini App PIN screen (host on GitHub Pages)
├── nginx/nginx.conf                # TLS + IP allowlist
├── scripts/
│   ├── generate_keys.py            # Generate SECRET_KEY, ENCRYPTION_KEY, mnemonic
│   ├── setup.sh                    # One-shot deployment script
│   └── backup.sh                   # Daily DB backup
├── run_local.py                    # Local polling-mode runner (no Docker needed)
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
  ├─── Set PIN (Mini App / pad)─►│                             │
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
  │◄── 💬 Private group invite ─┤──── 💬 Private group ──────►│
  │    (Telegram supergroup)    │    (real Telegram group)    │
  │                             │                             │
  │   [seller fulfils deal]     │                             │
  │                             │◄── 📦 Mark as Delivered ────┤
  │◄── Seller marked delivered ─┤                             │
  │                             │                             │
  ├─── Release Funds ──────────►│ (PIN verification)          │
  │                             │──── Funds released ────────►│
  │                             │                             │
  ├─── ⭐ Leave review ─────────►│                             │
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

## Quick Start (Local Development)

No Docker required. Runs on Windows, Linux, or macOS.

### 1. Clone and create virtualenv

```bash
git clone https://github.com/redteamhere/continental.git
cd continental
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values. Minimum required for local dev:

```env
BOT_TOKEN=7123456789:AAxxxxxxxxxxxx
ADMIN_IDS=123456789
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
LOCAL_DEV=true
```

### 3. Run the bot

```bash
python run_local.py
```

The runner:
- Creates all DB tables automatically
- Runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for any new columns
- Falls back to `MemoryStorage` if Redis is unavailable
- Uses polling mode (no webhook/domain needed)
- Registers the bot command menu in Telegram on startup

### 4. Simulate a payment (LOCAL_DEV only)

Once a deal is in `awaiting_payment` status, run:

```
/sim_pay DEAL-A1B2C3
```

This instantly marks the deal as FUNDED and notifies both parties, skipping the real blockchain step. Also triggers private group creation.

---

## Production Deployment

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
nano .env
```

### 4. SSL certificates

```bash
certbot certonly --standalone -d your_domain.com
cp /etc/letsencrypt/live/your_domain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/your_domain.com/privkey.pem nginx/ssl/
```

Update `nginx/nginx.conf` with your domain.

### 5. Deploy

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Or manually:

```bash
docker compose up -d postgres redis
docker compose run --rm migrate
docker compose up -d bot nginx
docker compose logs -f bot
```

---

## Optional Features Setup

### PIN Mini App (Visual PIN Screen)

Host `webapp/pin.html` on GitHub Pages (or any HTTPS URL):

1. Push to a public GitHub repo
2. Enable GitHub Pages on the `main` branch
3. Set in `.env`:
   ```env
   WEB_APP_URL=https://yourusername.github.io/yourrepo/webapp/pin.html
   ```

Users will see a full-screen PIN entry interface instead of the inline numpad.

> **Note:** `Telegram.WebApp.sendData()` only works from a `ReplyKeyboardMarkup` + `KeyboardButton(web_app=...)` — not from an inline keyboard button. The code uses the correct button type.

### Private Deal Groups (Telethon MTProto)

To enable automatic private group creation when deals are funded:

1. Go to [my.telegram.org/apps](https://my.telegram.org/apps)
2. Log in with your phone number
3. Create an application — copy `api_id` and `api_hash`
4. Add to `.env`:
   ```env
   TELEGRAM_API_ID=12345678
   TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
   ```

When a deal is funded, the bot automatically:
- Creates a private Telegram supergroup named `🔒 Deal DEAL-XXXXXX`
- Generates an invite link
- Sends the link to both buyer and seller

If `TELEGRAM_API_ID` is not set, the "💬 Deal Chat" button will display "group still being created" and retry.

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs of admins |
| `DATABASE_URL` | ✅ | PostgreSQL asyncpg connection string |
| `SECRET_KEY` | ✅ | 64-char hex random string |
| `ENCRYPTION_KEY` | ✅ | 64-char hex AES-256 key for private key storage |
| `MASTER_MNEMONIC` | ✅ | 24-word BIP-39 mnemonic (controls all escrow wallets) |
| `REDIS_URL` | ✅ | Redis connection string (FSM + rate limiting) |
| `BOT_WEBHOOK_URL` | prod | Your HTTPS domain |
| `TRON_API_KEY` | prod | TronGrid API key (USDT TRC20) |
| `ETH_RPC_URL` | prod | Infura/Alchemy RPC endpoint |
| `BLOCKCYPHER_TOKEN` | prod | BlockCypher API token (BTC/LTC) |
| `TELEGRAM_API_ID` | optional | MTProto API ID for deal group creation |
| `TELEGRAM_API_HASH` | optional | MTProto API hash for deal group creation |
| `WEB_APP_URL` | optional | HTTPS URL for the Mini App PIN screen |
| `LOCAL_DEV` | dev | `true` to skip blockchain calls and enable `/sim_pay` |
| `ESCROW_FEE_PERCENT` | — | Platform fee % (default: 1.5) |
| `MIN_DEAL_AMOUNT_USD` | — | Minimum deal value in USD (default: 10) |
| `MAX_DEAL_AMOUNT_USD` | — | Maximum deal value in USD (default: 100,000) |

See [`.env.example`](.env.example) for the full list.

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Telegram accounts, PIN hash, reputation, stats |
| `deals` | Escrow agreements with status machine + `chat_group_id`, `chat_invite_link` |
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
- **bcrypt** with cost factor 12 (direct `bcrypt` library — no passlib wrapper)
- **5 failed attempts → 30-minute lockout**
- PIN entry via inline numpad or Telegram Mini App
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
| Simulate payment | `/sim_pay DEAL-XXXXXX` (LOCAL_DEV only) |

---

## Migrations

Run after any schema change:

```bash
alembic upgrade head
```

Current migrations:
- `001_initial_schema` — full initial schema
- `002_deal_chat_group` — adds `chat_group_id` and `chat_invite_link` to `deals`

In local dev, `run_local.py` auto-applies `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on startup so you don't need to run Alembic manually.

---

## Adding New Currencies

1. Add value to `Currency` enum in `app/models/deal.py`
2. Add `Chain` mapping in `app/crypto/wallet_generator.py`
3. Create a client in `app/crypto/` (follow `btc_client.py` pattern)
4. Add a `_check_<chain>` method in `app/crypto/monitor.py`
5. Add confirmation count to `app/config.py`
6. Run `alembic revision --autogenerate -m "add_<currency>"` + `alembic upgrade head`

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

## Security Recommendations for Production

1. **Store `MASTER_MNEMONIC` in a Hardware Security Module (HSM)** or secret manager (AWS Secrets Manager, HashiCorp Vault) — not in a plain `.env` file
2. **Regular key rotation** for `ENCRYPTION_KEY` with re-encryption of stored private keys
3. **Database encryption at rest** (PostgreSQL with encrypted volumes)
4. **VPN/private network** between all Docker containers — never expose DB or Redis publicly
5. **Monitor `audit_logs`** for anomalies (unusual ban rates, high dispute frequency from one user)
6. **Set up alerts** on failed blockchain transactions and stuck deals
7. **Cold wallet architecture** — sweep escrowed funds to a cold multisig after confirmation, hold only what's needed for active deals in hot wallets
8. **Legal compliance** — consult a lawyer about escrow licensing requirements in your jurisdiction before operating
