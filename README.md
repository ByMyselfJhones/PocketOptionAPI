# 🚀 PocketOption API

[![GitHub](https://img.shields.io/badge/GitHub-ByMyselfJhones-blue?style=flat-square&logo=github)](https://github.com/ByMyselfJhones)
[![Telegram](https://img.shields.io/badge/Telegram-@traderjhonesofc-blue?style=flat-square&logo=telegram)](https://t.me/traderjhonesofc)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.12.7-blue?style=flat-square)](https://www.python.org)

> Uma API Python robusta e moderna para integração com a PocketOption, oferecendo uma interface limpa e eficiente para Automação de Operações.

![Preview da API](pocketoption.png)

## ✨ Destaques

- 🔐 **Autenticação Segura**: Login Via SSID e Gerenciamento de Sessão Robusto
- 💹 **Trading Automatizado**: Operações de Compra e Venda Programáticas
- 📊 **Dados em Tempo Real**: WebSocket para Cotações e Operações
- 📈 **Análise Técnica**: Acesso a Dados Históricos e Indicadores
- 🛡️ **Estabilidade**: Reconexão Automática e Tratamento de Erros
- 🔄 **Versátil**: Suporte a Conta de Demonstração e Real

## 🛠️ Instalação

> **Nota**: Recomenda-se atualizar o `pip` antes de instalar as dependências para garantir compatibilidade:
> ```bash
> python -m pip install --upgrade pip
> ```

### Via pip (Recomendado):
```bash
pip install git+https://github.com/ByMyselfJhones/PocketOptionAPI.git
```

### Para Desenvolvimento:
```bash
git clone https://github.com/ByMyselfJhones/PocketOptionAPI.git
cd PocketOptionAPI
pip install -e .
```

## 📖 Uso Básico

```python
from pocketoptionapi.client import PocketOptionClient
from pocketoptionapi.config import Config
import logging

# Configurar Logging (opcional)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuração da Sessão
config = Config(
    ssid='42["auth",{"session":"sua_sessao_aqui","isDemo":1,"uid":seu_uid_aqui,"platform":2}]',
    is_demo=True  # True para conta demo, False para conta real
)

# Inicializar Cliente
client = PocketOptionClient(config)

# Conectar
client.connect()
print("✅ Conectado!")

# Consultar saldo
saldo = client.get_balance()
print(f"💰 Saldo: ${saldo:.2f}")

# Realizar operação
resultado = client.buy(
    price=10,           # Valor em $
    asset="EURUSD_OTC", # Par de moedas (note o sufixo _OTC)
    direction="CALL",   # "CALL" (Alta) ou "PUT" (Baixa)
    duration=1          # Expiração em minutos
)

if resultado["success"]:
    print(f"✅ Operação Realizada: ID {resultado['order_id']}")
```

## 🎯 Recursos Avançados

### WebSocket em Tempo Real
```python
# Callback para Preços em Tempo Real
@api.on_price_update
def price_handler(data):
    print(f"📊 {data['asset']}: ${data['price']}")

# Callback para Resultados de Operações
@api.on_trade_complete
def trade_handler(result):
    print(f"💫 Resultado: {'✅ Vitória' if result['win'] else '❌ Derrota'}")
```

### Análise Técnica
```python
# Obter histórico de candles
candles = api.get_candles(
    asset="EURUSD_OTC",  # Note o sufixo _OTC para ativos OTC
    interval=60,         # Intervalo em segundos
    count=100           # Quantidade de candles
)

# Análise dos Dados
import pandas as pd
df = pd.DataFrame(candles)
print(f"📈 Média Móvel: {df['close'].rolling(20).mean().iloc[-1]:.5f}")
```

## 🔧 Configuração

### Dependências Principais
```txt
aiohttp>=3.8.0
certifi==2025.6.15
charset-normalizer==3.4.2
colorama==0.4.6
idna==3.10
loguru>=0.7.2
numpy==2.3.1
pandas>=2.3.0
psutil>=5.9.0
pydantic>=2.0.0
python-dateutil>=2.9.0.post0
python-dotenv>=1.0.0
pytz==2025.2
requests==2.32.4
rich>=13.0.0
selenium>=4.0.0
setuptools==80.9.0
six==1.17.0
typing-extensions>=4.0.0
tzdata==2025.2
tzlocal>=5.3.1
urllib3==2.5.0
webdriver-manager>=4.0.0
websocket-client==1.8.0
websockets>=15.0.1
wheel==0.45.1
```

### Obtendo o SSID
Para usar a API com Dados Reais, você precisa Extrair seu ID de Sessão do Navegador:

1. **Abra a PocketOption no seu navegador**
2. **Abra as Ferramentas do Desenvolvedor (F12)**
3. **Vá para a aba Network (Rede)**
4. **Filtre por WebSocket (WS)**
5. **Procure pela mensagem de Autenticação começando com `42["auth"`**
6. **Copie a mensagem completa, incluindo o formato `42["auth",{...}]`**

Exemplo de formato de SSID:
```
42["auth",{"session":"abcd1234efgh5678","isDemo":1,"uid":12345,"platform":1}]
```

Se você não conseguir encontrá-lo, tente executar o script de extração automática de SSID na pasta [tools_ferramentas](tools_ferramentas).

## 📂 Estrutura do Projeto

```
pocketoptionapi_async/
├── __init__.py            # Inicialização do pacote
├── client.py              # Cliente principal da API
├── config.py              # Configurações da API
├── connection_keep_alive.py # Manutenção de conexão
├── connection_monitor.py  # Monitoramento de conexão
├── constants.py           # Constantes da API
├── exceptions.py          # Exceções personalizadas
├── models.py              # Modelos de dados
├── monitoring.py          # Ferramentas de monitoramento
├── utils.py               # Funções utilitárias
├── websocket_client.py    # Cliente WebSocket
```

## 🤝 Contribuindo

Sua contribuição é muito bem-vinda! Siga estes passos:

1. 🍴 Fork este Repositório
2. 🔄 Crie uma branch para sua feature
   ```bash
   git checkout -b feature/MinhaFeature
   ```
3. 💻 Faça suas Alterações
4. ✅ Commit usando mensagens convencionais
   ```bash
   git commit -m "feat: Adiciona nova funcionalidade"
   ```
5. 📤 Push para sua branch
   ```bash
   git push origin feature/MinhaFeature
   ```
6. 🔍 Abra um Pull Request

## 📜 Licença

Este projeto está licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.

## ⚠️ Aviso Legal

Este projeto é uma implementação não oficial e não possui vínculo com a PocketOption. Use por sua conta e risco. O desenvolvedor não se responsabiliza por perdas financeiras ou outros danos.

## 📞 Suporte

- 💬 Telegram: [Trader Jhones](https://t.me/traderjhonesofc)
- 🌐 Website: [ByMyselfJhones](https://github.com/ByMyselfJhones)

---

<p align="center">
  Desenvolvido com ❤️ por <a href="https://github.com/ByMyselfJhones">ByMyselfJhones</a>
</p>