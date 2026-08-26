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

def znajdz_wartosc(dane, szukane_klucze):
    # Szukanie wartości w surowych danych systemowych IMGW
    if isinstance(dane, dict):
        for k, v in dane.items():
            if k.lower() in szukane_klucze and v is not None:
                return v
            res = znajdz_wartosc(v, szukane_klucze)
            if res is not None: return res
    elif isinstance(dane, list):
        for item in dane:
            res = znajdz_wartosc(item, szukane_klucze)
            if res is not None: return res
    return None

def sprawdz_stan_wody():
    url = "https://hydro.imgw.pl/#/station/hydro/153180090?h=25"
    
    aktualny_stan = None
    data_pomiaru = "Brak danych"
    przeplyw = "Brak danych"
    temperatura = "Brak danych"
    
    print("Otwieram wirtualną przeglądarkę (ekran Full HD) i ładuję mapę IMGW...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Ustawiamy duży ekran, by strona nie ukrywała tabel
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        ukryte_dane = {}
        
        def handle_response(response):
            if "153180090" in response.url and response.status == 200:
                try:
                    ukryte_dane["dane"] = response.json()
                except:
                    pass
                    
        page.on("response", handle_response)
        
        page.goto(url, wait_until="networkidle")
        # Wydłużamy czas do 10 sekund dla pewności
        page.wait_for_timeout(10000)
        
        tekst = page.inner_text("body")
        tekst_czysty = re.sub(r'\s+', ' ', tekst)
        
        # METODA 1: Najbardziej precyzyjna (czytanie surowych danych systemowych)
        if "dane" in ukryte_dane:
            dane_json = ukryte_dane["dane"]
            
            stan_siec = znajdz_wartosc(dane_json, ["stanwody", "waterlevel"])
            if stan_siec is not None: aktualny_stan = str(int(float(stan_siec)))
                
            przep_siec = znajdz_wartosc(dane_json, ["przeplyw", "flow", "discharge"])
            if przep_siec is not None: przeplyw = str(przep_siec) + " m³/s"
                
            temp_siec = znajdz_wartosc(dane_json, ["temperatura", "temperature", "watertemperature"])
            if temp_siec is not None: temperatura = str(temp_siec) + " °C"
                
            data_siec = znajdz_wartosc(dane_json, ["date", "measurementdate", "datemeasure"])
            if data_siec is not None: data_pomiaru = str(data_siec).replace("T", " ")[:16]

        # METODA 2: Awaryjne czytanie tekstu, jeśli metoda 1 zawiedzie
        if not aktualny_stan:
            m_stan = re.search(r'Stan wody[^0-9]{0,30}(\d+)', tekst_czysty, re.IGNORECASE)
            if m_stan: aktualny_stan = m_stan.group(1)

        if przeplyw == "Brak danych":
            m_przep = re.search(r'Przepływ[^0-9]{0,30}(\d+[.,]?\d*)', tekst_czysty, re.IGNORECASE)
            if m_przep: przeplyw = m_przep.group(1) + " m³/s"

        if temperatura == "Brak danych":
            m_temp = re.search(r'Temperatura wody[^0-9]{0,30}(\d+[.,]?\d*)', tekst_czysty, re.IGNORECASE)
            if m_temp: temperatura = m_temp.group(1) + " °C"

        if data_pomiaru == "Brak danych":
            daty = re.findall(r'202\d-\d\d-\d\d \d\d:\d\d', tekst_czysty)
            if daty: data_pomiaru = daty[0]

        # Dodatkowy log w razie kolejnego błędu
        if not aktualny_stan:
            print("\n--- ZRZUT EKRANU (TEKST) DO DEBUGOWANIA ---")
            print(tekst_czysty[:2000])
            print("-------------------------------------------\n")

        browser.close()

    if not aktualny_stan:
        print("Błąd: Nie udało się wyciągnąć stanu wody ze strony.")
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
