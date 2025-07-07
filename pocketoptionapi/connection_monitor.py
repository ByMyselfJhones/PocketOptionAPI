"""
# Autor: ByMyselfJhones
# Função: ConnectionMonitor
# Descrição:
# - Monitor avançado de conexão para API da PocketOption
# - Fornece métricas de desempenho em tempo real e snapshots
# - Gera relatórios de diagnóstico e exporta métricas
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
import statistics
from loguru import logger

from client import AsyncPocketOptionClient

@dataclass
class ConnectionMetrics:
    """Métricas de desempenho da conexão"""

    timestamp: datetime
    connection_time: float
    ping_time: Optional[float]
    message_count: int
    error_count: int
    region: str
    status: str

@dataclass
class PerformanceSnapshot:
    """Snapshot de desempenho"""

    timestamp: datetime
    memory_usage_mb: float
    cpu_percent: float
    active_connections: int
    messages_per_second: float
    error_rate: float
    avg_response_time: float

class ConnectionMonitor:
    """Monitoramento e diagnóstico avançado de conexão"""

    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo

        # Estado de monitoramento
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.client: Optional[AsyncPocketOptionClient] = None

        # Armazenamento de métricas
        self.connection_metrics: deque = deque(maxlen=1000)
        self.performance_snapshots: deque = deque(maxlen=500)
        self.error_log: deque = deque(maxlen=200)
        self.message_stats: Dict[str, int] = defaultdict(int)

        # Estatísticas em tempo real
        self.start_time = datetime.now()
        self.total_messages = 0
        self.total_errors = 0
        self.last_ping_time = None
        self.ping_times: deque = deque(maxlen=100)

        # Manipuladores de eventos
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)

        # Rastreamento de desempenho
        self.response_times: deque = deque(maxlen=100)
        self.connection_attempts = 0
        self.successful_connections = 0

    async def start_monitoring(self, persistent_connection: bool = True) -> bool:
        """Iniciar monitoramento em tempo real"""
        logger.info("Análise: Iniciando monitoramento de conexão...")

        try:
            # Inicializar cliente
            self.client = AsyncPocketOptionClient(
                self.ssid,
                is_demo=self.is_demo,
                persistent_connection=persistent_connection,
                auto_reconnect=True,
            )

            # Configurar manipuladores de eventos
            self._setup_event_handlers()

            # Conectar
            self.connection_attempts += 1
            start_time = time.time()

            success = await self.client.connect()

            if success:
                connection_time = time.time() - start_time
                self.successful_connections += 1

                # Registrar métricas de conexão
                self._record_connection_metrics(connection_time, "CONNECTED")

                # Iniciar tarefas de monitoramento
                self.is_monitoring = True
                self.monitor_task = asyncio.create_task(self._monitoring_loop())

                logger.success(
                    f"Sucesso: Monitoramento iniciado (tempo de conexão: {connection_time:.3f}s)"
                )
                return True
            else:
                self._record_connection_metrics(0, "FAILED")
                logger.error("Erro: Falha ao conectar para monitoramento")
                return False

        except Exception as e:
            self.total_errors += 1
            self._record_error("monitoring_start", str(e))
            logger.error(f"Erro: Falha ao iniciar monitoramento: {e}")
            return False

    async def stop_monitoring(self):
        """Parar monitoramento"""
        logger.info("Parando monitoramento de conexão...")

        self.is_monitoring = False

        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.disconnect()

        logger.info("Sucesso: Monitoramento parado")

    def _setup_event_handlers(self):
        """Configurar manipuladores de eventos para monitoramento"""
        if not self.client:
            return

        # Eventos de conexão
        self.client.add_event_callback("connected", self._on_connected)
        self.client.add_event_callback("disconnected", self._on_disconnected)
        self.client.add_event_callback("reconnected", self._on_reconnected)
        self.client.add_event_callback("auth_error", self._on_auth_error)

        # Eventos de dados
        self.client.add_event_callback("balance_updated", self._on_balance_updated)
        self.client.add_event_callback("candles_received", self._on_candles_received)
        self.client.add_event_callback("message_received", self._on_message_received)

    async def _monitoring_loop(self):
        """Loop principal de monitoramento"""
        logger.info("Persistente: Iniciando loop de monitoramento...")

        while self.is_monitoring:
            try:
                # Coletar snapshot de desempenho
                await self._collect_performance_snapshot()

                # Verificar saúde da conexão
                await self._check_connection_health()

                # Enviar ping e medir resposta
                await self._measure_ping_response()

                # Emitir eventos de monitoramento
                await self._emit_monitoring_events()

                await asyncio.sleep(5)  # Monitorar a cada 5 segundos

            except Exception as e:
                self.total_errors += 1
                self._record_error("monitoring_loop", str(e))
                logger.error(f"Erro: Erro no loop de monitoramento: {e}")

    async def _collect_performance_snapshot(self):
        """Coletar snapshot de métricas de desempenho"""
        try:
            # Tentar obter métricas do sistema
            memory_mb = 0
            cpu_percent = 0

            try:
                import psutil
                import os

                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
            except ImportError:
                pass

            # Calcular mensagens por segundo
            uptime = (datetime.now() - self.start_time).total_seconds()
            messages_per_second = self.total_messages / uptime if uptime > 0 else 0

            # Calcular taxa de erro
            error_rate = self.total_errors / max(self.total_messages, 1)

            # Calcular tempo médio de resposta
            avg_response_time = (
                statistics.mean(self.response_times) if self.response_times else 0
            )

            snapshot = PerformanceSnapshot(
                timestamp=datetime.now(),
                memory_usage_mb=memory_mb,
                cpu_percent=cpu_percent,
                active_connections=1 if self.client and self.client.is_connected else 0,
                messages_per_second=messages_per_second,
                error_rate=error_rate,
                avg_response_time=avg_response_time,
            )

            self.performance_snapshots.append(snapshot)

        except Exception as e:
            logger.error(f"Erro: Erro ao coletar snapshot de desempenho: {e}")

    async def _check_connection_health(self):
        """Verificar estado de saúde da conexão"""
        if not self.client:
            return

        try:
            # Verificar se ainda está conectado
            if not self.client.is_connected:
                self._record_connection_metrics(0, "DISCONNECTED")
                return

            # Tentar obter saldo como verificação de saúde
            start_time = time.time()
            balance = await self.client.get_balance()
            response_time = time.time() - start_time

            self.response_times.append(response_time)

            if balance:
                self._record_connection_metrics(response_time, "HEALTHY")
            else:
                self._record_connection_metrics(response_time, "UNHEALTHY")

        except Exception as e:
            self.total_errors += 1
            self._record_error("health_check", str(e))
            self._record_connection_metrics(0, "ERROR")

    async def _measure_ping_response(self):
        """Medir tempo de resposta de ping"""
        if not self.client or not self.client.is_connected:
            return

        try:
            start_time = time.time()
            await self.client.send_message('42["ps"]')

            # Nota: Não podemos medir facilmente o tempo de resposta real do ping
            # já que é tratado internamente. Isso mede o tempo de envio.
            ping_time = time.time() - start_time

            self.ping_times.append(ping_time)
            self.last_ping_time = datetime.now()

            self.total_messages += 1
            self.message_stats["ping"] += 1

        except Exception as e:
            self.total_errors += 1
            self._record_error("ping_measure", str(e))

    async def _emit_monitoring_events(self):
        """Emitir eventos de monitoramento"""
        try:
            # Emitir estatísticas em tempo real
            stats = self.get_real_time_stats()
            await self._emit_event("stats_update", stats)

            # Verificar e emitir alertas se necessário
            await self._check_and_emit_alerts(stats)

        except Exception as e:
            logger.error(f"Erro: Erro ao emitir eventos de monitoramento: {e}")

    async def _check_and_emit_alerts(self, stats: Dict[str, Any]):
        """Verificar condições de alerta e emitir alertas"""

        # Alerta de alta taxa de erro
        if stats["error_rate"] > 0.1:  # Taxa de erro de 10%
            await self._emit_event(
                "alert",
                {
                    "type": "high_error_rate",
                    "value": stats["error_rate"],
                    "threshold": 0.1,
                    "message": f"Alta taxa de erro detectada: {stats['error_rate']:.1%}",
                },
            )

        # Alerta de tempo de resposta lento
        if stats["avg_response_time"] > 5.0:  # 5 segundos
            await self._emit_event(
                "alert",
                {
                    "type": "slow_response",
                    "value": stats["avg_response_time"],
                    "threshold": 5.0,
                    "message": f"Tempo de resposta lento: {stats['avg_response_time']:.2f}s",
                },
            )

        # Alerta de problemas de conexão
        if not stats["is_connected"]:
            await self._emit_event(
                "alert", {"type": "connection_lost", "message": "Conexão perdida"}
            )

        # Alerta de uso de memória (se disponível)
        if "memory_usage_mb" in stats and stats["memory_usage_mb"] > 500:  # 500MB
            await self._emit_event(
                "alert",
                {
                    "type": "high_memory",
                    "value": stats["memory_usage_mb"],
                    "threshold": 500,
                    "message": f"Alto uso de memória: {stats['memory_usage_mb']:.1f}MB",
                },
            )

    def _record_connection_metrics(self, connection_time: float, status: str):
        """Registrar métricas de conexão"""
        region = "UNKNOWN"
        if self.client and self.client.connection_info:
            region = self.client.connection_info.region or "UNKNOWN"

        metrics = ConnectionMetrics(
            timestamp=datetime.now(),
            connection_time=connection_time,
            ping_time=self.ping_times[-1] if self.ping_times else None,
            message_count=self.total_messages,
            error_count=self.total_errors,
            region=region,
            status=status,
        )

        self.connection_metrics.append(metrics)

    def _record_error(self, error_type: str, error_message: str):
        """Registrar erro para análise"""
        error_record = {
            "timestamp": datetime.now(),
            "type": error_type,
            "message": error_message,
        }
        self.error_log.append(error_record)

    async def _emit_event(self, event_type: str, data: Any):
        """Emitir evento para manipuladores registrados"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Erro: Erro no manipulador de eventos para {event_type}: {e}")

    # Métodos de manipuladores de eventos
    async def _on_connected(self, data):
        self.total_messages += 1
        self.message_stats["connected"] += 1
        logger.info("Conexão estabelecida")

    async def _on_disconnected(self, data):
        self.total_messages += 1
        self.message_stats["disconnected"] += 1
        logger.warning("Conexão perdida")

    async def _on_reconnected(self, data):
        self.total_messages += 1
        self.message_stats["reconnected"] += 1
        logger.info("Conexão restaurada")

    async def _on_auth_error(self, data):
        self.total_errors += 1
        self.message_stats["auth_error"] += 1
        self._record_error("auth_error", str(data))
        logger.error("Erro de autenticação")

    async def _on_balance_updated(self, data):
        self.total_messages += 1
        self.message_stats["balance"] += 1

    async def _on_candles_received(self, data):
        self.total_messages += 1
        self.message_stats["candles"] += 1

    async def _on_message_received(self, data):
        self.total_messages += 1
        self.message_stats["message"] += 1

    def add_event_handler(self, event_type: str, handler: Callable):
        """Adicionar manipulador de eventos para eventos de monitoramento"""
        self.event_handlers[event_type].append(handler)

    def get_real_time_stats(self) -> Dict[str, Any]:
        """Obter estatísticas em tempo real atuais"""
        uptime = datetime.now() - self.start_time

        stats = {
            "uptime": uptime.total_seconds(),
            "uptime_str": str(uptime).split(".")[0],
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / max(self.total_messages, 1),
            "messages_per_second": self.total_messages / uptime.total_seconds()
            if uptime.total_seconds() > 0
            else 0,
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "connection_success_rate": self.successful_connections
            / max(self.connection_attempts, 1),
            "is_connected": self.client.is_connected if self.client else False,
            "last_ping_time": self.last_ping_time.isoformat()
            if self.last_ping_time
            else None,
            "message_types": dict(self.message_stats),
        }

        # Adicionar estatísticas de tempo de resposta
        if self.response_times:
            stats.update(
                {
                    "avg_response_time": statistics.mean(self.response_times),
                    "min_response_time": min(self.response_times),
                    "max_response_time": max(self.response_times),
                    "median_response_time": statistics.median(self.response_times),
                }
            )

        # Adicionar estatísticas de ping
        if self.ping_times:
            stats.update(
                {
                    "avg_ping_time": statistics.mean(self.ping_times),
                    "min_ping_time": min(self.ping_times),
                    "max_ping_time": max(self.ping_times),
                }
            )

        # Adicionar dados do snapshot de desempenho mais recente
        if self.performance_snapshots:
            latest = self.performance_snapshots[-1]
            stats.update(
                {
                    "memory_usage_mb": latest.memory_usage_mb,
                    "cpu_percent": latest.cpu_percent,
                }
            )

        return stats

    def get_historical_metrics(self, hours: int = 1) -> Dict[str, Any]:
        """Obter métricas históricas para o período de tempo especificado"""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Filtrar métricas
        recent_metrics = [
            m for m in self.connection_metrics if m.timestamp > cutoff_time
        ]
        recent_snapshots = [
            s for s in self.performance_snapshots if s.timestamp > cutoff_time
        ]
        recent_errors = [e for e in self.error_log if e["timestamp"] > cutoff_time]

        historical = {
            "time_period_hours": hours,
            "connection_metrics_count": len(recent_metrics),
            "performance_snapshots_count": len(recent_snapshots),
            "error_count": len(recent_errors),
            "metrics": [asdict(m) for m in recent_metrics],
            "snapshots": [asdict(s) for s in recent_snapshots],
            "errors": recent_errors,
        }

        # Calcular tendências
        if recent_snapshots:
            memory_values = [
                s.memory_usage_mb for s in recent_snapshots if s.memory_usage_mb > 0
            ]
            response_values = [
                s.avg_response_time for s in recent_snapshots if s.avg_response_time > 0
            ]

            if memory_values:
                historical["memory_trend"] = {
                    "avg": statistics.mean(memory_values),
                    "min": min(memory_values),
                    "max": max(memory_values),
                    "trend": "increasing"
                    if len(memory_values) > 1 and memory_values[-1] > memory_values[0]
                    else "stable",
                }

            if response_values:
                historical["response_time_trend"] = {
                    "avg": statistics.mean(response_values),
                    "min": min(response_values),
                    "max": max(response_values),
                    "trend": "improving"
                    if len(response_values) > 1
                    and response_values[-1] < response_values[0]
                    else "stable",
                }

        return historical

    def generate_diagnostics_report(self) -> Dict[str, Any]:
        """Gerar relatório de diagnóstico abrangente"""
        stats = self.get_real_time_stats()
        historical = self.get_historical_metrics(hours=2)

        # Avaliação de saúde
        health_score = 100
        health_issues = []

        if stats["error_rate"] > 0.05:
            health_score -= 20
            health_issues.append(f"Alta taxa de erro: {stats['error_rate']:.1%}")

        if not stats["is_connected"]:
            health_score -= 30
            health_issues.append("Não conectado")

        if stats.get("avg_response_time", 0) > 3.0:
            health_score -= 15
            health_issues.append(
                f"Tempo de resposta lento: {stats.get('avg_response_time', 0):.2f}s"
            )

        if stats["connection_success_rate"] < 0.9:
            health_score -= 10
            health_issues.append(
                f"Baixa taxa de sucesso de conexão: {stats['connection_success_rate']:.1%}"
            )

        health_score = max(0, health_score)

        # Recomendações
        recommendations = []

        if stats["error_rate"] > 0.1:
            recommendations.append(
                "Alta taxa de erro detectada. Verifique a conectividade de rede e a validade do SSID."
            )

        if stats.get("avg_response_time", 0) > 5.0:
            recommendations.append(
                "Tempos de resposta lentos. Considere usar conexões persistentes ou uma região diferente."
            )

        if stats.get("memory_usage_mb", 0) > 300:
            recommendations.append(
                "Alto uso de memória detectado. Monitore por vazamentos de memória."
            )

        if not recommendations:
            recommendations.append("Sistema está operando normalmente.")

        report = {
            "timestamp": datetime.now().isoformat(),
            "health_score": health_score,
            "health_status": "EXCELLENT"
            if health_score > 90
            else "GOOD"
            if health_score > 70
            else "FAIR"
            if health_score > 50
            else "POOR",
            "health_issues": health_issues,
            "recommendations": recommendations,
            "real_time_stats": stats,
            "historical_metrics": historical,
            "connection_summary": {
                "total_attempts": stats["connection_attempts"],
                "successful_connections": stats["successful_connections"],
                "current_status": "CONNECTED"
                if stats["is_connected"]
                else "DISCONNECTED",
                "uptime": stats["uptime_str"],
            },
        }

        return report

    def export_metrics_csv(self, filename: str = "") -> str:
        """Exportar métricas para arquivo CSV"""
        if not filename:
            filename = f"metrics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            import pandas as pd

            # Converter métricas para DataFrame
            metrics_data = []
            for metric in self.connection_metrics:
                metrics_data.append(asdict(metric))

            if metrics_data:
                df = pd.DataFrame(metrics_data)
                df.to_csv(filename, index=False)
                logger.info(f"Estatísticas: Métricas exportadas para {filename}")
            else:
                logger.warning("Nenhum dado de métricas para exportar")

            return filename

        except ImportError:
            logger.error("pandas não disponível para exportação CSV")

            # Fallback: exportação CSV básica
            import csv

            with open(filename, "w", newline="") as csvfile:
                if self.connection_metrics:
                    fieldnames = asdict(self.connection_metrics[0]).keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for metric in self.connection_metrics:
                        writer.writerow(asdict(metric))

            return filename

