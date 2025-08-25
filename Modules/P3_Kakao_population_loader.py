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
from shapely.geometry import Point
import yaml
import os

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

sejong_gdf = gpd.read_file("{}/../data/ODD/sejong/Station.shp".format(script_dir))
daejeon_gdf = gpd.read_file("{}/../data/ODD/daejeon/Station.shp".format(script_dir))
gdf = pd.concat([sejong_gdf, daejeon_gdf]).reset_index(drop=True)
gdf['pickupStationID'] = gdf['StationID']

def parse_onboarding_time(t):
    try:
        t_str = str(int(t)).zfill(12)
        return datetime.strptime(t_str, "%Y%m%d%H%M")
    except:
        return np.nan

pop_df = gpd.read_file("{}/../data/sejong/Population/Population_Sample.shp".format(script_dir))
station_df = gpd.read_file("{}/../data/ODD/sejong/Station.shp".format(script_dir))
station_df['pickupStationID'] = station_df['StationID']


dispatch_df = pd.read_csv("{}/../data/dispatch_df.csv".format(script_dir))
dispatch_df['onboarding_datetime'] = dispatch_df['onboardingTime'].apply(parse_onboarding_time)
dispatch_df['dropoff_datetime'] = dispatch_df['dropoffTime'].apply(parse_onboarding_time)

operation_df = pd.read_csv("{}/../data/operation_df.csv".format(script_dir))
operation_df['startTime_datetime'] = operation_df['startTime'].apply(parse_onboarding_time)
operation_df['endTime_datetime'] = operation_df['endTime'].apply(parse_onboarding_time)

route_df = pd.read_csv("{}/../data/route_df.csv".format(script_dir))
route_df['originDeptTime_datetime'] = route_df['originDeptTime'].apply(parse_onboarding_time)
route_df['destDeptTime_datetime'] = route_df['destDeptTime'].apply(parse_onboarding_time)

request_df = pd.read_csv("{}/../data/request_df.csv".format(script_dir))


vehicle_df = operation_df.drop_duplicates(['vehicleID', 'VehicleType'])[['vehicleID', 'VehicleType']]
vehicle_dict = dict(zip(vehicle_df['vehicleID'], vehicle_df['VehicleType']))

def return_last_population_df(current_time, days_interval):

    temp_dispatch_df = dispatch_df[(dispatch_df['onboarding_datetime'] >= current_time - dt.timedelta(days=days_interval*2)) & (dispatch_df['onboarding_datetime'] < current_time)].sort_values("onboarding_datetime").reset_index(drop=True)
    temp_dispatch_df = temp_dispatch_df[['onboarding_datetime', 'reserveType', 'dispatchID', 'pickupStationID', 'vehicleID']]
    temp_dispatch_df['Day'] = [(temp_dispatch_df['onboarding_datetime'][i] - current_time).days for i in range(len(temp_dispatch_df))]
    temp_dispatch_df['Hour'] = [temp_dispatch_df['onboarding_datetime'][i].hour for i in range(len(temp_dispatch_df))]

    temp_station_df = station_df[['pickupStationID', 'StationLat', 'StationLon']]
    temp_merged_df = pd.merge(left = temp_dispatch_df , right = temp_station_df, how = "inner", on = "pickupStationID")
    temp_merged_df['vehicleType'] = [vehicle_dict[vehid] for vehid in temp_merged_df['vehicleID'].tolist()]

    temp_request_df = request_df[['dispatchID', 'passengerCount', 'wheelchairCount', 'serviceType']]
    final_merged_df = pd.merge(left = temp_merged_df , right = temp_request_df, how = "inner", on = "dispatchID")

    past_df = final_merged_df[final_merged_df['Day'] < -days_interval].reset_index(drop=True)
    last_df = final_merged_df[final_merged_df['Day'] >= -days_interval].reset_index(drop=True)

    last_df['geometry'] = last_df.apply(lambda row: Point(row['StationLon'], row['StationLat']), axis=1)
    last_gdf = gpd.GeoDataFrame(last_df, geometry='geometry', crs="EPSG:4326")

    wheelchair_df = last_gdf[last_gdf['wheelchairCount'] == 1]
    joined_disabled = gpd.sjoin(wheelchair_df, pop_df, how="left", predicate="within")

    older_df = last_gdf[last_gdf['wheelchairCount'] == 0]
    joined_older = gpd.sjoin(older_df, pop_df, how="left", predicate="within")

    disabled_counts = joined_disabled.groupby('gid')['passengerCount'].sum().reset_index()
    disabled_counts.rename(columns={'passengerCount': 'pickup_disabledCount'}, inplace=True)

    older_counts = joined_older.groupby('gid')['passengerCount'].sum().reset_index()
    older_counts.rename(columns={'passengerCount': 'pickup_olderadultsCount'}, inplace=True)

    final_pop_df = pop_df.merge(disabled_counts, on='gid', how='left')
    final_pop_df = final_pop_df.merge(older_counts, on='gid', how='left')

    final_pop_df['pickup_disabledCount'] = final_pop_df['pickup_disabledCount'].fillna(0).astype(int)
    final_pop_df['pickup_olderadultsCount'] = final_pop_df['pickup_olderadultsCount'].fillna(0).astype(int)
    final_pop_df['pickup_totalCount'] = final_pop_df['pickup_disabledCount'] + final_pop_df['pickup_olderadultsCount']

    final_pop_df['disabled_percent'] = (final_pop_df['pickup_disabledCount'] / final_pop_df['disabled']) * 0.9
    final_pop_df['olderadults_percent'] = (final_pop_df['pickup_olderadultsCount'] / final_pop_df['older_adul']) * 0.9
    final_pop_df['total_percent'] = final_pop_df['disabled_percent'] + final_pop_df['olderadults_percent'] * 0.9

    final_pop_df = final_pop_df[['disabled_percent', 'olderadults_percent', 'total_percent', 'geometry']]

    return final_pop_df

