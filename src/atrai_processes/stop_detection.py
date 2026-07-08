import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from datetime import timedelta
import movingpandas as mpd
from movingpandas import TrajectoryCollection, TrajectoryStopDetector
import logging
import psycopg2 
from sqlalchemy import text

from config.db_config import DatabaseConfig 
LOGGER = logging.getLogger(__name__)

def load_bike_data_from_db(box_id: str, start_date: str = None, end_date: str = None, db_engine=None):
    """
    Loads spatial data from postgres for a single boxId and time range 
    into a time-indexed gdf
    """
    LOGGER.info(f"Querying data for boxId: {box_id}")

    gdf = gpd.GeoDataFrame()
    
    sql_base = """
    SELECT 
        "createdAt", 
        "Speed", 
        "Overtaking Manoeuvre", 
        "Overtaking Distance",
        "boxId",
        "geometry"
    FROM 
        osem_bike_data
    WHERE 
        "boxId" = ANY(:box_ids)
    """

    params = {"box_ids": box_id}
    
    if start_date:
        sql_base += f" AND \"createdAt\" >= :start_date"
        params["start_date"] = start_date
    if end_date:
        sql_base += f" AND \"createdAt\" <= :end_date"
        params["end_date"] = end_date
        
    sql_base += " ORDER BY \"createdAt\"" 

    # Use read_postgis to handle geom col
    try:
        gdf = gpd.read_postgis(
            text(sql_base), 
            db_engine, 
            geom_col='geometry', 
            params=params, 
            crs="EPSG:4326"
        )
    except Exception as e:
        LOGGER.error(f"Database query failed: SQL {sql_base}. Params: {params} Error: {e}")
        # raise ProcessorExecuteError(f"Failed to fetch data from DB: {e}")
        
    if gdf.empty:
        return gdf
    
    # Clean and prepare for mpd
    gdf = gdf[gdf.geometry.notnull()].copy()
    gdf['createdAt'] = pd.to_datetime(gdf['createdAt'], utc=True)
    gdf = gdf.set_index('createdAt').sort_index() # Set time as index and sort

    return gdf

def analyze_trajectories(gdf: gpd.GeoDataFrame, id_col: str, max_diam: float, min_dur: timedelta) -> gpd.GeoDataFrame:
    """
    Creates TrajectoryCollection and runs Stop Detection, returning stop points.
    """
    if gdf.empty:
        return gpd.GeoDataFrame()

    collection = mpd.TrajectoryCollection(gdf, id_col)
    
    detector = TrajectoryStopDetector(
        collection,
        max_diameter=max_diam,
        min_duration=min_dur
    )
    
    # Get the results as GeoDataFrame (Point Features)
    stops_gdf = detector.get_stop_points(
        max_diameter=max_diam,
        min_duration=min_dur
    )
    
    return stops_gdf