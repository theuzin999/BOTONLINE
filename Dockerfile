FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y chromium chromium-driver libnss3 xvfb wget unzip && \
    apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia a chave do Firebase para dentro do container
COPY firebase_key.json firebase_key.json

# Copia o restante do projeto
COPY . .

CMD ["python", "main.py"]
