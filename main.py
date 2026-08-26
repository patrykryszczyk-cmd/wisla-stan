import os
import re
import json
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

# Funkcja do wyszukiwania danych w ukrytych odpowiedziach serwera IMGW
def znajdz_wartosc(dane, klucze):
    if isinstance(dane, dict):
        for k, v in dane.items():
            if k in klucze: return v
            res = znajdz_wartosc(v, klucze)
            if res is not None: return res
    elif isinstance(dane, list):
        for item in dane:
            res = znajdz_wartosc(item, klucze)
            if res is not None: return res
    return None

def sprawdz_stan_wody():
    # Link, który mi podałeś - udajemy, że wchodzimy na tę stronę
    url = "https://hydro.imgw.pl/#/station/hydro/153180090?h=25"
    
    aktualny_stan = None
    data_pomiaru = "Brak daty"
    
    print("Otwieram wirtualną przeglądarkę i ładuję mapę IMGW...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        ukryte_dane = {}
        
        # Przechwytujemy niewidoczne dla zwykłego użytkownika zapytania, które strona wysyła do serwera po załadowaniu
        def handle_response(response):
            if "153180090" in response.url and response.status == 200:
                try:
                    dane_json = response.json()
                    ukryte_dane["dane"] = dane_json
                except:
                    pass
                    
        page.on("response", handle_response)
        
        # Wchodzimy na stronę i dajemy jej 5 sekund na załadowanie się do końca
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(5000)
        
        # Krok 1: Próba wyciągnięcia stanu z przechwyconego ruchu sieciowego
        if "dane" in ukryte_dane:
            stan_z_sieci = znajdz_wartosc(ukryte_dane["dane"], ["waterLevel", "stanWody", "value", "currentState"])
            data_z_sieci = znajdz_wartosc(ukryte_dane["dane"], ["date", "measurementDate", "time", "dateMeasure"])
            
            if stan_z_sieci is not None:
                aktualny_stan = str(int(float(stan_z_sieci)))
            if data_z_sieci is not None:
                data_pomiaru = str(data_z_sieci).replace("T", " ")[:16]
        
        # Krok 2 (Zabezpieczenie): Jeśli ruch sieciowy był zaszyfrowany, wyciągamy tekst wprost ze strony WWW
        if not aktualny_stan:
            tekst = page.inner_text("body")
            m = re.search(r'Stan wody.*?(\d+)\s*cm', tekst, re.IGNORECASE)
            if not m:
                m = re.search(r'(\d+)\s*cm', tekst, re.IGNORECASE)
            if m:
                aktualny_stan = m.group(1)
                data_pomiaru = "Odczyt bezpośrednio ze strony"
                
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

    tendencja = "Brak danych ➖"
    if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan and aktualny_stan.isdigit():
        roznica = int(aktualny_stan) - int(poprzedni_stan)
        if roznica > 0:
            tendencja = f"Rosnąca 📈 (+{roznica} cm)"
        elif roznica < 0:
            tendencja = f"Spadkowa 📉 ({roznica} cm)"
        else:
            tendencja = "Bez zmian ➖"

    naglowek = "Poranny raport" if czas_na_raport else "Wykryto zmianę"
    
    komunikat = (
        f"Pomiar: {data_pomiaru}\n"
        f"Stan aktualny: {aktualny_stan} cm\n"
        f"Stan ostatni: {poprzedni_stan if poprzedni_stan else 'Brak'} cm\n"
        f"Tendencja: {tendencja}"
    )
    
    stan_num = int(aktualny_stan) if aktualny_stan and aktualny_stan.isdigit() else 0
    priorytet = "high" if stan_num >= 530 else "default"
    
    title_encoded = f"Wisła: {aktualny_stan} cm [{naglowek}]".encode("utf-8")
    
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