class RealTimeDisplay:
    """Exibição em tempo real no console para monitoramento"""

    def __init__(self, monitor: ConnectionMonitor):
        self.monitor = monitor
        self.display_task: Optional[asyncio.Task] = None
        self.is_displaying = False

    async def start_display(self):
        """Iniciar exibição em tempo real"""
        self.is_displaying = True
        self.display_task = asyncio.create_task(self._display_loop())

    async def stop_display(self):
        """Parar exibição em tempo real"""
        self.is_displaying = False
        if self.display_task and not self.display_task.done():
            self.display_task.cancel()
            try:
                await self.display_task
            except asyncio.CancelledError:
                pass

    async def _display_loop(self):
        """Loop de exibição"""
        while self.is_displaying:
            try:
                # Limpar tela (sequência de escape ANSI)
                print("\033[2J\033[H", end="")

                # Exibir cabeçalho
                print("Análise: Monitor de Conexão da API PocketOption")
                print("=" * 60)

                # Obter estatísticas
                stats = self.monitor.get_real_time_stats()

                # Exibir status de conexão
                status = "Conectado" if stats["is_connected"] else "Desconectado"
                print(f"Status: {status}")
                print(f"Tempo ativo: {stats['uptime_str']}")
                print()

                # Exibir métricas
                print("Estatísticas: Métricas:")
                print(f"  Mensagens: {stats['total_messages']}")
                print(f"  Erros: {stats['total_errors']}")
                print(f"  Taxa de erro: {stats['error_rate']:.1%}")
                print(f"  Mensagens/seg: {stats['messages_per_second']:.2f}")
                print()

                # Exibir desempenho
                if "avg_response_time" in stats:
                    print("Desempenho:")
                    print(f"  Resposta média: {stats['avg_response_time']:.3f}s")
                    print(f"  Resposta mínima: {stats['min_response_time']:.3f}s")
                    print(f"  Resposta máxima: {stats['max_response_time']:.3f}s")
                    print()

                # Exibir memória se disponível
                if "memory_usage_mb" in stats:
                    print("Recursos:")
                    print(f"  Memória: {stats['memory_usage_mb']:.1f} MB")
                    print(f"  CPU: {stats['cpu_percent']:.1f}%")
                    print()

                # Exibir tipos de mensagens
                if stats["message_types"]:
                    print("Mensagem: Tipos de Mensagens:")
                    for msg_type, count in stats["message_types"].items():
                        print(f"  {msg_type}: {count}")
                    print()

                print("Pressione Ctrl+C para parar o monitoramento...")

                await asyncio.sleep(2)  # Atualizar a cada 2 segundos

            except Exception as e:
                logger.error(f"Erro na exibição: {e}")
                await asyncio.sleep(1)

