import os
import re
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright
import requests

TOPIC = "stan-wody-wisla"

STATE_FILE = "last_state.txt"
DAILY_FILE = "last_daily.txt"

def pobierz_plik(nazwa):
    if os.path.exists(nazwa):
        with open(nazwa, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def zapisz_plik(nazwa, tresc):
    with open(nazwa, "w", encoding="utf-8") as f:
        f.write(str(tresc))

def sprawdz_stan_wody():
    url = "https://hydro.imgw.pl/#/station/hydro/153180090?h=25"
    
    aktualny_stan = None
    data_pomiaru = "Brak danych"
    przeplyw = "Brak danych"
    temperatura = "Brak danych"
    
    print("Otwieram wirtualną przeglądarkę i ładuję mapę IMGW...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        ukryte_dane = {}
        
        def handle_response(response):
            if "153180090" in response.url and response.status == 200:
                try:
                    dane_json = response.json()
                    ukryte_dane["dane"] = dane_json
                except:
                    pass
                    
        page.on("response", handle_response)
        
        # Wchodzimy na stronę i czekamy aż wszystko się załaduje
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(5000)
        
        # Pobieramy cały tekst ze strony, żeby wyciągnąć wartości
        tekst = page.inner_text("body")
        
        # 1. Szukanie stanu wody
        m_stan = re.search(r'Stan wody\s*(\d+)\s*cm', tekst, re.IGNORECASE)
        if not m_stan:
            m_stan = re.search(r'(\d+)\s*cm', tekst, re.IGNORECASE)
        if m_stan:
            aktualny_stan = m_stan.group(1)

        # 2. Szukanie przepływu
        m_przep = re.search(r'Przepływ\s*(\d+[.,]?\d*)\s*m³/s', tekst, re.IGNORECASE)
        if m_przep:
            przeplyw = m_przep.group(1) + " m³/s"

        # 3. Szukanie temperatury wody
        m_temp = re.search(r'Temperatura wody\s*(\d+[.,]?\d*)\s*°C', tekst, re.IGNORECASE)
        if m_temp:
            temperatura = m_temp.group(1) + " °C"

        # 4. Data pomiaru z ukrytych danych JSON
        if "dane" in ukryte_dane:
            dane = str(ukryte_dane["dane"])
            m_data = re.search(r'202\d-\d\d-\d\dT\d\d:\d\d', dane)
            if m_data:
                data_pomiaru = m_data.group(0).replace("T", " ")

        browser.close()

    if not aktualny_stan:
        print("Błąd: Nie udało się wyciągnąć danych ze strony IMGW.")
        return

    poprzedni_stan = pobierz_plik(STATE_FILE)
    ostatni_raport_dzien = pobierz_plik(DAILY_FILE)

    tz_pl = pytz.timezone('Europe/Warsaw')
    teraz_pl = datetime.now(tz_pl)
    dzisiaj_str = teraz_pl.strftime("%Y-%m-%d")
    
    czas_na_raport = (teraz_pl.hour == 6) and (ostatni_raport_dzien != dzisiaj_str)
    stan_zmieniony = (poprzedni_stan != aktualny_stan)

    if not stan_zmieniony and not czas_na_raport:
        print(f"Brak zmian ({aktualny_stan} cm), czekam dalej.")
        return

    # Obliczanie tendencji
    tendencja = "Bez zmian ➖"
    if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan and aktualny_stan.isdigit():
        roznica = int(aktualny_stan) - int(poprzedni_stan)
        if roznica > 0:
            tendencja = f"Rosnąca 📈 (+{roznica} cm)"
        elif roznica < 0:
            tendencja = f"Spadkowa 📉 ({roznica} cm)"

    naglowek = "Poranny raport" if czas_na_raport else "Wykryto zmianę"
    
    # Składanie ostatecznej wiadomości
    komunikat = (
        f"📍 Miejsce: Wisła, Toruń\n"
        f"📏 Aktualny stan: {aktualny_stan} cm\n"
        f"📈 Tendencja: {tendencja}\n"
        f"🌊 Przepływ: {przeplyw}\n"
        f"🌡️ Temp. wody: {temperatura}\n"
        f"🕒 Pomiar z: {data_pomiaru}"
    )
    
    stan_num = int(aktualny_stan) if aktualny_stan and aktualny_stan.isdigit() else 0
    priorytet = "high" if stan_num >= 530 else "default"
    
    # Tytuł z polskimi znakami i emoji
    title_encoded = f"🌊 Wisła Toruń: {aktualny_stan} cm [{naglowek}]".encode("utf-8")
    
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=komunikat.encode("utf-8"),
        headers={
            "Title": title_encoded,
            "Priority": priorytet,
            "Tags": "droplet,water"
        },
        timeout=10
    )
    print(f"Sukces! Wysłano: {aktualny_stan} cm.")

    zapisz_plik(STATE_FILE, aktualny_stan)
    if czas_na_raport:
        zapisz_plik(DAILY_FILE, dzisiaj_str)

if __name__ == "__main__":
    sprawdz_stan_wody()
