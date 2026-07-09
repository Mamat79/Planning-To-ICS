# Planning To ICS V1.02

Application locale pour générer des fichiers calendrier `.ics` Outlook depuis les plannings PDF hebdomadaires Radio France.

Signature interface : `by Mamat`.

## Installation sur un autre PC

Envoyer et lancer l'installateur :

```text
installer-output\Planning_To_ICS_V1.02_Setup.exe
```

L'installateur contient l'application compilée et ses dépendances. Python n'est pas nécessaire sur le PC cible.

Par défaut, l'installation se fait sans droits administrateur dans :

```text
%LOCALAPPDATA%\Programs\Planning To ICS
```

Des raccourcis sont créés dans le menu Démarrer, dont `PDF to ICS`. L'installateur propose aussi un raccourci Bureau.

## Usage

Lancer `PDF to ICS` depuis le menu Démarrer.

L'interface locale s'ouvre dans le navigateur avec :

- le choix du dossier où se trouvent les plannings PDF par défaut ;
- la liste des PDF trouvés dans ce dossier ;
- le choix manuel d'un PDF ailleurs sur le disque avec `Parcourir` ;
- la liste des techniciens du PDF choisi ;
- le choix du dossier d'export du `.ics` ;
- un bouton de prévisualisation ;
- la modification des événements après prévisualisation ;
- un bouton de génération ICS.

Le dossier des plannings et le dossier d'export sont mémorisés entre deux lancements.

Après `Prévisualiser`, les événements extraits apparaissent dans un tableau modifiable. Tu peux décocher un événement, changer le résumé, les dates, les heures ou la description, puis cliquer sur `Exporter ICS modifié`.

## Règles appliquées

- Les jours sont associés aux dates par leur position horizontale dans le tableau.
- Les jours `SV`, `RH`, congés, récupérations, absence, santé ou mobilité ne génèrent aucun événement.
- Les pauses ne sont pas créées comme événements ; elles découpent le créneau travaillé.
- Si une fin est inférieure au début, l'événement finit le lendemain.
- Les titres Outlook retirent le nom du technicien quand il est répété au début de la mission.
- L'ICS est écrit en UTF-8 avec des dates UTC compatibles Outlook et la zone `Europe/Paris` en métadonnée.
- Les PDF source ne sont jamais modifiés.

## Développement

Le projet source est ici :

```text
D:\IA\Projets\Codex\Applis Persos\Planning To ICS
```

Installation des dépendances de développement :

```powershell
python -m pip install -r requirements.txt
```

Lancement sans compilation :

```powershell
python .\planning_ui.py
```

Compilation de l'application :

```powershell
python -m PyInstaller --noconfirm --clean ".\Planning To ICS.spec"
```

Compilation de l'installateur :

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" ".\installer\PlanningToICS.iss"
```
