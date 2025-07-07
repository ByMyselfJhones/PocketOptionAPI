"""
# Autor: ByMyselfJhones
# Função: Funções Utilitárias
# Descrição:
# - Fornece utilitários para a API da PocketOption
# - Inclui formatação de sessão, análise de candles, payout e gerenciamento de ordens
# - Suporta validação de ativos, limite de taxa e conversão de dados
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger
from .models import Candle, OrderResult

def format_session_id(
    session_id: str,
    is_demo: bool = True,
    uid: int = 0,
    platform: int = 1,
    is_fast_history: bool = True,
) -> str:
    """
    Formatar ID de sessão para autenticação

    Args:
        session_id: ID de sessão bruto
        is_demo: Se é uma conta demo
        uid: ID do usuário
        platform: Identificador da plataforma (1=web, 3=mobile)
        is_fast_history: Ativar carregamento rápido de histórico

    Returns:
        str: Mensagem de sessão formatada
    """
    import json

    auth_data = {
        "session": session_id,
        "isDemo": 1 if is_demo else 0,
        "uid": uid,
        "platform": platform,
    }

    if is_fast_history:
        auth_data["isFastHistory"] = True

    return f'42["auth",{json.dumps(auth_data)}]'

def calculate_payout_percentage(
    entry_price: float, exit_price: float, direction: str, payout_rate: float = 0.8
) -> float:
    """
    Calcular percentual de payout para uma ordem

    Args:
        entry_price: Preço de entrada
        exit_price: Preço de saída
        direction: Direção da ordem ('call' ou 'put')
        payout_rate: Taxa de payout (padrão 80%)

    Returns:
        float: Percentual de payout
    """
    if direction.lower() == "call":
        win = exit_price > entry_price
    else:  # put
        win = exit_price < entry_price

    return payout_rate if win else -1.0

def analyze_candles(candles: List[Candle]) -> Dict[str, Any]:
    """
    Analisar dados de candles para estatísticas básicas

    Args:
        candles: Lista de dados de candles

    Returns:
        Dict[str, Any]: Resultados da análise
    """
    if not candles:
        return {}

    prices = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]

    return {
        "count": len(candles),
        "first_price": prices[0],
        "last_price": prices[-1],
        "price_change": prices[-1] - prices[0],
        "price_change_percent": ((prices[-1] - prices[0]) / prices[0]) * 100,
        "highest": max(highs),
        "lowest": min(lows),
        "average_close": sum(prices) / len(prices),
        "volatility": calculate_volatility(prices),
        "trend": determine_trend(prices),
    }

def calculate_volatility(prices: List[float], periods: int = 14) -> float:
    """
    Calcular volatilidade de preço (desvio padrão)

    Args:
        prices: Lista de preços
        periods: Número de períodos para cálculo

    Returns:
        float: Valor da volatilidade
    """
    if len(prices) < periods:
        periods = len(prices)

    recent_prices = prices[-periods:]
    mean = sum(recent_prices) / len(recent_prices)

    variance = sum((price - mean) ** 2 for price in recent_prices) / len(recent_prices)
    return variance**0.5

def determine_trend(prices: List[float], periods: int = 10) -> str:
    """
    Determinar direção da tendência de preço

    Args:
        prices: Lista de preços
        periods: Número de períodos para análise

    Returns:
        str: Direção da tendência ('bullish', 'bearish', 'sideways')
    """
    if len(prices) < periods:
        periods = len(prices)

    if periods < 2:
        return "sideways"

    recent_prices = prices[-periods:]
    first_half = recent_prices[: periods // 2]
    second_half = recent_prices[periods // 2 :]

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    change_percent = ((second_avg - first_avg) / first_avg) * 100

    if change_percent > 0.1:
        return "bullish"
    elif change_percent < -0.1:
        return "bearish"
    else:
        return "sideways"

def calculate_support_resistance(
    candles: List[Candle], periods: int = 20
) -> Dict[str, float]:
    """
    Calcular níveis de suporte e resistência

    Args:
        candles: Lista de dados de candles
        periods: Número de períodos para análise

    Returns:
        Dict[str, float]: Níveis de suporte e resistência
    """
    if len(candles) < periods:
        periods = len(candles)

    recent_candles = candles[-periods:]
    highs = [candle.high for candle in recent_candles]
    lows = [candle.low for candle in recent_candles]

    # Cálculo simples de suporte/resistência
    resistance = max(highs)
    support = min(lows)

    return {"support": support, "resistance": resistance, "range": resistance - support}

def format_timeframe(seconds: int) -> str:
    """
    Formatar segundos de prazo em string legível

    Args:
        seconds: Prazo em segundos

    Returns:
        str: Prazo formatado (e.g., '1m', '5m', '1h')
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"

