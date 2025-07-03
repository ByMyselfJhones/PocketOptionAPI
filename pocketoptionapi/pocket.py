"""
# Autor: ByMyselfJhones
# Função: API para comunicação com servidor PocketOption via WebSocket
# Descrição:
# - Inicializa e gerencia conexões WebSocket (principal e chat)
# - Envia requisições e mensagens ao servidor
# - Mantém conexão ativa com pings automáticos
# - Gerencia login e reconexões em caso de falha
"""

from pocketoptionapi.backend.ws.client import WebSocketClient
from pocketoptionapi.backend.ws.chat import WebSocketClientChat
import pocketoptionapi.global_value as global_value
import threading, ssl, decimal, json, urllib, websocket, pause
from websocket._exceptions import WebSocketException

class PocketOptionApi:
    def __init__(self, init_msg) -> None:
        self.ws_url = "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket"
        self.token = "TEST_TOKEN"
        self.connected_event = threading.Event()
        self.client = WebSocketClient(self.ws_url)
        # self.logger = logging.getLogger(__name__)
        # self.logger.setLevel(logging.INFO)
        self.init_msg = init_msg
        # formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        self.websocket_client = WebSocketClient(self.ws_url, pocket_api_instance=self)

        # Create file handler and add it to the logger
        # file_handler = logging.FileHandler('pocket.log')
        # file_handler.setFormatter(formatter)
        # self.logger.addHandler(file_handler)

        # self.logger.info(f"initialiting Pocket API with token: {self.token}")
        global_value.logger("initialiting Pocket API with token: %s" % str(self.token), "DEBUG")

        self.websocket_client_chat = WebSocketClientChat(url="wss://chat-po.site/cabinet-client/socket.io/?EIO=4&transport=websocket")
        self.websocket_client_chat.run()

        # self.logger.info("Send chat websocket")
        global_value.logger("Send chat websocket", "DEBUG")

        self.websocket_client.ws.run_forever()
    def auto_ping(self):
        # self.logger.info("Starting auto ping thread")
        global_value.logger("Starting auto ping thread", "DEBUG")
        pause.seconds(5)
        while True:
            try:
                if self.websocket_client.ws.sock and self.websocket_client.ws.sock.connected:  # Check if socket is connected
                    self.ping()
                else:
                    # self.logger.warning("WebSocket is not connected. Attempting to reconnect.")
                    global_value.logger("WebSocket is not connected. Attempting to reconnect.", "WARNING")
                    # Attempt reconnection
                    if self.connect():
                        # self.logger.info("Successfully reconnected.")
                        global_value.logger("Successfully reconnected.", "DEBUG")
                    else:
                        # self.logger.warning("Reconnection attempt failed.")
                        global_value.logger("Reconnection attempt failed.", "WARNING")
                    try:
                        self.ping()
                        # self.logger.info("Sent ping reuqests successfully!")
                        global_value.logger("Sent ping reuqests successfully!", "DEBUG")
                    except Exception as e:
                        # self.logger.error(f"A error ocured trying to send ping: {e}")
                        global_value.logger("A error ocured trying to send ping: %s" % str(e), "ERROR")
            except Exception as e:  # Catch exceptions and log them
                # self.logger.error(f"An error occurred while sending ping or attempting to reconnect: {e}")
                global_value.logger("An error occurred while sending ping or attempting to reconnect: %s" % str(e), "ERROR")
                try:
                    # self.logger.warning("Trying again...")
                    global_value.logger("Trying again...", "WARNING")
                    v1 = self.connect()
                    if v1:
                        # self.logger.info("Conection completed!, sending ping...")
                        global_value.logger("Conection completed!, sending ping...", "DEBUG")
                        self.ping()
                    else:
                        self.logger.error("Connection was not established")
                        global_value.logger("Connection was not established", "ERROR")
                except Exception as e:
                    # self.logger.error(f"A error ocured when trying again: {e}")
                    global_value.logger("A error ocured when trying again: %s" % str(e), "ERROR")

    def connect(self):
        # self.logger.info("Attempting to connect...")
        global_value.logger("Attempting to connect...", "DEBUG")

        self.websocket_client_chat.ws.send("40")
        data = r"""42["user_init",{"id":27658142,"secret":"8ed9be7299c3aa6363e57ae5a4e52b7a"}]"""
        self.websocket_client_chat.ws.send(data)
        try:
            self.websocket_thread = threading.Thread(target=self.websocket_client.ws.run_forever, kwargs={
                'sslopt': {
                    "check_hostname": False,
                    "cert_reqs": ssl.CERT_NONE,
                    "ca_certs": "cacert.pem"
                },
                "ping_interval": 0,
                'skip_utf8_validation': True,
                "origin": "https://pocketoption.com",
                # "http_proxy_host": '127.0.0.1', "http_proxy_port": 8890
            })

            self.websocket_thread.daemon = True
            self.websocket_thread.start()

            # self.logger.info("Connection successful.")
            global_value.logger("Connection successful.", "DEBUG")

            self.send_websocket_request(msg="40")
            self.send_websocket_request(self.init_msg)
        except Exception as e:
            # print(f"Going for exception.... error: {e}")
            global_value.logger("Going for exception.... error: %s" % str(e), "ERROR")
            # self.logger.error(f"Connection failed with exception: {e}")
            global_value.logger("Connection failed with exception: %s" % str(e), "ERROR")
    def send_websocket_request(self, msg):
        """Send websocket request to PocketOption server.
        :param dict msg: The websocket request msg.
        """
        # self.logger.info(f"Sending websocket request: {msg}")
        global_value.logger("Sending websocket request: %s" % str(msg), "DEBUG")
        def default(obj):
            if isinstance(obj, decimal.Decimal):
                return str(obj)
            raise TypeError

        data = json.dumps(msg, default=default)

        try:
            # self.logger.info("Request sent successfully.")
            global_value.logger("Request sent successfully.", "DEBUG")
            self.websocket_client.ws.send(bytearray(urllib.parse.quote(data).encode('utf-8')), opcode=websocket.ABNF.OPCODE_BINARY)
            return True
        except Exception as e:
            # self.logger.error(f"Failed to send request with exception: {e}")
            global_value.logger("Failed to send request with exception: %s" % str(e), "ERROR")
            # Consider adding any necessary exception handling code here
            try:
                self.websocket_client.ws.send(bytearray(urllib.parse.quote(data).encode('utf-8')), opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception as e:
                # self.logger.warning(f"Was not able to reconnect: {e}")
                global_value.logger("Was not able to reconnect: %s" % str(e), "WARNING")

    def _login(self, init_msg):
        # self.logger.info("Trying to login...")
        global_value.logger("Trying to login...", "DEBUG")

        self.websocket_thread = threading.Thread(target=self.websocket_client.ws.run_forever, kwargs={
                'sslopt': {
                    "check_hostname": False,
                    "cert_reqs": ssl.CERT_NONE,
                    "ca_certs": "cacert.pem"
                },
                "ping_interval": 0,
                'skip_utf8_validation': True,
                "origin": "https://pocketoption.com",
                # "http_proxy_host": '127.0.0.1', "http_proxy_port": 8890
            })

        self.websocket_thread.daemon = True
        self.websocket_thread.start()

        # self.logger.info("Login thread initialised successfully!")
        global_value.logger("Login thread initialised successfully!", "DEBUG")

        # self.send_websocket_request(msg=init_msg)
        self.websocket_client.ws.send(init_msg)

        # self.logger.info(f"Message was sent successfully to log you in!, mesage: {init_msg}")
        global_value.logger("Message was sent successfully to log you in!, mesage: %s" % str(init_msg), "DEBUG")

        try:
            self.websocket_client.ws.run_forever()
        except WebSocketException as e:
            self.logger.error(f"A error ocured with websocket: {e}")
            global_value.logger("A error ocured with websocket: %s" % str(e), "ERROR")
            # self.send_websocket_request(msg=init_msg)
            try:
                self.websocket_client.ws.run_forever()
                self.send_websocket_request(msg=init_msg)
            except Exception as e:
                # self.logger.error(f"Trying again failed, skiping... error: {e}")
                global_value.logger("Trying again failed, skiping... error: %s" % str(e), "ERROR")
                # self.send_websocket_request(msg=init_msg)

    @property
    def ping(self):
        self.send_websocket_request(msg="3")
        # self.logger.info("Sent a ping request")
        global_value.logger("Sent a ping request", "DEBUG")
        return True
