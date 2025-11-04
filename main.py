import os, json
from time import sleep, time
from datetime import datetime, date

import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

import firebase_admin
from firebase_admin import credentials, db

# =========================
# 🔧 VARS DE AMBIENTE
# =========================
# Firebase
DATABASE_URL = os.getenv("DATABASE_URL")  # coloque isso no Railway
SERVICE_ACCOUNT_KEY = os.getenv("SERVICE_ACCOUNT_KEY")  # JSON inteiro como texto

# Login do site
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

# URLs (podem ficar hardcoded; se quiser, mova p/ ENV também)
URL_DO_SITE   = "https://www.goathbet.com"
LINK_AVIATOR  = "https://www.goathbet.com/game/spribe-aviator"

# Loop & horários
POLLING_INTERVAL = 1.0        # checagem a cada 1s
INTERVALO_MINIMO_ENVIO = 2.0  # pelo menos 2s entre dois saves
TEMPO_MAX_INATIVIDADE = 360   # 6 min sem novo multiplicador => reinicia
TZ_BR = pytz.timezone("America/Sao_Paulo")

# =========================
# 🔥 FIREBASE
# =========================
def init_firebase():
    if not SERVICE_ACCOUNT_KEY:
        print("❌ SERVICE_ACCOUNT_KEY não definida no Railway.")
        raise RuntimeError("SERVICE_ACCOUNT_KEY missing")

    if not DATABASE_URL:
        print("❌ DATABASE_URL não definida no Railway.")
        raise RuntimeError("DATABASE_URL missing")

    try:
        cred = credentials.Certificate(json.loads(SERVICE_ACCOUNT_KEY))
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
        print("✅ Firebase Admin SDK inicializado com sucesso. O bot salvará dados.")
    except Exception as e:
        print("❌ ERRO DE CONEXÃO FIREBASE:", e)
        raise

# =========================
# 🎨 UTIL
# =========================
def getColorClass(value):
    m = float(value)
    if 1.0 <= m < 2.0:   return "blue-bg"
    if 2.0 <= m < 10.0:  return "purple-bg"
    if m >= 10.0:        return "magenta-bg"
    return "default-bg"

def safe_click(driver, by, value, timeout=5):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        el.click()
        return True
    except Exception:
        return False

def safe_find(driver, by, value, timeout=5):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except Exception:
        return None

# =========================
# 🧭 DRIVER (Chromium headless no Railway)
# =========================
def resolve_chromedriver_path():
    # 1) caminho padrão em distros (apt)
    candidates = ["/usr/bin/chromedriver",
                  "/nix/store/chromedriver/bin/chromedriver"]
    for c in candidates:
        if os.path.exists(c):
            return c
    # fallback: deixa o Selenium Manager tentar (pode baixar em runtime)
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
    # binário do Chromium (Railway com nixPkgs costuma expor em /usr/bin/chromium)
    for chrome_bin in ("/usr/bin/chromium", "/usr/bin/google-chrome", "/nix/store/chromium/bin/chromium"):
        if os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
            break

    service_path = resolve_chromedriver_path()
    if service_path:
        service = Service(service_path)
        return webdriver.Chrome(service=service, options=options)
    else:
        # fallback: deixa Selenium resolver (requer internet na primeira vez)
        return webdriver.Chrome(options=options)

# =========================
# 🧩 INICIALIZA ELEMENTOS DO JOGO
# =========================
def initialize_game_elements(driver):
    POSSIVEIS_IFRAMES = [
        '//iframe[contains(@src, "/aviator/")]',
        '//iframe[contains(@src, "spribe")]',
        '//iframe[contains(@src, "aviator-game")]'
    ]
    POSSIVEIS_HISTORICOS = [
        ('.rounds-history', By.CSS_SELECTOR),
        ('.history-list', By.CSS_SELECTOR),
        ('.multipliers-history', By.CSS_SELECTOR),
        ('.result-history', By.CSS_SELECTOR),
        ('[data-testid="history"]', By.CSS_SELECTOR),
        ('.game-history', By.CSS_SELECTOR),
        ('.bet-history', By.CSS_SELECTOR),
        ('div[class*="recent-list"]', By.CSS_SELECTOR),
        ('ul.results-list', By.CSS_SELECTOR),
        ('div.history-block', By.CSS_SELECTOR),
        ('div[class*="history-container"]', By.CSS_SELECTOR),
        ('//div[contains(@class, "history")]', By.XPATH),
        ('//div[contains(@class, "rounds-list")]', By.XPATH)
    ]

    iframe = None
    for xp in POSSIVEIS_IFRAMES:
        try:
            driver.switch_to.default_content()
            iframe = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.switch_to.frame(iframe)
            print(f"✅ Iframe encontrado com XPath: {xp}")
            break
        except Exception:
            continue

    if not iframe:
        print("⚠️ Nenhum iframe encontrado. Verifique se o jogo está carregado.")
        return None, None

    historico_elemento = None
    for selector, by_method in POSSIVEIS_HISTORICOS:
        try:
            historico_elemento = WebDriverWait(driver, 7).until(
                EC.presence_of_element_located((by_method, selector))
            )
            print(f"✅ Seletor de histórico encontrado: {selector} ({by_method})")
            break
        except Exception:
            continue

    if not historico_elemento:
        print("⚠️ Nenhum seletor de histórico encontrado!")
        driver.switch_to.default_content()
        return None, None

    return iframe, historico_elemento

