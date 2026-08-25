import os
import requests

# Wpisz swój unikalny temat z aplikacji ntfy
TOPIC = "stan-wody-wisla"
STATE_FILE = "last_state.txt"

def pobierz_poprzedni_stan():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def zapisz_stan(stan):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(str(stan))

def sprawdz_stan_wody():
    # Pobieranie danych bezpośrednio z produkcyjnego API hydro.imgw.pl (stacja Toruń: 153180120)
    url = "https://hydro-back.imgw.pl/station/hydro/status?id=153180120"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        dane = response.json()

        # Odczyt danych ze struktury hydro-back
        status_info = dane.get("status", dane)
        aktualny_stan = status_info.get("currentState") or status_info.get("waterLevel") or status_info.get("value")
        data_pomiaru = status_info.get("date") or status_info.get("measurementDate") or "Brak daty"

        if aktualny_stan is None:
            print(f"Nie udało się odczytać stanu wody z odpowiedzi: {dane}")
            return

        aktualny_stan = str(aktualny_stan)
        poprzedni_stan = pobierz_poprzedni_stan()

        # Jeśli stan się nie zmienił, nie wysyłaj powiadomienia
        if poprzedni_stan == aktualny_stan:
            print(f"Brak zmian: stan nadal wynosi {aktualny_stan} cm.")
            return

        # Różnica w cm względem ostatniego pomiaru
        roznica_tekst = ""
        if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan.isdigit():
            roznica = int(aktualny_stan) - int(poprzedni_stan)
            znak = "+" if roznica > 0 else ""
            roznica_tekst = f" ({znak}{roznica} cm)"

        komunikat = f"Poziom wody: {aktualny_stan} cm{roznica_tekst}\nPomiar z: {data_pomiaru}"
        
        stan_num = int(aktualny_stan) if aktualny_stan.isdigit() else 0
        priorytet = 4 if stan_num >= 530 else 3

        payload = {
            "topic": TOPIC,
            "title": f"Wisła Toruń: {aktualny_stan} cm{roznica_tekst}",
            "message": komunikat,
            "priority": priorytet,
            "tags": ["droplet", "water"]
        }

        odpowiedz = requests.post("https://ntfy.sh", json=payload, timeout=10)
        odpowiedz.raise_for_status()

        print(f"Wysłano powiadomienie: {aktualny_stan} cm (poprzednio: {poprzedni_stan}).")
        zapisz_stan(aktualny_stan)

    except Exception as err:
        print(f"Błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
