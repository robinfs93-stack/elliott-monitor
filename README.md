# Elliott-Wellen-Monitor

Automatische Elliott-Wellen-Zählung auf Tageskerzen für ausgewählte Aktien, Indizes und Kryptowährungen. Das Dashboard läuft auf GitHub Pages und aktualisiert sich täglich um 6:00 Uhr deutscher Zeit.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `index.html` | Dashboard (Übersicht, Detail mit Chart, Methodik) |
| `config/assets.json` | Liste der analysierten Werte |
| `scripts/build.py` | Holt Kurse (Yahoo Finance, KuCoin) und schreibt `data/*.json` |
| `scripts/elliott.py` | Wellen-Engine: ZigZag, Regelprüfung, Fibonacci-Bewertung, Ziele |
| `.github/workflows/update.yml` | Tägliche Aktualisierung um 6:00 Uhr (Sommer- und Winterzeit) |

## Wert hinzufügen

In `config/assets.json` eine Zeile ergänzen:

- Aktie/Index: `{"id": "msft", "name": "Microsoft", "group": "Aktien", "yahoo": "MSFT", "unit": "USD"}`
- Krypto: `{"id": "xrp", "name": "XRP", "group": "Krypto", "kucoin": "XRP-USDT", "yahoo": "XRP-USD", "unit": "USD"}`

Deutsche Aktien mit Endung `.DE` (Xetra), z. B. `ALV.DE`. Danach unter *Actions → Kurse aktualisieren → Run workflow* sofort neu rechnen lassen.

## Hinweis

Keine Anlageberatung. Elliott-Zählungen sind Szenarien mit Invalidierungsniveau, keine Prognosen.
