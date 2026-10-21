# Fiche méthodologique — cartographie du bâti

_Comment SamaReew produit les cartes annuelles du bâti (2016–2026) des quatre villes et leurs indicateurs.
Chaque valeur citée ici vient de `config/settings.py` ou du code (`src/`, `pipeline/`) :
si un paramètre change, mettre cette fiche à jour._

---

## 1. Vue d'ensemble

Le problème est une **classification binaire au pixel** : pour chaque pixel de 10 m × 10 m de
la zone d'étude et pour chaque année, on décide « bâti » (1) ou « non bâti » (0).

```
               ┌──────────── 2021 seulement ────────────┐
Sentinel-2 ──► composite saison sèche ──► 10 variables ──┐
                                                         ├─► échantillons ──► Random Forest national
WorldCover 2021 ∩ Dynamic World 2021 ──► étiquettes ─────┘        (70 % appr. / 30 % test)
                                                                          │
               ┌──────────── chaque année 2016…2026 ─────┐                │
Sentinel-2 ──► composite saison sèche ──► 10 variables ──► classification ◄┘
                                                                │
                                         pile annuelle 0/1 ──► filtre temporel ──► année d'urbanisation
```

Idée clé : **on apprend une seule fois (2021), on applique partout et tous les ans.** Le modèle
apprend à reconnaître la « signature spectrale » du bâti à partir d'exemples dont on connaît la
réponse, puis on suppose que cette signature reste la même d'une année à l'autre.

---

## 2. Les images : Sentinel-2

| Élément | Choix | Pourquoi |
|---|---|---|
| Collection | `COPERNICUS/S2_HARMONIZED` (niveau **L1C**, réflectance au sommet de l'atmosphère) | Seule archive complète depuis 2015 ; le niveau L2A (corrigé de l'atmosphère) n'a une couverture mondiale complète qu'à partir de 2018–2019 et ne couvrirait pas 2016–2017 |
| « Harmonized » | Les scènes traitées après le 25/01/2022 (version 04.00 d'ESA) ont un décalage de +1000 dans leurs valeurs ; la collection harmonisée le retire | Sans cela, une même surface aurait des valeurs différentes avant et après 2022 : rupture artificielle dans la série |
| Saison | **1er novembre de l'année précédente – 31 mai** (la saison « 2016 » va du 01/11/2015 au 31/05/2016) | Saison sèche : peu de nuages, végétation stable, donc des images comparables d'une année à l'autre. Elle commençait d'abord en janvier ; elle a été allongée parce que 2017 avait trop peu d'images (voir §7) |
| Masque nuages | **Cloud Score+** (bande `cs_cdf`, score de 0 à 1 où 1 = pixel parfaitement dégagé) ; on garde les pixels ≥ **0,60** | Retire nuages, ombres de nuages et brumes épaisses |
| Composite | **Médiane** pixel par pixel de toutes les observations dégagées de la saison | La médiane ignore les valeurs extrêmes (nuage résiduel, ombre) mieux qu'une moyenne |
| Échelle | Réflectances divisées par 10 000 (valeurs de 0 à 1) | Unité physique, nécessaire pour les indices |

Un pixel sans aucune observation dégagée dans la saison reste vide et reçoit la valeur 255
(« pas de donnée ») dans la pile annuelle.

---

## 3. Les 10 variables du modèle

### 3.1 Six bandes spectrales

| Bande | Domaine | Longueur d'onde | Résolution | Ce qu'elle apporte |
|---|---|---|---|---|
| B2 | Bleu | 490 nm | 10 m | Brumes, eau peu profonde, toitures claires |
| B3 | Vert | 560 nm | 10 m | Eau, végétation |
| B4 | Rouge | 665 nm | 10 m | Absorbé par la chlorophylle : faible sur la végétation |
| B8 | Proche infrarouge (PIR) | 842 nm | 10 m | Très fort sur la végétation, faible sur l'eau |
| B11 | Infrarouge moyen 1 (SWIR1) | 1610 nm | 20 m | Sensible aux matériaux secs (béton, tôle, sol nu) et à l'humidité |
| B12 | Infrarouge moyen 2 (SWIR2) | 2190 nm | 20 m | Sépare minéraux, sols et matériaux de construction |

B11 et B12 sont à 20 m : Earth Engine les rééchantillonne à 10 m (plus proche voisin), donc un
pixel « SWIR » couvre en réalité 4 pixels de la carte.

Les bandes « red edge » (B5–B7) et atmosphériques (B1, B9, B10) ne sont pas utilisées : elles
servent surtout à la végétation ou à l'atmosphère, pas au bâti.

### 3.2 Quatre indices spectraux

Un indice est un **rapport normalisé** entre bandes (valeur de −1 à +1). Il rend explicite un
contraste physique que le modèle aurait du mal à trouver seul, et il atténue les variations
d'éclairement d'une image à l'autre (un rapport varie moins qu'une valeur brute).

| Indice | Formule | Lecture |
|---|---|---|
| **NDVI** (végétation) | (B8 − B4) / (B8 + B4) | Élevé = végétation ; proche de 0 = bâti, sol nu ; négatif = eau |
| **NDBI** (bâti) | (B11 − B8) / (B11 + B8) | Positif = surfaces minérales sèches (bâti **mais aussi sable**) |
| **MNDWI** (eau, Xu 2006) | (B3 − B11) / (B3 + B11) | Positif = eau ; sépare bien l'eau et les zones humides du bâti |
| **BSI** (sol nu) | ((B11 + B4) − (B8 + B2)) / ((B11 + B4) + (B8 + B2)) | Élevé = sol nu, sable ; aide à séparer le sable du bâti |

**Le problème central au Sénégal : le sable.** Sable, plages et tannes (sols salés) sont aussi
clairs et secs que le béton : le NDBI seul les confond. C'est la **combinaison** de plusieurs
variables (BSI, SWIR2, bleu) qui permet au modèle de les séparer, d'où l'intérêt d'un modèle
multivarié plutôt qu'un seuil sur un seul indice.

---

## 4. Les étiquettes d'entraînement

Il faut des exemples « bâti » et « non bâti » sûrs. Plutôt que de les dessiner à la main, on
les prend dans deux produits mondiaux **indépendants** :

- **ESA WorldCover 2021** (v200, 10 m) : classe 50 = « Built-up » ;
- **Google Dynamic World 2021** (10 m, une classification par scène) : on prend la classe la
  plus fréquente de l'année (**mode**) ; classe 6 = « Built ».

Règle (`src/gee_utils.py`, `reference_labels`) :

| WorldCover | Dynamic World | Étiquette |
|---|---|---|
| bâti | bâti | **1 = bâti** |
| non bâti | non bâti | **0 = non bâti** |
| désaccord | désaccord | **exclu** (pixel masqué) |

Garder seulement les zones d'accord **réduit le bruit des étiquettes** : un pixel que deux
méthodes différentes classent de la même façon a peu de chances d'être faux. Contrepartie : les
pixels difficiles (bâti épars, lisières, sable en bord de ville) sont sous-représentés dans
l'apprentissage (voir §8).

---

## 5. L'échantillonnage (étape 1)

Dans chaque ville, sur le composite **2021** (même année que les étiquettes) :

1. **Tirage stratifié** : **1 500 points par classe et par ville** (`POINTS_PER_CLASS`), soit
   3 000 points par ville et 12 000 au total. Chaque point porte son étiquette et ses 10
   variables.
2. **Équilibre ville × classe** : chaque ville pèse autant dans le modèle. Sans cela, Dakar
   (la plus grande zone) dominerait l'apprentissage et le modèle serait moins bon ailleurs.
   Les deux classes pèsent aussi autant, alors qu'en réalité le non-bâti est majoritaire dans
   les zones : on apprend ainsi aussi bien les deux classes.
