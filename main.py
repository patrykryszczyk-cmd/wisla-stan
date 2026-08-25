import os
import requests

# TUTAJ WPISZ SWOJĄ NAZWĘ Z KROKU 1:
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
    url = "https://danepubliczne.imgw.pl/api/data/hydro/"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        dane = response.json()
        
        torun = next((item for item in dane if item.get("stacja") == "Toruń" and item.get("rzeka") == "Wisła"), None)
        
        if not torun:
            print("Nie znaleziono stacji Toruń w API.")
            return

        aktualny_stan = torun.get("stan_wody")
        data_pomiaru = torun.get("stan_wody_data_pomiaru", "Brak daty")
        temp = torun.get("temperatura_wody")
        temp_tekst = f"{temp}°C" if temp else "brak danych"

        poprzedni_stan = pobierz_poprzedni_stan()

        # Jeśli stan się nie zmienił, nie wysyłaj powiadomienia
        if poprzedni_stan == aktualny_stan:
            print(f"Brak zmian: stan nadal wynosi {aktualny_stan} cm.")
            return

        # Różnica w cm względem ostatniego pomiaru
        roznica_tekst = ""
        if poprzedni_stan and poprzedni_stan.isdigit() and aktualny_stan and aktualny_stan.isdigit():
            roznica = int(aktualny_stan) - int(poprzedni_stan)
            znak = "+" if roznica > 0 else ""
            roznica_tekst = f" ({znak}{roznica} cm)"

        komunikat = f"Poziom wody: {aktualny_stan} cm{roznica_tekst}\nPomiar z: {data_pomiaru}\nTemp. wody: {temp_tekst}"
        
        stan_num = int(aktualny_stan) if aktualny_stan and aktualny_stan.isdigit() else 0
        priorytet = "high" if stan_num >= 530 else "default"
        
        requests.post(
            f"https://ntfy.sh/{TOPIC}",
            data=komunikat.encode("utf-8"),
            headers={
                "Title": f"Wisła Toruń: {aktualny_stan} cm{roznica_tekst}",
                "Priority": priorytet,
                "Tags": "droplet,water"
            },
            timeout=10
        )
        print(f"Wysłano powiadomienie: {aktualny_stan} cm (poprzednio: {poprzedni_stan}).")

        zapisz_stan(aktualny_stan)

    except Exception as err:
        print(f"Błąd: {err}")

if __name__ == "__main__":
    sprawdz_stan_wody()
