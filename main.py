import os
import requests
from datetime import datetime
import pytz

# TUTAJ WPISZ SWOJĄ NAZWĘ Z KROKU 1:
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
    url = "https://danepubliczne.imgw.pl/api/data/hydro/"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        dane = response.json()
        
        # Zostawiam "Silno" na czas awarii wodowskazu w Toruniu
        stacja = next((item for item in dane if item.get("stacja") == "Toruń" and item.get("rzeka") == "Wisła"), None)
        
        if not stacja:
            print("Nie znaleziono stacji w API.")
            return

        aktualny_stan = stacja.get("stan_wody")
        data_pomiaru = stacja.get("stan_wody_data_pomiaru", "Brak daty")
        
        poprzedni_stan = pobierz_plik(STATE_FILE)
        ostatni_raport_dzien = pobierz_plik(DAILY_FILE)

        # Ustalanie aktualnego czasu w Polsce
        tz_pl = pytz.timezone('Europe/Warsaw')
        teraz_pl = datetime.now(tz_pl)
        dzisiaj_str = teraz_pl.strftime("%Y-%m-%d")
        
        # Sprawdzenie, czy jest po 6:00 rano i czy raport był już dziś wysłany
        czas_na_raport = (teraz_pl.hour == 6) and (ostatni_raport_dzien != dzisiaj_str)
        
        # Sprawdzenie, czy stan się zmienił od ostatniego razu
        stan_zmieniony = (poprzedni_stan != aktualny_stan)

        # Jeśli nie ma 6:00 rano, a stan jest taki sam - kończymy
        if not stan_zmieniony and not czas_na_raport:
            print(f"Brak zmian ({aktualny_stan} cm), czekam dalej.")
            return

        # Obliczanie tendencji (rosnąca/spadkowa/bez zmian)
        tendencja = "Brak danych ➖"
        if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan and aktualny_stan.isdigit():
            roznica = int(aktualny_stan) - int(poprzedni_stan)
            if roznica > 0:
                tendencja = f"Rosnąca 📈 (+{roznica} cm)"
            elif roznica < 0:
                tendencja = f"Spadkowa 📉 ({roznica} cm)"
            else:
                tendencja = "Bez zmian ➖"

        # Formatowanie wiadomości
        naglowek = "Poranny raport" if czas_na_raport else "Wykryto zmianę"
        
        komunikat = (
            f"Pomiar z API: {data_pomiaru}\n"
            f"Stan aktualny: {aktualny_stan} cm\n"
            f"Stan ostatni: {poprzedni_stan if poprzedni_stan else 'Brak'} cm\n"
            f"Tendencja: {tendencja}"
        )
        
        stan_num = int(aktualny_stan) if aktualny_stan and aktualny_stan.isdigit() else 0
        priorytet = "high" if stan_num >= 530 else "default"
        
        requests.post(
            f"https://ntfy.sh/{TOPIC}",
            data=komunikat.encode("utf-8"),
            headers={
                "Title": f"Wisła: {aktualny_stan} cm [{naglowek}]".encode("utf-8"),
                "Priority": priorytet,
                "Tags": "droplet,water"
            },
            timeout=10
        )
        print(f"Wysłano powiadomienie. Aktualny stan: {aktualny_stan} cm.")

        # Zapisywanie danych do plików
        zapisz_plik(STATE_FILE, aktualny_stan)
        if czas_na_raport:
            zapisz_plik(DAILY_FILE, dzisiaj_str)

    except Exception as err:
        print(f"Błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
