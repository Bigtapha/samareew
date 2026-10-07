"""One fact sheet per indicator (ROADMAP §4.2), written to outputs/tables/indicators.json.

Adding an indicator = adding an entry here and computing it in pipeline/s4_indicators.py.
Texts are in French: they are shown as they are on the public site.

- title:       public title
- unit:        unit shown next to the values
- definition:  one sentence
- period:      "year" (one value per year) or "period" (one value per start -> end period)
- sources:     keys of SOURCES
- method:      section of METHODOLOGIE.md
- reliability: how far the value can be trusted (from the validation, METHODOLOGIE §14.4)
"""

SOURCES = {
    "samareew": {
        "name": "SamaReew, d'après Copernicus Sentinel-2 (2016–2026)",
        "licence": "CC BY 4.0",
    },
    "ansd": {
        "name": ("ANSD, cinquième Recensement général de la population et de l'habitat "
                 "(RGPH-5, 2023), répertoire des localités"),
        "licence": "CC BY 4.0",
    },
    "worldpop": {
        "name": ("WorldPop Global 2, R2025A v1 (Bondarenko et al., 2025, Université de "
                 "Southampton, doi:10.5258/SOTON/WP00839)"),
        "licence": "CC BY 4.0",
    },
}

UNIT_TYPES = {
    "city": "Ville (zone d'étude : agglomération GHSL 2025 + 2 km)",
    "commune": "Commune (OpenStreetMap, partie dans la zone d'étude)",
    "sector": "Secteur (disque central puis anneaux de 2 km × 8 directions)",
    "direction": "Direction depuis le centre (8 directions)",
    "ring": "Anneau de distance au centre (2 km)",
}

_MAP_RELIABILITY = ("Validée sur 480 points photo-interprétés : 85 % (± 4) de la surface bien "
                    "classée bâti / non bâti en 2025, de 82 % à Mbour à 87 % à Dakar. La surface "
                    "bâtie 2025 est juste en moyenne (corrigée : 60 400 ± 7 400 ha pour 61 000 ha "
                    "cartographiés dans les quatre villes) ; le bâti 2016 est surestimé à Dakar.")
_NEW_BUILT_RELIABILITY = ("Le nouveau bâti est moins sûr : la moitié seulement (51 ± 8 %) de "
                          "celui de la carte est vrai, mais la carte en oublie autant ailleurs, "
                          "et le total corrigé 2016-2025 (27 200 ± 6 800 ha) est proche de la "
                          "carte (23 300 ha). L'année est juste à ±1 an pour 2 points sur 3.")
_GROWTH_TYPE_RELIABILITY = ("Indicatif : seuls 45 % des points de saut sont vraiment du nouveau "
                            "bâti (5 sur 16 à Thiès), contre 48 % pour la densification et 69 % "
                            "pour l'extension.")
_POP_RELIABILITY = ("Population modélisée (projection répartie sur le bâti), pas un "
                    "recensement : bonne à l'échelle de la ville (97 % du recensement 2023 sur "
                    "les communes de Dakar), publiée seulement pour les villes entières.")
_CENSUS_RELIABILITY = ("Recensement : population résidente comptée en 2023. Publiée seulement "
                       "pour les communes entièrement dans la zone d'étude ; limites des "
                       "communes d'après OpenStreetMap, pas les limites officielles.")

