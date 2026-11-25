"""Plaatst elke week één bericht op Bluesky: de griep- en covidkaart van de voorpagina als afbeeldingen, met toelichting.

- Plaatst zodra de griepcijfers van een nieuwe week er zijn (ECDC, meestal vrijdag; vergeleken met data/gemeld.json).
  Dan zijn ook de rioolwatercijfers (RIVM, woensdag) van die week binnen, dus gaan griep en covid over dezelfde week. Eén post per week.
- Is het oordeel voor griep, covid of RSV omgeslagen, dan staat dat bovenaan.
- Teksten uit site/bluesky.json (build.py), afbeeldingen uit site/og/bsky-*.png (prerender.py); ontbreken die, dan alleen tekst.
- Zonder BSKY_HANDLE en BSKY_APP_PASSWORD (of met --proef) plaatst het niets en toont het alleen de tekst.
"""
import json, os, pathlib, sys, urllib.request, datetime as dt

BASIS = os.environ.get("BASIS", "https://infectieziekten-nl.pages.dev").rstrip("/")
HIST, GEMELD = pathlib.Path("data/fases.json"), pathlib.Path("data/gemeld.json")
KAART, OG = pathlib.Path("site/bluesky.json"), pathlib.Path("site/og")
NAAM = {"griep": "Griep", "covid": "Covid", "rsv": "RSV"}
PROEF = "--proef" in sys.argv


def api(pad, data, token=None, ruw=None, soort="application/json"):
    req = urllib.request.Request("https://bsky.social/xrpc/" + pad, data=ruw if ruw is not None else json.dumps(data).encode(),
                                 headers={"Content-Type": soort, **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.load(urllib.request.urlopen(req, timeout=60))


historie = json.load(open(HIST))
week = sorted(historie)[-1]
nu = {z: v["fase"] for z, v in historie[week].items()}
vorig = json.load(open(GEMELD)) if GEMELD.exists() else {"week": None, "fases": {}}
kaart = json.load(open(KAART)) if KAART.exists() else {}
gj, gw, _ = dt.date.fromisoformat(kaart["griep"]["week"]).isocalendar()
griepweek = f"{gj}-W{gw:02d}"


def bewaar():
    json.dump({"week": week, "griepweek": griepweek, "fases": nu}, open(GEMELD, "w"), ensure_ascii=False, indent=1)


if "griepweek" not in vorig and not PROEF:   # overgang van het oude schema: huidige griepweek geldt als gemeld
    bewaar()
    print(f"griepweek {griepweek} vastgelegd, niets geplaatst")
    sys.exit(0)
if vorig.get("griepweek") == griepweek and not PROEF:
    print(f"griepweek {griepweek}: al gemeld, niets te doen")
    sys.exit(0)

# ---- tekst
nr = gw
omslag = [f"{NAAM[z]} van {vorig['fases'].get(z, '?').lower()} naar {nu[z].lower()}."
          for z in ("griep", "covid", "rsv") if z in nu and vorig["fases"].get(z) and nu[z] != vorig["fases"][z]]
blokken = [f"{NAAM[z]}: {k['groot']} {k['maat']} t.o.v. vorige week." + (f" {k['context'][0].upper()}{k['context'][1:].replace(' · ', ', ')}." if k["context"] else "")
           for z, k in kaart.items()]
link = BASIS.replace("https://", "") + "/"


def opbouw(blokken):
    kop = f"Week {int(nr)}" + (" · Oordeel veranderd: " + " ".join(omslag) if omslag else "")
    return "\n\n".join([kop, *blokken, link])


tekst = opbouw(blokken)
if len(tekst) > 300:   # Bluesky-limiet: eerst de context-zinnen weglaten
    tekst = opbouw([f"{NAAM[z]}: {k['groot']} {k['maat']} t.o.v. vorige week." for z, k in kaart.items()])
if len(tekst) > 300:
    tekst = tekst[: 300 - len(link) - 3].rstrip() + "…\n\n" + link

# ---- afbeeldingen + alt-tekst
beelden = []
for z, k in kaart.items():
    f = OG / f"bsky-{z}.png"
    if not f.exists():
        continue
    b = f.read_bytes()
    if len(b) > 950_000:    # Bluesky weigert afbeeldingen boven ~1 MB
        print(f"{f} te groot ({len(b)} bytes), overgeslagen")
        continue
    alt = (f"Kaart {NAAM[z]} van {link.rstrip('/')}: {k['groot']} t.o.v. vorige week"
           + (f", {k['context'].replace(' · ', ', ')}" if k["context"] else "") + f". {k['oms']}. Grafiek van het afgelopen jaar, met een jaar eerder ter vergelijking. {k['tweede']}.")
    beelden.append((b, alt, int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")))

print(tekst)
print(f"\n{len(beelden)} afbeelding(en):")
for _, alt, w, h in beelden:
    print(f"- {w}x{h}: {alt}")

if PROEF:
    print("\nproef: niet geplaatst, stand niet bijgewerkt")
    sys.exit(0)

handle, wachtwoord = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
if not (handle and wachtwoord):
    bewaar()
    print("geen account gekoppeld: niet geplaatst, stand wel bijgewerkt")
    sys.exit(0)

sessie = api("com.atproto.server.createSession", {"identifier": handle, "password": wachtwoord})
print(f"inloggen als {handle} gelukt")
record = {"$type": "app.bsky.feed.post", "text": tekst, "langs": ["nl"],
          "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")}
b = tekst.encode("utf-8")
start = b.rfind(link.encode("utf-8"))
record["facets"] = [{"index": {"byteStart": start, "byteEnd": start + len(link.encode("utf-8"))},
                     "features": [{"$type": "app.bsky.richtext.facet#link", "uri": BASIS + "/"}]}]
if beelden:
    record["embed"] = {"$type": "app.bsky.embed.images", "images": [
        {"image": api("com.atproto.repo.uploadBlob", None, sessie["accessJwt"], ruw=data, soort="image/png")["blob"],
         "alt": alt[:2000], "aspectRatio": {"width": w, "height": h}} for data, alt, w, h in beelden]}
api("com.atproto.repo.createRecord", {"repo": sessie["did"], "collection": "app.bsky.feed.post", "record": record}, sessie["accessJwt"])
bewaar()
print("geplaatst op Bluesky")