3. **Partage 70 / 30** : chaque point reçoit un nombre aléatoire ; s'il est < 0,7 il sert à
   l'apprentissage, sinon au test. Le partage est donc d'environ 70 / 30 dans chaque ville
   (8 487 points d'apprentissage et 3 513 de test au dernier calcul).

Tous les tirages utilisent la graine `SEED = 42` : relancer l'étape 1 donne les mêmes points.
Les points sont écrits dans `data/training_samples.csv`, que l'étape 2 relit pour réentraîner
**exactement** le même modèle.

---

## 6. Le Random Forest

### 6.1 Principe

Un **arbre de décision** pose une suite de questions du type « B12 > 0,31 ? » puis
« NDVI > 0,18 ? »… jusqu'à une feuille qui donne une classe. Un seul arbre colle trop à ses
données d'apprentissage (sur-apprentissage). Une **forêt aléatoire** (Breiman, 2001) en
construit beaucoup, en les rendant différents par deux sources de hasard :

1. **Chaque arbre voit un sous-échantillon des points** (ici 50 % tirés au hasard,
   paramètre par défaut `bagFraction` d'Earth Engine) ;
2. **À chaque nœud, l'arbre ne choisit sa question que parmi quelques variables tirées au
   hasard** (par défaut √10 ≈ 3 variables sur 10).

Chaque nœud choisit la variable et le seuil qui séparent le mieux les deux classes (critère de
Gini : on cherche des groupes les plus « purs » possible). Pour classer un pixel, **les 200
arbres votent** et la classe majoritaire l'emporte.

Pourquoi ça marche : les arbres font des erreurs différentes, et le vote les compense. Le
modèle gère bien des variables corrélées (B11, B12, NDBI…), n'exige pas de normaliser les
données, et ne suppose aucune forme de relation entre variables et classes.

### 6.2 Paramètres utilisés

| Paramètre | Valeur | Source |
|---|---|---|
| Nombre d'arbres | 200 | `N_TREES` |
| Variables par nœud | √10 ≈ 3 | défaut Earth Engine |
| Part des points par arbre | 50 % | défaut Earth Engine |
| Taille minimale d'une feuille | 1 point | défaut Earth Engine |
| Graine | 42 | `SEED` |
| Implémentation | `ee.Classifier.smileRandomForest` (bibliothèque SMILE) | `pipeline/s1_train.py` |

### 6.3 Un seul modèle national

Le modèle est entraîné sur les points des **quatre villes ensemble**, puis évalué **ville par
ville**. Un modèle par ville serait peut-être un peu meilleur localement, mais deux modèles
différents ne tracent pas la limite bâti / non bâti au même endroit : les surfaces ne seraient
plus comparables entre villes, ce qui est le but du projet.

### 6.4 Importance des variables

Earth Engine donne pour chaque variable la somme de ses contributions aux séparations dans
toute la forêt (plus c'est élevé, plus la variable est utile). Au dernier calcul :

| B12 | MNDWI | B11 | B3 | BSI | B4 | NDVI | B8 | B2 | NDBI |
|---|---|---|---|---|---|---|---|---|---|
| 1623 | 1319 | 1232 | 1166 | 1148 | 1135 | 1133 | 1130 | 1108 | 1097 |

Les deux bandes SWIR et le MNDWI arrivent en tête, mais les écarts sont faibles : **aucune
variable ne suffit seule**, le modèle s'appuie sur leur combinaison. Ces valeurs sont à lire
avec prudence : avec des variables corrélées, l'importance se répartit entre elles.

---

## 7. Classification annuelle (étape 2)

Pour chaque ville et chaque année de 2016 à 2026 :

1. composite de saison sèche de l'année (§2) et ses 10 variables (§3) ;
2. le modèle national classe chaque pixel : 1 = bâti, 0 = non bâti ;
3. 255 là où il n'y a pas d'observation dégagée, ou hors de la zone d'étude ;
4. les 11 années sont empilées dans une image à 11 bandes (`built_by_year.tif`, UTM 28N, 10 m).

Le nombre de scènes Sentinel-2 par saison est enregistré (`image_counts.json`) pour repérer
les années faibles : 2016 n'a que Sentinel-2A (une scène tous les 10 jours au lieu de 5).
Au dernier calcul (scènes touchant la zone, novembre–mai) :

| Ville | 2016 | 2017 | 2018–2026 |
|---|---|---|---|
| Dakar, Thiès, Mbour | 64 | **48** | 82 à 132 |
| Touba (deux tuiles Sentinel-2) | 124 | **95** | 166 à 227 |

Avec la saison de janvier à mai, 2017 n'avait que 30 scènes (Dakar) ; l'allongement à
novembre–mai en ajoute 18.

**Années « sèches ».** Certaines années, le composite classe nettement plus de bâti que les
années voisines, surtout en périphérie (pixels bâtis une seule année, Dakar : 5 470 ha en
2017 et 4 330 ha en 2019, contre 300 à 1 900 ha les autres années). Ce n'est ni un artefact
de tuile ni un décalage radiométrique général (réflectances moyennes proches de 2016 et
2018) : ces deux années ont le NDVI moyen le plus faible (0,128 et 0,120 contre 0,134 à 0,153).
Le sol nu ou peu végétalisé des franges passe alors du côté « bâti ». C'est la limite du
transfert temporel (§10) ; 2017 est touchée dans les quatre villes.

---

## 8. Post-traitement : le filtre de cohérence temporelle (étape 3)

Une classification annuelle seule est **bruitée** : un pixel peut « clignoter » bâti / non bâti
d'une année à l'autre (poussière, chantier, sable, composite de moins bonne qualité). On ajoute
une hypothèse physique : **l'urbanisation est irréversible** (on démolit rarement pour revenir
au sol nu).

Règle (`src/postprocess.py`, `urbanisation_year`) — un pixel est urbanisé l'année Y si :

1. il est bâti en Y **et l'année valide suivante** ;
2. il est bâti dans **au moins 80 %** (`PERSISTENCE_RATIO`) des années valides de Y à 2026 ;
3. sa **dernière observation valide** est « bâti ».

La condition « et l'année suivante » a été ajoutée à cause des années sèches (§7). Sans elle,
un pixel construit en 2019 mais classé bâti par erreur en 2017 remplissait la règle des 80 %
dès 2017 (9 années bâties sur 10) : la croissance de 2018–2019 était avancée en 2017.

L'année d'urbanisation est la **première** année Y qui remplit ces conditions ; 0 si aucune ;
−1 si le pixel n'a jamais été observé.

Exemples (années 2016 → 2026) :

| Série | Résultat | Explication |
|---|---|---|
| `0 0 1 1 0 1 1 1 1 1 1` | **2018** | Bâti en 2018 et 2019 ; de 2018 à 2026 : 8 années bâties sur 9 (89 % ≥ 80 %) |
| `0 1 0 1 1 1 1 1 1 1 1` | **2019** | 2017 : 9 sur 10, mais 2018 non bâti, refusé (fausse détection d'année sèche) |
| `0 0 1 0 0 0 1 1 1 1 1` | **2022** | 2018 refusé (2019 non bâti, et 6 sur 9 = 67 %) ; 2022 : 5 sur 5 accepté |
| `0 1 1 1 1 1 1 1 1 1 0` | **0** | Dernière observation non bâtie : jamais urbanisé |
| `0 0 0 0 0 0 0 0 0 0 1` | **2026**, non publié | Pas d'année suivante pour confirmer ; compté « non bâti » dans les indicateurs (voir plus bas) |

Les surfaces sont ensuite comptées en pixels : surface bâtie de l'année Y = nombre de pixels
urbanisés en Y ou avant × 100 m².

La sensibilité de la carte au seuil de 80 % et à la condition « année suivante » est
mesurée avec les points de validation au §14.4 : la précision ne change presque pas.

**La dernière année n'est pas publiée.** Elle n'a qu'une observation, donc la règle des 80 % y
est toujours remplie : sa surface serait le bâti brut, bruit compris. La dernière année
classée (2026) sert seulement à confirmer les années précédentes ; les pixels qui ne
deviennent bâtis qu'en 2026 sont comptés « non bâti ». Les indicateurs vont de **2016 à
2025** ; 2026 sera publiée à la mise à jour 2027.

Au dernier calcul (surface bâtie publiée, ha) :

| Ville | 2016 | 2017 | 2018 | 2025 | Hausse 2016 → 2025 |
|---|---|---|---|---|---|
| Dakar | 21 134 | 22 782 | 23 215 | 31 775 | +50 % |
| Touba | 8 542 | 9 762 | 9 930 | 14 578 | +71 % |
| Thiès | 3 721 | 4 139 | 4 304 | 6 813 | +83 % |
| Mbour | 4 330 | 4 617 | 4 759 | 7 813 | +80 % |

**Pourquoi 2016 et pas avant ?** Sentinel-2A a été lancé en juin 2015 : aucune scène ne couvre
la saison sèche 2015. Remonter plus loin demanderait Landsat (30 m), une autre série, non
comparable pixel à pixel. Le recul historique viendra de GHSL (1975–2030, 100 m), en contexte.

---

## 9. Évaluation

### 9.1 Ce qui est mesuré aujourd'hui : la concordance (étape 1)

Les 30 % de points de test, jamais vus par le modèle, sont classés et comparés à leur
étiquette. Indicateurs (`outputs/model/accuracy_by_city.json`) :

- **Exactitude globale** : part des points bien classés ;
- **Kappa** : exactitude corrigée de l'accord dû au hasard (0 = hasard, 1 = parfait) ;
- **Précision producteur** (rappel) : parmi les vrais « bâti », part retrouvée par la carte
  → mesure les **oublis** ;
- **Précision utilisateur** : parmi les pixels que la carte dit « bâti », part qui l'est
  vraiment → mesure les **fausses alarmes**.

Au dernier calcul : exactitude 0,924 (kappa 0,849) au niveau national, de 0,906 (Dakar) à
0,946 (Touba). À Dakar, la précision utilisateur du bâti est de 0,865 : le modèle y classe
trop de non-bâti en bâti.

**Ce n'est pas la précision réelle de la carte**, pour trois raisons :

1. les points de test viennent des zones où WorldCover et Dynamic World sont d'accord, donc
   des pixels **faciles** : le chiffre est optimiste ;
2. on mesure l'accord avec deux autres modèles, pas avec la réalité du terrain ;
3. on ne teste que 2021, pas les autres années ni l'année d'urbanisation.

### 9.2 La validation nationale (J4)

La vraie précision vient d'un échantillon de 480 points **tiré dans notre propre carte** et
**photo-interprété à l'aveugle**, avec une marge d'erreur par ville (§14). Elle est plus
basse que la concordance : **0,85 ± 0,04** pour le bâti / non bâti en 2025, **0,82 ± 0,04**
pour les trois classes 2016 → 2025, de 0,77 (Mbour) à 0,85 (Dakar). Le point faible est le
nouveau bâti : la moitié seulement de celui de la carte est vrai (§14.4).

---

## 10. Hypothèses et limites

| Hypothèse / limite | Conséquence |
|---|---|
| **Transfert temporel** : un modèle appris en 2021 vaut pour 2016–2026 | Si une année est plus brumeuse ou plus poussiéreuse (harmattan), ses réflectances changent et le modèle peut s'y tromper ; le niveau L1C n'est pas corrigé de l'atmosphère |
| Étiquettes = zones d'accord seulement | Le modèle connaît moins bien les cas limites (bâti épars, lisières) |
| Résolution 10 m (SWIR à 20 m) | On détecte des ensembles de bâtiments plutôt que des maisons isolées |
| Sable, plages, tannes | Confusions possibles avec le bâti, réduites mais pas supprimées |
| Parcelles agricoles aménagées | Le modèle n'a presque pas vu d'exploitations irriguées à l'entraînement : leurs planches régulières, claires en saison sèche, peuvent être classées en bâti année après année, et le filtre temporel ne les retire donc pas. Plus grand cas connu : 75 ha au nord-est de Thiès, laissés sur la carte et signalés (§14.4, §15.6) |
| 2016 (Sentinel-2A seul), 2017 (peu de scènes claires) | Composites moins bons ; le saut 2016 → 2017 est probablement exagéré |
| Années sèches (2017, 2019 à Dakar) | Fausses détections en périphérie ; le filtre (dont la condition « année suivante ») les retire en grande partie, mais le saut 2016 → 2017 reste fort à Touba (+14 %, contre +1 % de toits dans Open Buildings, §13) : la validation montre que 4 des 8 points datés de 2017 à Touba ne sont pas bâtis, et que ce sont tous des lotissements non construits : la carte voit l'ouverture des lotissements avant les toits (§14.4). Remède de fond si besoin : entraîner le modèle sur plusieurs années |
| Filtre temporel en fin de période | Moins d'années pour confirmer : la dernière année publiée (2025) n'est confirmée que par 2026, sa croissance est probablement surestimée. La dernière année classée n'est pas publiée (§8) : avec une saison janvier–mai, non filtrée, elle donnait à Thiès +1 865 ha en 2026 contre environ 200 ha par an avant |
| Comptage de pixels | Surface « cartographiée », pas corrigée des erreurs. La validation donne la surface corrigée et sa marge (§14.4) : juste en 2025 pour chaque ville, bâti 2016 surestimé à Dakar |

---

## 11. Indicateurs (étape 4)

`pipeline/s4_indicators.py` part de la carte de l'année d'urbanisation (§8) et calcule chaque
indicateur pour **cinq types d'unités**, toujours dans la zone d'étude :

| Unité | Découpage | Pour quoi |
|---|---|---|
| Ville | Toute la zone d'étude | Comparer les villes |
| Commune | Communes OSM, partie dans la zone (`zones/communes.geojson`) | Unité grand public |
| Secteur | Touba seulement : disque central 0–2 km puis anneaux de 2 km × 8 directions (`zones/sectors.geojson`) | Touba Mosquée couvre presque toute la ville |
| Direction | 8 directions depuis le centre (N, NE…, chaque secteur angulaire de 45° centré sur sa direction) | « Vers où la ville pousse-t-elle ? » |
| Anneau | Anneaux de 2 km autour du centre (`RING_WIDTH_M`) | « La croissance se fait-elle de plus en plus loin ? » |

Un pixel appartient à l'unité qui contient **son centre**. Les communes, secteurs, directions
et anneaux d'une ville redonnent bien le total de la ville (à 0,2 % près pour les communes de
Dakar : quelques pixels de la zone ne tombent dans aucune commune OSM).

### 11.1 Indicateurs annuels (2016–2025)

| Indicateur | Calcul |
|---|---|
| Surface bâtie (ha) | Pixels urbanisés l'année Y ou avant × 100 m² |
| Nouveau bâti (ha) | Surface bâtie de Y − surface de Y−1 (pas de valeur pour 2016) |
| Croissance base 100 | Surface de Y / surface de 2016 × 100 |
| Part de la surface bâtie (%) | Surface bâtie / surface terrestre de l'unité (pixels observés) |

### 11.2 Type de croissance : densification, extension, saut

Règle de l'**Atlas of Urban Expansion** (Angel et al., 2016), calculée pour trois périodes
(`GROWTH_PERIODS`) : 2016 → 2020, 2020 → 2025 et 2016 → 2025. Pour une période de D à F :

1. **Bâti urbain de départ.** Un pixel bâti en D est « urbain » (urbain ou périurbain dans
   l'Atlas) si le bâti occupe **au moins 25 %** (`GROWTH_MIN_BUILT_SHARE`) des terres d'un
   **cercle de 1 km²** autour de lui (rayon 564 m, `GROWTH_CIRCLE_RADIUS_M` ; la mer n'est pas
   comptée). En dessous, c'est du bâti « rural » : villages, maisons isolées.
2. **Emprise urbaine de départ** = bâti urbain + **frange** de terrain libre à moins de
   **100 m** (`GROWTH_FRINGE_M`) + **espaces libres enclavés** de moins de **200 ha**
   (`GROWTH_MAX_HOLE_HA`) qui ne touchent ni le bord de la zone ni la mer.
3. Chaque pixel devenu bâti après D et au plus tard en F est classé :
   - **densification** s'il est dans l'emprise de départ ;
   - **extension** s'il est hors de l'emprise, dans un îlot de nouveau bâti (pixels voisins,
     diagonales comprises) qui touche l'emprise ;
   - **saut** sinon : îlot isolé, qui ne touche pas l'emprise.

Les surfaces de chaque type sont publiées en hectares et en part du nouveau bâti de la
période (`src/indicators.py`, `growth_types` ; cartes `growth_type_<D>_<F>.tif`).

**Pourquoi le seuil de 25 %.** Une première version prenait tout le bâti de départ pour
tracer l'emprise. À 10 m, le bâti de 2016 est éparpillé dans toute la périphérie (villages,
maisons isolées, fausses détections) et sa frange de 100 m couvrait presque tout : 81 à 86 %
du nouveau bâti sortait en densification dans les quatre villes, même là où Touba s'étale
nettement. L'Atlas, conçu pour Landsat (30 m), écarte justement le bâti rural de l'emprise.

Au dernier calcul (part du nouveau bâti 2016 → 2025, %) :

| Ville | Densification | Extension | Saut |
|---|---|---|---|
| Dakar | 36,0 | 25,8 | 38,2 |
| Touba | 37,5 | 35,4 | 27,1 |
| Thiès | 27,6 | 21,8 | 50,6 |
| Mbour | 36,9 | 26,9 | 36,2 |

**Sensibilité aux paramètres.** Le calcul 2016 → 2025 a été refait avec un seuil de densité
de 20, 25 et 30 %, une frange de 50, 100 et 150 m, et des trous enclavés de 100, 200 et
400 ha (11 combinaisons) :

| Part du nouveau bâti (%) | Dakar | Touba | Thiès | Mbour |
|---|---|---|---|---|
| Densification (min – max) | 26,6 – 44,9 | 29,6 – 46,2 | 20,8 – 35,1 | 27,6 – 47,7 |
| Extension (min – max) | 21,6 – 30,2 | 27,5 – 42,9 | 17,0 – 26,7 | 20,6 – 31,8 |
| Saut (min – max) | 33,5 – 43,2 | 26,3 – 27,5 | 48,0 – 52,6 | 31,7 – 40,5 |

- Les **valeurs** dépendent des paramètres : la densification varie de 14 à 20 points selon
  la ville (un seuil plus bas ou une frange plus large l'augmentent). La taille des trous
  enclavés ne change presque rien (moins d'un demi-point).
- Le **classement des villes** est stable : dans les 11 combinaisons, Thiès a le plus de saut
  et le moins de densification et d'extension, Touba le plus d'extension, et l'ordre du saut
  (Thiès, Dakar, Mbour, Touba) ne change jamais. En revanche Dakar, Touba et Mbour sont trop
  proches en densification (1 à 2 points) pour être classées entre elles.
- On garde les valeurs de l'Atlas (25 %, 100 m, 200 ha) ; les écarts de quelques points
  entre villes ne sont pas à commenter.

**À lire avec prudence :**
- l'emprise est celle du **début** de la période : sur dix ans, la densification est plus
  faible que sur les sous-périodes (environ 50 % en 2016 → 2020 et 2020 → 2025), car le bâti
  construit en 2018 ne compte pas dans l'emprise de 2016 ;
- le nouveau bâti autour d'un **village** compte comme saut (le village est du bâti rural) :
  c'est une part importante du saut à Thiès, dont la zone contient beaucoup de villages ;
- les **fausses détections** isolées qui passent le filtre temporel tombent surtout dans le
  saut. Le contrôle avec Open Buildings (§13) montre que la fiabilité du saut **dépend de la
  ville** : 65 % des pixels de saut sont confirmés par des toits à Touba (plus que la
  densification), mais 36 % seulement à Thiès et 43 % à Dakar. La validation (§14.4) le
  confirme : 45 % seulement des points de saut sont vraiment du nouveau bâti (5 sur 16 à
  Thiès), contre 69 % pour l'extension. Les types de croissance sont donc **indicatifs**, et
  le saut de Thiès (51 % du nouveau bâti) en grande partie une erreur.

## 12. Population et consommation d'espace

### 12.1 Source : WorldPop Global 2

**WorldPop Global 2, R2025A v1** (Bondarenko et al., 2025, CC BY 4.0) : nombre d'habitants
par cellule de 3 secondes d'arc (environ 93 m × 90 m à cette latitude), une carte par année de
2015 à 2030. Version **contrainte** : la population de chaque unité administrative (projetée
à partir des recensements) n'est répartie que sur les cellules où un produit satellitaire
voit du bâti. Les fichiers du Sénégal sont téléchargés une fois dans `data/raw/worldpop/`.

Passage à la grille de 10 m : la population de chaque cellule est divisée par sa surface
(calculée sur la sphère, `cell_areas_m2`), cette densité est rééchantillonnée au plus proche
voisin sur la grille de la ville, puis multipliée par 100 m². Les totaux par zone sont à
0,4 % près d'une somme directe des cellules dont le centre est dans la zone.

### 12.2 Indicateurs

| Indicateur | Calcul | Unités |
|---|---|---|
| Population | Somme des habitants WorldPop dans la zone | Ville seulement |
| Surface bâtie par habitant (m²) | Surface bâtie / population | Ville seulement |
| ODD 11.3.1 | Taux de consommation des terres / taux de croissance de la population, sur une période | Ville seulement |
| Population recensée 2023 | Population du RGPH-5 (§13.4) | Communes entièrement dans la zone |
| Surface bâtie par habitant recensé 2023 (m²) | Surface bâtie 2023 / population recensée 2023 | Communes entièrement dans la zone |

**WorldPop n'est publié que pour les villes entières** : le contrôle avec le recensement
(§13.4) montre que ses totaux sont bons mais que sa répartition entre communes est fausse
d'un facteur 0,35 à 2,9 ; il en va de même pour les secteurs, directions et anneaux. Par
commune, on publie à la place le **recensement de 2023**, pour les communes entièrement
dans la zone d'étude (60 communes : 51 à Dakar, 5 à Mbour, 3 à Thiès, Mbacké). Ses valeurs
de m² bâtis par habitant vont de 16 (Biscuiterie) à 331 (La Somone, station balnéaire).
WorldPop par commune reste calculé pour ce contrôle (`data/worldpop_by_commune.csv`, non
publié).

ODD 11.3.1 (méthode ONU-Habitat) : taux de consommation des terres = ln(B_F / B_D) / n,
taux de croissance de la population = ln(P_F / P_D) / n, où B est la surface bâtie, P la
population et n le nombre d'années (il s'annule dans le rapport). **Au-dessus de 1**, le bâti
s'étend plus vite que la population : la ville s'étale et sa densité baisse. Le rapport
n'est pas publié si la population baisse ou ne change pas.

Les m² bâtis par habitant ne sont pas publiés pour les communes de moins de **1 000
habitants** (`MIN_POPULATION`) : quelques centaines d'habitants donnent des rapports sans
signification.

Au dernier calcul :

| Ville | Population 2016 | Population 2025 | m² bâtis / hab. 2016 | 2025 | ODD 11.3.1 (2016 → 2025) |
|---|---|---|---|---|---|
| Dakar | 3 498 869 | 4 198 345 | 60 | 76 | 2,24 |
| Touba | 972 921 | 1 335 013 | 88 | 109 | 1,69 |
| Thiès | 442 607 | 550 456 | 84 | 124 | 2,77 |
| Mbour | 492 866 | 635 396 | 88 | 123 | 2,32 |

### 12.3 Limites

- **Population modélisée, pas recensée.** Les totaux sont des projections ; leur répartition
  dans l'unité administrative suit le bâti vu par satellite. Le contrôle avec le RGPH-5
  (§13.4) confirme que les **totaux** sont bons mais que la **répartition entre communes**
  est fausse d'un facteur 0,35 à 2,9 : d'où la publication par ville seulement.
- Le recensement ne donne qu'une date (2023) et ne couvre que les communes entièrement dans
  une zone : Touba Mosquée (58 % de sa surface dans la zone) n'a pas de valeur par commune.
- WorldPop et SamaReew n'utilisent pas la même carte du bâti : une partie de l'écart de
  croissance entre bâti et population peut venir de là.
- La croissance du bâti en 2025 est probablement surestimée (§10) : l'ODD 11.3.1 2020 → 2025
  l'est aussi.

---

## 13. Contrôle croisé avec GHSL et Open Buildings (étape 6)

`pipeline/s6_crosscheck.py` compare nos cartes à deux produits indépendants de notre modèle,
ramenés par Earth Engine sur notre grille de 10 m :

| Référence | Ce qu'elle mesure | Années | Licence |
|---|---|---|---|
| **Open Buildings Temporal v1** (Google, Sirko et al., 2023) | Confiance « bâtiment » de sous-pixels de 0,5 m (résolution effective 4 m), déduite de Sentinel-2 | Une carte par an, 2016–2023 | CC BY 4.0 (ou ODbL) |
| **GHSL GHS-BUILT-S** R2023A (Pesaresi et Politis, 2023) | Surface de bâtiments (m²) par cellule | 10 m en 2018 ; 100 m tous les 5 ans de 1975 à 2030 | Réutilisation libre avec citation (Commission européenne) |

Pour Open Buildings, un sous-pixel est un toit si sa confiance est ≥ **0,5**
(`OB_PRESENCE_THRESHOLD`) ; la **part de toits** de chaque pixel de 10 m est la moyenne de ses
sous-pixels. Les confiances ne sont pas calibrées : le seuil change la surface de toits, pas
la logique des comparaisons.

**Les surfaces ne sont pas comparables directement.** Les deux références mesurent des
**toits** ; notre carte mesure des **pixels bâtis** (toits, cours, rues entre les maisons).
Notre surface est donc 2 à 5 fois plus grande, par définition (Dakar 2023 : 28 711 ha de
pixels bâtis, 7 561 ha de toits selon Open Buildings). On compare donc **où** les cartes
s'accordent et **à quel rythme** elles grandissent.

### 13.1 Mesures (`src/crosscheck.py`)

| Mesure | Calcul | Ce qu'elle dit |
|---|---|---|
| Toits dans notre bâti | Part de la surface de toits de la référence qui tombe dans nos pixels bâtis | Proche de 100 % : on oublie peu de bâtiments |
| Taux de confirmation | Part de nos pixels qui ont des toits à proximité : au moins **5 %** de toits en moyenne dans une fenêtre de **30 m × 30 m** (`CHECK_MIN_ROOF_PCT`, `CHECK_WINDOW_PX`), soit environ une petite maison | Élevé : nos pixels bâtis correspondent à de vrais bâtiments ; calculé par groupe (bâti 2016, nouveau bâti par type de croissance, non bâti pour comparaison) |
| Corrélation par hectare | Corrélation entre notre part bâtie et la part de toits, sur des mailles de 1 ha entièrement dans la zone | Les deux cartes placent-elles le bâti dense au même endroit ? |
| Croissance | Croissance de la surface sur une période commune | Les deux sources racontent-elles la même évolution ? |

La fenêtre de 30 m absorbe les petits décalages entre les deux cartes. Le taux de
confirmation n'est pas une précision : une maison neuve sur une grande parcelle ne
confirme que les pixels proches d'elle, et un bâtiment qu'Open Buildings rate n'est pas
forcément absent.

### 13.2 Résultats au dernier calcul

| Mesure | Dakar | Touba | Thiès | Mbour |
|---|---|---|---|---|
| Toits Open Buildings 2023 dans notre bâti | 96 % | 94 % | 93 % | 93 % |
| Toits GHSL 2018 (10 m) dans notre bâti | 87 % | 78 % | 77 % | 74 % |
| Corrélation par hectare, Open Buildings 2023 | 0,79 | 0,84 | 0,86 | 0,88 |
| Corrélation par hectare, GHSL 2018 | 0,88 | 0,92 | 0,92 | 0,92 |
| Confirmés (Open Buildings 2023) : bâti 2016 | 75 % | 84 % | 80 % | 80 % |
| — nouveau bâti 2017–2023 | 48 % | 57 % | 43 % | 56 % |
| — dont densification | 48 % | 50 % | 55 % | 57 % |
| — dont extension | 55 % | 59 % | 45 % | 59 % |
| — dont saut | 43 % | 65 % | 36 % | 54 % |
| — non bâti (pour comparaison) | 4 % | 5 % | 2 % | 4 % |
| Croissance 2016 → 2023 : SamaReew | +36 % | +52 % | +63 % | +56 % |
| Croissance 2016 → 2023 : Open Buildings (toits) | +33 % | +44 % | +51 % | +54 % |
| Croissance annuelle : SamaReew 2016 → 2020 | 5,1 % | 6,7 % | 8,3 % | 7,0 % |
| Croissance annuelle : GHSL 2015 → 2020 | 2,5 % | 3,2 % | 2,0 % | 2,3 % |

### 13.3 Lecture

- **Peu d'oublis.** 93 à 96 % des toits d'Open Buildings tombent dans notre bâti ; un peu
  moins pour GHSL (74 à 87 %), qui voit plus de petits bâtiments épars.
- **Le nouveau bâti est moins sûr que l'ancien.** Environ la moitié de notre nouveau bâti a
  des toits à moins de 30 m dans Open Buildings 2023, contre 75 à 84 % du bâti de 2016 et
  2 à 5 % du non-bâti. Le nouveau bâti comprend des parcelles en chantier ou clôturées,
  encore sans toit visible à 4 m, mais aussi des fausses détections : la validation (§14.4)
  montre que 51 % du nouveau bâti cartographié est bâti en 2025, et 25 % de plus en
  lotissement non construit ou en chantier ; 15 % seulement sont de vraies fausses détections.
- **Même rythme qu'Open Buildings à Dakar et à Mbour** (+36 % contre +33 %, +56 % contre
  +54 %). À **Touba**, l'écart vient de 2017 : +14 % chez nous, +1 % de toits ; ensuite les
  pentes sont parallèles. À **Thiès**, notre croissance est plus forte à partir de 2019
  (+63 % contre +51 %), en accord avec le taux de confirmation le plus faible : c'est la ville
  où la carte est la moins sûre.
- **L'écart avec GHSL vient de sa méthode, pas de notre carte.** GHSL n'observe vraiment que
  1975, 1990, 2000, 2014 (Landsat) et 2018 (Sentinel-2) ; les époques intermédiaires sont
  interpolées et 2025–2030 extrapolées. Sa croissance 2015 → 2020 est donc reconstruite, pas
  observée, et elle est deux à quatre fois plus faible que la nôtre comme que celle d'Open
  Buildings (qui, lui, est observé chaque année). GHSL reste utile pour le **recul
  historique** (1975–2015) et pour la position du bâti en 2018 (corrélation 0,88 à 0,92).
- Open Buildings a ses propres irrégularités : sa surface de toits baisse en 2022 à Dakar
  et à Mbour, ce qui est très improbable.

Les tables sont dans `outputs/crosscheck/` (`built_area_sources.csv`, `agreement.csv`) ; la
série GHSL 1975–2030 par ville peut servir de contexte historique sur le site.

### 13.4 Population : WorldPop face au recensement (RGPH-5, 2023)

**Source.** Le « Répertoire des localités » de l'ANSD donne la population recensée de chaque
quartier et village, avec sa commune, pour 1988, 2002, 2013 et 2023 (export CSV par région
et par année, `CENSUS_URL`). Les données publiées par l'ANSD sont sous **CC BY 4.0** (« Les
informations publiées sur le site web de l'ANSD sont sous licence ouverte », Flash de
M@demba n° 022/2024). La somme des localités de la région de Thiès (2 463 679 habitants)
correspond au rapport régional définitif (2 463 677).

**Méthode.** Seules les communes **entièrement** dans une zone (`share_of_commune` ≥ 0,99,
`CENSUS_MIN_SHARE`) sont comparées : pour elles, la population WorldPop de l'étape 4 et le
recensement portent sur le même territoire, aux écarts près entre limites OSM et limites
officielles. Les noms OSM et ANSD sont rapprochés sans accents, majuscules, tirets ni
apostrophes ; sept variantes d'orthographe sont listées dans `CENSUS_COMMUNE_ALIASES`
(Bambylor / BAMBILOR, Yenne / YENE…). Comparaison : WorldPop 2023 / recensement 2023.

**Résultats au dernier calcul** (`outputs/crosscheck/population_census.csv`) :

| Ville | Communes comparées | Recensement 2023 | WorldPop 2023 | Rapport des totaux | Rapport médian |
|---|---|---|---|---|---|
| Dakar | 51 | 3 796 096 | 3 674 840 | 0,97 | 0,92 |
| Touba (Mbacké seule) | 1 | 101 451 | 104 585 | 1,03 | 1,03 |
| Thiès | 3 | 391 253 | 305 232 | 0,78 | 0,94 |
| Mbour | 5 | 396 470 | 463 377 | 1,17 | 1,98 |

**Lecture.**
- **Les totaux tiennent** là où l'échantillon est grand : 97 % de la population recensée
  pour les 51 communes de Dakar. Touba Mosquée (1 120 824 habitants recensés) n'est pas
  entièrement dans la zone et ne peut pas être comparée.
- **La répartition entre communes est mauvaise** : le rapport va de **0,35** à **2,9**.
  WorldPop **surestime** les quartiers d'affaires, aisés ou touristiques, où le bâti est
  étendu mais peu habité : Fann-Point E-Amitié et Ngor (×2,9), Dakar-Plateau (×1,9),
  Hann Bel-Air (×1,8, port et industries), Saly (×2,4), La Somone (×2,3). Il **sous-estime**
  les quartiers populaires denses : Biscuiterie (×0,35), Grand-Dakar (×0,38), Médina et
  Parcelles Assainies (×0,57). C'est l'effet attendu d'une répartition proportionnelle au
  bâti, qui ignore la densité des logements. À Thiès, l'écart entre Thiès Est (×0,43) et
  Thiès Nord (×1,10) vient aussi des limites OSM, imprécises dans cette ville.
- **La croissance de WorldPop suit le bâti, pas la population** : dans les communes déjà
  entièrement bâties du centre de Dakar, WorldPop donne partout environ 0,23 % par an, quel
  que soit le recensement (de −1,4 % à +3,1 % par an entre 2013 et 2023). Le recensement de
  2013 n'est pas disponible sous le même nom pour toutes les communes (communes créées ou
  renommées depuis).

