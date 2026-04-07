# Voice To Text

<p align="center">
  <img src="static/icona.png" alt="Voice To Text" width="120">
</p>

<p align="center">
  <strong>Desktop aplikace pro přepis videa a audia na text s překladem do více jazyků</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/whisper-faster--whisper-orange" alt="Whisper">
  <img src="https://img.shields.io/badge/UI-FastAPI%20%2B%20Dark%20Mode-purple" alt="UI">
  <img src="https://img.shields.io/badge/GPU-auto%20detect-green" alt="GPU">
</p>

---

## Co aplikace umí

- **Přepis audia/videa na text** s časovými značkami (timestamps)
- **Editace přepisu** přímo v aplikaci (oprava jmen, překlepů)
- **Hledání v textu** s možností červeně zvýraznit důležité výrazy
- **Překlad** do 7 jazyků (CZ, SK, EN, DE, PL, HU, RO) se zachováním vlastních jmen
- **Export** do TXT, PDF, SRT (titulky) nebo ZIP se vším
- **Dávkové zpracování** - více souborů najednou s progress barem
- **Ukládání projektů** - práce se neztratí po restartu
- **Auto-detekce GPU** - na PC s NVIDIA automaticky využije CUDA
- **Dark mode UI**

## Screenshot

<p align="center">
  <img src="docs/screenshot.png" alt="Screenshot" width="800">
</p>

## Rychlý start

### Instalace (Windows)

```
1. Stáhněte nebo naklonujte tento repozitář
2. Spusťte setup.bat (nainstaluje Python + knihovny + vytvoří ikonu na ploše)
3. Klikněte na ikonu "Voice To Text" na ploše
```

### Instalace (manuální)

```bash
pip install -r requirements.txt
python app.py
```

Aplikace se otevře na `http://localhost:8000`

## Jak to funguje

```
Video/Audio  ──>  Whisper AI  ──>  Text s timestamps
                                        │
                    ┌───────────────────┤
                    │                    │
              Hledání a             Editace textu
              zvýraznění            (opravy, jména)
                    │                    │
                    └───────────────────┤
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                      Export         Překlad        Uložení
                   TXT/PDF/SRT    7 jazyků         projektu
                      /ZIP       + SRT titulky
```

## Funkce podrobně

### Přepis
- Model **Whisper** (faster-whisper) s optimalizací pro češtinu
- 3 úrovně kvality: small (rychlý), medium (doporučený), large (nejpřesnější)
- Automatické sloučení do vět (ne po slovech)
- Slovník oprav pro automatickou korekci častých chyb

### Hledání a zvýraznění
- Vyhledávání v celém přepisu
- Nalezené výrazy zvýrazněny žlutě
- Možnost trvale označit výrazy červeně (zvýraznění se přenese do PDF exportu)

### Překlad
- 7 cílových jazyků najednou
- Zachování vlastních jmen (konfigurovatelný seznam)
- Export překladu jako SRT titulky

### Export
| Formát | Popis |
|--------|-------|
| **TXT** | Čistý text s timestamps `[00:01:23 - 00:01:45]` |
| **PDF** | Formátovaný dokument, označené výrazy červeně |
| **SRT** | Titulky pro import do video editoru |
| **ZIP** | Vše najednou včetně všech překladů |

## Technologie

| Komponenta | Technologie |
|-----------|-------------|
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn |
| Frontend | Vanilla JS, Dark Mode UI |
| Překlad | [deep-translator](https://github.com/nidhaloff/deep-translator) (Google Translate) |
| PDF export | [fpdf2](https://github.com/py-pdf/fpdf2) + DejaVu fonty |
| GPU akcelerace | CUDA (auto-detect) |

## Struktura projektu

```
VoiceToText/
├── app.py               # Hlavní aplikace (FastAPI server)
├── translator.py         # Překlad s ochranou jmen
├── exporter.py           # Export do TXT, PDF, SRT
├── dictionary.txt        # Slovník oprav (editovatelný)
├── names.txt             # Jména která se nepřekládají
├── requirements.txt      # Python závislosti
├── setup.bat             # Automatický instalátor (Windows)
├── start.bat             # Spouštěč aplikace
├── static/               # CSS, fonty, ikona
│   ├── style.css
│   ├── icona.png
│   ├── DejaVuSans.ttf
│   └── DejaVuSans-Bold.ttf
├── templates/
│   └── index.html        # Frontend (single page app)
├── uploads/              # Nahrané soubory (gitignored)
├── outputs/              # Exportované soubory (gitignored)
└── projects/             # Uložené projekty (gitignored)
```

## Přenositelnost

Aplikace je navržena pro snadné přenesení na jiný počítač:

1. Zkopírujte celou složku na nový PC
2. Spusťte `setup.bat`
3. Hotovo

Setup automaticky:
- Nainstaluje Python (pokud chybí)
- Nainstaluje všechny knihovny
- Detekuje a nakonfiguruje GPU (pokud je NVIDIA)
- Stáhne jazykový model
- Vytvoří ikonu na ploše

## Licence

MIT License - viz [LICENSE](LICENSE)
