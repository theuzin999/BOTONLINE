import os, json
from time import sleep, time
from datetime import datetime, date
import pytz

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

# Firebase
import firebase_admin
from firebase_admin import credentials, db

# =========================
# 🔧 VARIÁVEIS DE AMBIENTE
# =========================
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")
SERVICE_ACCOUNT_KEY = os.getenv("SERVICE_ACCOUNT_KEY")  # JSON inteiro como texto

# Se quiser mudar depois, coloque como ENV também:
URL_HOME = "https://www.goathbet.com"
URL_AVIATOR = "https://www.goathbet.com/game/spribe-aviator"

# Loop & comportamento “SEGURO”
POLLING_INTERVAL = 1.0          # checagem a cada 1s
INTERVAL_MIN_ENTRE_SAVES = 2.0  # evita flood no Firebase
MAX_INATIVIDADE = 360           # 6 min sem novo valor => reinicia driver
RETRY_DELAY = 5                 # SEGURO: espera 5s antes de reiniciar driver
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =========================
# 🔥 FIREBASE
# =========================
def init_firebase():
    if not SERVICE_ACCOUNT_KEY or not DATABASE_URL:
        raise RuntimeError("Faltam ENV: SERVICE_ACCOUNT_KEY e/ou DATABASE_URL")
    cred = credentials.Certificate(json.loads(SERVICE_ACCOUNT_KEY))
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("✅ Firebase inicializado.")

# =========================
# 🧭 DRIVER (Chromium headless ARM64 no Railway)
# =========================
def _find(path_list):
    for p in path_list:
        if os.path.exists(p):
            return p
    return None

def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--disable-features=BlinkGenPropertyTrees")
    options.add_argument("--window-size=1920,1080")

    # Binário do Chromium (nix/apt no Railway ARM64)
    chrome_bin = _find([
        "/usr/bin/chromium",
        "/nix/store/chromium/bin/chromium",
        "/usr/bin/google-chrome"  # fallback, se existir
    ])
    if chrome_bin:
        options.binary_location = chrome_bin

    # Chromedriver (instalado via nixPkgs no railway.toml)
    chromedriver_path = _find([
        "/usr/bin/chromedriver",
        "/nix/store/chromedriver/bin/chromedriver"
    ])

    if chromedriver_path:
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        # fallback: Selenium Manager tenta resolver (pode falhar no ARM64)
        driver = webdriver.Chrome(options=options)

    return driver

# =========================
# 🎯 UTIL
# =========================
def safe_click(driver, by, sel, t=5):
    try:
        WebDriverWait(driver, t).until(EC.element_to_be_clickable((by, sel))).click()
        return True
    except Exception:
        return False

def safe_find(driver, by, sel, t=5):
    try:
        return WebDriverWait(driver, t).until(EC.presence_of_element_located((by, sel)))
    except Exception:
        return None

def get_color(mult):
    m = float(mult)
    if 1.0 <= m < 2.0:  return "blue-bg"
    if 2.0 <= m < 10.0: return "purple-bg"
    if m >= 10.0:       return "magenta-bg"
    return "default-bg"

# =========================
# 🔑 LOGIN
# =========================
def do_login(driver):
    if not EMAIL or not PASSWORD:
        print("❌ Configure EMAIL e PASSWORD no Railway.")
        return False

    print("➡️ Abrindo página…")
    driver.get(URL_HOME)
    sleep(2)

    # Idade (se houver)
    safe_click(driver, By.CSS_SELECTOR, 'button[data-age-action="yes"]', 3)

    # Abrir modal login
    if not safe_click(driver, By.CSS_SELECTOR, 'a[data-ix="window-login"].btn-small.w-button', 5):
        print("⚠️ Botão de login inicial não encontrado.")
        return False

    # Inputs
    email_input = safe_find(driver, By.ID, "field-15", 5)
    pass_input  = safe_find(driver, By.ID, "password-login", 5)
    if not (email_input and pass_input):
        print("⚠️ Campos de login não encontrados.")
        return False

    email_input.clear(); email_input.send_keys(EMAIL)
    pass_input.clear();  pass_input.send_keys(PASSWORD)
    sleep(0.4)

    # Confirmar
    if not safe_click(driver, By.CSS_SELECTOR, 'a[login-btn].btn-small.btn-color-2.full-width.w-inline-block', 5):
        print("⚠️ Botão final de login não encontrado.")
        return False

    sleep(5)
    # Cookies (se aparecer)
    safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 3)

    # Ir ao Aviator
    if not safe_click(driver, By.CSS_SELECTOR, "img.slot-game", 3):
        driver.get(URL_AVIATOR)
        print("ℹ️ Indo direto para o Aviator…")
    sleep(8)
    return True

# =========================
# 🧩 ENCONTRAR IFRAME & HISTÓRICO
# =========================
IFRAMES_XPATH = [
    '//iframe[contains(@src, "/aviator/")]',
    '//iframe[contains(@src, "spribe")]',
    '//iframe[contains(@src, "aviator-game")]'
]
HISTORY_CANDIDATES = [
    (By.CSS_SELECTOR, '.rounds-history'),
    (By.CSS_SELECTOR, '.history-list'),
    (By.CSS_SELECTOR, '.multipliers-history'),
    (By.CSS_SELECTOR, '.result-history'),
    (By.CSS_SELECTOR, '[data-testid="history"]'),
    (By.CSS_SELECTOR, '.game-history'),
    (By.CSS_SELECTOR, '.bet-history'),
    (By.CSS_SELECTOR, 'div[class*="recent-list"]'),
    (By.CSS_SELECTOR, 'ul.results-list'),
    (By.CSS_SELECTOR, 'div.history-block'),
    (By.CSS_SELECTOR, 'div[class*="history-container"]'),
    (By.XPATH, '//div[contains(@class, "history")]'),
    (By.XPATH, '//div[contains(@class, "rounds-list")]'),
]

