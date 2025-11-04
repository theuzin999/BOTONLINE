# main.py
# Bot adaptado para rodar em container com Xvfb + webdriver_manager
# - Usa serviceAccountKey.json na raiz para Firebase
# - Lê EMAIL, PASSWORD, DATABASE_URL por env
# - Usa webdriver_manager para baixar/chromedriver correto
# - Não usa --headless (XVFB fornece display virtual)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep, time
from datetime import datetime, date
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import firebase_admin
from firebase_admin import credentials, db
import os
import pytz
import sys
import json

# -----------------------
# FIREBASE (arquivo na raiz)
# -----------------------
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
DATABASE_URL = os.getenv("DATABASE_URL")

try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("✅ Firebase Admin SDK inicializado com sucesso usando ARQUIVO.")
except FileNotFoundError:
    print("\n❌ ERRO CRÍTICO: 'serviceAccountKey.json' não encontrado na raiz do projeto.")
    # não interrompe completamente — só avisa
except Exception as e:
    print(f"\n❌ ERRO DE CONEXÃO FIREBASE: {e}")

# -----------------------
# CONFIG
# -----------------------
URL_DO_SITE = "https://www.goathbet.com"
LINK_AVIATOR = "https://www.goathbet.com/game/spribe-aviator"

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

POLLING_INTERVAL = 1.0
INTERVALO_MINIMO_ENVIO = 2.0
TEMPO_MAX_INATIVIDADE = 360
TZ_BR = pytz.timezone("America/Sao_Paulo")

# -----------------------
# HELPERS
# -----------------------
def getColorClass(value: float):
    m = float(value)
    if 1.0 <= m < 2.0: return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0: return "magenta-bg"
    return "default-bg"

def safe_click(driver, by, value, timeout=6):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        el.click()
        return True
    except Exception:
        return False

def safe_find(driver, by, value, timeout=8):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception:
        return None

# -----------------------
# DEBUG / PROVA DE VIDA
# -----------------------
def debug_assert_logged(driver):
    try:
        print("ℹ️ URL atual:", driver.current_url)
    except Exception as e:
        print("ℹ️ Erro lendo URL:", e)
    try:
        cookies = driver.get_cookies()
        print(f"ℹ️ Cookies de sessão: {len(cookies)} -> {[c.get('name') for c in cookies[:8]]}")
    except Exception as e:
        print("ℹ️ Erro lendo cookies:", e)

    # tenta ler saldo (se existir)
    saldo_selectors = [
        ('span[data-testid="balance"]', By.CSS_SELECTOR),
        ('.balance', By.CSS_SELECTOR),
        ('.header-balance', By.CSS_SELECTOR),
        ('//span[contains(@class,"balance") or contains(@data-testid,"balance")]', By.XPATH),
    ]
    for sel, how in saldo_selectors:
        try:
            el = WebDriverWait(driver, 4).until(EC.presence_of_element_located((how, sel)))
            txt = (el.text or "").strip()
            if txt:
                print(f"✅ Saldo detectado: {txt} (selector: {sel})")
                return
        except Exception:
            continue
    print("⚠️ Saldo não detectado (pode ser normal no build inicial).")

# -----------------------
# START DRIVER (webdriver_manager + XVFB-ready)
# -----------------------
def start_driver():
    options = webdriver.ChromeOptions()

    # NÃO setar headless (XVFB fornece display virtual)
    # Mas adicionamos flags úteis:
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--enable-webgl")
    options.add_argument("--use-gl=swiftshader")

    # Force binary location if set in env (defaults used in Dockerfile)
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    options.binary_location = chrome_bin

    # Use webdriver_manager to get matching chromedriver
    driver_path = ChromeDriverManager().install()
    service = Service(driver_path)

    driver = webdriver.Chrome(service=service, options=options)
    return driver

