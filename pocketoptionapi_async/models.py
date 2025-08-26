"""
# Autor: ByMyselfJhones
# Função: Modelos Pydantic (Python)
# Descrição:
# - Define modelos Pydantic (Python) para validação e segurança de tipos na API da PocketOption
# - Inclui enums para direção/status de ordens, status de conexão e prazos
# - Modelos para ativos, saldo, candles, ordens, resultados e sincronização de tempo
"""

from typing import Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum
import uuid

class OrderDirection(str, Enum):
    """
    Representa a direção de uma ordem em negociações.
    - CALL: Uma opção de compra, prevendo que o preço subirá.
    - PUT: Uma opção de venda, prevendo que o preço cairá.
    """

    CALL = "call"
    PUT = "put"

class OrderStatus(str, Enum):
    """
    Representa o status atual de uma ordem de negociação.
    - PENDING: A ordem foi enviada, mas ainda não processada.
    - ACTIVE: A ordem está atualmente ativa no mercado.
    - CLOSED: A ordem foi fechada (expirou naturalmente ou manualmente).
    - CANCELLED: A ordem foi cancelada antes da execução ou expiração.
    - WIN: A ordem resultou em lucro.
    - LOSE: A ordem resultou em perda.
    """

    PENDING = "pending"
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    WIN = "win"
    LOSE = "lose"

class ConnectionStatus(str, Enum):
    """
    Representa o status de conexão com a plataforma de negociação.
    - CONNECTED: Conectado com sucesso à plataforma.
    - DISCONNECTED: Conexão perdida.
    - CONNECTING: Tentando estabelecer uma conexão.
    - RECONNECTING: Tentando restabelecer uma conexão perdida.
    """

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"

class TimeFrame(int, Enum):
    """
    Representa prazos padrão para dados de candlestick em segundos.
    Esses valores são comumente usados em gráficos financeiros para agregar dados de preço
    em intervalos específicos.
    """

    S1 = 1  # 1 segundo
    S5 = 5  # 5 segundos
    S10 = 10  # 10 segundos
    S15 = 15  # 15 segundos
    S30 = 30  # 30 segundos
    M1 = 60  # 1 minuto
    M5 = 300  # 5 minutos
    M15 = 900  # 15 minutos
    M30 = 1800  # 30 minutos
    H1 = 3600  # 1 hora
    H4 = 14400  # 4 horas
    D1 = 86400  # 1 dia
    W1 = 604800  # 1 semana
    MN1 = 2592000  # 1 mês (aproximado, baseado em 30 dias)

class Asset(BaseModel):
    """
    Modelo de informações de ativo.
    Define as propriedades de um ativo negociável, como pares de moedas ou commodities.
    """

    id: str
    name: str
    symbol: str
    is_active: bool = True
    payout: Optional[float] = None

    class Config:
        frozen = True

class Balance(BaseModel):
    """
    Modelo de saldo da conta.
    Fornece detalhes sobre o saldo atual da conta do usuário, moeda,
    e se é uma conta demo ou real.
    """

    balance: float
    currency: str = "USD"
    is_demo: bool = True
    last_updated: datetime = Field(default_factory=datetime.now)

    class Config:
        frozen = True

class Candle(BaseModel):
    """
    Modelo de dados de candlestick OHLC (Abertura, Máxima, Mínima, Fechamento).
    Representa um único candlestick, que resume os movimentos de preço em um prazo específico.
    Inclui validação para garantir consistência lógica de preços máxima e mínima.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    asset: str
    timeframe: int  # em segundos, representando a duração do candlestick

    @validator("high")
    def high_must_be_valid(cls, v, values):
        """
        Validador para garantir que o preço 'máximo' nunca seja menor que o preço 'mínimo'.
        Isso mantém a integridade lógica dos dados do candlestick.
        """
        if "low" in values and v < values["low"]:
            raise ValueError("Máximo deve ser maior ou igual ao mínimo")
        return v

    @validator("low")
    def low_must_be_valid(cls, v, values):
        """
        Validador para garantir que o preço 'mínimo' nunca seja maior que o preço 'máximo'.
        Isso mantém a integridade lógica dos dados do candlestick.
        """
        if "high" in values and v > values["high"]:
            raise ValueError("Mínimo deve ser menor ou igual ao máximo")
        return v

    class Config:
        frozen = True

class Order(BaseModel):
    """
    Modelo de solicitação de ordem.
    Define os parâmetros para colocar uma nova ordem de negociação.
    Inclui validação para valor positivo e duração mínima.
    """

    asset: str
    amount: float
    direction: OrderDirection
    duration: int  # em segundos, quanto tempo a ordem está ativa
    request_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

    @validator("amount")
    def amount_must_be_positive(cls, v):
        """
        Validador para garantir que o valor da negociação seja positivo.
        Um valor zero ou menor não é válido para uma ordem.
        """
        if v <= 0:
            raise ValueError("Valor deve ser positivo")
        return v

    @validator("duration")
    def duration_must_be_valid(cls, v):
        """
        Validador para garantir que a duração da ordem atenda a um requisito mínimo.
        Isso impede ordens com durações impraticavelmente curtas.
        """
        if v < 5:  # mínimo de 5 segundos
            raise ValueError("Duração deve ser de pelo menos 5 segundos")
        return v

class OrderResult(BaseModel):
    """
    Modelo de resultado de execução de ordem.
    Fornece detalhes sobre uma ordem executada ou fechada, incluindo seu resultado.
    """

    order_id: str
    asset: str
    amount: float
    direction: OrderDirection
    duration: int
    status: OrderStatus
    placed_at: datetime
    expires_at: datetime
    profit: Optional[float] = None
    payout: Optional[float] = None
    error_message: Optional[str] = None

    class Config:
        frozen = True

class ServerTime(BaseModel):
    """
    Modelo de sincronização de tempo do servidor.
    Usado para sincronizar o tempo do cliente local com o tempo do servidor de negociação,
    importante para a precisão do timestamp de negociações e eventos.
    """

    server_timestamp: float
    local_timestamp: float
    offset: float
    last_sync: datetime = Field(default_factory=datetime.now)

    class Config:
        frozen = True

class ConnectionInfo(BaseModel):
    """
    Modelo de informações de conexão.
    Fornece detalhes sobre a conexão atual com a plataforma de negociação,
    incluindo URL, região, status e métricas de conexão.
    """

    url: str
    region: str
    status: ConnectionStatus
    connected_at: Optional[datetime] = None
    last_ping: Optional[datetime] = None
    reconnect_attempts: int = 0

    class Config:
        frozen = True