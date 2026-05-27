import osmnx as ox

# Définir les villes avec coordonnées approximatives pour les villes qui posent problème
cities = {
    "Bratislava": {"method": "place", "query": "Bratislava, Slovakia"},
    "Odesa": {"method": "place", "query": "Odesa, Ukraine"},
    "Larissa": {"method": "point", "coords": (39.639, 22.417), "dist": 10000}  # rayon 10 km
}

for city, params in cities.items():
    print(f"Processing {city}...")
    if params["method"] == "place":
        G = ox.graph_from_place(params["query"], network_type="drive")
    elif params["method"] == "point":
        G = ox.graph_from_point(params["coords"], dist=params["dist"], network_type="drive")
    
    filename = f"{city.lower()}_roads.graphml"
    ox.save_graphml(G, filepath=filename)
    print(f"{city} saved as {filename}\n")