async def run_monitoring_demo(ssid: Optional[str] = None):
    """Executar demonstração de monitoramento"""

    if not ssid:
        ssid = r'42["auth",{"session":"demo_session_for_monitoring","isDemo":1,"uid":0,"platform":1}]'
        logger.warning("Atenção: Usando SSID demo para monitoramento")

    logger.info("Análise: Iniciando Demonstração do Monitor de Conexão Avançado")

    # Criar monitor
    monitor = ConnectionMonitor(ssid, is_demo=True)

    # Adicionar manipuladores de eventos para alertas
    async def on_alert(alert_data):
        logger.warning(f"Alerta: ALERTA: {alert_data['message']}")

    async def on_stats_update(stats):
        # Poderia enviar para sistema de monitoramento externo
        pass

    monitor.add_event_handler("alert", on_alert)
    monitor.add_event_handler("stats_update", on_stats_update)

    # Criar exibição em tempo real
    display = RealTimeDisplay(monitor)

    try:
        # Iniciar monitoramento
        success = await monitor.start_monitoring(persistent_connection=True)

        if success:
            # Iniciar exibição em tempo real
            await display.start_display()

            # Deixar rodar por um tempo
            await asyncio.sleep(120)  # Rodar por 2 minutos

        else:
            logger.error("Erro: Falha ao iniciar monitoramento")

    except KeyboardInterrupt:
        logger.info("Parando: Monitoramento parado pelo usuário")

    finally:
        # Parar exibição e monitoramento
        await display.stop_display()
        await monitor.stop_monitoring()

        # Gerar relatório final
        report = monitor.generate_diagnostics_report()

        logger.info("\nConcluído: RELATÓRIO DE DIAGNÓSTICO FINAL")
        logger.info("=" * 50)
        logger.info(
            f"Pontuação de Saúde: {report['health_score']}/100 ({report['health_status']})"
        )

        if report["health_issues"]:
            logger.warning("Problemas encontrados:")
            for issue in report["health_issues"]:
                logger.warning(f"  - {issue}")

        logger.info("Recomendações:")
        for rec in report["recommendations"]:
            logger.info(f"  - {rec}")

        # Salvar relatório detalhado
        report_file = (
            f"monitoring_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Relatório: Relatório detalhado salvo em: {report_file}")

        # Exportar métricas
        metrics_file = monitor.export_metrics_csv()
        logger.info(f"Estatísticas: Métricas exportadas para: {metrics_file}")

if __name__ == "__main__":
    import sys

    # Permitir passar SSID como argumento de linha de comando
    ssid = None
    if len(sys.argv) > 1:
        ssid = sys.argv[1]
        logger.info(f"Usando SSID fornecido: {ssid[:50]}...")

    asyncio.run(run_monitoring_demo(ssid))