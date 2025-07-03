"""
# Autor: ByMyselfJhones
# Função: Classe base para canal WebSocket da Pocket Option
# Descrição:
# - Inicializa com instância da API
# - Envia solicitações WebSocket com nome, mensagem e ID opcional
"""

class Base(object):
    """Class for base Pocket Option websocket chanel."""

    # pylint: disable=too-few-public-methods

    def __init__(self, api):

        self.api = api

    def send_websocket_request(self, name, msg, request_id=""):

        return self.api.send_websocket_request(name, msg, request_id)
