"""
# Autor: ByMyselfJhones
# Função: Interface principal da API Pocket Option
# Descrição:
# - Gerencia conexão assíncrona com a Pocket Option
# - Suporta autenticação, saldo e velas em tempo real
"""

import aiohttp
import asyncio
import json
import logging
from pocketoptionapi.ws.client import WebSocketClient

class PocketOption:
    def __init__(self, ssid, is_demo=True):
        self.ssid = ssid
        self.is_demo = is_demo
        self.ws_client = None
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Conecta ao servidor WebSocket da Pocket Option."""
        self.ws_client = WebSocketClient(self.ssid, self.is_demo)
        await self.ws_client.connect()
        self.logger.info("Conexão estabelecida")
        return True, "Conexão OK"

    async def get_balance(self):
        """Obtém o saldo da conta."""
        if not self.ws_client:
            return None
        balance = await self.ws_client.get_balance()
        return balance

    async def get_candles(self, asset, timeframe=60):
        """Obtém velas em tempo real."""
        if not self.ws_client:
            return None
        candles = await self.ws_client.get_candles(asset, timeframe)
        return candles

    async def change_balance(self, account_type="PRACTICE"):
        """Altera entre conta demo e real."""
        if not self.ws_client:
            return False
        return await self.ws_client.change_balance(account_type)

    async def close(self):
        """Fecha a conexão WebSocket."""
        if self.ws_client:
            await self.ws_client.close()
            self.logger.info("Conexão fechada")