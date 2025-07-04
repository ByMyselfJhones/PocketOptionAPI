"""
# Autor: ByMyselfJhones
# Função: Cliente WebSocket para Pocket Option
# Descrição:
# - Gerencia conexão WebSocket com reconexão automática
# - Envia pings para manter a conexão ativa
"""

import aiohttp
import asyncio
import json
import logging
from pocketoptionapi.ws.channels.ssid import SSIDChannel
from pocketoptionapi.ws.channels.get_balances import BalanceChannel
from pocketoptionapi.ws.channels.candles import CandlesChannel

class WebSocketClient:
    def __init__(self, ssid, is_demo=True):
        self.ssid = ssid
        self.is_demo = is_demo
        self.url = "wss://api.po.market/ws/v3"
        self.session = None
        self.ws = None
        self.logger = logging.getLogger(__name__)
        self.ssid_channel = SSIDChannel(self)
        self.balance_channel = BalanceChannel(self)
        self.candles_channel = CandlesChannel(self)
        self.connected = False

    async def connect(self):
        """Inicia a conexão WebSocket."""
        try:
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(self.url, heartbeat=20)
            self.connected = True
            self.logger.info("WebSocket conectado")
            await self.ssid_channel.authenticate()
            asyncio.create_task(self.ping())
        except Exception as e:
            self.logger.error(f"Erro ao conectar: {e}")
            await self.reconnect()

    async def ping(self):
        """Envia pings para manter a conexão ativa."""
        while self.connected:
            try:
                await self.ws.send_str('{"type": "ping"}')
                await asyncio.sleep(20)
            except Exception as e:
                self.logger.error(f"Erro no ping: {e}")
                await self.reconnect()

    async def reconnect(self):
        """Reconecta automaticamente em caso de falha."""
        self.connected = False
        await self.close()
        self.logger.info("Tentando reconectar...")
        await asyncio.sleep(5)
        await self.connect()

    async def send(self, message):
        """Envia mensagem pelo WebSocket."""
        if self.connected:
            await self.ws.send_str(json.dumps(message))

    async def get_balance(self):
        """Obtém saldo via canal de saldo."""
        return await self.balance_channel.get_balance()

    async def get_candles(self, asset, timeframe):
        """Obtém velas via canal de velas."""
        return await self.candles_channel.get_candles(asset, timeframe)

    async def change_balance(self, account_type):
        """Altera tipo de conta."""
        return await self.balance_channel.change_balance(account_type)

    async def close(self):
        """Fecha a conexão WebSocket."""
        self.connected = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()