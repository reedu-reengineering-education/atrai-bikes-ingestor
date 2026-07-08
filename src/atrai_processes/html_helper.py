import matplotlib.colors as mcolors
import numpy as np

legend_html_bumpy_roads = '''
<div style="position: fixed; bottom: 30px; left: 30px; width: 300px; height: auto;
            background-color: white; z-index:9999; font-size:14px;
            border:2px solid grey; padding: 10px; text-align: center;">
    <b>Road Roughness Index (RRI)</b><br>

    <!-- Small color boxes above each range -->
    <div style="display: flex; justify-content: space-between; margin: 5px auto; width: 250px;">
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="width: 20px; height: 20px; background: green;"></div>
            <span style="margin-top: 5px;">0-20</span>
        </div>
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="width: 20px; height: 20px; background: lightgreen;"></div>
            <span style="margin-top: 5px;">21-40</span>
        </div>
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="width: 20px; height: 20px; background: yellow;"></div>
            <span style="margin-top: 5px;">41-60</span>
        </div>
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="width: 20px; height: 20px; background: orange;"></div>
            <span style="margin-top: 5px;">61-80</span>
        </div>
        <div style="display: flex; flex-direction: column; align-items: center;">
            <div style="width: 20px; height: 20px; background: red;"></div>
            <span style="margin-top: 5px;">81-100</span>
        </div>
    </div>

    <p style="margin-top: 10px; font-size: 12px; text-align: center;">
        RRI based on surface textures<br>
        calculated by senseBox:bike
    </p>
</div>
'''

def create_speed_legend_html(segment_data, cmap):
    colors = [mcolors.to_hex(cmap(v)) for v in np.linspace(0, 1, 256)]
    min_speed = segment_data['avg_speed_unnorm_kmh'].min()
    max_speed = segment_data['avg_speed_unnorm_kmh'].max()
    tick_values = np.linspace(min_speed, max_speed, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_speed) / (max_speed - min_speed)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid white; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_speed) / (max_speed - min_speed)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    speed_legend_html = f"""
        <div style="position: fixed; 
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: white;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: white;">
                <strong>Average Speed (km/h)</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: white;">
                {tick_labels_html}
            </div>
        </div>
    """
    return speed_legend_html

def create_traffic_flow_legend_html(segment_data, cmap):
    colors = [mcolors.to_hex(cmap(v)) for v in np.linspace(0, 1, 256)]
    min_traffic_flow = segment_data['avg_traffic_flow'].min()
    max_traffic_flow = segment_data['avg_traffic_flow'].max()

    tick_values = np.linspace(min_traffic_flow, max_traffic_flow, 5)  
    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_traffic_flow) / (max_traffic_flow - min_traffic_flow)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid white; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    
    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_traffic_flow) / (max_traffic_flow - min_traffic_flow)) * 100 
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    traffic_flow_legend_html = f"""
        <div style="position: fixed; 
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: white;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: white;">
                <strong>Average Traffic Flow</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: white;">
                {tick_labels_html}
            </div>
        </div>
    """
    return traffic_flow_legend_html

def create_distances_legend_html(segment_data, cmap):
    colors = [mcolors.to_hex(cmap(v)) for v in np.linspace(0, 1, 256)]
    min_distance = 0
    max_distance = segment_data['avg_distance_unnorm'].max()
    tick_values = np.linspace(min_distance, max_distance, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_distance) / (max_distance - min_distance)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid white; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_distance) / (max_distance - min_distance)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    distances_legend_html = f"""
        <div style="position: fixed; 
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: white;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: white;">
                <strong>Average Distance (cm)</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: white;">
                {tick_labels_html}
            </div>
        </div>
    """
    return distances_legend_html

def create_pm25_legend_html(data):
    colors = ['blue', 'cyan', 'lime', 'yellow', 'red']
    min_pm25 = 0
    max_pm25 = data['Finedust PM2.5'].max()
    tick_values = np.linspace(min_pm25, max_pm25, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_pm25) / (max_pm25 - min_pm25)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid black; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_pm25) / (max_pm25 - min_pm25)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    pm25_legend_html = f"""
        <div style="position: fixed;
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: black;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: black;">
                <strong>PM2.5 Concentration (µg/m³)</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: black;">
                {tick_labels_html}
            </div>
        </div>
    """
    return pm25_legend_html