**ODD 11.3.1 contrôlé avec le recensement** (21/10/2026, `python -m pipeline.s6_crosscheck
--census`, `outputs/crosscheck/sdg_census.csv`). WorldPop répartit la population d'après une
carte satellitaire du bâti : sa croissance pourrait suivre le bâti, ce qui rendrait l'ODD
11.3.1 en partie circulaire. Sur les communes présentes aux deux recensements (2013 et 2023)
et entièrement dans une zone, on calcule l'ODD avec la population recensée et avec WorldPop.
Les périodes diffèrent (recensement 2013–2023, carte et WorldPop 2016–2023) : on compare des
taux annuels, en les supposant constants (`sdg_11_3_1_annual`).

| | Communes | Habitants 2023 (recensement) | Population, % par an : recensement | WorldPop | Bâti, % par an | ODD 11.3.1 : recensement | WorldPop |
|---|---|---|---|---|---|---|---|
| Dakar | 33 | 2 628 289 | 1,41 | 1,42 | 1,13 | 0,80 | 0,80 |
| Thiès | 3 | 391 253 | 2,10 | 2,39 | 2,65 | 1,26 | 1,11 |

Mbour et Touba n'ont aucune commune comparable (communes créées ou renommées depuis 2013).

- **Pas de circularité visible au total.** Sur les 33 communes de Dakar (2,6 millions
  d'habitants), la croissance de WorldPop est celle du recensement à 0,01 point près, et
  l'ODD est le même. La répartition de WorldPop entre communes est fausse (voir plus haut),
  mais ses erreurs se compensent dans la somme. À Thiès, WorldPop surestime la croissance de
  la population (2,39 contre 2,10 % par an) : l'ODD de WorldPop serait plutôt **sous**-estimé.
- **Ces communes sont le cœur ancien, qui se densifie.** Dans les 33 communes de Dakar, la
  population croît plus vite que le bâti (ODD 0,80) ; elles ne portent que 12 600 des
  28 700 ha bâtis de la zone en 2023. L'étalement de Dakar (ODD 2,24 pour la ville) se fait
  donc dans les communes périphériques, en partie hors zone, que le recensement de 2013 ne
  permet pas de contrôler. Le contrôle couvre le cœur, pas la périphérie où WorldPop est le
  plus incertain.

**Conséquence** (décision du 06/10/2026, ROADMAP §9). Les indicateurs WorldPop (population,
m² bâtis par habitant, ODD 11.3.1) ne sont publiés que pour les **villes** ; par commune, on
publie la population recensée en 2023 et les m² bâtis par habitant qui en découlent (§12.2).

## 14. Validation nationale (étape 5)

`pipeline/s5_validation.py` mesure la précision réelle de la carte 2016 → 2025 : on tire des
points au hasard dans la carte, on regarde sur des images à très haute résolution ce qu'ils
sont vraiment, sans connaître la réponse de la carte, puis on estime la précision en tenant
compte de la surface de chaque strate (Olofsson et al., 2014).

### 14.1 Plan d'échantillonnage

**Même plan dans les quatre villes** (`VALIDATION_POINTS`, graine `VALIDATION_SEED = 42`) :
5 strates tirées dans la carte de l'année d'urbanisation (§8) et dans celle du type de
croissance 2016 → 2025 (§11.2), soit **120 points par ville et 480 au total**.

| Strate (classe de la carte) | Points par ville | Part de la surface : Dakar | Touba | Thiès | Mbour |
|---|---|---|---|---|---|
| Non bâti en 2025 | 40 | 63,8 % | 64,7 % | 81,8 % | 73,6 % |
| Bâti dès 2016 | 32 | 24,1 % | 20,7 % | 9,9 % | 14,6 % |
| Nouveau bâti — densification | 16 | 4,4 % | 5,5 % | 2,3 % | 4,3 % |
| Nouveau bâti — extension | 16 | 3,1 % | 5,2 % | 1,8 % | 3,2 % |
| Nouveau bâti — saut | 16 | 4,6 % | 4,0 % | 4,2 % | 4,3 % |

Pourquoi ce plan (décision du 06/10/2026, ROADMAP §9) :

- **Les petites strates sont sur-échantillonnées.** Le nouveau bâti couvre 8 à 15 % de la
  surface mais reçoit 40 % des points : c'est là que la carte est la moins sûre (§13 : la
  moitié seulement est confirmée par des toits Open Buildings). La pondération par la
  surface corrige ensuite ce déséquilibre.
