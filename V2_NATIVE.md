# Planning to ICS V2 native

La V2 remplace l'interface web locale de la V1 par une application de bureau
PySide6/Qt. Elle n'ouvre aucun navigateur, n'embarque aucune page web et ne
démarre aucun serveur HTTP.

La V2.0 est la version principale publiée dans `main`. Les anciennes releases
restent disponibles sur GitHub.

## Parcours disponibles

- choix du dossier de plannings et liste récursive des PDF ;
- choix manuel ou glisser-déposer d'un PDF ;
- sélection du technicien ;
- génération directe d'un ICS ;
- prévisualisation et modification des événements ;
- sélection de plusieurs techniciens, avec recherche et missions communes ;
- export d'un ICS par technicien accompagné d'un ZIP ;
- sélection de plusieurs PDF pour réunir plusieurs semaines dans un ICS ;
- mode sombre ;
- notice PDF accessible depuis le menu `Aide` ;
- import, export et réinitialisation des réglages ;
- ouverture de l'ICS ou de son dossier après génération.

Les réglages utilisent le même fichier que la V1 :

```text
%APPDATA%\Planning To ICS\settings.json
```

Une installation V2 remplaçant la V1 conserve donc les dossiers mémorisés.

## Lancement en développement

```powershell
.\.venv\Scripts\python.exe .\planning_native.py
```

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest
```

## Compilation

```powershell
$env:PLANNING_RELEASE_VERSION = "2.0"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ".\Planning To ICS V2.spec"
```

Le résultat local se trouve dans `dist\Planning to ICS`. L'installateur Windows
est ensuite généré avec `installer\PlanningToICS.iss`.