# -----------------------
# INIT GAME ELEMENTS (robusto)
# -----------------------
def initialize_game_elements(driver):
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(@src, "aviator-game")]'
    ]
    POSSIVEIS_HISTORICOS = [
        ('.result-history', By.CSS_SELECTOR),
        ('.rounds-history', By.CSS_SELECTOR),
        ('div[data-test="history-list"]', By.CSS_SELECTOR),
        ('.history-list', By.CSS_SELECTOR),
        ('.multipliers-history', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR),
        ('.recent-list', By.CSS_SELECTOR),
        ('div[class*="recent"]', By.CSS_SELECTOR),
        ('ul.results-list', By.CSS_SELECTOR),
        ('div.history-block', By.CSS_SELECTOR),
        ('div[class*="history-container"]', By.CSS_SELECTOR),
        ('//div[contains(@class,"history")]', By.XPATH),
        ('//div[contains(@class,"rounds")]', By.XPATH),
        ('//ul[contains(@class,"result")]', By.XPATH),
    ]

    iframe = None
    for xpath in POSSIVEIS_IFRAMES:
        try:
            driver.switch_to.default_content()
            iframe = WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.switch_to.frame(iframe)
            sleep(4)
            print(f"✅ Iframe encontrado com XPath: {xpath}")
            driver.switch_to.default_content()
            break
        except Exception:
            continue

    if not iframe:
        sleep(4)
        for xpath in POSSIVEIS_IFRAMES:
            try:
                driver.switch_to.default_content()
                iframe = WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.XPATH, xpath)))
                driver.switch_to.frame(iframe)
                sleep(4)
                print(f"✅ Iframe encontrado na 2ª tentativa: {xpath}")
                driver.switch_to.default_content()
                break
            except Exception:
                continue

    # tenta histórico primeiro FORA do iframe (muitos hosts rendereizam assim)
    driver.switch_to.default_content()
    historico_elemento = None
    for sel, how in POSSIVEIS_HISTORICOS:
        try:
            historico_elemento = WebDriverWait(driver, 10).until(EC.presence_of_element_located((how, sel)))
            print(f"✅ Histórico (fora iframe): {sel}")
            break
        except Exception:
            continue

    # se não, tenta dentro do iframe
    if not historico_elemento and iframe is not None:
        try:
            driver.switch_to.frame(iframe)
            for sel, how in POSSIVEIS_HISTORICOS:
                try:
                    historico_elemento = WebDriverWait(driver, 10).until(EC.presence_of_element_located((how, sel)))
                    print(f"✅ Histórico (iframe): {sel}")
                    break
                except Exception:
                    continue
        except Exception:
            pass

    if not historico_elemento:
        print("⚠️ Nenhum seletor de histórico encontrado!")
        driver.switch_to.default_content()
        return None, None

    return iframe, historico_elemento

# -----------------------
# LOGIN / ABRE AVIATOR
# -----------------------
def process_login(driver):
    if not EMAIL or not PASSWORD:
        print("❌ ERRO: configure EMAIL e PASSWORD nas variáveis de ambiente.")
        return False

    print("➡️ Executando login automático...")
    driver.get(URL_DO_SITE)
    sleep(2)

    safe_click(driver, By.CSS_SELECTOR, 'button[data-age-action="yes"]', 3)
    if not safe_click(driver, By.CSS_SELECTOR, 'a[data-ix="window-login"].btn-small.w-button', 8):
        print("❌ Botão 'Login' inicial não encontrado.")
        return False
    sleep(0.4)

    email_input = safe_find(driver, By.ID, "field-15", 8)
    pass_input  = safe_find(driver, By.ID, "password-login", 8)
    if not (email_input and pass_input):
        print("⚠️ Campos de login não encontrados!")
        return False

    email_input.clear(); email_input.send_keys(EMAIL)
    pass_input.clear();  pass_input.send_keys(PASSWORD)
    sleep(0.4)

    if not safe_click(driver, By.CSS_SELECTOR, "a[login-btn].btn-small.btn-color-2.full-width.w-inline-block", 8):
        print("❌ Botão final de login não encontrado.")
        return False

    print("✅ Credenciais preenchidas e login confirmado.")
    sleep(5)
    safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 3)
    print("✅ Cookies aceitos (se aplicável).")

    # tenta abrir o aviator via imagem, se não, vai direto pro link
    if safe_click(driver, By.CSS_SELECTOR, "img.slot-game", 4):
        print("✅ Aviator aberto via imagem.")
    else:
        driver.get(LINK_AVIATOR)
        print("ℹ️ Indo direto via link.")
    sleep(12)

    # debug proof-of-life
    debug_assert_logged(driver)
    return True

