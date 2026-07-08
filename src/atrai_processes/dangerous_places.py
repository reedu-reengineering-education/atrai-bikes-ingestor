import logging
from .atrai_processor import AtraiProcessor

from .useful_functs import  replace_outliers_with_nan_by_device

LOGGER = logging.getLogger(__name__)

METADATA = {
    'version': '0.2.0',
    'id': 'dangerous_places',
    'title': {
        'en': 'dangerous_places',
    },
    'description': {
        'en': 'evaluates danger of certain zones'},
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

class DangerousPlaces(AtraiProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, METADATA)


    def execute(self, data):
        self.check_request_params(data)
        atrai_bike_data = self.load_bike_data()
        atrai_bike_data['lng'] = atrai_bike_data['geometry'].x
        atrai_bike_data['lat'] = atrai_bike_data['geometry'].y

        device_counts = atrai_bike_data.groupby('boxId').size()
        valid_device_ids = device_counts[device_counts >= 10].index
        atrai_bike_data = atrai_bike_data[atrai_bike_data['boxId'].isin(valid_device_ids)]

        danger_data = atrai_bike_data[['createdAt', 'Overtaking Manoeuvre', 'Overtaking Distance', 'Standing', 'Rel. Humidity', 'Finedust PM1', 'Finedust PM2.5', 'Finedust PM4', 'Finedust PM10', 'geometry', 'boxId', 'lng', 'lat']]

        #
        # OVERTAKING DANGER WF
        #

        danger_zones = danger_data.copy()
        max_distance = 400
        danger_zones['Normalized Distance'] = 1 - (danger_zones['Overtaking Distance'] / max_distance)
        danger_zones['Normalized Distance'] = danger_zones['Normalized Distance'].clip(lower=0, upper=1)
        danger_zones = danger_zones[danger_zones['Overtaking Manoeuvre'] > 0.05] 
        alpha = 0.3  # Weight for Overtaking Manoeuvre
        beta = 0.7  # Weight for Overtaking Distance
        danger_zones['Risk Index Overtaking'] = (alpha * danger_zones['Overtaking Manoeuvre'] +
                                                beta * danger_zones['Normalized Distance'])

        #m_danger_zones = folium.Map(location=[51.9607, 7.6261], zoom_start=12)
        heatmap_data_dz = danger_zones[['lat', 'lng', 'Risk Index Overtaking', 'geometry']].dropna()
        heatmap_data_dz.reset_index(inplace=True)
        heatmap_data_dz.rename(columns={'index': 'id'}, inplace=True)

        # assign result to self.data
        self.data = heatmap_data_dz
        self.create_collection_entries('danger_zones')

        heatmap_data_dz.to_postgis(
            self.title,
            self.db_engine,
            if_exists="replace",
            index=False
        )
        # update_config
        if self.col_create:
            self.update_config()

        
        #
        # PM DANGER WF
        #

        danger_zones_PM = danger_data.copy()
        danger_zones_PM = danger_zones_PM[(danger_zones_PM['Rel. Humidity'] <= 75) & (danger_zones_PM['Rel. Humidity'].notna())]
        pm_columns = ['Finedust PM1', 'Finedust PM2.5', 'Finedust PM4', 'Finedust PM10']
        for column in pm_columns:
            danger_zones_PM = replace_outliers_with_nan_by_device(danger_zones_PM, column)
        for column in pm_columns:
            danger_zones_PM[column] = danger_zones_PM[column].astype('float64')

        danger_zones_PM['Normalized Distance'] = 1 - (danger_zones_PM['Overtaking Distance'] / max_distance)
        danger_zones_PM['Normalized Distance'] = danger_zones_PM['Normalized Distance'].clip(lower=0, upper=1)
        pm_columns = ['Finedust PM1', 'Finedust PM2.5', 'Finedust PM4', 'Finedust PM10']
        for column in pm_columns:
            max_value = danger_zones_PM[column].max()
            normalized_column = f'Normalized {column.split()[-1]}'
            danger_zones_PM[normalized_column] = danger_zones_PM[column] / max_value

        a = 0.15  # Weight for Overtaking Manoeuvre
        b = 0.35  # Weight for Overtaking Distance
        c = 0.2  # Weight for PM1
        d = 0.15  # Weight for PM2.5
        e = 0.1  # Weight for PM4
        f = 0.05  # Weight for PM10

        danger_zones_PM['Risk Index'] = (
        a * danger_zones_PM['Overtaking Manoeuvre'] +
        b * danger_zones_PM['Normalized Distance'] +
        c * danger_zones_PM['Normalized PM1'] +
        d * danger_zones_PM['Normalized PM2.5'] +
        e * danger_zones_PM['Normalized PM4'] +
        f * danger_zones_PM['Normalized PM10'])


        heatmap_data_danger_zones_PM = danger_zones_PM[['lat', 'lng', 'Risk Index', 'geometry']].dropna()
        heatmap_data_danger_zones_PM.reset_index(inplace=True)
        heatmap_data_danger_zones_PM.rename(columns={'index': 'id'}, inplace=True)


        # assign result to self.data
        self.data = heatmap_data_danger_zones_PM
        self.create_collection_entries('danger_zones_PM')

        heatmap_data_danger_zones_PM.to_postgis(
            self.title,
            self.db_engine,
            if_exists="replace",
            index=True
        )
        # update_config
        if self.col_create:
            self.update_config()

        outputs = {
            'id': 'dangerous_places',
            'status': f"""done"""
        }

        return self.mimetype, outputs

    def __repr__(self):
        return f'<DangerousPlaces> {self.name}'