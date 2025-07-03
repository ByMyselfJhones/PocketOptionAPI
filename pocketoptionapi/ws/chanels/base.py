"""
# Autor: ByMyselfJhones
# Função: Classe base para canal WebSocket do Pocket Option
# Descrição:
# - Inicializa com instância de API
# - Envia solicitações WebSocket ao servidor com nome, mensagem e ID opcional
"""

class Base(object):
    """Class for base Pocket Option websocket chanel."""

    # pylint: disable=too-few-public-methods

    def __init__(self, api):
        """
        :param api: The instance of :class:`IQOptionAPI
            <iqoptionapi.api.IQOptionAPI>`.
        """
        self.api = api

    def send_websocket_request(self, name, msg, request_id=""):
        """Send request to Pocket Option server websocket.

        :param request_id:
        :param str name: The websocket chanel name.
        :param list msg: The websocket chanel msg.

        :returns: The instance of :class:`requests.Response`.
        """

        return self.api.send_websocket_request(name, msg, request_id)
