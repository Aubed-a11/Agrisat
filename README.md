# AGRISAT

Plateforme d'assurance agricole indicielle par satellite pour les producteurs de coton et de maïs de 27 communes du Nord Bénin (Alibori, Borgou, Atacora, Donga). Elle couvre la chaîne complète : données satellitaires, indices par phase, modèles de rendement, conception et tarification des contrats, risque de portefeuille, souscription, alertes, déclenchement et paiement mobile money.

Le cahier des charges est dans `docs/Cahier_des_charges_AGRISAT.pdf`.

## Lancement rapide

Prérequis : Python 3.11 ou plus, Node.js 18 ou plus.

```bash
npm install            # installe concurrently
npm run setup          # dépendances Python et web, puis pipeline de données (environ 2 minutes)
npm run dev            # API sur le port 8000 et application web sur http://localhost:5173
```

Les données traitées sont déjà incluses dans l'archive : `npm run setup` peut être remplacé par `pip install -r requirements.txt && npm install --prefix web`.

Comptes de démonstration, mot de passe `agrisat2026` : `assureur`, `coop`, `imf`, `partenaire`, `admin`.

Production en une commande : `npm start` (compile le front, l'API sert l'application sur le port 8000), ou `docker compose up --build`.

Tests : `npm test`.

## Mode de données actuel : réel

Le projet livré tourne sur données réelles (`data/processed/meta.json`, `data_source: reel`) :
pluie CHIRPS par commune (HDX, WFP) recalée au pas journalier avec NASA POWER, température et ET0 NASA POWER,
NDVI WFP par commune, rendements du maïs DSA 1995 à 2023, FAOSTAT maïs et coton, Banque mondiale.

Principaux enseignements, détaillés dans la page « Données réelles » et `data/processed/findings.json` :
l'indice pluie ne suit pas les pertes réelles du maïs (corrélation moyenne de -0,11, aucune commune au dessus du seuil de 0,30)
et ne peut pas être vérifié pour le coton faute de rendements communaux (corrélation de 0,08 avec les pertes nationales FAOSTAT).
Le produit commercialisé pour le maïs est donc le contrat **rendement par zone**, tarifé sur les statistiques DSA.
Les indemnités de ce produit se calculent dès la publication des statistiques de campagne (campagne 2023 calculable,
campagne 2025 en attente).

Mise à jour des données : sur une machine connectée, `python telecharger_donnees_agrisat.py`, puis copier
`agrisat_donnees.zip` à la racine du projet et lancer `npm run donnees:importer`.
Pour revenir aux données synthétiques de démonstration : `python -m agrisat_core.pipeline --source synthetic`.

## Données réelles déjà intégrées

Le dossier `data/external/` contient des données réelles, utilisées dès maintenant (page « Données réelles ») :

| Fichier | Contenu | Source |
| --- | --- | --- |
| `dsa_mais_communes.csv` | Superficie, production et rendement du maïs, 27 communes, 1995 à 2023 | DSA MAEP, publié dans le dépôt GitHub steftdg/ZeaMays-Yield-Prediction-Benin (à citer) |
| `faostat_benin_mais.csv` | Maïs au Bénin, 1961 à 2024 | FAOSTAT |
| `prix_mais_detail.csv` | Prix de détail du maïs à Cotonou, Natitingou et Parakou, 2013 à 2024 | Dépôt GensericAguidissou/Analyse-Price-Maize-Benin (MIT) |
| `communes_nord.geojson`, `centroids.json` | Limites officielles des 27 communes | geoBoundaries (CC BY 4.0) |
| `sources.json` | Catalogue des sources, licences et état | |

Ces données alimentent un contrat d'assurance **rendement par zone** pour le maïs, tarifé sur les rendements communaux observés (contrôle qualité, tendance, bootstrap, diversification entre communes), et fixent le prix du maïs à 180 FCFA par kg (85 % du prix de détail du Nord).

