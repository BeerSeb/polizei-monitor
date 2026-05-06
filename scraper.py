#!/usr/bin/env python3
"""
PP München OSINT – GitHub Actions Scraper
Liest @PressePolizeiMuenchen Telegram-Kanal (alle Seiten per Pagination) + polizei.bayern.de
"""

import json, os, re, time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

DAYS_BACK  = 500
MAX_ARTS   = 400
SLEEP_SEC  = 0.4
BASE_URL   = "https://www.polizei.bayern.de"
TG_CHANNEL = "PressePolizeiMuenchen"
HEADERS    = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "de-DE,de;q=0.9"}

ANCHORS = sorted([
    (102241, datetime(2026,5,4)),(102182, datetime(2026,5,3)),(102135, datetime(2026,5,1)),
    (101569, datetime(2026,4,20)),(100970, datetime(2026,4,8)),(99056, datetime(2026,3,1)),
    (98461, datetime(2026,2,20)),(96662, datetime(2026,1,13)),(96203, datetime(2026,1,2)),
    (96156, datetime(2026,1,1)),(93500, datetime(2025,11,1)),(91000, datetime(2025,9,1)),
    (88500, datetime(2025,7,1)),(86000, datetime(2025,5,1)),(83500, datetime(2025,3,1)),
    (81000, datetime(2025,1,1)),
], key=lambda x: x[1])

