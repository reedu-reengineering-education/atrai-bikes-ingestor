import numpy as np
from sklearn.neighbors import BallTree

def filter_bike_data_location(atrai_bike_data):
    # Fixed coordinates for filtering
    additional_lat_min, additional_lat_max = 51.954148, 51.954402
    additional_lng_min, additional_lng_max = 7.631794, 7.632041
    lat_min, lat_max = 51.8, 52.1  
    lng_min, lng_max = 7.5, 7.7   

    # Exclude the office building and data outside Münster
    mask_no_office = ~((atrai_bike_data['lat'] >= additional_lat_min) & (atrai_bike_data['lat'] <= additional_lat_max) &
                       (atrai_bike_data['lng'] >= additional_lng_min) & (atrai_bike_data['lng'] <= additional_lng_max))
    atrai_bike_data_no_office = atrai_bike_data[mask_no_office]

    mask_filtered = ((atrai_bike_data_no_office['lat'] >= lat_min) & (atrai_bike_data_no_office['lat'] <= lat_max) &
                     (atrai_bike_data_no_office['lng'] >= lng_min) & (atrai_bike_data_no_office['lng'] <= lng_max))
    filtered_data = atrai_bike_data_no_office[mask_filtered]
    
    return filtered_data

def nearest_neighbor_search(filtered_data, edges_filtered):

    # for spatial operations:
    edges_projected = edges_filtered.to_crs("EPSG:3857")
    centroids = edges_projected.geometry.centroid

    # re(projection) for visualization
    centroids_4326 = centroids.to_crs("EPSG:4326")
    
    # BallTree for nearest-neighbor search
    road_coords = np.deg2rad(np.array([
        centroids_4326.x.values,
        centroids_4326.y.values
    ]).T)
    tree = BallTree(road_coords, metric='haversine')

    filtered_data = filtered_data.dropna(subset=['lng', 'lat'])

    bike_coords = np.deg2rad(filtered_data[['lng', 'lat']].values)
    _, indices = tree.query(bike_coords, k=1)
    filtered_data['road_segment'] = indices.flatten()
    
    return filtered_data

def replace_outliers_with_nan_by_device(PM_data_no_outliers, column):
    def calculate_and_replace_outliers(group):
        Q1 = group[column].quantile(0.25)
        Q3 = group[column].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        group[column] = group[column].apply(lambda x: x if lower_bound <= x <= upper_bound else np.nan)
        return group

    PM_data_no_outliers = PM_data_no_outliers.groupby('boxId', group_keys=False).apply(calculate_and_replace_outliers)
    
    return PM_data_no_outliers