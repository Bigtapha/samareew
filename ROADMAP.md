# Feuille de route — SamaReew

_Synthèse du brainstorming du 30/09/2026. Document vivant : cocher les tâches au fil de l'eau
et noter les décisions dans la section « Journal des décisions »._

---

## 1. Vision

Passer d'une étude de cas (expansion urbaine de la région de Dakar) à un **site national,
grand public, construit sur des données ouvertes**, qui permet de **comparer les villes
sénégalaises** entre elles.

Double objectif : **progresser techniquement** (télédétection, data engineering, web) et
**produire quelque chose d'utile** et compréhensible par tous.

**Modèle de référence : [Our World in Data](https://ourworldindata.org)**
- une **page thème** (texte court, points clés chiffrés, graphiques intégrés) ;
- **chaque graphique a sa page**, avec les onglets _Graphique / Carte / Tableau / Sources / Télécharger_ ;
- les **villes sont des entités comparables** qu'on sélectionne, comme les pays chez OWID ;
- l'**URL conserve l'état** (villes, années, onglet), pour partager un lien précis ;
- **tout est téléchargeable**, sourcé et sous licence ouverte ;
- des **titres qui affirment** (« Touba s'étend plus vite que Dakar ») plutôt que des titres techniques.

Autres références consultées : Atlas of Urban Expansion (NYU / Lincoln Institute),
Africapolis (OCDE / CSAO), ONS Census Maps (Royaume-Uni), Tree Equity Score, Géorisques.

---

## 2. Décisions prises

| Sujet | Décision |
|---|---|
| Public | Grand public, données **open source** uniquement |
| Nom | **SamaReew** (_sama réew_, « mon pays » en wolof) ; dépôt `samareew` |
| Thème de départ | **Expansion urbaine**, un seul thème pour la v1 |
| Villes (v1) | **Dakar, Touba, Thiès, Mbour** (capitale, ville religieuse de l'intérieur, carrefour, littoral) |
| Modèle de classification | **Un Random Forest national** (entraîné sur les 4 zones) ; adaptation par ville seulement si nécessaire |
| Définition d'une ville | Règle **homogène** : agglomération urbaine GHSL 2025 + tampon de 2 km, figée dans `zones/` |
| Unité grand public | **La commune** ; découpage plus fin uniquement si nécessaire (**Touba** : secteurs anneaux × directions ou grille hexagonale) |
| Licences | **MIT** pour le code, **CC BY 4.0** pour les données produites |
| Organisation du code | **Un seul dépôt**, avec une frontière stricte `pipeline/` → `outputs/` → `site/` ; séparation en deux dépôts plus tard (voir §6) |
| Outils du site | Site **statique** généré par **Astro** (pages HTML légères, JavaScript chargé seulement pour les graphiques et les cartes), graphiques **Observable Plot** (SVG), cartes **MapLibre GL** avec des tuiles **PMTiles** (un fichier par couche, sans serveur) ; **fond de carte Protomaps auto-hébergé** (extrait OpenStreetMap des zones, variantes « white » en clair et « black » en sombre, polices et icônes servies avec le site) ; Node 24 et Astro 7 ; hébergement GitHub Pages ; pensé d'abord pour le téléphone et les connexions lentes |
| Période | Saisons sèches **2016 à 2026** (1er novembre – 31 mai) ; indicateurs publiés **jusqu'à l'avant-dernière année** (2025), la dernière sert de confirmation |
| Type de croissance | Règle de l'**Atlas of Urban Expansion** : emprise de départ = bâti urbain (≥ 25 % de bâti dans un cercle de 1 km²) + frange de 100 m + trous enclavés < 200 ha ; nouveau bâti dedans = **densification**, nouvel îlot qui la touche = **extension**, sinon **saut** ; par période (2016→2020, 2020→2025, 2016→2025) |
| Population | **WorldPop Global 2** (R2025A, annuel, 100 m, contraint au bâti, CC BY 4.0) ; RGPH-5 2023 en contrôle sur les communes entièrement dans les zones |
| Échelle des indicateurs de population | WorldPop (population, m²/habitant, ODD 11.3.1) **par ville seulement** ; par commune, la **population recensée 2023** (RGPH-5, ANSD, CC BY 4.0) et les m² bâtis par habitant recensé, pour les communes entièrement dans les zones |
| Validation | Nouvel **échantillon national**, même plan dans chaque ville : 120 points par ville (480 au total) en 5 strates, non bâti 40, bâti 2016 32, puis nouveau bâti découpé par type de croissance 2016→2025 (densification 16, extension 16, saut 16) ; photo-interprétation à l'aveugle aux deux dates 2016 et 2025, année d'apparition notée si possible ; l'échantillon de Dakar (260 points) n'est **plus à étiqueter** ; publication : valeurs de la carte dans les tableaux, précision dans les fiches, surfaces corrigées avec leur marge à côté, types de croissance **indicatifs**, 2025 **provisoire** |

---

## 3. Principes directeurs

1. **La comparabilité avant tout** : même méthode, même définition de ville, mêmes indicateurs partout.
2. **Honnêteté sur l'incertitude** : chaque indicateur affiche sa fiabilité ; la validation est un argument de confiance.
3. **Langage simple** : « surface bâtie » plutôt que « classe 2 » ; la méthode détaillée est à un clic.
4. **Mobile d'abord et léger** : l'internet mobile est cher au Sénégal ; tuiles chargées à la demande, pages sobres.
5. **Ton neutre** sur les quartiers (« faible couverture végétale », pas « quartier défavorisé »).
6. **Tout est reproductible** : un paramètre dans la configuration, pas dans le code.

---

## 4. Architecture cible

### 4.1 Chaîne de traitement

| Étape | Rôle |
|---|---|
| 1. Entraînement | Échantillons équilibrés par ville et par classe → Random Forest national, évaluation par ville |
| 2. Classification | Composites de saison sèche par ville et par année → une pile annuelle par ville |
| 3. Post-traitement | Filtre de cohérence temporelle → année d'urbanisation par pixel |
| 4. Indicateurs | Calcul des indicateurs (§4.3) par ville, commune et secteur |
| 5. Validation | Tirage stratifié national, photo-interprétation, précision par ville avec marge d'erreur |
| 6. Contrôle croisé | Comparaison avec GHSL (GHS-BUILT) et Google Open Buildings |
| 7. Données du site | Export au format d'échange (§4.2) |

### 4.2 Format d'échange (le contrat entre traitements et site)

- **Une table « longue »** : `indicateur | ville | commune/secteur | année | valeur`
- **Une fiche par indicateur** : titre grand public, unité, définition en une phrase, source,
  licence, lien méthode, niveau de fiabilité, palette.
- **Des cartes par ville** (couches de périodes, tuiles) : depuis la version 0.2, dans `outputs/site/` (étape 7) : une archive PMTiles par couche pour les quatre villes, l'image satellite 2025 (clé `images`, ajout compatible), les limites en GeoJSON simplifié, les erreurs connues signalées sur les cartes (clé `notes`, ajout compatible du 12/10/2026), le résumé de la validation (croissance corrigée `growth` et comparaison des villes `growth_comparison`, ajout compatible du 21/10/2026), et un `manifest.json` qui liste les fichiers, les légendes et les licences.
- **Un numéro de version** du format dans les métadonnées (`FORMAT_VERSION`, 0.2 depuis le 09/10/2026).

Ajouter une ville = ajouter des lignes. Ajouter un indicateur = ajouter une fiche.
Le site ne change pas.

### 4.3 Indicateurs de la v1

| Indicateur | Question grand public |
|---|---|
| Surface bâtie (ha) | Quelle taille fait la ville ? |
| **Croissance base 100 (2016 = 100)** | Quelle ville grandit le plus vite ? |
| Nouveau bâti par an (ha) | La croissance accélère-t-elle ? |
| **Type de croissance** (densification / extension / saut) | La ville se remplit-elle ou s'étale-t-elle ? |
| **Direction de croissance** (8 secteurs) | Vers où la ville pousse-t-elle ? |
| Profil par anneaux de distance au centre | La croissance se fait-elle de plus en plus loin ? |
| **m² bâtis par habitant / ODD 11.3.1** | La ville consomme-t-elle plus d'espace que sa population n'augmente ? |

### 4.4 Structure du dépôt

```
samareew/
├── config/        settings (commun) + cities (une entrée par ville)
├── zones/         enveloppes figées, communes, secteurs (Touba)
├── pipeline/      étapes 1 à 7
├── src/           fonctions partagées (GEE, post-traitement, indicateurs)
├── data/          (ignoré par git) bruts et intermédiaires
├── outputs/       tables/ · cities/<ville>/ · validation/
├── site/          site public — ne lit QUE outputs/
└── tests/
```

Les gros fichiers (GeoTIFF, tuiles, images satellite) restent **hors de git**
(releases GitHub ou stockage externe).

### 4.5 Arborescence du site

```
Accueil            carte du Sénégal, cercles proportionnels = croissance des villes
├── Expansion urbaine     page thème (points clés + graphiques)
├── Graphiques            un graphique = une page (Graphique / Carte / Tableau / Sources / Télécharger)
├── Villes                une fiche par ville (même gabarit) : carte, chiffres clés, communes/secteurs
├── Données & méthode     téléchargements, validation, limites, licences
└── À propos
```

---

## 5. Jalons

### J0 — Mise en place
- [x] `git init` et premier commit de l'état actuel (projet Dakar)
- [x] Choisir le nom national, renommer le projet et le dépôt (SamaReew ; dossier local `samareew`)
- [x] Créer le dépôt GitHub : [Bigtapha/samareew](https://github.com/Bigtapha/samareew) (privé pour l’instant, à rendre public avant J6)
- [x] Choisir les licences : MIT pour le code (`LICENSE`), CC BY 4.0 pour les données (`LICENSE-DATA.md`)

**Critère de fin** : l'état actuel est versionné et sauvegardé en ligne.

### J1 — Définition des zones d'étude
- [x] Récupérer les enveloppes d'agglomération pour les 4 villes (GHSL GHS-SMOD 2025, agglomération urbaine ; Africapolis non téléchargeable par script)
- [x] Choisir la règle de tampon : 2 km fixes pour toutes les villes, terre uniquement (partage à mi-distance si deux zones se chevauchent)
- [x] Définir le centre de chaque ville (pour directions et anneaux) : lieu du cœur historique, `zones/centres.geojson`
- [x] Récupérer les limites communales : OpenStreetMap corrigé (OCHA et geoBoundaries s'arrêtent aux arrondissements)
- [x] Vérifier les communes de Thiès : aucune source officielle ouverte trouvée (GADM / mapSenegal testé : ancien découpage, licence non ouverte) ; on garde OSM corrigé, imprécision documentée
- [x] Concevoir le découpage en secteurs de Touba : disque central 0–2 km + anneaux de 2 km × 8 directions autour de la Grande Mosquée (47 secteurs, `zones/sectors.geojson`)
- [x] Documenter ces choix dans le journal des décisions

**Critère de fin** : `zones/` contient les 4 zones figées, les communes et les secteurs, tous documentés.

### J2 — Modèle national et classification
- [x] Réorganiser le code selon la structure cible (configuration par ville) : `config/`, `pipeline/s0…s3`, résultats Dakar dans `outputs/legacy_dakar/`
- [x] Échantillonnage d'entraînement équilibré par ville × classe (12 000 points)
- [x] Entraîner le Random Forest national et l'évaluer par ville (concordance 0,924, de 0,906 à Dakar à 0,946 à Touba)
- [x] Classer 2016–2026 pour les 4 villes (saison 1er nov. – 31 mai, publication jusqu'en 2025)
- [x] Contrôle qualité : nombre de scènes par ville et par an, repérer les années faibles (2017 : environ deux fois moins de scènes partout ; 2026 non filtrée)

**Critère de fin** : 4 piles annuelles et un rapport d'évaluation par ville.

### J3 — Indicateurs et contrôle croisé
- [x] Post-traitement (filtre temporel) pour chaque ville (fait pendant J2)
- [x] Définir les règles du type de croissance (seuil extension / saut) : règle Atlas of Urban Expansion
- [x] Choisir la source de population (WorldPop ou RGPH-5) : WorldPop Global 2, RGPH-5 en contrôle
- [x] Contrôler WorldPop avec le RGPH-5 2023 (communes entièrement dans les zones ; licence ANSD : CC BY 4.0) : totaux bons, répartition entre communes fausse (×0,35 à ×2,9), METHODOLOGIE §13.4
- [x] Calculer les indicateurs v1 (§4.3) par ville, commune et secteur (aussi par direction et anneau ; `pipeline/s4_indicators.py`)
- [x] Comparer avec GHSL et Open Buildings (`pipeline/s6_crosscheck.py`, METHODOLOGIE §13 ; écart GHSL : époques interpolées)
- [x] Produire la table longue et les fiches indicateurs (`outputs/tables/`, format 0.1)

**Critère de fin** : la table longue est complète pour les 4 villes, et les écarts avec GHSL sont expliqués.

### J4 — Validation nationale
- [x] Décider le plan d'échantillonnage : 120 points par ville, nouveau bâti découpé par type de croissance (densification / extension / saut), même plan partout, année d'apparition notée si possible (METHODOLOGIE §14.1)
- [x] Tirer l'échantillon stratifié ville × strate (480 points, `pipeline/s5_validation.py --draw` → `outputs/validation/`)
- [x] Confirmer la règle d'étiquetage (METHODOLOGIE §14.2) : pixel bâti si au moins la moitié du carré est construite ; parcelle seulement clôturée = non bâti
- [x] Photo-interprétation à l'aveugle dans Google Earth Pro : remplir `outputs/validation/labels.csv` à partir de `points.kml`, sans ouvrir `sample_key.csv` ; noter `year_built` pour le nouveau bâti quand les images le permettent
- [x] Calculer la précision par ville (avec marge d'erreur) et la précision nationale : `python -m pipeline.s5_validation` → `outputs/validation/accuracy.json`
- [x] Lire les résultats sur les points faibles de J3 : saut par ville et au niveau national, surface corrigée du nouveau bâti, dates (pic 2017 de Touba et de Dakar, année 2025)
- [x] Intégrer les résultats : METHODOLOGIE §14.4 (et §9, §10), fiabilité des fiches indicateurs (`config/indicators.py`, `_MAP_RELIABILITY`, puis relancer l'étape 4), README

- [x] Seconde lecture à l'aveugle des 228 points non bâtis en 2025 : occupation du sol dans une liste fermée (`outputs/validation/cover_2025.csv`, `cover_2025.kml`, METHODOLOGIE §14.2)
- [x] Précision tolérante (urbanisation en cours comptée comme bâti) et occupation du nouveau bâti cartographié : relancer `python -m pipeline.s5_validation`, puis METHODOLOGIE §14.4, fiches indicateurs, README

**Critère de fin** : chaque ville a une précision pondérée par la surface et sa marge d'erreur.

> J3 et J4 peuvent se chevaucher : étiqueter pendant que les indicateurs se construisent.

### J5 — Site v1
- [x] Choisir les outils : Astro, Observable Plot, MapLibre GL + PMTiles (§2)
- [x] Étape 7, données du site (§4.1) : couches cartographiques (année d'urbanisation, types de croissance) en PMTiles et limites (zones, communes, secteurs de Touba) dans `outputs/`, car le site ne lit que `outputs/` ; surfaces corrigées de la validation dans le format d'échange
- [x] Créer `site/` avec Astro 7 (Node 24 installé avec nvm) : lecture de `outputs/site/manifest.json` et de `outputs/tables/` à la construction, jamais de `pipeline/` ni de `src/` ; `npm run sync` copie dans `site/public/data/` les fichiers que le navigateur charge (tuiles, limites, tables)
- [x] Choisir le fond de carte : Protomaps auto-hébergé, « white » en clair et « black » en sombre (§9, 09/10/2026) ; reconstruit par `npm run basemap` (outil `pmtiles` requis), ignoré par git
- [x] Gabarit de graphique OWID : une page par indicateur (`/graphiques/<indicateur>`), onglets Graphique / Carte / Tableau / Sources / Télécharger, sélection des villes, niveaux ville / commune / secteur, URL avec état, CSV par graphique
- [x] Téléchargement du graphique en image (SVG, PNG, avec titre et source) ; directions et anneaux ajoutés au gabarit comme niveaux (`niveau=directions`, `niveau=anneaux`), dans leur ordre naturel
- [x] Première carte sur les couches PMTiles (`/villes/<ville>`), légende et tableau des surfaces à côté, précision de la validation ; chargée seulement quand elle approche de l'écran
- [x] Image satellite sous les couches (case à cocher, désactivée par défaut) : composite Sentinel-2 en couleurs naturelles de la saison sèche 2025, celui qu'a classé le modèle, en tuiles WebP produites par l'étape 7 ; curseur d'opacité des couches (environ 30 Ko par vue de ville, 100 à 220 Ko tout zoomé)
- [x] Image satellite de Dakar : quota gratuit d'Earth Engine épuisé en octobre (mode restreint jusqu'au 1er novembre) ; exportée vers Google Drive et déposée dans `data/cities/dakar/true_colour_2025.tif` le 09/10/2026 (emprise vérifiée), étape 7 relancée : 4,8 Mo pour les quatre villes
- [x] Page thème « Expansion urbaine » (`/expansion-urbaine`) : 5 points clés dont les chiffres et les classements sont calculés à la construction depuis `outputs/`, 4 graphiques en SVG statique (sans JavaScript), types de croissance, fiabilité
- [x] Les graphiques des indicateurs v1 : une page par indicateur (15), les mêmes fonctions de dessin pour le gabarit interactif et les pages statiques (`site/src/lib/charts.ts`)
- [x] 4 fiches villes (même gabarit) : chiffres clés avec surface corrigée, carte, surface et nouveau bâti par année, nouveau bâti par direction et par anneau, tableau par commune (recensement 2023 quand il existe), fiabilité
- [x] Fiche Touba : agglomération Touba-Mbacké (« un seul ensemble bâti ») ; tableaux par secteur et par commune (sections repliables)
- [x] Page Données & méthode (`/donnees`) : méthode en bref, téléchargements, sources et licences, validation par ville, limites, citation ; page À propos
- [x] Préciser dans les fiches que les chiffres par commune reposent sur des limites OpenStreetMap (ODbL, « © contributeurs OpenStreetMap »)
- [x] Ne pas classer Dakar, Touba et Mbour entre elles sur la densification (écarts de 1–2 points, inférieurs à la sensibilité aux paramètres, METHODOLOGIE §11.2) : dit sur la page thème
- [x] Chaque carte a sa légende (couleurs et libellés de `manifest.json`) et un tableau à côté (fiches) ou un onglet Tableau (gabarit) : l'orangé clair et le vert d'eau sont peu contrastés sur fond clair (METHODOLOGIE §15.1)
- [x] Afficher les surfaces corrigées de la validation à côté des valeurs de la carte (`outputs/site/validation.json`), types de croissance « indicatifs », 2025 « provisoire » (§9, 07/10/2026) : page thème, fiches, Données & méthode
- [x] Tests sur mobile et connexion lente (09/10/2026, 360 px, 4G lente et 3G simulées, fichiers compressés comme GitHub Pages) : aucune page ne déborde ; accueil, thème et Données & méthode font 3 à 8 Ko et s'affichent en moins d'une seconde en 3G ; une fiche ville fait 24 Ko tant que la carte n'est pas atteinte ; une carte coûte environ 500 Ko la première fois (MapLibre seul : 430 Ko), prête en 6,5 s en 4G lente et 13 s en 3G
- [x] Contrôle général des chiffres et des textes (09/10/2026) : tableau du README et fiches recoupés avec `outputs/` ; formulation corrigée partout (site, README, METHODOLOGIE, fiches d'indicateurs) : le nouveau bâti cartographié est à 51 % du bâti vraiment nouveau et à 9 % du bâti déjà là en 2016 (et non « bâti en 2025 ») ; la fiabilité du nouveau bâti est décrite ville par ville (lotissements à Touba et Mbour, fausses détections à Thiès, les deux à Dakar) ; liens de méthode sans ancre (GitHub ne reconnaît pas `#8`)
- [x] Accueil : les quatre villes à la même échelle (silhouettes du bâti 2016 et du nouveau bâti, une image par ville produite par l'étape 7, 91 Ko en tout, chargées en différé) ; page affichée en 0,4 s et complète en 2,3 s en 3G
- [ ] Accueil, en option : carte du Sénégal avec cercles proportionnels (surface bâtie 2025, cercle intérieur 2016), en SVG statique, contour Natural Earth (domaine public) à ajouter à l'étape 7
- [x] Relecture du site par l'utilisateur (textes, titres des points clés, chiffres) : validée le 09/10/2026 ; J5 terminé

**Critère de fin** : le site fonctionne en local, il est lisible sur téléphone et chaque chiffre renvoie à sa source.

### J6 — Publication
- [x] Dépôt GitHub public (13/10/2026), après un second audit : adresse e-mail des commits remplacée par l'adresse « noreply » de GitHub (historique réécrit, dépôt recréé), `CLAUDE.md` et `.vscode/` retirés et ignorés
- [x] Audit avant publication (09/10/2026) : aucun secret, chemin personnel ni gros fichier dans tout l'historique (plus gros fichier 2 Mo, dépôt 8,8 Mo) ; ancienne carte web de Dakar (`docs/`) retirée ; `sample_key.csv` publié (validation terminée)
- [x] Étape 8, `python -m pipeline.s8_release` : `samareew-data.zip` (tableaux, GeoTIFF par ville, limites, validation et étiquettes, contrôle croisé, README, licence, citation ; 6 Mo) et `site-assets.tar.gz` (PMTiles de l'étape 7 et fond de carte ; 22,5 Mo), avec `SHA256SUMS` ; noms fixes pour que `releases/latest/download/…` reste un lien valable
- [x] Workflow `.github/workflows/deploy.yml` : récupère `site-assets.tar.gz` dans la dernière release, vérifie la somme, `npm ci`, `check`, `build`, déploie sur Pages ; simulé dans un clone propre (25 pages construites)
- [x] Fausse détection au nord-est de Thiès (exploitation agricole irriguée de 75 ha à Fandène, classée en bâti depuis 2018, repérée le 12/10/2026) : laissée sur la carte, entourée et expliquée sur la fiche de Thiès (`config/map_notes.py`, étape 7, METHODOLOGIE §14.4 et §15.6) ; relancer l'étape 8 avant la release
- [x] Déploiement (GitHub Pages, source « GitHub Actions ») : site en ligne le 13/10/2026, pages et cartes vérifiées dans un navigateur ; la release n'a pas déclenché le workflow, lancé à la main (`gh workflow run deploy.yml`)
- [x] Données téléchargeables publiées : release `v1.0.0` du 13/10/2026 (commande affichée par l'étape 8) ; lien « Toutes les données (ZIP) » déjà sur la page Données & méthode
- [x] README mis à jour, avec la manière de citer le projet ; `CITATION.cff` (bouton « Cite this repository » de GitHub)
- [x] Archivage Zenodo du code à chaque release (métadonnées dans `.zenodo.json`) : DOI 10.5281/zenodo.23337573 (toutes versions), 10.5281/zenodo.23337574 (v1.0.0), ajouté au README et à `CITATION.cff`
- [x] DOI affiché dans la section « Citer » de la page Données & méthode du site
- [x] `samareew-data.zip` déposé à la main sur Zenodo (13/10/2026, les rasters ne sont pas dans l'archive automatique) : DOI 10.5281/zenodo.23338529 (toutes versions), 10.5281/zenodo.23338530 (v1.0.0), ajouté au README, à `CITATION.cff` et au site ; à refaire à chaque version (« New version » sur la fiche)
- [x] Premier récit à partager : ébauche du 13/10/2026, « Les villes sénégalaises s'étendent deux à trois fois plus vite que leur population » (article et version courte pour les réseaux, dans `data/recit/`, hors git) ; à relire et à diffuser par l'utilisateur ; J6 terminé

**Critère de fin** : le site est en ligne et partageable.

### v1.0.1 — Incertitudes de la v1
Après l'analyse critique du 21/10/2026 (relecture de type « revue ») : ce qui change la
lecture des résultats publiés se fait sur la carte v1, sans Earth Engine ; ce qui change la
carte attend la v1.1 (voir « Après la v1 »).
- [x] Croissance du bâti corrigée 2016 → 2025 avec sa marge à 95 %, par ville et pour les quatre villes, d'après les 480 points (estimateur de rapport, contrôle par bootstrap) ; écarts entre villes : le classement de la croissance est-il établi ? Fait le 21/10/2026 (`accuracy.json`, METHODOLOGIE §14.4) : Dakar +71 % (+37 à +112), Touba +86 % (+42 à +144), Thiès +66 % (+21 à +126), Mbour +159 % (+76 à +279) ; **aucun écart entre deux villes n'est établi à 95 %** ; l'ODD 11.3.1 corrigé dépasse 1 partout sauf à la borne basse de Thiès (0,9)
- [x] Récit (`data/recit/`) et formulations du site revus d'après ce résultat, avant toute diffusion : fait le 21/10/2026, la croissance corrigée et sa marge sont affichées à côté de celle de la carte (accueil, liste et fiches des villes, page thème, Données & méthode, fiches « Croissance du bâti » et « ODD 11.3.1 ») ; le site ne désigne plus de ville « la plus rapide » tant que la validation ne l'établit pas (`growth_comparison`, étape 7) ; récit : titre gardé (vrai pour les quatre villes ensemble, ODD 11.3.1 corrigé 2,8, de 2,1 à 3,4), classement des villes retiré, ancienne version dans `premier_recit_v1.0.0.md`
- [x] Sensibilité du filtre temporel (seuil de persistance, condition « année suivante ») face aux 480 points, sur les piles annuelles déjà calculées : fait le 21/10/2026 (`--filter-sensitivity`, METHODOLOGIE §14.4), 10 réglages ; la précision globale ne bouge que d'un millième et celle du nouveau bâti de 3 à 5 points, bien moins que les marges : les erreurs viennent de la classification, pas du filtre ; croissance de la carte entre +59 et +64 % de 0,6 à 0,9, +74 % à 1,0, toujours sous la croissance corrigée ; réglage publié gardé (diagnostic, pas un choix sur les points de validation)
- [x] ODD 11.3.1 contrôlé avec le recensement (2013 → 2023), au moins pour Dakar : WorldPop répartit la population d'après le bâti, ce qui rend le rapport en partie circulaire : fait le 21/10/2026 (`s6_crosscheck --census`, METHODOLOGIE §13.4) ; sur les 33 communes de Dakar présentes aux deux recensements, WorldPop donne la même croissance que le recensement (1,42 contre 1,41 % par an) et le même ODD (0,80, cœur ancien qui se densifie) ; à Thiès (3 communes), WorldPop surestime la croissance de la population, donc sous-estime l'ODD ; pas de circularité visible, mais la périphérie, où se fait l'étalement, ne peut pas être contrôlée ; Mbour et Touba sans commune comparable
- [x] Si les chiffres publiés changent : release 1.0.1 (étapes 7 et 8, déploiement, nouvelle version Zenodo des données) ; release `v1.0.1` publiée le 21/10/2026 (commit `a2235e5`, archive des données avec `filter_sensitivity.csv` et `sdg_census.csv`), site redéployé à la main et vérifié en ligne ; `samareew-data.zip` déposé sur Zenodo comme nouvelle version (DOI 10.5281/zenodo.23537896), code archivé par l'intégration GitHub (10.5281/zenodo.23537715), ajoutés au README ; DOI concept inchangés, donc rien à changer dans `CITATION.cff` ni sur le site ; v1.0.1 terminé

**Critère de fin** : chaque comparaison entre villes publiée est accompagnée de sa marge, et
le récit ne dit rien que la validation ne soutient.

### Après la v1
- [ ] Déploiement : ni la release ni un push sur `main` touchant `site/` n'ont déclenché le workflow le 13/10/2026 (seul le lancement manuel a marché, `gh workflow run deploy.yml --ref main`) ; chercher la cause
- [ ] Ajouter d'autres villes (Kaolack, Saint-Louis, Ziguinchor…)
- [ ] Mise à jour annuelle automatisée (nouvelle année Sentinel-2)
- [ ] Titres ou fiches en wolof
- [ ] Deuxième thème (voir §7)
- [ ] Forme des zones d'étude : la règle « agglomération GHSL 2025 + 2 km » laisse des encoches, par exemple au nord-est de Dakar entre le lac Rose et Kayar (dunes et niayes, hors zone, donc jamais classées : trou visible sur les silhouettes de l'accueil, `data/j5_dakar_lac_rose.png`). À reprendre avec la mise à jour annuelle : boucher les encoches pour les quatre villes à la fois (même règle), ce qui demande de reclasser, de relancer les étapes 3 à 7 et de recalculer la validation
- [ ] Parcelles agricoles classées en bâti (exploitation de Fandène à Thiès, METHODOLOGIE §14.4) : réentraîner le modèle avec des exemples d'exploitations irriguées, pour les quatre villes, avec la mise à jour annuelle ; demande de reclasser et de refaire la validation
- [ ] Modèle v1.1 (analyse critique du 21/10/2026), avec la mise à jour annuelle et le même reclassement : apprentissage sur plusieurs années (les « années sèches » trahissent un transfert temporel fragile), Sentinel-1 en plus de Sentinel-2 (sable, sols nivelés), variables de saison (percentiles) en plus de la médiane, sortie en probabilités et seuil recalibré (l'échantillon 50/50 pousse vers le bâti) ; évaluation interne par blocs spatiaux plutôt que par points tirés au hasard, désaccords de quantité et d'allocation (Pontius et Millones, 2011) plutôt que kappa
- [ ] Classe « terrain en urbanisation » (lotissements, chantiers) ou classe renommée « surfaces urbanisées » : la seconde lecture de J4 montre que la carte voit l'urbanisation foncière avant les toits (§7, thème Lotissements)
- [ ] Validation de la carte v1.1 : nouvel échantillon avec la strate tampon (non-bâti près du bâti, gardée en réserve le 07/10/2026) pour mieux mesurer les oublis du nouveau bâti ; second interprète indépendant sur une partie des points (accord entre interprètes : 49 % des points v1 sont « pas sûr »)
- [ ] Curseur avant / après sur l'image satellite (composites 2016 et 2025 côte à côte, on glisse pour comparer) : double le stockage de l'image, pas le poids d'une vue
- [ ] Partie WebSIG : une visionneuse plein écran pour naviguer dans toutes les cartes (années, types de croissance, limites, couches des thèmes suivants), en complément des pages éditoriales ; outil à choisir (§8), à partir des mêmes PMTiles de `outputs/site/`

---

## 6. Quand séparer le projet en deux dépôts

Garder un seul dépôt tant qu'aucun de ces signaux n'apparaît :
- **un deuxième thème arrive** (plusieurs chaînes de traitement pour un seul site : c'est
  l'organisation d'OWID, avec `owid/etl` pour les données et `owid/owid-grapher` pour le site) ;
- le **format d'échange est stable** depuis plusieurs mois ;
- **quelqu'un rejoint** le projet sur une des deux parties.

Condition pour que la séparation reste simple : `site/` ne lit **que** `outputs/`, sans aucun import partagé.

---

## 7. Thèmes à développer plus tard

Chaque nouveau thème s'ajoute comme une **nouvelle page thème** qui suit le même format
d'indicateurs et le même découpage (communes, secteurs).

| Thème | Question grand public | Données ouvertes | Compétence travaillée |
|---|---|---|---|
| **Densité de population** | Combien de gens vivent ici ? | WorldPop, GHS-POP, Meta HRSL, RGPH-5 (ANSD) pour contrôler | Statistiques zonales, désagrégation, confrontation modèle / recensement |
| **Végétation** | Mon quartier est-il vert ? Perd-il ses arbres ? | Sentinel-2 (NDVI), ESA WorldCover, hauteur de canopée (Meta / WRI) | Séries temporelles, détection de changement |
| **Îlots de chaleur** | Où fait-il le plus chaud en ville ? | Landsat 8/9 (température de surface) | Télédétection thermique, croisement avec la végétation |
| **Inondations** | Mon quartier est-il inondable ? | Sentinel-1 (radar), JRC Global Surface Water, MNT Copernicus GLO-30 | Radar SAR, hydrologie simple (Pikine, Keur Massar…) |
| **Érosion côtière** | La côte recule-t-elle ? | Landsat et Sentinel-2 sur 30 ans | Extraction du trait de côte (Saint-Louis, Rufisque…) |
| **Accès aux services** (santé, éducation) | À combien de minutes est l'hôpital ? | OSM, healthsites.io, surface de friction MAP (dans GEE), WorldPop | Analyse de réseau, coût cumulé |
| **Lumières nocturnes** | Quels quartiers sont électrifiés ? | VIIRS | Indicateur de développement |
| **Lotissements** (urbanisation en cours) | Où ouvre-t-on des terrains à bâtir avant les maisons ? | Sentinel-2 (sol nivelé, clôtures), Open Buildings (toits) pour séparer bâti et parcelles vides | Classe « terrain en urbanisation », détection précoce ; piste vue en J4 : environ 55 000 ha de terrains en urbanisation, plus du double du nouveau bâti cartographié (METHODOLOGIE §14.4) |

**Croisements prometteurs** (les meilleurs récits) :
- densité × végétation × chaleur : « les quartiers denses et sans arbres sont les plus chauds » ;
- expansion × inondation : « construit-on dans les zones inondables ? » ;
- expansion × accès aux services : « les nouveaux quartiers sont-ils loin des services ? ».

---

## 8. Décisions encore ouvertes

| Décision | Jalon |
|---|---|
| Outil de la partie WebSIG (par exemple GeoLibre ou une visionneuse MapLibre maison) : à étudier le moment venu | Après la v1 |

---

## 9. Journal des décisions

| Date | Décision | Raison |
|---|---|---|
| 30/09/2026 | Site national grand public, modèle OWID, thème unique « expansion urbaine » | Comparer les villes ; progresser en restant utile |
| 30/09/2026 | Villes v1 : Dakar, Touba, Thiès, Mbour | Contextes variés |
| 30/09/2026 | Modèle national unique | Comparabilité entre villes |
| 30/09/2026 | Échantillon de validation Dakar actuel abandonné au profit d'un échantillon national | La carte va changer avec le modèle national |
| 30/09/2026 | Un seul dépôt, frontière stricte pipeline / site | Format d'échange encore instable, projet solo |
| 30/09/2026 | Nom : SamaReew (« mon pays » en wolof) | Nom court, national, parlant pour le public sénégalais |
| 30/09/2026 | Licences : MIT (code), CC BY 4.0 (données) | Réutilisation libre avec attribution |
| 30/09/2026 | Enveloppe : agglomération urbaine GHSL (GHS-SMOD 2025, classe ≥ 21) plutôt que le centre urbain | Le centre urbain manque la croissance récente (Diamniadio, Petite Côte) ; GHSL est reproductible dans Earth Engine et sous CC BY 4.0 |
| 30/09/2026 | Tampon de 2 km pour toutes les villes, terre uniquement ; partage à mi-distance si deux zones se chevauchent | 5 km essayé puis écarté : zones 2 à 4 fois plus grandes que l'agglomération, surtout rurales, et Dakar touchait Thiès et Mbour ; même règle partout pour la comparabilité |
| 30/09/2026 | Communes : OpenStreetMap corrigé (noms post-2013, chevauchements retirés au profit de la plus petite commune, découpe à la côte), sous ODbL | Aucune source ouverte officielle au niveau commune |
| 05/10/2026 | Centres : Place de l'Indépendance (Dakar), Grande Mosquée (Touba), Place de France (Thiès), quai de pêche (Mbour) | Règle unique « cœur historique, lieu connu de tous » (comme l'Atlas of Urban Expansion) ; un centre calculé tomberait à Pikine pour Dakar |
| 05/10/2026 | Touba découpé en secteurs : disque central 0–2 km, puis anneaux de 2 km × 8 directions | La commune de Touba Mosquée couvre 264 des 413 km² de la zone ; les secteurs suivent la forme radiale de la ville et la géométrie des indicateurs direction / anneaux, et se nomment simplement (« Nord-Est, 4–6 km ») ; hexagones gardés en réserve comme couche de carte commune |
| 05/10/2026 | Mbacké : pas d'unité à part dans les secteurs ; ses chiffres viennent du découpage par commune ; « Touba » = agglomération Touba-Mbacké, précisé sur la fiche | Garder des secteurs purs (direction × distance) ; la commune de Mbacké est déjà entièrement dans la zone, sans travail supplémentaire |
| 05/10/2026 | Communes OSM corrigées pour les 4 villes, y compris Thiès (pas de secteurs) ; GADM / mapSenegal écarté | Uniformité entre villes ; GADM : 433 communes (découpage ancien, manque Mbour, Saly, Mbacké…), contours grossiers, licence non commerciale |
| 06/10/2026 | Départ en 2016 maintenu (pas 2015 ni 2014) | Sentinel-2A lancé en juin 2015 : aucune scène en saison sèche 2015 ; remonter plus loin demanderait Landsat (30 m, série non comparable) ; le recul historique viendra de GHSL en contexte (J3) |
| 06/10/2026 | Saison sèche allongée : 1er novembre (année précédente) – 31 mai, au lieu de janvier – mai | 2017 n'avait que 30 scènes (Dakar) et son composite surestimait le bâti (saut artificiel de +15 à +32 % en 2017) ; même règle pour toutes les années et toutes les villes |
| 06/10/2026 | Indicateurs publiés jusqu'à l'avant-dernière année (2016–2025) ; la dernière année (2026) sert seulement de confirmation au filtre temporel | Une année seule n'est jamais filtrée : la surface 2026 était le bâti brut (Thiès +1 865 ha en 2026 contre ~200 ha/an) ; 10 ans de recul à la mise à jour 2027 |
| 06/10/2026 | Filtre temporel : une année ne peut être l'année d'urbanisation que si le pixel est aussi bâti l'année valide suivante | Années sèches (2017, 2019) : fausses détections en périphérie qui avançaient la croissance réelle en 2017 (nouveau bâti 2017 à Dakar : 2 772 → 1 648 ha) ; hausse 2016–2025 quasi inchangée ; l'entraînement multi-années reste en réserve si J4 montre des erreurs variant selon l'année |
| 06/10/2026 | Type de croissance : règle de l'Atlas of Urban Expansion (frange 100 m, trous enclavés < 200 ha ; densification / extension / saut), par période 2016→2020, 2020→2025, 2016→2025 | Règle publiée et reconnue, lisible par le grand public ; l'indice LEI, calculé îlot par îlot, est plus sensible au bruit des petits îlots à 10 m |
| 06/10/2026 | Population : WorldPop Global 2 (R2025A), RGPH-5 2023 en contrôle | Seule source annuelle 2016–2025 au maillage fin (100 m), sous CC BY 4.0 (vérifié) ; le recensement ne donne que deux dates par commune entière |
| 06/10/2026 | Type de croissance : l'emprise de départ ne part que du bâti urbain ou périurbain (≥ 25 % de bâti dans un cercle de 1 km², comme l'Atlas), pas de tout le bâti | À 10 m, la frange de 100 m autour du bâti épars couvrait presque toute la périphérie : 81 à 86 % de densification partout ; avec le seuil, 28 à 38 % selon la ville (cartes `data/j3_growth_<ville>.png`) |
| 06/10/2026 | Indicateurs de population : WorldPop publié par ville seulement ; par commune, recensement 2023 (communes entièrement dans les zones) | Contrôle avec le RGPH-5 : totaux WorldPop bons (97 % sur les 51 communes de Dakar) mais répartition entre communes fausse d'un facteur 0,35 à 2,9 ; le recensement ne donne qu'une année mais il est juste |
| 06/10/2026 | Validation : 120 points par ville en 5 strates (non bâti 40, bâti 2016 32, densification / extension / saut 16 chacun), même plan dans les 4 villes ; année d'apparition du bâti notée si les images le permettent | Mesurer la fiabilité du saut, point faible vu en J3 (36 % confirmé à Thiès) ; précision du saut indicative par ville (±20 points), mieux cernée au niveau national (±11 points) ; pas de points en plus à Thiès, par comparabilité ; l'année notée teste le saut de Touba en 2017 et l'année 2025 sans points supplémentaires |
| 07/10/2026 | Pas de points ajoutés à la main (changements choisis sur les images) : on garde uniquement l'échantillon aléatoire | Des points choisis n'ont pas de poids connu et favorisent les changements évidents, ce qui rendrait la précision trop optimiste ; une strate tampon tirée au hasard (non-bâti à moins de ~200 m du bâti, Olofsson et al., 2014) reste en réserve si la précision producteur du nouveau bâti ressort trop imprécise |
| 07/10/2026 | Règle d'étiquetage confirmée (§14.2 de METHODOLOGIE), appliquée aux 480 points | Même définition que la carte : pixels bâtis, pas seulement des toits |
| 07/10/2026 | Publication après la validation : les tableaux gardent les valeurs de la carte ; les fiches donnent la précision mesurée ; les surfaces corrigées par ville, avec leur marge, sont publiées à côté ; types de croissance indicatifs, année 2025 provisoire | Surface bâtie 2025 juste en moyenne (60 400 ± 7 400 ha corrigés, 61 000 cartographiés) mais nouveau bâti juste à 51 % seulement et saut à 45 % ; les surfaces corrigées sont plus justes en moyenne mais trop incertaines par ville (± 40 % sur le nouveau bâti) pour remplacer la carte |
| 07/10/2026 | Seconde lecture des 228 points non bâtis en 2025 : occupation du sol dans une liste fermée de 8 codes fixée avant la lecture ; précision « tolérante » où chantier, lotissement non construit et pixel bâti à moins de moitié comptent comme bâti ; la précision stricte reste officielle | Les erreurs du nouveau bâti ne viennent pas de la qualité des images anciennes (précision utilisateur 0,53 sur les seuls points sûrs, contre 0,51) : 67 des 88 erreurs sont des points vus non bâtis sur les images de 2025, probablement des terrains en cours d'urbanisation que Sentinel-2 voit comme du bâti ; pondérer par la confiance aurait biaisé la précision vers le haut sans traiter ce cas |
| 08/10/2026 | Lotissements (urbanisation en cours) ajoutés aux thèmes à développer après la v1 ; rien ne change dans la carte v1 | La seconde lecture montre qu'un quart du nouveau bâti cartographié est en lotissement non construit ou en chantier, et que la carte ne voit qu'une partie des lotissements (précision producteur tolérante 0,32) |
| 09/10/2026 | Outils du site : Astro (statique), Observable Plot, MapLibre GL + PMTiles, GitHub Pages | Critères donnés : pratique, maintenable, bon rendu en débit faible et sur téléphone. Astro sert des pages HTML sans JavaScript par défaut et ne charge le code que pour les graphiques et les cartes ; Plot est léger et produit du SVG téléchargeable ; PMTiles évite tout serveur de tuiles. Écartés : Observable Framework (moins de liberté pour un site éditorial à gabarit OWID), Quarto / MkDocs (interactivité trop limitée) |
| 09/10/2026 | Partie WebSIG ajoutée après la v1 (navigation libre dans toutes les cartes) ; outil non choisi | Demande de l'utilisateur ; à préciser le moment venu, sans changer le périmètre de J5 |
| 09/10/2026 | Node 24 (installé avec nvm) et Astro 7 plutôt que Node 20 et Astro 5 | Node 20 n'est plus maintenu depuis avril 2026 et Astro 7 demande Node ≥ 22.12 ; Node 24 est la version maintenue, la même qu'au déploiement |
| 09/10/2026 | Fond de carte : extrait OpenStreetMap des zones depuis Protomaps, auto-hébergé avec le site (variantes « white » / « black ») | Comparé à OpenFreeMap (`data/j5_basemap_*.png`) : aucun service tiers ni clé, même technique PMTiles que les couches ; 12 Mo jusqu'au zoom 14, chargés par morceaux ; licences vérifiées : tuiles ODbL, style BSD-3, polices OFL, icônes MIT. Variante « light » écartée : ses forêts vertes se confondent avec le vert du « saut » |
| 09/10/2026 | Image satellite sous les couches des cartes : notre composite Sentinel-2 2025 (10 m, couleurs naturelles), désactivée par défaut ; curseur avant / après 2016-2025 gardé pour après la v1 | On voit ce que le modèle a vu, et les lotissements qui expliquent l'avance du nouveau bâti sur les toits (§14.4 de METHODOLOGIE) ; même saison et mêmes images que la carte, licence Copernicus libre, servie avec le site. Rien n'est chargé tant qu'on ne l'affiche pas. Écartés : imageries très fines (Esri, Google, Bing, Mapbox : clé ou conditions restrictives), EOX Sentinel-2 Cloudless (licence non commerciale, année différente), OpenAerialMap (couverture éparse) |
| 09/10/2026 | Accueil : les quatre villes à la même échelle (silhouettes du bâti) plutôt qu'une carte du Sénégal à cercles, pour l'instant | Plus parlant pour comparer les villes (Dakar face aux trois autres, et où chacune a poussé) ; images légères (PNG à palette, 80 m par pixel, 91 Ko pour les quatre) ; la carte à cercles en SVG reste possible en complément. Écartée sur l'accueil : une carte MapLibre (environ 500 Ko, 13 s en 3G) |
| 09/10/2026 | Encoche de la zone de Dakar entre le lac Rose et Kayar : laissée telle quelle pour la v1, à revoir après | Elle découle de la règle commune des zones (§2), pas d'une erreur de carte ; la corriger demande de changer la règle pour les quatre villes, de reclasser (quota Earth Engine épuisé jusqu'au 1er novembre) et de recalculer la validation |
| 09/10/2026 | Déploiement : archives PMTiles (couches et fond de carte) jointes à chaque release dans `site-assets.tar.gz`, site construit et déployé par GitHub Actions | L'étape 7 ne peut pas tourner dans GitHub Actions (GeoTIFF de `data/`) ; une release rend le déploiement reproductible sans alourdir l'historique git (25 Mo à chaque mise à jour) ; écartés : construire en local et pousser `dist/` (déploiement lié à une machine), versionner les PMTiles |
| 12/10/2026 | Fausse détection de 75 ha au nord-est de Thiès (exploitation agricole irriguée) : la carte n'est pas corrigée à la main ; l'erreur est entourée et expliquée sur la carte du site (contour toujours visible, texte au toucher, au clic ou au survol, et sous la carte) ; réentraînement du modèle après la v1 | Déjà comptée dans la validation (deux points y sont tombés) ; effet faible (croissance de Thiès +81 % au lieu de +83 %, aucun classement ne change) ; un masque manuel romprait la règle commune aux villes et rendrait la validation optimiste ; une règle automatique sur Open Buildings retirerait l'aéroport et le port ; quota Earth Engine épuisé jusqu'au 1er novembre. Le survol seul ne marche pas sur téléphone |
| 13/10/2026 | Archivage sur Zenodo : intégration GitHub (code, méthode et tableaux archivés à chaque release, avec un DOI), puis dépôt manuel de `samareew-data.zip` | Un DOI rend la version citable et durable, indépendamment de GitHub ; l'intégration n'archive que le code source de l'étiquette, pas les fichiers joints, donc les rasters demandent un dépôt à part ; à activer avant la release, car Zenodo ne reprend pas les releases passées |
| 21/10/2026 | Après une analyse critique de la v1 : jalon v1.0.1 sur la carte actuelle (croissance corrigée avec sa marge, récit et site revus, sensibilité du filtre temporel, ODD 11.3.1 contrôlé avec le recensement) avant de diffuser le récit ; améliorations du modèle et de la validation reportées à la v1.1 | Les surfaces corrigées par la validation peuvent inverser le classement de la croissance des villes (Thiès +83 % sur la carte, environ +66 % corrigé ; Mbour +80 %, environ +159 %), alors que le récit compare les villes ; tout ce qui change la carte demande de reclasser et de refaire la validation, ce qui sera fait une seule fois avec la v1.1 |
