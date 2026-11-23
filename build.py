"""Verwerkt de bronbestanden in bron/ tot de site in site/.
Controleert de data eerst; bij een verdachte uitkomst stopt de build en blijft de vorige versie online."""
import csv, datetime as dt, html, json, os, pathlib, re, sys, unicodedata
from collections import defaultdict

BRON = pathlib.Path("bron")
SITE = pathlib.Path("site")
BASIS = os.environ.get("BASIS", "https://infectieziekten-nl.pages.dev").rstrip("/")
NAAM = "Infectieziekten in Nederland"
VANDAAG = dt.date.today()
MAAND = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]


def fout(msg):
    print("DATACHECK MISLUKT:", msg, file=sys.stderr)
    sys.exit(1)


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def maandag(yw):  # "2026-W46" -> date
    y, w = yw.split("-W")
    return dt.date.fromisocalendar(int(y), int(w), 1)


def datum_nl(d):
    return f"{d.day} {MAAND[d.month - 1]} {d.year}"


def wk_nl(d):
    y, w, _ = d.isocalendar()
    return f"week {w} van {y}"


def f1(v):
    return "–" if v is None else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def f0(v):
    return "–" if v is None else f"{v:,.0f}".replace(",", ".")


def in_zin(t):
    """ziektenaam midden in een zin: 'Mazelen' -> 'mazelen', maar TBC, Q-koorts en Creutzfeldt-Jakob blijven"""
    return " ".join(w[0].lower() + w[1:] if len(w) > 1 and w[0].isupper() and w[1].islower() and not re.search(r"-[A-Z]", w) else w for w in t.split(" "))


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


# ---------------------------------------------------------------- ERVISS (ECDC)
def erviss(bestand, filter_fn, sleutel_fn):
    uit = defaultdict(dict)
    with open(BRON / bestand, newline="") as f:
        for r in csv.DictReader(f):
            if r["countryname"] != "Netherlands" or not filter_fn(r):
                continue
            v = num(r["value"])
            if v is not None:
                uit[maandag(r["yearweek"])][sleutel_fn(r)] = v
    return uit


sentinel = erviss("sentinel.csv", lambda r: r["age"] == "total" and r["pathogen"] == r["pathogentype"] and r["indicator"] in ("positivity", "tests"),
                  lambda r: (r["pathogen"], r["indicator"]))
lab = erviss("lab.csv", lambda r: r["age"] == "total" and r["indicator"] == "detections", lambda r: (r["pathogen"], r["pathogentype"]))
huisarts = erviss("huisarts.csv", lambda r: True, lambda r: (r["indicator"][:3], r["age"]))


def lab_totaal(d, p):
    if (p, p) in d:
        return d[(p, p)]
    deel = [v for (pp, t), v in d.items() if pp == p]
    return sum(deel) if deel else None


