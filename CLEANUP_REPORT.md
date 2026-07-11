# Rapport de nettoyage V1.07 beta

Date: 2026-07-11

## Périmètre audité

- Sources Python: `planning_to_ics.py`, `planning_ui.py`
- Interface Windows/WebView: `planning_ui.py`, `Planning To ICS.spec`
- Tests: `tests/`, `pytest.ini`, workflow GitHub Actions
- Installateur: `installer/PlanningToICS.iss`, `installer-output/`
- Builds PyInstaller: `build/`, `dist/`, `_internal/`, executable racine
- Caches et temporaires: `__pycache__/`, `.pytest_cache/`, `tests/__pycache__/`, `tmp/`
- Documentation: `README.md`
- Binaires suivis par Git: aucun installateur ou build compilé n'est suivi par Git

## Constat

- Le dépôt Git est propre au début de l'intervention et basé sur `main`.
- L'installateur V1.06 local existe dans `installer-output/` et reste conservé tant qu'un installateur V1.07 validé ne l'a pas remplacé.
- Des restes locaux de compilation non suivis étaient présents à la racine: `Planning to ICS.exe` et `_internal/`.
- Des caches Python et pytest étaient présents: `__pycache__/`, `tests/__pycache__/`, `.pytest_cache/`.
- Les installateurs compilés sont ignorés par Git et doivent rester distribués via GitHub Releases.

## Nettoyage effectué

- Suppression prévue des caches Python et pytest.
- Suppression prévue des restes locaux PyInstaller régénérables: executable racine, `_internal/`, `build/`, `dist/`.
- Conservation de `installer-output/Planning_to_ICS_V1.06_Setup.exe` jusqu'au remplacement par un installateur V1.07 validé.

## Éléments conservés volontairement

- Fixtures de tests anonymisées sous `tests/`.
- Icône `assets/planning-to-ics.ico`.
- Script Inno Setup.
- Fichier spec PyInstaller.
- Installateur V1.06 local actuel, car il correspond à la dernière release distribuée.

## Règle de publication

Les installateurs compilés ne doivent pas être commités dans Git. Ils doivent être attachés aux GitHub Releases après validation locale.
