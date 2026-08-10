# Système d'Archivage ETSL

Application d'archivage et de numérisation sur-mesure pour ETSL (Gabon).
Source des besoins : `SPECIFICATION_SYSTEME_ETSL.md` (références `RF-xx`).

## Stack

| Couche | Technologie |
|---|---|
| Backend | Python / Django + DRF + Celery |
| Base de données | PostgreSQL 16 |
| Stockage objets | MinIO (S3) sur NAS |
| Frontend | Tauri + React/TypeScript (app desktop Windows) |
| OCR | Tesseract 5 + OpenCV (à venir) |
| Orchestration | Docker Compose |

## Prérequis

- Docker Desktop (WSL2 backend) — sur ce poste, le binaire est à
  `C:\Users\user\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`
  (ajouter `...\resources\bin` au PATH si `docker` n'est pas reconnu).
- Python 3.13

## Démarrage (infrastructure)

```powershell
Copy-Item .env.example .env      # puis ajuster les mots de passe en dev si besoin
docker compose up -d             # lance postgres:16 + minio
docker compose ps                # attendre "healthy" sur les deux services
```

- API MinIO (S3) : http://localhost:9000
- Console MinIO : http://localhost:9001 (identifiants dans `.env`)
- PostgreSQL (container) : port hôte **5433** → 5432 interne (5432 est occupé par un
  PostgreSQL Windows natif sur la machine de dev)

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ../.env .env          # ou créer backend\.env
python manage.py migrate
python manage.py runserver
```

- Vérification : `GET http://localhost:8000/api/health/` → `{"status": "ok"}`
