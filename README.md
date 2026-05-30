# RouteWise TZ

Community-powered road intelligence for Tanzanian transporters.

## Setup

```bash
cd hackthon
pip install -r requirements.txt
cp .env.example .env   # or use your existing .ENV
# Edit .env with SECRET_KEY, GEMINI_API_KEY, AT_USERNAME, AT_API_KEY
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser
python manage.py runserver
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret |
| `DEBUG` | `True` or `False` (string) |
| `GEMINI_API_KEY` | Google Gemini API |
| `GEMINI_MODEL` | Default `gemini-2.5-flash` |
| `AT_USERNAME` | Africa's Talking username |
| `AT_API_KEY` | Africa's Talking API key |

Settings load `.env` and `.ENV` automatically. Never commit real keys.

Open http://127.0.0.1:8000/

## URLs

| Page | URL |
|------|-----|
| Home | `/` |
| Dashboard | `/dashboard/` |
| Routes | `/routes/` |
| Route detail | `/routes/<id>/` |
| Report incident | `/report/` |
| Register driver | `/register-driver/` |
| Simulate SMS/WhatsApp | `/simulate-message/` |
| Admin | `/admin/` |

## Route segments

Routes are multi-leg corridors (e.g. Dar es Salaam → Chalinze → Morogoro → Gairo → Dodoma), not single straight lines. Incidents attach to the closest **RouteSegment**; full route risk aggregates segment scores.

## Risk Scoring

See `core/services/risk_engine.py`. Per-segment scores use severity, incident type, verification, and freshness. Route score aggregates segments (max + multi-section boost). Recommendations warn per section, not “cancel whole trip.”

## Demo Script

1. Home → hero, features, pitch
2. Dashboard → stats, high-risk routes, latest reports
3. Routes → click Dar es Salaam → Morogoro
4. Report incident → submit, see risk update
5. Simulate SMS → `ACCIDENT#Chalinze#Dar es Salaam to Morogoro`
6. Register driver → add a driver
