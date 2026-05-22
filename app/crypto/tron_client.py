"""TRON / USDT-TRC20 blockchain client."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import aiohttp

from app.config import settings

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # mainnet USDT TRC20
USDT_CONTRACT_SHASTA = "TG3XXyExBkPp9nzdajDZsozEu4BkaSJozs"

TRONGRID_MAINNET = "https://api.trongrid.io"
TRONGRID_SHASTA = "https://api.shasta.trongrid.io"


class TronClient:
    def __init__(self) -> None:
        self._base = TRONGRID_MAINNET if settings.TRON_NETWORK == "mainnet" else TRONGRID_SHASTA
        self._contract = USDT_CONTRACT if settings.TRON_NETWORK == "mainnet" else USDT_CONTRACT_SHASTA
        self._headers = {"TRON-PRO-API-KEY": settings.TRON_API_KEY} if settings.TRON_API_KEY else {}

    async def get_trx_balance(self, address: str) -> Decimal:
        url = f"{self._base}/v1/accounts/{address}"
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        if data.get("data"):
            sun = data["data"][0].get("balance", 0)
            return Decimal(sun) / Decimal("1_000_000")
        return Decimal("0")

    async def get_usdt_balance(self, address: str) -> Decimal:
        """Return confirmed USDT-TRC20 balance."""
        url = f"{self._base}/v1/accounts/{address}"
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        if not data.get("data"):
            return Decimal("0")
        trc20_list = data["data"][0].get("trc20", [])
        for token_map in trc20_list:
            if self._contract in token_map:
                raw = int(token_map[self._contract])
                return Decimal(raw) / Decimal("1_000_000")
        return Decimal("0")

    async def get_incoming_usdt_tx(
        self, address: str, min_timestamp_ms: int = 0
    ) -> list[dict]:
        """Return incoming USDT-TRC20 transactions since min_timestamp_ms."""
        url = (
            f"{self._base}/v1/accounts/{address}/transactions/trc20"
            f"?contract_address={self._contract}&only_to=true&limit=20"
        )
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

        txs = []
        for tx in data.get("data", []):
            if int(tx.get("block_timestamp", 0)) < min_timestamp_ms:
                continue
            if tx.get("to") != address:
                continue
            txs.append({
                "tx_hash": tx["transaction_id"],
                "from_address": tx.get("from"),
                "to_address": tx.get("to"),
                "amount": Decimal(tx.get("value", "0")) / Decimal("1_000_000"),
                "block_timestamp": tx.get("block_timestamp"),
                "confirmed": True,  # TronGrid returns only confirmed TRC20 txs
                "confirmations": settings.USDT_TRC20_CONFIRMATIONS,  # treat as confirmed
            })
        return txs

    async def get_transaction(self, tx_hash: str) -> Optional[dict]:
        url = f"{self._base}/v1/transactions/{tx_hash}"
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return data.get("data", [None])[0]

    async def broadcast_transaction(self, signed_tx: dict) -> dict:
        url = f"{self._base}/wallet/broadcasttransaction"
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.post(url, json=signed_tx, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return await resp.json()
