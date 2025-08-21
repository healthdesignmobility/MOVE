import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import datetime as dt
import itertools
import json
import pymysql
import geopandas as gpd
import ast
import yaml
import os

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

with open("{}/db_config.yaml".format(script_dir), 'r') as file:
    config = yaml.safe_load(file)
mysql_config = config['mysql']
    
sejong_gdf = gpd.read_file("{}/ODD/sejong/Station.shp".format(script_dir))
daejeon_gdf = gpd.read_file("{}/ODD/daejeon/Station.shp".format(script_dir))
gdf = pd.concat([sejong_gdf, daejeon_gdf]).reset_index(drop=True)
gdf['pickupStationID'] = gdf['StationID']

def parse_onboarding_time(t):
    try:
        t_str = str(int(t)).zfill(12)
        return datetime.strptime(t_str, "%Y%m%d%H%M")
    except:
        return np.nan

con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.dispatch;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
dispatch_df = pd.DataFrame(data, columns=["dispatchID", "messageTime", "passengerID", "requestID", "routeIDs", "pickupStationName", "dropoffStationName", "reserveType", "onboardingTime", "dropoffTime", "linkIDs", "pickupStationID", "dropoffStationID", "tripID", "operationID", "vehicleID"])
dispatch_df['onboarding_datetime'] = dispatch_df['onboardingTime'].apply(parse_onboarding_time)
dispatch_df['dropoff_datetime'] = dispatch_df['dropoffTime'].apply(parse_onboarding_time)

con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.operation;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
operation_df = pd.DataFrame(data, columns=["operationID", "vehicleID", "StationIDs", "routeIDs", "startTime", "endTime", "VehicleType", "operationServiceType"])
operation_df['startTime_datetime'] = operation_df['startTime'].apply(parse_onboarding_time)
operation_df['endTime_datetime'] = operation_df['endTime'].apply(parse_onboarding_time)

con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.route;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
route_df = pd.DataFrame(data, columns=["routeID", "routeSeq", "operationID", "vehicleID", "routeInfo", "linkIDs", "NodeIDs", "originStationID", "originDeptTime", "destinationID", "destDeptTime", "onboardingNum", "dispatchIDs", "lon", "lat", "originBoardingPxIDs", "originGetoffPxIDs", "destBoardingPxIDs", "destGetoffPxIDs"])
route_df['originDeptTime_datetime'] = route_df['originDeptTime'].apply(parse_onboarding_time)
route_df['destDeptTime_datetime'] = route_df['destDeptTime'].apply(parse_onboarding_time)

con = pymysql.connect(
    user=mysql_config['user'],
    passwd=mysql_config['passwd'],
    host=mysql_config['host'],
    port=mysql_config['port'],
    db=mysql_config['db'],
    charset=mysql_config['charset'],
    use_unicode=mysql_config['use_unicode']
)
mycursor = con.cursor()
query = """
    select * from hdl.reservation_request;
"""
mycursor.execute(query)
data = mycursor.fetchall()
con.close()
request_df = pd.DataFrame(data, columns=["requestID", "passengerID", "messageTime", "pickupStationID", "dropoffStationID", "serviceType", "reserveType", "dispatchID", "responseStatus", "confirmCheck", "passengerCount", "wheelchairCount", "failInfoList", "pickupTimeRequest"])

color_list = ['#ED553B', '#173F5F', '#3CAEA3', '#F6D55C', '#20639B', 'brown', 'pink', 'cyan', 'magenta', 'olive']

