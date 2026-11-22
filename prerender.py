"""Rendert elke pagina in site/ vooraf in een browser, zodat zoekmachines de grafieken als SVG in de HTML zien,
en maakt per soort pagina een deelafbeelding (Open Graph, 1200x630) in site/og/."""
import json, threading, functools, http.server, pathlib
from playwright.sync_api import sync_playwright

SITE = pathlib.Path("site")
(SITE / "og").mkdir(exist_ok=True)
class Stil(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Stil, directory=str(SITE))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASIS = f"http://127.0.0.1:{server.server_address[1]}"

with sync_playwright() as p:
    try:
        browser = p.chromium.launch()
    except Exception:
        browser = p.chromium.launch(channel="chrome")   # lokaal: geïnstalleerde Chrome
    page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1, color_scheme="light")
    gemaakt = set()
    for item in json.load(open(SITE / "paginas.json")):
        pad = item["pad"]
        page.goto(BASIS + pad, wait_until="networkidle")
        page.wait_for_timeout(100)
        if item["og"] not in gemaakt:
            page.screenshot(path=str(SITE / "og" / f"{item['og']}.png"))
            gemaakt.add(item["og"])
        html = page.evaluate("""() => {
            document.querySelectorAll('.tip').forEach(e => e.remove());
            return '<!doctype html>\\n' + document.documentElement.outerHTML;
        }""")
        bestand = SITE / (pad.strip("/") + "/index.html" if pad != "/" else "index.html")
        bestand.write_text(html)
    # griep- en covidkaart van de voorpagina als losse afbeeldingen voor de wekelijkse Bluesky-post
    scherp = browser.new_page(viewport={"width": 1200, "height": 1600}, device_scale_factor=2, color_scheme="light")
    scherp.goto(BASIS + "/", wait_until="networkidle")
    scherp.wait_for_timeout(300)
    for k, soort in zip(scherp.query_selector_all(".duo-kaart"), ("griep", "covid")):
        k.screenshot(path=str(SITE / "og" / f"bsky-{soort}.png"))
    browser.close()
server.shutdown()
print(f"vooraf gerenderd: {len(json.load(open(SITE / 'paginas.json')))} pagina's, {len(gemaakt)} deelafbeeldingen")
