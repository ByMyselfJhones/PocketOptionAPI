"""
# Autor: ByMyselfJhones
# Função: Módulo para obtenção de candles via WebSocket da Pocket Option
# Descrição:
# - Gera índices aleatórios para requisições
# - Calcula offsets com base no intervalo de tempo
# - Envia requisições WebSocket para obter candles de ativos
"""

from pocketoptionapi.ws.channels.base import Base
import time, random


def index_num():
    minimum = 5000
    maximum = 10000 - 1
    return random.randint(minimum, maximum)


def offset_count(interval):
    offsets = {5: 1000, 10: 2000, 15: 3000, 30: 6000, 60: 9000, 120: 18000, 180: 27000, 300: 45000, 600: 90000, 900: 135000, 1800: 270000, 3600: 540000, 14400: 2160000, 86400: 12960000}
    if interval in offsets:
        return offsets[interval]
    else:
        return 9000


class GetCandles(Base):

    name = "sendMessage"

    def __call__(self, active_id, interval, end_time, count=1):
        data = {
            "asset": str(active_id),
            "index": index_num(),
            "time": end_time + 7200, #- offset_count(interval) * count,
            "offset": offset_count(interval),
            "period": interval,
        }
        # print(data)

        data = ["loadHistoryPeriod", data]

        self.send_websocket_request(self.name, data)
