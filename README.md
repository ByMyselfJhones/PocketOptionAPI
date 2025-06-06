# 🚀 PocketOption API

[![GitHub](https://img.shields.io/badge/GitHub-ByMyselfJhones-blue?style=flat-square&logo=github)](https://github.com/ByMyselfJhones)
[![Telegram](https://img.shields.io/badge/Telegram-@traderjhonesofc-blue?style=flat-square&logo=telegram)](https://t.me/traderjhonesofc)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

> Uma API Python robusta e moderna para integração com a PocketOption, oferecendo uma interface limpa e eficiente para automação de operações.

![Preview da API](pocketoption.png)

## ✨ Destaques

- 🔐 **Autenticação Segura**: Login via SSID e gerenciamento de sessão robusto
- 💹 **Trading Automatizado**: Operações de compra e venda programáticas
- 📊 **Dados em Tempo Real**: WebSocket para cotações e operações
- 📈 **Análise Técnica**: Acesso a dados históricos e indicadores
- 🛡️ **Estabilidade**: Reconexão automática e tratamento de erros
- 🔄 **Versátil**: Suporte a contas demo e real

## 🛠️ Instalação

### Via pip (recomendado):
```bash
pip install git+https://github.com/ByMyselfJhones/pocketoptionapi.git
```

### Para desenvolvimento:
```bash
git clone https://github.com/ByMyselfJhones/pocketoptionapi.git
cd pocketoptionapi
pip install -e .
```

## 📖 Uso Básico

```python
from pocketoptionapi.stable_api import PocketOption
import logging

# Configurar logging (opcional)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

# Configuração da sessão
ssid = """42["auth",{"session":"sua_sessao_aqui","isDemo":1,"uid":seu_uid_aqui,"platform":2}]"""
demo = True  # True para conta demo, False para conta real

# Inicializar API
api = PocketOption(ssid, demo)

# Conectar
connect = api.connect()
print(connect)

# Consultar saldo
saldo = api.get_balance()
print(f"💰 Saldo: ${saldo:.2f}")

# Realizar operação
resultado = api.buy(
    price=10,           # Valor em $
    asset="EURUSD_otc", # Par de moedas (note o sufixo _otc)
    direction="call",   # "call" (Alta) ou "put" (Baixa)
    duration=1          # Expiração em minutos
)

if resultado["success"]:
    print(f"✅ Operação realizada: ID {resultado['order_id']}")
```

## 🎯 Recursos Avançados

### WebSocket em Tempo Real
```python
# Callback para preços em tempo real
@api.on_price_update
def price_handler(data):
    print(f"📊 {data['asset']}: ${data['price']}")

# Callback para resultados de operações
@api.on_trade_complete
def trade_handler(result):
    print(f"💫 Resultado: {'✅ Gain' if result['win'] else '❌ Loss'}")
```

### Análise Técnica
```python
# Obter histórico de candles
candles = api.get_candles(
    asset="EURUSD_otc",  # Note o sufixo _otc para ativos OTC
    interval=60,         # Intervalo em segundos
    count=100           # Quantidade de candles
)

# Análise dos dados
import pandas as pd
df = pd.DataFrame(candles)
print(f"📈 Média móvel: {df['close'].rolling(20).mean().iloc[-1]:.5f}")
```

## 🔧 Configuração

### Dependências Principais
```txt
websocket-client>=1.6.1
requests>=2.31.0
python-dateutil>=2.8.2
pandas>=2.1.3
```

### Obtendo o SSID
Para obter o SSID necessário para autenticação:

1. Faça login na plataforma PocketOption pelo navegador
2. Abra as Ferramentas do Desenvolvedor (F12)
3. Vá para a aba "Network" (Rede)
4. Procure por conexões WebSocket
5. Encontre a mensagem de autenticação que contém o SSID
6. Copie o SSID completo no formato mostrado no exemplo

## 🤝 Contribuindo

Sua contribuição é muito bem-vinda! Siga estes passos:

1. 🍴 Fork este repositório
2. 🔄 Crie uma branch para sua feature
   ```bash
   git checkout -b feature/MinhaFeature
   ```
3. 💻 Faça suas alterações
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

Este projeto é uma implementação não oficial e não possui vínculo com a PocketOption. Use por sua conta e risco.

## 📞 Suporte

- 💬 Telegram: [Trader Jhones](https://t.me/traderjhonesofc)
- 🌐 Website: [ByMyselfJhones](https://github.com/ByMyselfJhones)

---

<p align="center">
  Desenvolvido com ❤️ por <a href="https://github.com/ByMyselfJhones">ByMyselfJhones</a>
</p>
