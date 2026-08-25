import os
import requests

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

    # 1. Główne źródło: Oficjalne API otwartych danych IMGW (pełna lista stacji)
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
        print(f"Błąd pobierania z danepubliczne: {e}")

    # 2. Zapasowe źródło: API hydro-back
    url_hydro = "https://hydro-back.imgw.pl/station/hydro/status?id=153180120"
    try:
        res = requests.get(url_hydro, headers=headers, timeout=15)
        if res.status_code == 200:
            dane = res.json()
            status_obj = dane.get("status") if isinstance(dane, dict) else None
            if isinstance(status_obj, dict):
                curr = status_obj.get("currentState")
                if isinstance(curr, dict):
                    val = curr.get("value")
                    data = curr.get("date")
                    if val is not None:
                        return int(float(val)), formatuj_date(data)
    except Exception as e:
        print(f"Błąd pobierania z hydro-back: {e}")

    return None, None

def sprawdz_stan_wody():
    try:
        aktualny_stan, data_pomiaru = pobierz_dane_torun()

        if aktualny_stan is None:
            print("Nie udało się pobrać aktualnego stanu wody dla Torunia.")
            return

        print(f"Pobrano aktualny stan: {aktualny_stan} cm, pomiar z: {data_pomiaru}")
        poprzedni_stan = pobierz_poprzedni_stan()

        # Jeśli stan się nie zmienił, nie wysyłaj powiadomienia
        if poprzedni_stan is not None and poprzedni_stan == aktualny_stan:
            print(f"Brak zmian: stan nadal wynosi {aktualny_stan} cm.")
            return

        # Wyznaczenie tendencji i różnicy
        if poprzedni_stan is not None and poprzedni_stan != 0:
            roznica = aktualny_stan -理 pop_roznica = aktualny_stan - poprzedni_stan
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

        print(f"Wysłano powiadomienie do ntfy: {aktualny_stan} cm.")
        zapisz_stan(aktualny_stan)

    except Exception as err:
        print(f"Wystąpił błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
