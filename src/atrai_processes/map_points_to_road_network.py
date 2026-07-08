import geopandas as gpd
import logging
import numpy as np


LOGGER = logging.getLogger(__name__)

def histo(data):
    clean_data = data.dropna()
    bins = [0, 50, 100, 150, 200, np.inf]

    counts, bin_edges = np.histogram(clean_data, bins=bins)
    string = ", ".join(str(x) for x in counts)

    return string

def map_points_to_road_segments(
    point_gdf: gpd.GeoDataFrame,
    road_segments: gpd.GeoDataFrame,
    numeric_columns: list,
    id_column: str = "id",
    distance_col: str = "distance_to_road"
) -> gpd.GeoDataFrame:
    """
    Maps point-based data (e.g., roughness, overtaking) to road segments
    and returns a GeoDataFrame of aggregated results per segment.

    Args:
        point_gdf (GeoDataFrame): Point data with geometry and numeric columns.
        road_segments (GeoDataFrame): Line geometries of road segments.
        numeric_columns (list): List of numeric column names to aggregate.
        id_column (str): Column to count (default is 'id').
        distance_col (str): Name of the distance column to compute.

    Returns:
        GeoDataFrame: Aggregated data per road segment.
    """
    # Ensure CRS match
    projected_crs = "EPSG:3857"
    road_segments = road_segments.set_crs(4326, allow_override=True).to_crs(projected_crs)
    point_gdf = point_gdf.set_crs(4326, allow_override=True).to_crs(projected_crs)


    point_extent = point_gdf.total_bounds
    LOGGER.debug(point_extent)
    road_segments_clipped = gpd.clip(road_segments, point_extent)
    road_segments_clipped = road_segments_clipped[~road_segments_clipped.is_empty]

    # road_segments = road_segments.reset_index(drop=True)

    # Spatial join to find nearest segment
    joined = gpd.sjoin_nearest(
        point_gdf,
        road_segments_clipped,
        how="left",
        distance_col=distance_col,
    )

    max_distance_threshold = 20
    joined = joined[joined[distance_col] < max_distance_threshold]
    LOGGER.debug(joined.columns)

    # Columns to aggregate
    o_dist = False
    agg_dict = {col: "mean" for col in numeric_columns}
    agg_dict[distance_col] = "mean"
    agg_dict[id_column] = "count"
    agg_dict['boxId'] = 'nunique'
    if 'Overtaking Distance' in joined.columns:
        o_dist = True
        agg_dict['Overtaking Distance'] = ['mean', histo]

    # Group by road segment index
    aggregated = joined.groupby("index_right").agg(agg_dict)

    aggregated.columns = ['_'.join(map(str, col)).strip() for col in aggregated.columns.values]


    # # Rename columns
    # new_columns = {
    #     col: f"Average {col}" for col in numeric_columns
    # }
    # new_columns[distance_col] = "Average Distance to Road"
    # new_columns[id_column] = f"Number of Points"
    # new_columns['boxId'] = "Number of Boxes"
    # if o_dist:
    #     new_columns['Overtaking Distance'] = 'counts'
    #
    new_columns = {
        f"{col}_mean": f"Average {col}" for col in numeric_columns
    }
    new_columns[f"{distance_col}_mean"] = "Average Distance to Road[m]"
    new_columns[f"{id_column}_count"] = "Number of Points"
    new_columns['boxId_nunique'] = "Number of Boxes"

    if o_dist:
        new_columns['Overtaking Distance_mean'] = 'Average Overtaking Distance[cm]'
        new_columns['Overtaking Distance_histo'] = 'Overtaking Distance Counts'
        new_columns['Overtaking Manoeuvre_mean'] = 'Average Overtaking Manoeuvre[%]'
    aggregated = aggregated.rename(columns=new_columns)

    #TODO just use another func at this point?
    if "i_d" in aggregated.columns:
        newer_cols = {}
        newer_cols["R_o_u_g_h_n_e_s_s"] = "Roughness"
        newer_cols["b_o_x_I_d"] = "Number of Boxes"
        newer_cols["i_d"] = "streetid"
        newer_cols["d_i_s_t_a_n_c_e___t_o___r_o_a_d"] = "Distance to Road"
        newer_cols["R_o_u_g_h_n_e_s_s___N_o_r_m_a_l_i_z_e_d"] = "Normalized Roughness"
        aggregated = aggregated.rename(columns=newer_cols)

    # aggregated.columns = ['_'.join(map(str, col)).strip() for col in aggregated.columns.values]

    # Join geometry back in
    result = aggregated.merge(
        road_segments_clipped, left_on="index_right", right_index=True
    )
    result["id"] = result.index

    gdf = gpd.GeoDataFrame(result, geometry="geometry", crs=projected_crs)

    return gdf.to_crs(4326)