def create_pm25_timeframe_legend_html(data, title):
    # Define the default gradient colors for Folium heatmaps
    colors = ['blue', 'cyan', 'lime', 'yellow', 'red']
    min_pm25 = 0
    max_pm25 = data['Finedust PM2.5'].max()
    tick_values = np.linspace(min_pm25, max_pm25, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_pm25) / (max_pm25 - min_pm25)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid black; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_pm25) / (max_pm25 - min_pm25)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    pm25_legend_html = f"""
        <div style="position: fixed;
                    top: 50px; right: 50px; width: 300px; height: 70px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: black;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: black;">
                <strong>{title}</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: black;">
                {tick_labels_html}
            </div>
        </div>
    """
    return pm25_legend_html

def create_danger_zones_legend_html(data):
    colors = ['blue', 'cyan', 'lime', 'yellow', 'red']
    min_risk = 0
    max_risk = 1
    tick_values = np.linspace(min_risk, max_risk, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_risk) / (max_risk - min_risk)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid black; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_risk) / (max_risk - min_risk)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    danger_zones_legend_html = f"""
        <div style="position: fixed;
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: black;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: black;">
                <strong>Risk Index for Overtaking Events</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: black;">
                {tick_labels_html}
            </div>
        </div>
    """
    return danger_zones_legend_html

def create_danger_zones_pm_legend_html(data):
    colors = ['blue', 'cyan', 'lime', 'yellow', 'red']
    min_risk_index = 0
    max_risk_index = 1
    tick_values = np.linspace(min_risk_index, max_risk_index, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_risk_index) / (max_risk_index - min_risk_index)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid black; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_risk_index) / (max_risk_index - min_risk_index)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    danger_zones_pm_legend_html = f"""
        <div style="position: fixed;
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: black;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: black;">
                <strong>Risk Index for Overtaking Events and PM Concentrations</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: black;">
                {tick_labels_html}
            </div>
        </div>
    """
    return danger_zones_pm_legend_html

def create_temperature_legend_html(data):
    colors = ['blue', 'cyan', 'lime', 'yellow', 'red']
    min_temp = data['Temperature'].min()
    max_temp = data['Temperature'].max()
    tick_values = np.linspace(min_temp, max_temp, 5)

    tick_marks = []
    for tick in tick_values:
        position = ((tick - min_temp) / (max_temp - min_temp)) * 100
        tick_marks.append(f'<div style="position: absolute; left: {position}%; border-left: 2px solid black; height: 10px; margin-top: -5px; opacity: 0.6;"></div>')

    tick_labels = []
    for tick in tick_values:
        position = ((tick - min_temp) / (max_temp - min_temp)) * 100
        tick_labels.append(f'<span style="position: absolute; left: {position}%; transform: translateX(-50%); font-size: 12px; margin-top: -10px; ">{tick:.1f}</span>')

    tick_marks_html = ''.join(tick_marks)
    tick_labels_html = ''.join(tick_labels)

    temperature_legend_html = f"""
        <div style="position: fixed;
                    top: 50px; right: 50px; width: 300px; height: 50px; 
                    background-color: transparent; opacity: 0.9; padding: 10px; 
                    border: none; z-index: 9999; color: black;">
            <div style="font-size: 18px; font-weight: bold; text-align: center; color: black;">
                <strong>Temperature (°C)</strong>
            </div>
            <div style="height: 20px; width: 100%; background: linear-gradient(to right, {', '.join(colors)});">
            </div>
            <!-- Add tick marks as physical ticks -->
            <div style="position: relative; height: 20px; width: 100%;">
                {tick_marks_html}
            </div>
            <!-- Add tick labels centered below the ticks -->
            <div style="font-size: 12px; display: flex; justify-content: space-between; padding-top: 5px; position: relative; width: 100%; color: black;">
                {tick_labels_html}
            </div>
        </div>
    """
    return temperature_legend_html