- **Le nouveau bâti est découpé par type de croissance**, pour mesurer la précision du saut
  (36 % seulement confirmé à Thiès). Avec 16 points, la précision du saut d'une ville est
  **indicative** (marge d'environ ±20 points) ; sur les quatre villes (64 points), la marge
  descend à environ ±11 points.
- **Pas de points en plus à Thiès** : même plan partout pour la comparabilité.
- Marge attendue de la précision globale pondérée : environ ±5 à ±7 points par ville.

Les points sont des **centres de pixels de 10 m**, mélangés dans chaque ville : ni l'ordre ni
l'identifiant (`DAK-001`…) ne trahissent la strate. Fichiers dans `outputs/validation/` :
`labels.csv` (fiche à remplir, sans la classe de la carte), `points.kml` (points et contour
du pixel pour Google Earth Pro, un dossier par ville), `sample_key.csv` (strate, classe et
année de la carte de chaque point : **à ne pas ouvrir pendant l'étiquetage**) et
`strata.csv` (pixels, surface et poids de chaque strate). Cartes de contrôle :
`data/j4_sample_<ville>.png`.

### 14.2 Protocole de photo-interprétation

Dans Google Earth Pro, ouvrir `points.kml`, sans aucune couche de nos cartes. Pour chaque
point, avec l'imagerie historique (icône horloge) :

1. **`built_2016`** : sur l'image la plus proche de la saison sèche 2016 (novembre 2015 –
   mai 2016) ; **`built_2025`** : sur l'image la plus proche de la saison sèche 2025
   (novembre 2024 – mai 2025). Noter la date des images utilisées (`image_date_2016`,
   `image_date_2025`, au format AAAA-MM).
2. **1 = bâti** si **au moins la moitié du carré jaune** est couverte de surfaces construites :
   toits, dalles, bâtiments en chantier (murs montés), routes revêtues, cours et ruelles
   prises dans le tissu bâti. C'est la définition de la carte : des pixels bâtis, pas
   seulement des toits (§13). **0 = non bâti** : sol nu, sable, champ, végétation, eau,
   parcelle vide, même clôturée (noter « clôture »), piste en terre hors du tissu bâti.
3. **`year_built`** (facultatif) : pour un point non bâti en 2016 et bâti en 2025, la première
   année où la construction apparaît, si les images le permettent. Ce n'est qu'une borne :
   les images ne sont pas annuelles partout.
4. **`sure`** : 1 si l'interprétation est sûre, 0 sinon (image floue, pixel à cheval sur un
   bord, chantier ambigu). `note` : remarque libre (« chantier », « clôture », « sable »…).

