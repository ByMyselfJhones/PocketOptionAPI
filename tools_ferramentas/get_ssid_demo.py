"""
# Autor: ByMyselfJhones
# Função: Automação de Login e Extração de SSID para Conta de Demonstração
# Descrição:
# - Automatiza o login na plataforma PocketOption e navega até a página de negociação demo.
# - Extrai o SSID (Session ID) de mensagens WebSocket usando regex para capturar o padrão de autenticação.
# - Salva o SSID extraído em um arquivo: SSID_DEMO.txt, dentro da pasta GET_SSID.
# - Utiliza Selenium WebDriver com Chrome para navegação e captura de logs de performance.
# - Inclui logging estruturado com mensagens em PT-BR, emojis e formato de data personalizado.
# - Versão atualizada com validação de SSID, timeout configurável e logging detalhado.
"""

import os
import json
import time
import re
import logging
from typing import cast, List, Dict, Any
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from get_driver import get_driver

# Configura o logging com formato personalizado
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Filtro para personalizar mensagens do webdriver_manager
class WDMFilter(logging.Filter):
    def filter(self, record):
        if record.name.startswith("webdriver_manager"):
            if "WebDriver manager" in record.msg:
                record.msg = "🔧 Gerenciador WebDriver em Ação..."
            elif "Get LATEST chromedriver version" in record.msg:
                record.msg = "🔍 Buscando versão mais recente do chromedriver para google-chrome..."
            elif "Driver [" in record.msg:
                record.msg = f"💾 Driver [{record.msg.split('Driver [')[1]} encontrado no Cache."
        return True

# Aplica o filtro ao logger raiz
logging.getLogger().addFilter(WDMFilter())

def save_to_file(filename: str, value: str):
    """
    Salva o valor fornecido no arquivo especificado dentro da pasta GET_SSID.

    Args:
        filename: Nome do arquivo para salvar o valor (ex.: SSID_DEMO.txt).
        value: Valor a ser escrito no arquivo.
    """
    profile_dir = os.path.join(os.getcwd(), "GET_SSID")
    os.makedirs(profile_dir, exist_ok=True)
    file_path = os.path.join(profile_dir, filename)
    with open(file_path, "w") as f:
        f.write(value)
    logger.info(f"💾 SSID salvo com Sucesso em {file_path}")
    logger.info(f"📁 SSID da Conta de Demonstração salvo em {filename}.")

def validate_ssid(ssid: str) -> bool:
    """
    Valida se o SSID capturado contém os campos esperados.

    Args:
        ssid: String do SSID capturado.

    Returns:
        bool: True se válido, False caso contrário.
    """
    try:
        # Extrai o JSON do SSID
        json_str = ssid[2:]  # Remove o prefixo "42"
        data = json.loads(json_str)[1]
        required_fields = ["session", "isDemo", "uid", "platform"]
        return all(field in data for field in required_fields) and data["isDemo"] == 1
    except json.JSONDecodeError:
        logger.error("❌ Erro ao decodificar JSON do SSID.")
        return False

def get_pocketoption_ssid():
    """
    Automatiza o processo de login na PocketOption, navega até a página de negociação demo
    e captura o tráfego WebSocket para extrair o SSID da Conta de Demonstração.
    O SSID extraído é salvo em SSID_DEMO.txt dentro da pasta GET_SSID.
    """
    driver = None
    try:
        # Configurações
        websocket_timeout = 15  # Tempo de espera para WebSocket (segundos)
        driver = get_driver("chrome")
        login_url = "https://pocketoption.com/pt/login"
        cabinet_base_url = "https://pocketoption.com/pt/cabinet"
        demo_url = "https://pocketoption.com/pt/cabinet/demo-quick-high-low/"
        # Regex mais específica para capturar mensagens de autenticação
        ssid_pattern = r'(42\["auth",\{.*"session":"[^"]+","isDemo":1.*"uid":\d+.*\}\])'

        logger.info(f"🌐 Acessando página de login: {login_url}")
        driver.get(login_url)

        # Aguarda o login manual do usuário
        logger.info(f"⏳ Aguardando Login do Usuário e redirecionamento para {cabinet_base_url}...")
        WebDriverWait(driver, 9999).until(EC.url_contains(cabinet_base_url))
        logger.info("🔓 Login bem-sucedido! Página principal carregada.")

        # Processa apenas a Conta de Demonstração
        logger.info(f"🎯 Acessando Conta de Demonstração: {demo_url}")
        driver.get(demo_url)

        # Aguarda o carregamento completo da página demo
        WebDriverWait(driver, 60).until(EC.url_contains(demo_url))
        logger.info("📈 Página Demo carregada com Sucesso.")

        # Aguarda conexões WebSocket
        logger.info(f"⏱️  Aguardando {websocket_timeout} segundos para conexões WebSocket da Conta de Demonstração.")
        time.sleep(websocket_timeout)

        # Captura logs de performance
        get_log = getattr(driver, "get_log", None)
        if not callable(get_log):
            raise AttributeError(
                "Seu WebDriver não suporta get_log(). Certifique-se de usar Chrome com logging de performance habilitado."
            )
        performance_logs = cast(List[Dict[str, Any]], get_log("performance"))
        logger.info(f"📥 Coletado {len(performance_logs)} entradas de log de desempenho da Conta de Demonstração.")

        found_full_ssid_string = None
        # Itera pelos logs para encontrar frames WebSocket
        for entry in performance_logs:
            message = json.loads(entry["message"])
            if (
                message["message"]["method"] == "Network.webSocketFrameReceived"
                or message["message"]["method"] == "Network.webSocketFrameSent"
            ):
                payload_data = message["message"]["params"]["response"]["payloadData"]
                # Log payload para depuração
                logger.debug(f"🔍 Payload WebSocket para demo: {payload_data}")
                match = re.search(ssid_pattern, payload_data)
                if match:
                    found_full_ssid_string = match.group(1)
                    logger.info(f"🔐 SSID capturado com Sucesso: {found_full_ssid_string[:50]}...")
                    break

        if found_full_ssid_string and validate_ssid(found_full_ssid_string):
            # Salva em SSID_DEMO.txt
            save_to_file("SSID_DEMO.txt", found_full_ssid_string)
        else:
            logger.warning("⚠️ Padrão de SSID completo não encontrado ou inválido nos logs WebSocket da Conta de Demonstração.")

    except Exception as e:
        logger.error(f"❌ Ocorreu um erro: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("🚪 WebDriver fechado.")

if __name__ == "__main__":
    get_pocketoption_ssid()