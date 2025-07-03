"""
# Autor: ByMyselfJhones
# Função: Concatenação de arquivos CSV
# Descrição:
# - Lê dois arquivos CSV com dados AUDNZD
# - Concatena os dataframes verticalmente
# - Exibe o tamanho do dataframe resultante
# - Salva o resultado em um novo arquivo CSV
"""

import pandas as pd

# Lê os arquivos CSV
df_1 = pd.read_csv('dados_completos_AUDNZD_OTC.csv')
df_2 = pd.read_csv('dados_completos_AUDNZD_OTC_2.csv')

# Concatena os dataframes
df_full = pd.concat([df_1, df_2], axis=0)
print(df_full.shape)
# Salva o resultado
df_full.to_csv('dados_full_AUDNZD_OTC.csv', index=False)
