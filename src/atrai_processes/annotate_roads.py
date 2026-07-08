from datetime import timedelta
from functools import partial
import logging
import multiprocessing
import os

import geopandas as gpd
from ast import literal_eval
import movingpandas as mpd
import numpy as np
import pandas as pd
from .process_base import BaseProcessor, ProcessorExecuteError
from shapely.geometry import LineString

from .atrai_processor import AtraiProcessor
from .snapping import snap_to_roads

LOGGER = logging.getLogger(__name__)

METADATA = {
    "version": "0.2.0",
    "id": "annotate_roads",
    "title": {
        "en": "annotate_roads",
    },
    "description": {"en": "annotates sensor data to road segments by snapping individual tours to the road segments"},
    "jobControlOptions": ["sync-execute", "async-execute"],
    "keywords": ["process"],
    "links": [
        {
            "type": "text/html",
            "rel": "about",
            "title": "information",
            "href": "https://example.org/process",
            "hreflang": "en-US",
        }
    ],
    "inputs": {
        "campaign": {
            "title": "campaign",
            "description": "campaign name",
            "schema": {"type": "string"},
        },
        "col_create": {
            "title": "col_create",
            "description": "create collection yes/ no",
            "schema": {"type": "string"},
        },
        "token": {
            "title": "secret token",
            "description": "identify yourself",
            "schema": {"type": "string"},
        },
    },
    "outputs": {
        "id": {
            "title": "ID",
            "description": "The ID of the process execution",
            "schema": {"type": "string"},
        },
        "status": {
            "title": "status",
            "description": "describes process",
            "schema": {"type": "string"},
        },
    },
    "example": {"inputs": {"campaign": "münster", "col_create": "true", "token": "ABC123XYZ666"}},
}

def calculate_flow_metrics(df):
    df = df.copy()
    mask = df['Speed'] >= 0
    limit = df.loc[mask, 'Speed'].quantile(0.999)
    df['Normalized_Speed'] = np.nan
    df.loc[mask, 'Normalized_Speed'] = (df.loc[mask, 'Speed'] / limit).clip(upper=1)
    df['traffic_flow'] = np.nan
    score = df.loc[mask, 'Normalized_Speed'] * (1 - (df.loc[mask, 'Standing'] ** 2))
    df.loc[mask, 'traffic_flow'] = score

    return df

def calculate_road_bumpiness(df):
    df = df.copy()
    weights = {'Asphalt': 1, 'Paving': 2, 'Compacted': 3, 'Sett': 4}
    scores = sum(df[f'Surface {surface_type}'] * weight for surface_type, weight in weights.items())
    df['Roughness'] = scores

    return df

def calculate_danger_zones(df):
    df = df.copy()
    max_dist = 400
    mask = df['Overtaking Manoeuvre'] >= 0.5
    df['Normalized Distance'] = np.nan
    norm_vals = 1 - (df.loc[mask, 'Overtaking Distance'] / max_dist)
    df.loc[mask, 'Normalized Distance'] = norm_vals.clip(lower=0, upper=1)
    weights_traffic = {'Normalized Distance': 0.7, 'Overtaking Manoeuvre': 0.3}
    df['danger_zone_traffic'] = np.nan
    score = sum(df.loc[mask, prob] * weight for prob, weight in weights_traffic.items())
    df.loc[mask, 'danger_zone_traffic'] = score

    return df

def histo(data):
    clean_data = data.dropna()
    bins = [0, 0.5, 1, 1.5, 2, np.inf]
    counts, bin_edges = np.histogram(clean_data, bins=bins)
    string = ", ".join(str(x) for x in counts)
    return string

def filter_undirected_duplicates(gdf):
    def normalize_geom(geom):
        wkt_a = geom.wkt
        wkt_b = LineString(list(geom.coords)[::-1]).wkt
        return wkt_a if wkt_a < wkt_b else wkt_b

    out_gdf = gdf.copy()
    out_gdf['__uid'] = out_gdf['geometry'].apply(normalize_geom)
    out_gdf = out_gdf.drop_duplicates(subset=['__uid'])
    return out_gdf.drop(columns=['__uid'])


