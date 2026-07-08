import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import LineString
import logging
from sklearn.cluster import DBSCAN
from shapely.geometry import Point

LOGGER = logging.getLogger(__name__)


# def filter_points(points, eps=10):
#     """
#     Filter points using DBSCAN clustering to remove clustered points.
#     Args:
#         points (list): List of shapely Point objects.
#         eps (float): The maximum distance between two samples for one to be considered as in the neighborhood of the other.
#     Returns:
#         list: List of filtered points.
#     """
#     coords = np.array([(point.y, point.x) for point in points])
#     # Convert meters to degrees
#     clustering = DBSCAN(eps=eps / 111139, min_samples=1).fit(coords)
#     unique_labels = set(clustering.labels_)
#
#     filtered_points = []
#     for label in unique_labels:
#         cluster_points = coords[clustering.labels_ == label]
#         centroid = cluster_points.mean(axis=0)
#         filtered_points.append(centroid)
#
#     return [Point(y, x) for y, x in filtered_points]
def filter_points(points, eps=10):
    """
    Filter points using DBSCAN clustering to remove clustered points.
    """
    # Check if the list of points is empty
    if not points:
        return []

    coords = np.array([(point.y, point.x) for point in points])
    # Convert meters to degrees
    clustering = DBSCAN(eps=eps / 111139, min_samples=1).fit(coords)
    unique_labels = set(clustering.labels_)

    filtered_points = []
    for label in unique_labels:
        cluster_points = coords[clustering.labels_ == label]
        centroid = cluster_points.mean(axis=0)
        filtered_points.append(centroid)

    return [Point(y, x) for y, x in filtered_points]

def process_tours(data, interval=15):
    """
    Process tours from the given data.
    Args:
        data (pd.DataFrame): DataFrame containing the data to process.
        interval (int): Time interval in minutes to determine if a new tour starts.
    Returns:
        gpd.GeoDataFrame: GeoDataFrame containing the processed tours.
    """
    boxids = data["boxId"].unique()
    all_tours = []

    for boxid in boxids:
        subset = data[data["boxId"] == boxid]
        subset["createdAt"] = pd.to_datetime(subset["createdAt"])
        subset = subset.sort_values(by="createdAt")
        subset["tdiff"] = subset["createdAt"].diff()
        subset["tour"] = (subset["tdiff"] > pd.Timedelta(
            minutes=interval)).cumsum()
        subset.drop(columns=["tdiff"], inplace=True)

        tours = subset["tour"].unique()
        for tour in tours:
            tour_data = subset[subset["tour"] == tour]
            ps = pd.Series([x for x in tour_data["geometry"]])
            valid_points = [p for p in ps if p is not None]
            # Apply filtering to remove clustered points
            valid_points = filter_points(valid_points)
            if len(valid_points) > 1:
                line = LineString(valid_points)
                start_time = tour_data["createdAt"].iloc[0]
                end_time = tour_data["createdAt"].iloc[-1]
                duration = (end_time - start_time).total_seconds()
                # Convert degrees to meters (approximation for WGS 84).
                distance = line.length * 111139

                # Apply filters: at least 120 seconds, 500 meters, and 10 points
                if duration >= 120 and distance >= 500 and len(valid_points) >= 10:
                    all_tours.append(
                        {
                            "boxid": boxid,
                            "tour": f"tour_{tour}",
                            "geometry": line,
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": duration,
                            "distance": distance,
                            "kcal": calc_calories(
                                duration_s=duration,
                            ),
                        }
                    )

    gdf = gpd.GeoDataFrame(all_tours, geometry="geometry").set_crs("EPSG:4326")

    return gdf


def calc_calories(duration_s):
    """
    Super simple calculation of calories burned based on MET value.
    Args:
        duration_s (int): Duration in seconds.
    Returns:
        float: Estimated calories burned.
    """
    average_weight_kg = 70
    met = 6.5  # reduced intensity
    duration_min = duration_s / 60
    calories_burned = (met * average_weight_kg * 3.5 / 200) * duration_min
    return calories_burned


def calculate_periodic_stats(tours_gdf):
    # Determine if data covers at least 2 unique weeks
    weeks = tours_gdf["start_time"].dt.to_period("W").unique()
    if len(weeks) < 2:
        # Use daily stats
        tours_gdf["period"] = tours_gdf["start_time"].dt.date
    else:
        # Use weekly stats
        tours_gdf["period"] = tours_gdf["start_time"].dt.to_period(
            "W").apply(lambda r: r.start_time)

    periodic_stats = tours_gdf.groupby("period").agg(
        trip_count=("duration", "count"),
        total_duration_s=("duration", "sum"),
        average_duration_s=("duration", "mean"),
        max_duration_s=("duration", "max"),
        min_duration_s=("duration", "min"),
        total_distance_m=("distance", "sum"),
        average_distance_m=("distance", "mean"),
        max_distance_m=("distance", "max"),
        min_distance_m=("distance", "min"),
        average_speed_kmh=("distance", lambda x: (
            x / tours_gdf.loc[x.index, "duration"]).mean() * 3.6),
        total_kcal=("kcal", "sum"),
    ).reset_index().rename(columns={"period": "period_start"})

    # Convert period_start to string for serialization
    periodic_stats["period_start"] = periodic_stats["period_start"].astype(str)

    # Add a "week" column with the same value as "period_start"
    # TODO: remove after renaming "week" to "periodic stat everywhere"
    periodic_stats["week"] = periodic_stats["period_start"]

    return periodic_stats


def tour_stats(tours_gdf):
    latest_stats = {
        "trip_count": len(tours_gdf),
        "total_duration_s": tours_gdf["duration"].sum(),  # unit: seconds
        "average_duration_s": tours_gdf["duration"].mean(),
        "max_duration_s": tours_gdf["duration"].max(),
        "min_duration_s": tours_gdf["duration"].min(),
        "total_distance_m": tours_gdf["distance"].sum(),
        "average_distance_m": tours_gdf["distance"].mean(),
        "max_distance_m": tours_gdf["distance"].max(),
        "min_distance_m": tours_gdf["distance"].min(),
        # unit: km/h
        "average_speed_kmh": (tours_gdf["distance"] / tours_gdf["duration"]).mean() * 3.6,
        "total_kcal": tours_gdf["kcal"].sum(),
    }

    latest_stats = {key: (value.isoformat() if isinstance(
        value, pd.Timestamp) else value) for key, value in latest_stats.items()}
    periodic_stats = calculate_periodic_stats(tours_gdf)

    return {
        "latest_stats": latest_stats,
        "periodic_stats": periodic_stats.to_dict(orient="records"),
        # TODO: remove after renaming "week" to "periodic stat everywhere"
        "weekly_stats": periodic_stats.to_dict(orient="records")
    }
