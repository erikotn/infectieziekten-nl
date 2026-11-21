"""Haalt de ruwe bronbestanden op in bron/. Stopt met een fout als een bron niet te bereiken is,
zodat de vorige versie van de site online blijft."""
import pathlib, sys, urllib.request

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
sys.exit(1 if fout else 0)
