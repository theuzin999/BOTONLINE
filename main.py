# =============================================================
# GOATHBOT 6.0 - DUAL MODE (RAILWAY EDITION)
# =============================================================
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

from time import sleep, time
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, db
import pytz
import os
import threading
import logging

# =============================================================
# CONFIGURAÇÃO PRINCIPAL
# =============================================================
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
SERVICE_ACCOUNT_FILE = "firebase_key.json"
DATABASE_URL = "https://history-dashboard-a70ee-default-rtdb.firebaseio.com"
BASE_URL = "https://www.goathbet.com"

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

logging.getLogger("WDM").setLevel(logging.ERROR)
TZ_BR = pytz.timezone("America/Sao_Paulo")
POLLING_INTERVAL = 0.15
TEMPO_MAX_INATIVIDADE = 360

# =============================================================
# FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("🔥 Firebase conectado com sucesso!")
except Exception as e:
    print("❌ ERRO FIREBASE:", e)

# =============================================================
# DRIVER
# =============================================================
def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--log-level=3")
    options.page_load_strategy = "eager"

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)

# =============================================================
# LOGIN
# =============================================================
def login(driver, jogo_link):
    driver.get(BASE_URL)
    sleep(2)

    try:
        driver.find_element(By.XPATH, "//button[contains(., 'Entrar')]").click()
        sleep(1)

        driver.find_element(By.NAME, "email").send_keys(EMAIL)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
    except:
        pass

    sleep(3)
    driver.get(jogo_link)

# =============================================================
# ENCONTRAR IFRAME DO JOGO
# =============================================================
def get_game_elements(driver):
    try:
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src,'aviator')]"))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    try:
        hist = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block"))
        )
        return iframe, hist
    except:
        return None, None

# =============================================================
# MONITORADOR DE UM BOT
# =============================================================
def run_bot(config):
    nome = config["nome"]
    link = config["link"]
    fb_path = config["firebase_path"]

    restart_day = date.today()

    while True:
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver()

            login(driver, link)
            iframe, hist = get_game_elements(driver)

            if not hist:
                raise Exception("Iframe não encontrado.")

            print(f"🚀 [{nome}] Monitorando...")

            LAST = None
            last_multiply_time = time()

            while True:
                # REINÍCIO DIÁRIO
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and restart_day != now_br.date():
                    print(f"🌙 [{nome}] Reinício programado.")
                    driver.quit()
                    restart_day = now_br.date()
                    break

                if (time() - last_multiply_time) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Inatividade detectada (sem novos multiplicadores).")

                try:
                    elem = hist.find_element(By.CSS_SELECTOR, ".payout:first-child")
                    txt = elem.text.replace("x", "").strip()

                    if not txt:
                        sleep(POLLING_INTERVAL)
                        continue

                    try:
                        val = float(txt)
                    except:
                        sleep(POLLING_INTERVAL)
                        continue

                    if val != LAST:
                        last_multiply_time = time()

                        entry = {
                            "multiplier": f"{val:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": "default-bg",
                            "date": now_br.strftime("%Y-%m-%d")
                        }

                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f")

                        db.reference(f"{fb_path}/{key}").set(entry)
                        print(f"🔥 [{nome}] {val:.2f}x")

                        LAST = val

                except Exception as e:
                    iframe, hist = get_game_elements(driver)
                    if not hist:
                        raise Exception("Perdeu o iframe do jogo.")
                    continue

                sleep(POLLING_INTERVAL)

        except Exception as e:
            print(f"⚠️ [{nome}] ERRO: {e}. Reiniciando em 5s...")
            try: driver.quit()
            except: pass
            sleep(5)

# =============================================================
# INICIAR THREADS
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❌ Configure EMAIL e PASSWORD no Railway!")
        exit()

    print("\n==============================================")
    print("      GOATHBOT 6.0 - DUAL MODE (RAILWAY)")
    print("==============================================\n")

    threads = []
    for cfg in CONFIG_BOTS:
        t = threading.Thread(target=run_bot, args=(cfg,))
        t.start()
        threads.append(t)
        sleep(2)

    for t in threads:
        t.join()
