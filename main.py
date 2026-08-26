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
    
    tz_pl = pytz.timezone('Europe/Warsaw')
    teraz_pl = datetime.now(tz_pl)
    dzisiaj_str = teraz_pl.strftime("%Y-%m-%d")
    
    print("Otwieram wirtualną przeglądarkę i ładuję mapę IMGW...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(10000)
        
        tekst = page.inner_text("body")
        tekst_czysty = re.sub(r'\s+', ' ', tekst)
        
        # Nowa, super-precyzyjna metoda: wyciąganie danych prosto z wiersza tabeli
        # Przykład, którego szuka skrypt: "25.08 06:00 UTC 79 246 19,2"
        m_row = re.search(r'(\d{2})\.(\d{2})\s+(\d{2}:\d{2})\s+UTC\s+(\d+)(?:\s+(\d+|-))?(?:\s+(\d+,\d+|-))?', tekst_czysty)
        
        if m_row:
            dzien = m_row.group(1)
            miesiac = m_row.group(2)
            godzina = m_row.group(3)
            # Składamy ładną datę np. 2026-08-25 06:00
            data_pomiaru = f"{teraz_pl.year}-{miesiac}-{dzien} {godzina}"
            
            aktualny_stan = m_row.group(4)
            
            p_val = m_row.group(5)
            if p_val and p_val != '-': przeplyw = p_val + " m³/s"
                
            t_val = m_row.group(6)
            if t_val and t_val != '-': temperatura = t_val.replace(',', '.') + " °C"
        else:
            # Zapasowe szukanie, gdyby IMGW znowu wyłączyło tabelę
            m_stan = re.search(r'(?:STAN AKTUALNY|STAN OSTATNI).*?(\d+)\s*cm', tekst_czysty, re.IGNORECASE)
            if m_stan: aktualny_stan = m_stan.group(1)

        if not aktualny_stan:
            print("\n--- ZRZUT EKRANU DO DEBUGOWANIA ---")
            print(tekst_czysty[:2000])
            print("-----------------------------------\n")

        browser.close()

    if not aktualny_stan:
        print("Błąd: Nie udało się wyciągnąć stanu wody ze strony.")
        return

    poprzedni_stan = pobierz_plik(STATE_FILE)
    ostatni_raport_dzien = pobierz_plik(DAILY_FILE)
    
    czas_na_raport = (teraz_pl.hour == 6) and (ostatni_raport_dzien != dzisiaj_str)
    stan_zmieniony = (poprzedni_stan != aktualny_stan)

    if not stan_zmieniony and not czas_na_raport:
        print(f"Brak zmian ({aktualny_stan} cm), czekam dalej.")
        return

    tendencja = "Bez zmian ➖"
    if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan and aktualny_stan.isdigit():
        roznica = int(aktualny_stan) - int(poprzedni_stan)
        if roznica > 0: tendencja = f"Rosnąca 📈 (+{roznica} cm)"
        elif roznica < 0: tendencja = f"Spadkowa 📉 ({roznica} cm)"

    naglowek = "Poranny raport" if czas_na_raport else "Wykryto zmianę"
    
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
    print(f"Sukces! Wysłano: {aktualny_stan} cm, Przepływ: {przeplyw}, Temp: {temperatura}")

    zapisz_plik(STATE_FILE, aktualny_stan)
    if czas_na_raport:
        zapisz_plik(DAILY_FILE, dzisiaj_str)

if __name__ == "__main__":
    sprawdz_stan_wody()
