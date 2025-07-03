"""
# Autor: ByMyselfJhones
# Função: Envio de ordens de compra via WebSocket para Pocket Option
# Descrição:
# - Buyv3: Envia ordens com valor, ativo, direção e duração
# - Buyv3_by_raw_expired: Envia ordens com preço, ativo, direção, tipo (turbo/binary) e expiração
# - Integra com API para contas demo ou real
"""

import datetime, json, time
from pocketoptionapi.ws.channels.base import Base
import pocketoptionapi.global_value as global_value
from pocketoptionapi.expiration import get_expiration_time


class Buyv3(Base):
    name = "sendMessage"

    def __call__(self, amount, active, direction, duration, request_id):
        data_dict = {
            "asset": active,
            "amount": amount,
            "action": direction,
            "isDemo": int(global_value.DEMO),
            "requestId": request_id,
            "optionType": 100,
            "time": duration
        }

        message = ["openOrder", data_dict]

        self.send_websocket_request(self.name, message, str(request_id))


class Buyv3_by_raw_expired(Base):
    name = "sendMessage"

    def __call__(self, price, active, direction, option, expired, request_id):

        if option == "turbo":
            option_id = 3  # "turbo"
        elif option == "binary":
            option_id = 1  # "binary"
        data = {
            "body": {"price": price,
                     "active_id": active,
                     "expired": int(expired),
                     "direction": direction.lower(),
                     "option_type_id": option_id,
                     "user_balance_id": int(global_value.balance_id)
                     },
            "name": "binary-options.open-option",
            "version": "1.0"
        }
        self.send_websocket_request(self.name, data, str(request_id))