INDICATORS = {
    "built_area_ha": {
        "title": "Surface bâtie",
        "unit": "ha",
        "definition": "Surface des pixels de 10 m classés bâtis à la fin de l'année.",
        "period": "year",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#8",
        "reliability": _MAP_RELIABILITY,
    },
    "new_built_ha": {
        "title": "Nouveau bâti dans l'année",
        "unit": "ha",
        "definition": "Surface devenue bâtie pendant l'année (rien pour la première année).",
        "period": "year",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#8",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY,
                                   "2025 est provisoire (52 % des points datés de 2025 ne sont "
                                   "pas bâtis) et 2017 surestimée à Touba."]),
    },
    "growth_index": {
        "title": "Croissance du bâti (2016 = 100)",
        "unit": "indice",
        "definition": "Surface bâtie de l'année divisée par celle de 2016, multipliée par 100.",
        "period": "year",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "built_share_pct": {
        "title": "Part de la surface bâtie",
        "unit": "%",
        "definition": "Surface bâtie divisée par la surface terrestre de l'unité.",
        "period": "year",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "growth_densification_ha": {
        "title": "Nouveau bâti en densification",
        "unit": "ha",
        "definition": ("Nouveau bâti de la période construit à l'intérieur de l'emprise urbaine "
                       "de départ (bâti dense, frange de 100 m et espaces enclavés de moins de "
                       "200 ha ; les villages et maisons isolées n'en font pas partie)."),
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "growth_extension_ha": {
        "title": "Nouveau bâti en extension",
        "unit": "ha",
        "definition": "Nouveau bâti de la période hors de l'emprise de départ, dans un îlot qui la touche.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "growth_leapfrog_ha": {
        "title": "Nouveau bâti par saut",
        "unit": "ha",
        "definition": ("Nouveau bâti de la période dans un îlot qui ne touche pas l'emprise de "
                       "départ, y compris autour des villages."),
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "growth_densification_share_pct": {
        "title": "Part du nouveau bâti en densification",
        "unit": "%",
        "definition": "Nouveau bâti en densification divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "growth_extension_share_pct": {
        "title": "Part du nouveau bâti en extension",
        "unit": "%",
        "definition": "Nouveau bâti en extension divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "growth_leapfrog_share_pct": {
        "title": "Part du nouveau bâti par saut",
        "unit": "%",
        "definition": "Nouveau bâti par saut divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": " ".join([_MAP_RELIABILITY, _NEW_BUILT_RELIABILITY, _GROWTH_TYPE_RELIABILITY]),
    },
    "population": {
        "title": "Population",
        "unit": "habitants",
        "definition": "Somme des habitants estimés par WorldPop dans la ville (zone d'étude entière).",
        "period": "year",
        "sources": ["worldpop"],
        "method": "METHODOLOGIE.md#12",
        "reliability": _POP_RELIABILITY,
    },
    "built_m2_per_capita": {
        "title": "Surface bâtie par habitant",
        "unit": "m²/hab.",
        "definition": "Surface bâtie de la ville divisée par sa population estimée par WorldPop.",
        "period": "year",
        "sources": ["samareew", "worldpop"],
        "method": "METHODOLOGIE.md#12",
        "reliability": _MAP_RELIABILITY + " " + _POP_RELIABILITY,
    },
    "sdg_11_3_1": {
        "title": "Consommation d'espace rapportée à la croissance de la population (ODD 11.3.1)",
        "unit": "ratio",
        "definition": ("Taux de croissance du bâti divisé par taux de croissance de la population "
                       "sur la période ; au-dessus de 1, le bâti s'étend plus vite que la population."),
        "period": "period",
        "sources": ["samareew", "worldpop"],
        "method": "METHODOLOGIE.md#12",
        "reliability": _MAP_RELIABILITY + " " + _POP_RELIABILITY,
    },
    "census_population": {
        "title": "Population recensée en 2023",
        "unit": "habitants",
        "definition": "Population résidente de la commune au recensement de 2023 (RGPH-5).",
        "period": "year",
        "sources": ["ansd"],
        "method": "METHODOLOGIE.md#13",
        "reliability": _CENSUS_RELIABILITY,
    },
    "census_built_m2_per_capita": {
        "title": "Surface bâtie par habitant recensé (2023)",
        "unit": "m²/hab.",
        "definition": "Surface bâtie de la commune en 2023 divisée par sa population recensée en 2023.",
        "period": "year",
        "sources": ["samareew", "ansd"],
        "method": "METHODOLOGIE.md#13",
        "reliability": _MAP_RELIABILITY + " " + _CENSUS_RELIABILITY,
    },
}
