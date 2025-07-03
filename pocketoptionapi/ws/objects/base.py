"""
# Autor: ByMyselfJhones
# Função: Classe base para objetos WebSocket do Pocket Option
# Descrição:
# - Define uma classe base com atributo de nome
# - Fornece acesso ao nome via propriedade
"""

class Base(object):
    """Class for Pocket Option Base websocket object."""
    # pylint: disable=too-few-public-methods

    def __init__(self):
        self.__name = None

    @property
    def name(self):
        return self.__name