# ---------------------------------------------------------------- RIVM
def rivm(bestand):
    with open(BRON / bestand, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


radar = defaultdict(list)
for r in rivm("radar_ari.csv"):
    v = num(r["Perc_ARI_symptoms"])
    if v is not None:
        d = dt.date.fromisoformat(r["Date_of_statistics"])
        radar[d - dt.timedelta(days=d.weekday())].append(v)
radar = {d: sum(v) / len(v) for d, v in radar.items() if len(v) == 7}

radar_covid = {}
for r in rivm("radar_covid.csv"):
    v = num(r["Perc_covid_test_positive"])
    if v is not None:
        radar_covid[dt.date.fromisoformat(r["Date_of_statistics"])] = v

riool = {}  # dagwaarden zoals het RIVM ze publiceert
for r in rivm("riool.csv"):
    v = num(r["RNA_flow_per_100000"])
    if v is not None:
        riool[dt.date.fromisoformat(r["Date_measurement"])] = v / 1e12

# meldingsplichtige ziekten (tabel op rivm.nl)
VOETNOOT = {"1": "Alleen meldingsplichtig in Caribisch Nederland.", "2": "Meldingsplichtig sinds 1 juli 2019.",
            "3": "Meldingsplichtig bij kinderen geboren vanaf 2006; sinds 1 april 2021 ook bij 60-plussers.",
            "4": "Meldingsplichtig van 28 januari 2020 tot 1 juli 2023.", "5": "Meldingsplichtig sinds 22 mei 2022.",
            "6": "Moeder en kind tellen samen als één infectie.", "7": "Meldingsplichtig sinds 1 maart 2025; 2023 en 2024 zijn vrijwillige meldingen."}
SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
RIVM_PAGINA = {
    "COVID-19": "https://www.rivm.nl/coronavirus-covid-19", "MERS-CoV": "https://www.rivm.nl/mers", "Pokken": "https://www.rivm.nl/pokken",
    "Polio": "https://www.rivm.nl/polio", "Severe Acute Respiratory Syndrome": "https://www.rivm.nl/sars", "Virale hemorragische koorts": "https://www.rivm.nl/ebola",
    "Difterie": "https://www.rivm.nl/difterie", "Humane infectie met dierlijk influenzavirus": "https://www.rivm.nl/vogelgriep", "Mpox": "https://www.rivm.nl/mpox",
    "Pest": "https://www.rivm.nl/pest", "Rabiës": "https://www.rivm.nl/rabies", "TBC": "https://www.rivm.nl/tuberculose",
    "Buiktyfus": "https://lci.rivm.nl/richtlijnen/paratyfus", "Cholera": "https://www.rivm.nl/cholera", "Clusters van voedselinfecties": "https://www.rivm.nl/voedselinfecties",
    "Hepatitis A": "https://www.rivm.nl/hepatitis-a", "Hepatitis B Acuut": "https://www.rivm.nl/hepatitis", "Hepatitis B Chronisch": "https://www.rivm.nl/hepatitis",
    "Hepatitis C Acuut": "https://www.rivm.nl/hepatitis", "Hepatitis C Chronisch": "https://www.rivm.nl/hepatitis", "Kinkhoest": "https://www.rivm.nl/kinkhoest",
    "Mazelen": "https://www.rivm.nl/mazelen", "Paratyfus A": "https://lci.rivm.nl/richtlijnen/paratyfus", "Paratyfus B": "https://lci.rivm.nl/richtlijnen/paratyfus",
    "Paratyfus C": "https://lci.rivm.nl/richtlijnen/paratyfus", "Rubella": "https://www.rivm.nl/rodehond", "Shigellose": "https://www.rivm.nl/shigellose",
    "STEC": "https://www.rivm.nl/stec-ehec", "Antrax": "https://www.rivm.nl/antrax", "Bof": "https://www.rivm.nl/bof", "Botulisme": "https://www.rivm.nl/botulisme",
    "Brucellose": "https://www.rivm.nl/brucellose", "Chikungunya": "https://www.rivm.nl/chikungunya", "Dengue": "https://www.rivm.nl/dengue",
    "Gele Koorts": "https://www.rivm.nl/gele-koorts", "Invasieve pneumokokkenziekte": "https://www.rivm.nl/pneumokokken", "Legionellose": "https://www.rivm.nl/legionella",
    "Leptospirose": "https://www.rivm.nl/leptospirose", "Listeriose": "https://www.rivm.nl/listeriose", "Malaria": "https://www.rivm.nl/malaria",
    "Meningokokkenziekte": "https://www.rivm.nl/meningokokken", "MRSA": "https://www.rivm.nl/mrsa", "Orthohantavirusinfectie": "https://www.rivm.nl/hantavirus",
    "Psittacose/zoönotische chlamydia-infecties": "https://lci.rivm.nl/richtlijnen/psittacose", "Q-koorts": "https://www.rivm.nl/q-koorts",
    "Tekenencefalitis": "https://www.rivm.nl/tekenencefalitis", "Tetanus": "https://www.rivm.nl/tetanus", "Tularemie": "https://www.rivm.nl/tularemie",
    "Ziekte van Creutzfeldt-Jakob": "https://lci.rivm.nl/richtlijnen/creutzfeldt-jakob", "Zika": "https://www.rivm.nl/zikavirus",
}
OVERZICHT = "https://www.rivm.nl/meldingsplicht-infectieziekten/overzicht-meldingen"
GROEP_UITLEG = {"A2": "groep A", "B1": "groep B1", "B2": "groep B2", "C": "groep C"}

s = (BRON / "meldingen.html").read_text(encoding="utf-8")
tabellen = re.findall(r"<table.*?</table>", s, re.S)
if not tabellen:
    fout("geen tabel gevonden op de RIVM-pagina met meldingen")
selectiedatum = re.search(r"selectiedatum\s+([\d-]+)", html.unescape(re.sub(r"<[^>]+>", " ", s)))
selectiedatum = selectiedatum.group(1) if selectiedatum else None
ziekten, jaren, groep = [], None, None
for tr in re.findall(r"<tr.*?</tr>", tabellen[0], re.S):
    c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
    if not c:
        continue
    if c[0] == "":
        jaren = [int(j) for j in c[1:]]
        continue
    if len(c) == 1:
        groep = c[0].replace("GROEP ", "").strip()
        continue
    ruw = c[0].translate(SUP)
    m = re.match(r"^(.*?[A-Za-zë\)])(\d)?$", ruw)
    naam, noot = (m.group(1), m.group(2)) if m and not ruw.startswith("COVID") else (ruw, None)
    if ruw.startswith("COVID-19"):
        naam, noot = "COVID-19", ruw[8:] or None
    kort = naam.split(" (")[0].strip()
    waarden = dict(zip(jaren, [int(x) for x in c[1:]]))
    ziekten.append(dict(naam=naam, kort=kort, slug=slug(kort), groep=groep, noot=VOETNOOT.get(noot or "", ""),
                        jaren={j: waarden[j] for j in sorted(waarden)}, rivm=RIVM_PAGINA.get(kort) or RIVM_PAGINA.get(naam)))


# rioolwater per zuiveringsinstallatie (RIVM) + locaties (Rijkswaterstaat) + provincies (CBS/PDOK)
locaties = {}
with open(BRON / "rwzi_locaties.csv", newline="", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        lat, lon = num(r.get("uwwlatitude")), num(r.get("uwwlongitude"))
        code = re.sub(r"\D", "", r.get("uwwcode", ""))[-5:]
        if lat and lon and code:
            locaties[code] = (lon, lat)
PROV = json.load(open("provincies.json"))["provincies"]


def in_poly(x, y, pts):
    binnen = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            binnen = not binnen
        j = i
    return binnen


def provincie_van(lon, lat):
    for p in PROV:
        if any(in_poly(lon, lat, poly) for poly in p["polys"]):
            return p["naam"]
    # net buiten de vereenvoudigde kustlijn: dichtstbijzijnde provincie
    return min(PROV, key=lambda p: min((lon - x) ** 2 + (lat - y) ** 2 for poly in p["polys"] for x, y in poly))["naam"]


per_rwzi = defaultdict(list)
namen = {}
for r in rivm("riool_rwzi.csv"):
    v = num(r["RNA_flow_per_100000"])
    if v is not None:
        per_rwzi[r["RWZI_AWZI_code"]].append((dt.date.fromisoformat(r["Date_measurement"]), v / 1e12))
        namen[r["RWZI_AWZI_code"]] = r["RWZI_AWZI_name"]
riool_eind = max(d for m in per_rwzi.values() for d, _ in m)
n_gemeten = sum(1 for m in per_rwzi.values() if any((riool_eind - d).days < 28 for d, _ in m))
zuiveringen = []
for code, metingen in per_rwzi.items():
    nu = [v for d, v in metingen if (riool_eind - d).days < 14]
    toen = [v for d, v in metingen if 14 <= (riool_eind - d).days < 28]
    sleutel = code.zfill(5)  # RIVM schrijft codes zonder voorloopnul, Rijkswaterstaat met
    if not nu or not toen or sleutel not in locaties:
        continue
    a, b = sum(nu) / len(nu), sum(toen) / len(toen)
    lon, lat = locaties[sleutel]
    zuiveringen.append(dict(code=code, naam=namen[code], lon=lon, lat=lat, prov=provincie_van(lon, lat), nu=a, toen=b,
                            groei=(a / b - 1) * 100 if b > 0 else None))

# jaren waarin de ziekte niet meldingsplichtig was, volgens de voetnoten van het RIVM.
# Een 0 in die jaren betekent "niet bijgehouden", niet "geen gevallen".
MELDPLICHT = {"COVID-19": (2020, 2023), "Mpox": (2022, None), "CPE": (2019, None), "Tekenencefalitis": (2023, None)}
for z in ziekten:
    van, tot = MELDPLICHT.get(z["kort"], (None, None))
    z["niet"] = {j for j, v in z["jaren"].items() if v == 0 and ((van and j < van) or (tot and j > tot))}
    z["gemeld"] = {j: v for j, v in z["jaren"].items() if j not in z["niet"]}

# ---------------------------------------------------------------- datacheck
def laatste(reeks):
    return max(reeks) if reeks else None


for naam, reeks, max_oud in [("peilstations (ECDC)", sentinel, 35), ("laboratoria (ECDC)", lab, 35), ("huisartsen (ECDC)", huisarts, 35),
                             ("Infectieradar klachten", radar, 21), ("Infectieradar covidtests", radar_covid, 21), ("rioolwater", riool, 21)]:
    if len(reeks) < 100:  # rioolwater: dagen, de rest: weken
        fout(f"{naam}: maar {len(reeks)} weken")
    if (VANDAAG - laatste(reeks)).days > max_oud:
        fout(f"{naam}: laatste week {laatste(reeks)} is ouder dan {max_oud} dagen")
if len(zuiveringen) < 110:
    fout(f"rioolwaterkaart: maar {len(zuiveringen)} zuiveringen met metingen in de laatste vier weken")
if (VANDAAG - riool_eind).days > 21:
    fout(f"rioolwater per zuivering: laatste meting {riool_eind} is te oud")
if len(ziekten) < 50 or not jaren or len(jaren) < 5:
    fout(f"meldingstabel: {len(ziekten)} ziekten, jaren {jaren}")
if len({z['slug'] for z in ziekten}) != len(ziekten):
    fout("dubbele slugs in de meldingstabel")
for z in ziekten:
    if any(v < 0 for v in z["jaren"].values()):
        fout(f"negatief aantal bij {z['naam']}")
for d, v in sentinel.items():
    for (p, i), x in v.items():
        if i == "positivity" and not 0 <= x <= 100:
            fout(f"positiviteit {p} {d}: {x}")

# ---------------------------------------------------------------- reeksen
def reeks(bron, fn):
    return [[d.isoformat(), round(fn(v), 3)] for d, v in sorted(bron.items()) if fn(v) is not None]


def opt(d, k):
    return d.get(k)


R = {
    "griep_pos": reeks(sentinel, lambda v: v.get(("Influenza", "positivity"))),
    "rsv_pos": reeks(sentinel, lambda v: v.get(("RSV", "positivity"))),
    "covid_pos": reeks(sentinel, lambda v: v.get(("SARS-CoV-2", "positivity"))),
    "monsters": reeks(sentinel, lambda v: v.get(("Influenza", "tests"))),
    "griep_lab": reeks(lab, lambda v: lab_totaal(v, "Influenza")),
    "rsv_lab": reeks(lab, lambda v: lab_totaal(v, "RSV")),
    "covid_lab": reeks(lab, lambda v: lab_totaal(v, "SARS-CoV-2")),
    "ili": reeks(huisarts, lambda v: v.get(("ILI", "total"))),
    "ari": reeks(huisarts, lambda v: v.get(("ARI", "total"))),
    "ari_0_4": reeks(huisarts, lambda v: v.get(("ARI", "0-4"))),
    "ari_5_14": reeks(huisarts, lambda v: v.get(("ARI", "5-14"))),
    "ari_15_64": reeks(huisarts, lambda v: v.get(("ARI", "15-64"))),
    "ari_65": reeks(huisarts, lambda v: v.get(("ARI", "65+"))),
    "radar": reeks(radar, lambda v: v),
    "radar_covid": reeks(radar_covid, lambda v: v),
    "riool": reeks(riool, lambda v: v),
}


def drie_weken(p):
    """aandeel positief over de week zelf en de twee weken ervoor: alle positieve monsters / alle geteste monsters"""
    uit = []
    for d in sorted(sentinel):
        weken = [sentinel.get(d - dt.timedelta(days=7 * i), {}) for i in range(3)]
        if not all((p, "positivity") in w and (p, "tests") in w for w in weken):
            continue
        tests = sum(w[(p, "tests")] for w in weken)
        if tests:
            uit.append([d.isoformat(), round(sum(w[(p, "positivity")] * w[(p, "tests")] / 100 for w in weken) / tests * 100, 2)])
    return uit


R["griep_pos3"], R["covid_pos3"], R["rsv_pos3"] = drie_weken("Influenza"), drie_weken("SARS-CoV-2"), drie_weken("RSV")


def jaar_eerder(k):
    return [[(dt.date.fromisoformat(d) + dt.timedelta(days=364)).isoformat(), v] for d, v in R[k]]


R["griep_lab_vj"], R["riool_vj"] = jaar_eerder("griep_lab"), jaar_eerder("riool")


def stand(k):
    """laatste waarde, de waarde precies 7 dagen eerder en de datum"""
    r = R[k]
    a = r[-1]
    week_eerder = (dt.date.fromisoformat(a[0]) - dt.timedelta(days=7)).isoformat()
    b = dict(r).get(week_eerder)
    return dict(d=dt.date.fromisoformat(a[0]), v=a[1], vorig=b)


def seizoen_van(d):
    y, w, _ = d.isocalendar()
    start = y if w >= 40 else y - 1
    return start


def seizoen_index(d):
    start = seizoen_van(d)
    return (d - dt.date.fromisocalendar(start, 40, 1)).days // 7


def zelfde_moment_vorig_seizoen(k):
    """waarde op hetzelfde punt in het vorige seizoen"""
    s0 = stand(k)
    idx, sz = seizoen_index(s0["d"]), seizoen_van(s0["d"])
    for d, v in R[k]:
        d = dt.date.fromisoformat(d)
        if seizoen_van(d) == sz - 1 and seizoen_index(d) == idx:
            return v
    return None


def seizoenpiek(k, sz):
    p = [(v, d) for d, v in R[k] if seizoen_van(dt.date.fromisoformat(d)) == sz]
    return max(p) if p else None


def verschil_pp(a, b):
    if b is None:
        return ""
    d = a - b
    if abs(d) < 0.05:
        return "gelijk aan de week ervoor"
    return f"{'+' if d > 0 else '−'}{f1(abs(d))} procentpunt ten opzichte van de week ervoor"


def verschil_pct(a, b):
    if not b:
        return ""
    d = (a - b) / b * 100
    if abs(d) < 0.5:
        return "gelijk aan de week ervoor"
    return f"{'+' if d > 0 else '−'}{f0(abs(d))}% ten opzichte van de week ervoor"


def richting(a, b, drempel):
    if b is None:
        return "flat"
    return "up" if a - b > drempel else "down" if b - a > drempel else "flat"


G, P, RV, C = stand("griep_pos"), stand("griep_pos"), stand("rsv_pos"), stand("covid_pos")
RI, RA, RC, AR = stand("riool"), stand("radar"), stand("radar_covid"), stand("ari")
huidig_sz = seizoen_van(G["d"])
SZ_NAAM = lambda s: f"{s}/{str(s + 1)[2:]}"


# ---------------------------------------------------------------- rioolwaterkaart (statische SVG)
KLASSEN = [(-25, "down", "Daalt (meer dan 25% minder)"), (25, "gelijk", "Ongeveer gelijk (tot 25% verschil)"),
           (100, "stijgt", "Stijgt (25 tot 100% meer)"), (1e9, "sterk", "Stijgt sterk (meer dan verdubbeld)")]


def klasse(g):
    if g is None:
        return "gelijk"
    return next(k for grens, k, _ in KLASSEN if g < grens)


def kaart_svg(breed=520):
    lon0, lon1, lat0, lat1 = 3.3, 7.25, 50.72, 53.58
    kx = 0.613  # cos(52,2°): lengtegraden zijn in Nederland korter dan breedtegraden
    sc = breed / ((lon1 - lon0) * kx)
    hoog = round((lat1 - lat0) * sc)
    P = lambda lon, lat: ((lon - lon0) * kx * sc, (lat1 - lat) * sc)
    paden = []
    for p in PROV:
        d = "".join("M" + "L".join(f"{P(x, y)[0]:.1f},{P(x, y)[1]:.1f}" for x, y in poly) + "Z" for poly in p["polys"])
        paden.append(f'<path d="{d}" class="prov"><title>{html.escape(p["naam"])}</title></path>')
    mx = max(z["nu"] for z in zuiveringen) or 1
    stippen = []
    for z in sorted(zuiveringen, key=lambda z: -z["nu"]):
        x, y = P(z["lon"], z["lat"])
        r = 3 + 11 * (z["nu"] / mx) ** 0.5
        g = "onbekend" if z["groei"] is None else ("+" if z["groei"] >= 0 else "−") + f0(abs(z["groei"])) + "%"
        stippen.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" class="st {klasse(z["groei"])}"><title>{html.escape(z["naam"])} ({html.escape(z["prov"])}): {g} · {f0(z["nu"])} biljoen deeltjes per 100.000 inwoners</title></circle>')
    return (f'<svg class="nlkaart" viewBox="0 0 {breed} {hoog}" role="img" aria-label="Kaart van Nederland met de verandering van coronavirus in het rioolwater per zuiveringsinstallatie">'
            + "".join(paden) + "".join(stippen) + "</svg>")


def kaart_legenda():
    return '<div class="legend">' + "".join(f'<span><i class="dotk {k}"></i>{t}</span>' for _, k, t in KLASSEN) + "<span>Grotere stip = meer virus</span></div>"


telling = {k: sum(1 for z in zuiveringen if klasse(z["groei"]) == k) for _, k, _ in KLASSEN}
n_stijg = telling["stijgt"] + telling["sterk"]
venster = f"{datum_nl(riool_eind - dt.timedelta(days=13))} t/m {datum_nl(riool_eind)}"
kaart_zin = (f"Bij <b>{n_stijg} van de {len(zuiveringen)}</b> rioolwaterzuiveringen zat er de afgelopen twee weken meer coronavirus in het water dan in de twee weken daarvoor; "
             f"bij {telling['sterk']} is het meer dan verdubbeld. Bij {telling['down']} daalt het.")

per_prov = defaultdict(list)
for z in zuiveringen:
    per_prov[z["prov"]].append(z)
prov_rijen = []
for naam, zz in sorted(per_prov.items(), key=lambda kv: -sum(z["nu"] for z in kv[1]) / sum(z["toen"] for z in kv[1]) if sum(z["toen"] for z in kv[1]) else 0):
    nu, toen = sum(z["nu"] for z in zz) / len(zz), sum(z["toen"] for z in zz) / len(zz)
    g = (nu / toen - 1) * 100 if toen else None
    st = sum(1 for z in zz if klasse(z["groei"]) in ("stijgt", "sterk"))
    prov_rijen.append(f'<tr><td>{html.escape(naam)}</td><td class="num"><span class="chg {"up" if g and g > 25 else "down" if g and g < -25 else ""}">{"+" if (g or 0) >= 0 else "−"}{f0(abs(g or 0))}%</span></td><td class="num">{st} van {len(zz)}</td><td class="num">{f0(nu)}</td></tr>')
prov_tabel = f"""<details class="onder"><summary>Per provincie</summary><div class="scroll"><table>
<thead><tr><th>Provincie</th><th class="num">Verandering</th><th class="num">Zuiveringen met stijging</th><th class="num">Biljoen deeltjes (gem.)</th></tr></thead><tbody>{"".join(prov_rijen)}</tbody></table></div>
<p class="uitleg">Verandering = gemiddelde van de zuiveringen in de provincie, laatste twee weken tegenover de twee weken daarvoor. Niet gewogen naar inwoners.</p></details>"""

BRON_KAART = ('<a href="https://data.rivm.nl/data/covid-19/COVID-19_rioolwaterdata.csv">RIVM, rioolwater per zuivering</a> · locaties: '
              '<a href="https://data.overheid.nl/dataset/48818-richtlijn-stedelijk-afvalwater---rioolwaterzuiveringsinstallaties-nederland-eu2024">Rijkswaterstaat</a> · grenzen: CBS/PDOK')


def kaart_blok(gid):
    return f"""<figure class="card fig" id="{gid}">
<h3>Waar groeit corona? Rioolwater per zuivering</h3>
<p class="uitleg">Elke stip is een rioolwaterzuivering. De kleur laat zien hoe de hoeveelheid virus veranderde: de laatste twee weken ({venster}) tegenover de twee weken daarvoor. Het RIVM meet elke week bij ongeveer {n_gemeten} zuiveringen; {len(zuiveringen)} hebben in beide periodes een meting en staan op de kaart. Eén losse meting schommelt sterk, daarom vergelijkt de kaart twee weken met twee weken.</p>
{kaart_legenda()}
<div class="kaartbox">{kaart_svg()}</div>
<figcaption class="meta">Bron: {BRON_KAART}</figcaption>
</figure>"""


# ---------------------------------------------------------------- luchtweginfecties per GGD-regio (Nivel)
def xlsx_blad(pad, blad):
    """Leest één werkblad uit een .xlsx als lijst van rijen (alleen stdlib)."""
    import zipfile, xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    z = zipfile.ZipFile(pad)
    gedeeld = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            gedeeld.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next(sh.get("{%s}id" % ns["r"]) for sh in wb.find("m:sheets", ns) if sh.get("name") == blad)
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    doel = next(r.get("Target") for r in rels if r.get("Id") == rid).lstrip("/")
    doel = doel if doel.startswith("xl/") else "xl/" + doel
    rijen = []
    for rij in ET.fromstring(z.read(doel)).iter("{%s}row" % ns["m"]):
        cellen = {}
        for c in rij.findall("m:c", ns):
            kol = 0
            for ch in re.match(r"[A-Z]+", c.get("r")).group():
                kol = kol * 26 + ord(ch) - 64
            v = c.find("m:v", ns)
            if c.get("t") == "s" and v is not None:
                w = gedeeld[int(v.text)]
            elif c.get("t") == "inlineStr":
                w = "".join(t.text or "" for t in c.iter("{%s}t" % ns["m"]))
            elif v is not None:
                w = float(v.text)
            else:
                w = None
            cellen[kol - 1] = w
        rijen.append([cellen.get(i) for i in range(max(cellen, default=-1) + 1)])
    return rijen


def nivel_per_ggd():
    """{'weken': [46, 45, 44] (nieuwste eerst), 'jaar': 2026, 'ggd': {naam: [w46, w45, w44]}, 'praktijken': {naam: n}}"""
    pad = BRON / "nivel_ggd.xlsx"
    if not pad.exists():
        return None
    rijen = xlsx_blad(pad, "ARI")
    kop = next(r for r in rijen if "week" in r)
    kolommen = [(i, int(r)) for i, (w, r) in enumerate(zip(kop, kop[1:])) if w == "week"]
    uit = {"weken": [w for _, w in kolommen], "ggd": {}}
    for r in rijen:
        if r and isinstance(r[0], str) and r[0] not in ("GGD",) and len(r) > kolommen[0][0] and (r[kolommen[0][0]] is None or isinstance(r[kolommen[0][0]], float)):
            uit["ggd"][r[0].strip()] = [r[i] if i < len(r) else None for i, _ in kolommen]
    pop = xlsx_blad(pad, "Populatie")
    uit["praktijken"] = {r[0].strip(): int(r[2] or 0) for r in pop if r and isinstance(r[0], str) and len(r) > 2 and isinstance(r[2], float)}
    m = re.search(r"(\d{4})", " ".join(str(c) for r in xlsx_blad(pad, "Voorblad") for c in r if c))
    uit["jaar"] = int(m.group(1)) if m else dt.date.today().year
    if "Nederland" not in uit["ggd"] or len(uit["ggd"]) < 20:
        fout(f"Nivel-bestand per GGD: onverwachte opbouw ({len(uit['ggd'])} regio's)")
    return uit


NIV = nivel_per_ggd()
GGD = json.load(open("ggd.json"))["regios"]
ARI_KLASSEN = [(-15, "laag", "Lager dan landelijk (meer dan 15% minder)"), (15, "gelijk", "Rond het landelijk gemiddelde"),
               (35, "hoger", "Hoger (15 tot 35% meer)"), (1e9, "hoogst", "Veel hoger (meer dan 35% meer)")]


def ggd_kort(naam):
    return re.sub(r"^GGD ", "", naam)


def ari_gem(waarden):
    w = [v for v in waarden if v is not None]
    return sum(w) / len(w) if len(w) == len(waarden) else None


if NIV:
    ARI_NL = ari_gem(NIV["ggd"]["Nederland"])
    ARI_REGIO = {}
    for g in GGD:
        k = ggd_kort(g["naam"])
        rij = NIV["ggd"].get(k)
        gem = ari_gem(rij) if rij else None
        ARI_REGIO[g["naam"]] = {"kort": k, "gem": gem, "weken": rij or [None] * 3, "praktijken": NIV["praktijken"].get(k, 0),
                               "afwijking": (gem / ARI_NL - 1) * 100 if gem is not None and ARI_NL else None}
    onbekend = [k for k in NIV["ggd"] if k != "Nederland" and k not in {ggd_kort(g["naam"]) for g in GGD}]
    if onbekend:
        fout(f"Nivel-regio's zonder kaartvlak: {onbekend}")
    ARI_WEKEN = f"week {NIV['weken'][-1]} t/m {NIV['weken'][0]}"


def ari_klasse(a):
    return "geen" if a is None else next(k for grens, k, _ in ARI_KLASSEN if a < grens)


def ari_kaart_svg(breed=520):
    lon0, lon1, lat0, lat1 = 3.3, 7.25, 50.72, 53.58
    kx = 0.613
    sc = breed / ((lon1 - lon0) * kx)
    hoog = round((lat1 - lat0) * sc)
    P = lambda lon, lat: ((lon - lon0) * kx * sc, (lat1 - lat) * sc)
    paden = []
    for g in GGD:
        a = ARI_REGIO[g["naam"]]
        d = "".join("M" + "L".join(f"{P(x, y)[0]:.1f},{P(x, y)[1]:.1f}" for x, y in poly) + "Z" for poly in g["polys"])
        if a["gem"] is None:
            t = f"{a['kort']}: geen cijfers (te weinig deelnemende huisartsen)"
        else:
            wk = ", ".join(f"week {w}: {f0(v)}" for w, v in zip(NIV["weken"], a["weken"]))
            t = f"{a['kort']}: gemiddeld {f0(a['gem'])} per 100.000 ({'+' if a['afwijking'] >= 0 else '−'}{f0(abs(a['afwijking']))}% t.o.v. landelijk) · {wk} · {a['praktijken']} praktijken"
        paden.append(f'<path d="{d}" class="ggd {ari_klasse(a["afwijking"])}"><title>{html.escape(t)}</title></path>')
    return (f'<svg class="nlkaart" viewBox="0 0 {breed} {hoog}" role="img" aria-label="Kaart van Nederland met huisartsbezoek voor luchtweginfecties per GGD-regio, vergeleken met het landelijk gemiddelde">'
            + "".join(paden) + "</svg>")


BRON_NIVEL = ('<a href="https://www.nivel.nl/nl/zorg-en-ziekte-in-cijfers/actuele-cijfers-ziekten-per-week">Nivel Zorgregistraties Eerste Lijn</a>, cijfers per GGD-regio · grenzen: CBS/PDOK')


def ari_kaart_blok(gid, titel="Luchtweginfecties per regio"):
    if not NIV:
        return ""
    met = [a for a in ARI_REGIO.values() if a["gem"] is not None]
    zonder = sorted(a["kort"] for a in ARI_REGIO.values() if a["gem"] is None)
    hoogst = max(met, key=lambda a: a["gem"])
    laagst = min(met, key=lambda a: a["gem"])
    rijen = "".join(
        f'<tr><td>{html.escape(a["kort"])}</td>' + "".join(f'<td class="num">{f0(v) if v is not None else "–"}</td>' for v in a["weken"])
        + f'<td class="num">{a["praktijken"]}</td></tr>'
        for a in sorted(ARI_REGIO.values(), key=lambda a: -(a["gem"] or -1)))
    nl = NIV["ggd"]["Nederland"]
    return f"""<figure class="card fig" id="{gid}">
<h3>{titel}</h3>
<p class="uitleg">Hoeveel mensen gingen per 100.000 inwoners naar de huisarts met een acute luchtweginfectie, gemiddeld over {ARI_WEKEN}? De kleur vergelijkt elke GGD-regio met het landelijk gemiddelde van {f0(ARI_NL)}. Het hoogst is {html.escape(hoogst["kort"])} ({f0(hoogst["gem"])}), het laagst {html.escape(laagst["kort"])} ({f0(laagst["gem"])}).</p>
<p class="uitleg">Dit zijn alle luchtweginfecties samen: griep, covid, RSV en verkoudheid. Welk virus erachter zit, wordt alleen landelijk gemeten. Per regio doen soms maar een handvol huisartspraktijken mee, dus één week kan flink schommelen; daarom drie weken gemiddeld.{(" Geen cijfers voor " + " en ".join(zonder) + ": daar doen te weinig praktijken mee.") if zonder else ""}</p>
<div class="legend">{"".join(f'<span><i class="vlak {k}"></i>{t}</span>' for _, k, t in ARI_KLASSEN)}<span><i class="vlak geen"></i>Geen cijfers</span></div>
<div class="kaartbox">{ari_kaart_svg()}</div>
<details class="onder"><summary>Per GGD-regio</summary><div class="scroll"><table>
<thead><tr><th>GGD-regio</th>{"".join(f'<th class="num">Week {w}</th>' for w in NIV["weken"])}<th class="num">Praktijken</th></tr></thead><tbody>{rijen}
<tr><td><b>Nederland</b></td>{"".join(f'<td class="num"><b>{f0(v)}</b></td>' for v in nl)}<td class="num">{NIV["praktijken"].get("Nederland", "")}</td></tr></tbody></table></div>
<p class="uitleg">Huisartsbezoek voor een acute luchtweginfectie per 100.000 inwoners per week. Voorlopige cijfers; het Nivel herberekent ze na afloop van het jaar.</p></details>
<figcaption class="meta">Bron: {BRON_NIVEL}</figcaption>
</figure>"""



# ---------------------------------------------------------------- HTML
KLEUR = {"griep": "var(--griep)", "covid": "var(--covid)", "rsv": "var(--rsv)", "ari": "var(--ari)", "grijs": "var(--grijs)"}
pagina_lijst = []
NAV = f"""<nav class="top"><div class="in"><a class="logo" href="/">{NAAM}</a>
<a href="/griep/">Griep</a><a href="/covid/">Covid</a><a href="/rsv/">RSV</a><a href="/luchtwegklachten/">Luchtwegklachten</a><a href="/meldingsplichtige-ziekten/">Meldingsplichtige ziekten</a><a href="/over/">Over</a></div></nav>"""
STAND = max(G["d"], RA["d"])


# Op het eigen domein: bezoekers van pages.dev en www doorsturen naar dezelfde pagina op BASIS.
DOORSTUUR = "" if BASIS.endswith(".pages.dev") else (
    f'\n<script>if (/(\\.pages\\.dev|^www\\.)/.test(location.hostname)) location.replace("{BASIS}" + location.pathname + location.search + location.hash);</script>')


def kop(titel, beschrijving, pad, og, ld_extra=()):
    url = BASIS + pad
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": titel, "description": beschrijving, "url": url, "inLanguage": "nl",
           "dateModified": VANDAAG.isoformat(), "isPartOf": {"@type": "WebSite", "name": NAAM, "url": BASIS + "/"}}, *ld_extra]
    e = html.escape
    return f"""<title>{e(titel)}</title>
<meta name="description" content="{e(beschrijving)}">{DOORSTUUR}
<script>if (/(^|\\.)(infectiebron\\.nl|infectieziekten-nl\\.pages\\.dev)$/.test(location.hostname)) {{ const s = document.createElement("script"); s.defer = true; s.src = "https://static.cloudflareinsights.com/beacon.min.js"; s.dataset.cfBeacon = '{{"token": "5b281c2234df4b768c5f6aec5b0ac3f6"}}'; document.head.appendChild(s); }}</script>
<link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:locale" content="nl_NL"><meta property="og:site_name" content="{NAAM}">
<meta property="og:title" content="{e(titel)}"><meta property="og:description" content="{e(beschrijving)}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{BASIS}/og/{og}.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="{NAAM}: weekoverzicht" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400..700;1,7..72,400..700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="/stijl.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>"""


