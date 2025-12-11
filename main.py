import asyncio
from playwright.async_api import async_playwright
import time

URLS = [
    "https://botapostamax.netlify.app/",
    "https://botapostaganha.netlify.app/"
]

INTERVALO = 7200  # 2 horas em segundos

async def manter_aberto(playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()

    pages = []

    # abre cada site e deixa aberto
    for url in URLS:
        page = await context.new_page()
        await page.goto(url)
        print(f"[ABERTO] {url}")
        pages.append(page)

    # loop infinito: recarrega a cada 2h
    while True:
        await asyncio.sleep(INTERVALO)
        for page, url in zip(pages, URLS):
            await page.reload()
            print(f"[RECARREGADO] {url} - {time.ctime()}")

async def main():
    async with async_playwright() as playwright:
        await manter_aberto(playwright)

asyncio.run(main())
