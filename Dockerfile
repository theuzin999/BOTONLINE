FROM python:3.10-slim

# Instala dependências do Chromium e Chromedriver
RUN apt-get update && \
    apt-get install -y \
        chromium \
        chromium-driver \
        libnss3 \
        xvfb \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Variáveis para evitar erro do Selenium/Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

CMD ["python", "main.py"]
