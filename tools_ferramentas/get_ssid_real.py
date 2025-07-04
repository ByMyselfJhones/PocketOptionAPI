"""
# Autor: ByMyselfJhones
# Função: Automação de Login e Extração de SSID para Conta Real
# Descrição:
# - Automatiza o login na plataforma PocketOption e navega até a página de negociação real.
# - Extrai o SSID (Session ID) de mensagens WebSocket usando regex para capturar o padrão de autenticação.
# - Salva o SSID extraído em um arquivo: SSID_REAL.txt, dentro da pasta GET_SSID.
# - Utiliza Selenium WebDriver com Chrome para navegação e captura de logs de performance.
# - Inclui logging estruturado com mensagens em PT-BR, emojis e formato de data personalizado.
# - Versão atualizada com regex flexível, tentativas múltiplas, validação simplificada e logging detalhado.
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
                record.msg = "🔧 Gerenciador WebDriver em ação..."
            elif "Get LATEST chromedriver version" in record.msg:
                record.msg = "🔍 Buscando versão mais recente do chromedriver para google-chrome..."
            elif "Driver [" in record.msg:
                record.msg = f"💾 Driver [{record.msg.split('Driver [')[1]} encontrado no cache."
        return True

# Aplica o filtro ao logger raiz
logging.getLogger().addFilter(WDMFilter())

def save_to_file(filename: str, value: str):
    """
    Salva o valor fornecido no arquivo especificado dentro da pasta GET_SSID.

    Args:
        filename: Nome do arquivo para salvar o valor (ex.: SSID_REAL.txt).
        value: Valor a ser escrito no arquivo.
    """
    profile_dir = os.path.join(os.getcwd(), "GET_SSID")
    os.makedirs(profile_dir, exist_ok=True)
    file_path = os.path.join(profile_dir, filename)
    with open(file_path, "w") as f:
        f.write(value)
    logger.info(f"💾 SSID salvo com sucesso em {file_path}")
    logger.info(f"📁 SSID da Conta Real salvo em {filename}")

def save_payloads_to_file(payloads: List[str]):
    """
    Salva todos os payloads WebSocket em um arquivo para depuração.

    Args:
        payloads: Lista de payloads WebSocket capturados.
    """
    profile_dir = os.path.join(os.getcwd(), "GET_SSID")
    os.makedirs(profile_dir, exist_ok=True)
    file_path = os.path.join(profile_dir, "websocket_payloads_real.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for payload in payloads:
            f.write(payload + "\n")
    logger.info(f"📝 Payloads WebSocket salvos em {file_path} para depuração.")

def validate_ssid(ssid: str) -> bool:
    """
    Valida se o SSID capturado contém o campo 'session'.

    Args:
        ssid: String do SSID capturado.

    Returns:
        bool: True se válido, False caso contrário.
    """
    try:
        # Extrai o JSON do SSID
        json_str = ssid[2:]  # Remove o prefixo "42"
        data = json.loads(json_str)[1]
        if "session" not in data:
            logger.error("❌ Campo 'session' não encontrado no SSID.")
            return False
        if "isDemo" in data and data["isDemo"] != 0:
            logger.warning("⚠️ SSID não corresponde a uma conta real (isDemo != 0).")
        return True
    except json.JSONDecodeError:
        logger.error("❌ Erro ao decodificar JSON do SSID.")
        return False

def get_pocketoption_ssid():
    """
    Automatiza o processo de login na PocketOption, navega até a página de negociação real
    e captura o tráfego WebSocket para extrair o SSID da Conta Real.
    O SSID extraído é salvo em SSID_REAL.txt dentro da pasta GET_SSID.
    """
    driver = None
    try:
        # Configurações
        websocket_timeout = 30  # Tempo de espera inicial para WebSocket (segundos)
        max_attempts = 3  # Número máximo de tentativas para capturar SSID
        attempt_interval = 10  # Intervalo entre tentativas (segundos)
        driver = get_driver("chrome")
        login_url = "https://pocketoption.com/pt/login"
        cabinet_base_url = "https://pocketoption.com/pt/cabinet"
        real_url = "https://pocketoption.com/pt/cabinet/quick-high-low/"
        # Regex flexível para capturar mensagens de autenticação
        ssid_pattern = r'(42\["auth",\{.*"session":"[^"]+".*\}\])'

        logger.info(f"🌐 Acessando página de login: {login_url}")
        driver.get(login_url)

        # Aguarda o login manual do usuário
        logger.info(f"⏳ Aguardando login do usuário e redirecionamento para {cabinet_base_url}...")
        WebDriverWait(driver, 9999).until(EC.url_contains(cabinet_base_url))
        logger.info("🔓 Login bem-sucedido! Página principal carregada.")

        # Processa a Conta Real
        logger.info(f"🎯 Acessando Conta Real: {real_url}")
        driver.get(real_url)

        # Aguarda o carregamento completo da página real
        WebDriverWait(driver, 60).until(EC.url_contains(real_url))
        logger.info("📈 Página real carregada com sucesso.")

        # Captura logs de performance em múltiplas tentativas
        found_full_ssid_string = None
        all_payloads = []
        for attempt in range(1, max_attempts + 1):
            logger.info(f"⏱️  Tentativa {attempt}/{max_attempts}: Aguardando {attempt_interval} segundos para conexões WebSocket da Conta Real.")
            time.sleep(attempt_interval)

            # Captura logs de performance
            get_log = getattr(driver, "get_log", None)
            if not callable(get_log):
                raise AttributeError(
                    "Seu WebDriver não suporta get_log(). Certifique-se de usar Chrome com logging de performance habilitado."
                )
            performance_logs = cast(List[Dict[str, Any]], get_log("performance"))
            logger.info(f"📥 Coletado {len(performance_logs)} entradas de log de desempenho na tentativa {attempt}.")

            # Itera pelos logs para encontrar frames WebSocket
            for entry in performance_logs:
                message = json.loads(entry["message"])
                if (
                    message["message"]["method"] == "Network.webSocketFrameReceived"
                    or message["message"]["method"] == "Network.webSocketFrameSent"
                ):
                    payload_data = message["message"]["params"]["response"]["payloadData"]
                    all_payloads.append(payload_data)
                    # Log payload para depuração
                    logger.debug(f"🔍 Payload WebSocket (tentativa {attempt}): {payload_data}")
                    match = re.search(ssid_pattern, payload_data)
                    if match:
                        found_full_ssid_string = match.group(1)
                        logger.info(f"🔐 SSID capturado com sucesso: {found_full_ssid_string[:50]}...")
                        break
            if found_full_ssid_string:
                break

        # Salva payloads para depuração
        if all_payloads:
            save_payloads_to_file(all_payloads)

        if found_full_ssid_string and validate_ssid(found_full_ssid_string):
            # Salva em SSID_REAL.txt
            save_to_file("SSID_REAL.txt", found_full_ssid_string)
        else:
            logger.warning("⚠️ Padrão de SSID completo não encontrado ou inválido após todas as tentativas.")

    except Exception as e:
        logger.error(f"❌ Ocorreu um erro: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("🚪 WebDriver fechado.")

if __name__ == "__main__":
    get_pocketoption_ssid()