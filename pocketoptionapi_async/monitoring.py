"""
# Autor: ByMyselfJhones
# Função: ErrorMonitor e HealthChecker
# Descrição:
# - Sistema avançado de monitoramento e tratamento de erros para API da PocketOption
# - Inclui enums para severidade/categoria, circuit breaker e retry policy
# - Monitora saúde do sistema com alertas e relatórios
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, deque
from loguru import logger

class ErrorSeverity(Enum):
    """Níveis de severidade de erro"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Categorias de erro"""

    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    TRADING = "trading"
    DATA = "data"
    SYSTEM = "system"
    RATE_LIMIT = "rate_limit"

@dataclass
class ErrorEvent:
    """Estrutura de dados de evento de erro"""

    timestamp: datetime
    error_type: str
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    context: Dict[str, Any]
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_time: Optional[datetime] = None

@dataclass
class PerformanceMetrics:
    """Métricas de monitoramento de desempenho"""

    timestamp: datetime
    operation: str
    duration: float
    success: bool
    memory_usage: Optional[int] = None
    cpu_usage: Optional[float] = None
    active_connections: int = 0

class CircuitBreaker:
    """Implementação do padrão Circuit Breaker"""

    from typing import Type

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[BaseException] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs):
        """Executar função com proteção do circuit breaker"""
        if self.state == "OPEN":
            if (
                self.last_failure_time is not None
                and time.time() - self.last_failure_time < self.recovery_timeout
            ):
                raise Exception("Circuit breaker está ABERTO")
            else:
                self.state = "HALF_OPEN"

        try:
            result = await func(*args, **kwargs)
            self.on_success()
            return result
        except self.expected_exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        """Tratar operação bem-sucedida"""
        self.failure_count = 0
        self.state = "CLOSED"

    def on_failure(self):
        """Tratar operação com falha"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker aberto após {self.failure_count} falhas"
            )

class RetryPolicy:
    """Política de retentativa avançada com backoff exponencial"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    async def execute(self, func: Callable, *args, **kwargs):
        """Executar função com política de retentativa"""
        import random

        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt == self.max_attempts - 1:
                    break

                # Calcular atraso
                delay = min(
                    self.base_delay * (self.exponential_base**attempt), self.max_delay
                )

                # Adicionar jitter
                if self.jitter:
                    delay *= 0.5 + random.random() * 0.5

                logger.warning(
                    f"Tentativa {attempt + 1} falhou: {e}. Retentando em {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        if last_exception is not None:
            raise last_exception
        else:
            raise Exception("RetryPolicy falhou, mas nenhuma exceção foi capturada.")

class ErrorMonitor:
    """Sistema abrangente de monitoramento e tratamento de erros"""

    def __init__(
        self, max_errors: int = 1000, alert_threshold: int = 10, alert_window: int = 300
    ):  # 5 minutos
        self.max_errors = max_errors
        self.alert_threshold = alert_threshold
        self.alert_window = alert_window

        self.errors: deque = deque(maxlen=max_errors)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.error_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self.alert_callbacks: List[Callable] = []

        # Circuit breakers para diferentes operações
        self.circuit_breakers = {
            "connection": CircuitBreaker(failure_threshold=3, recovery_timeout=30),
            "trading": CircuitBreaker(failure_threshold=5, recovery_timeout=60),
            "data": CircuitBreaker(failure_threshold=10, recovery_timeout=30),
        }

        # Políticas de retentativa
        self.retry_policies = {
            "connection": RetryPolicy(max_attempts=3, base_delay=2.0),
            "trading": RetryPolicy(max_attempts=2, base_delay=1.0),
            "data": RetryPolicy(max_attempts=5, base_delay=0.5),
        }

    def add_alert_callback(self, callback: Callable):
        """Adicionar função de callback de alerta"""
        self.alert_callbacks.append(callback)

    async def record_error(
        self,
        error_type: str,
        severity: ErrorSeverity,
        category: ErrorCategory,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
    ):
        """Registrar um evento de erro"""
        error_event = ErrorEvent(
            timestamp=datetime.now(),
            error_type=error_type,
            severity=severity,
            category=category,
            message=message,
            context=context or {},
            stack_trace=stack_trace or "",
        )

        self.errors.append(error_event)
        self.error_counts[error_type] += 1
        self.error_patterns[error_type].append(error_event.timestamp)

        # Verificar condições de alerta
        await self._check_alert_conditions(error_event)

        logger.error(f"[{severity.value.upper()}] {category.value}: {message}")

        return error_event

    async def _check_alert_conditions(self, error_event: ErrorEvent):
        """Verificar se as condições de alerta são atendidas"""
        current_time = datetime.now()
        window_start = current_time - timedelta(seconds=self.alert_window)

        # Contar erros recentes do mesmo tipo
        recent_errors = [
            timestamp
            for timestamp in self.error_patterns[error_event.error_type]
            if timestamp >= window_start
        ]

        if len(recent_errors) >= self.alert_threshold:
            await self._trigger_alert(error_event, len(recent_errors))

    async def _trigger_alert(self, error_event: ErrorEvent, error_count: int):
        """Acionar alerta para alta taxa de erro"""
        alert_data = {
            "error_type": error_event.error_type,
            "error_count": error_count,
            "time_window": self.alert_window,
            "severity": error_event.severity,
            "category": error_event.category,
            "latest_message": error_event.message,
        }

        logger.critical(
            f"ALERTA: Alta taxa de erro para {error_event.error_type}: "
            f"{error_count} erros em {self.alert_window}s"
        )

        for callback in self.alert_callbacks:
            try:
                await callback(alert_data)
            except Exception as e:
                logger.error(f"Falha no callback de alerta: {e}")

    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Obter resumo de erros para o período de tempo especificado"""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        recent_errors = [
            error for error in self.errors if error.timestamp >= cutoff_time
        ]

        summary = {
            "total_errors": len(recent_errors),
            "error_by_type": defaultdict(int),
            "error_by_category": defaultdict(int),
            "error_by_severity": defaultdict(int),
            "top_errors": [],
            "error_rate": len(recent_errors) / hours if hours > 0 else 0,
        }

        for error in recent_errors:
            summary["error_by_type"][error.error_type] += 1
            summary["error_by_category"][error.category.value] += 1
            summary["error_by_severity"][error.severity.value] += 1

        # Obter principais erros
        summary["top_errors"] = sorted(
            summary["error_by_type"].items(), key=lambda x: x[1], reverse=True
        )[:10]

        return summary

    async def execute_with_monitoring(
        self,
        func: Callable,
        operation_name: str,
        category: ErrorCategory,
        use_circuit_breaker: bool = False,
        use_retry: bool = False,
        *args,
        **kwargs,
    ):
        """Executar função com monitoramento de erros abrangente"""
        start_time = time.time()

        try:
            # Aplicar circuit breaker se solicitado
            if use_circuit_breaker and category.value in self.circuit_breakers:
                circuit_breaker = self.circuit_breakers[category.value]

                if use_retry and category.value in self.retry_policies:
                    retry_policy = self.retry_policies[category.value]
                    result = await circuit_breaker.call(
                        retry_policy.execute, func, *args, **kwargs
                    )
                else:
                    result = await circuit_breaker.call(func, *args, **kwargs)
            elif use_retry and category.value in self.retry_policies:
                retry_policy = self.retry_policies[category.value]
                result = await retry_policy.execute(func, *args, **kwargs)
            else:
                result = await func(*args, **kwargs)

            # Registrar métricas de sucesso
            duration = time.time() - start_time
            logger.debug(f"Operação '{operation_name}' concluída em {duration:.3f}s")

            return result

        except Exception as e:
            # Registrar erro
            duration = time.time() - start_time

            await self.record_error(
                error_type=f"{operation_name}_error",
                severity=ErrorSeverity.MEDIUM,
                category=category,
                message=str(e),
                context={
                    "operation": operation_name,
                    "duration": duration,
                    "args": str(args)[:200],  # Truncar por segurança
                    "kwargs": str({k: str(v)[:100] for k, v in kwargs.items()})[:200],
                },
                stack_trace="",  # Poderia adicionar traceback.format_exc() aqui
            )

            raise e

class HealthChecker:
    """Monitoramento de saúde do sistema"""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.health_checks: Dict[str, Callable] = {}
        self.health_status: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._health_task: Optional[asyncio.Task] = None

    def register_health_check(self, name: str, check_func: Callable):
        """Registrar uma função de verificação de saúde"""
        self.health_checks[name] = check_func

    async def start_monitoring(self):
        """Iniciar monitoramento de saúde"""
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())

    async def stop_monitoring(self):
        """Parar monitoramento de saúde"""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

    async def _health_check_loop(self):
        """Loop principal de verificação de saúde"""
        while self._running:
            try:
                for name, check_func in self.health_checks.items():
                    try:
                        start_time = time.time()
                        result = await check_func()
                        duration = time.time() - start_time

                        self.health_status[name] = {
                            "status": "healthy" if result else "unhealthy",
                            "last_check": datetime.now(),
                            "response_time": duration,
                            "details": result if isinstance(result, dict) else {},
                        }

                    except Exception as e:
                        self.health_status[name] = {
                            "status": "error",
                            "last_check": datetime.now(),
                            "error": str(e),
                            "response_time": None,
                        }

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no loop de verificação de saúde: {e}")
                await asyncio.sleep(self.check_interval)

    def get_health_report(self) -> Dict[str, Any]:
        """Obter relatório de saúde abrangente"""
        overall_status = "healthy"
        unhealthy_services = []

        for service, status in self.health_status.items():
            if status["status"] != "healthy":
                overall_status = (
                    "degraded" if overall_status == "healthy" else "unhealthy"
                )
                unhealthy_services.append(service)

        return {
            "overall_status": overall_status,
            "services": self.health_status,
            "unhealthy_services": unhealthy_services,
            "timestamp": datetime.now(),
        }

# Instâncias globais de monitoramento
error_monitor = ErrorMonitor()
health_checker = HealthChecker()

# Manipulador de alerta padrão para demonstração
async def default_alert_handler(alert_data: Dict[str, Any]):
    """Manipulador de alerta padrão"""
    logger.critical(
        f"🚨 ALERTA: {alert_data['error_type']} - {alert_data['error_count']} erros"
    )

# Registrar manipulador de alerta padrão
error_monitor.add_alert_callback(default_alert_handler)