# =========================
# 🔑 LOGIN
# =========================
def process_login(driver):
    if not EMAIL or not PASSWORD:
        print("❌ ERRO: EMAIL ou PASSWORD não configurados.")
        return False

    print("➡️ Executando login automático...")
    driver.get(URL_DO_SITE)
    sleep(2)

    # 1) maior de 18 (se existir)
    safe_click(driver, By.CSS_SELECTOR, 'button[data-age-action="yes"]', 5)

    # 2) abre modal de login
    if not safe_click(driver, By.CSS_SELECTOR, 'a[data-ix="window-login"].btn-small.w-button', 5):
        print("❌ Botão 'Login' inicial não encontrado.")
        return False
    sleep(1)

    # 3) credenciais
    email_input = safe_find(driver, By.ID, "field-15", 5)
    pass_input  = safe_find(driver, By.ID, "password-login", 5)
    if not (email_input and pass_input):
        print("⚠️ Campos de login não encontrados!")
        return False

    email_input.clear(); email_input.send_keys(EMAIL)
    pass_input.clear();  pass_input.send_keys(PASSWORD)
    sleep(0.5)

    # 4) confirmar login
    if not safe_click(driver, By.CSS_SELECTOR, "a[login-btn].btn-small.btn-color-2.full-width.w-inline-block", 5):
        print("❌ Botão final de login não encontrado.")
        return False
    sleep(5)

    # 5) cookies (se houver)
    safe_click(driver, By.XPATH, "//button[contains(., 'Aceitar')]", 4)

    # 6) abrir Aviator
    if not safe_click(driver, By.CSS_SELECTOR, "img.slot-game", 4):
        driver.get(LINK_AVIATOR)
        print("ℹ️ Indo direto para o Aviator via link.")
    sleep(10)
    return True

# =========================
# 🚀 LOOP PRINCIPAL + AUTO-RESTART
# =========================
def start_bot(relogin_done_for: date = None):
    print("\n==============================================")
    print("         INICIALIZANDO GOATHBOT")
    print("==============================================")

    driver = start_driver()

    def setup_game():
        if not process_login(driver):
            return None, None
        iframe, hist = initialize_game_elements(driver)
        if not hist:
            print("❌ Não conseguiu iniciar o jogo. Tentando novamente...")
            return None, None
        return iframe, hist

    iframe, hist = setup_game()
    if not hist:
        driver.quit()
        return start_bot()  # recomeça do zero

    LAST_SENT = None
    ULTIMO_ENVIO = time()
    ULTIMO_MULTIPLIER_TIME = time()
    falhas = 0
    relogin_done_for = relogin_done_for or date.today()

    print("✅ Captura iniciada.\n")

    while True:
        try:
            now_br = datetime.now(TZ_BR)

            # Reinício diário perto de 23:59 (evita ficar dias aberto)
            if now_br.hour == 23 and now_br.minute >= 59 and (relogin_done_for != now_br.date()):
                print(f"🕛 Reinício diário {now_br.strftime('%H:%M:%S')} → aguardando 1 min e reiniciando.")
                driver.quit()
                sleep(60)
                return start_bot(relogin_done_for=now_br.date())

            # Timeout de inatividade (6 min sem novo valor)
            if (time() - ULTIMO_MULTIPLIER_TIME) > TEMPO_MAX_INATIVIDADE:
                print("🚨 Inatividade > 6min. Reiniciando bot…")
                driver.quit()
                return start_bot()

            # Garantir contexto no iframe
            try:
                driver.switch_to.frame(iframe)
            except Exception:
                driver.switch_to.default_content()
                iframe, hist = initialize_game_elements(driver)
                if not hist:
                    print("⚠️ Iframe/Histórico perdido. Reiniciando…")
                    driver.quit()
                    return start_bot()

            # Leitura do histórico/velas
            resultados_texto = hist.text.strip() if hist else ""
            if not resultados_texto:
                falhas += 1
                if falhas > 5:
                    print("⚠️ 5 falhas seguidas. Re-localizando elementos…")
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
                            seen.add(v); resultados.append(v)
                except ValueError:
                    pass

            # Envio p/ Firebase
            if resultados:
                novo = resultados[0]
                if (novo != LAST_SENT) and ((time() - ULTIMO_ENVIO) > INTERVALO_MINIMO_ENVIO):
                    now   = datetime.now().astimezone(TZ_BR)
                    raw   = f"{novo:.2f}"
                    dstr  = now.strftime("%Y-%m-%d")
                    tkey  = now.strftime("%H-%M-%S.%f")
                    tdisp = now.strftime("%H:%M:%S")
                    color = getColorClass(novo)

                    entry_key = f"{dstr}_{tkey}_{raw}x".replace(':', '-').replace('.', '-')
                    entry = {"multiplier": raw, "time": tdisp, "color": color, "date": dstr}

                    try:
                        db.reference(f"history/{entry_key}").set(entry)
                        print(f"🔥 {raw}x salvo às {tdisp}")
                    except Exception as e:
                        print("⚠️ Erro ao salvar no Firebase:", e)

                    LAST_SENT = novo
                    ULTIMO_ENVIO = time()
                    ULTIMO_MULTIPLIER_TIME = time()

            driver.switch_to.default_content()
            sleep(POLLING_INTERVAL)

        except (StaleElementReferenceException, TimeoutException):
            print("⚠️ Elemento obsoleto/sumiu. Recarregando elementos…")
            driver.switch_to.default_content()
            iframe, hist = initialize_game_elements(driver)
            continue
        except Exception as e:
            # Qualquer crash inesperado → fecha e reinicia tudo
            print(f"❌ Erro inesperado no loop: {e}")
            try:
                driver.quit()
            except Exception:
                pass
            sleep(3)
            return start_bot()  # auto-restart

# =========================
# ▶️ ENTRYPOINT
# =========================
if __name__ == "__main__":
    init_firebase()
    if not EMAIL or not PASSWORD:
        print("❗ Configure EMAIL e PASSWORD nas variáveis do Railway.")
    else:
        start_bot(relogin_done_for=date.today())
