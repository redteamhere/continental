#!/bin/bash
set -euo pipefail

echo "=== EscrowBot Setup ==="

# Check dependencies
command -v docker &>/dev/null || { echo "Docker not found"; exit 1; }
command -v docker compose &>/dev/null || { echo "docker compose not found"; exit 1; }

# Copy env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — EDIT IT NOW with your real values before continuing."
    echo "Required: BOT_TOKEN, ENCRYPTION_KEY, SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD"
    exit 0
fi

# Generate master mnemonic if not set
if ! grep -q "^MASTER_MNEMONIC=" .env 2>/dev/null; then
    echo ""
    echo "⚠️  MASTER_MNEMONIC not found in .env"
    echo "Generating a new HD wallet mnemonic..."
    MNEMONIC=$(python -c "from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum; print(Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24))")
    echo ""
    echo "=== YOUR MASTER MNEMONIC (SAVE THIS SECURELY OFFLINE) ==="
    echo "$MNEMONIC"
    echo "=========================================================="
    echo ""
    echo "MASTER_MNEMONIC=$MNEMONIC" >> .env
    echo "Mnemonic saved to .env — back it up securely NOW."
fi

# Create SSL directory
mkdir -p nginx/ssl

echo ""
echo "=== Starting services ==="
docker compose up -d postgres redis
echo "Waiting for database..."
sleep 5

echo "Running migrations..."
docker compose run --rm migrate

echo "Starting bot..."
docker compose up -d bot nginx

echo ""
echo "=== Done ==="
echo "Bot is running. Check logs with: docker compose logs -f bot"
