FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# atualiza pacotes e instala dependências + xvfb + chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    libx11-6 \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    fonts-liberation \
    xdg-utils \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_DRIVER_PATH=/usr/bin/chromedriver

# aqui está o segredo -> força o container rodar num DISPLAY virtual
ENV DISPLAY=:99

# inicia XVFB e depois inicia o bot
CMD bash -c "Xvfb :99 -screen 0 1920x1080x24 & python main.py"
