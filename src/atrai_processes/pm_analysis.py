import os
import logging
from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor


import pandas as pd
import folium
from folium.plugins import HeatMap
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

from .useful_functs import filter_bike_data_location, replace_outliers_with_nan_by_device
from .html_helper import create_pm25_legend_html, create_pm25_timeframe_legend_html

LOGGER = logging.getLogger(__name__)

METADATA = {
    'version': '0.2.0',
    'id': 'pm_analysis',
    'title': {
        'en': 'pm_analysis',
    },
    'description': {
        'en': 'processes to evaluate pm concentrations'},
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

def get_season(month):
    if month in [3, 4, 5]:
        return 'Spring'
    elif month in [6, 7, 8]:
        return 'Summer'
    elif month in [9, 10, 11]:
        return 'Autumn'
    else:
        return 'Winter'
    
def filter_season_and_time(filtered_data, start_time, end_time, selected_season, time_filter=True, season_filter=True):
    
    if time_filter:
        filtered_data = filtered_data[(filtered_data['time_of_day'] >= start_time) & (filtered_data['time_of_day'] <= end_time)]
    
    if season_filter:
        filtered_data = filtered_data[filtered_data['season'] == selected_season]
    
    return filtered_data[['lat', 'lng', 'Finedust PM2.5']].dropna(subset=['lat', 'lng', 'Finedust PM2.5'])

class PMAnalysis(AtraiProcessor):
    def __init__(self, processor_def):

        super().__init__(processor_def, METADATA)
        # self.secret_token = os.environ.get('INT_API_TOKEN', 'token')
        # self.data_base_dir = '/pygeoapi/data'
        # self.html_out = '/pygeoapi/data/html'
        self.png_out = '/pygeoapi/data/png'


    def execute(self, data):
        mimetype =  'application/json'

        self.check_request_params(data)
        atrai_bike_data = self.load_data()
        atrai_bike_data['lng'] = atrai_bike_data['geometry'].x
        atrai_bike_data['lat'] = atrai_bike_data['geometry'].y

        # self.boxid = data.get('id')
        # self.token = data.get('token')

        # if self.boxid is None:
        #     raise ProcessorExecuteError('Cannot process without a id')
        if self.token is None:
            raise ProcessorExecuteError('Identify yourself with valid token!')

        if self.token != self.secret_token:
            LOGGER.error("WRONG INTERNAL API TOKEN")
            raise ProcessorExecuteError('ACCESS DENIED wrong token')

        # if self.boxid not in os.listdir(self.data_base_dir):
        #     LOGGER.info(f'download data for {self.boxid}')
        #     OSM = OpenSenseMap.OpenSenseMap()
        #     OSM.add_box(self.boxid)
        #     OSM.save_OSM()

        #script
        # atrai_bike_data = pd.read_csv('/pygeoapi/combined_data.csv')
        device_counts = atrai_bike_data.groupby('boxId').size()
        valid_device_ids = device_counts[device_counts >= 10].index
        atrai_bike_data = atrai_bike_data[atrai_bike_data['boxId'].isin(valid_device_ids)]
        filtered_data_MS = filter_bike_data_location(atrai_bike_data)

        filtered_data_MS = filtered_data_MS[['createdAt', 'Rel. Humidity', 'Finedust PM1', 'Finedust PM2.5', 'Finedust PM4', 'Finedust PM10', 'geometry', 'boxId', 'lng', 'lat']]
        filtered_data_MS = filtered_data_MS[(filtered_data_MS['Rel. Humidity'] <= 75) & (filtered_data_MS['Rel. Humidity'].notna())]
        
        pm_columns = ['Finedust PM1', 'Finedust PM2.5', 'Finedust PM4', 'Finedust PM10']
        PM_no_outliers = filtered_data_MS.copy(deep=True)

        for column in pm_columns:
            PM_no_outliers = replace_outliers_with_nan_by_device(PM_no_outliers, column)
        for column in pm_columns:
            PM_no_outliers[column] = PM_no_outliers[column].astype('float64')


        plt.figure(figsize=(12, 10))

        plt.subplot(2, 2, 1) 
        sns.boxplot(data=filtered_data_MS, x='boxId', y='Finedust PM1')
        plt.title('PM1 Concentration by Device ID, Münster')
        plt.xlabel('Devices')
        plt.ylabel('PM1 (µg/m³)')
        plt.xticks([])
        plt.ylim(0,80)

        plt.subplot(2, 2, 2)
        sns.boxplot(data=filtered_data_MS, x='boxId', y='Finedust PM2.5')
        plt.title('PM2.5 Concentration by Device ID, Münster')
        plt.xlabel('Devices')
        plt.ylabel('PM2.5(µg/m³)')
        plt.xticks([])
        plt.ylim(0,80)

        plt.subplot(2, 2, 3)
        sns.boxplot(data=filtered_data_MS, x='boxId', y='Finedust PM4')
        plt.title('PM4 Concentration by Device ID, Münster')
        plt.xlabel('Devices')
        plt.ylabel('PM4 (µg/m³)')
        plt.xticks([])
        plt.ylim(0,80)

        plt.subplot(2, 2, 4)
        sns.boxplot(data=filtered_data_MS, x='boxId', y='Finedust PM10')
        plt.title('PM10 Concentration by Device ID, Münster')
        plt.xlabel('Devices')
        plt.ylabel('PM10 (µg/m³)')
        plt.xticks([])
        plt.ylim(0,80)

        plt.tight_layout()
        pm_boxplots = plt.gcf()

        os.makedirs(self.png_out, exist_ok=True)
        pm_boxplots.savefig(os.path.join(self.png_out, "pm_boxplots.png"))

        muenster_data_diurnal = filtered_data_MS.copy()

        muenster_data_diurnal['createdAt'] = pd.to_datetime(muenster_data_diurnal['createdAt'])
        muenster_data_diurnal['time_30min'] = muenster_data_diurnal['createdAt'].dt.strftime('%H:%M')
        muenster_data_diurnal['time_30min'] = pd.to_datetime(muenster_data_diurnal['time_30min'], format='%H:%M')
        muenster_data_diurnal['time_30min'] = muenster_data_diurnal['time_30min'].dt.round('30min')
        diurnal_cycle = muenster_data_diurnal.groupby('time_30min')['Finedust PM2.5'].mean()
        start_time_day = pd.to_datetime('00:00', format='%H:%M')
        end_time_day = pd.to_datetime('23:30', format='%H:%M')
        date_range = pd.date_range(start=start_time_day, end=end_time_day, freq='30min')
        diurnal_cycle_full = diurnal_cycle.reindex(date_range, fill_value=None)

        plt.figure(figsize=(10, 6))
        plt.plot(diurnal_cycle_full.index, diurnal_cycle_full.values, marker='o', linestyle='-', color='skyblue')
        plt.title("Diurnal Cycle of PM2.5 Concentrations (µg/m³), Münster")
        plt.xlabel("Time of Day")
        plt.ylabel("Average PM2.5 Concentration(µg/m³)")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(ticks=diurnal_cycle_full.index, labels=diurnal_cycle_full.index.strftime('%H:%M'), rotation=45)
        plt.tight_layout()
        pm_diurnal_cycle = plt.gcf()	

        pm_diurnal_cycle.savefig(os.path.join(self.png_out, "pm_diurnal_cycle.png"))

        muenster_data_monthly = filtered_data_MS.copy()
        muenster_data_monthly['createdAt'] = pd.to_datetime(muenster_data_monthly['createdAt'])
        muenster_data_monthly['month'] = muenster_data_monthly['createdAt'].dt.to_period('M')
        muenster_monthly_averages = muenster_data_monthly.groupby('month')['Finedust PM2.5'].mean()
        muenster_monthly_averages.index = muenster_monthly_averages.index.to_timestamp()

        plt.figure(figsize=(10, 6))
        plt.plot(muenster_monthly_averages.index, muenster_monthly_averages.values, marker='o', linestyle='-', color='skyblue')
        plt.title("Monthly Average PM2.5 Concentrations (µg/m³), Münster")
        plt.xlabel("Month")
        plt.ylabel("Average PM2.5 Concentration (µg/m³)")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        pm_monthly_avg = plt.gcf()	

        pm_monthly_avg.savefig(os.path.join(self.png_out, "pm_monthly_avg.png"))

        pm25_data_heatmap = PM_no_outliers[['lat', 'lng', 'Finedust PM2.5']]
        pm25_data_heatmap = pm25_data_heatmap.dropna(subset=['lat', 'lng', 'Finedust PM2.5'])
        m_PM25 = folium.Map(location=[51.9607, 7.6261], zoom_start=12)
        heat_data_25 = pm25_data_heatmap[['lat', 'lng', 'Finedust PM2.5']].values
        HeatMap(heat_data_25, radius = 10, blur = 10).add_to(m_PM25) #adjust radius and blur for change in visualization

        legend_html_pm25 = create_pm25_legend_html(pm25_data_heatmap)
        m_PM25.get_root().html.add_child(folium.Element(legend_html_pm25))

        os.makedirs(self.html_out, exist_ok=True)
        m_PM25.save(os.path.join(self.html_out, "PM_25_heatmap.html"))

        seasonal_time_data = PM_no_outliers.copy(deep=True)
        seasonal_time_data['createdAt'] = pd.to_datetime(seasonal_time_data['createdAt'])
        seasonal_time_data['month'] = seasonal_time_data['createdAt'].dt.month
        seasonal_time_data['time_of_day'] = seasonal_time_data['createdAt'].dt.time
        seasonal_time_data['season'] = seasonal_time_data['month'].apply(get_season)
        start_time = pd.to_datetime("16:00", format="%H:%M").time() #change for different time of day
        end_time = pd.to_datetime("18:00", format="%H:%M").time() #change for different time of day
        selected_season = 'Autumn' #change for different season
        data_timeframe = filter_season_and_time(seasonal_time_data, start_time, end_time, selected_season)

        m_PM25_timeframe = folium.Map(location=[51.9607, 7.6261], zoom_start=12)
        heat_data_timeframe = data_timeframe[['lat', 'lng', 'Finedust PM2.5']].values
        HeatMap(heat_data_timeframe, radius=10, blur=10).add_to(m_PM25_timeframe)

        timeframe_title = f"PM2.5 Concentration (µg/m³)<br>{selected_season} {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')}"
        legend_html_timeframe = create_pm25_timeframe_legend_html(data_timeframe, timeframe_title)
        m_PM25_timeframe.get_root().html.add_child(folium.Element(legend_html_timeframe))
        
        m_PM25_timeframe.save(os.path.join(self.html_out, "PM_25_timeframe_heatmap.html"))

        outputs = {
            'id': 'pm_analysis',
            'status': f"""created files at '{os.path.join(self.png_out, "pm_boxplots.png")}, '{os.path.join(self.html_out, "PM_25_heatmap.html")} and {os.path.join(self.html_out, "PM_25_timeframe_heatmap.html")}'"""
        }

        return mimetype, outputs

    def __repr__(self):
        return f'<PMAnalysis> {self.name}'