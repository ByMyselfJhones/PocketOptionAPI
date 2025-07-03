"""
# Autor: ByMyselfJhones
# Função: Canal WebSocket para mudança de símbolo na Pocket Option
# Descrição:
# - Envia solicitação WebSocket para alterar ativo e intervalo
"""

from pocketoptionapi.ws.channels.base import Base
import time, random


class ChangeSymbol(Base):
    """Class for Pocket option change symbol websocket chanel."""
    # pylint: disable=too-few-public-methods

    name = "sendMessage"

    def __call__(self, active_id, interval):

        data_stream = ["changeSymbol", {
            "asset": active_id,
            "period": interval}]

        self.send_websocket_request(self.name, data_stream)
