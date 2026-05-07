#!/usr/bin/env python3
"""
PP München OSINT – GitHub Actions Scraper
Liest @PressePolizeiMuenchen Telegram-Kanal (alle Seiten per Pagination)
Ermittelt aktuelle Artikel-IDs automatisch – keine fixen Ankerpunkte nötig
"""

import json, os, re, time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ── Konfiguration ─────────────────────────────────────────────────────────────
DAYS_BACK  = 500          # Wie viele Tage zurück scrapen
MAX_ARTS   = 400          # Maximale Artikelanzahl pro Lauf
SLEEP_SEC  = 0.4          # Pause zwischen Requests
BASE_URL   = "https://www.polizei.bayern.de"
TG_CHANNEL = "PressePolizeiMuenchen"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}

# ── Kategorisierung ───────────────────────────────────────────────────────────
RULES = [
    ("Tötungsdelikt",    3, ["tötungsdelikt","mord","totschlag","mordkommission","kommissariat 11","lebensgefahr","tödlich verletzt"]),
    ("Sexualdelikt",     3, ["vergewaltigung","sexuelle nötigung","missbrauch von kindern","sexueller missbrauch"]),
    ("Raub",             3, ["unter vorhalt einer schusswaffe","unter vorhalt eines messers","bewaffneter raubüberfall"]),
    ("Körperverletzung", 3, ["messer","gestochen","stichverletzung","schwere körperverletzung","gefährliche körperverletzung","notoperation"]),
    ("Einbruch",         3, ["wohnungseinbruch"]),
    ("Branddelikt",      3, ["schwere brandstiftung","vorsätzliche brandleg","feuer gelegt","in brand gesetzt"]),
    ("Sexualdelikt",     2, ["sexuelle belästigung","unsittlich berührt","exhibitionistisch"]),
    ("Raub",             2, ["raub","beraubt","entrissen","handtaschenraub","erpressung"]),
    ("Körperverletzung", 2, ["körperverletzung","schlägerei","geschlagen","getreten","faustschlag","bewusstlos","angriff"]),
    ("Einbruch",         2, ["einbruch","einbrecher","eingebrochen","aufgehebelt","aufgebrochen","einbruchsversuch","gewaltsam zutritt"]),
    ("Branddelikt",      2, ["brandstiftung","brand","flammen"]),
    ("Drogen",           2, ["kokain","heroin","amphetamin","crystal","drogenhandel"]),
    ("Betrug",           2, ["enkeltrick","schockanruf","falscher polizist","trickbetrug"]),
    ("Vermisstenfall",   2, ["vermisst","vermisstenfall","abgängig","kind vermisst"]),
    ("Fahndung",         2, ["öffentlichkeitsfahndung","haftbefehl","festgenommen"]),
    ("Verkehr",          2, ["rettungshubschrauber","kollision mit","zusammenstoß mit"]),
    ("Diebstahl",        1, ["diebstahl","gestohlen","entwendet","taschendiebstahl","ladendiebstahl","fahrraddiebstahl","kfz-diebstahl"]),
    ("Drogen",           1, ["cannabis","marihuana","btm","betäubungsmittel","dealer"]),
    ("Betrug",           1, ["betrug","betrüger","phishing","cybercrime"]),
    ("Verkehr",          1, ["verkehrsunfall","unfall","auffahrunfall","unfallflucht","fahrerflucht","alkohol am steuer","überladung","stürzte","rotlicht"]),
    ("Vandalismus",      1, ["sachbeschädigung","graffiti","beschmiert","schmähschrift"]),
    ("Fahndung",         1, ["zeugenaufruf","zeugen gesucht","hinweise erbeten"]),
    ("Prävention",       1, ["prävention","warnt","warnung","hinweis der polizei","fahrradcodier","terminhinweis"]),
]

