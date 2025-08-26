"""
# Autor: ByMyselfJhones
# Função: ConnectionKeepAlive
# Descrição:
# - Gerenciador de conexão keep-alive assíncrono para API da PocketOption
# - Suporta reconexão automática, monitoramento de saúde e tratamento de eventos
# - Mantém compatibilidade com padrões da API antiga
"""

import asyncio
from typing import Optional, List, Callable, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect, WebSocketClientProtocol

from models import ConnectionInfo, ConnectionStatus
from constants import REGIONS

class ConnectionKeepAlive:
    """
    Gerenciador avançado de conexão keep-alive baseado em padrões da API antiga
    """

    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo

        # Estado da conexão
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connection_info: Optional[ConnectionInfo] = None
        self.is_connected = False
        self.should_reconnect = True

        # Tarefas em segundo plano
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._message_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None

        # Configurações de keep-alive
        self.ping_interval = 20  # segundos (igual à API antiga)
        self.reconnect_delay = 5  # segundos
        self.max_reconnect_attempts = 10
        self.current_reconnect_attempts = 0

        # Manipuladores de eventos
        self._event_handlers: Dict[str, List[Callable]] = {}

        # Pool de conexões com múltiplas regiões
        self.available_urls = (
            REGIONS.get_demo_regions() if is_demo else REGIONS.get_all()
        )
        self.current_url_index = 0

        # Estatísticas
        self.connection_stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "total_reconnects": 0,
            "last_ping_time": None,
            "last_pong_time": None,
            "total_messages_sent": 0,
            "total_messages_received": 0,
        }

        logger.info(
            f"Gerenciador keep-alive inicializado com {len(self.available_urls)} regiões disponíveis"
        )

    async def start_persistent_connection(self) -> bool:
        """
        Iniciar uma conexão persistente com keep-alive automático
        Similar à abordagem de thread daemon da API antiga, mas com async moderno
        """
        logger.info("Iniciando conexão persistente com keep-alive...")

        try:
            # Conexão inicial
            if await self._establish_connection():
                # Iniciar todas as tarefas em segundo plano
                await self._start_background_tasks()
                logger.success(
                    "Sucesso: Conexão persistente estabelecida com keep-alive ativo"
                )
                return True
            else:
                logger.error("Erro: Falha ao estabelecer conexão inicial")
                return False

        except Exception as e:
            logger.error(f"Erro: Erro ao iniciar conexão persistente: {e}")
            return False

    async def stop_persistent_connection(self):
        """Parar a conexão persistente e todas as tarefas em segundo plano"""
        logger.info("Parando conexão persistente...")

        self.should_reconnect = False

        # Cancelar todas as tarefas em segundo plano
        tasks = [
            self._ping_task,
            self._reconnect_task,
            self._message_task,
            self._health_task,
        ]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Fechar conexão
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        self.is_connected = False
        logger.info("Sucesso: Conexão persistente parada")

    async def _establish_connection(self) -> bool:
        """
        Estabelecer conexão com URLs de fallback (como na API antiga)
        """
        for attempt in range(len(self.available_urls)):
            url = self.available_urls[self.current_url_index]

            try:
                logger.info(
                    f"Conectando: Tentando conexão com {url} (tentativa {attempt + 1})"
                )

                # Contexto SSL (como na API antiga)
                import ssl

                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Conectar com cabeçalhos (como na API antiga)
                self.websocket = await asyncio.wait_for(
                    connect(
                        url,
                        ssl=ssl_context,
                        extra_headers={
                            "Origin": "https://pocketoption.com",
                            "Cache-Control": "no-cache",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                        ping_interval=None,  # Gerenciamos pings manualmente
                        ping_timeout=None,
                        close_timeout=10,
                    ),
                    timeout=15.0,
                )

                # Atualizar informações de conexão
                region = self._extract_region_from_url(url)
                self.connection_info = ConnectionInfo(
                    url=url,
                    region=region,
                    status=ConnectionStatus.CONNECTED,
                    connected_at=datetime.now(),
                    reconnect_attempts=self.current_reconnect_attempts,
                )

                self.is_connected = True
                self.current_reconnect_attempts = 0
                self.connection_stats["total_connections"] += 1
                self.connection_stats["successful_connections"] += 1

                # Enviar handshake inicial (como na API antiga)
                await self._send_handshake()

                logger.success(f"Sucesso: Conectado à região {region} com sucesso")
                await self._emit_event("connected", {"url": url, "region": region})

                return True

            except Exception as e:
                logger.warning(f"Atenção: Falha ao conectar a {url}: {e}")

                # Tentar próxima URL
                self.current_url_index = (self.current_url_index + 1) % len(
                    self.available_urls
                )

                if self.websocket:
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass
                    self.websocket = None

                await asyncio.sleep(1)  # Breve atraso antes da próxima tentativa

        return False

    async def _send_handshake(self):
        """Enviar sequência de handshake inicial (como na API antiga)"""
        try:
            if not self.websocket:
                raise RuntimeError("Handshake chamado sem conexão websocket.")
            # Aguardar mensagem de conexão inicial
            initial_message = await asyncio.wait_for(
                self.websocket.recv(), timeout=10.0
            )
            logger.debug(f"Recebido inicial: {initial_message}")

            # Enviar sequência de handshake (como na API antiga)
            await self.websocket.send("40")
            await asyncio.sleep(0.1)

            # Aguardar estabelecimento de conexão
            conn_message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            logger.debug(f"Conexão recebida: {conn_message}")

            # Enviar autenticação SSID
            await self.websocket.send(self.ssid)
            logger.debug("Handshake concluído")

            self.connection_stats["total_messages_sent"] += 2

        except Exception as e:
            logger.error(f"Falha no handshake: {e}")
            raise

    async def _start_background_tasks(self):
        """Iniciar todas as tarefas em segundo plano (como tarefas concorrentes da API antiga)"""
        logger.info("Persistente: Iniciando tarefas de keep-alive em segundo plano...")

        # Tarefa de ping (a cada 20 segundos como na API antiga)
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Tarefa de recebimento de mensagens
        self._message_task = asyncio.create_task(self._message_loop())

        # Tarefa de monitoramento de saúde
        self._health_task = asyncio.create_task(self._health_monitor_loop())

        # Tarefa de monitoramento de reconexão
        self._reconnect_task = asyncio.create_task(self._reconnection_monitor())

        logger.success("Sucesso: Todas as tarefas em segundo plano iniciadas")

    async def _ping_loop(self):
        """
        Loop de ping contínuo (como a função send_ping da API antiga)
        Envia '42["ps"]' a cada 20 segundos
        """
        logger.info("Ping: Iniciando loop de ping...")

        while self.should_reconnect:
            try:
                if self.is_connected and self.websocket:
                    # Enviar mensagem de ping (formato exato da API antiga)
                    await self.websocket.send('42["ps"]')
                    self.connection_stats["last_ping_time"] = datetime.now()
                    self.connection_stats["total_messages_sent"] += 1

                    logger.debug("Ping: Ping enviado")

                await asyncio.sleep(self.ping_interval)

            except ConnectionClosed:
                logger.warning("Conectando: Conexão fechada durante ping")
                self.is_connected = False
                break
            except Exception as e:
                logger.error(f"Erro: Falha no ping: {e}")
                self.is_connected = False
                break

    async def _message_loop(self):
        """
        Loop contínuo de recebimento de mensagens (como o websocket_listener da API antiga)
        """
        logger.info("Mensagem: Iniciando loop de mensagens...")

        while self.should_reconnect:
            try:
                if self.is_connected and self.websocket:
                    try:
                        # Receber mensagem com timeout
                        message = await asyncio.wait_for(
                            self.websocket.recv(), timeout=30.0
                        )

                        self.connection_stats["total_messages_received"] += 1
                        await self._process_message(message)

                    except asyncio.TimeoutError:
                        logger.debug("Mensagem: Timeout no recebimento de mensagem (normal)")
                        continue
                else:
                    await asyncio.sleep(1)

            except ConnectionClosed:
                logger.warning("Conectando: Conexão fechada durante recebimento de mensagem")
                self.is_connected = False
                break
            except Exception as e:
                logger.error(f"Erro: Erro no loop de mensagens: {e}")
                self.is_connected = False
                break

    async def _health_monitor_loop(self):
        """Monitorar a saúde da conexão e acionar reconexões se necessário"""
        logger.info("Saúde: Iniciando monitor de saúde...")

        while self.should_reconnect:
            try:
                await asyncio.sleep(30)  # Verificar a cada 30 segundos

                if not self.is_connected:
                    logger.warning("Saúde: Verificação de saúde: Conexão perdida")
                    continue

                # Verificar se recebemos um pong recentemente
                if self.connection_stats["last_ping_time"]:
                    time_since_ping = (
                        datetime.now() - self.connection_stats["last_ping_time"]
                    )
                    if time_since_ping > timedelta(
                        seconds=60
                    ):  # Sem resposta por 60 segundos
                        logger.warning(
                            "Saúde: Verificação de saúde: Sem resposta de ping, conexão pode estar morta"
                        )
                        self.is_connected = False

                # Verificar estado do WebSocket
                if self.websocket and self.websocket.closed:
                    logger.warning("Saúde: Verificação de saúde: WebSocket está fechado")
                    self.is_connected = False

            except Exception as e:
                logger.error(f"Erro: Erro no monitor de saúde: {e}")

    async def _reconnection_monitor(self):
        """
        Monitorar desconexões e reconectar automaticamente (como na API antiga)
        """
        logger.info("Persistente: Iniciando monitor de reconexão...")

        while self.should_reconnect:
            try:
                await asyncio.sleep(5)  # Verificar a cada 5 segundos

                if not self.is_connected and self.should_reconnect:
                    logger.warning(
                        "Persistente: Desconexão detectada, tentando reconectar..."
                    )

                    self.current_reconnect_attempts += 1
                    self.connection_stats["total_reconnects"] += 1

                    if self.current_reconnect_attempts <= self.max_reconnect_attempts:
                        logger.info(
                            f"Persistente: Tentativa de reconexão {self.current_reconnect_attempts}/{self.max_reconnect_attempts}"
                        )

                        # Limpar conexão atual
                        if self.websocket:
                            try:
                                await self.websocket.close()
                            except Exception:
                                pass
                            self.websocket = None

                        # Tentar reconectar
                        success = await self._establish_connection()

                        if success:
                            logger.success("Sucesso: Reconexão bem-sucedida!")
                            await self._emit_event(
                                "reconnected",
                                {
                                    "attempt": self.current_reconnect_attempts,
                                    "url": self.connection_info.url
                                    if self.connection_info
                                    else None,
                                },
                            )
                        else:
                            logger.error(
                                f"Erro: Tentativa de reconexão {self.current_reconnect_attempts} falhou"
                            )
                            await asyncio.sleep(self.reconnect_delay)
                    else:
                        logger.error(
                            f"Erro: Máximo de tentativas de reconexão ({self.max_reconnect_attempts}) atingido"
                        )
                        await self._emit_event(
                            "max_reconnects_reached",
                            {"attempts": self.current_reconnect_attempts},
                        )
                        break

            except Exception as e:
                logger.error(f"Erro: Erro no monitor de reconexão: {e}")

    async def _process_message(self, message):
        """Processar mensagens recebidas (como o on_message da API antiga)"""
        try:
            # Converter bytes para string se necessário
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            logger.debug(f"Mensagem: Recebida: {message[:100]}...")

            # Tratar ping-pong (como na API antiga)
            if message == "2":
                if self.websocket:
                    await self.websocket.send("3")
                    self.connection_stats["last_pong_time"] = datetime.now()
                    logger.debug("Ping: Pong enviado")
                return

            # Tratar sucesso de autenticação (como na API antiga)
            if "successauth" in message:
                logger.success("Sucesso: Autenticação bem-sucedida")
                await self._emit_event("authenticated", {})
                return

            # Tratar outros tipos de mensagens
            await self._emit_event("message_received", {"message": message})

        except Exception as e:
            logger.error(f"Erro: Erro ao processar mensagem: {e}")

    async def send_message(self, message: str) -> bool:
        """Enviar mensagem com verificação de conexão"""
        try:
            if self.is_connected and self.websocket:
                await self.websocket.send(message)
                self.connection_stats["total_messages_sent"] += 1
                logger.debug(f"Mensagem: Enviada: {message[:50]}...")
                return True
            else:
                logger.warning("Atenção: Não é possível enviar mensagem: não conectado")
                return False
        except Exception as e:
            logger.error(f"Erro: Falha ao enviar mensagem: {e}")
            self.is_connected = False
            return False

    def add_event_handler(self, event: str, handler: Callable):
        """Adicionar manipulador de eventos"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    async def _emit_event(self, event: str, data: Any):
        """Emitir evento para manipuladores"""
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Erro: Erro no manipulador de eventos para {event}: {e}")

    def _extract_region_from_url(self, url: str) -> str:
        """Extrair nome da região da URL"""
        try:
            parts = url.split("//")[1].split(".")[0]
            if "api-" in parts:
                return parts.replace("api-", "").upper()
            elif "demo" in parts:
                return "DEMO"
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def get_connection_stats(self) -> Dict[str, Any]:
        """Obter estatísticas detalhadas de conexão"""
        return {
            **self.connection_stats,
            "is_connected": self.is_connected,
            "current_url": self.connection_info.url if self.connection_info else None,
            "current_region": self.connection_info.region
            if self.connection_info
            else None,
            "reconnect_attempts": self.current_reconnect_attempts,
            "uptime": (
                datetime.now() - self.connection_info.connected_at
                if self.connection_info and self.connection_info.connected_at
                else timedelta()
            ),
            "available_regions": len(self.available_urls),
        }

    async def connect_with_keep_alive(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Estabelecer uma conexão persistente com keep-alive, opcionalmente usando uma lista de regiões."""
        # Opcionalmente atualizar available_urls se regiões forem fornecidas
        if regions:
            # Assumir que regiões são URLs ou nomes de regiões; adaptar conforme necessário
            self.available_urls = regions
            self.current_url_index = 0
        return await self.start_persistent_connection()

    async def disconnect(self) -> None:
        """Desconectar e limpar conexão persistente."""
        await self.stop_persistent_connection()

    def get_stats(self) -> Dict[str, Any]:
        """Retornar estatísticas de conexão (alias para get_connection_stats)."""
        return self.get_connection_stats()

async def demo_keep_alive():
    """Demonstração do gerenciador de conexão keep-alive"""

    # Exemplo de SSID completo
    ssid = r'42["auth",{"session":"n1p5ah5u8t9438rbunpgrq0hlq","isDemo":1,"uid":0,"platform":1}]'

    # Criar gerenciador de keep-alive
    keep_alive = ConnectionKeepAlive(ssid, is_demo=True)

    # Adicionar manipuladores de eventos
    async def on_connected(data):
        logger.success(f"Sucesso: Conectado a: {data}")

    async def on_reconnected(data):
        logger.success(f"Persistente: Reconectado após {data['attempt']} tentativas")

    async def on_message(data):
        logger.info(f"Mensagem: Mensagem: {data['message'][:50]}...")

    keep_alive.add_event_handler("connected", on_connected)
    keep_alive.add_event_handler("reconnected", on_reconnected)
    keep_alive.add_event_handler("message_received", on_message)

    try:
        # Iniciar conexão persistente
        success = await keep_alive.start_persistent_connection()

        if success:
            logger.info(
                "Iniciando: Conexão keep-alive iniciada, manterá a conexão automaticamente..."
            )

            # Deixar rodar por um tempo para demonstrar keep-alive
            for i in range(60):  # Rodar por 1 minuto
                await asyncio.sleep(1)

                # Imprimir estatísticas a cada 10 segundos
                if i % 10 == 0:
                    stats = keep_alive.get_connection_stats()
                    logger.info(
                        f"Estatísticas: Stats: Conectado={stats['is_connected']}, "
                        f"Mensagens enviadas={stats['total_messages_sent']}, "
                        f"Mensagens recebidas={stats['total_messages_received']}, "
                        f"Tempo ativo={stats['uptime']}"
                    )

                # Enviar uma mensagem de teste a cada 30 segundos
                if i % 30 == 0 and i > 0:
                    await keep_alive.send_message('42["test"]')

        else:
            logger.error("Erro: Falha ao iniciar conexão keep-alive")

    finally:
        # Desligamento limpo
        await keep_alive.stop_persistent_connection()

if __name__ == "__main__":
    logger.info("Testando: Testando Gerenciador de Conexão Keep-Alive Aprimorado")
    asyncio.run(demo_keep_alive())