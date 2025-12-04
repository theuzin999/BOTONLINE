# Usa Python 3.11 Slim (Versão leve e compatível com Selenium)
FROM python:3.11-slim

# Evita arquivos temporários e logs travados
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala o Chromium, Driver e dependências necessárias
# Removemos bibliotecas obsoletas que causavam o erro no seu print
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgconf-2-4 \
    xvfb \
    wget \
    unzip \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Define pasta de trabalho
WORKDIR /app

# Copia e instala as bibliotecas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do bot
COPY . .

# Comando para iniciar
CMD ["python", "main.py"]