ORT_MAP = [
    ("Altstadt-Lehel","Altstadt-Lehel"),("Altstadt","Altstadt-Lehel"),("Lehel","Altstadt-Lehel"),
    ("Maxvorstadt","Maxvorstadt"),("Schwabing-West","Schwabing-West"),("Schwabing","Schwabing"),
    ("Neuhausen-Nymphenburg","Neuhausen-Nymphenburg"),("Neuhausen","Neuhausen-Nymphenburg"),("Nymphenburg","Neuhausen-Nymphenburg"),
    ("Sendling-Westpark","Sendling"),("Sendling","Sendling"),
    ("Au-Haidhausen","Au-Haidhausen"),("Haidhausen","Au-Haidhausen"),("Au","Au-Haidhausen"),
    ("Bogenhausen","Bogenhausen"),("Pasing-Obermenzing","Pasing-Obermenzing"),
    ("Pasing","Pasing-Obermenzing"),("Obermenzing","Pasing-Obermenzing"),
    ("Obergiesing","Obergiesing"),("Untergiesing","Untergiesing"),("Harlaching","Harlaching"),
    ("Giesing","Giesing"),("Moosach","Moosach"),
    ("Ramersdorf-Perlach","Ramersdorf-Perlach"),("Ramersdorf","Ramersdorf-Perlach"),("Perlach","Ramersdorf-Perlach"),
    ("Milbertshofen","Milbertshofen"),("Freimann","Milbertshofen"),
    ("Trudering","Trudering"),("Hadern","Hadern"),("Fürstenried","Hadern"),
    ("Laim","Laim"),("Berg am Laim","Berg am Laim"),
    ("Feldmoching-Hasenbergl","Feldmoching-Hasenbergl"),("Feldmoching","Feldmoching-Hasenbergl"),("Hasenbergl","Feldmoching-Hasenbergl"),
    ("Schwanthalerhöhe","Schwanthalerhöhe"),("Thalkirchen","Thalkirchen"),
    ("Ludwigsvorstadt","Ludwigsvorstadt"),("Isarvorstadt","Isarvorstadt"),("Glockenbachviertel","Isarvorstadt"),
    ("Allach-Untermenzing","Allach-Untermenzing"),("Allach","Allach-Untermenzing"),
    ("Hauptbahnhof","Stadtmitte"),("Marienplatz","Stadtmitte"),("Stachus","Stadtmitte"),
    ("Karlsplatz","Stadtmitte"),("Innenstadt","Stadtmitte"),("Stadtmitte","Stadtmitte"),
    ("Rotkreuzplatz","Neuhausen-Nymphenburg"),("Kolumbusplatz","Ramersdorf-Perlach"),
    ("Grünwald","Münchner Umland"),("Sauerlach","Münchner Umland"),("Haar","Münchner Umland"),
    ("Dachau","Münchner Umland"),("Unterhaching","Münchner Umland"),("Aschheim","Münchner Umland"),
    ("Hohenbrunn","Münchner Umland"),("Kirchheim","Münchner Umland"),("Garching","Münchner Umland"),
    ("Ismaning","Münchner Umland"),("Unterschleißheim","Münchner Umland"),("Neubiberg","Münchner Umland"),
    ("Landkreis","Münchner Umland"),
]


def categorize(text):
    t = text.lower()
    for kat, sev, words in RULES:
        if any(w in t for w in words): return kat, sev
    return "Sonstiges", 1


def detect_ort(text):
    for term, canonical in ORT_MAP:
        if term in text: return canonical
    return "Unbekannt"


def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status(); r.encoding = "utf-8"; return r.text
    except Exception as e:
        print(f"  ✗ {url[-60:]} → {e}"); return None


def get_all_telegram_urls(from_date, to_date):
    """
    Liest Telegram-Kanal seitenweise per ?before=MSG_ID Pagination.
    Ermittelt die aktuellen Artikel-IDs direkt aus den Links – keine Ankerpunkte nötig.
    """
    print("Lese Telegram-Kanal (alle Seiten)…")

    art_pat = re.compile(
        r'https?://(?:www\.)?polizei\.bayern\.de/aktuelles/pressemitteilungen/(\d{6})/index\.html'
    )
    msg_pat = re.compile(r'data-post="[^/]+/(\d+)"')

    seen_arts  = set()
    all_urls   = []
    all_art_ids = []
    before_id  = None
    reached_old = False

    for page in range(80):  # max 80 Seiten
        url = f"https://t.me/s/{TG_CHANNEL}" + (f"?before={before_id}" if before_id else "")
        html = fetch(url, timeout=25)
        if not html:
            print(f"  Seite {page+1}: nicht erreichbar"); break

        # Alle Artikel-Links auf dieser Seite sammeln
        new_count = 0
        for m in art_pat.finditer(html):
            art_id  = int(m.group(1))
            art_url = m.group(0)
            all_art_ids.append(art_id)
            if art_url not in seen_arts:
                seen_arts.add(art_url)
                all_urls.append((art_id, art_url))
                new_count += 1

        # Kleinste Post-ID für nächste Seite
        msg_ids = [int(x) for x in msg_pat.findall(html)]
        if not msg_ids:
            print(f"  Seite {page+1}: Ende des Kanals"); break

        min_msg_id = min(msg_ids)
        print(f"  Seite {page+1} (vor #{before_id or 'aktuell'}): {new_count} neue Links")

        if len(all_urls) >= MAX_ARTS:
            print(f"  Maximum von {MAX_ARTS} Artikeln erreicht"); break
        if min_msg_id <= 1:
            print("  Kanalanfang erreicht"); break
        if min_msg_id == before_id:
            print("  Keine Änderung – stoppe"); break

        before_id = min_msg_id
        time.sleep(0.6)

    # Jetzt Datumsfilter anwenden:
    # Wir kennen die Artikel-IDs – wir brauchen einen Referenzpunkt.
    # Strategie: die höchste ID = heute, die niedrigste im Zeitraum berechnen.
    if not all_art_ids:
        print("  Telegram: keine Links gefunden")
        return []

    max_id = max(all_art_ids)
    min_id = min(all_art_ids)
    total_ids = max_id - min_id if max_id != min_id else 1

    # Schätze Datum pro Artikel-ID (lineare Interpolation)
    # max_id = heute, min_id = ältester Post im Kanal
    # Kanal existiert seit ~2020, aber wir kennen max_id = heute
    now = datetime.now()

    def estimate_date(art_id):
        """Schätze Datum einer Artikel-ID basierend auf max_id = heute."""
        # PP München veröffentlicht ca. 2-3 Artikel pro Tag
        days_ago = (max_id - art_id) / 2.5
        return now - timedelta(days=days_ago)

    # Filter auf gewünschten Zeitraum
    filtered_urls = []
    for art_id, art_url in sorted(all_urls, key=lambda x: x[0]):
        est_date = estimate_date(art_id)
        if from_date <= est_date <= to_date:
            filtered_urls.append(art_url)

    print(f"  Telegram gesamt: {len(all_urls)} Links, davon {len(filtered_urls)} im Zeitraum")
    return filtered_urls


