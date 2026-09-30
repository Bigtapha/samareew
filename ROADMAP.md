# Feuille de route — Atlas urbain du Sénégal (nom provisoire)

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
| Nom | National (à choisir : _Atlas urbain du Sénégal_, _Villes du Sénégal en données_, _Dëkk_…) |
| Thème de départ | **Expansion urbaine**, un seul thème pour la v1 |
| Villes (v1) | **Dakar, Touba, Thiès, Mbour** (capitale, ville religieuse de l'intérieur, carrefour, littoral) |
| Modèle de classification | **Un Random Forest national** (entraîné sur les 4 zones) ; adaptation par ville seulement si nécessaire |
| Définition d'une ville | Règle **homogène** : enveloppe d'agglomération (Africapolis / GHSL) + tampon, figée dans le dépôt |
| Unité grand public | **La commune** ; découpage plus fin uniquement si nécessaire (**Touba** : secteurs anneaux × directions ou grille hexagonale) |
| Organisation du code | **Un seul dépôt**, avec une frontière stricte `pipeline/` → `outputs/` → `site/` ; séparation en deux dépôts plus tard (voir §6) |
| Validation | Nouvel **échantillon national** stratifié par ville × classe (~120 points/ville) ; l'échantillon actuel de Dakar (260 points) n'est **plus à étiqueter** |

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
- **Des cartes par ville** (couches de périodes, tuiles).
- **Un numéro de version** du format dans les métadonnées.

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
<nom-national>/
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
- [ ] `git init` et premier commit de l'état actuel (projet Dakar)
- [ ] Choisir le nom national, renommer le projet et le dépôt
- [ ] Créer le dépôt GitHub
- [ ] Choisir les licences (proposition : MIT pour le code, CC-BY 4.0 pour les données produites)

**Critère de fin** : l'état actuel est versionné et sauvegardé en ligne.

### J1 — Définition des zones d'étude
- [ ] Récupérer les enveloppes d'agglomération (Africapolis ou GHS-UCDB) pour les 4 villes
- [ ] Choisir la règle de tampon (fixe ou proportionnelle) en laissant de la marge pour 10 ans de croissance
- [ ] Définir le centre de chaque ville (pour directions et anneaux)
- [ ] Récupérer les limites communales (OCHA COD-AB sur HDX, ou geoBoundaries)
- [ ] Concevoir le découpage en secteurs de Touba
- [ ] Documenter ces choix dans le journal des décisions

**Critère de fin** : `zones/` contient les 4 zones figées, les communes et les secteurs, tous documentés.

### J2 — Modèle national et classification
- [ ] Réorganiser le code selon la structure cible (configuration par ville)
- [ ] Échantillonnage d'entraînement équilibré par ville × classe
- [ ] Entraîner le Random Forest national et l'évaluer par ville
- [ ] Classer 2016–2026 pour les 4 villes
- [ ] Contrôle qualité : nombre de scènes par ville et par an, repérer les années faibles

**Critère de fin** : 4 piles annuelles et un rapport d'évaluation par ville.

### J3 — Indicateurs et contrôle croisé
- [ ] Post-traitement (filtre temporel) pour chaque ville
- [ ] Définir les règles du type de croissance (seuil extension / saut)
- [ ] Choisir la source de population (WorldPop ou RGPH-5)
- [ ] Calculer les indicateurs v1 (§4.3) par ville, commune et secteur
- [ ] Comparer avec GHSL et Open Buildings
- [ ] Produire la table longue et les fiches indicateurs

**Critère de fin** : la table longue est complète pour les 4 villes, et les écarts avec GHSL sont expliqués.

### J4 — Validation nationale
- [ ] Tirer l'échantillon stratifié ville × classe (~480 points)
- [ ] Photo-interprétation à l'aveugle dans Google Earth Pro
- [ ] Calculer la précision par ville (avec marge d'erreur) et la précision nationale
- [ ] Intégrer les résultats aux fiches indicateurs et à la page Méthode

**Critère de fin** : chaque ville a une précision pondérée par la surface et sa marge d'erreur.

> J3 et J4 peuvent se chevaucher : étiqueter pendant que les indicateurs se construisent.

### J5 — Site v1
- [ ] Choisir les outils (générateur statique, bibliothèque de graphiques, MapLibre + PMTiles)
- [ ] Gabarit de graphique OWID (onglets, sélection de villes, URL avec état, téléchargement)
- [ ] Page thème « Expansion urbaine » avec 4 ou 5 points clés
- [ ] Les graphiques des indicateurs v1
- [ ] 4 fiches villes
- [ ] Page Données & méthode (sources, licences, limites, validation)
- [ ] Tests sur mobile et connexion lente

**Critère de fin** : le site fonctionne en local, il est lisible sur téléphone et chaque chiffre renvoie à sa source.

### J6 — Publication
- [ ] Déploiement (GitHub Pages)
- [ ] Données téléchargeables publiées (releases)
- [ ] README mis à jour, avec la manière de citer le projet
- [ ] Premier récit à partager (par exemple « Touba a grandi de X % en 10 ans »)

**Critère de fin** : le site est en ligne et partageable.

### Après la v1
- [ ] Ajouter d'autres villes (Kaolack, Saint-Louis, Ziguinchor…)
- [ ] Mise à jour annuelle automatisée (nouvelle année Sentinel-2)
- [ ] Titres ou fiches en wolof
- [ ] Deuxième thème (voir §7)

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

**Croisements prometteurs** (les meilleurs récits) :
- densité × végétation × chaleur : « les quartiers denses et sans arbres sont les plus chauds » ;
- expansion × inondation : « construit-on dans les zones inondables ? » ;
- expansion × accès aux services : « les nouveaux quartiers sont-ils loin des services ? ».

---

## 8. Décisions encore ouvertes

| Décision | Jalon |
|---|---|
| Nom du site | J0 |
| Taille / règle du tampon autour des agglomérations | J1 |
| Centre de chaque ville | J1 |
| Découpage de Touba (secteurs ou hexagones) | J1 |
| Règles densification / extension / saut | J3 |
| Source de population (WorldPop ou RGPH-5) | J3 |
| Outils du site | J5 |

---

## 9. Journal des décisions

| Date | Décision | Raison |
|---|---|---|
| 30/09/2026 | Site national grand public, modèle OWID, thème unique « expansion urbaine » | Comparer les villes ; progresser en restant utile |
| 30/09/2026 | Villes v1 : Dakar, Touba, Thiès, Mbour | Contextes variés |
| 30/09/2026 | Modèle national unique | Comparabilité entre villes |
| 30/09/2026 | Échantillon de validation Dakar actuel abandonné au profit d'un échantillon national | La carte va changer avec le modèle national |
| 30/09/2026 | Un seul dépôt, frontière stricte pipeline / site | Format d'échange encore instable, projet solo |
