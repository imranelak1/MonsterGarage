# ERP Monster Garage

Application web locale pour la gestion de Monster Garage / WIDINE MOTORS SERVICES à Marrakech.

Le projet est développé en français et suit le plan de développement V2.

## Démarrage rapide

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm.cmd install
npm.cmd run css:build
python scripts\init_db.py
python run.py
```

Puis ouvrir `http://localhost:5000`.

Compte de départ : `admin / admin123`. Changez le mot de passe avec `python scripts\creer_admin.py`.
