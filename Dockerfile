# Usa uma imagem Node.js recente (baseada em Debian), que geralmente tem melhor compatibilidade com as dependências do Chrome
FROM node:18-slim

# Instala o Python 3.11 e outras dependências essenciais
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-venv \
    # Dependências do Chromium/Chrome (Corrigidas após erro de 'Unable to locate')
    chromium \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    fonts-liberation \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Configura o ambiente
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_DRIVER_PATH=/usr/bin/chromedriver

# Define o diretório de trabalho
WORKDIR /app

# Define 'python3.11' como o comando padrão para o Python
ENV PATH="/usr/bin:${PATH}"

# Copia os arquivos necessários
COPY requirements.txt .
COPY main.py .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Comando de inicialização do serviço
CMD ["python3.11", "main.py"]