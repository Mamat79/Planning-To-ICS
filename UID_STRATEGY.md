# Strategie des UID ICS

La V1.08 attribue a chaque evenement un `UID` deterministe construit a partir de :

- la personne normalisee ;
- la semaine et l'annee du planning ;
- la date et les heures de debut et de fin ;
- le titre de la mission normalise.

Le chemin du PDF, sa date de copie, sa date de modification et l'heure de
l'export ne sont pas utilises. Le meme evenement conserve donc son `UID` si le
PDF est deplace ou si l'ICS est genere une nouvelle fois.

## Evolutions d'un evenement

- titre modifie : nouvel `UID`, car il peut s'agir d'une autre mission ;
- description modifiee : `UID` conserve ;
- horaires ou date modifies : nouvel `UID` ;
- technicien modifie : nouvel `UID` ;
- evenement supprime : aucun nouvel evenement n'est produit dans le nouvel ICS.

Les exports repetes ecrivent le meme fichier ICS et conservent `DTSTAMP` au
format UTC pour rester compatibles avec Outlook. Un import manuel ne garantit
pas que tous les logiciels de calendrier supprimeront automatiquement un
evenement qui n'existe plus dans le nouvel export.