def schrijf(pad, titel, beschrijving, inhoud, grafieken, og="home", ld_extra=(), kruimel=None):
    k = ""
    if kruimel:
        k = f'<div class="breadcrumb"><a href="/">{NAAM}</a>' + "".join(f' › <a href="{u}">{html.escape(t)}</a>' if u else f" › {html.escape(t)}" for t, u in kruimel) + "</div>"
        crumbs = [{"@type": "ListItem", "position": 1, "name": NAAM, "item": BASIS + "/"}] + [
            {"@type": "ListItem", "position": i + 2, "name": t, "item": BASIS + (u or pad)} for i, (t, u) in enumerate(kruimel)]
        ld_extra = [*ld_extra, {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": crumbs}]
    data = json.dumps(grafieken, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    t = f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{kop(titel, beschrijving, pad, og, ld_extra)}
</head>
<body>
{NAV}
<main>
{k}
{inhoud}
<footer>
<p>Bronnen: <a href="https://erviss.org">ECDC ERVISS</a> (cijfers van RIVM en Nivel) · <a href="https://data.rivm.nl/">RIVM open data</a> · <a href="{OVERZICHT}">RIVM meldingsplichtige ziekten</a> · <a href="/over/">Werkwijze</a> · <a href="https://github.com/erikotn/infectieziekten-nl">Code</a></p>
<p>Deze site geeft geen medisch advies. Bij klachten: neem contact op met je huisarts. Bijgewerkt op {datum_nl(VANDAAG)}.</p>
<p class="hoekje">Een hoekje van <a href="https://erikmeijerink.nl">erikmeijerink.nl</a></p>
</footer>
</main>
<script>window.G={data};</script>
<script src="/grafiek.js"></script>
</body>
</html>"""
    doel = SITE / pad.strip("/") / "index.html" if pad != "/" else SITE / "index.html"
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_text(t)
    pagina_lijst.append(dict(pad=pad, og=og))


def grafiek(gid, titel, uitleg, bron_html, legenda=(), hoog=False):
    leg = "".join(f'<span><i class="sw" style="background:{k}"></i>{html.escape(n)}</span>' for n, k in legenda)
    return f"""<figure class="card fig" id="{gid}">
<h3>{titel}</h3>
<p class="uitleg">{uitleg}</p>
{f'<div class="legend">{leg}</div>' if leg else ''}
<div class="chart{' hoog' if hoog else ''}" data-g="{gid}" role="img" aria-label="{html.escape(titel)}"></div>
<figcaption class="meta">Bron: {bron_html}</figcaption>
</figure>"""


def lijn_cfg(series, fmt, vanaf=None, y0=True):
    out = []
    for item in series:
        naam, k, kleur = item[:3]
        pts = [p for p in R[k] if not vanaf or p[0] >= vanaf]
        soort = item[3] if len(item) > 3 else ""
        out.append(dict(naam=naam, kleur=kleur, p=pts, dun=soort == "dun", vj=soort == "vj"))
    return dict(t="lijn", s=out, fmt=fmt, y0=y0, dag=all(item[1] == "riool" for item in series))


def tot_nu(cfg):
    """vorig-jaarlijn niet verder laten lopen dan de laatste datum van dit jaar"""
    eind = max(p[0] for s_ in cfg["s"] if not s_["vj"] for p in s_["p"])
    for s_ in cfg["s"]:
        if s_["vj"]:
            s_["p"] = [p for p in s_["p"] if p[0] <= eind]
    return cfg


def seizoen_cfg(k, kleur, fmt, n=4):
    per = defaultdict(list)
    for d, v in R[k]:
        dd = dt.date.fromisoformat(d)
        per[seizoen_van(dd)].append([seizoen_index(dd), v, d])
    sz = sorted(per)[-n:]
    return dict(t="seizoen", fmt=fmt, s=[dict(naam=SZ_NAAM(s), kleur=kleur if s == sz[-1] else "var(--grijs)", nu=s == sz[-1], p=per[s]) for s in sz])


def tabel_laatste(kolommen, n=12):
    """kolommen: [(kop, reeks-sleutel, formatter)]"""
    alle = sorted({d for _, k, _ in kolommen for d, _ in R[k]})[-n:]
    idx = {k: dict(R[k]) for _, k, _ in kolommen}
    rijen = "".join("<tr><td>" + wk_nl(dt.date.fromisoformat(d)) + "</td>" + "".join(
        f'<td class="num">{fm(idx[k].get(d))}</td>' for _, k, fm in kolommen) + "</tr>" for d in reversed(alle))
    return f"""<details class="onder"><summary>De cijfers van de laatste {n} weken</summary><div class="scroll"><table>
<thead><tr><th>Week</th>{''.join(f'<th class="num">{html.escape(h)}</th>' for h, _, _ in kolommen)}</tr></thead><tbody>{rijen}</tbody></table></div></details>"""


def tegel(label, waarde, zin, cls, href=None, kleur=None):
    tag = f'a href="{href}"' if href else "div"
    end = "a" if href else "div"
    rand = f' style="border-top-color:{kleur}"' if kleur else ""
    return f'<{tag} class="tegel"{rand}><div class="t">{label}</div><div class="g">{waarde}</div><div class="chg {cls}">{zin}</div></{end}>'


BRON_PEIL = '<a href="https://erviss.org">ECDC ERVISS</a>, huisartsenpeilstations (Nivel en RIVM)'
BRON_LAB = '<a href="https://erviss.org">ECDC ERVISS</a>, laboratoriumuitslagen buiten de peilstations (RIVM)'
BRON_HA = '<a href="https://erviss.org">ECDC ERVISS</a>, huisartsconsulten (Nivel)'
BRON_RADAR = '<a href="https://www.infectieradar.nl/">Infectieradar</a> (RIVM), <a href="https://data.rivm.nl/data/covid-19/ARI_Infectieradar_symptomen_per_dag.csv">open data</a>'
BRON_RADAR_C = '<a href="https://www.infectieradar.nl/">Infectieradar</a> (RIVM), <a href="https://data.rivm.nl/data/covid-19/COVID-19_infectieradar_positieve_testuitslagen_per_week.csv">open data</a>'
BRON_RIOOL = '<a href="https://www.rivm.nl/corona/actueel">RIVM rioolwatermetingen</a>, <a href="https://data.rivm.nl/data/covid-19/COVID-19_rioolwaterdata_landelijk.csv">open data</a>'
PCT = "pct"
EEN_JAAR = (G["d"] - dt.timedelta(days=371)).isoformat()
TWEE_JAAR = (G["d"] - dt.timedelta(days=735)).isoformat()


def vorig_seizoen_zin(k, naam):
    v = zelfde_moment_vorig_seizoen(k)
    return f" Op hetzelfde moment vorig seizoen was dat {f1(v)}%." if v is not None else ""


# zinnen
def drie(k):
    """laatste 3-weekgemiddelde en de waarde drie weken eerder"""
    r = R[k + "_pos3"]
    d = dt.date.fromisoformat(r[-1][0])
    return r[-1][1], dict(r).get((d - dt.timedelta(days=21)).isoformat()), d


def drie_zin(k, ziekte):
    nu, toen, d = drie(k)
    return (f"Gemiddeld over de drie weken tot en met {wk_nl(d)} testte <b>{f1(nu)}%</b> van de monsters bij huisartsen positief op {ziekte}"
            + (f" (drie weken eerder: {f1(toen)}%)." if toen is not None else ".") + vorig_seizoen_zin(k + "_pos3", ziekte))


griep_zin = drie_zin("griep", "griep")
rsv_zin = drie_zin("rsv", "RSV")
covid_zin = (f"Op {datum_nl(RI['d'])} zaten er gemiddeld <b>{f0(RI['v'])} biljoen</b> coronavirusdeeltjes in het rioolwater per 100.000 inwoners ({verschil_pct(RI['v'], RI['vorig']).replace('de week ervoor', 'een week eerder')}). "
             f"Bij huisartsen testte gemiddeld over de laatste drie weken {f1(drie('covid')[0])}% van de monsters positief op covid.")
radar_zin = f"In {wk_nl(RA['d'])} meldde <b>{f1(RA['v'])}%</b> van de deelnemers aan Infectieradar klachten van een luchtweginfectie ({verschil_pp(RA['v'], RA['vorig'])})."

# ---------------------------------------------------------------- inzicht: fase, seizoenspositie, buurlanden, historie
# Alles met vaste regels; de drempels staan ook op /over/.
STIJG, DAAL = 1.15, 0.87          # verandering over drie weken: >15% erbij = stijgt, >13% eraf = daalt
NIVEAU_GRENZEN = [(50, "laag"), (80, "gemiddeld"), (95, "hoog"), (101, "zeer hoog")]   # percentiel van de eigen historie


def tot(k, cutoff):
    return [p for p in R[k] if p[0] <= cutoff] if cutoff else R[k]


def gem_venster(punten, eind, dagen):
    """gemiddelde van de punten in (eind - dagen, eind]"""
    e = dt.date.fromisoformat(eind)
    v = [x for d, x in punten if 0 <= (e - dt.date.fromisoformat(d)).days < dagen]
    return sum(v) / len(v) if v else None


def signaal(naam, k, soort, cutoff=None):
    """richting van één signaal over drie weken. soort: 'glad' (al een 3-weekgemiddelde), 'week' (3 weken tegen 3 weken), 'dag' (7 dagen tegen 7 dagen, 3 weken eerder)"""
    p = tot(k, cutoff)
    if len(p) < 8:
        return None
    eind = p[-1][0]
    eerder = (dt.date.fromisoformat(eind) - dt.timedelta(days=21)).isoformat()
    if soort == "glad":
        nu, toen = p[-1][1], dict(p).get(eerder)
    elif soort in ("week", "pctweek"):
        nu, toen = gem_venster(p, eind, 21), gem_venster(p, eerder, 21)
    else:
        nu, toen = gem_venster(p, eind, 7), gem_venster(p, eerder, 7)
    if nu is None or not toen:
        return None
    r = nu / toen
    # kleine aantallen: een verschil moet ook in absolute zin iets voorstellen
    min_abs = {"glad": 1.0, "week": 20, "pctweek": 0.1, "dag": 5}[soort]
    beweegt = abs(nu - toen) >= min_abs
    richting = ("stijgt" if r > STIJG else "daalt" if r < DAAL else "gelijk") if beweegt else "gelijk"
    return dict(naam=naam, richting=richting, verandering=(r - 1) * 100, nu=nu, toen=toen, soort=soort)


def niveau(k, cutoff=None, seizoensgebonden=False):
    """seizoensgebonden (griep, RSV): huidige stand als deel van de gemiddelde piek van eerdere seizoenen.
    anders (covid): percentiel van alle weken sinds het begin van de reeks."""
    p = tot(k, cutoff)
    nu = p[-1][1]
    if seizoensgebonden:
        sz_nu = seizoen_van(dt.date.fromisoformat(p[-1][0]))
        pieken = defaultdict(float)
        for d, v in p:
            sz = seizoen_van(dt.date.fromisoformat(d))
            if sz < sz_nu:
                pieken[sz] = max(pieken[sz], v)
        if pieken:
            deel = 100 * nu / (sum(pieken.values()) / len(pieken))
            return ("laag" if deel < 10 else "gemiddeld" if deel < 40 else "hoog" if deel < 80 else "zeer hoog"), deel
    alle = sorted(v for _, v in p)
    pct = 100 * sum(1 for v in alle if v < nu) / len(alle)
    return next(n for g, n in NIVEAU_GRENZEN if pct < g), pct


SIGNALEN = {
    "griep": [("Labuitslagen", "griep_lab", "week"), ("Huisartsmonsters", "griep_pos3", "glad")],
    "covid": [("Rioolwater", "riool", "dag"), ("Labuitslagen", "covid_lab", "week"), ("Huisartsmonsters", "covid_pos3", "glad"), ("Infectieradar-tests", "radar_covid", "pctweek")],
    "rsv": [("Labuitslagen", "rsv_lab", "week"), ("Huisartsmonsters", "rsv_pos3", "glad")],
}
NIVEAU_REEKS = {"griep": "griep_pos3", "covid": "riool", "rsv": "rsv_pos3"}
ZNAAM = {"griep": "Griep", "covid": "Covid", "rsv": "RSV"}


def fase(ziekte, cutoff=None):
    sig = [s for s in (signaal(n, k, soort, cutoff) for n, k, soort in SIGNALEN[ziekte]) if s]
    if not sig:
        return None
    n, op, af = len(sig), sum(s["richting"] == "stijgt" for s in sig), sum(s["richting"] == "daalt" for s in sig)
    niv, pct = niveau(NIVEAU_REEKS[ziekte], cutoff, seizoensgebonden=ziekte in ("griep", "rsv"))
    if op > n / 2:
        f, cls = ("Hoog en stijgend" if niv in ("hoog", "zeer hoog") else "Begint op te lopen" if niv == "laag" else "Stijgend"), "up"
    elif af > n / 2:
        f, cls = ("Laag en dalend" if niv == "laag" else "Dalend"), "down"
    else:
        f, cls = ("Hoog" if niv in ("hoog", "zeer hoog") else "Rustig" if niv == "laag" else "Stabiel"), "flat"
    eens = f"{op} van de {n} signalen stijgen" if cls == "up" else f"{af} van de {n} signalen dalen" if cls == "down" else f"signalen wijzen niet één kant op ({op} omhoog, {af} omlaag)"
    return dict(ziekte=ziekte, fase=f, cls=cls, eens=eens, niveau=niv, pct=pct, signalen=sig)


def fase_pill(fz):
    return f'<span class="fase {fz["cls"]}">{fz["fase"]}</span><span class="eens">{fz["eens"]}</span>' if fz else ""


def waarde_tekst(s):
    fm = {"glad": lambda v: f1(v) + "%", "pctweek": lambda v: f1(v) + "%", "week": lambda v: f0(v) + " per week", "dag": lambda v: f0(v) + " biljoen"}[s["soort"]]
    return f"{fm(s['toen'])} → {fm(s['nu'])}"


def signalen_blok(fz):
    if not fz:
        return ""
    pijl = {"stijgt": "↑", "daalt": "↓", "gelijk": "→"}
    rijen = "".join(f'<li><span class="pijl {s["richting"]}">{pijl[s["richting"]]}</span><b>{s["naam"]}</b> {s["richting"]} '
                    f'<span class="meta">({waarde_tekst(s)})</span></li>' for s in fz["signalen"])
    return f"""<div class="card signalen"><h3>{ZNAAM[fz['ziekte']]} nu: {fase_pill(fz)}</h3>
<ul>{rijen}</ul>
<p class="uitleg">Elk signaal vergelijkt de laatste drie weken met de drie weken daarvoor: meer dan 15% erbij telt als stijgen, meer dan 13% eraf als dalen, mits het verschil ook in absolute zin iets voorstelt. Het niveau ({fz['niveau']}) {"zet de huidige stand af tegen de gemiddelde piek van eerdere seizoenen" if fz['ziekte'] in ("griep", "rsv") else "vergelijkt de huidige stand met alle metingen sinds 2020"}. <a href="/over/#fase">Hoe het oordeel tot stand komt</a>.</p></div>"""


# --- seizoenspositie (griep en RSV): beschrijft eerdere seizoenen, voorspelt niets
def seizoen_positie(k):
    per = defaultdict(list)
    for d, v in R[k]:
        dd = dt.date.fromisoformat(d)
        per[seizoen_van(dd)].append((seizoen_index(dd), v))
    nu_sz = max(per)
    nu_idx, nu_v = per[nu_sz][-1]
    vorige = [s for s in sorted(per) if s < nu_sz and len(per[s]) >= 45]
    piek_nu = max(per[nu_sz], key=lambda p: p[1])
    week_van = lambda sz, i: (dt.date.fromisocalendar(sz, 40, 1) + dt.timedelta(days=7 * i)).isocalendar()[1]
    if piek_nu[1] >= 3 * max(nu_v, 0.1) and piek_nu[0] < nu_idx - 2:
        return f"De piek van dit seizoen lag in week {week_van(nu_sz, piek_nu[0])} ({f1(piek_nu[1])}%). Sindsdien daalt het."
    if nu_v < 2:   # seizoen nog niet begonnen: wanneer passeerden eerdere seizoenen de 2%?
        starts = [next((i for i, v in per[s] if v >= 2), None) for s in vorige]
        starts = [i for i in starts if i is not None]
        if not starts:
            return ""
        return (f"Het seizoen is nog niet begonnen: het aandeel positieve monsters is {f1(nu_v)}%. In de vorige {len(vorige)} seizoenen kwam het gemiddeld "
                f"rond week {week_van(nu_sz, round(sum(starts) / len(starts)))} boven de 2% (vroegst week {week_van(nu_sz, min(starts))}, laatst week {week_van(nu_sz, max(starts))}).")
    bereikt = []
    for s in vorige:
        reeks = per[s]
        piek = max(reeks, key=lambda p: p[1])
        eerst = next((i for i, v in reeks if v >= nu_v and i <= piek[0]), None)
        if eerst is not None:
            bereikt.append((s, eerst, piek[0] - eerst, piek[1]))
    if not vorige or not bereikt:
        return ""
    gem_week = sum(b[1] for b in bereikt) / len(bereikt)
    verschil = round(gem_week - nu_idx)
    wanneer = ("even vroeg als gemiddeld" if verschil == 0 else f"{abs(verschil)} {'week' if abs(verschil) == 1 else 'weken'} {'eerder' if verschil > 0 else 'later'} dan gemiddeld")
    tot_piek = sorted(b[2] for b in bereikt)
    pieken = sorted(b[3] for b in bereikt)
    return (f"De vorige {len(vorige)} seizoenen ({', '.join(SZ_NAAM(s) for s in vorige)}) bereikten dit niveau ({f1(nu_v)}%) gemiddeld rond week {week_van(nu_sz, round(gem_week))}; "
            f"dit seizoen is dat {wanneer}. Vanaf dit niveau duurde het toen nog {tot_piek[0]} tot {tot_piek[-1]} weken tot de piek, die lag tussen {f0(pieken[0])}% en {f0(pieken[-1])}%. "
            f"Dat beschrijft eerdere seizoenen; een voorspelling voor dit seizoen is het niet.")


# --- historie van het weekoordeel (voor de RSS-feed); staat in data/fases.json in de repo
HIST_PAD = pathlib.Path("data/fases.json")
historie = json.load(open(HIST_PAD)) if HIST_PAD.exists() else {}


def week_sleutel(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_oordeel(cutoff=None):
    uit = {}
    for z in ("griep", "covid", "rsv"):
        fz = fase(z, cutoff)
        if fz:
            uit[z] = dict(fase=fz["fase"], cls=fz["cls"], eens=fz["eens"])
    return uit


laatste_week = max(dt.date.fromisoformat(R["griep_pos"][-1][0]), dt.date.fromisoformat(R["riool"][-1][0]) - dt.timedelta(days=dt.date.fromisoformat(R["riool"][-1][0]).weekday()))
if not historie:   # eerste keer: twaalf weken terug invullen
    for i in range(12, 0, -1):
        d = laatste_week - dt.timedelta(days=7 * i)
        historie[week_sleutel(d)] = week_oordeel((d + dt.timedelta(days=6)).isoformat())
historie[week_sleutel(laatste_week)] = week_oordeel()
FASES = {z: fase(z) for z in ("griep", "covid", "rsv")}


def weken_op_rij(k):
    """hoeveel weken op rij de waarde steeg (+) of daalde (-), telkens vergeleken met 7 dagen eerder"""
    idx = dict(R[k])
    d = dt.date.fromisoformat(R[k][-1][0])
    teken, n = 0, 0
    while True:
        a, b = idx.get(d.isoformat()), idx.get((d - dt.timedelta(days=7)).isoformat())
        if a is None or b is None or a == b:
            break
        t = 1 if a > b else -1
        if teken and t != teken:
            break
        teken, n, d = t, n + 1, d - dt.timedelta(days=7)
    return teken * n


def sinds(k):
    """'hoogste sinds januari 2024' of 'laagste sinds ...', alleen als dat minstens 8 weken terug is"""
    laatste_d, laatste_v = R[k][-1]
    hoger = weken_op_rij(k) >= 0
    for d, v in reversed(R[k][:-1]):
        if (v >= laatste_v) if hoger else (v <= laatste_v):
            dd = dt.date.fromisoformat(d)
            if (dt.date.fromisoformat(laatste_d) - dd).days < 56:
                return ""
            return f"{'hoogste' if hoger else 'laagste'} sinds {MAAND[dd.month - 1]} {dd.year}"
    return f"{'hoogste' if hoger else 'laagste'} sinds het begin van de metingen"


def groei(k):
    """(groot getal, context-regel, css-klasse): procentuele groei t.o.v. 7 dagen eerder, weken op rij, hoogste/laagste sinds"""
    s0 = stand(k)
    if s0["vorig"]:
        d = (s0["v"] - s0["vorig"]) / s0["vorig"] * 100
        groot = "±0%" if abs(d) < 0.5 else f"{'+' if d > 0 else '−'}{f0(abs(d))}%"
    else:
        groot = "–"
    n = weken_op_rij(k)
    delen = [f"{abs(n)}e week op rij {'gestegen' if n > 0 else 'gedaald'}"] if abs(n) >= 2 else []
    z = sinds(k)
    if z:
        delen.append(z)
    return groot, " · ".join(delen), richting(s0["v"], s0["vorig"], (s0["vorig"] or 0) * .005)


KORT_SIG = {"Labuitslagen": "Lab", "Huisartsmonsters": "Huisarts", "Rioolwater": "Riool", "Infectieradar-tests": "Infectieradar"}


def meter(fz):
    """horizontale meter met vier zones en een streep op de huidige stand"""
    if fz["ziekte"] in ("griep", "rsv"):
        grenzen, maxv = [10, 40, 80], 120          # % van de gemiddelde seizoenspiek
        uitleg = f"{f0(fz['pct'])}% van een gemiddelde seizoenspiek"
    else:
        grenzen, maxv = [50, 80, 95], 100          # percentiel van alle rioolwatermetingen
        uitleg = f"hoger dan {f0(fz['pct'])}% van alle metingen sinds 2020"
    randen = [0, *grenzen, maxv]
    v = min(max(fz["pct"], 0), maxv)
    i = next(j for j in range(4) if v < randen[j + 1] or j == 3)
    pos = (i + (v - randen[i]) / (randen[i + 1] - randen[i])) * 25   # vier even brede zones; streep binnen de zone naar rato
    zones = "".join(f'<span class="z z{j}"></span>' for j in range(4))
    return f"""<div class="meter" role="img" aria-label="Niveau {fz['niveau']}: {uitleg}">
<div class="balk">{zones}<span class="streep" style="left:{min(pos, 99):.1f}%"></span></div>
<div class="schaal"><span>laag</span><span>gemiddeld</span><span>hoog</span><span>zeer hoog</span></div>
</div>
<div class="niv">Niveau: <b>{fz['niveau']}</b> · {uitleg}</div>"""


def kort_kaart(z):
    fz = FASES[z]
    n = len(fz["signalen"])
    op = sum(s["richting"] == "stijgt" for s in fz["signalen"])
    af = sum(s["richting"] == "daalt" for s in fz["signalen"])
    groot, onder = (f"{op}/{n}", "signalen stijgen") if fz["cls"] == "up" else (f"{af}/{n}", "signalen dalen") if fz["cls"] == "down" else (f"{n - op - af}/{n}", "signalen stabiel")
    pijl = {"stijgt": "↑", "daalt": "↓", "gelijk": "→"}
    chips = "".join(f'<span class="chip {s["richting"]}" title="{html.escape(s["naam"])}: {waarde_tekst(s)}">{pijl[s["richting"]]} {KORT_SIG[s["naam"]]}</span>' for s in fz["signalen"])
    return f"""<a class="kort-kaart" href="/{z}/" style="--k:{KLEUR[z]}">
<div class="kop"><span class="naam">{ZNAAM[z]}</span><span class="fase {fz['cls']}">{fz['fase']}</span></div>
<div class="getal">{groot}<span>{onder}</span></div>
{meter(fz)}
<div class="chips">{chips}</div>
</a>"""


def weekoverzicht():
    vorige = sorted(historie)[-2] if len(historie) > 1 else None
    nu_k = sorted(historie)[-1]
    veranderd = [f"{ZNAAM[z]} van {historie[vorige][z]['fase'].lower()} naar {historie[nu_k][z]['fase'].lower()}"
                 for z in ("griep", "covid", "rsv") if vorige and z in historie[vorige] and z in historie[nu_k] and historie[vorige][z]["fase"] != historie[nu_k][z]["fase"]]
    wijziging = ("Veranderd sinds vorige week: " + "; ".join(veranderd) + ".") if veranderd else "Geen veranderingen ten opzichte van vorige week."
    return f"""<section class="kort" id="deze-week" aria-label="Deze week in het kort">
<h2><small>Deze week in het kort · {wk_nl(laatste_week)}</small>Hoe staat het ervoor?</h2>
<div class="kort-grid">{"".join(kort_kaart(z) for z in ("griep", "covid", "rsv") if FASES[z])}</div>
<p class="meta">{wijziging} Signalen: verandering over drie weken. <a href="/over/#fase">Zo werkt het oordeel</a> · <a href="/feed.xml">volg via RSS</a></p>
</section>"""


def duo_kaart(soort, titel, href, groot, eenheid, context, cls, oms, tweede, mini_id):
    return f"""<a class="duo-kaart" href="{href}" style="--k:{KLEUR[soort]}">
<div class="t">{titel}</div>
<div class="g {cls}">{groot}<span class="e">{eenheid}</span></div>
{f'<div class="groei">{context}</div>' if context else ''}
<div class="oms">{oms}</div>
<div class="minileg"><span><i class="sw" style="background:var(--k)"></i>dit jaar</span><span><i class="sw" style="background:var(--grijs)"></i>een jaar eerder</span></div>
<div class="chart mini" data-g="{mini_id}" role="img" aria-label="{titel}, laatste jaar, met een jaar eerder ter vergelijking"></div>
<div class="tweede">{tweede}</div>
<div class="naar">Alle {titel.lower()}cijfers →</div>
</a>"""


def duo_home():
    GL = stand("griep_lab")
    MON = stand("monsters")
    pos = round(G["v"] * MON["v"] / 100) if MON["d"] == G["d"] else None
    g_groot, g_ctx, g_cls = groei("griep_lab")
    c_groot, c_ctx, c_cls = groei("riool")
    huisarts = f"Huisarts: <b>{f1(R['griep_pos3'][-1][1])}%</b> van de monsters positief op griep, gemiddeld over de laatste drie weken"
    g_oms = f"Positieve griepuitslagen uit laboratoria: <b>{f0(GL['v'])}</b> in {wk_nl(GL['d'])}"
    c_oms = f"Coronavirus in het rioolwater, gemeten op {datum_nl(RI['d'])}"
    c_tweede = f"Huisarts: <b>{f1(R['covid_pos3'][-1][1])}%</b> van de monsters positief op covid, gemiddeld over de laatste drie weken"
    # dezelfde teksten als platte tekst voor de wekelijkse Bluesky-post (meld.py)
    kaal = lambda s: re.sub(r"<[^>]+>", "", s)
    SITE.mkdir(exist_ok=True)
    (SITE / "bluesky.json").write_text(json.dumps({
        "griep": {"groot": g_groot, "maat": "positieve labuitslagen", "context": g_ctx, "oms": kaal(g_oms), "tweede": kaal(huisarts)},
        "covid": {"groot": c_groot, "maat": "virus in het rioolwater", "context": c_ctx, "oms": kaal(c_oms), "tweede": kaal(c_tweede)},
    }, ensure_ascii=False, indent=1))
    return '<div class="duo">' + duo_kaart(
        "griep", "Griep", "/griep/", g_groot, " t.o.v. vorige week", g_ctx, g_cls, g_oms, huisarts, "duo-griep") + duo_kaart(
        "covid", "Covid", "/covid/", c_groot, " t.o.v. vorige week", c_ctx, c_cls, c_oms, c_tweede, "duo-covid") + "</div>"


def tegels_overig():
    return '<div class="tegels klein">' + "".join([
        tegel("RSV · positieve monsters", f1(RV["v"]) + "%", verschil_pp(RV["v"], RV["vorig"]).replace(" ten opzichte van de week ervoor", " t.o.v. vorige week"), richting(RV["v"], RV["vorig"], .05), "/rsv/", KLEUR["rsv"]),
        tegel("Luchtwegklachten · Infectieradar", f1(RA["v"]) + "%", verschil_pp(RA["v"], RA["vorig"]).replace(" ten opzichte van de week ervoor", " t.o.v. vorige week"), richting(RA["v"], RA["vorig"], .05), "/luchtwegklachten/", KLEUR["ari"]),
    ]) + "</div>"


grafieken_home = {
    "duo-griep": tot_nu(lijn_cfg([("Een jaar eerder", "griep_lab_vj", KLEUR["grijs"], "vj"), ("Dit jaar", "griep_lab", KLEUR["griep"])], "int", vanaf=EEN_JAAR)),
    "duo-covid": tot_nu(lijn_cfg([("Een jaar eerder", "riool_vj", KLEUR["grijs"], "vj"), ("Dit jaar", "riool", KLEUR["covid"])], "dec", vanaf=EEN_JAAR)),
    "h-samen": lijn_cfg([("Griep (3 weken)", "griep_pos3", KLEUR["griep"]), ("Covid (3 weken)", "covid_pos3", KLEUR["covid"])], PCT, vanaf=TWEE_JAAR),
    "h-covid-radar": lijn_cfg([("Positieve test", "radar_covid", KLEUR["covid"])], PCT, vanaf=TWEE_JAAR),
    "h-griep": seizoen_cfg("griep_pos", KLEUR["griep"], PCT),
    "h-covid": lijn_cfg([("Rioolwater", "riool", KLEUR["covid"])], "dec", vanaf=TWEE_JAAR),
    "h-rsv": seizoen_cfg("rsv_pos", KLEUR["rsv"], PCT),
    "h-radar": lijn_cfg([("Infectieradar", "radar", KLEUR["ari"])], PCT, vanaf=TWEE_JAAR),
}
JL, JV = max(jaren), max(jaren) - 1
top = sorted([z for z in ziekten if z["kort"] != "COVID-19"], key=lambda z: (-z["jaren"][JL], -z["jaren"][JV]))
grafieken_home["h-meld"] = dict(t="staaf", s=[dict(naam=z["kort"], a=z["jaren"][JV], b=z["jaren"][JL], href=f"/ziekten/{z['slug']}/") for z in top[:10]], la=str(JV), lb=str(JL))

seizoen_leg = lambda kleur: [(f"Seizoen {SZ_NAAM(huidig_sz)}", kleur), ("Eerdere seizoenen", KLEUR["grijs"])]

def drie_weken_zin(k, naam):
    r = R[k + "_pos3"]
    nu, d = r[-1][1], dt.date.fromisoformat(r[-1][0])
    eerder = dict(r).get((d - dt.timedelta(days=21)).isoformat())
    return f"<b>{f1(nu)}%</b> op {naam}" + (f" (drie weken eerder: {f1(eerder)}%)" if eerder is not None else "")


samen_zin = (f"Gemiddeld over de drie weken tot en met {wk_nl(dt.date.fromisoformat(R['griep_pos3'][-1][0]))} testte "
             f"{drie_weken_zin('griep', 'griep')} en {drie_weken_zin('covid', 'covid')} positief.")


inhoud_home = f"""<header>
<h1>Hoeveel griep en corona is er nu?</h1>
<p class="lead">De actuele cijfers over griep en covid in Nederland, plus RSV, luchtwegklachten en alle meldingsplichtige infectieziekten. Elke week bijgewerkt met de officiële cijfers van het RIVM, Nivel en het Europese ECDC.</p>
<p class="meta">Laatste cijfers: {wk_nl(STAND)} · bijgewerkt {datum_nl(VANDAAG)}</p>
</header>
{weekoverzicht()}
{duo_home()}
<section id="samen">
<h2><small>Griep en covid</small>Hoeveel luchtwegklachten komen door griep of covid?</h2>
<p>Huisartsen in de peilstations testen elke week een deel van hun patiënten met luchtwegklachten op griep en op corona. {samen_zin}</p>
{grafiek("h-samen", "Griep en covid bij de huisarts, laatste twee jaar", "Percentage positieve monsters bij de huisartsenpeilstations, gemiddeld over drie weken. Per week worden maar 30 tot 70 monsters getest; het gemiddelde haalt het toeval eruit.", BRON_PEIL, [("Griep", KLEUR["griep"]), ("Covid", KLEUR["covid"])])}
</section>
<section id="griep">
<h2><small>Griep</small>Hoe verloopt dit griepseizoen?</h2>
<p>{seizoen_positie("griep_pos3")}</p>
{grafiek("h-griep", "Griep: dit seizoen naast eerdere seizoenen", "Percentage positieve monsters bij huisartsenpeilstations per week, van week 40 tot week 39.", BRON_PEIL, seizoen_leg(KLEUR["griep"]))}
<p><a href="/griep/">Alle griepcijfers →</a></p>
</section>
<section id="covid">
<h2><small>Covid</small>Hoeveel corona is er nu?</h2>
<p>{covid_zin}</p>
<div class="twee">
{grafiek("h-covid", "Coronavirus in het rioolwater", "Virusdeeltjes per 100.000 inwoners, in biljoenen (10¹²), per dag, laatste twee jaar.", BRON_RIOOL, [("Rioolwater", KLEUR["covid"])])}
{grafiek("h-covid-radar", "Positieve coronatest bij Infectieradar", "Percentage deelnemers met een positieve zelftest of PCR-test, per week, laatste twee jaar.", BRON_RADAR_C, [("Positieve test", KLEUR["covid"])])}
</div>
<p>{kaart_zin}</p>
{kaart_blok("h-kaart")}
<p><a href="/covid/">Alle covidcijfers →</a></p>
</section>
<section id="ook">
<h2><small>Ook gevolgd</small>RSV en luchtwegklachten</h2>
{tegels_overig()}
<div class="twee">
{grafiek("h-rsv", "RSV: dit seizoen naast eerdere seizoenen", "Percentage positieve monsters bij huisartsenpeilstations, week 40 tot week 39.", BRON_PEIL, seizoen_leg(KLEUR["rsv"]))}
{grafiek("h-radar", "Zelf gemelde luchtwegklachten", "Percentage Infectieradar-deelnemers met klachten van een luchtweginfectie, laatste twee jaar.", BRON_RADAR, [("Infectieradar", KLEUR["ari"])])}
</div>
</section>
<section id="meldingsplichtig">
<h2><small>Meldingsplichtige ziekten</small>Welke meldingsplichtige ziekten kwamen het meest voor in {JL}?</h2>
<p>Artsen en laboratoria moeten {len(ziekten)} infectieziekten melden bij de GGD. Dit zijn de tien met de meeste meldingen in {JL}, zonder covid. Klik op een ziekte voor de cijfers sinds {min(jaren)}.</p>
{grafiek("h-meld", f"Meldingen in {JV} en {JL}", "Aantal door het RIVM goedgekeurde meldingen per jaar.", f'<a href="{OVERZICHT}">RIVM, overzicht meldingen</a>', [(str(JV), KLEUR["grijs"]), (str(JL), KLEUR["griep"])], hoog=True)}
<p><a href="/meldingsplichtige-ziekten/">Alle {len(ziekten)} meldingsplichtige ziekten →</a></p>
</section>"""

dataset_ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Infectieziekten in Nederland: wekelijkse cijfers",
              "description": "Wekelijkse cijfers over griep, covid, RSV en luchtwegklachten in Nederland, en jaartotalen van alle meldingsplichtige infectieziekten, samengesteld uit open data van ECDC en RIVM.",
              "url": BASIS + "/", "inLanguage": "nl", "dateModified": VANDAAG.isoformat(), "temporalCoverage": f"2016-01-01/{STAND.isoformat()}",
              "spatialCoverage": {"@type": "Place", "name": "Nederland"},
              "isBasedOn": ["https://github.com/EU-ECDC/Respiratory_viruses_weekly_data", "https://data.rivm.nl/", OVERZICHT,
                            "https://www.nivel.nl/nl/zorg-en-ziekte-in-cijfers/actuele-cijfers-ziekten-per-week"],
              "license": "https://creativecommons.org/licenses/by/4.0/",
              "creator": {"@type": "Person", "name": "Erik Meijerink", "url": "https://erikmeijerink.nl"},
              "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": BASIS + "/data.json"}}
schrijf("/", "Griep en corona in Nederland nu – actuele cijfers",
        f"Hoeveel griep en corona is er nu in Nederland? Griep: {f1(G['v'])}% positieve monsters bij de huisarts. Covid: rioolwater, tests en huisartscijfers. Plus RSV en alle meldingsplichtige ziekten. Stand {wk_nl(STAND)}.",
        inhoud_home, grafieken_home, "home", [dataset_ld])

# ---- griep
gp = seizoenpiek("griep_pos", huidig_sz - 1)
inhoud = f"""<header><h1>Griep in Nederland: hoeveel griep is er nu?</h1>
<p class="lead">{griep_zin}</p>
<p class="meta">Laatste cijfers: {wk_nl(G['d'])}</p></header>
{signalen_blok(FASES["griep"])}
<p>{seizoen_positie("griep_pos3")}</p>
<div class="tegels">
{tegel("Positieve monsters huisarts", f1(drie('griep')[0]) + "%", "gemiddeld over drie weken; drie weken eerder " + f1(drie('griep')[1]) + "%", richting(drie('griep')[0], drie('griep')[1], 1.0), kleur=KLEUR['griep'])}
{tegel("Laboratoriumuitslagen", f0(stand('griep_lab')['v']), "positieve griepuitslagen in " + wk_nl(stand('griep_lab')['d']), "flat", kleur=KLEUR['griep'])}
{tegel(f"Piek seizoen {SZ_NAAM(huidig_sz - 1)}", (f1(gp[0]) + "%") if gp else "–", ("in " + wk_nl(dt.date.fromisoformat(gp[1]))) if gp else "", "flat", kleur=KLEUR['grijs'])}
</div>
{grafiek("griep-seizoen", "Griep: dit seizoen naast eerdere seizoenen", "Percentage positieve monsters bij huisartsenpeilstations. Een griepseizoen loopt van week 40 tot week 39 van het jaar erna.", BRON_PEIL, seizoen_leg(KLEUR['griep']))}
{grafiek("griep-pos", "Aandeel positieve griepmonsters sinds 2022", f"Per week testen huisartsen in de peilstations zo'n {f0(min(v for _, v in R['monsters'][-26:]))} tot {f0(max(v for _, v in R['monsters'][-26:]))} patiënten met luchtwegklachten. Bij zo weinig monsters schommelt het percentage van week tot week.", BRON_PEIL, [("Gemiddelde over 3 weken", KLEUR['griep']), ("Per week (dun)", KLEUR['grijs'])])}
{grafiek("griep-lab", "Positieve griepuitslagen uit laboratoria", "Aantal positieve testen op influenza per week, uit laboratoria buiten de peilstations.", BRON_LAB, [("Griep", KLEUR['griep'])])}
{grafiek("griep-ili", "Huisartsbezoek voor griepachtige klachten", "Consulten voor een griepachtig ziektebeeld (plotseling koorts plus luchtwegklachten) per 100.000 inwoners per week. Nederland stopte met deze reeks na week 9 van 2026; de bredere reeks staat op de pagina luchtwegklachten.", BRON_HA, [("Griepachtig ziektebeeld", KLEUR['griep'])])}
{ari_kaart_blok("griep-kaart", "Griep per regio? Wel: luchtweginfecties per regio")}
{tabel_laatste([("Positief (%)", "griep_pos", f1), ("Monsters", "monsters", f0), ("Lab-uitslagen", "griep_lab", f0)])}
<section><h2>Meer weten over griep</h2><ul>
<li><a href="https://www.rivm.nl/griep-griepprik">RIVM: griep en de griepprik</a></li>
<li><a href="https://www.rivm.nl/luchtweginfecties">RIVM: luchtweginfecties</a> (hoe het RIVM griep en andere luchtweginfecties volgt)</li>
<li><a href="https://erviss.org">ECDC ERVISS</a> (griep in Europa per land)</li></ul></section>"""
schrijf("/griep/", f"Griep in Nederland nu – cijfers {wk_nl(G['d'])}",
        f"Hoeveel griep is er nu? {f1(G['v'])}% van de monsters bij huisartsen testte in {wk_nl(G['d'])} positief op griep. Dit griepseizoen naast eerdere seizoenen, met laboratorium- en huisartscijfers.",
        inhoud, {"griep-seizoen": seizoen_cfg("griep_pos", KLEUR["griep"], PCT, 5), "griep-pos": lijn_cfg([("Griep (3 weken)", "griep_pos3", KLEUR["griep"]), ("Griep per week", "griep_pos", KLEUR["griep"], "dun")], PCT),
                 "griep-lab": lijn_cfg([("Griep", "griep_lab", KLEUR["griep"])], "int"), "griep-ili": lijn_cfg([("Griepachtig ziektebeeld", "ili", KLEUR["griep"])], "dec")},
        "griep", kruimel=[("Griep", None)])

# ---- covid
CL = stand("covid_lab")
inhoud = f"""<header><h1>Corona in Nederland: hoeveel covid is er nu?</h1>
<p class="lead">{covid_zin}</p>
<p class="meta">Laatste meting: {datum_nl(RI['d'])}</p></header>
{signalen_blok(FASES["covid"])}
<div class="tegels">
{tegel("Rioolwater", f0(RI['v']), "biljoen deeltjes per 100.000 op " + datum_nl(RI['d']) + " · " + verschil_pct(RI['v'], RI['vorig']).replace("de week ervoor", "een week eerder"), richting(RI['v'], RI['vorig'], RI['vorig'] * .005 if RI['vorig'] else 0), kleur=KLEUR['covid'])}
{tegel("Positieve monsters huisarts", f1(drie('covid')[0]) + "%", "gemiddeld over drie weken; drie weken eerder " + f1(drie('covid')[1]) + "%", richting(drie('covid')[0], drie('covid')[1], 1.0), kleur=KLEUR['covid'])}
{tegel("Positieve test Infectieradar", f1(RC['v']) + "%", "van de deelnemers · " + wk_nl(RC['d']), richting(RC['v'], RC['vorig'], .05), kleur=KLEUR['covid'])}
{tegel("Laboratoriumuitslagen", f0(CL['v']), "positieve coronatesten in " + wk_nl(CL['d']), "flat", kleur=KLEUR['covid'])}
</div>
<section id="kaart"><h2><small>Per regio</small>Waar groeit corona nu?</h2>
<p>{kaart_zin}</p>
{kaart_blok("covid-kaart")}
{prov_tabel}
</section>
{grafiek("covid-riool-jaar", "Coronavirus in het rioolwater, laatste twee jaar", "Gemiddeld aantal virusdeeltjes per 100.000 inwoners, in biljoenen (10¹²), per dag zoals het RIVM het berekent. Sinds juli 2025 meet het RIVM één keer per week bij ongeveer 40% van de rioolwaterzuiveringen.", BRON_RIOOL, [("Rioolwater", KLEUR['covid'])])}
{grafiek("covid-riool", "Coronavirus in het rioolwater sinds 2020", "Dezelfde reeks vanaf het begin van de metingen in september 2020.", BRON_RIOOL, [("Rioolwater", KLEUR['covid'])])}
{grafiek("covid-pos", "Aandeel positieve coronamonsters bij huisartsen", "Percentage van de monsters uit de huisartsenpeilstations dat positief testte op SARS-CoV-2. De dikke lijn is het gemiddelde over drie weken, de dunne lijn het weekcijfer.", BRON_PEIL, [("Gemiddelde over 3 weken", KLEUR['covid']), ("Per week (dun)", KLEUR['grijs'])])}
{grafiek("covid-radar", "Infectieradar: deelnemers met een positieve coronatest", "Percentage van alle deelnemers die die week een vragenlijst invulden, met een positieve zelftest of PCR-test.", BRON_RADAR_C, [("Positieve test", KLEUR['covid'])])}
{grafiek("covid-lab", "Positieve coronatesten uit laboratoria", "Aantal positieve testen op SARS-CoV-2 per week, uit laboratoria buiten de peilstations. Sinds het einde van het testbeleid wordt veel minder getest; vergelijk vooral recente weken met elkaar.", BRON_LAB, [("Covid", KLEUR['covid'])])}
{tabel_laatste([("Positief huisarts (%)", "covid_pos", f1), ("Infectieradar (%)", "radar_covid", f1), ("Lab-uitslagen", "covid_lab", f0)])}
<section><h2>Meer weten over corona</h2><ul>
<li><a href="https://www.rivm.nl/corona/actueel">RIVM: actuele cijfers over corona</a></li>
<li><a href="https://www.rivm.nl/coronavirus-covid-19">RIVM: coronavirus COVID-19</a></li>
<li><a href="https://www.infectieradar.nl/">Infectieradar</a> (meedoen en de wekelijkse uitkomsten)</li></ul>
<p class="uitleg">Ziekenhuis- en IC-opnames publiceert het RIVM sinds april 2024 niet meer als open data; die staan hier daarom niet.</p></section>"""
schrijf("/covid/", f"Corona in Nederland nu – rioolwater en tests {wk_nl(C['d'])}",
        f"Hoeveel corona is er nu? Rioolwater: {f0(RI['v'])} biljoen virusdeeltjes per 100.000 inwoners op {datum_nl(RI['d'])}. Plus positieve tests bij huisartsen, Infectieradar en laboratoria.",
        inhoud, {"covid-riool-jaar": lijn_cfg([("Rioolwater", "riool", KLEUR["covid"])], "dec", vanaf=TWEE_JAAR),
                 "covid-riool": lijn_cfg([("Rioolwater", "riool", KLEUR["covid"])], "dec"),
                 "covid-pos": lijn_cfg([("Covid (3 weken)", "covid_pos3", KLEUR["covid"]), ("Covid per week", "covid_pos", KLEUR["covid"], "dun")], PCT),
                 "covid-radar": lijn_cfg([("Positieve test", "radar_covid", KLEUR["covid"])], PCT),
                 "covid-lab": lijn_cfg([("Covid", "covid_lab", KLEUR["covid"])], "int")},
        "covid", kruimel=[("Covid", None)])

# ---- RSV
rp = seizoenpiek("rsv_pos", huidig_sz - 1)
inhoud = f"""<header><h1>RS-virus in Nederland: hoeveel RSV is er nu?</h1>
<p class="lead">{rsv_zin} RSV geeft vooral bij baby's en ouderen ernstige klachten.</p>
<p class="meta">Laatste cijfers: {wk_nl(RV['d'])}</p></header>
{signalen_blok(FASES["rsv"])}
<p>{seizoen_positie("rsv_pos3")}</p>
<div class="tegels">
{tegel("Positieve monsters huisarts", f1(drie('rsv')[0]) + "%", "gemiddeld over drie weken; drie weken eerder " + f1(drie('rsv')[1]) + "%", richting(drie('rsv')[0], drie('rsv')[1], 1.0), kleur=KLEUR['rsv'])}
{tegel("Laboratoriumuitslagen", f0(stand('rsv_lab')['v']), "positieve RSV-uitslagen in " + wk_nl(stand('rsv_lab')['d']), "flat", kleur=KLEUR['rsv'])}
{tegel(f"Piek seizoen {SZ_NAAM(huidig_sz - 1)}", (f1(rp[0]) + "%") if rp else "–", ("in " + wk_nl(dt.date.fromisoformat(rp[1]))) if rp else "", "flat", kleur=KLEUR['grijs'])}
</div>
{grafiek("rsv-seizoen", "RSV: dit seizoen naast eerdere seizoenen", "Percentage positieve monsters bij huisartsenpeilstations, van week 40 tot week 39.", BRON_PEIL, seizoen_leg(KLEUR['rsv']))}
{grafiek("rsv-pos", "Aandeel positieve RSV-monsters sinds 2022", "Percentage positieve monsters bij huisartsenpeilstations. De dikke lijn is het gemiddelde over drie weken, de dunne lijn het weekcijfer.", BRON_PEIL, [("Gemiddelde over 3 weken", KLEUR['rsv']), ("Per week (dun)", KLEUR['grijs'])])}
{grafiek("rsv-lab", "Positieve RSV-uitslagen uit laboratoria", "Aantal positieve testen op RSV per week, uit laboratoria buiten de peilstations.", BRON_LAB, [("RSV", KLEUR['rsv'])])}
{tabel_laatste([("Positief (%)", "rsv_pos", f1), ("Lab-uitslagen", "rsv_lab", f0)])}
<section><h2>Meer weten over RSV</h2><ul>
<li><a href="https://www.rivm.nl/rs-virus">RIVM: RS-virus</a></li>
<li><a href="https://www.rivm.nl/rs-virus/stand-van-zaken-rs-virus">RIVM: stand van zaken RS-virus</a></li></ul></section>"""
schrijf("/rsv/", f"RS-virus (RSV) in Nederland nu – cijfers {wk_nl(RV['d'])}",
        f"Hoeveel RSV is er nu? {f1(RV['v'])}% van de monsters bij huisartsen testte in {wk_nl(RV['d'])} positief op het RS-virus. Dit seizoen naast eerdere seizoenen.",
        inhoud, {"rsv-seizoen": seizoen_cfg("rsv_pos", KLEUR["rsv"], PCT, 5), "rsv-pos": lijn_cfg([("RSV (3 weken)", "rsv_pos3", KLEUR["rsv"]), ("RSV per week", "rsv_pos", KLEUR["rsv"], "dun")], PCT),
                 "rsv-lab": lijn_cfg([("RSV", "rsv_lab", KLEUR["rsv"])], "int")},
        "rsv", kruimel=[("RSV", None)])

# ---- luchtwegklachten
inhoud = f"""<header><h1>Luchtwegklachten in Nederland: hoeveel mensen zijn verkouden of grieperig?</h1>
<p class="lead">{radar_zin} Bij de huisarts ging het in {wk_nl(AR['d'])} om {f0(AR['v'])} consulten per 100.000 inwoners voor een acute luchtweginfectie ({verschil_pct(AR['v'], AR['vorig'])}).</p>
<p class="meta">Laatste cijfers: {wk_nl(RA['d'])}</p></header>
{grafiek("lw-radar", "Zelf gemelde luchtwegklachten", "Percentage deelnemers aan Infectieradar met klachten van een acute luchtweginfectie, zoals hoesten, keelpijn of een loopneus, weekgemiddelde sinds november 2020.", BRON_RADAR, [("Infectieradar", KLEUR['ari'])])}
{grafiek("lw-ari", "Huisartsbezoek voor luchtweginfecties per leeftijd", "Consulten voor een acute luchtweginfectie per 100.000 inwoners per week, sinds week 40 van 2025. Jonge kinderen gaan veel vaker naar de huisarts.", BRON_HA,
         [("0–4 jaar", "var(--covid)"), ("5–14 jaar", "var(--rsv)"), ("15–64 jaar", "var(--griep)"), ("65 jaar en ouder", "var(--ari)")])}
{ari_kaart_blok("lw-kaart")}
{tabel_laatste([("Infectieradar (%)", "radar", f1), ("Huisarts totaal", "ari", f0), ("0–4 jaar", "ari_0_4", f0), ("65+", "ari_65", f0)])}
<section><h2>Meer weten</h2><ul>
<li><a href="https://www.infectieradar.nl/">Infectieradar</a>: meld zelf elke week je klachten</li>
<li><a href="https://www.rivm.nl/luchtweginfecties">RIVM: luchtweginfecties</a></li></ul></section>"""
ari_vanaf = "2025-09-29"
schrijf("/luchtwegklachten/", "Luchtwegklachten en verkoudheid in Nederland nu",
        f"Hoeveel mensen hebben nu luchtwegklachten? {f1(RA['v'])}% van de Infectieradar-deelnemers in {wk_nl(RA['d'])}, en huisartsbezoek per leeftijdsgroep.",
        inhoud, {"lw-radar": lijn_cfg([("Infectieradar", "radar", KLEUR["ari"])], PCT),
                 "lw-ari": lijn_cfg([("0–4 jaar", "ari_0_4", "var(--covid)"), ("5–14 jaar", "ari_5_14", "var(--rsv)"), ("15–64 jaar", "ari_15_64", "var(--griep)"), ("65+", "ari_65", "var(--ari)")], "int", vanaf=ari_vanaf)},
        "luchtwegklachten", kruimel=[("Luchtwegklachten", None)])

# ---- meldingsplichtige ziekten
def spark(z):
    return json.dumps([None if j in z["niet"] else z["jaren"][j] for j in sorted(jaren)])


def cel(z, jaar):
    return '<span class="meta" title="niet meldingsplichtig">–</span>' if jaar in z["niet"] else f0(z["jaren"][jaar])

rijen = "".join(f"""<tr><td><a href="/ziekten/{z['slug']}/">{html.escape(z['kort'])}</a></td><td><span class="pill">{z['groep']}</span></td>
<td class="num">{cel(z, JL-2)}</td><td class="num">{cel(z, JV)}</td><td class="num"><b>{cel(z, JL)}</b></td>
<td><span class="spark" data-v='{spark(z)}'></span></td></tr>""" for z in sorted(ziekten, key=lambda z: (-z['jaren'][JL], -z['jaren'][JV])))
stijgers = sorted([z for z in ziekten if z["jaren"][JV] >= 20], key=lambda z: -(z["jaren"][JL] / z["jaren"][JV]))[:3]
dalers = sorted([z for z in ziekten if z["jaren"][JV] >= 20], key=lambda z: z["jaren"][JL] / z["jaren"][JV])[:3]
lijstje = lambda zz: ", ".join(f'<a href="/ziekten/{z["slug"]}/">{html.escape(in_zin(z["kort"]))}</a> ({f0(z["jaren"][JV])} → {f0(z["jaren"][JL])})' for z in zz)
inhoud = f"""<header><h1>Meldingsplichtige infectieziekten in Nederland</h1>
<p class="lead">Van {len(ziekten)} infectieziekten moeten artsen en laboratoria elk geval melden bij de GGD. Het RIVM houdt bij hoe vaak ze voorkomen. Hier staan de aantallen per jaar van {min(jaren)} tot en met {JL}.</p>
<p class="meta">Stand: RIVM, Osiris-AIZ{(", selectiedatum " + selectiedatum) if selectiedatum else ""}</p></header>
<p>De grootste stijgers van {JV} naar {JL}: {lijstje(stijgers)}. De grootste dalers: {lijstje(dalers)}. Alleen ziekten met minstens 20 meldingen in {JV} tellen mee.</p>
{grafiek("meld-top", f"De tien meest gemelde ziekten in {JL}", "Aantal door het RIVM goedgekeurde meldingen per jaar, zonder covid.", f'<a href="{OVERZICHT}">RIVM, overzicht meldingen</a>', [(str(JV), KLEUR['grijs']), (str(JL), KLEUR['griep'])], hoog=True)}
<div class="card"><h3>Alle meldingsplichtige ziekten</h3><p class="uitleg">Gesorteerd op het aantal meldingen in {JL}. De lijntjes lopen van {min(jaren)} tot en met {JL}. Groep A heeft de zwaarste maatregelen, groep C de lichtste. Een streepje betekent dat de ziekte dat jaar niet meldingsplichtig was.</p>
<div class="scroll"><table><thead><tr><th>Ziekte</th><th>Groep</th><th class="num">{JL-2}</th><th class="num">{JV}</th><th class="num">{JL}</th><th>{min(jaren)}–{JL}</th></tr></thead><tbody>{rijen}</tbody></table></div></div>
<p class="uitleg">De aantallen kunnen nog veranderen door late meldingen of als een melding na onderzoek wordt ingetrokken. Een ziekte telt mee in het jaar van de eerste ziektedag.</p>"""
schrijf("/meldingsplichtige-ziekten/", f"Meldingsplichtige infectieziekten in Nederland – aantallen {min(jaren)}–{JL}",
        f"Hoe vaak komen mazelen, kinkhoest, legionella, tuberculose en de andere {len(ziekten)} meldingsplichtige infectieziekten voor in Nederland? Aantallen per jaar van het RIVM, {min(jaren)} tot en met {JL}.",
        inhoud, {"meld-top": grafieken_home["h-meld"]}, "meldingen", kruimel=[("Meldingsplichtige ziekten", None)])

# ---- per ziekte
for z in ziekten:
    j = z["gemeld"]
    naam_z = html.escape(in_zin(z["kort"]))
    hoogste = max(j, key=lambda k: (j[k], k))
    totaal = sum(j.values())
    eerste = min(j)
    if JL in z["niet"]:
        zin = (f"{html.escape(z['kort'])} is niet meer meldingsplichtig, dus het RIVM telt geen meldingen meer. "
               f"In de jaren met meldplicht ({eerste}–{max(j)}) lag het hoogste aantal in {hoogste}: <b>{f0(j[hoogste])}</b> meldingen.")
        if z["kort"] == "COVID-19":
            zin += ' De actuele cijfers over corona, zoals het rioolwater, staan op <a href="/covid/">de covidpagina</a>.'
    else:
        if j.get(JV):
            ver = (j[JL] - j[JV]) / j[JV] * 100
            trend = f"{'meer' if ver > 0 else 'minder'} dan in {JV}, toen waren het er {f0(j[JV])} ({'+' if ver > 0 else '−'}{f0(abs(ver))}%)" if abs(ver) >= 0.5 else f"evenveel als in {JV}"
        else:
            trend = f"in {JV} waren het er 0"
        if totaal == 0:
            zin = f"Het RIVM kreeg tussen {eerste} en {JL} geen enkele melding van {naam_z}."
        else:
            zin = (f"In {JL} kreeg het RIVM <b>{f0(j[JL])} {'melding' if j[JL] == 1 else 'meldingen'}</b> van {naam_z}. Dat is {trend}. "
                   f"Het hoogste aantal sinds {eerste} was {f0(j[hoogste])} in {hoogste}.")
    bronlink = f'<a href="{z["rivm"]}">RIVM-informatie over {html.escape(z["kort"])}</a>' if z["rivm"] else f'<a href="{OVERZICHT}">RIVM, overzicht meldingen</a>'
    tabel = "".join(f'<tr><td>{k}</td><td class="num">{"<span class=meta>niet meldingsplichtig</span>" if k in z["niet"] else f0(v)}</td></tr>' for k, v in sorted(z["jaren"].items(), reverse=True))
    inhoud = f"""<header><h1>{html.escape(z['naam'])} in Nederland: aantal meldingen per jaar</h1>
<p class="lead">{zin}</p>
<p class="meta">{"Niet meer meldingsplichtig" if JL in z["niet"] else "Meldingsplichtig, " + GROEP_UITLEG.get(z['groep'], 'groep ' + z['groep'])} · bron: RIVM</p></header>
{f'<p class="let">Let op: {html.escape(z["noot"])}</p>' if z['noot'] else ''}
{grafiek("ziekte", f"Meldingen van {html.escape(z['kort'])} per jaar, {min(jaren)}–{JL}", "Aantal door het RIVM goedgekeurde meldingen, op het jaar van de eerste ziektedag.", f'<a href="{OVERZICHT}">RIVM, overzicht meldingen</a>')}
<div class="card"><h3>De aantallen</h3><div class="scroll"><table><thead><tr><th>Jaar</th><th class="num">Meldingen</th></tr></thead><tbody>{tabel}</tbody></table></div></div>
<section><h2>Meer weten</h2><ul><li>{bronlink}</li><li><a href="https://lci.rivm.nl/richtlijnen">LCI-richtlijnen infectieziektebestrijding</a> (voor professionals)</li>
<li><a href="/meldingsplichtige-ziekten/">Alle meldingsplichtige ziekten</a></li></ul></section>"""
    schrijf(f"/ziekten/{z['slug']}/", f"{z['kort']} in Nederland – aantal meldingen {min(jaren)}–{JL}",
            (f"Hoe vaak komt {in_zin(z['kort'])} voor in Nederland? {f0(j[JL])} meldingen in {JL}, {f0(j[JV])} in {JV}. Aantallen per jaar van het RIVM sinds {eerste}."
             if JL not in z["niet"] else f"Aantal meldingen van {in_zin(z['kort'])} in Nederland per jaar, {eerste}–{max(j)}, toen de ziekte meldingsplichtig was. Cijfers van het RIVM."),
            inhoud, {"ziekte": dict(t="jaren", s=[[str(k), None if k in z["niet"] else v] for k, v in z["jaren"].items()], kleur=KLEUR["griep"])}, "meldingen",
            kruimel=[("Meldingsplichtige ziekten", "/meldingsplichtige-ziekten/"), (z["kort"], None)])

# ---- over
inhoud = f"""<header><h1>Over deze site</h1>
<p class="lead">Waar de cijfers vandaan komen, wat ze wel en niet zeggen, en hoe vaak ze worden bijgewerkt.</p></header>
<section><h2>Bronnen</h2><ul>
<li><b>Luchtweginfecties per GGD-regio:</b> de wekelijkse regionale tabel van <a href="https://www.nivel.nl/nl/zorg-en-ziekte-in-cijfers/actuele-cijfers-ziekten-per-week">Nivel Zorgregistraties Eerste Lijn</a> (huisartsbezoek voor een acute luchtweginfectie per 100.000 inwoners). Grenzen van de GGD-regio's: CBS via PDOK.</li>
<li><b>Huisartsenpeilstations, laboratoria en huisartsconsulten:</b> de Europese ademhalingsvirussurveillance <a href="https://erviss.org">ERVISS</a> van het <a href="https://www.ecdc.europa.eu/en/publications-data/european-respiratory-virus-surveillance-summary-erviss">ECDC</a>. Het RIVM en Nivel leveren daar elke week de Nederlandse cijfers aan. De bestanden staan op <a href="https://github.com/EU-ECDC/Respiratory_viruses_weekly_data">GitHub</a>.</li>
<li><b>Infectieradar:</b> een wekelijkse vragenlijst van het RIVM waarin deelnemers hun klachten en testuitslagen melden. <a href="https://data.rivm.nl/data/covid-19/">RIVM open data</a>.</li>
<li><b>Rioolwater:</b> het landelijk gemiddelde aantal coronavirusdeeltjes per 100.000 inwoners uit metingen bij rioolwaterzuiveringen. <a href="https://data.rivm.nl/data/covid-19/COVID-19_rioolwaterdata_landelijk.csv">RIVM open data</a>.</li>
<li><b>Meldingsplichtige ziekten:</b> de jaartabel van het RIVM uit het meldsysteem Osiris-AIZ. <a href="{OVERZICHT}">RIVM, overzicht meldingen</a>.</li></ul></section>
<section><h2>Wat de cijfers zeggen</h2><ul>
<li><b>Positieve monsters:</b> huisartsen in de peilstations nemen bij een deel van hun patiënten met luchtwegklachten een monster af. Het percentage positief laat zien hoeveel van die klachten door griep, RSV of corona komen. Het gaat om tientallen monsters per week, dus kleine schommelingen zeggen weinig.</li>
<li><b>Laboratoriumuitslagen:</b> het aantal positieve testen hangt af van hoeveel er getest wordt. Vergelijk vooral weken die dicht bij elkaar liggen.</li>
<li><b>Seizoenen:</b> een griep- of RSV-seizoen loopt van week 40 tot en met week 39 van het jaar erna.</li>
<li><b>Rioolwater</b> zegt iets over de hoeveelheid virus in de bevolking, niet over hoeveel mensen ziek zijn. Sinds juli 2025 meet het RIVM één keer per week bij ongeveer 40% van de zuiveringen.</li>
<li><b>Meldingen</b> tellen alleen gevallen die een arts of laboratorium vaststelde en meldde. Wie niet naar de dokter gaat, telt niet mee.</li></ul></section>
<section id="fase"><h2>Hoe het oordeel per ziekte werkt</h2><ul>
<li><b>Signalen.</b> Griep: labuitslagen en huisartsmonsters. Covid: rioolwater, labuitslagen, huisartsmonsters en positieve tests bij Infectieradar. RSV: labuitslagen en huisartsmonsters.</li>
<li><b>Richting per signaal.</b> De laatste drie weken tegenover de drie weken daarvoor (bij rioolwater: de laatste zeven dagen tegenover zeven dagen, drie weken eerder). Meer dan 15% erbij is stijgen, meer dan 13% eraf is dalen. Het verschil moet ook in absolute zin iets voorstellen: minstens 1 procentpunt bij huisartsmonsters, 0,1 procentpunt bij Infectieradar, gemiddeld 20 uitslagen per week bij laboratoria en 5 biljoen deeltjes bij rioolwater. Anders telt het als gelijk.</li>
<li><b>Niveau.</b> Griep en RSV: de huidige stand als deel van de gemiddelde piek van eerdere seizoenen (onder 10% laag, tot 40% gemiddeld, tot 80% hoog, daarboven zeer hoog). Covid heeft geen vast seizoen: daar telt hoe de rioolwaterstand zich verhoudt tot alle metingen sinds 2020 (onder de helft laag, tot 80% gemiddeld, tot 95% hoog, daarboven zeer hoog).</li>
<li><b>Oordeel.</b> Stijgt meer dan de helft van de signalen, dan is het oordeel stijgend (bij een laag niveau: begint op te lopen, bij een hoog niveau: hoog en stijgend). Daalt meer dan de helft, dan dalend. Anders bepaalt het niveau het oordeel: rustig, stabiel of hoog.</li>
<li><b>Seizoenspositie.</b> Voor griep en RSV staat erbij wanneer eerdere seizoenen hetzelfde niveau bereikten en hoe lang het toen nog tot de piek duurde. Dat beschrijft het verleden en is geen voorspelling.</li></ul></section>
<section><h2>Bijwerken</h2>
<p>Elke dag haalt een script de nieuwste bestanden op. De Europese cijfers komen meestal op vrijdag, de RIVM-cijfers op woensdag. Voor publicatie controleert het script of elke bron recent is, genoeg weken bevat en geen onmogelijke waarden heeft. Klopt iets niet, dan blijft de vorige versie online. Alle berekeningen zijn vaste regels, zonder AI. De verwerkte cijfers staan in <a href="/data.json">data.json</a>.</p></section>
<section><h2>Geen medisch advies</h2><p>Deze site laat cijfers zien en geeft geen medisch advies. Heb je klachten, bel dan je huisarts. Kijk voor adviezen op de sites van het <a href="https://www.rivm.nl/">RIVM</a> en je GGD.</p></section>"""
schrijf("/over/", "Over deze site – bronnen en werkwijze", "Waar de cijfers over griep, covid, RSV en meldingsplichtige ziekten vandaan komen, wat ze zeggen en hoe vaak ze worden bijgewerkt.",
        inhoud, {}, "home", kruimel=[("Over", None)])

# ---- overige bestanden
(SITE / "stijl.css").write_text(open("stijl.css").read())
(SITE / "grafiek.js").write_text(open("grafiek.js").read())
(SITE / "favicon.svg").write_text(open("logo.svg").read())
# Bluesky-handle @infectiebron.nl: bewijs dat het domein bij dit account hoort (werkt zodra het domein naar de site wijst)
(SITE / ".well-known").mkdir(exist_ok=True)
(SITE / ".well-known" / "atproto-did").write_text("did:plc:6pbok5tfywzymbtbw4epiecg")
(SITE / "_headers").write_text("/.well-known/atproto-did\n  Content-Type: text/plain; charset=utf-8\n  Access-Control-Allow-Origin: *\n")
(SITE / "apple-touch-icon.png").write_bytes(open("apple-touch-icon.png", "rb").read())
uitvoer = dict(bijgewerkt=VANDAAG.isoformat(), reeksen=R, meldingen=[dict(ziekte=z["naam"], groep=z["groep"], let_op=z["noot"], jaren=z["jaren"]) for z in ziekten],
               bronnen={"ERVISS": "https://github.com/EU-ECDC/Respiratory_viruses_weekly_data", "RIVM open data": "https://data.rivm.nl/data/covid-19/", "RIVM meldingen": OVERZICHT})
json.dump(uitvoer, open(SITE / "data.json", "w"), ensure_ascii=False, separators=(",", ":"))
(SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                                  "".join(f"  <url><loc>{BASIS}{x['pad']}</loc><lastmod>{VANDAAG.isoformat()}</lastmod></url>\n" for x in pagina_lijst) + "</urlset>\n")
HIST_PAD.parent.mkdir(exist_ok=True)
json.dump(dict(sorted(historie.items())), open(HIST_PAD, "w"), ensure_ascii=False, indent=1)
items = []
weken = sorted(historie)
for i, wk in enumerate(reversed(weken[-26:])):
    h = historie[wk]
    vorig = historie.get(weken[weken.index(wk) - 1]) if weken.index(wk) > 0 else None
    jaar, nr = wk.split("-W")
    titel = f"Week {int(nr)} van {jaar}: " + ", ".join(f"{ZNAAM[z].lower() if z != 'rsv' else 'RSV'} {h[z]['fase'].lower()}" for z in ("griep", "covid", "rsv") if z in h)
    titel = titel[0].upper() + titel[1:]
    wijz = [f"{ZNAAM[z]}: van {vorig[z]['fase'].lower()} naar {h[z]['fase'].lower()}" for z in ("griep", "covid", "rsv") if vorig and z in vorig and z in h and vorig[z]["fase"] != h[z]["fase"]]
    tekst = " ".join(f"{ZNAAM[z]}: {h[z]['fase'].lower()} ({h[z]['eens']})." for z in ("griep", "covid", "rsv") if z in h) + ((" Veranderd: " + "; ".join(wijz) + ".") if wijz else "")
    datum = dt.date.fromisocalendar(int(jaar), int(nr), 7)
    items.append(f"""<item><title>{html.escape(titel)}</title><link>{BASIS}/#deze-week</link><guid isPermaLink="false">{BASIS}/week/{wk}</guid>
<pubDate>{datum.strftime('%a, %d %b %Y')} 12:00:00 +0000</pubDate><description>{html.escape(tekst)}</description></item>""")
(SITE / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{NAAM}: weekoverzicht</title><link>{BASIS}/</link>
<description>Elke week het oordeel over griep, covid en RSV in Nederland, op basis van open data van RIVM, Nivel en ECDC.</description><language>nl</language>
{"".join(items)}
</channel></rss>
""")
(SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASIS}/sitemap.xml\n")
(SITE / "404.html").write_text(f'<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pagina niet gevonden</title><link rel="stylesheet" href="/stijl.css"></head><body>{NAV}<main><h1>Pagina niet gevonden</h1><p><a href="/">Naar de voorpagina</a></p></main></body></html>')
json.dump(pagina_lijst, open(SITE / "paginas.json", "w"))
# vingerafdruk van de cijfers (zonder datum van vandaag), voor de workflow
import hashlib
(SITE / "stand.txt").write_text(hashlib.md5(json.dumps([R, [z["jaren"] for z in ziekten], NIV], sort_keys=True).encode()).hexdigest())
print(f"ok: {len(pagina_lijst)} pagina's · griep {wk_nl(G['d'])} {f1(G['v'])}% · rioolwater {wk_nl(RI['d'])} {f0(RI['v'])} · {len(ziekten)} meldingsplichtige ziekten t/m {JL}")