**Seuls les points tirés au hasard comptent** : aucun point n'est ajouté à la main, même là
où un changement est évident sur les images (décision du 07/10/2026). Un point choisi n'a pas
de poids connu dans l'estimation et favorise les changements faciles à voir, donc ceux que la
carte trouve le mieux.

La **classe de référence** se déduit des deux dates, comme pour la carte : non bâti en 2025 →
non bâti ; bâti en 2016 et en 2025 → bâti dès 2016 ; bâti en 2025 seulement → nouveau bâti
(`src/validation.py`, `reference_class`).

**Seconde lecture : occupation du sol en 2025** (décision du 07/10/2026). La première passe
dit seulement « non bâti » ; or une parcelle de lotissement nivelée ou un chantier sont, pour
l'expansion urbaine, de l'urbanisation en cours, que Sentinel-2 voit à 10 m comme du sol nu
et clair. Pour faire la part des fausses détections et de ces terrains, on reprend **les 228
points étiquetés non bâti en 2025**, sur l'image de 2025 seulement, et on note dans
`outputs/validation/cover_2025.csv` (`cover_2025`) ce qui couvre le carré, dans une **liste
fermée fixée avant la lecture** (`VALIDATION_COVER_CLASSES`) :

| Code | Occupation | Urbanisation en cours ? |
|---|---|---|
| `partly_built` | bâti, mais sur moins de la moitié du carré | oui |
| `construction` | chantier : fondations, dalle ou murs bas (pas encore « murs montés ») | oui |
| `subdivision` | lotissement non construit : parcelles nivelées, bornées ou clôturées, rues tracées | oui |
| `dirt_track` | piste ou route en terre hors du tissu bâti et hors lotissement | non |
| `bare_soil` | sol nu, sable, dune, plage, carrière | non |
| `vegetation` | champ, jachère, arbres, herbe | non |
| `water` | eau, zone humide, tanne | non |
| `other` | autre (préciser dans `note`) | non |

Règles : la lecture reste **à l'aveugle** (les points sont choisis d'après la première
étiquette, jamais d'après la carte ; ne pas ouvrir `sample_key.csv`) ; on ne change pas les
étiquettes de la première passe ; en cas d'hésitation entre deux codes, prendre le plus
« naturel » (par exemple `bare_soil` plutôt que `subdivision` si aucune parcelle n'est
visible) et l'écrire dans `note`. Une rue en terre **dans le tissu bâti** est déjà « bâti » (règle
2 ci-dessus) : elle ne devrait pas apparaître ici. Préparation : `python -m
pipeline.s5_validation --cover` (fiche et `cover_2025.kml`, les mêmes carrés que `points.kml`).

### 14.3 Estimations (`src/validation.py`)

Chaque strate *h* pèse sa part *W_h* de la surface de la ville. Pour un indicateur 0/1
(point bien classé, point vraiment nouveau bâti…), la moyenne de la ville est
Σ *W_h* · moyenne_h, avec une erreur type √(Σ *W_h*² · *s_h*² / *n_h*). Les précisions
utilisateur et producteur sont des **rapports** de deux telles moyennes (Stehman, 2014).
Toutes les valeurs sont données avec leur **marge à 95 %** (1,96 erreur type) :

| Mesure | Question |
|---|---|
| Précision globale pondérée | Quelle part de la surface de la ville est bien classée ? |
| Précision utilisateur par classe | Quand la carte dit « nouveau bâti », a-t-elle raison ? (fausses alarmes) |
| Précision producteur par classe | Le vrai nouveau bâti est-il bien trouvé ? (oublis) |
| Précision par strate | En particulier : le saut est-il fiable dans chaque ville ? |
| Surface corrigée par classe | Surface de nouveau bâti estimée d'après la réalité, avec sa marge, à comparer à la surface cartographiée |
| Année d'urbanisation | Part des points bien datés à ±1 an près, d'après `year_built` (année 2017, année 2025) |
| Croissance corrigée | Croissance du bâti 2016 → 2025 d'après les points, avec sa marge : les villes se classent-elles comme sur la carte ? |

