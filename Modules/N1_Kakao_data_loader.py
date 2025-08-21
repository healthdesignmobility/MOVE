import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import datetime as dt
import itertools
import json
import pymysql
import geopandas as gpd
import yaml
import os

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

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

df = pd.read_csv("{}/data/dispatch_df.csv".format(script_dir))
df['onboarding_datetime'] = df['onboardingTime'].apply(parse_onboarding_time)

def return_pickup_station_count(current_time, days_interval):
    df_from_now = df[(df['onboarding_datetime'] < current_time)&(df['onboarding_datetime'] >= current_time - dt.timedelta(days=days_interval))]
    last_log = df_from_now.sort_values('onboarding_datetime')['onboarding_datetime'].values[-1]
    pickup_counts = df_from_now['pickupStationID'].value_counts()
    pickup_station_count_df = pd.DataFrame(pickup_counts).reset_index()
    merged_df = pd.merge(left = pickup_station_count_df , right = gdf, how = "inner", on = "pickupStationID")
    merged_df = merged_df.sort_values("StationLat", ascending=False).reset_index(drop=True)
    locations = [
        {"lat": row.StationLat, "lng": row.StationLon, "weight": row['count'], "station": row['pickupStationID']}
        for _, row in merged_df.iterrows()
    ]
    return locations, pd.to_datetime(last_log).to_pydatetime().strftime("%Y-%m-%d %H:%M")