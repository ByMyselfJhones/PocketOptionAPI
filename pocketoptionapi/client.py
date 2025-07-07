"""
# Autor: ByMyselfJhones
# Função: AsyncPocketOptionClient
# Descrição:
# - Cliente assíncrono para API da PocketOption
# - Gerencia conexões WebSocket, ordens, saldos e dados de candles
# - Suporta modo demo/live, reconexão automática e monitoramento de erros
"""

import asyncio
import json
import time
import uuid
from typing import Optional, List, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from loguru import logger

from .monitoring import error_monitor, health_checker, ErrorCategory, ErrorSeverity
from .websocket_client import AsyncWebSocketClient
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    ServerTime,
)
from .constants import ASSETS, REGIONS, TIMEFRAMES, API_LIMITS
from .exceptions import (
    PocketOptionError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    InvalidParameterError,
)

class AsyncPocketOptionClient:
    """
    Cliente assíncrono profissional para API da PocketOption com práticas modernas de Python
    """

    def __init__(
        self,
        ssid: str,
        is_demo: bool = True,
        region: Optional[str] = None,
        uid: int = 0,
        platform: int = 1,
        is_fast_history: bool = True,
        persistent_connection: bool = False,
        auto_reconnect: bool = True,
        enable_logging: bool = True,
    ):
        """
        Inicializa cliente assíncrono da PocketOption com monitoramento aprimorado

        Args:
            ssid: String SSID completa ou ID de sessão bruto para autenticação
            is_demo: Se deve usar conta demo
            region: Região preferida para conexão
            uid: ID do usuário (se fornecer sessão bruta)
            platform: Identificador da plataforma (1=web, 3=mobile)
            is_fast_history: Ativar carregamento rápido de histórico
            persistent_connection: Ativar conexão persistente com keep-alive (como API antiga)
            auto_reconnect: Ativar reconexão automática ao desconectar
            enable_logging: Ativar log detalhado (padrão: True)
        """
        self.raw_ssid = ssid
        self.is_demo = is_demo
        self.preferred_region = region
        self.uid = uid
        self.platform = platform
        self.is_fast_history = is_fast_history
        self.persistent_connection = persistent_connection
        self.auto_reconnect = auto_reconnect
        self.enable_logging = enable_logging

        # Configurar log com base na preferência
        if not enable_logging:
            logger.remove()
            logger.add(lambda msg: None, level="CRITICAL")  # Desativa maioria dos logs
        # Analisar SSID se for uma mensagem de autenticação completa
        self._original_demo = None  # Armazena valor demo original do SSID
        if ssid.startswith('42["auth",'):
            self._parse_complete_ssid(ssid)
        else:
            # Tratar como ID de sessão bruto
            self.session_id = ssid
            self._complete_ssid = None

        # Componentes principais
        self._websocket = AsyncWebSocketClient()
        self._balance: Optional[Balance] = None
        self._orders: Dict[str, OrderResult] = {}
        self._active_orders: Dict[str, OrderResult] = {}
        self._order_results: Dict[str, OrderResult] = {}
        self._candles_cache: Dict[str, List[Candle]] = {}
        self._server_time: Optional[ServerTime] = None
        self._event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        # Configurar manipuladores de eventos para mensagens WebSocket
        self._setup_event_handlers()

        # Adicionar manipulador para mensagens de dados JSON (contém dados detalhados de ordens)
        self._websocket.add_event_handler("json_data", self._on_json_data)
        # Monitoramento e tratamento de erros aprimorado

        self._error_monitor = error_monitor
        self._health_checker = health_checker

        # Rastreamento de desempenho
        self._operation_metrics: Dict[str, List[float]] = defaultdict(list)
        self._last_health_check = time.time()

        # Funcionalidade de keep-alive (baseada em padrões da API antiga)
        self._keep_alive_manager = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._is_persistent = False

        # Estatísticas de conexão (como na API antiga)
        self._connection_stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "total_reconnects": 0,
            "last_ping_time": None,
            "messages_sent": 0,
            "messages_received": 0,
            "connection_start_time": None,
        }

        logger.info(
            f"Cliente PocketOption inicializado (demo={is_demo}, uid={self.uid}, persistente={persistent_connection}) com monitoramento aprimorado"
            if enable_logging
            else ""
        )

    def _setup_event_handlers(self):
        """Configurar manipuladores de eventos WebSocket"""
        self._websocket.add_event_handler("authenticated", self._on_authenticated)
        self._websocket.add_event_handler("balance_updated", self._on_balance_updated)
        self._websocket.add_event_handler(
            "balance_data", self._on_balance_data
        )  # Adicionar manipulador de balance_data
        self._websocket.add_event_handler("order_opened", self._on_order_opened)
        self._websocket.add_event_handler("order_closed", self._on_order_closed)
        self._websocket.add_event_handler("stream_update", self._on_stream_update)
        self._websocket.add_event_handler("candles_received", self._on_candles_received)
        self._websocket.add_event_handler("disconnected", self._on_disconnected)

    async def connect(
        self, regions: Optional[List[str]] = None, persistent: Optional[bool] = None
    ) -> bool:
        """
        Conectar à PocketOption com suporte a múltiplas regiões

        Args:
            regions: Lista de regiões para tentar (usa padrões se None)
            persistent: Sobrescrever configuração de conexão persistente

        Returns:
            bool: True se conectado com sucesso
        """
        logger.info("Conectando à PocketOption...")
        # Atualizar configuração persistente se fornecida
        if persistent is not None:
            self.persistent_connection = bool(persistent)

        try:
            if self.persistent_connection:
                return await self._start_persistent_connection(regions)
            else:
                return await self._start_regular_connection(regions)

        except Exception as e:
            logger.error(f"Falha na conexão: {e}")
            await self._error_monitor.record_error(
                error_type="connection_failed",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.CONNECTION,
                message=f"Falha na conexão: {e}",
            )
            return False

    async def _start_regular_connection(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Iniciar conexão regular (comportamento existente)"""
        logger.info("Iniciando conexão regular...")
        # Usar regiões apropriadas com base no modo demo
        if not regions:
            if self.is_demo:
                # Para modo demo, usar apenas regiões demo
                demo_urls = REGIONS.get_demo_regions()
                regions = []
                all_regions = REGIONS.get_all_regions()
                for name, url in all_regions.items():
                    if url in demo_urls:
                        regions.append(name)
                logger.info(f"Modo demo: Usando regiões demo: {regions}")
            else:
                # Para modo live, usar todas as regiões exceto demo
                all_regions = REGIONS.get_all_regions()
                regions = [
                    name
                    for name, url in all_regions.items()
                    if "DEMO" not in name.upper()
                ]
                logger.info(f"Modo live: Usando regiões não-demo: {regions}")
        # Atualizar estatísticas de conexão
        self._connection_stats["total_connections"] += 1
        self._connection_stats["connection_start_time"] = time.time()

        for region in regions:
            try:
                region_url = REGIONS.get_region(region)
                if not region_url:
                    continue

                urls = [region_url]  # Converter URL única para lista
                logger.info(f"Tentando região: {region} com URL: {region_url}")

                # Tentar conectar
                ssid_message = self._format_session_message()
                success = await self._websocket.connect(urls, ssid_message)

                if success:
                    logger.info(f" Conectado à região: {region}")

                    # Aguardar autenticação
                    await self._wait_for_authentication()

                    # Inicializar dados
                    await self._initialize_data()

                    # Iniciar tarefas de keep-alive
                    await self._start_keep_alive_tasks()

                    self._connection_stats["successful_connections"] += 1
                    logger.info("Conectado e autenticado com sucesso")
                    return True

            except Exception as e:
                logger.warning(f"Falha ao conectar à região {region}: {e}")
                continue

        return False

    async def _start_persistent_connection(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Iniciar conexão persistente com keep-alive (como API antiga)"""
        logger.info("Iniciando conexão persistente com keep-alive automático...")

        # Importar gerenciador de keep-alive
        from .connection_keep_alive import ConnectionKeepAlive

        # Criar gerenciador de keep-alive
        complete_ssid = self.raw_ssid
        self._keep_alive_manager = ConnectionKeepAlive(complete_ssid, self.is_demo)

        # Adicionar manipuladores de eventos
        self._keep_alive_manager.add_event_handler(
            "connected", self._on_keep_alive_connected
        )
        self._keep_alive_manager.add_event_handler(
            "reconnected", self._on_keep_alive_reconnected
        )
        self._keep_alive_manager.add_event_handler(
            "message_received", self._on_keep_alive_message
        )

        # Adicionar manipuladores para eventos WebSocket encaminhados
        self._keep_alive_manager.add_event_handler(
            "balance_data", self._on_balance_data
        )
        self._keep_alive_manager.add_event_handler(
            "balance_updated", self._on_balance_updated
        )
        self._keep_alive_manager.add_event_handler(
            "authenticated", self._on_authenticated
        )
        self._keep_alive_manager.add_event_handler(
            "order_opened", self._on_order_opened
        )
        self._keep_alive_manager.add_event_handler(
            "order_closed", self._on_order_closed
        )
        self._keep_alive_manager.add_event_handler(
            "stream_update", self._on_stream_update
        )
        self._keep_alive_manager.add_event_handler("json_data", self._on_json_data)

        # Conectar com keep-alive
        success = await self._keep_alive_manager.connect_with_keep_alive(regions)

        if success:
            self._is_persistent = True
            logger.info(" Conexão persistente estabelecida com sucesso")
            return True
        else:
            logger.error("Falha ao estabelecer conexão persistente")
            return False

    async def _start_keep_alive_tasks(self):
        """Iniciar tarefas de keep-alive para conexão regular"""
        logger.info("Iniciando tarefas de keep-alive para conexão regular...")

        # Iniciar tarefa de ping (como na API antiga)
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Iniciar monitoramento de reconexão se auto_reconnect estiver habilitado
        if self.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnection_monitor())

    async def _ping_loop(self):
        """Loop de ping para conexões regulares (como API antiga)"""
        while self.is_connected and not self._is_persistent:
            try:
                await self._websocket.send_message('42["ps"]')
                self._connection_stats["last_ping_time"] = time.time()
                await asyncio.sleep(20)  # Ping a cada 20 segundos
            except Exception as e:
                logger.warning(f"Falha no ping: {e}")
                break

    async def _reconnection_monitor(self):
        """Monitorar e gerenciar reconexões para conexões regulares"""
        while self.auto_reconnect and not self._is_persistent:
            await asyncio.sleep(30)  # Verificar a cada 30 segundos

            if not self.is_connected:
                logger.info("Conexão perdida, tentando reconectar...")
                self._connection_stats["total_reconnects"] += 1

                try:
                    success = await self._start_regular_connection()
                    if success:
                        logger.info(" Reconexão bem-sucedida")
                    else:
                        logger.error("Falha na reconexão")
                        await asyncio.sleep(10)  # Aguardar antes da próxima tentativa
                except Exception as e:
                    logger.error(f"Erro na reconexão: {e}")
                    await asyncio.sleep(10)

    async def disconnect(self) -> None:
        """Desconectar da PocketOption e limpar todos os recursos"""
        logger.info("Desconectando da PocketOption...")

        # Cancelar tarefas
        if self._ping_task:
            self._ping_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

        # Desconectar com base no tipo de conexão
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.disconnect()
        else:
            await self._websocket.disconnect()

        # Redefinir estado
        self._is_persistent = False
        self._balance = None
        self._orders.clear()

        logger.info("Desconectado com sucesso")

    async def get_balance(self) -> Balance:
        """
        Obter saldo atual da conta

        Returns:
            Balance: Informações do saldo atual
        """
        if not self.is_connected:
            raise ConnectionError("Não conectado à PocketOption")

        # Solicitar atualização de saldo se necessário
        if (
            not self._balance
            or (datetime.now() - self._balance.last_updated).seconds > 60
        ):
            await self._request_balance_update()

            # Aguardar um pouco para o saldo ser recebido
            await asyncio.sleep(1)

        if not self._balance:
            raise PocketOptionError("Dados de saldo não disponíveis")

        return self._balance

    async def place_order(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> OrderResult:
        """
        Colocar uma ordem de opções binárias

        Args:
            asset: Símbolo do ativo (e.g., "EURUSD_otc")
            amount: Valor da ordem
            direction: OrderDirection.CALL ou OrderDirection.PUT
            duration: Duração em segundos

        Returns:
            OrderResult: Resultado da colocação da ordem
        """
        if not self.is_connected:
            raise ConnectionError("Não conectado à PocketOption")
            # Validar parâmetros
        self._validate_order_parameters(asset, amount, direction, duration)

        try:
            # Criar ordem
            order_id = str(uuid.uuid4())
            order = Order(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration,
                request_id=order_id,  # Usar request_id, não order_id
            )  # Enviar ordem
            await self._send_order(order)

            # Aguardar resultado (obtém resposta do servidor ou cria um fallback)
            result = await self._wait_for_order_result(order_id, order)

            # Não armazenar novamente - _wait_for_order_result já gerencia armazenamento
            logger.info(f"Ordem colocada: {result.order_id} - {result.status}")
            return result

        except Exception as e:
            logger.error(f"Falha ao colocar ordem: {e}")
            raise OrderError(f"Falha ao colocar ordem: {e}")

    async def get_candles(
        self,
        asset: str,
        timeframe: Union[str, int],
        count: int = 100,
        end_time: Optional[datetime] = None,
    ) -> List[Candle]:
        """
        Obter dados históricos de candles com reconexão automática

        Args:
            asset: Símbolo do ativo
            timeframe: Período (e.g., "1m", "5m", 60)
            count: Número de candles a recuperar
            end_time: Tempo final para os dados (padrão: agora)

        Returns:
            List[Candle]: Dados históricos de candles
        """
        # Verificar conexão e tentar reconectar se necessário
        if not self.is_connected:
            if self.auto_reconnect:
                logger.info(
                    f"Conexão perdida, tentando reconectar para candles de {asset}..."
                )
                reconnected = await self._attempt_reconnection()
                if not reconnected:
                    raise ConnectionError(
                        "Não conectado à PocketOption e reconexão falhou"
                    )
            else:
                raise ConnectionError("Não conectado à PocketOption")

        # Converter período para segundos
        if isinstance(timeframe, str):
            timeframe_seconds = TIMEFRAMES.get(timeframe, 60)
        else:
            timeframe_seconds = timeframe

        # Validar ativo
        if asset not in ASSETS:
            raise InvalidParameterError(f"Ativo inválido: {asset}")

        # Definir tempo final padrão
        if not end_time:
            end_time = datetime.now()

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Solicitar dados de candles
                candles = await self._request_candles(
                    asset, timeframe_seconds, count, end_time
                )

                # Armazenar resultados em cache
                cache_key = f"{asset}_{timeframe_seconds}"
                self._candles_cache[cache_key] = candles

                logger.info(f"Recuperados {len(candles)} candles para {asset}")
                return candles

            except Exception as e:
                if "WebSocket is not connected" in str(e) and attempt < max_retries - 1:
                    logger.warning(
                        f"Conexão perdida durante solicitação de candles para {asset}, tentando reconectar..."
                    )
                    if self.auto_reconnect:
                        reconnected = await self._attempt_reconnection()
                        if reconnected:
                            logger.info(
                                f" Reconectado, tentando novamente solicitação de candles para {asset}"
                            )
                            continue

                logger.error(f"Falha ao obter candles para {asset}: {e}")
                raise PocketOptionError(f"Falha ao obter candles: {e}")

        raise PocketOptionError(f"Falha ao obter candles após {max_retries} tentativas")

    async def get_candles_dataframe(
        self,
        asset: str,
        timeframe: Union[str, int],
        count: int = 100,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Obter dados históricos de candles como DataFrame

        Args:
            asset: Símbolo do ativo
            timeframe: Período (e.g., "1m", "5m", 60)
            count: Número de candles a recuperar
            end_time: Tempo final para os dados (padrão: agora)

        Returns:
            pd.DataFrame: Dados históricos de candles
        """
        candles = await self.get_candles(asset, timeframe, count, end_time)

        # Converter para DataFrame
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
                }
            )
        df = pd.DataFrame(data)

        if not df.empty:
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

        return df

    async def check_order_result(self, order_id: str) -> Optional[OrderResult]:
        """
        Verificar o resultado de uma ordem específica

        Args:
            order_id: ID da ordem a verificar

        Returns:
            OrderResult: Resultado da ordem ou None se não encontrada
        """
        # Primeiro verificar ordens ativas
        if order_id in self._active_orders:
            return self._active_orders[order_id]

        # Depois verificar ordens concluídas
        if order_id in self._order_results:
            return self._order_results[order_id]

        # Não encontrada
        return None

    async def get_active_orders(self) -> List[OrderResult]:
        """
        Obter todas as ordens ativas

        Returns:
            List[OrderResult]: Ordens ativas
        """
        return list(self._active_orders.values())

    def add_event_callback(self, event: str, callback: Callable) -> None:
        """
        Adicionar callback de evento

        Args:
            event: Nome do evento (e.g., 'order_closed', 'balance_updated')
            callback: Função de callback
        """
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    def remove_event_callback(self, event: str, callback: Callable) -> None:
        """
        Remover callback de evento

        Args:
            event: Nome do evento
            callback: Função de callback a remover
        """
        if event in self._event_callbacks:
            try:
                self._event_callbacks[event].remove(callback)
            except ValueError:
                pass

    @property
    def is_connected(self) -> bool:
        """Verificar se o cliente está conectado (incluindo conexões persistentes)"""
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.is_connected
        else:
            return self._websocket.is_connected

    @property
    def connection_info(self):
        """Obter informações de conexão (incluindo conexões persistentes)"""
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.connection_info
        else:
            return self._websocket.connection_info

    async def send_message(self, message: str) -> bool:
        """Enviar mensagem pela conexão ativa"""
        try:
            if self._is_persistent and self._keep_alive_manager:
                return await self._keep_alive_manager.send_message(message)
            else:
                await self._websocket.send_message(message)
                return True
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem: {e}")
            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        """Obter estatísticas completas de conexão"""
        stats = self._connection_stats.copy()

        if self._is_persistent and self._keep_alive_manager:
            stats.update(self._keep_alive_manager.get_stats())
        else:
            stats.update(
                {
                    "websocket_connected": self._websocket.is_connected,
                    "connection_info": self._websocket.connection_info,
                }
            )

        return stats  # Métodos privados

    def _format_session_message(self) -> str:
        """Formatar mensagem de autenticação de sessão"""
        # Sempre criar mensagem de autenticação a partir de componentes usando parâmetros do construtor
        # Isso garante que o parâmetro is_demo seja respeitado independentemente do formato do SSID
        auth_data = {
            "session": self.session_id,
            "isDemo": 1 if self.is_demo else 0,
            "uid": self.uid,
            "platform": self.platform,
        }

        if self.is_fast_history:
            auth_data["isFastHistory"] = True

        return f'42["auth",{json.dumps(auth_data)}]'

    def _parse_complete_ssid(self, ssid: str) -> None:
        """Analisar mensagem de autenticação SSID completa para extrair componentes"""
        try:
            # Extrair parte JSON
            json_start = ssid.find("{")
            json_end = ssid.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_part = ssid[json_start:json_end]
                data = json.loads(json_part)

                self.session_id = data.get("session", "")
                # Armazenar valor demo original do SSID, mas não sobrescrever o parâmetro do construtor
                self._original_demo = bool(data.get("isDemo", 1))
                # Manter o valor is_demo do construtor - não sobrescrevê-lo
                self.uid = data.get("uid", 0)
                self.platform = data.get("platform", 1)
                # Não armazenar SSID completo - reconstruiremos com valor demo correto
                self._complete_ssid = None
        except Exception as e:
            logger.warning(f"Falha ao analisar SSID: {e}")
            self.session_id = ssid
            self._complete_ssid = None

    async def _wait_for_authentication(self, timeout: float = 10.0) -> None:
        """Aguardar a conclusão da autenticação (como API antiga)"""
        auth_received = False

        def on_auth(data):
            nonlocal auth_received
            auth_received = True

        # Adicionar manipulador temporário
        self._websocket.add_event_handler("authenticated", on_auth)

        try:
            # Aguardar autenticação
            start_time = time.time()
            while not auth_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            if not auth_received:
                raise AuthenticationError("Tempo limite de autenticação")

        finally:
            # Remover manipulador temporário
            self._websocket.remove_event_handler("authenticated", on_auth)

    async def _initialize_data(self) -> None:
        """Inicializar dados do cliente após conexão"""
        # Solicitar saldo inicial
        await self._request_balance_update()

        # Configurar sincronização de tempo
        await self._setup_time_sync()

    async def _request_balance_update(self) -> None:
        """Solicitar atualização de saldo do servidor"""
        message = '42["getBalance"]'

        # Usar método de conexão apropriado
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

    async def _setup_time_sync(self) -> None:
        """Configurar sincronização de tempo do servidor"""
        # Normalmente, isso envolveria obter o timestamp do servidor
        # Por enquanto, criar um objeto básico de sincronização de tempo
        local_time = datetime.now().timestamp()
        self._server_time = ServerTime(
            server_timestamp=local_time, local_timestamp=local_time, offset=0.0
        )

    def _validate_order_parameters(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> None:
        """Validar parâmetros da ordem"""
        if asset not in ASSETS:
            raise InvalidParameterError(f"Ativo inválido: {asset}")

        if (
            amount < API_LIMITS["min_order_amount"]
            or amount > API_LIMITS["max_order_amount"]
        ):
            raise InvalidParameterError(
                f"Valor deve estar entre {API_LIMITS['min_order_amount']} e {API_LIMITS['max_order_amount']}"
            )

        if (
            duration < API_LIMITS["min_duration"]
            or duration > API_LIMITS["max_duration"]
        ):
            raise InvalidParameterError(
                f"Duração deve estar entre {API_LIMITS['min_duration']} e {API_LIMITS['max_duration']} segundos"
            )

    async def _send_order(self, order: Order) -> None:
        """Enviar ordem ao servidor"""
        # Formatar nome do ativo com prefixo # se ainda não presente
        asset_name = order.asset

        # Criar mensagem no formato correto da PocketOption
        message = f'42["openOrder",{{"asset":"{asset_name}","amount":{order.amount},"action":"{order.direction.value}","isDemo":{1 if self.is_demo else 0},"requestId":"{order.request_id}","optionType":100,"time":{order.duration}}}]'

        # Enviar usando conexão apropriada
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        if self.enable_logging:
            logger.debug(f"Ordem enviada: {message}")

    async def _wait_for_order_result(
        self, request_id: str, order: Order, timeout: float = 30.0
    ) -> OrderResult:
        """Aguardar resultado da execução da ordem"""
        start_time = time.time()

        # Aguardar a ordem aparecer no sistema de rastreamento
        while time.time() - start_time < timeout:
            # Verificar se a ordem foi adicionada às ordens ativas (por _on_order_opened ou _on_json_data)
            if request_id in self._active_orders:
                if self.enable_logging:
                    logger.success(f" Ordem {request_id} encontrada no rastreamento ativo")
                return self._active_orders[request_id]

            # Verificar se a ordem foi diretamente para resultados (falhou ou concluída)
            if request_id in self._order_results:
                if self.enable_logging:
                    logger.info(f"📋 Ordem {request_id} encontrada nos resultados concluídos")
                return self._order_results[request_id]

            await asyncio.sleep(0.2)  # Verificar a cada 200ms

        # Verificar mais uma vez antes de criar fallback
        if request_id in self._active_orders:
            if self.enable_logging:
                logger.success(
                    f" Ordem {request_id} encontrada no rastreamento ativo (verificação final)"
                )
            return self._active_orders[request_id]

        if request_id in self._order_results:
            if self.enable_logging:
                logger.info(
                    f"📋 Ordem {request_id} encontrada nos resultados concluídos (verificação final)"
                )
            return self._order_results[request_id]

        # Se houver timeout, criar um resultado fallback com os dados originais da ordem
        if self.enable_logging:
            logger.warning(
                f"⏰ Ordem {request_id} atingiu timeout aguardando resposta do servidor, criando resultado fallback"
            )
        fallback_result = OrderResult(
            order_id=request_id,
            asset=order.asset,
            amount=order.amount,
            direction=order.direction,
            duration=order.duration,
            status=OrderStatus.ACTIVE,  # Assumir que está ativa desde que foi colocada
            placed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=order.duration),
            error_message="Timeout aguardando confirmação do servidor",
        )  # Armazenar nas ordens ativas caso o servidor responda depois
        self._active_orders[request_id] = fallback_result
        if self.enable_logging:
            logger.info(f"📝 Criado resultado fallback para ordem {request_id}")
        return fallback_result

    async def check_win(
        self, order_id: str, max_wait_time: float = 300.0
    ) -> Optional[Dict[str, Any]]:
        """
        Verificar funcionalidade de vitória - aguarda mensagem de conclusão da negociação

        Args:
            order_id: ID da ordem a verificar
            max_wait_time: Tempo máximo para aguardar o resultado (padrão: 5 minutos)

        Returns:
            Dicionário com resultado da negociação ou None se timeout/erro
        """
        start_time = time.time()

        if self.enable_logging:
            logger.info(
                f"🔍 Iniciando check_win para ordem {order_id}, espera máxima: {max_wait_time}s"
            )

        while time.time() - start_time < max_wait_time:
            # Verificar se a ordem está nos resultados concluídos
            if order_id in self._order_results:
                result = self._order_results[order_id]
                if self.enable_logging:
                    logger.success(
                        f" Ordem {order_id} concluída - Status: {result.status.value}, Lucro: ${result.profit:.2f}"
                    )

                return {
                    "result": "win"
                    if result.status == OrderStatus.WIN
                    else "loss"
                    if result.status == OrderStatus.LOSE
                    else "draw",
                    "profit": result.profit if result.profit is not None else 0,
                    "order_id": order_id,
                    "completed": True,
                    "status": result.status.value,
                }

            # Verificar se a ordem ainda está ativa (ainda não expirou)
            if order_id in self._active_orders:
                active_order = self._active_orders[order_id]
                time_remaining = (
                    active_order.expires_at - datetime.now()
                ).total_seconds()

                if time_remaining <= 0:
                    if self.enable_logging:
                        logger.info(
                            f"⏰ Ordem {order_id} expirou mas sem resultado ainda, continuando a aguardar..."
                        )
                else:
                    if (
                        self.enable_logging and int(time.time() - start_time) % 10 == 0
                    ):  # Log a cada 10 segundos
                        logger.debug(
                            f"⌛ Ordem {order_id} ainda ativa, expira em {time_remaining:.0f}s"
                        )

            await asyncio.sleep(1.0)  # Verificar a cada segundo

        # Timeout atingido
        if self.enable_logging:
            logger.warning(
                f"⏰ Timeout no check_win para ordem {order_id} após {max_wait_time}s"
            )

        return {
            "result": "timeout",
            "order_id": order_id,
            "completed": False,
            "timeout": True,
        }

    async def _request_candles(
        self, asset: str, timeframe: int, count: int, end_time: datetime
    ):
        """Solicitar dados de candles do servidor usando o formato changeSymbol correto"""
        # Criar dados da mensagem no formato esperado pela PocketOption para candles em tempo real
        data = {
            "asset": str(asset),
            "period": timeframe,  # período em segundos
        }

        # Criar mensagem completa usando changeSymbol
        message_data = ["changeSymbol", data]
        message = f"42{json.dumps(message_data)}"

        if self.enable_logging:
            logger.debug(f"Solicitando candles com changeSymbol: {message}")

        # Criar um futuro para aguardar a resposta
        candle_future = asyncio.Future()
        request_id = f"{asset}_{timeframe}"

        # Armazenar o futuro para esta solicitação
        if not hasattr(self, "_candle_requests"):
            self._candle_requests = {}
        self._candle_requests[request_id] = candle_future

        # Enviar a solicitação usando conexão apropriada
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        try:
            # Aguardar a resposta (com timeout)
            candles = await asyncio.wait_for(candle_future, timeout=10.0)
            return candles
        except asyncio.TimeoutError:
            if self.enable_logging:
                logger.warning(f"Solicitação de candles atingiu timeout para {asset}")
            return []
        finally:
            # Limpar a solicitação
            if request_id in self._candle_requests:
                del self._candle_requests[request_id]

    def _parse_candles_data(self, candles_data: List[Any], asset: str, timeframe: int):
        """Analisar dados de candles da resposta do servidor"""
        candles = []

        try:
            if isinstance(candles_data, list):
                for candle_data in candles_data:
                    if isinstance(candle_data, (list, tuple)) and len(candle_data) >= 5:
                        # Formato do servidor: [timestamp, open, low, high, close]
                        # Nota: Servidor envia low/high trocados comparado ao formato OHLC padrão
                        raw_high = float(candle_data[2])
                        raw_low = float(candle_data[3])

                        # Garantir que high >= low, trocando se necessário
                        actual_high = max(raw_high, raw_low)
                        actual_low = min(raw_high, raw_low)

                        candle = Candle(
                            timestamp=datetime.fromtimestamp(candle_data[0]),
                            open=float(candle_data[1]),
                            high=actual_high,
                            low=actual_low,
                            close=float(candle_data[4]),
                            volume=float(candle_data[5])
                            if len(candle_data) > 5
                            else 0.0,
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)

        except Exception as e:
            if self.enable_logging:
                logger.error(f"Erro ao analisar dados de candles: {e}")

        return candles

    async def _on_json_data(self, data: Dict[str, Any]) -> None:
        """Gerenciar dados detalhados de ordens de mensagens JSON bytes"""
        if not isinstance(data, dict):
            return
        # Verificar se é resposta de dados de candles
        if "candles" in data and isinstance(data["candles"], list):
            # Encontrar a solicitação de candles correspondente
            if hasattr(self, "_candle_requests"):
                # Tentar corresponder à solicitação com base em ativo e período
                asset = data.get("asset")
                period = data.get("period")
                if asset and period:
                    request_id = f"{asset}_{period}"
                    if (
                        request_id in self._candle_requests
                        and not self._candle_requests[request_id].done()
                    ):
                        candles = self._parse_candles_data(
                            data["candles"], asset, period
                        )
                        self._candle_requests[request_id].set_result(candles)
                        if self.enable_logging:
                            logger.success(
                                f" Dados de candles recebidos: {len(candles)} candles para {asset}"
                            )
                        del self._candle_requests[request_id]
                        return
            return

        # Verificar se é dado detalhado de ordem com requestId
        if "requestId" in data and "asset" in data and "amount" in data:
            request_id = str(data["requestId"])

            # Se for uma nova ordem, adicioná-la ao rastreamento
            if (
                request_id not in self._active_orders
                and request_id not in self._order_results
            ):
                order_result = OrderResult(
                    order_id=request_id,
                    asset=data.get("asset", "UNKNOWN"),
                    amount=float(data.get("amount", 0)),
                    direction=OrderDirection.CALL
                    if data.get("command", 0) == 0
                    else OrderDirection.PUT,
                    duration=int(data.get("time", 60)),
                    status=OrderStatus.ACTIVE,
                    placed_at=datetime.now(),
                    expires_at=datetime.now()
                    + timedelta(seconds=int(data.get("time", 60))),
                    profit=float(data.get("profit", 0)) if "profit" in data else None,
                    payout=data.get("payout"),
                )

                # Adicionar às ordens ativas
                self._active_orders[request_id] = order_result
                if self.enable_logging:
                    logger.success(
                        f" Ordem {request_id} adicionada ao rastreamento a partir de dados JSON"
                    )

                await self._emit_event("order_opened", data)

        # Verificar se é dado de resultado de ordem com deals
        elif "deals" in data and isinstance(data["deals"], list):
            for deal in data["deals"]:
                if isinstance(deal, dict) and "id" in deal:
                    order_id = str(deal["id"])

                    if order_id in self._active_orders:
                        active_order = self._active_orders[order_id]
                        profit = float(deal.get("profit", 0))

                        # Determinar status
                        if profit > 0:
                            status = OrderStatus.WIN
                        elif profit < 0:
                            status = OrderStatus.LOSE
                        else:
                            status = OrderStatus.LOSE  # Padrão para lucro zero

                        result = OrderResult(
                            order_id=active_order.order_id,
                            asset=active_order.asset,
                            amount=active_order.amount,
                            direction=active_order.direction,
                            duration=active_order.duration,
                            status=status,
                            placed_at=active_order.placed_at,
                            expires_at=active_order.expires_at,
                            profit=profit,
                            payout=deal.get("payout"),
                        )

                        # Mover de ativa para concluída
                        self._order_results[order_id] = result
                        del self._active_orders[order_id]

                        if self.enable_logging:
                            logger.success(
                                f" Ordem {order_id} concluída via dados JSON: {status.value} - Lucro: ${profit:.2f}"
                            )
                            await self._emit_event("order_closed", result)

    async def _emit_event(self, event: str, data: Any) -> None:
        """Emitir evento para callbacks registrados"""
        if event in self._event_callbacks:
            for callback in self._event_callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    if self.enable_logging:
                        logger.error(f"Erro no callback de evento para {event}: {e}")

    # Manipuladores de eventos
    async def _on_authenticated(self, data: Dict[str, Any]) -> None:
        """Gerenciar autenticação bem-sucedida"""
        if self.enable_logging:
            logger.success(" Autenticado com sucesso na PocketOption")
        self._connection_stats["successful_connections"] += 1
        await self._emit_event("authenticated", data)

    async def _on_balance_updated(self, data: Dict[str, Any]) -> None:
        """Gerenciar atualização de saldo"""
        try:
            balance = Balance(
                balance=float(data.get("balance", 0)),
                currency=data.get("currency", "USD"),
                is_demo=self.is_demo,
            )
            self._balance = balance
            if self.enable_logging:
                logger.info(f"Saldo atualizado: ${balance.balance:.2f}")
            await self._emit_event("balance_updated", balance)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Falha ao analisar dados de saldo: {e}")

    async def _on_balance_data(self, data: Dict[str, Any]) -> None:
        """Gerenciar mensagem de dados de saldo"""
        # Similar a balance_updated, mas para formato de mensagem diferente
        await self._on_balance_updated(data)

    async def _on_order_opened(self, data: Dict[str, Any]) -> None:
        """Gerenciar evento de ordem aberta"""
        if self.enable_logging:
            logger.info(f"Ordem aberta: {data}")
        await self._emit_event("order_opened", data)

    async def _on_order_closed(self, data: Dict[str, Any]) -> None:
        """Gerenciar evento de ordem fechada"""
        if self.enable_logging:
            logger.info(f"📊 Ordem fechada: {data}")
        await self._emit_event("order_closed", data)

    async def _on_stream_update(self, data: Dict[str, Any]) -> None:
        """Gerenciar evento de atualização de stream - inclui dados de candles em tempo real"""
        if self.enable_logging:
            logger.debug(f"📡 Atualização de stream: {data}")

        # Verificar se é dado de candles da assinatura changeSymbol
        if (
            "asset" in data
            and "period" in data
            and ("candles" in data or "data" in data)
        ):
            await self._handle_candles_stream(data)

        await self._emit_event("stream_update", data)

    async def _on_candles_received(self, data: Dict[str, Any]) -> None:
        """Gerenciar dados de candles recebidos"""
        if self.enable_logging:
            logger.info(f"🕯️ Candles recebidos com dados: {type(data)}")
        # Verificar se há solicitações de candles pendentes
        if hasattr(self, "_candle_requests") and self._candle_requests:
            try:
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        parts = request_id.split("_")
                        if len(parts) >= 2:
                            asset = "_".join(parts[:-1])
                            timeframe = int(parts[-1])
                            candles = self._parse_candles_data(
                                data.get("candles", []), asset, timeframe
                            )
                            if self.enable_logging:
                                logger.info(
                                    f"🕯️ Analisados {len(candles)} candles da resposta"
                                )
                            future.set_result(candles)
                            if self.enable_logging:
                                logger.debug(f"Solicitação de candles resolvida: {request_id}")
                            break
            except Exception as e:
                if self.enable_logging:
                    logger.error(f"Erro ao processar dados de candles: {e}")
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        future.set_result([])
                        break
        await self._emit_event("candles_received", data)

    async def _on_disconnected(self, data: Dict[str, Any]) -> None:
        """Gerenciar evento de desconexão"""
        if self.enable_logging:
            logger.warning("Desconectado da PocketOption")
        await self._emit_event("disconnected", data)

    async def _handle_candles_stream(self, data: Dict[str, Any]) -> None:
        """Gerenciar dados de candles de atualizações de stream (respostas changeSymbol)"""
        try:
            asset = data.get("asset")
            period = data.get("period")
            if not asset or not period:
                return
            request_id = f"{asset}_{period}"
            if self.enable_logging:
                logger.info(f"🕯️ Processando stream de candles para {asset} ({period}s)")
            if (
                hasattr(self, "_candle_requests")
                and request_id in self._candle_requests
            ):
                future = self._candle_requests[request_id]
                if not future.done():
                    candles = self._parse_stream_candles(data, asset, period)
                    if candles:
                        future.set_result(candles)
                        if self.enable_logging:
                            logger.info(
                                f"🕯️ Solicitação de candles resolvida para {asset} com {len(candles)} candles"
                            )
                del self._candle_requests[request_id]
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Erro ao gerenciar stream de candles: {e}")

    def _parse_stream_candles(
        self, stream_data: Dict[str, Any], asset: str, timeframe: int
    ):
        """Analisar candles de dados de atualização de stream (resposta changeSymbol)"""
        candles = []
        try:
            candle_data = stream_data.get("data") or stream_data.get("candles") or []
            if isinstance(candle_data, list):
                for item in candle_data:
                    if isinstance(item, dict):
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(item.get("time", 0)),
                            open=float(item.get("open", 0)),
                            high=float(item.get("high", 0)),
                            low=float(item.get("low", 0)),
                            close=float(item.get("close", 0)),
                            volume=float(item.get("volume", 0)),
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)
                    elif isinstance(item, (list, tuple)) and len(item) >= 6:
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(item[0]),
                            open=float(item[1]),
                            high=float(item[3]),
                            low=float(item[4]),
                            close=float(item[2]),
                            volume=float(item[5]) if len(item) > 5 else 0.0,
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)
            candles.sort(key=lambda x: x.timestamp)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Erro ao analisar candles de stream: {e}")
        return candles

    async def _on_keep_alive_connected(self):
        """Gerenciar evento quando a conexão keep-alive é estabelecida"""
        logger.info("Conexão keep-alive estabelecida")

        # Inicializar dados após conexão
        await self._initialize_data()

        # Emitir evento
        for callback in self._event_callbacks.get("connected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Erro no callback de conectado: {e}")

    async def _on_keep_alive_reconnected(self):
        """Gerenciar evento quando a conexão keep-alive é restabelecida"""
        logger.info("Conexão keep-alive restabelecida")

        # Re-inicializar dados
        await self._initialize_data()

        # Emitir evento
        for callback in self._event_callbacks.get("reconnected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Erro no callback de reconectado: {e}")

    async def _on_keep_alive_message(self, message):
        """Gerenciar mensagens recebidas via conexão keep-alive"""
        # Processar a mensagem
        if message.startswith("42"):
            try:
                # Analisar a mensagem (remover prefixo 42 e analisar JSON)
                data_str = message[2:]
                data = json.loads(data_str)

                if isinstance(data, list) and len(data) >= 2:
                    event_type = data[0]
                    event_data = data[1]

                    # Processar diferentes tipos de eventos
                    if event_type == "authenticated":
                        await self._on_authenticated(event_data)
                    elif event_type == "balance_data":
                        await self._on_balance_data(event_data)
                    elif event_type == "balance_updated":
                        await self._on_balance_updated(event_data)
                    elif event_type == "order_opened":
                        await self._on_order_opened(event_data)
                    elif event_type == "order_closed":
                        await self._on_order_closed(event_data)
                    elif event_type == "stream_update":
                        await self._on_stream_update(event_data)
            except Exception as e:
                logger.error(f"Erro ao processar mensagem keep-alive: {e}")

        # Emitir evento de mensagem bruta
        for callback in self._event_callbacks.get("message", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Erro no callback de mensagem: {e}")

    async def _attempt_reconnection(self, max_attempts: int = 3) -> bool:
        """
        Tentar reconectar à PocketOption

        Args:
            max_attempts: Número máximo de tentativas de reconexão

        Returns:
            bool: True se a reconexão foi bem-sucedida
        """
        logger.info(f"Tentando reconexão (máximo de {max_attempts} tentativas)...")

        for attempt in range(max_attempts):
            try:
                logger.info(f"Tentativa de reconexão {attempt + 1}/{max_attempts}")

                # Desconectar primeiro para limpar
                if self._is_persistent and self._keep_alive_manager:
                    await self._keep_alive_manager.disconnect()
                else:
                    await self._websocket.disconnect()

                # Aguardar um pouco antes de reconectar
                await asyncio.sleep(2 + attempt)  # Atraso progressivo

                # Tentar reconectar
                if self.persistent_connection:
                    success = await self._start_persistent_connection()
                else:
                    success = await self._start_regular_connection()

                if success:
                    logger.info(f" Reconexão bem-sucedida na tentativa {attempt + 1}")

                    # Acionar evento de reconectado
                    await self._emit_event("reconnected", {})
                    return True
                else:
                    logger.warning(f"Tentativa de reconexão {attempt + 1} falhou")

            except Exception as e:
                logger.error(
                    f"Tentativa de reconexão {attempt + 1} falhou com erro: {e}"
                )

        logger.error(f"Todas as {max_attempts} tentativas de reconexão falharam")
        return False