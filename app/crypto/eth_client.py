"""Ethereum blockchain client (ETH native)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

from app.config import settings


class EthClient:
    def __init__(self) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(settings.ETH_RPC_URL))

    async def get_balance(self, address: str) -> Decimal:
        checksum = AsyncWeb3.to_checksum_address(address)
        wei = await self._w3.eth.get_balance(checksum)
        return Decimal(wei) / Decimal("1_000_000_000_000_000_000")

    async def get_latest_block(self) -> int:
        return await self._w3.eth.block_number

    async def get_transaction(self, tx_hash: str) -> Optional[dict]:
        try:
            tx = await self._w3.eth.get_transaction(tx_hash)
            return dict(tx) if tx else None
        except Exception:
            return None

    async def get_transaction_receipt(self, tx_hash: str) -> Optional[dict]:
        try:
            receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
            return dict(receipt) if receipt else None
        except Exception:
            return None

    async def get_confirmations(self, tx_hash: str) -> int:
        """Return number of confirmations for a transaction."""
        receipt = await self.get_transaction_receipt(tx_hash)
        if not receipt or receipt.get("blockNumber") is None:
            return 0
        current = await self.get_latest_block()
        return max(0, current - receipt["blockNumber"])

    async def get_incoming_txs(self, address: str, from_block: int) -> list[dict]:
        """
        NOTE: Polling full node logs for ETH transfers is expensive.
        In production, use Alchemy/Infura WebSocket or Etherscan API.
        This implementation uses Etherscan-compatible API via httpx.
        """
        import aiohttp
        checksum = AsyncWeb3.to_checksum_address(address)
        # Use Etherscan API if available (free tier works)
        etherscan_url = (
            f"https://api.etherscan.io/api"
            f"?module=account&action=txlist"
            f"&address={checksum}"
            f"&startblock={from_block}"
            f"&endblock=99999999"
            f"&sort=asc"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(etherscan_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()

        txs = []
        for tx in data.get("result", []):
            if not isinstance(tx, dict):
                continue
            if tx.get("to", "").lower() != checksum.lower():
                continue
            if tx.get("isError", "0") != "0":
                continue
            wei = int(tx.get("value", "0"))
            if wei == 0:
                continue
            txs.append({
                "tx_hash": tx["hash"],
                "from_address": tx.get("from"),
                "to_address": tx.get("to"),
                "amount": Decimal(wei) / Decimal("1_000_000_000_000_000_000"),
                "block_number": int(tx.get("blockNumber", 0)),
                "confirmations": int(tx.get("confirmations", 0)),
            })
        return txs
