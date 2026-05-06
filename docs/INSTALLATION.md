# Installation

Ce document décrit l'installation locale de l'ERP Monster Garage sur le PC administrateur.

## Préparer l'environnement

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm.cmd install
npm.cmd run css:build
python scripts\init_db.py
python run.py
```

L'application sera disponible sur `http://localhost:5000`.

Le compte de départ est `admin / admin123`. Après l'installation, changez le mot de passe avec :

```powershell
python scripts\creer_admin.py
```
