import os
import logging
from .process_base import BaseProcessor, ProcessorExecuteError

import pandas as pd
import folium
from folium.plugins import HeatMap

from .useful_functs import filter_bike_data_location
from .html_helper import create_temperature_legend_html

LOGGER = logging.getLogger(__name__)

METADATA = {
    'version': '0.2.0',
    'id': 'Temperature',
    'title': {
        'en': 'Temperature',
    },
    'description': {
        'en': 'Visualization of temperature data'},
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

# Function to extract season from CreatedAt column
def get_season(month):
    if month in [3, 4, 5]: 
        return 'Spring'
    elif month in [6, 7, 8]: 
        return 'Summer'
    elif month in [9, 10, 11]:
        return 'Autumn'
    else:  
        return 'Winter'

#Function to generate heatmap
def create_heatmap(data, title, file_name="Heatmap.html"):
    heatmap_data_temp = data[['lat', 'lng', 'Temperature']].dropna(subset=['Temperature', 'lat', 'lng'])
    heat_data_temp = heatmap_data_temp[['lat', 'lng', 'Temperature']].values
    m_temp = folium.Map(location=[51.9607, 7.6261], zoom_start=12)
    HeatMap(heat_data_temp, radius=10, blur=10).add_to(m_temp)
    legend_html = create_temperature_legend_html(data)
    m_temp.get_root().html.add_child(folium.Element(legend_html))
    m_temp.save(file_name)

    return m_temp

def reset_first_time_diff(group):
    group.iloc[0, group.columns.get_loc('time_diff')] = 0
    
    return group


class Temperature(BaseProcessor):
    def __init__(self, processor_def):

        super().__init__(processor_def, METADATA)
        self.secret_token = os.environ.get('INT_API_TOKEN', 'token')
        self.data_base_dir = '/pygeoapi/data'
        self.html_out = '/pygeoapi/data/html'


    def execute(self, data):
        mimetype =  'application/json'

        self.boxid = data.get('id')
        self.token = data.get('token')

        if self.boxid is None:
            raise ProcessorExecuteError('Cannot process without a id')
        if self.token is None:
            raise ProcessorExecuteError('Identify yourself with valid token!')

        if self.token != self.secret_token:
            LOGGER.error("WRONG INTERNAL API TOKEN")
            raise ProcessorExecuteError('ACCESS DENIED wrong token')

        #if self.boxid not in os.listdir(self.data_base_dir):
        #    LOGGER.info(f'download data for {self.boxid}')
        #    OSM = OpenSenseMap.OpenSenseMap()
        #    OSM.add_box(self.boxid)
        #    OSM.save_OSM()

        #script
        initial_data = pd.read_csv('/pygeoapi/combined_data.csv')
        device_counts = initial_data.groupby('device_id').size()
        valid_device_ids = device_counts[device_counts >= 10].index
        atrai_bike_data = initial_data[initial_data['device_id'].isin(valid_device_ids)]

        atrai_bike_data['createdAt'] = pd.to_datetime(atrai_bike_data['createdAt'])
        filtered_data_MS = filter_bike_data_location(atrai_bike_data)

        filtered_data_MS['Season'] = filtered_data_MS['createdAt'].dt.month.apply(get_season)
        filtered_data_MS = filtered_data_MS.sort_values(by=['device_id', 'createdAt'])
        filtered_data_MS['time_diff'] = filtered_data_MS.groupby('device_id')['createdAt'].diff().dt.total_seconds()
        filtered_data_MS['ride_id'] = filtered_data_MS.groupby('device_id')['time_diff'].transform(lambda x: (x > 600).cumsum())
        filtered_data_MS = filtered_data_MS.groupby(['device_id', 'ride_id']).apply(reset_first_time_diff)
        filtered_data_MS = filtered_data_MS.reset_index(drop=True)
        filtered_data_MS['ride_time'] = filtered_data_MS.groupby(['device_id', 'ride_id'])['time_diff'].cumsum()
        filtered_data_MS['total_ride_duration'] = filtered_data_MS.groupby(['device_id', 'ride_id'])['ride_time'].transform('max')
        filtered_data_MS = filtered_data_MS[filtered_data_MS['total_ride_duration'] >= 60]
        filtered_time_data = filtered_data_MS[
            (filtered_data_MS['ride_time'] > 60) &
            (filtered_data_MS['ride_time'] < (filtered_data_MS['total_ride_duration'] - 60))
        ]

        os.makedirs(self.html_out, exist_ok=True)

        html_files = []

        for season in ['Spring', 'Summer', 'Autumn', 'Winter']:
            seasonal_data = filtered_time_data[filtered_time_data['Season'] == season]
            if not seasonal_data.empty:
                file_name = os.path.join(self.html_out, f"{season}_Temperature_Heatmap_MS.html")
                create_heatmap(
                    seasonal_data,
                    title=f"{season} Temperature Heatmap",
                    file_name=file_name
                )
                html_files.append(file_name)


        outputs = {
            'id': 'Temperature',
            'status': f"""created html files at '{', '.join(html_files)}'"""
        }

        return mimetype, outputs

    def __repr__(self):
        return f'<Temperature> {self.name}'