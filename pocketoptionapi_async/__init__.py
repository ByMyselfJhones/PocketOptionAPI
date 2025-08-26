"""
# Autor: ByMyselfJhones
# Função: Inicialização do pacote PocketOptionAPI
# Descrição:
# - Define o pacote principal para interação com a API da Pocket Option
# - Manter compatibilidade com os exemplos (PocketOption → AsyncPocketOptionClient)
"""
# pocketoptionapi package initializer
# Exposes primary classes for easier imports
from .client import AsyncPocketOptionClient
from .config import Config

__all__ = ["AsyncPocketOptionClient", "Config"]
