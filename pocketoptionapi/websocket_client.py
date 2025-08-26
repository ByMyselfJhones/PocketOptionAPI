"""
# Autor: ByMyselfJhones
# Função: AsyncWebSocketClient
# Descrição:
# - Cliente WebSocket assíncrono para API da PocketOption
# - Gerencia conexões, mensagens em lote e pooling de conexões
# - Suporta autenticação, reconexão e tratamento de eventos
"""

import asyncio
import json
import ssl
import time
from typing import Optional, Callable, Dict, Any, List, Deque
from datetime import datetime
from collections import deque
import websockets
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import WebSocketClientProtocol
from loguru import logger

def _normalize_headers_for_websockets(headers):
    """
    Convert headers dict to list of (key, value) tuples to avoid compatibility issues
    with older/newer versions of `websockets` that are strict about types.
    """
    if headers is None:
        return None
    if isinstance(headers, dict):
        return list(headers.items())
    if isinstance(headers, (list, tuple)):
        return list(headers)
    try:
        return list(headers.items())
    except Exception:
        return None

def _get_websockets_connect():
    """
    Return a reference to the correct connect function regardless of where it lives
    across `websockets` versions.
    """
    try:
        import websockets as _ws
        # Newer versions expose connect at top-level; some have it under .client
        if hasattr(_ws, "connect"):
            return _ws.connect
        if hasattr(_ws, "client") and hasattr(_ws.client, "connect"):
            return _ws.client.connect
        # Legacy path (very old)
        from websockets.legacy.client import connect as legacy_connect  # type: ignore
        return legacy_connect
    except Exception as e:
        raise RuntimeError(f"Falha ao localizar websockets.connect: {e}")

from .models import ConnectionInfo, ConnectionStatus, ServerTime
from .constants import CONNECTION_SETTINGS, DEFAULT_HEADERS
from .exceptions import WebSocketError, ConnectionError


class MessageBatcher:
    """Agrupar mensagens para melhorar o desempenho"""

    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_messages: Deque[str] = deque()
        self._last_batch_time = time.time()
        self._batch_lock = asyncio.Lock()

    async def add_message(self, message: str) -> List[str]:
        """Adicionar mensagem ao lote e retornar lote se pronto"""
        async with self._batch_lock:
            self.pending_messages.append(message)
            current_time = time.time()

            # Verificar se o lote está pronto
            if (
                len(self.pending_messages) >= self.batch_size
                or current_time - self._last_batch_time >= self.batch_timeout
            ):
                batch = list(self.pending_messages)
                self.pending_messages.clear()
                self._last_batch_time = current_time
                return batch

            return []

    async def flush_batch(self) -> List[str]:
        """Forçar liberação do lote atual"""
        async with self._batch_lock:
            if self.pending_messages:
                batch = list(self.pending_messages)
                self.pending_messages.clear()
                self._last_batch_time = time.time()
                return batch
            return []


class ConnectionPool:
    """Pool de conexões para melhor gerenciamento de recursos"""

    def __init__(self, max_connections: int = 3):
        self.active_connections: Dict[str, WebSocketClientProtocol] = {}
        self.connection_stats: Dict[str, Dict[str, Any]] = {}
        self._pool_lock = asyncio.Lock()

    async def get_best_connection(self) -> Optional[str]:
        """Obter a conexão com melhor desempenho"""
        async with self._pool_lock:
            if not self.connection_stats:
                return None

            # Ordenar por tempo de resposta e taxa de sucesso
            best_url = min(
                self.connection_stats.keys(),
                key=lambda url: (
                    self.connection_stats[url].get("avg_response_time", float("inf")),
                    -self.connection_stats[url].get("success_rate", 0),
                ),
            )
            return best_url

    async def update_stats(self, url: str, response_time: float, success: bool):
        """Atualizar estatísticas de conexão"""
        async with self._pool_lock:
            if url not in self.connection_stats:
                self.connection_stats[url] = {
                    "response_times": deque(maxlen=100),
                    "successes": 0,
                    "failures": 0,
                    "avg_response_time": 0,
                    "success_rate": 0,
                }

            stats = self.connection_stats[url]
            stats["response_times"].append(response_time)

            if success:
                stats["successes"] += 1
            else:
                stats["failures"] += 1

            # Atualizar médias
            if stats["response_times"]:
                stats["avg_response_time"] = sum(stats["response_times"]) / len(
                    stats["response_times"]
                )

            total_attempts = stats["successes"] + stats["failures"]
            if total_attempts > 0:
                stats["success_rate"] = stats["successes"] / total_attempts


