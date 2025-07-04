"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para obtenção de saldo
# Descrição:
# - Solicita e recebe informações de saldo em tempo real
"""

import json
import logging
import asyncio

class BalanceChannel:
    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.balance = None

    async def get_balance(self):
        """Obtém o saldo atual."""
        await self.client.send({"type": "get_balances"})
        async for msg in self.client.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "balances":
                    self.balance = data["data"]["balance"]
                    return self.balance
            await asyncio.sleep(0.1)
        return None

    async def change_balance(self, account_type):
        """Altera entre conta demo e real."""
        account = "demo" if account_type == "PRACTICE" else "real"
        await self.client.send({"type": "change_balance", "data": {"account": account}})
        return True