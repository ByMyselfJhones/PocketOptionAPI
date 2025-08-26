"""
# Autor: ByMyselfJhones
# Função: Configurações e Constantes
# Descrição:
# - Define constantes para a API da PocketOption
# - Inclui mapeamento de ativos, regiões WebSocket e prazos
# - Configura limites da API e cabeçalhos padrão
"""

from typing import Dict, List
import random

# Mapeamento de ativos com seus respectivos IDs
ASSETS: Dict[str, int] = {
    # Pares Forex principais
    "EURUSD": 1,
    "GBPUSD": 56,
    "USDJPY": 63,
    "USDCHF": 62,
    "USDCAD": 61,
    "AUDUSD": 40,
    "NZDUSD": 90,
    # Pares Forex OTC
    "EURUSD_OTC": 66,
    "GBPUSD_OTC": 86,
    "USDJPY_OTC": 93,
    "USDCHF_OTC": 92,
    "USDCAD_OTC": 91,
    "AUDUSD_OTC": 71,
    "AUDNZD_OTC": 70,
    "AUDCAD_OTC": 67,
    "AUDCHF_OTC": 68,
    "AUDJPY_OTC": 69,
    "CADCHF_OTC": 72,
    "CADJPY_OTC": 73,
    "CHFJPY_OTC": 74,
    "EURCHF_OTC": 77,
    "EURGBP_OTC": 78,
    "EURJPY_OTC": 79,
    "EURNZD_OTC": 80,
    "GBPAUD_OTC": 81,
    "GBPJPY_OTC": 84,
    "NZDJPY_OTC": 89,
    "NZDUSD_OTC": 90,
    # Commodities
    "XAUUSD": 2,  # Ouro
    "XAUUSD_OTC": 169,
    "XAGUSD": 65,  # Prata
    "XAGUSD_OTC": 167,
    "UKBrent": 50,  # Petróleo
    "UKBrent_OTC": 164,
    "USCrude": 64,
    "USCrude_OTC": 165,
    "XNGUSD": 311,  # Gás Natural
    "XNGUSD_OTC": 399,
    "XPTUSD": 312,  # Platina
    "XPTUSD_OTC": 400,
    "XPDUSD": 313,  # Paládio
    "XPDUSD_OTC": 401,
    # Criptomoedas
    "BTCUSD": 197,
    "ETHUSD": 272,
    "DASH_USD": 209,
    "BTCGBP": 453,
    "BTCJPY": 454,
    "BCHEUR": 450,
    "BCHGBP": 451,
    "BCHJPY": 452,
    "DOTUSD": 458,
    "LNKUSD": 464,
    # Índices de ações
    "SP500": 321,
    "SP500_OTC": 408,
    "NASUSD": 323,
    "NASUSD_OTC": 410,
    "DJI30": 322,
    "DJI30_OTC": 409,
    "JPN225": 317,
    "JPN225_OTC": 405,
    "D30EUR": 318,
    "D30EUR_OTC": 406,
    "E50EUR": 319,
    "E50EUR_OTC": 407,
    "F40EUR": 316,
    "F40EUR_OTC": 404,
    "E35EUR": 314,
    "E35EUR_OTC": 402,
    "100GBP": 315,
    "100GBP_OTC": 403,
    "AUS200": 305,
    "AUS200_OTC": 306,
    "CAC40": 455,
    "AEX25": 449,
    "SMI20": 466,
    "H33HKD": 463,
    # Ações dos EUA
    "#AAPL": 5,
    "#AAPL_OTC": 170,
    "#MSFT": 24,
    "#MSFT_OTC": 176,
    "#TSLA": 186,
    "#TSLA_OTC": 196,
    "#FB": 177,
    "#FB_OTC": 187,
    "#AMZN_OTC": 412,
    "#NFLX": 182,
    "#NFLX_OTC": 429,
    "#INTC": 180,
    "#INTC_OTC": 190,
    "#BA": 8,
    "#BA_OTC": 292,
    "#JPM": 20,
    "#JNJ": 144,
    "#JNJ_OTC": 296,
    "#PFE": 147,
    "#PFE_OTC": 297,
    "#XOM": 153,
    "#XOM_OTC": 426,
    "#AXP": 140,
    "#AXP_OTC": 291,
    "#MCD": 23,
    "#MCD_OTC": 175,
    "#CSCO": 154,
    "#CSCO_OTC": 427,
    "#VISA_OTC": 416,
    "#CITI": 326,
    "#CITI_OTC": 413,
    "#FDX_OTC": 414,
    "#TWITTER": 330,
    "#TWITTER_OTC": 415,
    "#BABA": 183,
    "#BABA_OTC": 428,
    # Ativos adicionais
    "EURRUB_OTC": 200,
    "USDRUB_OTC": 199,
    "EURHUF_OTC": 460,
    "CHFNOK_OTC": 457,
    # Microsoft e outras ações de tecnologia
    "Microsoft_OTC": 521,
    "Facebook_OTC": 522,
    "Tesla_OTC": 523,
    "Boeing_OTC": 524,
    "American_Express_OTC": 525,
}

# Regiões WebSocket com suas URLs
class Regions:
    """Endpoints de regiões WebSocket"""

    _REGIONS = {
        "EUROPA": "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "SEYCHELLES": "wss://api-sc.po.market/socket.io/?EIO=4&transport=websocket",
        "HONGKONG": "wss://api-hk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER1": "wss://api-spb.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE2": "wss://api-fr2.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES4": "wss://api-us4.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES3": "wss://api-us3.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES2": "wss://api-us2.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO": "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO_2": "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES": "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
        "RUSSIA": "wss://api-msk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER2": "wss://api-l.po.market/socket.io/?EIO=4&transport=websocket",
        "INDIA": "wss://api-in.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE": "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
        "FINLAND": "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER3": "wss://api-c.po.market/socket.io/?EIO=4&transport=websocket",
        "ASIA": "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER4": "wss://api-us-south.po.market/socket.io/?EIO=4&transport=websocket",
    }

    @classmethod
    def get_all(cls, randomize: bool = True) -> List[str]:
        """Obter todas as URLs de regiões"""
        urls = list(cls._REGIONS.values())
        if randomize:
            random.shuffle(urls)
        return urls

    @classmethod
    def get_all_regions(cls) -> Dict[str, str]:
        """Obter todas as regiões como dicionário"""
        return cls._REGIONS.copy()

    from typing import Optional

    @classmethod
    def get_region(cls, region_name: str) -> Optional[str]:
        """Obter URL de uma região específica"""
        return cls._REGIONS.get(region_name.upper())

    @classmethod
    def get_demo_regions(cls) -> List[str]:
        """Obter URLs de regiões demo"""
        return [url for name, url in cls._REGIONS.items() if "DEMO" in name]

# Constantes globais
REGIONS = Regions()

# Prazos (em segundos)
TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

# Configurações de conexão
CONNECTION_SETTINGS = {
    "ping_interval": 20,  # segundos
    "ping_timeout": 10,  # segundos
    "close_timeout": 10,  # segundos
    "max_reconnect_attempts": 5,
    "reconnect_delay": 5,  # segundos
    "message_timeout": 30,  # segundos
}

# Limites da API
API_LIMITS = {
    "min_order_amount": 1.0,
    "max_order_amount": 50000.0,
    "min_duration": 5,  # segundos
    "max_duration": 43200,  # 12 horas em segundos
    "max_concurrent_orders": 10,
    "rate_limit": 100,  # requisições por minuto
}

# Cabeçalhos padrão
DEFAULT_HEADERS = {
    "Origin": "https://pocketoption.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}