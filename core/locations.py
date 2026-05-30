"""Approximate coordinates for Tanzanian transport locations."""

LOCATION_COORDS = {
    "dar es salaam": (-6.7924, 39.2083),
    "morogoro": (-6.8278, 37.6591),
    "chalinze": (-6.6378, 38.3522),
    "dodoma": (-6.1630, 35.7516),
    "arusha": (-3.3869, 36.6830),
    "mwanza": (-2.5164, 32.9175),
    "mbeya": (-8.9000, 33.4500),
    "tanga": (-5.0689, 39.0988),
    "kilosa": (-7.4170, 36.9830),
    "gairo": (-6.3330, 36.8670),
    "singida": (-5.0670, 34.7500),
    "nzega": (-5.0670, 33.1830),
    "moshi": (-3.3500, 37.3400),
    "same": (-4.0660, 37.7330),
    "segera": (-5.5000, 38.5000),
    "bagamoyo": (-6.4330, 38.9000),
    "msata": (-6.3500, 38.7500),
    "mikumi": (-7.4000, 37.0000),
    "iringa": (-7.7700, 35.6900),
    "makambako": (-8.9330, 34.6830),
    "pangani": (-5.4250, 38.8000),
}


def get_coords(location_name: str):
    if not location_name:
        return None
    key = location_name.strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    for name, coords in LOCATION_COORDS.items():
        if name in key or key in name:
            return coords
    return None


def route_endpoints(origin: str, destination: str):
    return get_coords(origin), get_coords(destination)


def location_matches(loc_a: str, loc_b: str) -> bool:
    """Fuzzy match two place names."""
    if not loc_a or not loc_b:
        return False
    a, b = loc_a.strip().lower(), loc_b.strip().lower()
    return a == b or a in b or b in a
