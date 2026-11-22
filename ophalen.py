"""Haalt de ruwe bronbestanden op in bron/. Stopt met een fout als een bron niet te bereiken is,
zodat de vorige versie van de site online blijft."""
import datetime as dt, pathlib, sys, urllib.request

BRON = pathlib.Path("bron")
BRON.mkdir(exist_ok=True)
ERVISS = "https://raw.githubusercontent.com/EU-ECDC/Respiratory_viruses_weekly_data/main/data/"
RIVM = "https://data.rivm.nl/data/covid-19/"
BESTANDEN = {
    "sentinel.csv": ERVISS + "sentinelTestsDetectionsPositivity.csv",
    "lab.csv": ERVISS + "nonSentinelTestsDetections.csv",
    "huisarts.csv": ERVISS + "ILIARIRates.csv",
    "radar_ari.csv": RIVM + "ARI_Infectieradar_symptomen_per_dag.csv",
    "radar_covid.csv": RIVM + "COVID-19_infectieradar_positieve_testuitslagen_per_week.csv",
    "riool.csv": RIVM + "COVID-19_rioolwaterdata_landelijk.csv",
    "riool_rwzi.csv": RIVM + "COVID-19_rioolwaterdata.csv",
    "rwzi_locaties.csv": "https://geo.rijkswaterstaat.nl/services/ogc/gdr/richtlijn_stedelijkafvalwater/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=rsa_rwzi&outputFormat=csv",
    "meldingen.html": "https://www.rivm.nl/meldingsplicht-infectieziekten/overzicht-meldingen",
}
fout = False
for naam, url in BESTANDEN.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (infectieziekten-dashboard)"})
        data = urllib.request.urlopen(req, timeout=120).read()
        if len(data) < 1000:
            raise ValueError(f"verdacht klein ({len(data)} bytes)")
        (BRON / naam).write_bytes(data)
        print(f"opgehaald: {naam} ({len(data):,} bytes)")
    except Exception as e:
        print(f"FOUT bij {naam}: {e}", file=sys.stderr)
        fout = True

# Nivel: cijfers per GGD-regio, elke woensdag voor de week ervoor. Bestandsnaam bevat het weeknummer,
# dus de nieuwste van de afgelopen weken proberen. Optioneel: zonder dit bestand bouwt de site zonder ARI-kaart.
NIVEL = "https://www.nivel.nl/sites/default/files/algemene-content/surveillance/NivelSurveillanceBulletin_GGD_{j}_wk{w:02d}.xlsx"
for terug in range(1, 5):
    j, w, _ = (dt.date.today() - dt.timedelta(weeks=terug)).isocalendar()
    try:
        req = urllib.request.Request(NIVEL.format(j=j, w=w), headers={"User-Agent": "Mozilla/5.0 (infectieziekten-dashboard)"})
        data = urllib.request.urlopen(req, timeout=60).read()
        if data[:2] == b"PK":
            (BRON / "nivel_ggd.xlsx").write_bytes(data)
            print(f"opgehaald: nivel_ggd.xlsx (week {w} van {j})")
            break
    except Exception:
        pass
else:
    print("let op: geen Nivel-bestand per GGD-regio gevonden; site zonder ARI-kaart", file=sys.stderr)

sys.exit(1 if fout else 0)
