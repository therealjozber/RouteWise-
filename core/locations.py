"""Approximate coordinates for Tanzanian transport locations."""

LOCATION_COORDS = {
    # Coast & Dar es Salaam region
    "dar es salaam": (-6.7924, 39.2083),
    "chalinze": (-6.6378, 38.3522),
    "bagamoyo": (-6.4330, 38.9000),
    "msata": (-6.3500, 38.7500),
    "pangani": (-5.4250, 38.8000),
    "tanga": (-5.0689, 39.0988),
    "korogwe": (-5.1667, 38.4833),
    "muheza": (-5.1667, 38.7833),
    "mombo": (-4.8833, 38.2833),
    # Central corridor
    "morogoro": (-6.8278, 37.6591),
    "kilosa": (-7.4170, 36.9830),
    "gairo": (-6.3330, 36.8670),
    "mikumi": (-7.4000, 37.0000),
    "dodoma": (-6.1630, 35.7516),
    "singida": (-5.0670, 34.7500),
    "nzega": (-5.0670, 33.1830),
    "tabora": (-5.0165, 32.8012),
    # Northern corridor
    "segera": (-5.5000, 38.5000),
    "same": (-4.0660, 37.7330),
    "moshi": (-3.3500, 37.3400),
    "arusha": (-3.3869, 36.6830),
    "namanga": (-2.5464, 36.7920),
    "karatu": (-3.3500, 35.5333),
    "babati": (-4.2167, 35.7500),
    # Lake Victoria & West
    "mwanza": (-2.5164, 32.9175),
    "musoma": (-1.5000, 33.8000),
    "bukoba": (-1.3333, 31.8167),
    "geita": (-2.8667, 32.2333),
    # Southern Highland corridor
    "iringa": (-7.7700, 35.6900),
    "makambako": (-8.9330, 34.6830),
    "njombe": (-9.3333, 34.7667),
    "mbeya": (-8.9000, 33.4500),
    "tunduma": (-9.3000, 32.7667),
    # South-west
    "sumbawanga": (-7.9667, 31.6167),
    "mpanda": (-6.3500, 31.0667),
    "kigoma": (-4.8793, 29.6257),
    # Southern coast
    "lindi": (-9.9667, 39.7167),
    "mtwara": (-10.2667, 40.1833),
    "masasi": (-10.7333, 38.8000),
    "songea": (-10.6833, 35.6500),
    # Other key towns
    "kahama": (-3.8333, 32.6000),
    "shinyanga": (-3.6604, 33.4280),
    "kibaha": (-6.7811, 38.9140),
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
