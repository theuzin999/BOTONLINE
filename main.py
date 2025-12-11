import time
import requests

# Coloque os links dos seus sites aqui
URLS = [
    "https://seusite1.netlify.app/",
    "https://seusite2.netlify.app/"
]

INTERVALO = 7200  # 2 horas em segundos

def acessar_sites():
    for url in URLS:
        try:
            r = requests.get(url, timeout=15)
            print(f"[OK] {url} - {r.status_code}")
        except Exception as e:
            print(f"[ERRO] {url} - {e}")

if __name__ == "__main__":
    while True:
        acessar_sites()
        time.sleep(INTERVALO)