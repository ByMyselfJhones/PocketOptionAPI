"""
# Autor: ByMyselfJhones
# Função: Inicialização de WebDriver
# Descrição:
# - Inicializa e configura um WebDriver do Selenium para os navegadores Chrome ou Firefox.
# - Não utiliza perfis persistentes para evitar criação de pastas de perfil (como chrome_profile).
# - Utiliza ChromeDriverManager e GeckoDriverManager para download automático dos drivers.
# - Configura opções avançadas, como tamanho de janela, desativação de GPU e logging de performance.
# - Inclui logging detalhado em PT-BR com emojis e formato de data personalizado.
"""

import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager

# Configura o logging com formato personalizado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S"
)
logger = logging.getLogger(__name__)

def get_driver(browser_name: str = "chrome"):
    """
    Inicializa e retorna uma instância do Selenium WebDriver para o navegador especificado.
    Gerencia automaticamente o download e configuração do driver sem usar perfis persistentes.

    Args:
        browser_name: Nome do navegador a ser usado ('chrome' ou 'firefox'). Padrão: 'chrome'.

    Returns:
        Instância configurada do Selenium WebDriver.

    Raises:
        ValueError: Se um nome de navegador não suportado for fornecido.
    """
    if browser_name.lower() == "chrome":
        chrome_options = ChromeOptions()

        # Adiciona argumentos para otimizar a operação do navegador
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        # Habilita logging de performance para capturar eventos de rede
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        logger.info("🚀 Iniciando Chrome WebDriver...")
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("✅ WebDriver Chrome iniciado com sucesso.")
            return driver
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Chrome WebDriver: {e}")
            raise

    elif browser_name.lower() == "firefox":
        firefox_options = FirefoxOptions()

        # Define tamanho da janela para renderização consistente
        firefox_options.add_argument("--width=1920")
        firefox_options.add_argument("--height=1080")

        # Tenta habilitar persistência de logs de rede
        firefox_options.set_capability(
            "moz:firefoxOptions", {"prefs": {"devtools.netmonitor.persistlog": True}}
        )

        logger.info("🚀 Iniciando Firefox WebDriver...")
        try:
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=firefox_options)
            logger.info("✅ WebDriver Firefox iniciado com sucesso.")
            return driver
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Firefox WebDriver: {e}")
            raise

    else:
        raise ValueError(
            f"❌ Navegador não suportado: {browser_name}. Escolha 'chrome' ou 'firefox'."
        )