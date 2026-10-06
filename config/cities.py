"""The cities, one entry each. Adding a city = adding an entry, then re-running step 0.

- name:    display name
- seed:    [lon, lat] inside the city, used to pick its GHSL urban cluster
- centre:  (landmark, [lon, lat], OpenStreetMap source). Rule: the historic heart of the
           city, marked by a landmark everyone knows (as in the Atlas of Urban Expansion).
           Used for growth directions and distance rings.
- sectors: True where one commune covers most of the city (Touba Mosquée): the city is
           then also split into rings x directions (config.settings.SECTOR_RING_M).
- census_regions: ANSD regions holding the communes of the zone (2023 census check, step 6)
"""

CITIES = {
    "dakar": {
        "name": "Dakar",
        "seed": [-17.447, 14.693],
        "centre": ("Place de l'Indépendance", [-17.43206, 14.66953], "way/27811247"),
        "sectors": False,
        "census_regions": ["DAKAR", "THIES"],
    },
    "touba": {
        "name": "Touba",
        "seed": [-15.883, 14.855],
        "centre": ("Grande Mosquée", [-15.87554, 14.86319], "way/362222045"),
        "sectors": True,
        "census_regions": ["DIOURBEL"],
    },
    "thies": {
        "name": "Thiès",
        "seed": [-16.926, 14.791],
        "centre": ("Place de France", [-16.92562, 14.79154], "way/340403572"),
        "sectors": False,
        "census_regions": ["THIES"],
    },
    "mbour": {
        "name": "Mbour",
        "seed": [-16.967, 14.420],
        "centre": ("Quai de pêche (marché aux poissons)", [-16.96940, 14.40780], "way/221602952"),
        "sectors": False,
        "census_regions": ["THIES"],
    },
}
