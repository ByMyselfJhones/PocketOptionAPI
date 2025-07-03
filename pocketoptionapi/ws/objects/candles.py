"""
# Autor: ByMyselfJhones
# Função: Gerenciamento de dados de velas financeiras
# Descrição:
# - Armazena e acessa dados de velas (abertura, fechamento, máxima, mínima, tempo)
# - Solicita velas via WebSocket por ativo, período, contagem ou intervalo de tempo
"""

from pocketoptionapi.ws.objects.base import Base


class Candles(Base):
    """Class to represent financial candles."""

    def __init__(self):
        super(Candles, self).__init__()
        self.__name = "candles"
        self.__candles_data = None

    @property
    def candles_data(self):
        return self.__candles_data

    @candles_data.setter
    def candles_data(self, candles_data):
        self.__candles_data = candles_data

    @property
    def candle_open(self):
        return self.candles_data.candle_open

    @property
    def candle_close(self):
        return self.candles_data.candle_close

    @property
    def candle_high(self):
        return self.candles_data.candle_high

    @property
    def candle_low(self):
        return self.candles_data.candle_low

    @property
    def candle_time(self):
        return self.candles_data.candle_time

    def get_candles(self, active_id, period):
        self.send_websocket_request(self.name, {"active_id": active_id,
                                              "period": period,
                                              "count": 100})

    def get_candles_v2(self, active_id, period, count, endtime):
        self.send_websocket_request(self.name, {"active_id": active_id,
                                              "period": period,
                                              "count": count,
                                              "endtime": endtime})

    def get_candles_from_to_time(self, active_id, period, from_time, to_time):
        self.send_websocket_request(self.name, {"active_id": active_id,
                                              "period": period,
                                              "from": from_time,
                                              "to": to_time})
