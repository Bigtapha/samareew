"""Known errors of the map, shown on the site maps. Adding a note = adding an entry, then
re-running step 7.

The map is not corrected by hand (decided 12/10/2026, ROADMAP §9): a large false detection
that was checked on the imagery is kept, outlined on the map and explained. The list is not
exhaustive; the validation (METHODOLOGIE §14) measures the errors of the whole map.

- city:     city slug (config/cities.py)
- kind:     "false_detection" (mapped as built-up, not built on the ground)
- title:    what is there on the ground (French, shown to the public)
- bounds:   [west, south, east, north] in degrees, a box around the object; step 7 outlines
            the mapped built-up area inside it and measures its weight in the city's figures
- evidence: how it was checked (French, shown to the public)
- reported: date the note was added
"""

MAP_NOTES = [
    {
        "id": "thies-fandene-farm",
        "city": "thies",
        "kind": "false_detection",
        "title": "Exploitation agricole irriguée (parcelles et bassin), à Fandène",
        "bounds": [-16.85577, 14.82085, -16.84520, 14.83404],
        # validation points THI-092 and THI-101
        "evidence": ("aucun toit dans Open Buildings 2023, et deux points de validation y ont été "
                     "vus non bâtis (végétation)"),
        "reported": "2026-10-12",
    },
]
