import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine

DB_URL = "postgresql://postgres:postgres@postgis:5432/geoapi_db"

def import_muenster_bike_network():
    road_network_muenster = ox.graph_from_place("Münster, Germany", network_type="bike")
    _, edges = ox.graph_to_gdfs(road_network_muenster)
    edges_filtered = edges[~edges['highway'].isin(['primary', 'secondary', 'tertiary'])]
    engine = create_engine(DB_URL)
    edges_filtered.to_postgis("bike_road_network", engine, if_exists="replace", index=False)

if __name__ == "__main__":
    import_muenster_bike_network()