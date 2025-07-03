"""
# Autor: ByMyselfJhones
# Função: Sincronização de tempo para API WebSocket
# Descrição:
# - Gerencia timestamp do servidor e tempos de expiração
# - Fornece data/hora do servidor e expiração em formatos datetime e timestamp
"""

import time, datetime

from pocketoptionapi.ws.objects.base import Base


class TimeSync(Base):
    """Class for Pocket Option TimeSync websocket object."""

    def __init__(self):
        super(TimeSync, self).__init__()
        self.__name = "timeSync"
        self.__server_timestamp = time.time()
        self.__expiration_time = 1

    @property
    def server_timestamp(self):
        return self.__server_timestamp

    @server_timestamp.setter
    def server_timestamp(self, timestamp):
        self.__server_timestamp = timestamp

    @property
    def server_datetime(self):
        return datetime.datetime.fromtimestamp(self.server_timestamp)

    @property
    def expiration_time(self):
        return self.__expiration_time

    @expiration_time.setter
    def expiration_time(self, minutes):
        self.__expiration_time = minutes

    @property
    def expiration_datetime(self):
        return self.server_datetime + datetime.timedelta(minutes=self.expiration_time)

    @property
    def expiration_timestamp(self):
        return time.mktime(self.expiration_datetime.timetuple())


