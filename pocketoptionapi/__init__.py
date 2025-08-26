"""
# Autor: ByMyselfJhones
# Função: Inicialização do pacote PocketOptionAPI
# Descrição:
# - Define o pacote principal para interação com a API da Pocket Option
# - Manter compatibilidade com os exemplos (PocketOption → AsyncPocketOptionClient)
"""

__version__ = "1.0.0"

# Alias para a classe assíncrona principal
from .client import AsyncPocketOptionClient as PocketOption

# Expor também a configuração
from .config import Config

__all__ = ["PocketOption", "Config"]
