# Utilisation

Le flux métier validé est :

1. Prise en charge du véhicule et devis initial.
2. Accord du client et expertise assurance si nécessaire.
3. Achat des approvisionnements nécessaires.
4. Réparation.
5. Modification du devis si de nouveaux travaux sont nécessaires.
6. Nouvel accord client avant continuation.
7. Finition.
8. Facturation finale.
9. Livraison et règlement.

## Paramètres

La page `Paramètres > Entreprise` permet au gérant de modifier les informations utilisées dans les documents : raison sociale, adresse, téléphones, email, RC, IF, ICE, patente, RIB et agrément SNTL.

La page `Paramètres > Système` centralise les valeurs de base : TVA, commission SNTL, délai de paiement par défaut et charges fixes mensuelles.

## Clients et véhicules

La page `Clients` permet de rechercher un client, créer une nouvelle fiche client et ajouter un premier véhicule dès la création.

Les types de clients utilisés sont uniquement : `Particulier`, `Administration` et `Administration SNTL`.

Les numéros de téléphone sont vérifiés au format marocain. Un numéro invalide bloque la création du client ou du dossier.

La fiche client affiche les informations principales et la liste des véhicules associés. Un véhicule peut aussi être ajouté depuis cette fiche.

La page `Véhicules` permet de retrouver rapidement un véhicule par immatriculation, marque, modèle ou nom du client.

## Dossiers atelier et devis

La page `Dossiers réparation` pilote le flux atelier réel :

1. Le personnel du garage ouvre une prise en charge.
2. Le client et le véhicule peuvent être créés directement dans ce ticket.
3. Les blocs `Client déjà enregistré` et `Véhicule déjà enregistré` ne s'affichent que si le mode `Existant` est coché.
4. Le système enregistre le client, le véhicule et le dossier atelier dans la base.
5. Pour un client `Particulier`, l'assurance liée à la prise en charge peut être enregistrée dans le ticket.
6. Pour un client `Administration SNTL`, le type d'immatriculation d'un nouveau véhicule passe automatiquement en `Administrative`.
7. Le dossier démarre au statut `En attente de devis`.
8. Un devis initial versionné est créé.
9. Les lignes du devis sont ajoutées avec le bouton `Ajouter une ligne`.
10. Le bouton `Ajouter main d'oeuvre` ajoute rapidement une ligne de main d'oeuvre avec son coût HT.
11. Pour les clients `Particulier` et `Administration`, chaque ligne peut préciser si la pièce est `Neuf` ou `Occasion`.
12. Pour un client `Administration SNTL`, les pièces sont toujours considérées comme neuves et le choix neuf/occasion n'est pas affiché.
13. Le dossier passe en `En attente d'accord`.
14. Seule la dernière version du devis peut être approuvée ou refusée.
15. Après accord client, le dossier passe en `En réparation`.
16. Si un coût supplémentaire apparaît, le dossier est mis en pause.
17. Une nouvelle version de devis est créée en reprenant les lignes du dernier devis pour modification.
18. Après refus d'un devis, le dossier revient en attente de devis avec deux actions claires : créer une version corrigée ou annuler le dossier.
19. Quand les travaux sont terminés, le dossier passe en `Terminé`.
20. La facture finale est générée uniquement depuis le dernier devis approuvé.
21. La facture suit ensuite son propre flux : `Émise`, `Livrée`, puis `Réglée`.

La liste des dossiers atelier permet de rechercher par numéro de dossier, nom ou code client, marque, modèle, immatriculation ou demande client.

## Facturation finale, livraison et règlement

La page `Factures` affiche toutes les factures finales générées depuis les dossiers terminés.

Une facture ne peut pas être créée tant que la réparation n'est pas terminée. Elle reprend automatiquement les montants HT, TVA et TTC du dernier devis approuvé.

Après génération :

1. La facture est au statut `Émise`.
2. L'équipe marque le véhicule comme livré.
3. Le règlement final est enregistré avec le mode de paiement et une référence éventuelle.

Le flux complet du dossier est clôturé quand la facture est `Réglée`.
