import os
import requests

# Twój stały kanał ntfy:
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

def parsuj_dane_imgw(dane):
    status_info = dane.get("status", dane) if isinstance(dane, dict) else {}
    
    stan_val = None
    data_val = None

    # Obsługa zagnieżdżonego słownika currentState
    curr = status_info.get("currentState")
    if isinstance(curr, dict):
        stan_val = curr.get("value") or curr.get("waterLevel")
        data_val = curr.get("date") or curr.get("measurementDate")
    elif isinstance(curr, (int, float, str)):
        stan_val = curr

    # Alternatywne pola zapasowe
    if stan_val is None:
        wl = status_info.get("waterLevel")
        if isinstance(wl, dict):
            stan_val = wl.get("value")
            data_val = data_val or wl.get("date")
        else:
            stan_val = wl or status_info.get("value")

    if data_val is None:
        data_val = status_info.get("date") or status_info.get("measurementDate") or "Brak daty"

    return stan_val, data_val

def sprawdz_stan_wody():
    url = "https://hydro-back.imgw.pl/station/hydro/status?id=153180120"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        dane = response.json()

        stan_raw, data_pomiaru_raw = parsuj_dane_imgw(dane)

        if stan_raw is None:
            print(f"Nie udało się odczytać wartości ze struktury: {dane}")
            return

        aktualny_stan = int(float(str(stan_raw).strip()))
        data_pomiaru = formatuj_date(data_pomiaru_raw)
        poprzedni_stan = pobierz_poprzedni_stan()

        # Jeśli stan się nie zmienił, nie wysyłaj powiadomienia
        if poprzedni_stan is not None and poprzedni_stan == aktualny_stan:
            print(f"Brak zmian: stan nadal wynosi {aktualny_stan} cm.")
            return

        # Wyznaczenie tendencji i różnicy
        if poprzedni_stan is not None:
            roznica = aktualny_stan - poprzedni_stan
            if roznica > 0:
                tendencja_tekst = f"📈 Wzrost (+{roznica} cm)"
                tytul_roznica = f" (+{roznica} cm)"
                tag_trend = "chart_with_upwards_trend"
            elif roznica < 0:
                tendencja_tekst = f"📉 Spadek ({roznica} cm)"
                tytul_roznica = f" ({roznica} cm)"
                tag_trend = "chart_with_downwards_trend"
            else:
                tendencja_tekst = "➡️ Bez zmian"
                tytul_roznica = ""
                tag_trend = "arrow_right"
            poprzedni_opis = f"Poprzedni stan: {poprzedni_stan} cm\n"
        else:
            tendencja_tekst = "ℹ️ Pierwszy odczyt bota"
            tytul_roznica = ""
            tag_trend = "droplet"
            poprzedni_opis = ""

        # Sformatowany komunikat
        komunikat = (
            f"📏 Aktualny stan: {aktualny_stan} cm\n"
            f"📊 Tendencja: {tendencja_tekst}\n"
            f"{poprzedni_opis}"
            f"🕒 Data pomiaru: {data_pomiaru}"
        )

        priorytet = 4 if aktualny_stan >= 530 else 3

        payload = {
            "topic": TOPIC,
            "title": f"Wisła Toruń: {aktualny_stan} cm{tytul_roznica}",
            "message": komunikat,
            "priority": priorytet,
            "tags": ["ocean", tag_trend]
        }

        odpowiedz = requests.post("https://ntfy.sh", json=payload, timeout=10)
        odpowiedz.raise_for_status()

        print(f"Wysłano powiadomienie: {aktualny_stan} cm.")
        zapisz_stan(aktualny_stan)

    except Exception as err:
        print(f"Błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
