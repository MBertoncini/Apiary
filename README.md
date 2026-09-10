# Apiary — Beekeeping Management Platform

A full-stack web application for professional and hobbyist beekeepers. Manage apiaries, hives, colonies, queens, harvests, treatments, equipment, sales, and storage — with AI-powered frame analysis, voice input, and real-time weather integration.

**Live demo:** [cible99.pythonanywhere.com](https://cible99.pythonanywhere.com)

---

## Features

| Module | Capabilities |
|--------|-------------|
| **Apiaries & Hives** | Multi-apiary management, interactive map layout, hive inspections, NFC tagging |
| **Colonies** | Colony tracking decoupled from physical hive (Colonia model), independent history |
| **Queen Tracking** | Genealogy tree, queen comparisons, lineage history, fallback to previous queens |
| **Honey Production** | Honey supers, super position history, harvest (smielatura), jar-filling records |
| **Cantina / Storage** | Maturatori (maturation tanks), storage containers, maturation preferences |
| **Health & Treatments** | Varroa/disease treatment log, customizable treatment types |
| **Blooms (Fioriture)** | Flower source tracking with community confirmations |
| **Equipment** | Inventory, maintenance log, equipment lending, hive-equipment binding |
| **Sales & Clients** | Sales transactions, client management, payment tracking |
| **Groups** | Multi-user groups with roles, invitation system, shared resources |
| **Nucleus (Nuclei)** | Nucleus management, inspections, conversion to full hive |
| **Weather** | Per-apiary weather & forecasts (OpenWeatherMap), charts |
| **Calendar** | Unified calendar view of all events |
| **Maps** | Visual apiary layout editor + weather map |
| **Notifications** | Real-time notification center with polling, per-type filters |
| **AI Assistant** | Gemini-powered chat, voice input, YOLO bee frame analysis, AI quota system |
| **Voice Entry** | Voice-driven creation of hives and treatments (mobile-first) |
| **Tutorial** | Onboarding flow and in-app guide |
| **Search** | Global search across the app |
| **Donations & Payments** | Donation page + payment/quota administration |
| **Export** | PDF/CSV/XLSX export (reportlab, openpyxl) |
| **REST API** | Full DRF API with JWT auth and Swagger/OpenAPI docs |

---

## Tech Stack

### Backend
| Component | Technology |
|-----------|-----------|
| Framework | Django 4.2 |
| Database | SQLite 3 |
| REST API | Django REST Framework 3.14 |
| Auth (API) | JWT — `djangorestframework-simplejwt` (with token blacklist + `UPDATE_LAST_LOGIN`) |
| Auth (Web) | Django session auth + Google Sign-In (`google-auth`) |
| CORS | `django-cors-headers` |
| Forms | django-crispy-forms + crispy-bootstrap5 |
| API Docs | drf-yasg (Swagger / OpenAPI) |
| Images | Pillow |
| HTTP | requests |
| Env config | python-dotenv |
| Date utils | python-dateutil |
| Reporting | reportlab (PDF), openpyxl (XLSX) |

### AI & ML
| Component | Technology |
|-----------|-----------|
| LLM Chat | Google Gemini API — model rotation (2.5-flash → 2.0-flash → 2.0-flash-lite → 1.5-flash → 1.5-flash-8b) |
| AI Quota | Per-user quota tiers + activation codes (`SystemAiQuota`, `ActivationCode`) |
| Frame Analysis | YOLO (`ultralytics`, optional) — detects bees, drones, queen bees, royal cells |
| Voice Input | Web Speech API (browser-native) + dedicated voice-creation API endpoints |

### Frontend
| Component | Technology |
|-----------|-----------|
| CSS Framework | Bootstrap 5 |
| Design System | Custom "Honey & Wood" theme (amber `#F5A623`, cream `#FFFDF5`, dark brown `#2C1810`) |
| Fonts | Caveat (display), Poppins (body) |
| Icons | Bootstrap Icons |
| JS | Vanilla JS (no framework) |
| Real-time | AJAX polling (notifications, 60s interval) |

### Hosting
- **PythonAnywhere** — `cible99.pythonanywhere.com`
- **Media storage** — local filesystem (`/media/`)
- **Static files** — PythonAnywhere static serving

---

## Project Structure

```
Apiary/
│
├── apiario_manager/            # Django project config
│   ├── settings.py             # Settings (env-based secrets)
│   ├── urls.py                 # Root URL dispatcher
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                       # Main application (all business logic)
│   ├── models.py               # 43 Django models (~2.2k lines)
│   ├── views.py                # Web views (~6.3k lines)
│   ├── api_views.py            # 25+ DRF viewsets + function endpoints (~3k lines)
│   ├── ai_views.py             # AI chat, voice, YOLO frame analysis (~900 lines)
│   ├── auth_views.py           # Login / register / Google Sign-In flows
│   ├── authentication.py       # Custom auth classes
│   ├── admin.py                # Django admin customization
│   ├── admin_stats.py          # Custom admin statistics views
│   ├── decorators.py           # View decorators (permissions, group access)
│   ├── forms.py                # ModelForm classes (~1k lines)
│   ├── urls.py                 # 140 web URL routes
│   ├── api_urls.py             # REST API routes (DRF router + extras)
│   ├── serializers.py          # DRF serializers (~1.3k lines)
│   ├── context_processors.py   # Global template context (weather, notifications)
│   ├── notifications.py        # Notification creation utilities
│   ├── ai_services.py          # Gemini AI service (singleton + model rotation)
│   ├── meteo_utils.py          # Weather data fetching & processing
│   ├── gbif_utils.py           # GBIF species data utilities (blooms)
│   ├── templatetags/           # Custom Django template tags
│   ├── management/commands/    # aggiorna_meteo, fix_encoding, link_orphan_regine, …
│   ├── migrations/             # Database migrations
│   └── ai_models/              # YOLO model weights (best.pt — gitignored)
│
├── templates/                  # 100 HTML templates (all extend base.html)
│   ├── base.html               # Main layout: sidebar (260px) + topbar (60px)
│   ├── dashboard.html          # Main dashboard
│   ├── homepage.html           # Public homepage
│   ├── admin/                  # Admin overrides
│   ├── apiari/                 # Apiary forms + group sharing
│   ├── arnie/                  # Hive forms, inspections, copy controllo
│   ├── regine/                 # Queens: genealogy, compare, search, replace
│   ├── melari/                 # Honey supers + harvest + jar-filling
│   ├── nuclei/                 # Nucleus management
│   ├── cantina/                # Maturation / storage room
│   ├── fioriture/              # Bloom tracking
│   ├── trattamenti/            # Health treatments
│   ├── attrezzature/           # Equipment & maintenance
│   ├── vendite/                # Sales
│   ├── clienti/                # Client management
│   ├── gruppi/                 # Group & member management
│   ├── notifiche/              # Notification center
│   ├── ai/                     # AI chat, voice control, frame analysis
│   ├── meteo/                  # Weather visualization & charts
│   ├── calendario/             # Calendar view
│   ├── maps/                   # Map views
│   ├── pagamenti/              # Payments & user quotas
│   ├── donazione/              # Donation page
│   ├── tutorial/               # Onboarding + guide
│   ├── ricerca/                # Global search results
│   ├── profilo/                # User profile
│   ├── email/                  # Email templates
│   └── auth/                   # Login / register
│
├── static/
│   ├── css/custom.css          # Complete design system (Honey & Wood theme)
│   ├── js/
│   │   ├── ai-chat.js          # Floating AI chat widget
│   │   ├── notifications.js    # Notification polling & AJAX
│   │   ├── tooltips.js         # Bootstrap tooltip bootstrapping
│   │   └── voice-controllo.js  # Voice control for hive inspections
│   └── images/
│       ├── logo.svg
│       └── icon.svg
│
├── media/                      # User-uploaded files (gitignored)
├── db.sqlite3                  # Database (gitignored in production)
├── manage.py
├── requirements.txt
└── .env                        # Secrets (gitignored)
```

---

## Data Models

The application uses **43 Django models** in `core/models.py`:

| Group | Models |
|-------|--------|
| **Organization** | `Gruppo`, `MembroGruppo`, `InvitoGruppo`, `QuotaUtente` |
| **Apiaries & Hives** | `Apiario`, `Arnia`, `ControlloArnia`, `ApiarioMapLayout` |
| **Colonies** | `Colonia` (decoupled colony tracking) |
| **Nucleus** | `Nucleo`, `ControlloNucleo` |
| **Queens** | `Regina`, `StoriaRegine` |
| **Production** | `Melario`, `StoricoPosizioneMelario`, `Smielatura`, `SmielaturaMelario`, `Invasettamento` |
| **Cantina / Storage** | `PreferenzaMaturazione`, `Maturatore`, `ContenitoreStoccaggio` |
| **Health** | `TipoTrattamento`, `TrattamentoSanitario` |
| **Blooms** | `Fioritura`, `FiorituraConferma` |
| **Commerce** | `Cliente`, `Vendita`, `DettaglioVendita`, `Pagamento` |
| **Equipment** | `CategoriaAttrezzatura`, `Attrezzatura`, `ManutenzioneAttrezzatura`, `PrestitoAttrezzatura`, `SpesaAttrezzatura`, `InventarioAttrezzature` |
| **Weather** | `DatiMeteo`, `PrevisioneMeteo` |
| **Users** | `Profilo`, `ImmagineProfilo`, `ActivationCode` |
| **AI** | `AnalisiTelaino`, `SystemAiQuota` |
| **Notifications** | `Notifica` |

---

## API

A full REST API is available at `/api/` with JWT authentication, designed to power the companion **Flutter mobile app** (`Apiary_app`).

### Auth
- `POST /api/token/` — obtain JWT token pair
- `POST /api/token/refresh/`
- `POST /api/register/` — user registration (mobile)
- `POST /api/auth/google/` — Google Sign-In (server-side ID token verification)
- `POST /api/password-reset/` + `/api/password-reset/confirm/`

### Core ViewSets (DRF router)
`apiari`, `arnie`, `colonie`, `controlli`, `regine`, `storia-regine`, `fioriture`, `fioriture-conferme`, `trattamenti`, `tipi-trattamento`, `melari`, `smielature`, `gruppi`, `pagamenti`, `quote`, `attrezzature`, `spese-attrezzatura`, `manutenzioni`, `invasettamenti`, `clienti`, `vendite`, `analisi-telaini`, `nuclei`, `maturatori`, `contenitori-stoccaggio`, `preferenze-maturazione`.

### Extra endpoints
- `GET /api/users/me/` — current user
- `GET /api/sync/` — bulk sync
- `GET/POST /api/inviti/...` — group invitations
- `POST /api/arnie/create_from_voice/` and `/api/trattamenti/create_from_voice/` — voice creation
- `POST /api/ai/chat/` — AI chat (JWT-compatible)
- `GET /api/ai/quota/`, `POST /api/ai/record-voice-call/`, `/api/ai/request-upgrade/`, `/api/ai/activate-code/`
- `GET /api/meteo/` — weather by location
- `GET /api/melari/?ids=...` — punctual re-fetch by ID list

### Docs
- `/api/docs/` — interactive Swagger UI
- `/api/schema/` — OpenAPI JSON

---

## Setup (Local Development)

```bash
# 1. Clone the repository
git clone https://github.com/your-username/Apiary.git
cd Apiary

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
#    There is no .env.example: create .env in the project root by hand.
#    settings.py loads /home/Cible99/.env in production, else <project>/.env.
#    See "Environment Variables" below for the exact names.

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Then open [http://localhost:8000](http://localhost:8000).

### Environment Variables

All are read by `apiario_manager/settings.py` from the `.env` loaded at
startup. Missing values fall back to the defaults shown, so nothing crashes on
a fresh checkout — the corresponding feature is simply disabled.

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | insecure dev key | Django secret key |
| `DJANGO_DEBUG` | `False` | `True` for dev. Also selects the database: SQLite when true, MySQL when false |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | — | MySQL connection, required only when `DJANGO_DEBUG=False` |
| `DB_PORT` | `3306` | MySQL port |
| `GEMINI_API_KEY` | empty | **Shared system Gemini key.** Used by `GeminiService` whenever the caller has no personal key |
| `GROQ_API_KEY` | empty | Shared system Groq key, statistics NL query |
| `OPENWEATHERMAP_API_KEY` | empty | Weather data |
| `BREVO_API_KEY` | empty | Transactional email through Anymail |
| `DEFAULT_FROM_EMAIL` | `Apiario Manager <noreply@gestioneapiario.it>` | Sender address |
| `FEEDBACK_RECIPIENT_EMAIL` | `noreply@gestioneapiario.it` | Where in-app feedback is delivered |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | 25 MB | Raised from Django's 2.5 MB because the Gemini proxy forwards base64 audio |
| `STATS_MAX_RESULT_ROWS` | `500` | Row cap for NL query results |
| `STATS_CACHE_WIDGETS_SECONDS` | `300` | Statistics widget cache TTL |

The Google Sign-In client IDs are **not** environment variables: they are
hardcoded in `core/api_views.py` (mobile) and `core/auth_views.py` (web), and
the two values differ.

### The shared Gemini key

`GEMINI_API_KEY` is the key the Flutter app uses when a user has not entered a
personal one. The app never sees it: it posts to
`POST /api/v1/ai/gemini-proxy/`, which injects the key server-side. This is
deliberate — the key used to be compiled into the app binary, was extracted
from it, and was suspended by Google.

To rotate it, edit the `.env` in use (`/home/Cible99/.env` in production) and
reload the web app. No app release is needed.

Resolution order per request, in `core/ai_services.py`:

1. The caller's personal key (`Profilo.gemini_api_key`), when set.
2. `GEMINI_API_KEY` from settings.
3. Neither → `403 Nessuna GEMINI_API_KEY configurata`.

A `400 API_KEY_INVALID` from `generativelanguage.googleapis.com` means a key
*was* sent and Google rejected it: revoked, restricted to an app or referrer,
or belonging to a project where the Generative Language API is not enabled.

### Optional — AI Frame Analysis

YOLO-based bee frame analysis requires `ultralytics` (commented out in `requirements.txt`):

```bash
pip install ultralytics
```

The trained model (`core/ai_models/best.pt`) is not included in the repository. Contact the maintainer to obtain it.

### i18n (Windows)

Windows lacks `gettext`, so use the bundled helper to compile `.po` → `.mo`:

```bash
python compile_translations.py
```

---

## Companion App

The Flutter mobile app **Apiary_app** consumes this project's REST API with JWT auth, sharing the same "Honey & Amber" design language.

---

## License

Private project. All rights reserved.
