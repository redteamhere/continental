FROM python:3.11-slim

# System dependencies — build-essential + libc6-dev required for
# native extensions (ed25519-blake2b from bip-utils, bcrypt, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libc6-dev \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -u 1000 botuser

WORKDIR /app

# Dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create log directory
RUN mkdir -p /app/logs && chown botuser:botuser /app/logs

USER botuser

CMD ["python", "run_local.py"]
