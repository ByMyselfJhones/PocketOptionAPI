"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para envio de SSID na API Pocket Option
# Descrição:
# - Envia identificador de sessão (SSID) via requisição WebSocket
"""

from pocketoptionapi.ws.channels.base import Base


class Ssid(Base):
    """Class for Pocket Option API ssid websocket chanel."""
    # pylint: disable=too-few-public-methods

    name = "ssid"

    def __call__(self, ssid):
        self.send_websocket_request(self.name, ssid)