def get_urls_by_id_range(from_date, to_date, max_known_id):
    """
    Fallback: generiert URLs basierend auf der höchsten bekannten ID.
    max_known_id wird aus Telegram ermittelt.
    """
    now = datetime.now()
    days_to   = (to_date   - now).days
    days_from = (from_date - now).days

    # ca. 2.5 Artikel pro Tag
    id_to   = max_known_id + abs(days_to)   * 3 + 10
    id_from = max_known_id + days_from * 3  - 10
    id_from = max(1, id_from)

    print(f"  ID-Range Fallback: {id_from}–{id_to} ({id_to-id_from+1} Kandidaten)")
    return [f"{BASE_URL}/aktuelles/pressemitteilungen/{i:06d}/index.html"
            for i in range(id_from, id_to + 1)]


def parse_article(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title_text = (soup.find("title") or type("",(),{"get_text":lambda *a:""})()).get_text()
    dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title_text)
    if not dm or "München" not in title_text: return []
    pm_date = datetime(int(dm[3]), int(dm[2]), int(dm[1]))

    for tag in soup(["nav","header","footer","script","style"]): tag.decompose()
    content = soup.find(class_="c-richtext") or soup.find("article") or soup.find("main")
    if not content: return []

    incidents = []
    sections  = content.find_all("h3")

    if not sections:
        body = content.get_text(" ", strip=True)
        if len(body) < 50: return []
        kat, sev = categorize(body)
        dm2 = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", body)
        inc_date = datetime(int(dm2[3]),int(dm2[2]),int(dm2[1])) if dm2 else pm_date
        tm = re.search(r"(\d{1,2})[:.h](\d{2})\s*Uhr", body)
        return [_make(inc_date, f"{int(tm[1]):02d}:{tm[2]}" if tm else "",
                      "", kat, sev, detect_ort(body), body[:120], body[:1500], url)]

    for h in sections:
        heading = h.get_text(" ", strip=True)
        num_m   = re.match(r"^(\d+)\.\s+", heading)
        nr      = num_m[1] if num_m else ""
        titel   = re.sub(r"^\d+\.\s+", "", heading).strip()
        ort_m   = re.search(r"–\s*(.+)$", titel)
        ort_raw = ort_m[1].strip() if ort_m else ""
        ort     = detect_ort(ort_raw) if ort_raw else "Unbekannt"

        parts = []
        for sib in h.find_next_siblings():
            if sib.name in ("h3","h2","hr"): break
            parts.append(sib.get_text(" ", strip=True))
        body = " ".join(parts).strip()
        if len(body) < 30: continue

        dm2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", body)
        inc_date = datetime(int(dm2[3]),int(dm2[2]),int(dm2[1])) if dm2 else pm_date
        tm = re.search(r"(\d{1,2})[:.h](\d{2})\s*Uhr", body)
        kat, sev = categorize(titel + " " + body)
        if ort == "Unbekannt": ort = detect_ort(body)

        incidents.append(_make(
            inc_date, f"{int(tm[1]):02d}:{tm[2]}" if tm else "",
            nr, kat, sev, ort, titel[:120], body[:1500], url
        ))

    return incidents


