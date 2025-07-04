"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para autenticação via SSID
# Descrição:
# - Envia SSID para autenticação na Pocket Option
"""

import json
import logging

class SSIDChannel:
    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

    async def authenticate(self):
        """Autentica usando SSID."""
        message = {
            "type": "auth",
            "data": json.loads(self.client.ssid[2:])["auth"]
        }
        self.logger.info("Enviando autenticação SSID")
        await self.client.send(message)