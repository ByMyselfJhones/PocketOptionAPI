"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para envio de SSID na API Pocket Option
# Descrição:
# - Envia identificador de sessão (SSID) via canal WebSocket
"""

from pocketoptionapi.ws.chanels.base import Base


class Ssid(Base):
    """Class for Pocket Option API ssid websocket chanel."""
    # pylint: disable=too-few-public-methods

    name = "ssid"

    def __call__(self, ssid):
        """Method to send message to ssid websocket chanel.

        :param ssid: The session identifier.
        """
        self.send_websocket_request(self.name, ssid)