def return_realtime_operations(current_time, minutes_interval):

    start_range = current_time - dt.timedelta(minutes=minutes_interval)
    end_range = current_time + dt.timedelta(minutes=minutes_interval)

    filtered_df = operation_df[
        ((operation_df["startTime_datetime"] <= start_range) & (operation_df["endTime_datetime"] >= start_range)) |
        ((operation_df["startTime_datetime"] >= start_range) & (operation_df["endTime_datetime"] <= end_range)) |
        ((operation_df["startTime_datetime"] <= end_range) & (operation_df["endTime_datetime"] >= end_range))
    ]

    filtered_route_ids = filtered_df["routeIDs"].tolist()
    filtered_operation_ids = filtered_df["operationID"].tolist()

    final_operation_info = []
    final_route_info = []
    final_pickup_info = []
    final_dropoff_info = []

    for temp_idx in range(len(filtered_route_ids)):

        temp_route_ids = ast.literal_eval(filtered_route_ids[temp_idx])
        temp_operation_id = filtered_operation_ids[temp_idx]
        temp_route_df = route_df[(route_df['operationID']==temp_operation_id) & (route_df['routeID'].isin(temp_route_ids))].sort_values('routeSeq').reset_index(drop=True)
        temp_route_df_one = temp_route_df.copy()

        temp_route_df_one['dispatchIDs'] = temp_route_df_one['dispatchIDs'].apply(lambda x: ast.literal_eval(x) if len(ast.literal_eval(x)) > 0 else np.nan)
        temp_route_df_one['lon'] = temp_route_df_one['lon'].apply(lambda x: ast.literal_eval(x) if len(ast.literal_eval(x)) > 0 else np.nan)
        temp_route_df_one['lat'] = temp_route_df_one['lat'].apply(lambda x: ast.literal_eval(x) if len(ast.literal_eval(x)) > 0 else np.nan)

        temp_route_df_explode = temp_route_df_one.explode('dispatchIDs').reset_index(drop=True)
        temp_route_df_explode['latlon'] = temp_route_df_explode.apply(lambda row: list(zip(row['lat'], row['lon'])), axis=1)
        temp_route_df_explode = temp_route_df_explode.explode('latlon').reset_index(drop=True)

        temp_route_df_explode['lat'] = temp_route_df_explode['latlon'].apply(lambda x: x[0])
        temp_route_df_explode['lon'] = temp_route_df_explode['latlon'].apply(lambda x: x[1])
        temp_route_df_explode.drop(columns='latlon', inplace=True)


        unique_dispatch_ids = temp_route_df_explode['dispatchIDs'].dropna().unique()
        dispatch_color_map = {dispatch_id: color_list[i % len(color_list)] for i, dispatch_id in enumerate(unique_dispatch_ids)}

        temp_route_df_explode['color'] = temp_route_df_explode['dispatchIDs'].map(dispatch_color_map)
        temp_route_df_explode['color'] = temp_route_df_explode['color'].fillna('gray')

        result_df = temp_route_df_explode[['lat', 'lon', 'dispatchIDs', 'onboardingNum', 'color']]
        result_df.rename(columns={'dispatchIDs': 'dispatchID'}, inplace=True)

        temp_dispatch_ids_list = list(dispatch_color_map.keys())
        temp_request_ids = [dispatch_df[dispatch_df['dispatchID'] == disp_id]['requestID'].values[0] for disp_id in temp_dispatch_ids_list]

        pickup_stations = [request_df[request_df['requestID']==temp_one_req_id]['pickupStationID'].values[0] for temp_one_req_id in temp_request_ids]
        dropoff_stations = [request_df[request_df['requestID']==temp_one_req_id]['dropoffStationID'].values[0] for temp_one_req_id in temp_request_ids]

        pickup_df = pd.DataFrame({
            'Station': pickup_stations,
            'lat': [result_df[result_df['dispatchID']==disp_id]['lat'].values[0] for disp_id in temp_dispatch_ids_list],
            'lon': [result_df[result_df['dispatchID']==disp_id]['lon'].values[0] for disp_id in temp_dispatch_ids_list],
            'colors' : [dispatch_color_map[disp_id] for disp_id in temp_dispatch_ids_list],
            'onboardingTime' : [dispatch_df[dispatch_df['dispatchID']==disp_id]['onboarding_datetime'].values[0] for disp_id in temp_dispatch_ids_list],
            'serviceType': ['사전예약' if request_df[request_df['requestID']==temp_one_req_id]['reserveType'].values[0] == 1 else '실시간' for temp_one_req_id in temp_request_ids],
            'passengerCount': [request_df[request_df['requestID']==temp_one_req_id]['passengerCount'].values[0] for temp_one_req_id in temp_request_ids],
            'wheelchairCount': [request_df[request_df['requestID']==temp_one_req_id]['wheelchairCount'].values[0] for temp_one_req_id in temp_request_ids],
        })

        dropoff_df = pd.DataFrame({
            'Station': dropoff_stations,
            'lat': [gdf[gdf['StationID']==temp_station]['StationLat'].values[0] for temp_station in dropoff_stations],
            'lon': [gdf[gdf['StationID']==temp_station]['StationLon'].values[0] for temp_station in dropoff_stations],
            'colors' : [dispatch_color_map[disp_id] for disp_id in temp_dispatch_ids_list],
            'dropoffTime' : [dispatch_df[dispatch_df['dispatchID']==disp_id]['dropoff_datetime'].values[0] for disp_id in temp_dispatch_ids_list],
            'serviceType': ['사전예약' if request_df[request_df['requestID']==temp_one_req_id]['reserveType'].values[0] == 1 else '실시간' for temp_one_req_id in temp_request_ids],
            'passengerCount': [request_df[request_df['requestID']==temp_one_req_id]['passengerCount'].values[0] for temp_one_req_id in temp_request_ids],
            'wheelchairCount': [request_df[request_df['requestID']==temp_one_req_id]['wheelchairCount'].values[0] for temp_one_req_id in temp_request_ids],
        })

        total_dispatch = len(temp_dispatch_ids_list)
        total_passengers = pickup_df.passengerCount.sum()
        total_wheel_count = pickup_df.wheelchairCount.sum()
        total_operation_time = (filtered_df['endTime_datetime'].values[temp_idx] - filtered_df['startTime_datetime'].values[temp_idx]) / np.timedelta64(1, 'm')
        total_vehtype = filtered_df['VehicleType'].values[temp_idx]

        operation_info = [
            total_vehtype, total_operation_time, total_dispatch, total_passengers, total_wheel_count
        ]

        route_info = [
            {"lat": row.lat, "lng": row.lon, "color": row.color, "onboardingNum": row.onboardingNum}
            for _, row in result_df.iterrows()
        ]

        pickup_location_info = [
            {"lat": row.lat, "lng": row.lon, "color": row.colors, "serviceType": row.serviceType, "passengerCount": row.passengerCount, "wheelchairCount": row.wheelchairCount, "onboardingTime": row.onboardingTime}
            for _, row in pickup_df.iterrows()
        ]

        dropoff_location_info = [
            {"lat": row.lat, "lng": row.lon, "color": row.colors, "serviceType": row.serviceType, "passengerCount": row.passengerCount, "wheelchairCount": row.wheelchairCount, "dropoffTime": row.dropoffTime}
            for _, row in dropoff_df.iterrows()
        ]

        final_operation_info.append(operation_info)
        final_route_info.append(route_info)
        final_pickup_info.append(pickup_location_info)
        final_dropoff_info.append(dropoff_location_info)

    return final_operation_info, final_route_info, final_pickup_info, final_dropoff_info
