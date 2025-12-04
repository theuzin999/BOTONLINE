import os
import json
import logging
import threading
import pytz
from time import sleep, time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

import firebase_admin
from firebase_admin import credentials, db

# =============================================================
# FIREBASE VIA ARQUIVO LOCAL
# =============================================================
SERVICE_ACCOUNT_FILE = "firebase_key.json"
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'

CONFIG_BOTS = [
    {
        "nome": "ORIGINAL",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase_path": "history"
    },
    {
        "nome": "AVIATOR 2",
        "link": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase_path": "aviator2"
    }
]

logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

TZ_BR = pytz.timezone("America/Sao_Paulo")
POLLING_INTERVAL = 0.1
TEMPO_MAX_INATIVIDADE = 360

# =============================================================
# INICIALIZAR FIREBASE
# =============================================================
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Firebase conectado com sucesso!")
except Exception as e:
    print("\n❌ ERRO CRÍTICO NO FIREBASE:", e)
    exit(1)

# =============================================================
# DRIVER SELENIUM
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.binary_location = "/usr/bin/chromium"

    try:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# =============================================================
# FUNÇÃO PRINCIPAL DO BOT
# =============================================================
def monitor_bot(config):
    nome = config["nome"]
    link = config["link"]
    firebase_path = config["firebase_path"]

    while True:
        try:
            print(f"[{nome}] Iniciando driver...")
            driver = start_driver()
            driver.get(link)
            sleep(5)

            print(f"[{nome}] Monitorando...")

            ref = db.reference(firebase_path)

            ultimo_envio = time()

            while True:
                try:
                    elements = driver.find_elements(By.CLASS_NAME, "crash-point")
                    if not elements:
                        continue

                    ultimo = elements[-1].text.strip()

                    if ultimo.replace(".", "", 1).isdigit():
                        valor = float(ultimo)
                        horario = datetime.now(TZ_BR).strftime("%H:%M:%S")

                        ref.push({
                            "valor": valor,
                            "hora": horario
                        })

                        print(f"[{nome}] Enviado → {valor} às {horario}")

                        ultimo_envio = time()

                    sleep(POLLING_INTERVAL)

                    if time() - ultimo_envio > TEMPO_MAX_INATIVIDADE:
                        raise Exception("Inatividade detectada.")

                except StaleElementReferenceException:
                    continue
                except TimeoutException:
                    continue

        except Exception as e:
            print(f"[{nome}] ERRO → {e}")
            sleep(3)
            continue
        finally:
            try:
                driver.quit()
            except:
                pass

# =============================================================
# THREADS DOS BOTS
# =============================================================
def iniciar_bots():
    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=monitor_bot, args=(config,))
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

# =============================================================
# INÍCIO
# =============================================================
print("\nGOATHBOT V6.0 — BOTONLINE EDITION")
print("Iniciando bots...\n")

iniciar_bots()
