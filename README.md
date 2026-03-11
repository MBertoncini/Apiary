# Apiary — Beekeeping Management Platform

A full-stack web application for professional and hobbyist beekeepers. Manage apiaries, hives, queens, harvests, treatments, equipment, sales, and more — with AI-powered frame analysis and real-time weather integration.

**Live demo:** [cible99.pythonanywhere.com](https://cible99.pythonanywhere.com)

---

## Features

| Module | Capabilities |
|--------|-------------|
| **Apiaries & Hives** | Multi-apiary management, interactive map layout, hive inspections |
| **Queen Tracking** | Genealogy tree, queen comparisons, lineage history |
| **Honey Production** | Honey supers, harvest (smielatura), jar-filling records |
| **Health & Treatments** | Varroa/disease treatment log, customizable treatment types |
| **Blooms (Fioriture)** | Flower source tracking with community confirmations |
| **Equipment** | Inventory, maintenance log, equipment lending system |
| **Sales & Clients** | Sales transactions, client management, payment tracking |
| **Groups** | Multi-user groups with roles, invitation system, shared resources |
| **Nucleus (Nuclei)** | Nucleus management, inspections, conversion to full hive |
| **Weather** | Per-apiary weather & forecasts (OpenWeatherMap), charts |
| **Calendar** | Unified calendar view of all events |
| **Maps** | Visual apiary layout editor + weather map |
| **Notifications** | Real-time notification center with polling, per-type filters |
| **AI Assistant** | Gemini-powered chat, voice input, YOLO bee frame analysis |
| **Export** | PDF/CSV export for inspections, treatments, production, sales |
| **REST API** | Full DRF API with JWT auth and Swagger/OpenAPI docs |

---

## Tech Stack

### Backend
| Component | Technology |
|-----------|-----------|
| Framework | Django 4.2 |
| Database | SQLite 3 |
| REST API | Django REST Framework 3.14 |
| Auth (API) | JWT — `djangorestframework-simplejwt` |
| Auth (Web) | Django session auth |
| Forms | django-crispy-forms + crispy-bootstrap5 |
| API Docs | drf-yasg (Swagger / OpenAPI) |
| Images | Pillow |
| HTTP | requests |
| Env config | python-dotenv |
| Date utils | python-dateutil |

### AI & ML
| Component | Technology |
|-----------|-----------|
| LLM Chat | Google Gemini API (model rotation: 2.5-flash → 2.0-flash → 1.5-flash) |
| Frame Analysis | YOLO (`ultralytics`) — detects bees, drones, queen bees, royal cells |
| Voice Input | Web Speech API (browser-native) |

### Frontend
| Component | Technology |
|-----------|-----------|
| CSS Framework | Bootstrap 5 |
| Design System | Custom "Honey & Wood" theme (amber `#F5A623`, dark brown `#2C1810`) |
| Fonts | Caveat (display), Poppins (body) |
| Icons | Bootstrap Icons |
| JS | Vanilla JS (no framework) |
| Real-time | AJAX polling (notifications, 60s interval) |

### Hosting
- **PythonAnywhere** — `cible99.pythonanywhere.com`
- **Media storage** — local filesystem (`/media/`)
- **Static files** — WhiteNoise / PythonAnywhere static serving

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
│   ├── models.py               # 34 Django models
│   ├── views.py                # 50+ view functions (web UI)
│   ├── api_views.py            # 15+ DRF viewsets (REST API)
│   ├── ai_views.py             # AI chat, voice, YOLO frame analysis
│   ├── forms.py                # 20+ ModelForm classes
│   ├── urls.py                 # 70+ web URL routes
│   ├── api_urls.py             # REST API routes
│   ├── serializers.py          # DRF serializers
│   ├── context_processors.py   # Global template context (weather, notifications)
│   ├── notifications.py        # Notification creation utilities
│   ├── ai_services.py          # Gemini AI service (singleton + model rotation)
│   ├── meteo_utils.py          # Weather data fetching & processing
│   ├── templatetags/           # Custom Django template tags
│   ├── management/             # Django management commands
│   ├── migrations/             # Database migrations
│   └── ai_models/              # YOLO model weights (best.pt — gitignored)
│
├── templates/                  # 89 HTML templates (extends base.html)
│   ├── base.html               # Main layout: sidebar (260px) + topbar (60px)
│   ├── dashboard.html          # Main dashboard
│   ├── apiari/                 # Apiary CRUD + map layout
│   ├── arnie/                  # Hive management & inspections
│   ├── regine/                 # Queen tracking & genealogy
│   ├── melari/                 # Honey supers & harvest
│   ├── nuclei/                 # Nucleus management
│   ├── fioriture/              # Bloom tracking
│   ├── trattamenti/            # Health treatments
│   ├── attrezzature/           # Equipment & maintenance
│   ├── vendite/                # Sales
│   ├── clienti/                # Client management
│   ├── gruppi/                 # Group & member management
│   ├── notifiche/              # Notification center
│   ├── ai/                     # AI chat & frame analysis UI
│   ├── meteo/                  # Weather & charts
│   ├── calendario/             # Calendar view
│   ├── maps/                   # Map views
│   └── auth/                   # Login / register
│
├── static/
│   ├── css/custom.css          # Complete design system (Honey & Wood theme)
│   ├── js/
│   │   ├── ai-chat.js          # Floating AI chat widget
│   │   ├── notifications.js    # Notification polling & AJAX
│   │   └── voice-controllo.js  # Voice control for hive inspections
│   └── images/
│       ├── logo.svg
│       └── icon.svg
│
├── media/                      # User-uploaded files (gitignored)
│   ├── profili/                # Profile pictures
│   └── gruppi/                 # Group images
│
├── db.sqlite3                  # Database (gitignored in production)
├── manage.py
├── requirements.txt
└── .env                        # Secrets (gitignored)
```

---

## Data Models

The application uses **34 Django models** organized in `core/models.py`:

| Group | Models |
|-------|--------|
| **Organization** | `Gruppo`, `MembroGruppo`, `InvitoGruppo`, `QuotaUtente` |
| **Apiaries & Hives** | `Apiario`, `Arnia`, `ControlloArnia`, `ApiarioMapLayout` |
| **Nucleus** | `Nucleo`, `ControlloNucleo` |
| **Queens** | `Regina`, `StoriaRegine` |
| **Production** | `Melario`, `Smielatura`, `Invasettamento` |
| **Health** | `TipoTrattamento`, `TrattamentoSanitario` |
| **Blooms** | `Fioritura`, `FiorituraConferma` |
| **Commerce** | `Cliente`, `Vendita`, `DettaglioVendita`, `Pagamento` |
| **Equipment** | `CategoriaAttrezzatura`, `Attrezzatura`, `ManutenzioneAttrezzatura`, `PrestitoAttrezzatura`, `SpesaAttrezzatura`, `InventarioAttrezzature` |
| **Weather** | `DatiMeteo`, `PrevisioneMeteo` |
| **Users** | `Profilo`, `ImmagineProfilo` |
| **AI** | `AnalisiTelaino` |
| **Notifications** | `Notifica` |

---

## API

A full REST API is available at `/api/` with JWT authentication.

- **Auth:** `POST /api/token/` — obtain JWT token pair
- **Refresh:** `POST /api/token/refresh/`
- **Docs:** `/api/docs/` — interactive Swagger UI
- **Schema:** `/api/schema/` — OpenAPI JSON

Designed for use by the companion **Flutter mobile app** (`Apiary_app`).

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
cp .env.example .env
# Edit .env with your SECRET_KEY, GEMINI_API_KEY, OPENWEATHERMAP_API_KEY

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Then open [http://localhost:8000](http://localhost:8000).

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for dev, `False` for prod |
| `GEMINI_API_KEY` | Google Gemini API key (AI features) |
| `OPENWEATHERMAP_API_KEY` | Weather data |

### Optional — AI Frame Analysis

YOLO-based bee frame analysis requires `ultralytics`:

```bash
pip install ultralytics
```

The trained model (`core/ai_models/best.pt`) is not included in the repository. Contact the maintainer to obtain it.

---

## Companion App

The Flutter mobile app **Apiary_app** consumes this project's REST API with JWT auth, sharing the same "Honey & Amber" design language.

---

## License

Private project. All rights reserved.
