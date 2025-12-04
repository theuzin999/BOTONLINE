FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY firebase_key.json firebase_key.json
COPY . .

CMD ["python3", "main.py"]
