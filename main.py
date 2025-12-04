import firebase_admin
from firebase_admin import credentials, db
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import json
import os


# ---------- FIREBASE ----------
def conectar_firebase():
    print("Conectando ao Firebase...")

    cred_path = "firebase_key.json"

    if not os.path.exists(cred_path):
        raise Exception("Arquivo firebase_key.json não encontrado!")

    cred = credentials.Certificate(cred_path)

    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://history-dashboard-a70ee-default-rtdb.firebaseio.com/"
    })

    print("Firebase conectado com sucesso!")


# ---------- DRIVER SELENIUM ----------
def start_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service("/usr/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


# ---------- LOOP PRINCIPAL ----------
def monitorar():
    driver = start_driver()
    print("Driver iniciado com sucesso!")

    while True:
        print("Rodando...")
        time.sleep(5)


if __name__ == "__main__":
    conectar_firebase()
    monitorar()
