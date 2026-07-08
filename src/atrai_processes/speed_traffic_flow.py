import os
import logging
from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor


import pandas as pd
import folium
import geopandas as gpd
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
from sklearn.neighbors import BallTree
from sqlalchemy import create_engine

from .html_helper import create_speed_legend_html, create_traffic_flow_legend_html
from .useful_functs import filter_bike_data_location, nearest_neighbor_search

LOGGER = logging.getLogger(__name__)

METADATA = {
    'version': '0.2.0',
    'id': 'speed_traffic_flow',
    'title': {
        'en': 'speed_traffic_flow',
    },
    'description': {
        'en': 'evaluates speed and traffic flow'},
    'jobControlOptions': ['sync-execute', 'async-execute'],
    'keywords': ['process'],
    'links': [{
        'type': 'text/html',
        'rel': 'about',
        'title': 'information',
        'href': 'https://example.org/process',
        'hreflang': 'en-US'
    }],
    'inputs': {
        'id': {
            'title': 'boxid',
            'description': 'boxid to get the data from',
            'schema': {
                'type': 'string'
            }
        },
        'token': {
            'title': 'secret token',
            'description': 'identify yourself',
            'schema': {
                'type': 'string'
            }
        }
    },
    'outputs': {
        'id': {
            'title': 'ID',
            'description': 'The ID of the process execution',
            'schema': {
                'type': 'string'
            }
        },
        'status': {
            'title': 'status',
            'description': 'describes process',
            'schema': {
                'type': 'string'
            }
        }
    },
    'example': {
        "inputs": {
            "ids": "ABCDEF123456",
            "token": "ABC123XYZ666"
        }
    }
}

def filter_start_end(group):
    standing_threshold = 0.9
    group = group.copy()

    start_indices_to_drop = []
    for idx, row in group.iterrows():
        if row['Standing'] > standing_threshold:
            start_indices_to_drop.append(idx)
        else:
            break

    end_indices_to_drop = []
    for idx, row in group[::-1].iterrows():
        if row['Standing'] > standing_threshold:
            end_indices_to_drop.append(idx)
        else:
            break

    group = group.drop(index=start_indices_to_drop + end_indices_to_drop)

    return group

class SpeedTrafficFlow(AtraiProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, METADATA)


    def execute(self, data):
        #
        # SPEED MAP WF
        #
        self.check_request_params(data)
        atrai_bike_data = self.load_bike_data()
        edges_filtered = self.load_road_data()
        atrai_bike_data['lng'] = atrai_bike_data['geometry'].x
        atrai_bike_data['lat'] = atrai_bike_data['geometry'].y

        device_counts = atrai_bike_data.groupby('boxId').size()
        valid_device_ids = device_counts[device_counts >= 10].index
        atrai_bike_data = atrai_bike_data[atrai_bike_data['boxId'].isin(valid_device_ids)]

        atrai_bike_data = atrai_bike_data[['createdAt', 'Speed', 'lat', 'lng', 'boxId', 'Standing', 'geometry']]
        atrai_bike_data['createdAt'] = pd.to_datetime(atrai_bike_data['createdAt'])
        atrai_bike_data = atrai_bike_data[atrai_bike_data['Speed'] >= 0]
        percentile_999 = atrai_bike_data['Speed'].quantile(0.999)
        atrai_bike_data['Normalized_Speed'] = (atrai_bike_data['Speed'] / percentile_999).clip(upper=1)

        edges_filtered = edges_filtered.reset_index(drop=True)
        atrai_bike_data = nearest_neighbor_search(atrai_bike_data, edges_filtered)

        segment_data = atrai_bike_data.groupby('road_segment').agg(
            avg_speed=('Normalized_Speed', 'mean'),
            points_in_segment=('road_segment', 'size')
        ).reset_index()

        segment_data = segment_data.merge(
            edges_filtered,
            left_on='road_segment',
            right_index=True
        )

        segment_data = gpd.GeoDataFrame(
            segment_data,
            geometry='geometry',
            crs=edges_filtered.crs
        )

        segment_data['avg_speed[km/h]'] = (segment_data['avg_speed'] * percentile_999) * 3.6
        segment_data.reset_index(inplace=True)
        segment_data.rename(columns={'index': 'id'}, inplace=True)
        segment_data.drop(columns='avg_speed', inplace=True)

        self.data = segment_data
        self.create_collection_entries('speed_map')

        segment_data.to_postgis(
            self.title,
            self.db_engine,
            if_exists="replace",
            index=False
        )
        # update_config
        if self.col_create:
            self.update_config()


        #
        # TRAFFIC FLOW WF
        #
        atrai_bike_data = self.load_bike_data()
        edges_filtered = self.load_road_data()
        atrai_bike_data['lng'] = atrai_bike_data['geometry'].x
        atrai_bike_data['lat'] = atrai_bike_data['geometry'].y

        atrai_bike_data = atrai_bike_data[['createdAt', 'Speed', 'lat', 'lng', 'boxId', 'Standing', 'geometry']]
        atrai_bike_data['createdAt'] = pd.to_datetime(atrai_bike_data['createdAt'])
        atrai_bike_data = atrai_bike_data.dropna(subset=['Standing'])
        atrai_bike_data = atrai_bike_data.sort_values(by='createdAt')
        atrai_bike_data['time_diff'] = atrai_bike_data.groupby('boxId')['createdAt'].diff().dt.total_seconds() / 60
        atrai_bike_data['new_ride'] = atrai_bike_data['time_diff'] > 10
        atrai_bike_data['ride_id'] = atrai_bike_data.groupby('boxId')['new_ride'].cumsum() + 1

        atrai_bike_data = atrai_bike_data.groupby('ride_id').apply(lambda group: filter_start_end(group)).reset_index(drop=True)
        
        atrai_bike_data = atrai_bike_data[atrai_bike_data['Speed'] >= 0]
        percentile_999_tf = atrai_bike_data['Speed'].quantile(0.999)
        atrai_bike_data['Normalized_Speed'] = (atrai_bike_data['Speed'] / percentile_999_tf).clip(upper=1)
        atrai_bike_data['traffic_flow'] = (atrai_bike_data['Normalized_Speed'] * (1 - (atrai_bike_data['Standing'] ** 2)))

        edges_filtered = edges_filtered.reset_index(drop=True)
        atrai_bike_data = nearest_neighbor_search(atrai_bike_data, edges_filtered)

        segment_data_tf = atrai_bike_data.groupby('road_segment').agg(
            avg_traffic_flow=('traffic_flow', 'mean'),
            points_in_segment=('road_segment', 'size')
        ).reset_index()

        segment_data_tf = segment_data_tf.merge(
            edges_filtered,
            left_on='road_segment',
            right_index=True
        )

        segment_data_tf = gpd.GeoDataFrame(
            segment_data_tf,
            geometry='geometry',
            crs=edges_filtered.crs
        )

        segment_data_tf.reset_index(inplace=True)
        segment_data_tf.rename(columns={'index': 'id'}, inplace=True)

        self.data = segment_data_tf
        self.create_collection_entries('traffic_flow')

        segment_data_tf.to_postgis(
            self.title,
            self.db_engine,
            if_exists="replace",
            index=False
        )
        # update_config
        if self.col_create:
            self.update_config()
        

                
        outputs = {
            'id': 'speed_traffic_flow',
            'status': f"""done"""
        }

        return self.mimetype, outputs

    def __repr__(self):
        return f'<SpeedTrafficFlow> {self.name}'