def validate_asset_symbol(symbol: str, available_assets: Dict[str, int]) -> bool:
    """
    Validar se o símbolo do ativo está disponível

    Args:
        symbol: Símbolo do ativo a validar
        available_assets: Dicionário de ativos disponíveis

    Returns:
        bool: True se o ativo está disponível
    """
    return symbol in available_assets

def calculate_order_expiration(
    duration_seconds: int, current_time: Optional[datetime] = None
) -> datetime:
    """
    Calcular tempo de expiração da ordem

    Args:
        duration_seconds: Duração em segundos
        current_time: Tempo atual (padrão: agora)

    Returns:
        datetime: Tempo de expiração
    """
    if current_time is None:
        current_time = datetime.now()

    return current_time + timedelta(seconds=duration_seconds)

def retry_async(max_attempts: int = 3, delay: float = 1.0, backoff_factor: float = 2.0):
    """
    Decorador para retentativa de funções assíncronas

    Args:
        max_attempts: Número máximo de tentativas
        delay: Atraso inicial entre tentativas
        backoff_factor: Multiplicador de atraso para cada tentativa
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Função {func.__name__} falhou após {max_attempts} tentativas: {e}"
                        )
                        raise

                    logger.warning(
                        f"Tentativa {attempt + 1} falhou para {func.__name__}: {e}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor

        return wrapper

    return decorator

def performance_monitor(func):
    """
    Decorador para monitoramento de desempenho de função
    """

    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} executada em {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} falhou após {execution_time:.3f}s: {e}")
            raise

    return wrapper

class RateLimiter:
    """
    Limitador de taxa para chamadas de API
    """

    def __init__(self, max_calls: int = 100, time_window: int = 60):
        """
        Inicializar limitador de taxa

        Args:
            max_calls: Máximo de chamadas permitidas
            time_window: Janela de tempo em segundos
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    async def acquire(self) -> bool:
        """
        Adquirir permissão para fazer uma chamada

        Returns:
            bool: True se a permissão foi concedida
        """
        now = time.time()

        # Remover chamadas antigas fora da janela de tempo
        self.calls = [
            call_time for call_time in self.calls if now - call_time < self.time_window
        ]

        # Verificar se podemos fazer outra chamada
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True

        # Calcular tempo de espera
        wait_time = self.time_window - (now - self.calls[0])
        if wait_time > 0:
            logger.warning(f"Limite de taxa excedido, aguardando {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return await self.acquire()

        return True

class OrderManager:
    """
    Gerenciar múltiplas ordens e seus resultados
    """

    def __init__(self):
        self.active_orders: Dict[str, OrderResult] = {}
        self.completed_orders: Dict[str, OrderResult] = {}
        self.order_callbacks: Dict[str, List] = {}

    def add_order(self, order: OrderResult) -> None:
        """Adicionar uma ordem ativa"""
        self.active_orders[order.order_id] = order

    def complete_order(self, order_id: str, result: OrderResult) -> None:
        """Marcar ordem como concluída"""
        if order_id in self.active_orders:
            del self.active_orders[order_id]

        self.completed_orders[order_id] = result

        # Chamar callbacks registrados
        if order_id in self.order_callbacks:
            for callback in self.order_callbacks[order_id]:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Erro no callback de ordem: {e}")
            del self.order_callbacks[order_id]

    def add_order_callback(self, order_id: str, callback) -> None:
        """Adicionar callback para conclusão de ordem"""
        if order_id not in self.order_callbacks:
            self.order_callbacks[order_id] = []
        self.order_callbacks[order_id].append(callback)

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Obter status da ordem"""
        if order_id in self.active_orders:
            return self.active_orders[order_id]
        elif order_id in self.completed_orders:
            return self.completed_orders[order_id]
        return None

    def get_active_count(self) -> int:
        """Obter número de ordens ativas"""
        return len(self.active_orders)

    def get_completed_count(self) -> int:
        """Obter número de ordens concluídas"""
        return len(self.completed_orders)

def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """
    Converter candles para DataFrame pandas

    Args:
        candles: Lista de objetos de candles

    Returns:
        pd.DataFrame: Candles como DataFrame
    """
    data = []
    for candle in candles:
        data.append(
            {
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "asset": candle.asset,
            }
        )

    df = pd.DataFrame(data)
    if not df.empty:
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

    return df