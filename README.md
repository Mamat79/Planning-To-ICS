# Planning to ICS V1.08

Application locale Windows et macOS pour générer des fichiers calendrier `.ics` Outlook depuis les plannings PDF hebdomadaires Radio France.


## Origine du projet

Le projet a commencé avec des scripts manuels, de l'OCR et des traitements de fichiers. Des agents IA ont ensuite contribué à moderniser le code, améliorer l'extraction des PDF, gérer les accents et préparer l'application Windows.

## Télécharger et installer

Le téléchargement le plus simple est ici : [Télécharger l'installateur Windows V1.08](https://github.com/Mamat79/Planning-To-ICS/releases/download/v1.08/Planning_to_ICS_V1.08_Setup.exe).

Si le téléchargement direct ne démarre pas :

1. Ouvrir la [page des Releases GitHub](https://github.com/Mamat79/Planning-To-ICS/releases).
2. Cliquer sur `v1.08` dans la liste.
3. Descendre jusqu'à la rubrique **Assets**.
4. Cliquer sur `Planning_to_ICS_V1.08_Setup.exe`.
5. Ouvrir le fichier téléchargé pour lancer l'installation.

L'installateur contient l'application compilée et ses dépendances. Python n'est pas nécessaire sur le PC cible.

L'assistant d'installation permet de choisir le dossier d'installation. Par défaut, l'installation se fait sans droits administrateur dans :

```text
%LOCALAPPDATA%\Programs\Planning to ICS
```

L'assistant propose la création de raccourcis, avec un raccourci dans le menu Démarrer coché par défaut. Le raccourci Bureau reste optionnel.

Si une version de Planning to ICS ou Planning To ICS est déjà installée, l'assistant le détecte au démarrage. Il propose soit de remplacer la version existante, soit d'installer la nouvelle version en plus dans un autre dossier avec des raccourcis séparés.

### macOS

Télécharger le paquet [Planning_to_ICS_V1.08_macOS.dmg](https://github.com/Mamat79/Planning-To-ICS/releases/download/v1.08/Planning_to_ICS_V1.08_macOS.dmg).

1. Ouvrir le fichier `.dmg` téléchargé.
2. Faire glisser `Planning To ICS` dans le dossier **Applications**.
3. Ouvrir l'application depuis **Applications**.

Le paquet macOS contient Python et les dépendances nécessaires. Il n'est pas encore signé par Apple : au premier lancement, faire un clic droit sur l'application, choisir **Ouvrir**, puis confirmer.

## Usage

Lancer `Planning to ICS` depuis le menu Démarrer sous Windows ou depuis le dossier Applications sous macOS.

L'application s'ouvre dans une fenêtre dédiée avec :

- le choix du dossier où se trouvent les plannings PDF par défaut ;
- la liste de tous les PDF trouvés dans ce dossier et ses sous-dossiers ;
- le choix manuel d'un PDF ailleurs sur le disque avec `Parcourir` ;
- la liste des techniciens du PDF choisi ;
- un diagnostic indiquant si le planning est compatible, scanné ou non reconnu ;
- le choix du dossier d'export du `.ics` ;
- la recherche et l'export de plusieurs techniciens, avec un ICS par personne et un ZIP regroupé ;
- un diagnostic des événements, doublons, chevauchements et vacations de nuit ;
- le glisser-déposer d'un PDF ;
- un bouton de prévisualisation ;
- la modification des événements après prévisualisation ;
- un bouton de génération ICS ;
- des boutons pour ouvrir l'ICS ou afficher son dossier après génération ;
- un bouton `Quitter l'application` et une fermeture complète avec la croix de la fenêtre.
- un mode sombre et un bouton de vérification de la dernière version publiée ;
- l'export, l'import et la réinitialisation des réglages mémorisés.

Le dossier des plannings et le dossier d'export sont mémorisés entre deux lancements.

Après `Prévisualiser`, les événements extraits apparaissent dans un tableau modifiable. Tu peux décocher un événement, changer le résumé, les dates, les heures ou la description, puis cliquer sur `Exporter ICS modifié`.

Une fois le fichier `.ics` généré, il faut l'importer dans l'agenda voulu. L'application crée le fichier ICS, mais elle ne l'ajoute pas automatiquement dans Outlook, Google Agenda ou un autre calendrier.

## Tutoriel vidéo

Tutoriel vidéo sous-titré : [télécharger le tutoriel V1.08](https://github.com/Mamat79/Planning-To-ICS/releases/download/v1.08/Planning_to_ICS_V1.08_Tutoriel.mp4).

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

Le glisser-déposer copie le PDF dans le dossier des plannings sélectionné afin
qu'il reste disponible dans la liste au prochain lancement.
