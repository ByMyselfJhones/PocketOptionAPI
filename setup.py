"""
# Autor: ByMyselfJhones
# Função: Configuração de empacotamento da biblioteca PocketOptionAPI
# Descrição:
# - Configura metadados para distribuição do pacote Python
# - Lê descrição longa do README.md
# - Carrega dependências do requirements.txt
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="pocketoptionapi",
    version="0.1.1",
    author="ByMyselfJhones",
    description="API for integration with PocketOption",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ByMyselfJhones/PocketOptionAPI",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=requirements,
) 