Le niveau national traite les 20 strates ville × strate comme un seul tirage, pondéré par
la surface de chaque zone. Lancement : `python -m pipeline.s5_validation` (sur les points
déjà étiquetés ; une ville n'est estimée que si chaque strate a au moins deux points),
résultats dans `outputs/validation/accuracy.json`. Le rapport donne aussi, par ville et pour
les quatre villes : la précision bâti / non bâti à chaque date (sans tenir compte de la date
du changement, `date_accuracy`), la surface bâtie corrigée en 2016 et en 2025, la précision
globale sur les seuls points marqués sûrs, et la part de nouveau bâti vrai selon l'année
d'urbanisation de la carte.

Une fois la seconde lecture complète, le rapport ajoute une **précision tolérante**
(`tolerant`) : un point non bâti en 2025 mais en urbanisation (`VALIDATION_URBANISING` :
`partly_built`, `construction`, `subdivision`) compte comme bâti, puis les mêmes estimations
sont refaites (précision globale, utilisateur et producteur, surfaces, bâti / non bâti 2025).
Elle s'inspire de l'évaluation « floue » de Gopal et Woodcock (1994). La précision
**stricte reste le chiffre officiel** ; la tolérante dit combien des erreurs de la carte
sont des terrains en cours d'urbanisation. Le rapport donne aussi, pour chaque classe de la
carte, la part pondérée de chaque occupation (`cover_of_map_class`) : par exemple, de quoi
est fait le nouveau bâti cartographié qui n'est pas bâti en réalité.

### 14.4 Résultats

Étiquetage du 07/10/2026 : les 480 points, à l'aveugle, en suivant la règle du §14.2
(confirmée le même jour). Dates des images : janvier à mars 2016 pour 2016, janvier à
mars 2025 pour 2025, sauf **21 points** (8 à Dakar, 13 à Thiès) sans image de 2025, étiquetés
sur une image de 2023 : un bâtiment construit entre 2023 et 2025 y est compté non bâti.
**237 points sur 480 sont marqués « pas sûr »** (34 à Dakar, 67 à Touba, 58 à Thiès, 78 à
Mbour) : pixels à cheval sur un bord, chantiers, images de 2016 floues. Ils sont gardés dans
toutes les estimations.

**Précision pondérée par la surface** (marge à 95 %, `outputs/validation/accuracy.json`) :

| | Dakar | Touba | Thiès | Mbour | Quatre villes |
|---|---|---|---|---|---|
| Globale, 3 classes (non bâti / bâti 2016 / nouveau) | 0,85 ± 0,07 | 0,78 ± 0,07 | 0,84 ± 0,09 | 0,77 ± 0,09 | **0,82 ± 0,04** |
| Bâti / non bâti en 2025 | 0,87 ± 0,06 | 0,83 ± 0,07 | 0,86 ± 0,09 | 0,82 ± 0,09 | **0,85 ± 0,04** |
| Bâti / non bâti en 2016 | 0,94 ± 0,04 | 0,90 ± 0,05 | 0,91 ± 0,07 | 0,90 ± 0,05 | 0,92 ± 0,02 |
| Globale, points sûrs seulement | 0,89 | 0,87 | 0,91 | 0,86 | 0,88 ± 0,04 |
| Nouveau bâti : précision utilisateur | 0,55 ± 0,15 | 0,40 ± 0,14 | 0,52 ± 0,14 | 0,56 ± 0,14 | **0,51 ± 0,08** |
| Nouveau bâti : précision producteur | 0,49 ± 0,22 | 0,40 ± 0,19 | 0,43 ± 0,26 | 0,36 ± 0,16 | 0,43 ± 0,11 |
| Bâti 2016 : précision utilisateur | 0,78 | 0,66 | 0,78 | 0,56 | 0,73 ± 0,09 |
| Non bâti : précision utilisateur | 0,93 | 0,90 | 0,88 | 0,85 | 0,90 ± 0,05 |

La précision sur les seuls points sûrs est une **borne haute** : les points douteux sont
justement les cas difficiles.

**Surfaces corrigées** (ha, d'après les points ; « carte » = comptage de pixels) :

| | Dakar | Touba | Thiès | Mbour | Quatre villes |
|---|---|---|---|---|---|
| Bâti 2016 corrigé | 17 019 ± 3 150 | 6 998 ± 2 019 | 5 668 ± 2 611 | 3 461 ± 1 344 | 33 147 ± 4 757 |
| Bâti 2016 carte | 21 134 | 8 542 | 3 721 | 4 330 | 37 727 |
| Bâti 2025 corrigé | 29 026 ± 5 470 | 13 005 ± 2 871 | 9 382 ± 3 225 | 8 948 ± 2 562 | 60 361 ± 7 425 |
| Bâti 2025 carte | 31 775 | 14 578 | 6 813 | 7 813 | 60 979 |
| Nouveau bâti 2016–2025 corrigé | 12 007 ± 5 346 | 6 007 ± 2 639 | 3 714 ± 2 193 | 5 487 ± 2 386 | 27 214 ± 6 786 |
| Nouveau bâti 2016–2025 carte | 10 641 | 6 036 | 3 092 | 3 483 | 23 252 |

**Croissance corrigée 2016 → 2025** (ajoutée le 21/10/2026, jalon v1.0.1). C'est le rapport
des surfaces bâties corrigées de 2025 et de 2016, moins un (`growth_estimate`). Les deux
surfaces viennent des mêmes points : l'estimateur de rapport (Stehman, 2014) tient compte de
leur corrélation. Un rapport de surfaces est dissymétrique, donc la marge est calculée sur
son logarithme (méthode delta) ; un bootstrap stratifié (20 000 tirages) donne les mêmes
bornes à 3 points près (Dakar : +37 à +112 % contre +40 à +115 %).

| | Dakar | Touba | Thiès | Mbour | Quatre villes |
|---|---|---|---|---|---|
| Croissance cartographiée | +50 % | +71 % | +83 % | +80 % | +62 % |
| Croissance corrigée | **+71 %** | **+86 %** | **+66 %** | **+159 %** | **+82 %** |
| Intervalle à 95 % | +37 à +112 % | +42 à +144 % | +21 à +126 % | +76 à +279 % | +58 à +110 % |

**Écarts entre villes** (`growth_difference`, `growth_comparison` dans `accuracy.json`). Les
échantillons des villes sont indépendants : on compare les logarithmes des facteurs de
croissance, dont les variances s'ajoutent. **Aucun écart n'est établi à 95 %** pour les six
paires. Le plus net est Mbour face à Dakar (rapport des facteurs 0,66, intervalle 0,42 à
1,02) et face à Thiès (0,64, de 0,39 à 1,05). Le classement de la carte (Thiès, Mbour,
Touba, Dakar) n'est donc pas soutenu par la validation : corrigé, Thiès passe dernière et
Mbour première, mais ce classement n'est pas établi non plus. Sur les seuls points sûrs
(borne biaisée, les points douteux sont les cas difficiles), les valeurs bougent encore
(Touba +40 %, Thiès +29 %, Mbour +176 %) : seule Mbour reste nettement au-dessus.

Ce qui tient : **le bâti croît plus vite que la population**. Avec la croissance corrigée et
la population WorldPop (§12.2), l'ODD 11.3.1 vaut 2,9 à Dakar (intervalle 1,7 à 4,1),
2,0 à Touba (1,1 à 2,8), 2,3 à Thiès (0,9 à 3,7) et 3,7 à Mbour (2,2 à 5,3) : il dépasse 1
même à la borne basse sauf à Thiès, où ce n'est pas établi (l'incertitude de WorldPop n'est
pas comptée). Pour les quatre villes ensemble (population +24 %), il vaut 2,8 (2,1 à 3,4),
contre 2,2 avec la carte. Sur les quatre villes, la croissance corrigée (+82 %) est
plus forte que celle de la carte (+62 %), surtout parce que le bâti 2016 de Dakar est
surestimé.

**Sensibilité du filtre temporel** (21/10/2026, `python -m pipeline.s5_validation
--filter-sensitivity`, `outputs/validation/filter_sensitivity.csv`). Le filtre de l'étape 3
(§8) est rejoué sur les piles annuelles avec un seuil de persistance de 0,6, 0,7, 0,8
(publié), 0,9 et 1,0, avec et sans la condition « année suivante » (10 réglages), et chaque
carte obtenue est évaluée sur les mêmes 480 points. L'échantillon a été tiré dans la carte
publiée, mais ses strates restent une partition fixe des zones : les estimations pondérées
restent sans biais pour une autre carte (Stehman, 2014). Le réglage publié redonne
exactement la carte publiée (contrôle du calcul). Quatre villes :

| Réglage | Globale, 3 classes | Nouveau bâti : utilisateur | producteur | Année à ±1 an | Bâti 2016 (ha) | Croissance de la carte |
|---|---|---|---|---|---|---|
| 0,6 | 0,82 | 0,52 | 0,43 | 0,66 | 38 674 | +62 % |
| 0,7 | 0,82 | 0,52 | 0,43 | 0,66 | 38 307 | +61 % |
| **0,8 (publié)** | **0,82** | **0,51** | **0,43** | **0,66** | **37 727** | **+62 %** |
| 0,9 | 0,82 | 0,50 | 0,45 | 0,63 | 36 696 | +64 % |
| 1,0 | 0,82 | 0,48 | 0,45 | 0,61 | 34 433 | +74 % |
| 0,8 sans « année suivante » | 0,82 | 0,51 | 0,43 | 0,69 | 38 097 | +60 % |

Marges à 95 % : ± 0,04 (globale), ± 0,08 (utilisateur), ± 0,11 (producteur), ± 0,12 (année).

- **Le filtre n'explique pas les erreurs de la carte.** Sur les dix réglages, la précision
  globale ne bouge que d'un millième (0,817 à 0,819), et les précisions du nouveau bâti de
  3 à 5 points, bien moins que leur marge. Les erreurs viennent de la classification
  annuelle (lotissements, sol nu, végétation vus comme du bâti), pas de la règle qui en
  déduit l'année : c'est le modèle qu'il faut améliorer (v1.1), pas le filtre.
- **La croissance de la carte dépend du seuil seulement aux extrêmes.** De 0,6 à 0,9, elle
  reste entre +59 et +64 % pour les quatre villes ; à 1,0 (bâti toutes les années), le
  bâti 2016 perd 3 300 ha de pixels qui clignotent et la croissance monte à +74 %. Aucun
  réglage n'atteint la croissance corrigée (+82 %, de +58 à +110 %), qui ne dépend pas de
  la carte. Le bâti 2016 de Dakar reste au-dessus de la valeur corrigée même au seuil 1,0
  (19 405 ha contre 17 019 ± 3 150) : sa surestimation vient surtout de la classification.
- **La condition « année suivante » ne change ni la précision ni, de façon mesurable, la
  datation** (0,66 avec, 0,69 sans, sur 55 points : écart bien moindre que la marge). Elle
  reste justifiée par le mécanisme qu'elle corrige (années sèches, §7 et §8), que 55 points
  datés ne suffisent pas à mesurer.
- **Le classement des villes sur la carte n'est pas stable non plus** : Thiès a la plus
  forte croissance de 0,6 à 0,8, Mbour à 0,9 et 1,0. Cela rejoint la conclusion de la
  croissance corrigée : les villes ne sont pas classées.
- Le réglage publié est gardé. Ce tableau est un diagnostic : choisir un réglage d'après
  ces points les rendrait juges et parties, et la validation ne serait plus indépendante.

**Par strate** (points dont la référence est « nouveau bâti », sur 16 par ville et 64 au total ;
non pondéré) :

| Strate | Dakar | Touba | Thiès | Mbour | Total | Non bâti en réalité | Déjà bâti en 2016 |
|---|---|---|---|---|---|---|---|
| Densification | 9 | 5 | 9 | 8 | 31 (48 %) | 20 | 13 |
| Extension | 11 | 5 | 15 | 13 | 44 (69 %) | 19 | 1 |
| Saut | 7 | 10 | 5 | 7 | 29 (45 %) | 28 | 7 |

**Année d'urbanisation** : sur les 56 points vraiment nouveaux dont l'année a pu être lue sur
les images, la carte est juste **à ±1 an près pour 66 % (± 12 points)**, sans décalage moyen
(+0,02 an). Parmi les points que la carte date de 2025, 14 sur 27 ne sont pas bâtis
(52 %, la plus forte part avec 2018, 3 sur 6 ; de 18 à 46 % les autres années) ; pour 2017, 13 sur 22 sont vraiment nouveaux.

**Seconde lecture : de quoi sont faites les erreurs** (08/10/2026, 228 points non bâtis en
2025 relus sur l'image de 2025 ; 65 en lotissement non construit, 11 en chantier, 1 bâti à
moins de moitié, 11 en piste, 65 en sol nu, 75 en végétation). Part pondérée de la surface
que la carte classe « nouveau bâti » :

| Ce qu'il y a en 2025 | Dakar | Touba | Thiès | Mbour | Quatre villes |
|---|---|---|---|---|---|
| Nouveau bâti vrai | 55 % | 40 % | 52 % | 56 % | 51 % |
| Déjà bâti en 2016 | 5 % | 12 % | 15 % | 14 % | 9 % |
| Lotissement non construit | 18 % | 44 % | 0 % | 17 % | 22 % ± 6 |
| Chantier | 2 % | 2 % | 5 % | 7 % | 3 % |
| Végétation, sol nu, piste (vraie fausse détection) | 20 % | 2 % | 29 % | 6 % | 15 % |

**Précision tolérante** (chantier, lotissement non construit et bâti à moins de moitié
comptent comme bâti ; la stricte reste officielle) :

| | Dakar | Touba | Thiès | Mbour | Quatre villes |
|---|---|---|---|---|---|
| Nouveau bâti : précision utilisateur | 0,75 ± 0,12 | 0,86 ± 0,10 | 0,56 ± 0,14 | 0,80 ± 0,11 | **0,76 ± 0,07** |
| Nouveau bâti : précision producteur | 0,30 ± 0,10 | 0,37 ± 0,10 | 0,37 ± 0,21 | 0,29 ± 0,09 | 0,32 ± 0,06 |
| Globale, 3 classes | 0,74 ± 0,10 | 0,75 ± 0,10 | 0,82 ± 0,09 | 0,71 ± 0,11 | 0,75 ± 0,05 |
| Surface nouveau bâti + urbanisation en cours (ha) | 26 680 ± 8 405 | 14 130 ± 3 836 | 4 736 ± 2 621 | 9 713 ± 3 070 | 55 258 ± 10 082 |

La précision globale tolérante est **plus basse** que la stricte : la tolérance joue dans les
deux sens. Des lotissements se trouvent aussi dans ce que la carte classe « non bâti »
(12 ± 6 % de cette surface au niveau national, 20 % à Dakar, 0 % à Thiès), et comme cette
classe couvre les deux tiers des zones, ils pèsent lourd : les terrains en cours
d'urbanisation couvrent environ 55 000 ha, plus du double du nouveau bâti cartographié.

**Lecture :**

- **La surface bâtie totale est juste.** En 2025, la surface corrigée des quatre villes
  (60 400 ha) est presque égale à la surface cartographiée (61 000 ha), et chaque ville est
  dans sa marge. Les fausses alarmes et les oublis se compensent.
- **Le nouveau bâti de la carte est surtout de l'urbanisation réelle.** La moitié seulement
  est du bâti vraiment nouveau en 2025 (9 % était déjà bâti en 2016), mais **les trois quarts**
  sont du bâti nouveau, en chantier ou en lotissement ; les
  vraies fausses détections (végétation, sol nu, piste) ne font que 15 %. Sentinel-2 voit un
  lotissement nivelé ou clôturé comme du bâti : la carte annonce le bâti avec un temps
  d'avance. Le taux d'environ 50 % confirmé par Open Buildings (§13) s'explique donc surtout
  par des parcelles pas encore construites.
- **Son total tient, mais il ne voit qu'une partie de l'urbanisation.** La surface corrigée
  du nouveau bâti strict (27 200 ± 6 800 ha) est proche de la carte (23 300 ha) ; en
  revanche, la plupart des lotissements non construits restent « non bâti » sur la carte
  (précision producteur tolérante 0,32) : la carte n'est **pas** une carte des lotissements.
- **Le bâti 2016 est surestimé à Dakar** (21 100 ha sur la carte, 17 000 ± 3 200 corrigés) :
  la croissance réelle de Dakar est probablement plus forte que les +50 % cartographiés.
  Dans les autres villes, l'écart reste dans la marge.
- **Le saut est le type le moins fiable** : 28 points de saut sur 64 ne sont pas bâtis, dont
  12 en lotissement ou chantier et 16 de vraies fausses détections (végétation surtout). À
  **Thiès**, 5 points de saut sur 16 seulement sont vrais et aucun n'est un lotissement : la
  forte part de saut de Thiès (51 %) est en grande partie une erreur. L'**extension** est le
  type le plus sûr. La densification contient des pixels déjà bâtis en 2016 (13 sur 64) :
  erreurs de date plutôt que de bâti.
- **Touba : des lotissements, pas du sable.** La précision stricte y est la plus basse
  (0,78), mais 17 des 19 points de densification et d'extension non bâtis sont des
  lotissements, et la précision utilisateur tolérante du nouveau bâti y est la meilleure
  (0,86). Les 4 points datés de 2017 non bâtis sont tous des lotissements : **le saut de 2017
  à Touba (§10) est en bonne partie l'ouverture de lotissements**, que la carte voit dès
  qu'ils sont nivelés, alors qu'Open Buildings attend les toits.
- **Thiès : de vraies fausses détections.** Thiès n'a presque pas de lotissements dans
  l'échantillon ; ses erreurs sont de la végétation et du sol nu (29 % du nouveau bâti
  cartographié), d'où la précision tolérante la plus basse (0,56). La plus grande est une
  **exploitation agricole irriguée de 75 ha** à Fandène, à 9 km au nord-est du centre
  (repérée le 12/10/2026) : classée en bâti dès 2018 (55 à 88 % du bloc chaque année, d'où
  un filtre temporel sans effet), sans toit dans Open Buildings, entièrement en « saut ». Deux
  points de l'échantillon y sont tombés (THI-092, THI-101, vus non bâtis, en végétation) :
  elle est donc déjà comptée dans la précision de Thiès. Elle pèse 2,4 % du nouveau bâti de
  Thiès et 4,8 % de son saut ; sans elle, la croissance 2016–2025 serait de +81,1 % au lieu
  de +83,1 %, et la part de saut de 49,4 % au lieu de 50,6 % : aucun classement ne change.
  Elle reste sur la carte, signalée (§15.6).
