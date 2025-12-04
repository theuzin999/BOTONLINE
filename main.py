import os
import json
import logging
import threading
import pytz
from time import sleep, time
from datetime import datetime, date

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
# 🔧 SETUP RAILWAY (PROCESSO DE SEGURANÇA)
# =============================================================
# O Railway usa variáveis de ambiente. Este bloco cria o arquivo
# serviceAccountKey.json na hora que o bot liga, usando a variável.
SERVICE_ACCOUNT_FILE = 'serviceAccountKey.json'
firebase_creds = os.getenv("FIREBASE_CREDENTIALS")

if firebase_creds:
    print("⚙️ [SETUP] Criando credenciais Firebase via Variável de Ambiente...")
    with open(SERVICE_ACCOUNT_FILE, "w") as f:
        f.write(firebase_creds)
else:
    print(f"⚠️ [SETUP] Variável FIREBASE_CREDENTIALS não encontrada. Tentando arquivo local...")

# =============================================================
# 🔥 GOATHBOT V6.0 - DUAL MODE
# =============================================================
DATABASE_URL = 'https://history-dashboard-a70ee-default-rtdb.firebaseio.com'
URL_DO_SITE = "https://www.goathbet.com"

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

# Configuração de Logs
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
TZ_BR = pytz.timezone("America/Sao_Paulo")

POLLING_INTERVAL = 0.1          
TEMPO_MAX_INATIVIDADE = 360     

# =============================================================
# 🔧 CONEXÃO FIREBASE
# =============================================================
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
    print("✅ Conexão Firebase estabelecida.")
except Exception as e:
    print(f"\n❌ ERRO CRÍTICO NO FIREBASE: {e}")
    # Sem banco de dados, o bot não serve de nada, então encerramos.
    exit(1)

# =============================================================
# 🛠️ NAVEGADOR (OTIMIZADO PARA RAILWAY/LINUX)
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

    # Caminho padrão do Chromium no Docker/Linux (Railway)
    options.binary_location = "/usr/bin/chromium"

    try:
        # Tenta usar o driver nativo instalado pelo Dockerfile
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    except Exception as e:
        print(f"⚠️ Driver nativo falhou, tentando gerenciador automático: {e}")
        # Fallback caso mude o ambiente
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def safe_click(driver, by, value, timeout=5):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except: return False

def check_blocking_modals(driver):
    try:
        xpaths = [
            "//button[contains(., 'Sim')]", 
            "//button[@data-age-action='yes']", 
            "//div[contains(text(), '18')]/following::button[1]",
            "//button[contains(., 'Aceitar')]"
        ]
        for xp in xpaths:
            if safe_click(driver, By.XPATH, xp, 1): break
    except: pass

def process_login(driver, target_link):
    try: driver.get(URL_DO_SITE)
    except: pass
    sleep(2)
    check_blocking_modals(driver)

    # Tenta clicar em entrar
    if safe_click(driver, By.XPATH, "//button[contains(., 'Entrar')]", 5) or \
       safe_click(driver, By.CSS_SELECTOR, 'a[href*="login"]', 5):
        sleep(1)
        try:
            driver.find_element(By.NAME, "email").send_keys(EMAIL)
            driver.find_element(By.NAME, "password").send_keys(PASSWORD)
            if safe_click(driver, By.CSS_SELECTOR, "button[type='submit']", 5):
                sleep(3)
        except: pass
    
    driver.get(target_link)
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
    except: pass
        
    check_blocking_modals(driver)
    return True

def initialize_game_elements(driver):
    try:
        driver.switch_to.default_content()
    except: pass
    
    iframe = None
    try:
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "spribe") or contains(@src, "aviator")]'))
        )
        driver.switch_to.frame(iframe)
    except:
        return None, None

    hist = None
    try:
        hist = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".payouts-block, app-stats-widget"))
        )
    except:
        return None, None

    return iframe, hist

def getColorClass(value):
    try:
        m = float(value)
        if 1.0 <= m < 2.0: return "blue-bg"
        if 2.0 <= m < 10.0: return "purple-bg"
        if m >= 10.0: return "magenta-bg"
        return "default-bg"
    except: return "default-bg"

# =============================================================
# 🤖 LOOP PRINCIPAL (THREAD INDIVIDUAL)
# =============================================================
def run_single_bot(bot_config):
    nome = bot_config["nome"]
    link = bot_config["link"]
    path_fb = bot_config["firebase_path"]
    
    relogin_date = date.today()

    while True: 
        driver = None
        try:
            print(f"🔄 [{nome}] Iniciando driver...")
            driver = start_driver()
            process_login(driver, link)

            iframe, hist = initialize_game_elements(driver)
            if not hist: raise Exception("Elementos do jogo não carregaram")

            print(f"🚀 [{nome}] MONITORANDO EM '{path_fb}'")
            
            LAST_SENT = None
            ULTIMO_MULTIPLIER_TIME = time()
            
            while True:
                # Reinício diário (evita vazamento de memória do Chrome)
                now_br = datetime.now(TZ_BR)
                if now_br.hour == 0 and now_br.minute <= 5 and (relogin_date != now_br.date()):
                    print(f"🌙 [{nome}] Reinício diário programado...")
                    driver.quit()
                    relogin_date = now_br.date()
                    break 

                # Check Inatividade
                if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                    raise Exception("Sem novos resultados há 6 minutos")

                try:
                    first_payout = hist.find_element(By.CSS_SELECTOR, ".payout:first-child, .bubble-multiplier:first-child")
                    raw_text = first_payout.get_attribute("innerText")
                    clean_text = raw_text.strip().lower().replace('x', '')

                    if not clean_text:
                        sleep(POLLING_INTERVAL)
                        continue 

                    try:
                        novo = float(clean_text)
                    except ValueError:
                        sleep(POLLING_INTERVAL)
                        continue 
                    
                    if novo != LAST_SENT:
                        ULTIMO_MULTIPLIER_TIME = time()
                        now_br = datetime.now(TZ_BR)
                        
                        entry = {
                            "multiplier": f"{novo:.2f}",
                            "time": now_br.strftime("%H:%M:%S"),
                            "color": getColorClass(novo),
                            "date": now_br.strftime("%Y-%m-%d")
                        }
                        # Chave única baseada no tempo
                        key = now_br.strftime("%Y-%m-%d_%H-%M-%S-%f").replace('.', '-')
                        
                        try:
                            db.reference(f"{path_fb}/{key}").set(entry)
                            print(f"🔥 [{nome}] {entry['multiplier']}x")
                            LAST_SENT = novo
                        except Exception as e:
                            print(f"⚠️ [{nome}] Erro ao enviar para Firebase: {e}")

                    sleep(POLLING_INTERVAL)

                except (StaleElementReferenceException, TimeoutException) as e:
                    # Erro leve, tenta reconectar elementos
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    if not hist: raise Exception("Falha ao recuperar elementos")
                    sleep(POLLING_INTERVAL)
                    continue 

        except Exception as e:
            print(f"❌ [{nome}] Erro/Restart: {e}")
            if driver:
                try: driver.quit()
                except: pass
            sleep(10) # Espera 10s antes de tentar voltar

# =============================================================
# 🚀 INICIALIZAÇÃO
# =============================================================
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("❗ ERRO: Configure as variáveis EMAIL e PASSWORD no painel do Railway!")
    
    print("=== INICIANDO SISTEMA ===")
    
    threads = []
    for config in CONFIG_BOTS:
        t = threading.Thread(target=run_single_bot, args=(config,))
        t.start()
        threads.append(t)
        sleep(5) 

    for t in threads:
        t.join()