def _make(dt, time_str, nr, kat, sev, ort, titel, volltext, link):
    return {
        "date":        dt.strftime("%d.%m.%Y"),
        "dateSort":    dt.strftime("%Y-%m-%d"),
        "time":        time_str,
        "nr":          nr,
        "kategorie":   kat,
        "schweregrad": sev,
        "ort":         ort,
        "titel":       titel,
        "volltext":    volltext,
        "link":        link,
    }


def main():
    to_date   = datetime.now().replace(hour=23, minute=59, second=59)
    from_date = (to_date - timedelta(days=DAYS_BACK)).replace(hour=0, minute=0, second=0)

    print(f"═══════════════════════════════════════════")
    print(f"  PP München OSINT Scraper")
    print(f"  Zeitraum: {from_date.date()} → {to_date.date()}")
    print(f"═══════════════════════════════════════════")

    # 1. URLs aus Telegram holen (automatische ID-Erkennung)
    urls = get_all_telegram_urls(from_date, to_date)

    if not urls:
        print("Telegram leer – verwende ID-Range Fallback")
        # Versuche höchste bekannte ID aus letztem Datensatz zu lesen
        max_id = 102400  # Mindest-Fallback
        try:
            with open("data/incidents.json", "r") as f:
                existing = json.load(f)
                if existing:
                    links = [p.get("link","") for p in existing if p.get("link")]
                    ids   = [int(m.group(1)) for l in links
                             for m in [re.search(r'/(\d{6})/', l)] if m]
                    if ids: max_id = max(ids)
                    print(f"  Höchste bekannte ID aus Datensatz: {max_id}")
        except: pass
        urls = get_urls_by_id_range(from_date, to_date, max_id)

    urls = urls[:MAX_ARTS]
    print(f"\n  Verarbeite {len(urls)} Artikel…\n")

    # 2. Bestehende Daten laden (um sie zu ergänzen, nicht zu überschreiben)
    existing_data = []
    existing_links = set()
    try:
        with open("data/incidents.json", "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            existing_links = {p.get("link","") for p in existing_data}
            print(f"  Bestehende Daten: {len(existing_data)} Vorfälle geladen")
    except:
        print("  Kein bestehender Datensatz – starte frisch")

    # 3. Neue Artikel abrufen & parsen
    all_incidents = list(existing_data)
    loaded = 0

    for i, url in enumerate(urls):
        # Bereits bekannte Artikel überspringen (nur neue laden)
        if url in existing_links:
            print(f"  [{i+1:3d}/{len(urls)}] {url.split('/')[-2]} … bereits vorhanden ✓")
            continue

        art_id = url.split("/")[-2]
        print(f"  [{i+1:3d}/{len(urls)}] {art_id}", end=" … ")
        html = fetch(url)
        if not html or len(html) < 300: print("leer"); continue
        if "München" not in html[:4000]: print("kein PP München"); continue

        # Datum-Vorabcheck
        soup_q = BeautifulSoup(html[:2000], "html.parser")
        t = (soup_q.find("title") or type("",(),{"get_text":lambda *a:""})()).get_text()
        dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", t)
        if dm:
            ad = datetime(int(dm[3]),int(dm[2]),int(dm[1]))
            if ad < from_date or ad > to_date:
                print(f"außerhalb ({ad.date()})"); continue

        incidents = parse_article(html, url)
        if incidents:
            print(f"✓ {len(incidents)} Vorfälle")
            all_incidents.extend(incidents)
            existing_links.add(url)
            loaded += 1
        else:
            print("✗ keine Vorfälle")

        time.sleep(SLEEP_SEC)

    # 4. Sortieren & Deduplizieren
    all_incidents.sort(key=lambda x: (x.get("dateSort",""), x.get("time","")), reverse=True)

    seen, deduped = set(), []
    for inc in all_incidents:
        key = f"{inc.get('dateSort','')}|{inc.get('titel','')[:60]}|{inc.get('nr','')}"
        if key not in seen:
            seen.add(key); deduped.append(inc)
    all_incidents = deduped
    print(f"\n  Nach Deduplizierung: {len(all_incidents)} Vorfälle gesamt")

    # 5. Speichern
    Path("data").mkdir(exist_ok=True)
    with open("data/incidents.json", "w", encoding="utf-8") as f:
        json.dump(all_incidents, f, ensure_ascii=False, indent=2)

    meta = {
        "updated":     datetime.now().strftime("%d.%m.%Y %H:%M"),
        "updated_iso": datetime.now().isoformat(),
        "from_date":   from_date.strftime("%Y-%m-%d"),
        "to_date":     to_date.strftime("%Y-%m-%d"),
        "articles":    loaded,
        "incidents":   len(all_incidents),
    }
    with open("data/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {loaded} neue Artikel · {len(all_incidents)} Vorfälle gesamt")
    print(f"     → data/incidents.json ({os.path.getsize('data/incidents.json')//1024} KB)")


if __name__ == "__main__":
    main()
