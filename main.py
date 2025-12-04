import os
import time
import pytz
import traceback
import firebase_admin
from datetime import datetime
from firebase_admin import credentials, db

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# =======================================================
# CFG
# =======================================================

URLS = {
    "ORIGINAL": {
        "url": "https://www.goathbet.com/pt/casino/spribe/aviator",
        "firebase": "history"
    },
    "AVIATOR2": {
        "url": "https://www.goathbet.com/pt/casino/spribe/aviator-2",
        "firebase": "aviator2"
    }
}

TZ = pytz.timezone("America/Sao_Paulo")

# =======================================================
# FIREBASE
# =======================================================

try:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
    })
    print("🔥 Firebase conectado com sucesso!")
except Exception as e:
    print("❌ ERRO FIREBASE:", e)
    traceback.print_exc()
    exit()


# =======================================================
# DRIVER FIXADO PARA O RAILWAY (SEM webdriver_manager)
# =======================================================

def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    try:
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print("❌ ERRO AO INICIAR CHROMEDRIVER:", e)
        traceback.print_exc()
        raise


# =======================================================
# LOGIN
# =======================================================

def fazer_login(driver):
    try:
        print("➡ Tentando login...")

        email = os.getenv("EMAIL", "")
        senha = os.getenv("PASSWORD", "")

        if not email or not senha:
            print("⚠ EMAIL/PASSWORD ausentes — prosseguindo sem login.")
            return

        time.sleep(4)

        inputs = driver.find_elements(By.TAG_NAME, "input")
        if len(inputs) >= 2:
            inputs[0].send_keys(email)
            inputs[1].send_keys(senha)

            botoes = driver.find_elements(By.TAG_NAME, "button")
            botoes[-1].click()

        print("✔ Login enviado.")
    except Exception as e:
        print("⚠ Erro no login:", e)


# =======================================================
# CAPTURA DE SINAL
# =======================================================

def capturar_sinal(driver):
    try:
        elementos = driver.find_elements(By.CLASS_NAME, "crash-point")
        if not elementos:
            return None

        texto = elementos[-1].text.strip()
        if not texto:
            return None

        texto = texto.replace("x", "")

        try:
            return float(texto)
        except:
            return None

    except:
        return None


# =======================================================
# MONITOR
# =======================================================

def monitorar(nome, cfg):
    url = cfg["url"]
    firebase_path = cfg["firebase"]

    while True:
        try:
            print(f"\n[{nome}] Iniciando driver...")
            driver = start_driver()

            driver.get(url)
            time.sleep(5)

            fazer_login(driver)

            ref = db.reference(firebase_path)
            ultimo_valor = None

            print(f"[{nome}] Monitorando...\n")

            while True:
                valor = capturar_sinal(driver)

                if valor is not None and valor != ultimo_valor:
                    ultimo_valor = valor
                    hora = datetime.now(TZ).strftime("%H:%M:%S")

                    ref.push({"valor": valor, "hora": hora})
                    print(f"[{nome}] → {valor}x às {hora}")

                time.sleep(0.15)

        except Exception as e:
            print(f"\n[{nome}] ERRO:", e)
            traceback.print_exc()
            time.sleep(3)

        finally:
            try:
                driver.quit()
            except:
                pass


# =======================================================
# THREADS
# =======================================================

import threading

for nome, cfg in URLS.items():
    t = threading.Thread(target=monitorar, args=(nome, cfg))
    t.daemon = True
    t.start()

print("\n🔥 BOT ONLINE — Railway")
print("Monitorando ambos aviadores...\n")

while True:
    time.sleep(10)