class AnnotateRoads(AtraiProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, METADATA)

    def execute(self, data):
        # check params
        self.check_request_params(data)
        # load data
        atrai_bike_data = self.load_bike_data().to_crs("EPSG:3857").dropna(subset=['geometry'])
        road_segments = filter_undirected_duplicates(self.load_road_data().to_crs("EPSG:3857").dropna(subset=['geometry']))

        # process data
        #create tour trajectories
        tc = mpd.TrajectoryCollection(atrai_bike_data,'boxId', t='createdAt')
        LOGGER.info(tc)
        # tc.add_direction()
        split = mpd.ObservationGapSplitter(tc).split(gap=timedelta(minutes=15))

        #snap each tour to roads using multiprocessing
        LOGGER.info("snapping")

        # func = partial(worker, road_network=road_segments)
        # ctx = multiprocessing.get_context('spawn')
        # with ctx.Pool(processes=os.cpu_count()) as pool:
        #     results = pool.map(func, split.trajectories)

        results = []
        for i, traj in enumerate(split.trajectories):
            LOGGER.info(f"processing {i} / {len(split.trajectories)} tours")
            results.append(snap_to_roads(road_df=road_segments, traject_df=traj.df))

        LOGGER.info("snapping done")

        res = [x for x in results if x is not None]
        all_snapped = pd.concat(res)

        avg_speeds = all_snapped[all_snapped['Speed'] >= 0].groupby('way_id')['Speed'].mean() * 3.6
        avg_speeds.name = 'avg_speed'
        avg_dist = all_snapped[all_snapped['Overtaking Manoeuvre'] > 0.5].groupby('way_id')['Overtaking Distance'].mean()
        avg_dist.name = 'avg_overtake_dist'
        total_tours = all_snapped.groupby('way_id')['boxId'].nunique()
        total_tours.name = 'total_unique_tours'

        all_snapped = calculate_flow_metrics(all_snapped)
        all_snapped = calculate_road_bumpiness(all_snapped)
        all_snapped = calculate_danger_zones(all_snapped)

        avg_traffic_flow = all_snapped.groupby('way_id')['traffic_flow'].mean()
        avg_traffic_flow.name = 'avg_traffic_flow'
        road_roughness = all_snapped.groupby('way_id')['Roughness'].mean()
        road_roughness.name = 'road_roughness'
        danger_zones = all_snapped.groupby('way_id')['danger_zone_traffic'].mean()
        danger_zones.name = 'danger_zone_traffic'

        mask_overtake = all_snapped['Overtaking Manoeuvre'] >= 0.5
        overtaking_histo = all_snapped[mask_overtake].groupby('way_id')['Overtaking Distance'].apply(histo)
        overtaking_histo.name = 'overtaking_histogram'

        road_df_with_metrics = road_segments.join([avg_speeds,
                                             avg_dist,
                                             total_tours,
                                             avg_traffic_flow,
                                             road_roughness,
                                             danger_zones,
                                             overtaking_histo
                                             ], how='left')

        road_df_with_metrics = road_df_with_metrics.to_crs("EPSG:4326")

        # assign result to self.data
        self.data = road_df_with_metrics
        self.create_collection_entries('annotate_roads')

        # write result
        road_df_with_metrics['id'] = range(1, len(road_df_with_metrics) + 1)
        road_df_with_metrics.to_postgis(
            self.title,
            self.db_engine,
            if_exists="replace",
            index=False
        )

        # update_config
        if self.col_create:
            self.update_config()

        outputs = {
            "id": "annotat_roads",
            "status": f"Processed {len(road_df_with_metrics)} road segments with bike data"
        }
        return self.mimetype, outputs

    def __repr__(self):
        return f"<AnnotateRoads> {self.name}"