- **L'année 2025 est en avance plutôt que fausse** : sur les 14 points datés de 2025 non
  bâtis, 10 sont des lotissements ou des chantiers. La surface « nouveau bâti 2025 » annonce
  de la construction qui n'a pas encore eu lieu ; elle reste **provisoire**.
- Les marges par ville sont larges (± 7 à 9 points pour la précision globale, ± 14 à 26 pour
  le nouveau bâti) : les comparaisons fines entre villes ne sont pas significatives.

**Conséquences pour la publication** (décision du 07/10/2026, ROADMAP §9) : les tableaux
gardent les valeurs de la carte, cohérentes avec les cartes publiées ; les fiches
indicateurs donnent la précision mesurée, et la surface corrigée de chaque ville avec sa
marge est publiée à côté (README, site) ; les types de croissance, surtout le saut, sont
**indicatifs** ; l'année 2025 est **provisoire**.

---

## 15. Données du site (étape 7)

Le site (J5) ne lit que `outputs/`. `pipeline/s7_site_data.py` y dépose, dans
`outputs/site/`, tout ce qu'il lui faut en plus des tableaux d'indicateurs, sous une forme
légère pour les téléphones et les connexions lentes. Le `manifest.json` liste les fichiers,
les légendes, l'emprise et le centre de chaque ville, l'image satellite (`images`), les
erreurs connues signalées sur les cartes (`notes`, §15.6) et les licences (format d'échange
0.2).

### 15.1 Cartes : tuiles PMTiles

Deux couches, pour les quatre villes à la fois (`SITE_LAYERS`) :