class AsyncWebSocketClient:
    """
    Cliente WebSocket assíncrono profissional para PocketOption
    """

    def __init__(self):
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connection_info: Optional[ConnectionInfo] = None
        self.server_time: Optional[ServerTime] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = CONNECTION_SETTINGS["max_reconnect_attempts"]

        # Melhorias de desempenho
        self._message_batcher = MessageBatcher()
        self._connection_pool = ConnectionPool()
        self._rate_limiter = asyncio.Semaphore(10)  # Máximo de 10 operações simultâneas
        self._message_cache: Dict[str, Any] = {}
        self._cache_ttl = 5.0  # TTL do cache em segundos

        # Otimização de processamento de mensagens
        self._message_handlers = {
            "0": self._handle_initial_message,
            "2": self._handle_ping_message,
            "40": self._handle_connection_message,
            "451-[": self._handle_json_message_wrapper,
            "42": self._handle_auth_message,
            "[[5,": self._handle_payout_message,
        }

    async def connect(self, urls: List[str], ssid: str) -> bool:
        """
        Conectar ao WebSocket da PocketOption com URLs de fallback

        Args:
            urls: Lista de URLs WebSocket para tentar
            ssid: ID de sessão para autenticação

        Returns:
            bool: True se conectado com sucesso
        """
        for url in urls:
            try:
                logger.info(f"Tentando conectar a {url}")

                # Configuração do contexto SSL
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Conectar com timeout
                ws = await asyncio.wait_for(
                    (_get_websockets_connect())(
                        url,
                        ssl=ssl_context,
                        extra_headers=_normalize_headers_for_websockets(DEFAULT_HEADERS),
                        ping_interval=CONNECTION_SETTINGS["ping_interval"],
                        ping_timeout=CONNECTION_SETTINGS["ping_timeout"],
                        close_timeout=CONNECTION_SETTINGS["close_timeout"],
                    ),
                    timeout=10.0,
                )
                self.websocket = ws  # type: ignore
                # Atualizar informações de conexão
                region = self._extract_region_from_url(url)
                self.connection_info = ConnectionInfo(
                    url=url,
                    region=region,
                    status=ConnectionStatus.CONNECTED,
                    connected_at=datetime.now(),
                    reconnect_attempts=self._reconnect_attempts,
                )

                logger.info(f"Conectado à região {region} com sucesso")
                # Iniciar manipulação de mensagens
                self._running = True

                # Enviar handshake inicial e aguardar conclusão
                await self._send_handshake(ssid)

                # Iniciar tarefas em segundo plano após conclusão do handshake
                await self._start_background_tasks()

                self._reconnect_attempts = 0
                return True

            except Exception as e:
                logger.warning(f"Falha ao conectar a {url}: {e}")
                if self.websocket:
                    await self.websocket.close()
                    self.websocket = None
                continue

        raise ConnectionError("Falha ao conectar a qualquer endpoint WebSocket")

    async def _handle_payout_message(self, message: str) -> None:
        """
        Gerencia mensagens relacionadas a informações de pagamento de ativos.
        Essas mensagens geralmente estão no formato `[[5, [...]]]`.
        O percentual de pagamento está no índice 5 da lista interna.

        Args:
            message: A mensagem WebSocket bruta contendo dados de pagamento.
        """
        try:
            # A mensagem começa com "[[5," e é uma string JSON.
            # Precisamos analisá-la como JSON.
            # Exemplo: [[5, ["5", "#AAPL", "Apple", "stock", 2, 50, ...]]]
            # A estrutura é uma lista contendo uma lista, onde o primeiro elemento
            # da lista interna é '5' (indicando dados de pagamento), e o restante são os dados.

            # Remover o inicial '[[5,' e o final ']]' e analisar o restante como JSON.
            # Uma maneira mais robusta é encontrar o primeiro '[' e o último ']' do array JSON real.

            # Encontrar o início do array JSON real
            json_start_index = message.find("[", message.find("[") + 1)
            # Encontrar o fim do array JSON real
            json_end_index = message.rfind("]")

            if json_start_index == -1 or json_end_index == -1:
                logger.warning(
                    f"Não foi possível encontrar array JSON válido na mensagem de pagamento: {message[:100]}..."
                )
                return

            # Extrair a string JSON interna que representa o array de arrays
            json_str = message[json_start_index : json_end_index + 1]

            # Analisar a string JSON extraída
            data: List[List[Any]] = json.loads(json_str)

            # Iterar pelas informações de pagamento de cada ativo
            for asset_data in data:
                # Garantir que asset_data é uma lista e tem elementos suficientes
                if isinstance(asset_data, list) and len(asset_data) > 5:
                    try:
                        # Extrair informações relevantes
                        asset_id = asset_data[0]
                        asset_symbol = asset_data[1]
                        asset_name = asset_data[2]
                        asset_type = asset_data[3]
                        payout_percentage = asset_data[5]  # Pagamento está no índice 5

                        payout_info = {
                            "id": asset_id,
                            "symbol": asset_symbol,
                            "name": asset_name,
                            "type": asset_type,
                            "payout": payout_percentage,
                        }
                        logger.debug(f"Informações de pagamento analisadas: {payout_info}")
                        # Emitir um evento com os dados de pagamento analisados
                        await self._emit_event("payout_update", payout_info)
                    except IndexError:
                        logger.warning(
                            f"Elemento de mensagem de pagamento ausente para asset_data: {asset_data}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Erro ao processar dados de pagamento de ativo individual {asset_data}: {e}"
                        )
                else:
                    logger.warning(
                        f"Formato inesperado para dados de pagamento de ativo: {asset_data}"
                    )

        except json.JSONDecodeError as e:
            logger.error(
                f"Falha ao decodificar JSON da mensagem de pagamento '{message[:100]}...': {e}"
            )
        except Exception as e:
            logger.error(
                f"Erro em _handle_payout_message para mensagem '{message[:100]}...': {e}"
            )

    async def disconnect(self):
        """Desconectar do WebSocket de forma graciosa"""
        logger.info("Desconectando do WebSocket")

        self._running = False

        # Cancelar tarefas em segundo plano
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # Fechar conexão WebSocket
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        # Atualizar status de conexão
        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=ConnectionStatus.DISCONNECTED,
                connected_at=self.connection_info.connected_at,
                reconnect_attempts=self.connection_info.reconnect_attempts,
            )

    async def send_message(self, message: str) -> None:
        """
        Enviar mensagem para o WebSocket

        Args:
            message: Mensagem a enviar
        """
        if not self.websocket or self.websocket.closed:
            raise WebSocketError("WebSocket não está conectado")

        try:
            await self.websocket.send(message)
            logger.debug(f"Mensagem enviada: {message}")
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem: {e}")
            raise WebSocketError(f"Falha ao enviar mensagem: {e}")

    async def send_message_optimized(self, message: str) -> None:
        """
        Enviar mensagem com otimização de agrupamento

        Args:
            message: Mensagem a enviar
        """
        async with self._rate_limiter:
            if not self.websocket or self.websocket.closed:
                raise WebSocketError("WebSocket não está conectado")

            try:
                start_time = time.time()

                # Adicionar ao lote
                batch = await self._message_batcher.add_message(message)

                # Enviar lote se pronto
                if batch:
                    for msg in batch:
                        await self.websocket.send(msg)
                        logger.debug(f"Mensagem em lote enviada: {msg}")

                # Atualizar estatísticas de conexão
                response_time = time.time() - start_time
                if self.connection_info:
                    await self._connection_pool.update_stats(
                        self.connection_info.url, response_time, True
                    )

            except Exception as e:
                logger.error(f"Falha ao enviar mensagem: {e}")
                if self.connection_info:
                    await self._connection_pool.update_stats(
                        self.connection_info.url, 0, False
                    )
                raise WebSocketError(f"Falha ao enviar mensagem: {e}")

    async def receive_messages(self) -> None:
        """
        Receber e processar mensagens continuamente
        """
        try:
            while self._running and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=CONNECTION_SETTINGS["message_timeout"],
                    )
                    await self._process_message(message)

                except asyncio.TimeoutError:
                    logger.warning("Timeout na recepção de mensagem")
                    continue
                except ConnectionClosed:
                    logger.warning("Conexão WebSocket fechada")
                    await self._handle_disconnect()
                    break

        except Exception as e:
            logger.error(f"Erro na recepção de mensagens: {e}")
            await self._handle_disconnect()

    def add_event_handler(self, event: str, handler: Callable) -> None:
        """
        Adicionar manipulador de eventos

        Args:
            event: Nome do evento
            handler: Função manipuladora
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def remove_event_handler(self, event: str, handler: Callable) -> None:
        """
        Remover manipulador de eventos

        Args:
            event: Nome do evento
            handler: Função manipuladora a remover
        """
        if event in self._event_handlers:
            try:
                self._event_handlers[event].remove(handler)
            except ValueError:
                pass

    async def _send_handshake(self, ssid: str) -> None:
        """Enviar mensagens de handshake inicial (seguindo exatamente o padrão da API antiga)"""
        try:
            # Aguardar mensagem de conexão inicial com "0" e "sid" (como na API antiga)
            logger.debug("Aguardando mensagem de handshake inicial...")
            if not self.websocket:
                raise WebSocketError("WebSocket não está conectado durante o handshake")
            initial_message = await asyncio.wait_for(
                self.websocket.recv(), timeout=10.0
            )
            logger.debug(f"Recebido inicial: {initial_message}")

            # Garantir que initial_message é uma string
            if isinstance(initial_message, memoryview):
                initial_message = bytes(initial_message).decode("utf-8")
            elif isinstance(initial_message, (bytes, bytearray)):
                initial_message = initial_message.decode("utf-8")

            # Verificar se é o formato de mensagem inicial esperado
            if initial_message.startswith("0") and "sid" in initial_message:
                # Enviar resposta "40" (como na API antiga)
                await self.send_message("40")
                logger.debug("Enviada resposta '40'")

                # Aguardar mensagem de estabelecimento de conexão com "40" e "sid"
                conn_message = await asyncio.wait_for(
                    self.websocket.recv(), timeout=10.0
                )
                logger.debug(f"Conexão recebida: {conn_message}")

                # Garantir que conn_message é uma string
                if isinstance(conn_message, memoryview):
                    conn_message_str = bytes(conn_message).decode("utf-8")
                elif isinstance(conn_message, (bytes, bytearray)):
                    conn_message_str = conn_message.decode("utf-8")
                else:
                    conn_message_str = conn_message
                if conn_message_str.startswith("40") and "sid" in conn_message_str:
                    # Enviar autenticação SSID (como na API antiga)
                    await self.send_message(ssid)
                    logger.debug("Enviada autenticação SSID")
                else:
                    logger.warning(
                        f"Formato de mensagem de conexão inesperado: {conn_message}"
                    )
            else:
                logger.warning(f"Formato de mensagem inicial inesperado: {initial_message}")

            logger.debug("Sequência de handshake concluída")

        except asyncio.TimeoutError:
            logger.error("Timeout no handshake - servidor não respondeu como esperado")
            raise WebSocketError("Timeout no handshake")
        except Exception as e:
            logger.error(f"Falha no handshake: {e}")
            raise

    async def _start_background_tasks(self) -> None:
        """Iniciar tarefas em segundo plano"""
        # Iniciar tarefa de ping
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Iniciar tarefa de recebimento de mensagens (iniciar apenas uma vez aqui)
        asyncio.create_task(self.receive_messages())

    async def _ping_loop(self) -> None:
        """Enviar mensagens de ping periódicas"""
        while self._running and self.websocket:
            try:
                await asyncio.sleep(CONNECTION_SETTINGS["ping_interval"])

                if self.websocket and not self.websocket.closed:
                    await self.send_message('42["ps"]')

                    # Atualizar último tempo de ping
                    if self.connection_info:
                        self.connection_info = ConnectionInfo(
                            url=self.connection_info.url,
                            region=self.connection_info.region,
                            status=self.connection_info.status,
                            connected_at=self.connection_info.connected_at,
                            last_ping=datetime.now(),
                            reconnect_attempts=self.connection_info.reconnect_attempts,
                        )

            except Exception as e:
                logger.error(f"Falha no ping: {e}")
                break

    async def _process_message(self, message) -> None:
        """
        Processar mensagem WebSocket recebida (seguindo exatamente o padrão da API antiga)

        Args:
            message: Mensagem bruta do WebSocket (bytes ou str)
        """
        try:
            # Tratar mensagens em bytes primeiro (como na API antiga) - contêm dados de saldo
            if isinstance(message, bytes):
                decoded_message = message.decode("utf-8")
                try:
                    # Tentar analisar como JSON (como na API antiga)
                    json_data = json.loads(decoded_message)
                    logger.debug(f"Mensagem JSON em bytes recebida: {json_data}")

                    # Tratar dados de saldo (como na API antiga)
                    if "balance" in json_data:
                        balance_data = {
                            "balance": json_data["balance"],
                            "currency": "USD",  # Moeda padrão
                            "is_demo": bool(json_data.get("isDemo", 1)),
                        }
                        if "uid" in json_data:
                            balance_data["uid"] = json_data["uid"]

                        logger.info(f"Dados de saldo recebidos: {balance_data}")
                        await self._emit_event("balance_data", balance_data)

                    # Tratar dados de ordem (como na API antiga)
                    elif "requestId" in json_data and json_data["requestId"] == "buy":
                        await self._emit_event("order_data", json_data)

                    # Tratar outros dados JSON
                    else:
                        await self._emit_event("json_data", json_data)

                except json.JSONDecodeError:
                    # Se não for JSON, tratar como mensagem em bytes regular
                    logger.debug(f"Mensagem em bytes não-JSON: {decoded_message[:100]}...")

                return

            # Converter bytes para string se necessário
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            logger.debug(f"Mensagem recebida: {message}")

            # Tratar diferentes tipos de mensagens
            if message.startswith("0") and "sid" in message:
                await self.send_message("40")

            elif message == "2":
                await self.send_message("3")

            elif message.startswith("40") and "sid" in message:
                # Conexão estabelecida
                await self._emit_event("connected", {})

            elif message.startswith("451-["):
                # Analisar mensagem JSON
                json_part = message.split("-", 1)[1]
                data = json.loads(json_part)
                await self._handle_json_message(data)

            elif message.startswith("42") and "NotAuthorized" in message:
                logger.error("Falha na autenticação: SSID inválido")
                await self._emit_event("auth_error", {"message": "SSID inválido"})

        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")

    async def _handle_initial_message(self, message: str) -> None:
        """Tratar mensagem de conexão inicial"""
        if "sid" in message:
            await self.send_message("40")

    async def _handle_ping_message(self, message: str) -> None:
        """Tratar mensagem de ping"""
        await self.send_message("3")

    async def _handle_connection_message(self, message: str) -> None:
        """Tratar mensagem de estabelecimento de conexão"""
        if "sid" in message:
            await self._emit_event("connected", {})

    async def _handle_json_message_wrapper(self, message: str) -> None:
        """Tratar wrapper de mensagem JSON"""
        json_part = message.split("-", 1)[1]
        data = json.loads(json_part)
        await self._handle_json_message(data)

    async def _handle_auth_message(self, message: str) -> None:
        """Tratar mensagem de autenticação"""
        if "NotAuthorized" in message:
            logger.error("Falha na autenticação: SSID inválido")
            await self._emit_event("auth_error", {"message": "SSID inválido"})

    async def _process_message_optimized(self, message) -> None:
        """
        Processar mensagem WebSocket recebida com otimização

        Args:
            message: Mensagem bruta do WebSocket (bytes ou str)
        """
        try:
            # Converter bytes para string se necessário
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            logger.debug(f"Mensagem recebida: {message}")

            # Verificar cache primeiro
            message_hash = hash(message)
            cached_time = self._message_cache.get(f"{message_hash}_time")

            if cached_time and time.time() - cached_time < self._cache_ttl:
                # Usar resultado de processamento em cache
                cached_result = self._message_cache.get(str(message_hash))
                if cached_result:
                    await self._emit_event("cached_message", cached_result)
                    return

            # Roteamento rápido de mensagens
            for prefix, handler in self._message_handlers.items():
                if message.startswith(prefix):
                    await handler(message)
                    break
            else:
                # Tipo de mensagem desconhecido
                logger.warning(f"Tipo de mensagem desconhecido: {message[:20]}...")

            # Armazenar resultado de processamento em cache
            self._message_cache[str(message_hash)] = {
                "processed": True,
                "type": "unknown",
            }
            self._message_cache[f"{message_hash}_time"] = time.time()

        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")

    async def _handle_json_message(self, data: List[Any]) -> None:
        """
        Tratar mensagens formatadas em JSON

        Args:
            data: Dados JSON analisados
        """
        if not data or len(data) < 1:
            return

        event_type = data[0]
        event_data = data[1] if len(data) > 1 else {}

        # Tratar eventos específicos
        if event_type == "successauth":
            await self._emit_event("authenticated", event_data)

        elif event_type == "successupdateBalance":
            await self._emit_event("balance_updated", event_data)

        elif event_type == "successopenOrder":
            await self._emit_event("order_opened", event_data)

        elif event_type == "successcloseOrder":
            await self._emit_event("order_closed", event_data)

        elif event_type == "updateStream":
            await self._emit_event("stream_update", event_data)

        elif event_type == "loadHistoryPeriod":
            await self._emit_event("candles_received", event_data)

        elif event_type == "updateHistoryNew":
            await self._emit_event("history_update", event_data)

        else:
            await self._emit_event(
                "unknown_event", {"type": event_type, "data": event_data}
            )

    async def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        """
        Emitir evento para manipuladores registrados

        Args:
            event: Nome do evento
            data: Dados do evento
        """
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Erro no manipulador de eventos para {event}: {e}")

    async def _handle_disconnect(self) -> None:
        """Tratar desconexão do WebSocket"""
        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=ConnectionStatus.DISCONNECTED,
                connected_at=self.connection_info.connected_at,
                last_ping=self.connection_info.last_ping,
                reconnect_attempts=self.connection_info.reconnect_attempts,
            )

        await self._emit_event("disconnected", {})

        # Tentar reconexão se habilitado
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            logger.info(
                f"Tentando reconexão {self._reconnect_attempts}/{self._max_reconnect_attempts}"
            )
            await asyncio.sleep(CONNECTION_SETTINGS["reconnect_delay"])
            # Nota: A lógica de reconexão seria tratada pelo cliente principal

    def _extract_region_from_url(self, url: str) -> str:
        """Extrair nome da região da URL"""
        try:
            # Extrair de URLs como "wss://api-eu.po.market/..."
            parts = url.split("//")[1].split(".")[0]
            if "api-" in parts:
                return parts.replace("api-", "").upper()
            elif "demo" in parts:
                return "DEMO"
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    @property
    def is_connected(self) -> bool:
        """Verificar se o WebSocket está conectado"""
        return (
            self.websocket is not None
            and not self.websocket.closed
            and self.connection_info is not None
            and self.connection_info.status == ConnectionStatus.CONNECTED
        )