"""
# Autor: ByMyselfJhones
# Função: AsyncPocketOptionClient com login por e-mail/senha (SSID Automaticamente Gerado)
# Descrição:
# - Cliente assíncrono para API da PocketOption
# - Gerencia conexões WebSocket, ordens, saldos e dados de candles
# - Suporta:
#    * Autenticação por SSID ou via login por e-mail/senha -> captura cookie 'ci_session' e usa como SSID
# - Suporta modo Conta Demo/Conta Real, reconexão automática e monitoramento de erros
"""

import asyncio
import json
import time
import uuid
from contextlib import suppress
from typing import Optional, List, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import requests
from requests.exceptions import RequestException
from loguru import logger

# Selenium (fallback opcional)
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception:  # não obrigar selenium se não instalado
    uc = None

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

    Agora com suporte a:
    - ssid (string completa ou id de sessão) OU
    - email + password  -> login automático e captura do SSID (cookie 'ci_session')
    """

    def __init__(
        self,
        ssid: Optional[str] = None,
        # novos parâmetros:
        email: Optional[str] = None,
        password: Optional[str] = None,
        #
        is_demo: bool = True,
        region: Optional[str] = None,
        uid: int = 0,
        platform: int = 1,
        is_fast_history: bool = True,
        persistent_connection: bool = False,
        auto_reconnect: bool = True,
        enable_logging: bool = True,
        # ajustes/fallbacks de login:
        login_language: str = "pt",        # caminho /pt/ ou /en/
        selenium_headless: bool = True,    # fallback headless
        selenium_wait_timeout: int = 25,   # segundos
    ):
        """
        Inicializa cliente assíncrono da PocketOption com monitoramento aprimorado

        Args:
            ssid: SSID completo (42["auth", {...}]) ou o valor bruto do cookie 'ci_session' ou ainda um session_id simples
            email/password: usados se ssid não for fornecido; o client fará login e obterá o cookie 'ci_session'
            is_demo: usar conta demo? (afeta a flag 'isDemo' do auth WS)
            region: região preferida
            uid/platform/is_fast_history: mantidos p/ compatibilidade (uid pode ser 0; o servidor resolve pelo cookie)
            persistent_connection/auto_reconnect/enable_logging: comportamentos de conexão
            login_language: subpath do site (pt, en, etc.) para o login
            selenium_headless: se True, usa Chrome headless no fallback
            selenium_wait_timeout: timeout de espera de elementos na página
        """
        # Preferências
        self.enable_logging = enable_logging
        if not enable_logging:
            logger.remove()
            logger.add(lambda msg: None, level="CRITICAL")

        # Credenciais
        self.email = email
        self.password = password
        self.login_language = (login_language or "pt").strip("/")

        # Sessão/SSID
        self.raw_ssid = ssid or ""
        self.is_demo = is_demo
        self.preferred_region = region
        self.uid = uid
        self.platform = platform
        self.is_fast_history = is_fast_history
        self.persistent_connection = persistent_connection
        self.auto_reconnect = auto_reconnect

        self.selenium_headless = selenium_headless
        self.selenium_wait_timeout = int(selenium_wait_timeout)

        # Estado de SSID/Session
        self._original_demo = None
        self.session_id: str = ""
        self._complete_ssid: Optional[str] = None

        # Se veio um SSID já no formato completo, parseia; caso contrário, trata como sessão/cookie bruto
        if self.raw_ssid:
            if self.raw_ssid.startswith('42["auth",'):
                self._parse_complete_ssid(self.raw_ssid)
            else:
                # Pode ser o cookie 'ci_session' (a:4:{...}HASH) ou um id simples
                self.session_id = self.raw_ssid

        # Componentes principais e estados internos
        self._websocket = AsyncWebSocketClient()
        self._balance: Optional[Balance] = None
        self._orders: Dict[str, OrderResult] = {}
        self._active_orders: Dict[str, OrderResult] = {}
        self._order_results: Dict[str, OrderResult] = {}
        self._candles_cache: Dict[str, List[Candle]] = {}
        self._server_time: Optional[ServerTime] = None
        self._event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._setup_event_handlers()

        self._error_monitor = error_monitor
        self._health_checker = health_checker

        self._operation_metrics: Dict[str, List[float]] = defaultdict(list)
        self._last_health_check = time.time()

        self._keep_alive_manager = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._is_persistent = False

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
            f"Cliente PocketOption inicializado (demo={is_demo}, uid={self.uid}, persistente={persistent_connection}) com login {'via SSID' if bool(ssid) else 'via email/senha' if (email and password) else 'sem credenciais definidas'}"
            if enable_logging
            else ""
        )

    # ===================== Login Helpers =====================

    def _mask(self, s: str, keep: int = 6) -> str:
        """Mascara strings sensíveis para logs"""
        if not s:
            return ""
        if len(s) <= keep * 2:
            return "*" * len(s)
        return f"{s[:keep]}...{s[-keep:]}"

    def _base_site(self) -> str:
        return "https://pocketoption.com"

    def _login_urls(self) -> Dict[str, str]:
        lang = self.login_language
        return {
            "login_page": f"{self._base_site()}/{lang}/login/",
            "home": f"{self._base_site()}/{lang}/",
            # endpoints comuns (alguns clientes usam ajax/login/ ou signin/)
            "ajax_login": f"{self._base_site()}/ajax/login/",
            "ajax_signin": f"{self._base_site()}/signin/",
        }

    def _obtain_ci_session_via_http(self) -> Optional[str]:
        """
        Tenta executar login HTTP para capturar o cookie 'ci_session'.
        Nota: endpoints podem mudar; por isso há fallback Selenium.
        """
        urls = self._login_urls()
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": urls["home"],
        })

        try:
            # Carrega página para obter cookies iniciais/CSRF (se houver)
            session.get(urls["login_page"], timeout=20)

            candidate_payloads = [
                {"email": self.email, "password": self.password},
                {"login": self.email, "password": self.password},
                {"username": self.email, "password": self.password},
            ]

            for endpoint in ("ajax_login", "ajax_signin"):
                post_url = urls[endpoint]
                for payload in candidate_payloads:
                    try:
                        session.post(post_url, data=payload, timeout=20, allow_redirects=True)
                    except RequestException:
                        continue

            # alguns fluxos setam cookie após navegar
            session.get(urls["home"], timeout=15)

            # busca cookie do domínio raiz (CodeIgniter default: 'ci_session')
            for c in session.cookies:
                if "ci_session" in c.name.lower() and c.value:
                    cookie_val = c.value
                    logger.info(f"Login HTTP obteve cookie ci_session: {self._mask(cookie_val)}")
                    return cookie_val

        except RequestException as e:
            logger.warning(f"Login HTTP falhou: {e}")

        return None

    def _obtain_ci_session_via_selenium(self) -> Optional[str]:
        """
        Fallback por Selenium (undetected-chromedriver) para logar e capturar 'ci_session'
        """
        if uc is None:
            logger.warning("Selenium/undetected-chromedriver não instalado. Pulei fallback Selenium.")
            return None

        urls = self._login_urls()

        options = uc.ChromeOptions()
        if self.selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--lang=pt-BR")

        driver = None
        try:
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(60)

            driver.get(urls["login_page"])

            # Seletores comuns (ajuste se seu front for diferente)
            candidates_email = [
                (By.NAME, "email"),
                (By.NAME, "login"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.ID, "email"),
            ]
            candidates_password = [
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.ID, "password"),
            ]
            candidates_submit = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "button.login__btn"),
                (By.XPATH, "//button[contains(.,'Entrar') or contains(.,'Login') or contains(.,'Sign in')]"),
            ]

            # encontra campo e-mail
            email_elt = None
            for by, sel in candidates_email:
                with suppress(Exception):
                    email_elt = WebDriverWait(driver, self.selenium_wait_timeout).until(
                        EC.presence_of_element_located((by, sel))
                    )
                    if email_elt:
                        break
            if not email_elt:
                raise RuntimeError("Campo de e-mail não encontrado na página de login.")

            # encontra campo senha
            pass_elt = None
            for by, sel in candidates_password:
                with suppress(Exception):
                    pass_elt = WebDriverWait(driver, self.selenium_wait_timeout).until(
                        EC.presence_of_element_located((by, sel))
                    )
                    if pass_elt:
                        break
            if not pass_elt:
                raise RuntimeError("Campo de senha não encontrado na página de login.")

            email_elt.clear()
            email_elt.send_keys(self.email)
            pass_elt.clear()
            pass_elt.send_keys(self.password)

            # clicar no botão de submit
            submit_elt = None
            for by, sel in candidates_submit:
                with suppress(Exception):
                    submit_elt = driver.find_element(by, sel)
                    if submit_elt:
                        break
            if not submit_elt:
                pass_elt.submit()
            else:
                submit_elt.click()

            # Espera redirecionar/logar (procura algum elemento do painel)
            with suppress(Exception):
                WebDriverWait(driver, self.selenium_wait_timeout).until(
                    EC.url_contains("/cabinet")
                )
            # como alguns ambientes não redirecionam, navega pra home
            with suppress(Exception):
                driver.get(urls["home"])

            # pega cookies e procura ci_session
            cookies = driver.get_cookies()
            for c in cookies:
                name = (c.get("name") or "").lower()
                val = c.get("value") or ""
                if "ci_session" in name and val:
                    logger.info(f"Login Selenium obteve cookie ci_session: {self._mask(val)}")
                    return val

        except Exception as e:
            logger.warning(f"Login Selenium falhou: {e}")
        finally:
            with suppress(Exception):
                if driver:
                    driver.quit()

        return None

    async def _ensure_session_credentials(self) -> None:
        """
        Garante que self.session_id esteja pronto.
        Se não houver SSID configurado, e houver email+password, tenta login HTTP e depois Selenium (em threads).
        """
        if self.session_id:
            return

        if not (self.email and self.password):
            raise AuthenticationError(
                "Nenhum SSID e nenhuma combinação email/senha fornecida para autenticação."
            )

        logger.info("Nenhum SSID fornecido. Tentando login via HTTP para obter 'ci_session'...")

        # executa métodos bloqueantes em thread para não travar o loop
        cookie_val = await asyncio.to_thread(self._obtain_ci_session_via_http)

        if not cookie_val:
            logger.info("Login HTTP não retornou 'ci_session'. Tentando fallback via Selenium...")
            cookie_val = await asyncio.to_thread(self._obtain_ci_session_via_selenium)

        if not cookie_val:
            raise AuthenticationError("Falha ao obter 'ci_session' por HTTP e Selenium.")

        # Guarda o cookie (é exatamente o valor que você colava como 'session' no 42['auth',...])
        self.session_id = cookie_val
        self.raw_ssid = ""  # limpa formato completo, vamos sempre construir a partir de session_id

    # ===================== Fim dos Helpers de Login =====================

    def _setup_event_handlers(self):
        """Configurar manipuladores de eventos WebSocket"""
        self._websocket.add_event_handler("authenticated", self._on_authenticated)
        self._websocket.add_event_handler("balance_updated", self._on_balance_updated)
        self._websocket.add_event_handler("balance_data", self._on_balance_data)
        self._websocket.add_event_handler("order_opened", self._on_order_opened)
        self._websocket.add_event_handler("order_closed", self._on_order_closed)
        self._websocket.add_event_handler("stream_update", self._on_stream_update)
        self._websocket.add_event_handler("candles_received", self._on_candles_received)
        self._websocket.add_event_handler("disconnected", self._on_disconnected)
        self._websocket.add_event_handler("json_data", self._on_json_data)

    async def connect(
        self, regions: Optional[List[str]] = None, persistent: Optional[bool] = None
    ) -> tuple[bool, str]:
        """
        Conectar à PocketOption com suporte a múltiplas regiões.
        Retorna (ok: bool, mensagem: str)
        """
        logger.info("Conectando à PocketOption...")

        # Garante que temos session_id (gera via email/senha se preciso)
        try:
            await self._ensure_session_credentials()
        except AuthenticationError as e:
            logger.error(f"Falha de autenticação: {e}")
            await self._error_monitor.record_error(
                error_type="auth_failed",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.AUTHENTICATION,
                message=str(e),
            )
            return False, "Falha ao autenticar"

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
            return False, "Falha ao conectar"

    async def _start_regular_connection(
        self, regions: Optional[List[str]] = None
    ) -> tuple[bool, str]:
        """Iniciar conexão regular (comportamento existente). Retorna (ok, msg)."""
        logger.info("Iniciando conexão regular...")

        if not regions:
            if self.is_demo:
                demo_urls = REGIONS.get_demo_regions()
                regions = []
                all_regions = REGIONS.get_all_regions()
                for name, url in all_regions.items():
                    if url in demo_urls:
                        regions.append(name)
                logger.info(f"Modo demo: Usando regiões demo: {regions}")
            else:
                all_regions = REGIONS.get_all_regions()
                regions = [name for name, url in all_regions.items() if "DEMO" not in name.upper()]
                logger.info(f"Modo live: Usando regiões não-demo: {regions}")

        self._connection_stats["total_connections"] += 1
        self._connection_stats["connection_start_time"] = time.time()

        for region in regions:
            try:
                region_url = REGIONS.get_region(region)
                if not region_url:
                    continue

                urls = [region_url]
                logger.info(f"Tentando região: {region} com URL: {region_url}")

                ssid_message = self._format_session_message()
                success = await self._websocket.connect(urls, ssid_message)

                if success:
                    logger.info(f" Conectado à região: {region}")

                    await self._wait_for_authentication()
                    await self._initialize_data()
                    await self._start_keep_alive_tasks()

                    logger.info("Conectado e autenticado com sucesso")
                    return True, "Conexão bem sucedida"

            except Exception as e:
                logger.warning(f"Falha ao conectar à região {region}: {e}")
                continue

        return False, "Falha ao conectar"

    async def _start_persistent_connection(
        self, regions: Optional[List[str]] = None
    ) -> tuple[bool, str]:
        """Iniciar conexão persistente com keep-alive (como API antiga). Retorna (ok, msg)."""
        logger.info("Iniciando conexão persistente com keep-alive automático...")

        from .connection_keep_alive import ConnectionKeepAlive

        # sempre enviar a mensagem de autenticação completa
        complete_ssid = self._format_session_message()
        self._keep_alive_manager = ConnectionKeepAlive(complete_ssid, self.is_demo)

        self._keep_alive_manager.add_event_handler("connected", self._on_keep_alive_connected)
        self._keep_alive_manager.add_event_handler("reconnected", self._on_keep_alive_reconnected)
        self._keep_alive_manager.add_event_handler("message_received", self._on_keep_alive_message)

        self._keep_alive_manager.add_event_handler("balance_data", self._on_balance_data)
        self._keep_alive_manager.add_event_handler("balance_updated", self._on_balance_updated)
        self._keep_alive_manager.add_event_handler("authenticated", self._on_authenticated)
        self._keep_alive_manager.add_event_handler("order_opened", self._on_order_opened)
        self._keep_alive_manager.add_event_handler("order_closed", self._on_order_closed)
        self._keep_alive_manager.add_event_handler("stream_update", self._on_stream_update)
        self._keep_alive_manager.add_event_handler("json_data", self._on_json_data)

        success = await self._keep_alive_manager.connect_with_keep_alive(regions)

        if success:
            self._is_persistent = True
            logger.info(" Conexão persistente estabelecida com sucesso")
            return True, "Conexão bem sucedida"
        else:
            logger.error("Falha ao estabelecer conexão persistente")
            return False, "Falha ao conectar"

    async def _start_keep_alive_tasks(self):
        """Iniciar tarefas de keep-alive para conexão regular"""
        logger.info("Iniciando tarefas de keep-alive para conexão regular...")
        self._ping_task = asyncio.create_task(self._ping_loop())
        if self.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnection_monitor())

    async def _ping_loop(self):
        """Loop de ping para conexões regulares (como API antiga)"""
        while self.is_connected and not self._is_persistent:
            try:
                await self._websocket.send_message('42["ps"]')
                self._connection_stats["last_ping_time"] = time.time()
                await asyncio.sleep(20)
            except Exception as e:
                logger.warning(f"Falha no ping: {e}")
                break

    async def _reconnection_monitor(self):
        """Monitorar e gerenciar reconexões para conexões regulares"""
        while self.auto_reconnect and not self._is_persistent:
            await asyncio.sleep(30)
            if not self.is_connected:
                logger.info("Conexão perdida, tentando reconectar...")
                self._connection_stats["total_reconnects"] += 1
                try:
                    ok, _msg = await self._start_regular_connection()
                    if ok:
                        logger.info(" Reconexão bem sucedida")
                    else:
                        logger.error("Falha na reconexão")
                        await asyncio.sleep(10)
                except Exception as e:
                    logger.error(f"Erro na reconexão: {e}")
                    await asyncio.sleep(10)

    async def disconnect(self) -> None:
        """Desconectar da PocketOption e limpar todos os recursos"""
        logger.info("Desconectando da PocketOption...")
        if self._ping_task:
            self._ping_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.disconnect()
        else:
            await self._websocket.disconnect()

        self._is_persistent = False
        self._balance = None
        self._orders.clear()
        logger.info("Desconectado com sucesso")

    async def get_balance(self) -> Balance:
        """
        Obter saldo atual da conta.
        """
        if not self.is_connected:
            raise ConnectionError("Não conectado à PocketOption")

        if (not self._balance) or (datetime.now() - self._balance.last_updated).seconds > 60:
            await self._request_balance_update()
            await asyncio.sleep(1)

        if not self._balance:
            raise PocketOptionError("Dados de saldo não disponíveis")

        return self._balance

    async def place_order(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> OrderResult:
        """
        Enviar ordem binária.
        """
        if not self.is_connected:
            raise ConnectionError("Não conectado à PocketOption")
        self._validate_order_parameters(asset, amount, direction, duration)

        try:
            order_id = str(uuid.uuid4())
            order = Order(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration,
                request_id=order_id,
            )
            await self._send_order(order)
            result = await self._wait_for_order_result(order_id, order)
            logger.info(f"Ordem colocada: {result.order_id} - {result.status}")
            return result
        except Exception as e:
            logger.error(f"Falha ao colocar ordem: {e}")
            raise OrderError(f"Falha ao colocar ordem: {e}")

    async def get_candles(
        self, asset: str, timeframe: Union[str, int], count: int = 100, end_time: Optional[datetime] = None
    ) -> List[Candle]:
        """
        Obter dados de candles. (Observação: o parâmetro `count` pode não ser respeitado pela API de stream usada.)
        """
        if not self.is_connected:
            if self.auto_reconnect:
                logger.info(f"Conexão perdida, tentando reconectar para candles de {asset}...")
                ok, _ = await self._attempt_reconnection()
                if not ok:
                    raise ConnectionError("Não conectado à PocketOption e reconexão falhou")
            else:
                raise ConnectionError("Não conectado à PocketOption")

        if isinstance(timeframe, str):
            timeframe_seconds = TIMEFRAMES.get(timeframe, 60)
        else:
            timeframe_seconds = timeframe

        if asset not in ASSETS:
            raise InvalidParameterError(f"Ativo inválido: {asset}")

        if not end_time:
            end_time = datetime.now()

        max_retries = 2
        for attempt in range(max_retries):
            try:
                candles = await self._request_candles(asset, timeframe_seconds, count, end_time)
                cache_key = f"{asset}_{timeframe_seconds}"
                self._candles_cache[cache_key] = candles
                logger.info(f"Recuperados {len(candles)} candles para {asset}")
                return candles
            except Exception as e:
                if "WebSocket is not connected" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Conexão perdida durante solicitação de candles para {asset}, tentando reconectar...")
                    if self.auto_reconnect:
                        ok, _ = await self._attempt_reconnection()
                        if ok:
                            logger.info(" Reconectado, tentando novamente solicitação de candles")
                            continue
                logger.error(f"Falha ao obter candles para {asset}: {e}")
                raise PocketOptionError(f"Falha ao obter candles: {e}")

        raise PocketOptionError(f"Falha ao obter candles após {max_retries} tentativas")

    async def get_candles_dataframe(
        self, asset: str, timeframe: Union[str, int], count: int = 100, end_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        candles = await self.get_candles(asset, timeframe, count, end_time)
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
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        if order_id in self._order_results:
            return self._order_results[order_id]
        return None

    async def get_active_orders(self) -> List[OrderResult]:
        return list(self._active_orders.values())

    def add_event_callback(self, event: str, callback: Callable) -> None:
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    def remove_event_callback(self, event: str, callback: Callable) -> None:
        if event in self._event_callbacks:
            with suppress(ValueError):
                self._event_callbacks[event].remove(callback)

    @property
    def is_connected(self) -> bool:
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.is_connected
        else:
            return self._websocket.is_connected

    @property
    def connection_info(self):
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.connection_info
        else:
            return self._websocket.connection_info

    async def send_message(self, message: str) -> tuple[bool, str]:
        """Enviar mensagem pela conexão ativa. Retorna (ok, msg)."""
        try:
            if self._is_persistent and self._keep_alive_manager:
                ok = await self._keep_alive_manager.send_message(message)
                return (True, "OK") if ok else (False, "Falha ao enviar via keep-alive")
            else:
                await self._websocket.send_message(message)
                return True, "OK"
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem: {e}")
            return False, "Falha ao conectar"

    def get_connection_stats(self) -> Dict[str, Any]:
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
        return stats

    # ===================== Internos =====================

    def _format_session_message(self) -> str:
        """Monta 42['auth', {...}] SEMPRE a partir de self.session_id atual."""
        auth_data = {
            "session": self.session_id,                 # pode ser 'a:4:{...}HASH' (cookie) ou id simples
            "isDemo": 1 if self.is_demo else 0,
            "uid": self.uid,                            # pode ser 0; servidor descobre pelo cookie
            "platform": self.platform,
        }
        if self.is_fast_history:
            auth_data["isFastHistory"] = True

        return f'42["auth",{json.dumps(auth_data)}]'

    def _parse_complete_ssid(self, ssid: str) -> None:
        try:
            json_start = ssid.find("{")
            json_end = ssid.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_part = ssid[json_start:json_end]
                data = json.loads(json_part)
                self.session_id = data.get("session", "")
                self._original_demo = bool(data.get("isDemo", 1))
                self.uid = data.get("uid", self.uid)
                self.platform = data.get("platform", self.platform)
                self._complete_ssid = None
        except Exception as e:
            logger.warning(f"Falha ao analisar SSID: {e}")
            self.session_id = ssid
            self._complete_ssid = None

    async def _wait_for_authentication(self, timeout: float = 10.0) -> None:
        auth_received = False

        def on_auth(_data):
            nonlocal auth_received
            auth_received = True

        self._websocket.add_event_handler("authenticated", on_auth)
        try:
            start_time = time.time()
            while not auth_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            if not auth_received:
                raise AuthenticationError("Tempo limite de autenticação")
        finally:
            self._websocket.remove_event_handler("authenticated", on_auth)

    async def _initialize_data(self) -> None:
        await self._request_balance_update()
        await self._setup_time_sync()

    async def _request_balance_update(self) -> None:
        message = '42["getBalance"]'
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

    async def _setup_time_sync(self) -> None:
        local_time = datetime.now().timestamp()
        self._server_time = ServerTime(
            server_timestamp=local_time, local_timestamp=local_time, offset=0.0
        )

    def _validate_order_parameters(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> None:
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
        asset_name = order.asset
        message = (
            f'42["openOrder",{{"asset":"{asset_name}","amount":{order.amount},"action":"{order.direction.value}",'
            f'"isDemo":{1 if self.is_demo else 0},"requestId":"{order.request_id}","optionType":100,"time":{order.duration}}}]'
        )
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        if self.enable_logging:
            logger.debug(f"Ordem enviada: {message}")

    async def _wait_for_order_result(
        self, request_id: str, order: Order, timeout: float = 30.0
    ) -> OrderResult:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if request_id in self._active_orders:
                if self.enable_logging:
                    logger.success(f" Ordem {request_id} encontrada no rastreamento ativo")
                return self._active_orders[request_id]
            if request_id in self._order_results:
                if self.enable_logging:
                    logger.info(f"📋 Ordem {request_id} encontrada nos resultados concluídos")
                return self._order_results[request_id]
            await asyncio.sleep(0.2)

        if request_id in self._active_orders:
            if self.enable_logging:
                logger.success(f" Ordem {request_id} encontrada no rastreamento ativo (verificação final)")
            return self._active_orders[request_id]
        if request_id in self._order_results:
            if self.enable_logging:
                logger.info(f"📋 Ordem {request_id} encontrada nos resultados concluídos (verificação final)")
            return self._order_results[request_id]

        if self.enable_logging:
            logger.warning(f"⏰ Ordem {request_id} atingiu timeout aguardando confirmação do servidor, criando resultado fallback")

        fallback_result = OrderResult(
            order_id=request_id,
            asset=order.asset,
            amount=order.amount,
            direction=order.direction,
            duration=order.duration,
            status=OrderStatus.ACTIVE,
            placed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=order.duration),
            error_message="Timeout aguardando confirmação do servidor",
        )
        self._active_orders[request_id] = fallback_result
        if self.enable_logging:
            logger.info(f"📝 Criado resultado fallback para ordem {request_id}")
        return fallback_result

    async def check_win(self, order_id: str, max_wait_time: float = 300.0) -> Optional[Dict[str, Any]]:
        start_time = time.time()
        if self.enable_logging:
            logger.info(f"🔍 Iniciando check_win para ordem {order_id}, espera máxima: {max_wait_time}s")
        while time.time() - start_time < max_wait_time:
            if order_id in self._order_results:
                result = self._order_results[order_id]
                if self.enable_logging:
                    logger.success(
                        f" Ordem {order_id} concluída - Status: {result.status.value}, Lucro: ${result.profit:.2f}"
                    )
                return {
                    "result": "win" if result.status == OrderStatus.WIN else "loss" if result.status == OrderStatus.LOSE else "draw",
                    "profit": result.profit if result.profit is not None else 0,
                    "order_id": order_id,
                    "completed": True,
                    "status": result.status.value,
                }

            if order_id in self._active_orders:
                active_order = self._active_orders[order_id]
                time_remaining = (active_order.expires_at - datetime.now()).total_seconds()
                if time_remaining <= 0:
                    if self.enable_logging:
                        logger.info("⏰ Ordem expirou mas sem resultado ainda, continuando a aguardar...")
                else:
                    if self.enable_logging and int(time.time() - start_time) % 10 == 0:
                        logger.debug(f"⌛ Ordem ainda ativa, expira em {time_remaining:.0f}s")

            await asyncio.sleep(1.0)

        if self.enable_logging:
            logger.warning(f"⏰ Timeout no check_win para ordem {order_id} após {max_wait_time}s")

        return {"result": "timeout", "order_id": order_id, "completed": False, "timeout": True}

    async def _request_candles(self, asset: str, timeframe: int, count: int, end_time: datetime):
        data = {"asset": str(asset), "period": timeframe}
        message_data = ["changeSymbol", data]
        message = f"42{json.dumps(message_data)}"

        if self.enable_logging:
            logger.debug(f"Solicitando candles com changeSymbol: {message}")

        candle_future = asyncio.Future()
        request_id = f"{asset}_{timeframe}"
        if not hasattr(self, "_candle_requests"):
            self._candle_requests = {}
        self._candle_requests[request_id] = candle_future

        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        try:
            candles = await asyncio.wait_for(candle_future, timeout=10.0)
            return candles
        except asyncio.TimeoutError:
            if self.enable_logging:
                logger.warning(f"Solicitação de candles atingiu timeout para {asset}")
            return []
        finally:
            if request_id in self._candle_requests:
                del self._candle_requests[request_id]

    def _parse_candles_data(self, candles_data: List[Any], asset: str, timeframe: int):
        candles = []
        try:
            if isinstance(candles_data, list):
                for candle_data in candles_data:
                    if isinstance(candle_data, (list, tuple)) and len(candle_data) >= 5:
                        raw_high = float(candle_data[2])
                        raw_low = float(candle_data[3])
                        actual_high = max(raw_high, raw_low)
                        actual_low = min(raw_high, raw_low)
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(candle_data[0]),
                            open=float(candle_data[1]),
                            high=actual_high,
                            low=actual_low,
                            close=float(candle_data[4]),
                            volume=float(candle_data[5]) if len(candle_data) > 5 else 0.0,
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Erro ao analisar dados de candles: {e}")
        return candles

    async def _on_json_data(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return

        # Resposta de candles (JSON detalhado)
        if "candles" in data and isinstance(data["candles"], list):
            if hasattr(self, "_candle_requests"):
                asset = data.get("asset")
                period = data.get("period")
                if asset and period:
                    request_id = f"{asset}_{period}"
                    if request_id in self._candle_requests and not self._candle_requests[request_id].done():
                        candles = self._parse_candles_data(data["candles"], asset, period)
                        self._candle_requests[request_id].set_result(candles)
                        if self.enable_logging:
                            logger.success(f" Dados de candles recebidos: {len(candles)} candles para {asset}")
                        del self._candle_requests[request_id]
                        return
            return

        # Detalhe de ordem (abertura)
        if "requestId" in data and "asset" in data and "amount" in data:
            request_id = str(data["requestId"])
            if request_id not in self._active_orders and request_id not in self._order_results:
                order_result = OrderResult(
                    order_id=request_id,
                    asset=data.get("asset", "UNKNOWN"),
                    amount=float(data.get("amount", 0)),
                    direction=OrderDirection.CALL if data.get("command", 0) == 0 else OrderDirection.PUT,
                    duration=int(data.get("time", 60)),
                    status=OrderStatus.ACTIVE,
                    placed_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(seconds=int(data.get("time", 60))),
                    profit=float(data.get("profit", 0)) if "profit" in data else None,
                    payout=data.get("payout"),
                )
                self._active_orders[request_id] = order_result
                if self.enable_logging:
                    logger.success(f" Ordem {request_id} adicionada ao rastreamento a partir de dados JSON")
                # emitir evento fora do bloco de logging
                await self._emit_event("order_opened", data)

        # Resultado de ordem (fechamento)
        elif "deals" in data and isinstance(data["deals"], list):
            for deal in data["deals"]:
                if isinstance(deal, dict) and "id" in deal:
                    order_id = str(deal["id"])
                    if order_id in self._active_orders:
                        active_order = self._active_orders[order_id]
                        profit = float(deal.get("profit", 0))
                        if profit > 0:
                            status = OrderStatus.WIN
                        elif profit < 0:
                            status = OrderStatus.LOSE
                        else:
                            # trate zero como empate se sua enum suportar
                            status = OrderStatus.DRAW if hasattr(OrderStatus, "DRAW") else OrderStatus.LOSE

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

                        self._order_results[order_id] = result
                        del self._active_orders[order_id]

                        if self.enable_logging:
                            logger.success(f" Ordem {order_id} concluída via dados JSON: {status.value} - Lucro: ${profit:.2f}")
                        # emitir evento fora do bloco de logging
                        await self._emit_event("order_closed", result)

    async def _emit_event(self, event: str, data: Any) -> None:
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

    async def _on_authenticated(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.success(" Autenticado com sucesso na PocketOption")
        # incrementar somente aqui para evitar duplicidade
        self._connection_stats["successful_connections"] += 1
        await self._emit_event("authenticated", data)

    async def _on_balance_updated(self, data: Dict[str, Any]) -> None:
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
        await self._on_balance_updated(data)

    async def _on_order_opened(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info(f"Ordem aberta: {data}")
        await self._emit_event("order_opened", data)

    async def _on_order_closed(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info(f"📊 Ordem fechada: {data}")
        await self._emit_event("order_closed", data)

    async def _on_stream_update(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.debug(f"📡 Atualização de stream: {data}")
        if "asset" in data and "period" in data and ("candles" in data or "data" in data):
            await self._handle_candles_stream(data)
        await self._emit_event("stream_update", data)

    async def _on_candles_received(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info(f"🕯️ Candles recebidos com dados: {type(data)}")
        if hasattr(self, "_candle_requests") and self._candle_requests:
            try:
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        parts = request_id.split("_")
                        if len(parts) >= 2:
                            asset = "_".join(parts[:-1])
                            timeframe = int(parts[-1])
                            candles = self._parse_candles_data(data.get("candles", []), asset, timeframe)
                            if self.enable_logging:
                                logger.info(f"🕯️ Analisados {len(candles)} candles da resposta")
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
        if self.enable_logging:
            logger.warning("Desconectado da PocketOption")
        await self._emit_event("disconnected", data)

    async def _handle_candles_stream(self, data: Dict[str, Any]) -> None:
        try:
            asset = data.get("asset")
            period = data.get("period")
            if not asset or not period:
                return
            request_id = f"{asset}_{period}"
            if self.enable_logging:
                logger.info(f"🕯️ Processando stream de candles para {asset} ({period}s)")
            if hasattr(self, "_candle_requests") and request_id in self._candle_requests:
                future = self._candle_requests[request_id]
                if not future.done():
                    candles = self._parse_stream_candles(data, asset, period)
                    if candles:
                        future.set_result(candles)
                        if self.enable_logging:
                            logger.info(f"🕯️ Solicitação de candles resolvida para {asset} com {len(candles)} candles")
                del self._candle_requests[request_id]
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Erro ao gerenciar stream de candles: {e}")

    def _parse_stream_candles(self, stream_data: Dict[str, Any], asset: str, timeframe: int):
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
        logger.info("Conexão keep-alive estabelecida")
        await self._initialize_data()
        for callback in self._event_callbacks.get("connected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Erro no callback de conectado: {e}")

    async def _on_keep_alive_reconnected(self):
        logger.info("Conexão keep-alive restabelecida")
        await self._initialize_data()
        for callback in self._event_callbacks.get("reconnected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Erro no callback de reconectado: {e}")

    async def _on_keep_alive_message(self, message):
        if message.startswith("42"):
            try:
                data_str = message[2:]
                data = json.loads(data_str)
                if isinstance(data, list) and len(data) >= 2:
                    event_type = data[0]
                    event_data = data[1]
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

        for callback in self._event_callbacks.get("message", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Erro no callback de mensagem: {e}")

    async def _attempt_reconnection(self, max_attempts: int = 3) -> tuple[bool, str]:
        """
        Tentar reconectar à PocketOption.
        Retorna (ok, msg).
        """
        logger.info(f"Tentando reconexão (máximo de {max_attempts} tentativas)...")
        for attempt in range(max_attempts):
            try:
                logger.info(f"Tentativa de reconexão {attempt + 1}/{max_attempts}")
                if self._is_persistent and self._keep_alive_manager:
                    await self._keep_alive_manager.disconnect()
                else:
                    await self._websocket.disconnect()

                await asyncio.sleep(2 + attempt)  # Atraso progressivo

                if self.persistent_connection:
                    ok, msg = await self._start_persistent_connection()
                else:
                    ok, msg = await self._start_regular_connection()

                if ok:
                    logger.info(f" Reconexão bem sucedida na tentativa {attempt + 1}")
                    await self._emit_event("reconnected", {})
                    return True, "Conexão bem sucedida"
                else:
                    logger.warning(f"Tentativa de reconexão {attempt + 1} falhou: {msg}")

            except Exception as e:
                logger.error(f"Tentativa de reconexão {attempt + 1} falhou com erro: {e}")

        logger.error(f"Todas as {max_attempts} tentativas de reconexão falharam")
        return False, "Falha ao conectar"