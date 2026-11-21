# Infectieziekten in Nederland

Statische site met wekelijkse cijfers over griep, covid, RSV en luchtwegklachten, en jaartotalen van alle meldingsplichtige infectieziekten in Nederland.

- `ophalen.py` haalt de bronbestanden op (ECDC ERVISS, RIVM open data, RIVM-overzicht meldingen).
- `build.py` controleert de data en bouwt `site/` (63 pagina's, sitemap, data.json).
- `prerender.py` rendert de grafieken vooraf in de HTML en maakt deelafbeeldingen.
- `.github/workflows/bijwerken.yml` draait dit drie keer per dag en zet de site op Cloudflare Pages als er nieuwe cijfers zijn.

Lokaal: `python3 ophalen.py && python3 build.py && python3 prerender.py`, daarna `python3 -m http.server -d site`.
