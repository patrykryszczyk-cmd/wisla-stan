import os
import socket
import requests
import urllib3.util.connection as urllib_connection

# Wymuszenie IPv4 dla GitHub Actions
urllib_connection.allowed_gai_family = lambda: socket.AF_INET

TOPIC = "stan-wody-wisla"
STATE_FILE = "last_state.txt"

def pobierz_poprzedni_stan():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            zawartosc = f.read().strip()
            return int(zawartosc) if zawartosc.lstrip("-").isdigit() else None
    return None

def zapisz_stan(stan):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(str(stan))

def formatuj_date(data_raw):
    if not data_raw:
        return "brak danych"
    return str(data_raw).replace("T", " ").replace("Z", "")[:16]

def pobierz_dane_torun():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    url_public = "https://danepubliczne.imgw.pl/api/data/hydro/"
    try:
        res = requests.get(url_public, headers=headers, timeout=15)
        if res.status_code == 200:
            lista = res.json()
            if isinstance(lista, list):
                for stacja in lista:
                    if stacja.get("stacja") == "Toruń" and stacja.get("rzeka") == "Wisła":
                        stan = stacja.get("stan_wody")
                        data = stacja.get("stan_wody_data_pomiaru")
                        if stan is not None:
                            return int(float(stan)), formatuj_date(data)
    except Exception as e:
        print(f"Błąd pobierania danych: {e}")
    return None, None

def sprawdz_stan_wody():
    try:
        aktualny_stan, data_pomiaru = pobierz_dane_torun()

        if aktualny_stan is None:
            print("Nie udało się pobrać aktualnego stanu wody dla Torunia.")
            return

        poprzedni_stan = pobierz_poprzedni_stan()

        # Jeśli stan się nie zmienił, nie wysyłaj powiadomienia
        if poprzedni_stan is not None and poprzedni_stan == aktualny_stan:
            print(f"Brak zmian: stan nadal wynosi {aktualny_stan} cm.")
            return

        # Obliczanie tendencji
        if poprzedni_stan is not None and poprzedni_stan != 0:
            roznica = aktualny_stan - poprzedni_stan
            if roznica > 0:
                tendencja = f"📈 Wzrost (+{roznica} cm)"
                tytul_roznica = f" (+{roznica} cm)"
                tag_trend = "chart_with_upwards_trend"
            elif roznica < 0:
                tendencja = f"📉 Spadek ({roznica} cm)"
                tytul_roznica = f" ({roznica} cm)"
                tag_trend = "chart_with_downwards_trend"
            else:
                tendencja = "➡️ Bez zmian"
                tytul_roznica = ""
                tag_trend = "arrow_right"
            linia_poprzedni = f"Poprzednio: {poprzedni_stan} cm\n"
        else:
            tendencja = "ℹ️ Pierwszy odczyt"
            tytul_roznica = ""
            tag_trend = "droplet"
            linia_poprzedni = ""

        # Czytelny, estetyczny układ tekstu
        wiadomosc = (
            f"Poziom wody: {aktualny_stan} cm\n"
            f"Tendencja: {tendencja}\n"
            f"{linia_poprzedni}"
            f"Pomiar IMGW: {data_pomiaru}"
        )

        priorytet = 4 if aktualny_stan >= 530 else 3

        payload = {
            "topic": TOPIC,
            "title": f"Wisła Toruń: {aktualny_stan} cm{tytul_roznica}",
            "message": wiadomosc,
            "priority": priorytet,
            "tags": ["ocean", tag_trend]
        }

        # Wysyłamy do głównego punktu ntfy.sh (prawidłowe parsowanie JSON)
        odpowiedz = requests.post("https://ntfy.sh", json=payload, timeout=15)
        odpowiedz.raise_for_status()

        print(f"Wysłano powiadomienie: {aktualny_stan} cm.")
        zapisz_stan(aktualny_stan)

    except Exception as err:
        print(f"Wystąpił błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
