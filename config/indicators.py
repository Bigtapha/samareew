"""One fact sheet per indicator (ROADMAP §4.2), written to outputs/tables/indicators.json.

Adding an indicator = adding an entry here and computing it in pipeline/s4_indicators.py.
Texts are in French: they are shown as they are on the public site.

- title:       public title
- unit:        unit shown next to the values
- definition:  one sentence
- period:      "year" (one value per year) or "period" (one value per start -> end period)
- sources:     keys of SOURCES
- method:      section of METHODOLOGIE.md
- reliability: how far the value can be trusted (updated after the validation, J4)
"""

SOURCES = {
    "samareew": {
        "name": "SamaReew, d'après Copernicus Sentinel-2 (2016–2026)",
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

_MAP_RELIABILITY = ("Provisoire : concordance de 0,92 avec deux produits de référence ; "
                    "la précision réelle viendra de la validation nationale (J4).")
_POP_RELIABILITY = ("Population modélisée (projection répartie sur le bâti), pas un "
                    "recensement : à lire comme un ordre de grandeur.")

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
        "reliability": _MAP_RELIABILITY + " 2017 et 2025 sont probablement surestimées.",
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
        "reliability": _MAP_RELIABILITY,
    },
    "growth_extension_ha": {
        "title": "Nouveau bâti en extension",
        "unit": "ha",
        "definition": "Nouveau bâti de la période hors de l'emprise de départ, dans un îlot qui la touche.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "growth_leapfrog_ha": {
        "title": "Nouveau bâti par saut",
        "unit": "ha",
        "definition": ("Nouveau bâti de la période dans un îlot qui ne touche pas l'emprise de "
                       "départ, y compris autour des villages."),
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY + " Les petits îlots isolés sont les plus sujets aux erreurs.",
    },
    "growth_densification_share_pct": {
        "title": "Part du nouveau bâti en densification",
        "unit": "%",
        "definition": "Nouveau bâti en densification divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "growth_extension_share_pct": {
        "title": "Part du nouveau bâti en extension",
        "unit": "%",
        "definition": "Nouveau bâti en extension divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "growth_leapfrog_share_pct": {
        "title": "Part du nouveau bâti par saut",
        "unit": "%",
        "definition": "Nouveau bâti par saut divisé par tout le nouveau bâti de la période.",
        "period": "period",
        "sources": ["samareew"],
        "method": "METHODOLOGIE.md#11",
        "reliability": _MAP_RELIABILITY,
    },
    "population": {
        "title": "Population",
        "unit": "habitants",
        "definition": "Somme des habitants estimés par WorldPop dans l'unité.",
        "period": "year",
        "sources": ["worldpop"],
        "method": "METHODOLOGIE.md#12",
        "reliability": _POP_RELIABILITY,
    },
    "built_m2_per_capita": {
        "title": "Surface bâtie par habitant",
        "unit": "m²/hab.",
        "definition": "Surface bâtie divisée par la population (unités de plus de 1 000 habitants).",
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
}