RULES = [
    ("Tötungsdelikt",3,["tötungsdelikt","mord","totschlag","mordkommission","kommissariat 11","lebensgefahr","tödlich verletzt"]),
    ("Sexualdelikt",3,["vergewaltigung","sexuelle nötigung","missbrauch von kindern","sexueller missbrauch"]),
    ("Raub",3,["unter vorhalt einer schusswaffe","unter vorhalt eines messers","bewaffneter raubüberfall"]),
    ("Körperverletzung",3,["messer","gestochen","stichverletzung","schwere körperverletzung","gefährliche körperverletzung","notoperation"]),
    ("Einbruch",3,["wohnungseinbruch"]),
    ("Branddelikt",3,["schwere brandstiftung","vorsätzliche brandleg","feuer gelegt","in brand gesetzt"]),
    ("Sexualdelikt",2,["sexuelle belästigung","unsittlich berührt","exhibitionistisch"]),
    ("Raub",2,["raub","beraubt","entrissen","handtaschenraub","erpressung"]),
    ("Körperverletzung",2,["körperverletzung","schlägerei","geschlagen","getreten","faustschlag","bewusstlos","angriff"]),
    ("Einbruch",2,["einbruch","einbrecher","eingebrochen","aufgehebelt","aufgebrochen","einbruchsversuch","gewaltsam zutritt"]),
    ("Branddelikt",2,["brandstiftung","brand","flammen"]),
    ("Drogen",2,["kokain","heroin","amphetamin","crystal","drogenhandel"]),
    ("Betrug",2,["enkeltrick","schockanruf","falscher polizist","trickbetrug"]),
    ("Vermisstenfall",2,["vermisst","vermisstenfall","abgängig","kind vermisst"]),
    ("Fahndung",2,["öffentlichkeitsfahndung","haftbefehl","festgenommen"]),
    ("Verkehr",2,["rettungshubschrauber","kollision mit","zusammenstoß mit"]),
    ("Diebstahl",1,["diebstahl","gestohlen","entwendet","taschendiebstahl","ladendiebstahl","fahrraddiebstahl","kfz-diebstahl"]),
    ("Drogen",1,["cannabis","marihuana","btm","betäubungsmittel","dealer"]),
    ("Betrug",1,["betrug","betrüger","phishing","cybercrime"]),
    ("Verkehr",1,["verkehrsunfall","unfall","auffahrunfall","unfallflucht","fahrerflucht","alkohol am steuer","überladung","stürzte","rotlicht"]),
    ("Vandalismus",1,["sachbeschädigung","graffiti","beschmiert","schmähschrift"]),
    ("Fahndung",1,["zeugenaufruf","zeugen gesucht","hinweise erbeten"]),
    ("Prävention",1,["prävention","warnt","warnung","hinweis der polizei","fahrradcodier","terminhinweis"]),
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

def interpolate_id(target_date):
    before, after = ANCHORS[0], ANCHORS[-1]
    for a in ANCHORS:
        if a[1] <= target_date: before = a
        if a[1] >= target_date and a[1] <= after[1]: after = a
    if before[1] == after[1]: return before[0]
    r = (target_date - before[1]).total_seconds() / (after[1] - before[1]).total_seconds()
    return round(before[0] + r * (after[0] - before[0]))

def fetch(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status(); r.encoding = "utf-8"; return r.text
    except Exception as e:
        print(f"  ✗ {url[-60:]} → {e}"); return None

def get_urls_from_telegram(from_date, to_date):
    """Liest Telegram-Kanal seitenweise durch ?before=MSG_ID Pagination."""
    print("Lese Telegram-Kanal (alle Seiten per Pagination)…")
    id_from = interpolate_id(from_date) - 20
    id_to   = interpolate_id(to_date)   + 20
    art_pat = re.compile(r'https?://(?:www\.)?polizei\.bayern\.de/aktuelles/pressemitteilungen/(\d{6})/index\.html')
    msg_pat = re.compile(r'data-post="[^/]+/(\d+)"')
    seen, urls, before_id = set(), [], None

    for page in range(60):  # max 60 Seiten x ~20 Posts = ~1200 Posts
        url = f"https://t.me/s/{TG_CHANNEL}" + (f"?before={before_id}" if before_id else "")
        html = fetch(url, timeout=20)
        if not html: print(f"  Seite {page+1}: nicht erreichbar"); break

        new_count = 0
        for m in art_pat.finditer(html):
            art_id, art_url = int(m.group(1)), m.group(0)
            if art_url not in seen and id_from <= art_id <= id_to:
                seen.add(art_url); urls.append(art_url); new_count += 1

        msg_ids = [int(x) for x in msg_pat.findall(html)]
        if not msg_ids: print(f"  Seite {page+1}: keine weiteren Posts"); break

        min_id = min(msg_ids)
        print(f"  Seite {page+1} (vor #{before_id or 'aktuell'}): {new_count} neue Links, Posts bis #{min_id}")

        if len(urls) >= MAX_ARTS: print(f"  Maximum erreicht"); break
        if min_id <= 1: print("  Kanalanfang erreicht"); break
        if min_id == before_id: print("  Keine Änderung – stoppe"); break

        before_id = min_id
        time.sleep(0.6)

    print(f"  Telegram gesamt: {len(urls)} Artikel-Links")
    return sorted(urls)

def get_urls_by_id(from_date, to_date):
    id_from = max(1, interpolate_id(from_date) - 10)
    id_to   = interpolate_id(to_date) + 10
    print(f"  ID-Range Fallback: {id_from}–{id_to} ({id_to-id_from+1} Kandidaten)")
    return [f"{BASE_URL}/aktuelles/pressemitteilungen/{i:06d}/index.html" for i in range(id_from, id_to+1)]

def parse_article(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title_text = (soup.find("title") or type("",(),{"get_text":lambda *a:""})()).get_text()
    dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title_text)
    if not dm or "München" not in title_text: return []
    pm_date = datetime(int(dm[3]),int(dm[2]),int(dm[1]))
    for tag in soup(["nav","header","footer","script","style"]): tag.decompose()
    content = soup.find(class_="c-richtext") or soup.find("article") or soup.find("main")
    if not content: return []
    incidents = []
    sections = content.find_all("h3")
    if not sections:
        body = content.get_text(" ", strip=True)
        if len(body) < 50: return []
        kat, sev = categorize(body)
        dm2 = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", body)
        inc_date = datetime(int(dm2[3]),int(dm2[2]),int(dm2[1])) if dm2 else pm_date
        tm = re.search(r"(\d{1,2})[:.h](\d{2})\s*Uhr", body)
        return [_make(inc_date, f"{int(tm[1]):02d}:{tm[2]}" if tm else "", "", kat, sev, detect_ort(body), body[:120], body[:1500], url)]
    for h in sections:
        heading = h.get_text(" ", strip=True)
        num_m = re.match(r"^(\d+)\.\s+", heading)
        nr = num_m[1] if num_m else ""
        titel = re.sub(r"^\d+\.\s+", "", heading).strip()
        ort_m = re.search(r"–\s*(.+)$", titel)
        ort_raw = ort_m[1].strip() if ort_m else ""
        ort = detect_ort(ort_raw) if ort_raw else "Unbekannt"
        parts = []
        for sib in h.find_next_siblings():
            if sib.name in ("h3","h2","hr"): break
            parts.append(sib.get_text(" ", strip=True))
        body = " ".join(parts).strip()
        if len(body) < 30: continue
        dm2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", body)
        inc_date = datetime(int(dm2[3]),int(dm2[2]),int(dm2[1])) if dm2 else pm_date
        tm = re.search(r"(\d{1,2})[:.h](\d{2})\s*Uhr", body)
        kat, sev = categorize(titel+" "+body)
        if ort == "Unbekannt": ort = detect_ort(body)
        incidents.append(_make(inc_date, f"{int(tm[1]):02d}:{tm[2]}" if tm else "", nr, kat, sev, ort, titel[:120], body[:1500], url))
    return incidents

def _make(dt, time_str, nr, kat, sev, ort, titel, volltext, link):
    return {"date":dt.strftime("%d.%m.%Y"),"dateSort":dt.strftime("%Y-%m-%d"),"time":time_str,
            "nr":nr,"kategorie":kat,"schweregrad":sev,"ort":ort,"titel":titel,"volltext":volltext,"link":link}

def main():
    to_date   = datetime.now().replace(hour=23,minute=59,second=59)
    from_date = (to_date - timedelta(days=DAYS_BACK)).replace(hour=0,minute=0,second=0)
    print(f"═══════════════════════════════════════════")
    print(f"  PP München OSINT Scraper")
    print(f"  Zeitraum: {from_date.date()} → {to_date.date()}")
    print(f"═══════════════════════════════════════════")

    urls = get_urls_from_telegram(from_date, to_date)
    if not urls:
        print("Telegram leer – verwende ID-Range als Fallback")
        urls = get_urls_by_id(from_date, to_date)
    urls = urls[:MAX_ARTS]
    print(f"\n  Verarbeite {len(urls)} Artikel…\n")

    all_incidents, loaded = [], 0
    for i, url in enumerate(urls):
        art_id = url.split("/")[-2]
        print(f"  [{i+1:3d}/{len(urls)}] {art_id}", end=" … ")
        html = fetch(url)
        if not html or len(html) < 300: print("leer"); continue
        if "München" not in html[:4000]: print("kein PP München"); continue
        soup_q = BeautifulSoup(html[:2000],"html.parser")
        t = (soup_q.find("title") or type("",(),{"get_text":lambda *a:""})()).get_text()
        dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", t)
        if dm:
            ad = datetime(int(dm[3]),int(dm[2]),int(dm[1]))
            if ad < from_date or ad > to_date: print(f"außerhalb ({ad.date()})"); continue
        incidents = parse_article(html, url)
        if incidents: print(f"✓ {len(incidents)} Vorfälle"); all_incidents.extend(incidents); loaded += 1
        else: print("✗ keine Vorfälle")
        time.sleep(SLEEP_SEC)

    Path("data").mkdir(exist_ok=True)
    all_incidents.sort(key=lambda x:(x["dateSort"],x["time"]),reverse=True)
    seen, deduped = set(), []
    for inc in all_incidents:
        key = f"{inc.get('dateSort','')}|{inc.get('titel','')[:60]}|{inc.get('nr','')}"
        if key not in seen: seen.add(key); deduped.append(inc)
    all_incidents = deduped
    print(f"\n  Nach Deduplizierung: {len(all_incidents)} Vorfälle")

    with open("data/incidents.json","w",encoding="utf-8") as f:
        json.dump(all_incidents,f,ensure_ascii=False,indent=2)
    meta = {"updated":datetime.now().strftime("%d.%m.%Y %H:%M"),"updated_iso":datetime.now().isoformat(),
            "from_date":from_date.strftime("%Y-%m-%d"),"to_date":to_date.strftime("%Y-%m-%d"),
            "articles":loaded,"incidents":len(all_incidents)}
    with open("data/meta.json","w",encoding="utf-8") as f:
        json.dump(meta,f,ensure_ascii=False,indent=2)
    print(f"  ✅ {loaded} Artikel · {len(all_incidents)} Vorfälle")
    print(f"     → data/incidents.json ({os.path.getsize('data/incidents.json')//1024} KB)")

if __name__ == "__main__":
    main()
