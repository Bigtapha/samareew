# Fiche méthodologique — cartographie du bâti

_Comment SamaReew produit les cartes annuelles du bâti (2016–2026) des quatre villes.
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

### 9.2 Ce qui viendra : la validation nationale (J4)

Un échantillon **tiré dans notre propre carte**, stratifié par ville × classe (non bâti, bâti
dès 2016, nouveau bâti), environ 120 points par ville, **photo-interprété à l'aveugle** dans
Google Earth Pro. Chaque strate est ensuite pondérée par sa part de la surface de la carte
(`src/validation.py`), ce qui donne une précision par ville avec sa marge d'erreur.

---

## 10. Hypothèses et limites

| Hypothèse / limite | Conséquence |
|---|---|
| **Transfert temporel** : un modèle appris en 2021 vaut pour 2016–2026 | Si une année est plus brumeuse ou plus poussiéreuse (harmattan), ses réflectances changent et le modèle peut s'y tromper ; le niveau L1C n'est pas corrigé de l'atmosphère |
| Étiquettes = zones d'accord seulement | Le modèle connaît moins bien les cas limites (bâti épars, lisières) |
| Résolution 10 m (SWIR à 20 m) | On détecte des ensembles de bâtiments plutôt que des maisons isolées |
| Sable, plages, tannes | Confusions possibles avec le bâti, réduites mais pas supprimées |
| 2016 (Sentinel-2A seul), 2017 (peu de scènes claires) | Composites moins bons ; le saut 2016 → 2017 est probablement exagéré |
| Années sèches (2017, 2019 à Dakar) | Fausses détections en périphérie ; le filtre (dont la condition « année suivante ») les retire en grande partie, mais le saut 2016 → 2017 reste fort à Touba (+14 %), peut-être une base 2016 sous-estimée : à vérifier à la validation (J4). Remède de fond si besoin : entraîner le modèle sur plusieurs années |
| Filtre temporel en fin de période | Moins d'années pour confirmer : la dernière année publiée (2025) n'est confirmée que par 2026, sa croissance est probablement surestimée. La dernière année classée n'est pas publiée (§8) : avec une saison janvier–mai, non filtrée, elle donnait à Thiès +1 865 ha en 2026 contre environ 200 ha par an avant |
| Comptage de pixels | Surface « cartographiée », pas encore corrigée des erreurs ; l'estimation corrigée viendra de la validation (J4) |

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
- Olofsson, P. et al. (2014). Good practices for estimating area and assessing accuracy of
  land change. _Remote Sensing of Environment_, 148, 42–57.