Pour compléter avec le climat réel, le NDVI, la pluie CHIRPS par commune, FAOSTAT et Kaggle (sur votre machine, avec internet) :

```bash
pip install requests kaggle faostat
python -m agrisat_core.sources.fetch_open_data all
python -m agrisat_core.pipeline --source real
```

Le pipeline tourne alors sur le climat réel NASA POWER et les rendements réels du maïs. Aucune source ouverte de rendements communaux du coton n'a été trouvée : le contrat coton reste conçu sur le climat seul et marqué non validé tant que ces données ne sont pas fournies.

## Données de démonstration

Par défaut, la plateforme tourne sur des **données synthétiques** générées par `agrisat_core/synthetic.py` (pluie par chaîne de Markov et loi Gamma, erreur satellitaire, NDVI, rendements par bilan hydrique). Elles reproduisent le climat du Nord Bénin mais ne doivent jamais servir à une tarification réelle. Un bandeau le rappelle dans l'application.

Pour passer aux données réelles :

1. `pip install earthengine-api`, puis `earthengine authenticate` et `export GEE_PROJECT=...`
2. `python -m agrisat_core.gee.extract_gee --start 1981 --end 2025` (CHIRPS, MODIS MOD13Q1, ERA5 Land, masque WorldCover, limites geoBoundaries)
3. Placer les rendements communaux du MAEP dans `data/raw/rendements_communes.csv` (modèle fourni) et, si disponible, l'exposition dans `data/raw/exposition.csv`
4. `python -m agrisat_core.pipeline --source real`

## Architecture

| Dossier | Contenu |
| --- | --- |
| `agrisat_core/` | Phénologie, indices, modèles ML (régression pénalisée, forêt aléatoire, XGBoost, SHAP), générateur stochastique de pluie, contrats, tarification Monte Carlo, risque de base, portefeuille, extraction Earth Engine |
| `api/` | FastAPI : authentification par rôle, suivi de saison, cotation, producteurs, polices, indemnités, paiements, réclamations, SMS, USSD, rapports PDF et Excel, paramètres, journal d'audit |
| `web/` | React, Vite, Tailwind, Leaflet, Recharts, icônes lucide-react |
| `data/processed/` | Sorties du pipeline lues par l'API |
| `tests/` | Tests du moteur actuariel et parcours complet de l'API |

## Intégrations externes

Sans configuration, paiements et SMS sont simulés localement. Variables dans `.env.example` :

* `FEDAPAY_SECRET_KEY` : versements et encaissements en sandbox FedaPay (MTN MoMo, Moov Money, Celtiis Cash)
* `AT_USERNAME`, `AT_API_KEY` : SMS Africa's Talking
* `DATABASE_URL` : PostgreSQL en production (SQLite par défaut)

Le point d'accès USSD `POST /api/ussd` suit le format des agrégateurs USSD (sessionId, serviceCode, phoneNumber, text).

Les messages en bariba, dendi, ditammari et fon ne sont pas traduits automatiquement : tant qu'une traduction n'est pas validée par des locuteurs natifs dans `api/services/sms.py`, le message part en français avec une mention.

## Méthode, en bref

* Démarrage de saison : premier jour après le 15 avril avec 20 mm en 3 jours sans séquence sèche de 7 jours dans les 30 jours suivants.
* Indice contractuel : pluie cumulée par phase, plafonnée à 50 mm par jour. Indemnité linéaire entre seuil de déclenchement et seuil de sortie.
* Seuils optimisés par commune en maximisant l'équivalent certain du revenu d'un producteur averse au risque (utilité CRRA), sous plafond de taux de prime.
* Prime pure par 10 000 saisons simulées ; prime commerciale avec coût du capital alloué après diversification (CVaR 99,5 %) et frais ; subvention de 80 % paramétrable.
* Contrat non commercialisé si plus de 20 % des années de forte perte n'auraient pas été indemnisées.
