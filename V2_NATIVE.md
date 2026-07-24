# Planning to ICS V2 native

La V2 remplace l'interface web locale de la V1 par une application de bureau
PySide6/Qt. Elle n'ouvre aucun navigateur, n'embarque aucune page web et ne
démarre aucun serveur HTTP.

Cette version est développée dans la branche locale `v2-native`. Elle reste en
test sur le PC de développement et ne doit pas être publiée avant validation.

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
- import, export et réinitialisation des réglages ;
- ouverture de l'ICS ou de son dossier après génération.

Les réglages utilisent le même fichier que la V1 :

```text
%APPDATA%\Planning To ICS\settings.json
```

La V1.09 et la V2 peuvent donc utiliser les mêmes dossiers mémorisés tout en
restant installées côte à côte.

## Lancement en développement

```powershell
.\.venv\Scripts\python.exe .\planning_native.py
```

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest
```

## Compilation locale de test

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ".\Planning To ICS V2.spec"
```

Le résultat local se trouve dans `dist\Planning to ICS V2`. La création d'un
installateur de diffusion, d'une archive et d'une Release GitHub est volontairement
reportée jusqu'à la demande explicite `Compile et publie`.
