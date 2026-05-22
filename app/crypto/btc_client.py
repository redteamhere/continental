"""Bitcoin and Litecoin blockchain client via BlockCypher API."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import aiohttp

from app.config import settings

BLOCKCYPHER_BASE = "https://api.blockcypher.com/v1"


class BlockClient:
    """Handles BTC and LTC via BlockCypher REST API."""

    COIN_SLUG = {
        "BTC": "btc/main",
        "LTC": "ltc/main",
    }

    def __init__(self, coin: str) -> None:
        self._coin = coin
        self._slug = self.COIN_SLUG[coin]
        self._token = settings.BLOCKCYPHER_TOKEN

    def _url(self, path: str) -> str:
        base = f"{BLOCKCYPHER_BASE}/{self._slug}{path}"
        if self._token:
            sep = "&" if "?" in base else "?"
            base = f"{base}{sep}token={self._token}"
        return base

    async def get_balance(self, address: str) -> Decimal:
        url = self._url(f"/addrs/{address}/balance")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        satoshis = data.get("final_balance", 0)
        return Decimal(satoshis) / Decimal("100_000_000")

    async def get_unconfirmed_balance(self, address: str) -> Decimal:
        url = self._url(f"/addrs/{address}/balance")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        satoshis = data.get("unconfirmed_balance", 0)
        return Decimal(satoshis) / Decimal("100_000_000")

    async def get_transactions(self, address: str) -> list[dict]:
        """Return confirmed and unconfirmed incoming transactions."""
        url = self._url(f"/addrs/{address}/full?limit=50")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        results = []
        for tx in data.get("txs", []):
            # Check if this address is in the outputs
            for output in tx.get("outputs", []):
                if address in output.get("addresses", []):
                    satoshis = output.get("value", 0)
                    confirmations = tx.get("confirmations", 0)
                    results.append({
                        "tx_hash": tx["hash"],
                        "from_address": None,  # UTXO model — multiple inputs
                        "to_address": address,
                        "amount": Decimal(satoshis) / Decimal("100_000_000"),
                        "confirmations": confirmations,
                        "block_height": tx.get("block_height"),
                        "confirmed": confirmations > 0,
                    })
        return results

    async def get_transaction(self, tx_hash: str) -> Optional[dict]:
        url = self._url(f"/txs/{tx_hash}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()

    async def get_chain_height(self) -> int:
        url = self._url("")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        return data.get("height", 0)
