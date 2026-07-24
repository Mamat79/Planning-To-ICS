# Journal des modifications

## V1.09

- notice complétée avec les procédures d'importation pour le nouvel Outlook, Outlook sur le web et Outlook classique ;
- export multi-semaines : sélection de plusieurs PDF hebdomadaires et création d'un seul ICS pour le technicien choisi ;
- prévisualisation et modification de chaque semaine avant l'export multi-semaines ;
- ouverture explicite du fichier ICS avec l'application d'agenda par défaut ;
- avertissement contre le glisser-déposer dans la grille du nouvel Outlook, qui peut mal décoder les accents malgré un fichier UTF-8 valide ;

## V1.08

- descriptions simplifiées : mission et pause uniquement, sans horaires ni durée totale issus du PDF ;
- quatre parcours distincts : export direct, prévisualisation modifiable, plusieurs semaines et ajout de techniciens ;
- tableau à cases à cocher pour sélectionner plusieurs techniciens ;
- sélection automatique des techniciens partageant une mission avec le technicien principal ;
- prévisualisation et modification séparées pour chaque technicien avant l'export multiple ;
- lecture groupée du PDF : 65 techniciens analysés en quelques secondes au lieu de relire le document pour chaque personne ;
- notice PDF intégrée à l'installateur et publiée séparément ;
- paquet Windows reconstruit avec Python 3.12 autonome et testé après installation ;
- correctif urgent : activation des boutons et du mode sombre après correction du JavaScript de l'interface ;
- glisser-déposer fonctionnel dans WebView/Chrome, avec copie du PDF dans le dossier des plannings ;
- ajout du glisser-déposer des PDF ;
- export de plusieurs techniciens, avec recherche, sélection globale, un ICS par personne et un ZIP ;
- diagnostic des événements, doublons, chevauchements et vacations de nuit ;
- réglages exportables, importables et réinitialisables ;
- mode sombre et vérification manuelle de la dernière version publiée ;
- identifiants ICS stables lorsque le PDF est déplacé ou réexporté ;
- possibilité d'installer la version en parallèle d'une version existante ;
- correctifs de compatibilité macOS et de tests multiplateformes.

## V1.07

- installateur Windows avec choix du dossier et raccourcis ;
- paquet macOS non signé ;
- gestion des accents en UTF-8 sans BOM pour Outlook ;
- sélection explicite du PDF et mémorisation des dossiers.