| Couche | Classes | Couleurs |
|---|---|---|
| `urbanisation` | bâti en 2016 ; nouveau bâti 2017-2020 ; nouveau bâti 2021-2025 (année d'urbanisation, §8) | gris neutre, puis un même orangé du clair au foncé |
| `growth_type_2016_2025` | densification ; extension ; saut (§11.2) | bleu, orange, vert d'eau |

- **Tuiles raster** (PNG à palette, 256 px, Web Mercator), une archive **PMTiles** par couche :
  un seul fichier statique, lu par morceaux par MapLibre, sans serveur de tuiles.
- **Zooms 8 à 14** : au zoom 14, un pixel de tuile mesure environ 9,2 m au sol à la latitude
  du Sénégal, proche du pixel de 10 m ; au-delà, le site agrandit le zoom 14. Aux zooms
  inférieurs, chaque pixel prend la **classe la plus fréquente** des pixels qu'il couvre : le
  bâti épars s'efface (à Dakar, 14 % du bâti en moins au zoom 10, 6 % au zoom 12). Les cartes
  servent à voir où ; **les chiffres viennent des tableaux, jamais des tuiles**.
- **Années regroupées en deux périodes**, les mêmes que les types de croissance : neuf
  années côte à côte ne se distinguent pas à l'œil sur une carte. Le détail annuel est dans
  les graphiques.
- **Couleurs** vérifiées pour les daltoniens (validateur du guide de visualisation,
  09/10/2026) : le gris de 2016 est volontairement neutre (fond, pas une catégorie) ;
  l'orangé clair et le vert d'eau sont peu contrastés sur fond clair, d'où une légende et un
  tableau toujours à côté de la carte. Le bleu est évité pour le bâti, car le fond de carte
  l'emploie pour l'eau.

**Contrôles au dernier calcul** (09/10/2026) : relues au zoom 14, les tuiles donnent la même
surface que les rasters de 10 m à **0,1 à 0,7 %** près pour chaque ville et chaque classe (un
peu plus, car le pixel de tuile est plus petit que le pixel source) ; 0,06 % des pixels bâtis
tombent juste hors des zones, au bord, par la reprojection. Taille : 2,9 Mo (`urbanisation`)
et 2,2 Mo (`growth_type_2016_2025`) ; une tuile pèse au plus 14,5 Ko (médiane 3,6 Ko au zoom
14), soit moins de 100 Ko pour un écran de téléphone. Cartes de contrôle :
`data/j5_tiles_<couche>.png`. Les archives ne sont pas dans git : l'étape 7 les reconstruit.

### 15.2 Image satellite sous les couches

Sur les cartes des villes, une case affiche sous les couches l'**image Sentinel-2 de 2025**
(`SITE_IMAGE_*`, décision du 09/10/2026). Elle est **désactivée par défaut** : rien n'est
téléchargé tant qu'on ne l'affiche pas, et les couches passent alors à 60 % d'opacité
(curseur réglable).

- **Même image que la carte** : composite médian de la saison sèche 2025 (1er novembre
  2024 – 31 mai 2025), mêmes scènes et même masque des nuages (Cloud Score+ ≥ 0,60) que la
  classification (§4–§7), bandes rouge, vert, bleu (B4, B3, B2) à 10 m, sur le rectangle
  englobant chaque zone. On voit donc ce que le modèle a vu, y compris les lotissements
  nivelés qui expliquent l'avance du nouveau bâti sur les toits (§14.4).
- **Même étirement pour toutes les villes** (comparabilité) : réflectance 0,06 → 0 et
  0,32 → 255 sur les trois bandes (couleurs naturelles), puis gamma 1,1. Choisi à l'œil sur
  Touba (sable clair, réflectances entre 0,15 et 0,30) et Mbour (mer et végétation sombres) :
  un seuil bas de 0,10 noircissait la végétation et la mer (`data/j5_image_stretch_*.png`).
- **Tuiles WebP** (qualité 70), zooms 8 à 14 comme les couches ; moyenne des pixels aux
  zooms inférieurs. À 10 m, on distingue quartiers, routes et parcelles, pas les maisons.
- Attribution : « Contient des données Copernicus Sentinel modifiées (2025) ». Les images
  téléchargées sont en cache dans `data/cities/<ville>/true_colour_2025.tif`
  (`--refresh` pour les retélécharger).

**Au dernier calcul** (09/10/2026) : 1 223 tuiles, **4,8 Mo** pour les quatre villes ; au
zoom 14, une tuile pèse environ 4,6 Ko en médiane (11 Ko au plus, en ville dense), soit 100 à
220 Ko pour un écran de téléphone tout zoomé, environ 30 Ko pour la vue d'ensemble d'une
ville. Contrôle à l'œil des tuiles relues (`data/j5_image_tile_check.png`,
`data/j5_tiles_sentinel2_2025.png`) : routes, Grande Mosquée et parcellaire lisibles à
Touba ; couleurs semblables d'une ville à l'autre. Le quota mensuel gratuit d'Earth Engine
étant épuisé (mode restreint jusqu'au 1er novembre), l'image de **Dakar** a été exportée
vers Google Drive (`python -m pipeline.s7_site_data --drive dakar`), même image et même
emprise, puis déposée dans `data/cities/dakar/`.

### 15.3 Les villes à la même échelle

L'accueil montre les quatre villes côte à côte, à la même échelle (`SITE_FOOTPRINT_*`,
décision du 09/10/2026), avec les classes et les couleurs de la couche `urbanisation` (bâti
en 2016, nouveau bâti 2017-2020, 2021-2025). Une image par ville
(`outputs/site/footprints/<ville>.png`) :

- **80 m par pixel** (blocs de 8 × 8 pixels de 10 m, en UTM 28N), recadrée sur le bâti plus
  1 km de marge ; sur le site, chaque image a une largeur proportionnelle aux kilomètres
  qu'elle couvre, avec une barre d'échelle de 10 km ;
- chaque pixel prend la **classe la plus fréquente** de son bloc et une **opacité égale à la
  part de pixels bâtis** : le bâti épars reste visible, plus pâle, au lieu de disparaître (mode)
  ou de tout remplir ; la surface bâtie est conservée (écart de 0,00 à 0,05 % avec les rasters
  de 10 m) ;
- **PNG à palette** (3 couleurs × 8 niveaux d'opacité) : 45 Ko pour Dakar, 14 à 16 Ko pour
  les autres, 91 Ko en tout (225 Ko en WebP), images chargées en différé.

### 15.4 Limites

Zones, communes et secteurs de Touba en GeoJSON (EPSG:4326), avec les noms d'unités de
`outputs/tables/units.csv` (`city`, `unit_type`, `unit`, `label`), plus les centres.
Simplification à **15 m** (`SITE_SIMPLIFY_M`) en UTM, ville par ville ; pour les communes et
les secteurs, une **simplification de couverture** garde les frontières communes
identiques (ni trou ni chevauchement) ; coordonnées arrondies à 5 décimales (environ 1 m).
Résultat : surfaces modifiées de moins de 0,1 %, chevauchement nul, communes 138 Ko au lieu
de 660 Ko. `communes.geojson` reste sous **ODbL** (© OpenStreetMap contributors).

### 15.5 Validation

`validation.json` reprend, pour chaque ville et pour les quatre villes, ce que le site
montre de §14.4 : précision globale, précision bâti / non bâti en 2016 et 2025, précisions
utilisateur et producteur du nouveau bâti (stricte et tolérante), contenu réel du nouveau
bâti cartographié, et surfaces cartographiées et corrigées avec leur marge.

### 15.6 Erreurs connues signalées sur les cartes

**La carte n'est pas corrigée à la main** (décision du 12/10/2026, ROADMAP §9). Retirer un
bloc faux dans une ville romprait la règle commune aux quatre villes et rendrait la
validation trop optimiste, puisque la carte serait corrigée après la lecture des points.
Une grande fausse détection vérifiée sur les images reste donc dans les rasters, les
tableaux et les tuiles ; elle est **entourée et expliquée** sur la carte de sa ville.

- **Liste** : `config/map_notes.py`, une entrée par erreur (ville, ce qu'il y a sur le
  terrain, rectangle englobant, vérification, date). La liste n'est **pas exhaustive** : c'est
  la validation (§14) qui mesure les erreurs de toute la carte. Une recherche des blocs
  denses sans toits dans Open Buildings montre d'autres cas probables, plus diffus (dunes de
  la côte nord de Dakar, tannes à Mbour, sol nu à l'est de Touba), mêlés à du vrai bâti sans
  toits (aéroport, port, cimenterie) : ils ne sont pas signalés un par un.
- **Contour** (`SITE_NOTE_*`) : le bâti cartographié dans le rectangle, interstices refermés
  (fermeture morphologique de 3 pixels) et trous bouchés, morceaux de moins de 1 ha retirés, tracé 20 m à l'extérieur, simplifié
  à 15 m (`outputs/site/map_notes.geojson`).
- **Poids dans les chiffres** (`note_stats`, `src/site_data.py`) : surface cartographiée,
  année où le bloc apparaît surtout, part du nouveau bâti de la ville, croissance de la ville
  avec et sans le bloc. Le texte du site est écrit à partir de ces valeurs, jamais à la main.
- **Sur le site** : contour noir bordé de blanc (lisible sur les deux fonds et sur l'image
  satellite), cercle repère tant que le zoom est inférieur à 12, explication au toucher, au
  clic ou au survol, et le même texte sous la carte avec un bouton pour y aller. Le survol
  seul n'aurait rien montré sur téléphone.

**Au dernier calcul** (12/10/2026) : une note, l'exploitation agricole de Fandène à Thiès
(§14.4) : 74,9 ha cartographiés, surtout en 2018, 2,4 % du nouveau bâti de Thiès, croissance
+83,1 % avec et +81,1 % sans. Cartes de contrôle : `data/j6_thies_artefact.png` (classification
brute année par année), `data/j6_blocks_without_roofs.png` (blocs sans toits des quatre
villes), `data/j6_note_*.png` (rendu sur le site).

---

## Références

- Breiman, L. (2001). Random Forests. _Machine Learning_, 45, 5–32.
- Xu, H. (2006). Modification of normalised difference water index (NDWI) to enhance open
  water features in remotely sensed imagery. _International Journal of Remote Sensing_, 27(14).
- Zha, Y., Gao, J., Ni, S. (2003). Use of normalized difference built-up index in
  automatically mapping urban areas from TM imagery. _International Journal of Remote Sensing_, 24(3).
- Pasquarella, V. J. et al. (2023). Comprehensive quality assessment of optical satellite
  imagery using weakly supervised video learning (Cloud Score+). _CVPR Workshops_.
- Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200.
- Brown, C. F. et al. (2022). Dynamic World, near real-time global 10 m land use land cover
  mapping. _Scientific Data_, 9, 251.
- Angel, S. et al. (2016). _Atlas of Urban Expansion — 2016 Edition_, vol. 1 : Areas and
  Densities. NYU Urban Expansion Program, UN-Habitat, Lincoln Institute of Land Policy.
- ONU-Habitat (2021). Métadonnées de l'indicateur ODD 11.3.1 (rapport du taux de consommation
  des terres au taux de croissance de la population).
- Bondarenko, M. et al. (2025). Constrained estimates of 2015–2030 total number of people per
  grid square, WorldPop Global 2, R2025A v1. Université de Southampton. doi:10.5258/SOTON/WP00839.
- ANSD (2025–2026). Cinquième Recensement général de la population et de l'habitat (RGPH-5,
  2023) : rapports régionaux définitifs et répertoire des localités. Dakar, ANSD.
- Pesaresi, M., Politis, P. (2023). GHS-BUILT-S R2023A — GHS built-up surface grid, derived
  from Sentinel-2 composite and Landsat, multitemporal (1975–2030). Commission européenne,
  JRC. doi:10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA.
- Sirko, W. et al. (2023). High-Resolution Building and Road Detection from Sentinel-2
  (Open Buildings Temporal). arXiv:2310.11622.
- Olofsson, P. et al. (2014). Good practices for estimating area and assessing accuracy of
  land change. _Remote Sensing of Environment_, 148, 42–57.
- Gopal, S., Woodcock, C. (1994). Theory and methods for accuracy assessment of thematic
  maps using fuzzy sets. _Photogrammetric Engineering and Remote Sensing_, 60(2), 181–188.
- Stehman, S. V. (2014). Estimating area and map accuracy for stratified random sampling
  when the strata are different from the map classes. _International Journal of Remote
  Sensing_, 35(13), 4923–4939.
