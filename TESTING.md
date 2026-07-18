# Vérification

Depuis la racine du dépôt :

```powershell
python -m pytest -q
python -m py_compile planning_to_ics.py planning_ui.py
```

Les tests couvrent notamment les accents UTF-8, les pauses multiples, les
vacations de nuit, les exports multiples et ZIP, les identifiants ICS stables,
les diagnostics, les réglages et les lanceurs Windows/macOS/Linux.

La construction Windows utilise PyInstaller puis Inno Setup. La construction
macOS est exécutée par GitHub Actions sur macOS et produit un DMG.