# -----------------------
# LOOP PRINCIPAL
# -----------------------
def start_bot(relogin_done_for: date = None):
    print("\n==============================================")
    print("         INICIALIZANDO GOATHBOT")
    print("==============================================")

    try:
        driver = start_driver()
    except Exception as e:
        print("❌ ERRO AO INICIAR DRIVER:", e)
        return

    def setup_game(drv):
        if not process_login(drv):
            return None, None
        iframe, hist = initialize_game_elements(drv)
        if not hist:
            print("❌ Não conseguiu iniciar o jogo. Tentando novamente...")
            return None, None
        return iframe, hist

    iframe, hist = setup_game(driver)
    if not hist:
        driver.quit()
        return start_bot()

    LAST_SENT = None
    ULTIMO_ENVIO = time()
    ULTIMO_MULTIPLIER_TIME = time()
    falhas = 0
    relogin_done_for = relogin_done_for if relogin_done_for else date.today()

    print("✅ Captura iniciada.\n")

    while True:
        try:
            now_br = datetime.now(TZ_BR)

            if now_br.hour == 23 and now_br.minute >= 59 and (relogin_done_for != now_br.date()):
                print(f"🕛 REINÍCIO PROGRAMADO: {now_br.strftime('%H:%M:%S')}.")
                driver.quit()
                sleep(60)
                return start_bot(relogin_done_for=now_br.date())

            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print("🚨 Inatividade > 6min. Reiniciando o bot…")
                driver.quit()
                return start_bot()

            # tenta garantir que estamos no contexto correto
            try:
                if iframe:
                    driver.switch_to.frame(iframe)
                else:
                    driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
                iframe, hist = initialize_game_elements(driver)
                if not hist:
                    print("⚠️ Iframe/Histórico perdido. Reiniciando…")
                    driver.quit()
                    return start_bot()

            resultados_texto = hist.text.strip() if hist else ""
            if not resultados_texto:
                falhas += 1
                if falhas > 5:
                    print("⚠️ 5+ falhas de leitura. Re-inicializando elementos…")
                    driver.switch_to.default_content()
                    iframe, hist = initialize_game_elements(driver)
                    falhas = 0
                sleep(1)
                continue

            falhas = 0
            resultados = []
            seen = set()
            for n in resultados_texto.split("\n"):
                n = n.replace("x", "").strip()
                try:
                    if n:
                        v = float(n)
                        if v >= 1.0 and v not in seen:
                            seen.add(v)
                            resultados.append(v)
                except ValueError:
                    pass

            if resultados:
                novo = resultados[0]
                if (novo != LAST_SENT) and ((time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO):
                    now = datetime.now().astimezone(TZ_BR)
                    raw = f"{novo:.2f}"
                    date_str = now.strftime("%Y-%m-%d")
                    time_key = now.strftime("%H-%M-%S.%f")
                    time_display = now.strftime("%H:%M:%S")
                    color = getColorClass(novo)

                    entry_key = f"{date_str}_{time_key}_{raw}x".replace(":", "-").replace(".", "-")
                    entry = {"multiplier": raw, "time": time_display, "color": color, "date": date_str}

                    try:
                        db.reference(f"history/{entry_key}").set(entry)
                        print(f"🔥 {raw}x salvo às {time_display}")
                    except Exception as e:
                        print("⚠️ Erro ao salvar:", e)

                    LAST_SENT = novo
                    ULTIMO_ENVIO = time()
                    ULTIMO_MULTIPLIER_TIME = time()

            driver.switch_to.default_content()
            sleep(POLLING_INTERVAL)

        except (StaleElementReferenceException, TimeoutException):
            print("⚠️ Histórico obsoleto/sumiu. Recarregando elementos…")
            driver.switch_to.default_content()
            iframe, hist = initialize_game_elements(driver)
            continue
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            sleep(3)
            continue

# ENTRY
if __name__ == "__main__":
    if not EMAIL or not PASSWORD:
        print("\n❗ Configure EMAIL e PASSWORD nas variáveis de ambiente.")
        sys.exit(1)
    start_bot(relogin_done_for=date.today())
