# Planning to ICS V1.07

Application locale pour générer des fichiers calendrier `.ics` Outlook depuis les plannings PDF hebdomadaires Radio France.

Signature interface : `by Mamat et ses agents`.

## Origine du projet

Planning to ICS est l'aboutissement d'un projet commencé il y a plusieurs années. Les premières versions reposaient sur des scripts manuels, de l'OCR et des traitements de fichiers difficiles à maintenir et à transmettre.

L'arrivée d'agents IA modernes a permis de franchir un cap important : structurer le code, fiabiliser l'extraction PDF, gérer les accents, tester les cas particuliers, créer une véritable interface Windows et préparer un installateur partageable.

Cette signature reflète volontairement cette histoire : Mamat porte le projet, et des agents IA ont largement contribué à sa conception, son évolution, ses tests et sa documentation.

## Installation sur un autre PC

Télécharger l'installateur depuis la page [Releases GitHub](https://github.com/Mamat79/Planning-To-ICS/releases) :

```text
Planning_to_ICS_V1.07_Setup.exe
```

L'installateur contient l'application compilée et ses dépendances. Python n'est pas nécessaire sur le PC cible.

L'assistant d'installation permet de choisir le dossier d'installation. Par défaut, l'installation se fait sans droits administrateur dans :

```text
%LOCALAPPDATA%\Programs\Planning to ICS
```

L'assistant propose la création de raccourcis, avec un raccourci dans le menu Démarrer coché par défaut. Le raccourci Bureau reste optionnel.

Si une version de Planning to ICS ou Planning To ICS est déjà installée, l'assistant le détecte au démarrage. Il propose soit de remplacer la version existante, soit d'installer la nouvelle version en plus dans un autre dossier avec des raccourcis séparés.

## Usage

Lancer `Planning to ICS` depuis le menu Démarrer.

L'application s'ouvre dans une fenêtre Windows dédiée avec :

- le choix du dossier où se trouvent les plannings PDF par défaut ;
- la liste de tous les PDF trouvés dans ce dossier et ses sous-dossiers ;
- le choix manuel d'un PDF ailleurs sur le disque avec `Parcourir` ;
- la liste des techniciens du PDF choisi ;
- un diagnostic indiquant si le planning est compatible, scanné ou non reconnu ;
- le choix du dossier d'export du `.ics` ;
- un bouton de prévisualisation ;
- la modification des événements après prévisualisation ;
- un bouton de génération ICS ;
- des boutons pour ouvrir l'ICS ou afficher son dossier après génération ;
- un bouton `Quitter l'application` et une fermeture complète avec la croix de la fenêtre.

Le dossier des plannings et le dossier d'export sont mémorisés entre deux lancements.

Après `Prévisualiser`, les événements extraits apparaissent dans un tableau modifiable. Tu peux décocher un événement, changer le résumé, les dates, les heures ou la description, puis cliquer sur `Exporter ICS modifié`.

Une fois le fichier `.ics` généré, il faut l'importer dans l'agenda voulu. L'application crée le fichier ICS, mais elle ne l'ajoute pas automatiquement dans Outlook, Google Agenda ou un autre calendrier.

## Tutoriel vidéo

Vidéo silencieuse avec sous-titres : [télécharger le tutoriel V1.07](https://github.com/Mamat79/Planning-To-ICS/releases/download/v1.07/Planning_to_ICS_V1.07_Tutoriel.mp4).

L'application compilée ne laisse ni fenêtre CMD ni onglet de navigateur visible. Fermer la fenêtre arrête complètement l'application.

## Règles appliquées

- Les jours sont associés aux dates par leur position horizontale dans le tableau.
- Les jours `SV`, `RH`, congés, récupérations, absence, santé ou mobilité ne génèrent aucun événement.
- Les pauses ne sont pas créées comme événements ; elles découpent le créneau travaillé.
- Si une fin est inférieure au début, l'événement finit le lendemain.
- Les titres Outlook retirent le nom du technicien quand il est répété au début de la mission.
- La semaine et l'année sont lues en priorité dans le contenu du PDF, sans utiliser sa date de copie.
- L'ICS est écrit en UTF-8 standard sans BOM, avec des dates UTC compatibles Outlook et la zone `Europe/Paris` en métadonnée.
- Les PDF source ne sont jamais modifiés.

## Développement

Le code source est disponible dans ce dépôt GitHub :

```text
https://github.com/Mamat79/Planning-To-ICS
```

Installation des dépendances de développement :

```powershell
python -m pip install -r requirements-dev.txt
```

Lancement sans compilation :

```powershell
python .\planning_ui.py
```

Exécution des tests automatiques :

```powershell
python -m pytest
```

Compilation de l'application :

```powershell
python -m PyInstaller --noconfirm --clean ".\Planning To ICS.spec"
```

Compilation de l'installateur :

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" ".\installer\PlanningToICS.iss"
```

Les installateurs compilés ne sont pas versionnés dans Git. Ils sont joints aux Releases GitHub afin de garder le dépôt source léger.