def summarize_counts_by_day(df, total_people_count, total_diabled_count, total_olderadults_count):

    all_days = sorted(df["Day"].unique())
    total = df.groupby("Day")["passengerCount"].sum().reindex(all_days, fill_value=0)
    disabled = df[df["wheelchairCount"] == 0].groupby("Day")["passengerCount"].sum().reindex(all_days, fill_value=0)
    older_adults = df[df["wheelchairCount"] == 1].groupby("Day")["passengerCount"].sum().reindex(all_days, fill_value=0)
    
    summary_df = pd.DataFrame({
        "total_count": np.round(total / total_people_count * 100 ,1),
        "disabled_count": np.round(disabled / total_diabled_count * 100 ,1),
        "older_adults_count": np.round(older_adults / total_olderadults_count * 100 ,1)
    }).reset_index().rename(columns={"Day": "day"})
    return summary_df

def return_last_past_population_df(current_time, days_interval, total_people_count, total_diabled_count, total_olderadults_count):

    temp_dispatch_df = dispatch_df[(dispatch_df['onboarding_datetime'] >= current_time - dt.timedelta(days=days_interval*2)) & (dispatch_df['onboarding_datetime'] < current_time)].sort_values("onboarding_datetime").reset_index(drop=True)
    temp_dispatch_df = temp_dispatch_df[['onboarding_datetime', 'reserveType', 'dispatchID', 'pickupStationID', 'vehicleID']]
    temp_dispatch_df['Day'] = [(temp_dispatch_df['onboarding_datetime'][i] - current_time).days for i in range(len(temp_dispatch_df))]
    temp_dispatch_df['Hour'] = [temp_dispatch_df['onboarding_datetime'][i].hour for i in range(len(temp_dispatch_df))]

    temp_station_df = station_df[['pickupStationID', 'StationLat', 'StationLon']]
    temp_merged_df = pd.merge(left = temp_dispatch_df , right = temp_station_df, how = "inner", on = "pickupStationID")
    temp_merged_df['vehicleType'] = [vehicle_dict[vehid] for vehid in temp_merged_df['vehicleID'].tolist()]

    temp_request_df = request_df[['dispatchID', 'passengerCount', 'wheelchairCount', 'serviceType']]
    final_merged_df = pd.merge(left = temp_merged_df , right = temp_request_df, how = "inner", on = "dispatchID")

    past_df = final_merged_df[final_merged_df['Day'] < -days_interval].reset_index(drop=True)
    last_df = final_merged_df[final_merged_df['Day'] >= -days_interval].reset_index(drop=True)

    past_summary_df = summarize_counts_by_day(past_df, total_people_count, total_diabled_count, total_olderadults_count)
    last_summary_df = summarize_counts_by_day(last_df, total_people_count, total_diabled_count, total_olderadults_count)

    past_total_sum = past_summary_df.total_count.mean()
    past_disabled_sum = past_summary_df.disabled_count.mean()
    past_older_adults_sum = past_summary_df.older_adults_count.mean()

    last_total_sum = last_summary_df.total_count.mean()
    last_disabled_sum = last_summary_df.disabled_count.mean()
    last_older_adults_sum = last_summary_df.older_adults_count.mean()

    return last_summary_df, past_summary_df, [last_total_sum, past_total_sum, last_disabled_sum, past_disabled_sum, last_older_adults_sum, past_older_adults_sum]