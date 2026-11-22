"""Plaatst een bericht op Bluesky als het oordeel voor griep, covid of RSV is omgeslagen.

- Vergelijkt de stand van deze week (data/fases.json) met wat het laatst gemeld is (data/gemeld.json).
- Eerste keer: legt alleen de stand vast, plaatst niets.
- Zonder BSKY_HANDLE en BSKY_APP_PASSWORD (of met --proef) plaatst het niets en toont het alleen de tekst.
"""
import json, os, pathlib, sys, urllib.request, datetime as dt

BASIS = os.environ.get("BASIS", "https://infectieziekten-nl.pages.dev").rstrip("/")
HIST, GEMELD = pathlib.Path("data/fases.json"), pathlib.Path("data/gemeld.json")
NAAM = {"griep": "Griep", "covid": "Covid", "rsv": "RSV"}
PROEF = "--proef" in sys.argv

historie = json.load(open(HIST))
week = sorted(historie)[-1]
nu = {z: v["fase"] for z, v in historie[week].items()}

if not GEMELD.exists():
    json.dump({"week": week, "fases": nu}, open(GEMELD, "w"), ensure_ascii=False, indent=1)
    print(f"eerste keer: stand van {week} vastgelegd, niets geplaatst")
    sys.exit(0)

vorig = json.load(open(GEMELD))["fases"]
omslag = [z for z in ("griep", "covid", "rsv") if z in nu and nu[z] != vorig.get(z)]
if not omslag:
    print(f"{week}: geen omslag, niets te melden")
    sys.exit(0)

jaar, nr = week.split("-W")
regels = [f"{NAAM[z]}: van {vorig.get(z, '?').lower()} naar {nu[z].lower()} ({historie[week][z]['eens']})." for z in omslag]
rest = [f"{NAAM[z]}: {nu[z].lower()}" for z in ("griep", "covid", "rsv") if z in nu and z not in omslag]
link = BASIS.replace("https://", "") + "/"
tekst = f"Week {int(nr)}: " + " ".join(regels) + ((" " + ", ".join(rest) + ".") if rest else "") + f"\n\n{link}"
if len(tekst) > 300:   # Bluesky-limiet; de link blijft altijd staan
    tekst = tekst[: 300 - len(link) - 3].rstrip() + "…\n\n" + link
print(tekst)

handle, wachtwoord = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
if PROEF:
    print("proef: niet geplaatst, stand niet bijgewerkt")
    sys.exit(0)
if not handle or not wachtwoord:
    json.dump({"week": week, "fases": nu}, open(GEMELD, "w"), ensure_ascii=False, indent=1)
    print("geen account gekoppeld: niet geplaatst, stand wel bijgewerkt")
    sys.exit(0)


def api(pad, data, token=None):
    req = urllib.request.Request("https://bsky.social/xrpc/" + pad, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.load(urllib.request.urlopen(req, timeout=30))


sessie = api("com.atproto.server.createSession", {"identifier": handle, "password": wachtwoord})
b = tekst.encode("utf-8")
start = b.rfind(link.encode("utf-8"))
api("com.atproto.repo.createRecord", {
    "repo": sessie["did"], "collection": "app.bsky.feed.post",
    "record": {"$type": "app.bsky.feed.post", "text": tekst, "langs": ["nl"], "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
               "facets": [{"index": {"byteStart": start, "byteEnd": start + len(link.encode("utf-8"))},
                           "features": [{"$type": "app.bsky.richtext.facet#link", "uri": BASIS + "/"}]}]},
}, sessie["accessJwt"])
json.dump({"week": week, "fases": nu}, open(GEMELD, "w"), ensure_ascii=False, indent=1)
print("geplaatst op Bluesky")
