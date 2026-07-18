# Journal des modifications

## V1.08

- trois parcours distincts : export direct, prévisualisation modifiable et ajout de techniciens ;
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