def attach_history(driver):
    iframe_el = None
    for xp in IFRAMES_XPATH:
        try:
            driver.switch_to.default_content()
            iframe_el = WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.switch_to.frame(iframe_el)
            print(f"✅ Iframe OK: {xp}")
            break
        except Exception:
            continue
    if not iframe_el:
        print("⚠️ Não achei iframe.")
        return None, None

    hist = None
    for by, sel in HISTORY_CANDIDATES:
        try:
            hist = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, sel)))
            print(f"✅ Histórico OK: {sel}")
            break
        except Exception:
            continue

    if not hist:
        print("⚠️ Não achei histórico dentro do iframe.")
        driver.switch_to.default_content()
        return None, None

    return iframe_el, hist

# =========================
# 🚀 LOOP PRINCIPAL (SEGURO)
# =========================
def start_bot(relogin_done_for: date = None):
    print("\n====================================")
    print("      INICIALIZANDO GOATHBOT")
    print("====================================")

    driver = start_driver()

    def setup():
        if not do_login(driver):
            return None, None
        return attach_history(driver)

    iframe, hist = setup()
    if not hist:
        try: driver.quit()
        except: pass
        print(f"⏳ Retentando em {RETRY_DELAY}s…")
        sleep(RETRY_DELAY)
        return start_bot()

    last_sent = None
    last_sent_ts = 0.0
    last_seen_ts = time()
    relogin_done_for = relogin_done_for or date.today()

    print("✅ Captura iniciada.\n")

    while True:
        try:
            now_br = datetime.now(TZ_BR)

            # Reinício diário (23:59) — evita chrome ficar dias aberto
            if now_br.hour == 23 and now_br.minute >= 59 and relogin_done_for != now_br.date():
                print("🕛 Reinício diário…")
                try: driver.quit()
                except: pass
                sleep(60)
                return start_bot(relogin_done_for=now_br.date())

            # Timeout de inatividade
            if (time() - last_seen_ts) > MAX_INATIVIDADE:
                print("🚨 Inatividade > 6min. Reiniciando…")
                try: driver.quit()
                except: pass
                sleep(RETRY_DELAY)
                return start_bot()

            # Garante contexto do iframe sempre ativo
            try:
                driver.switch_to.frame(iframe)
            except Exception:
                driver.switch_to.default_content()
                iframe, hist = attach_history(driver)
                if not hist:
                    print("⚠️ Perdi iframe/hist. Reiniciando…")
                    try: driver.quit()
                    except: pass
                    sleep(RETRY_DELAY)
                    return start_bot()

            text = hist.text.strip() if hist else ""
            if not text:
                sleep(1)
                continue

            # Extrai multiplicadores
            vals, seen = [], set()
            for s in text.split("\n"):
                s = s.replace("x", "").strip()
                try:
                    if s:
                        v = float(s)
                        if v >= 1.0 and v not in seen:
                            seen.add(v); vals.append(v)
                except ValueError:
                    pass

            if vals:
                novo = vals[0]
                if (novo != last_sent) and ((time() - last_sent_ts) > INTERVAL_MIN_ENTRE_SAVES):
                    now = datetime.now(TZ_BR)
                    raw = f"{novo:.2f}"
                    dstr = now.strftime("%Y-%m-%d")
                    tkey = now.strftime("%H-%M-%S.%f")
                    tdisp = now.strftime("%H:%M:%S")
                    color = get_color(novo)

                    entry_key = f"{dstr}_{tkey}_{raw}x".replace(':', '-').replace('.', '-')
                    data = {"multiplier": raw, "time": tdisp, "color": color, "date": dstr}

                    try:
                        db.reference(f"history/{entry_key}").set(data)
                        print(f"🔥 {raw}x salvo às {tdisp}")
                    except Exception as e:
                        print("⚠️ Erro ao salvar no Firebase:", e)

                    last_sent = novo
                    last_sent_ts = time()
                    last_seen_ts = time()

            driver.switch_to.default_content()
            sleep(POLLING_INTERVAL)

        except (StaleElementReferenceException, TimeoutException):
            print("⚠️ Elemento instável. Tentando reanexar histórico…")
            driver.switch_to.default_content()
            iframe, hist = attach_history(driver)
            if not hist:
                print(f"⏳ Retentando em {RETRY_DELAY}s…")
                try: driver.quit()
                except: pass
                sleep(RETRY_DELAY)
                return start_bot()
            continue

        except Exception as e:
            print(f"❌ Erro inesperado no loop: {e}")
            try: driver.quit()
            except: pass
            print(f"⏳ Reiniciando em {RETRY_DELAY}s…")
            sleep(RETRY_DELAY)
            return start_bot()

# =========================
# ▶️ ENTRYPOINT
# =========================
if __name__ == "__main__":
    try:
        init_firebase()
    except Exception as e:
        print("❌ Firebase não inicializou:", e)
        raise

    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis do Railway.")
    else:
        start_bot(relogin_done_for=date.today())
