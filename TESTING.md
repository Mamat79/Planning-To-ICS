# Vérification

Depuis la racine du dépôt :

```powershell
python -m pytest -q
python -m py_compile planning_to_ics.py planning_ui.py
```

Les tests couvrent notamment les accents UTF-8, les pauses multiples, les
vacations de nuit, les exports multiples et ZIP, les identifiants ICS stables,
les diagnostics, les réglages, la sélection par mission, l'édition de plusieurs
techniciens et les lanceurs Windows/macOS/Linux.

La notice PDF est générée et contrôlée ainsi :

```powershell
python .\tools\make_user_guide.py
pdfinfo .\output\pdf\Planning_to_ICS_V1.08_Notice.pdf
pdftoppm -png .\output\pdf\Planning_to_ICS_V1.08_Notice.pdf .\tmp\pdfs\notice
```

La construction Windows utilise PyInstaller puis Inno Setup. La construction
macOS est exécutée par GitHub Actions sur macOS et produit un DMG.

Le build Windows de diffusion doit utiliser l'environnement Python 3.12 du
projet (`.venv`). Un build réalisé avec l'interpréteur Python du Microsoft Store
ne doit pas être publié sans un test de lancement de l'exécutable installé.
