"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para obtenção de velas
# Descrição:
# - Solicita e recebe velas em tempo real para um ativo específico
"""

import json
import logging
import asyncio

class CandlesChannel:
    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

    async def get_candles(self, asset, timeframe):
        """Obtém velas para o ativo e timeframe especificados."""
        await self.client.send({
            "type": "subscribe_candles",
            "data": {"asset": asset, "timeframe": timeframe}
        })
        candles = []
        async for msg in self.client.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "candles":
                    candles.append(data["data"])
                    if len(candles) >= 10:  # Limite para exemplo
                        return candles
            await asyncio.sleep(0.1)
        return candles