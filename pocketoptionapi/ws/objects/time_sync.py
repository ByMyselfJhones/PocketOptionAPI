"""
# Autor: ByMyselfJhones
# Função: Sincronização de tempo com servidor
# Descrição:
# - Sincroniza timestamp local com timestamp do servidor
# - Retorna datetime ajustado em UTC com base na sincronização
# - Levanta erro se não sincronizado
"""

from datetime import datetime, timezone

class TimeSynchronizer:
    def __init__(self):
        self.server_time_reference = None
        self.local_time_reference = None

    def synchronize(self, server_timestamp):
        self.server_time_reference = server_timestamp
        self.local_time_reference = datetime.now(timezone.utc).timestamp()

    def get_synced_datetime(self):
        if self.server_time_reference is None or self.local_time_reference is None:
            raise ValueError("The time has not yet been synchronized.")

        # Calculates the elapsed time since the last synchronization
        time_elapsed = datetime.now(timezone.utc).timestamp() - self.local_time_reference

        # Adjust server timestamp with elapsed time
        synced_timestamp = self.server_time_reference + time_elapsed

        # Convert to datetime
        return datetime.fromtimestamp(synced_timestamp, timezone.utc)
