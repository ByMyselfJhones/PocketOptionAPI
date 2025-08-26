"""
# Autor: ByMyselfJhones
# Função: Exceções Personalizadas
# Descrição:
# - Define exceções personalizadas para a API da PocketOption
# - Inclui erros para conexão, autenticação, ordens, timeout, parâmetros inválidos e WebSocket
"""

class PocketOptionError(Exception):
    """Exceção base para todos os erros da API da PocketOption"""

    from typing import Optional

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

class ConnectionError(PocketOptionError):
    """Levantada quando a conexão com a PocketOption falha"""

    pass

class AuthenticationError(PocketOptionError):
    """Levantada quando a autenticação falha"""

    pass

class OrderError(PocketOptionError):
    """Levantada quando uma operação de ordem falha"""

    pass

class TimeoutError(PocketOptionError):
    """Levantada quando uma operação atinge o tempo limite"""

    pass

class InvalidParameterError(PocketOptionError):
    """Levantada quando parâmetros inválidos são fornecidos"""

    pass

class WebSocketError(PocketOptionError):
    """Levantada quando operações WebSocket falham"""

    pass