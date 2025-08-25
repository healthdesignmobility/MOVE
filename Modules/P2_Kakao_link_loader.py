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
from collections import Counter
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


def return_link_frequency(current_time, day_interval):

    temp_route_df = route_df[(route_df['destDeptTime_datetime'] <= current_time) & (route_df['originDeptTime_datetime'] >= current_time - dt.timedelta(days=day_interval))].reset_index(drop=True)

    link_list = []

    for idx, row in temp_route_df.iterrows():
        lons = ast.literal_eval(row['lon'])
        lats = ast.literal_eval(row['lat'])

        for i in range(len(lons) - 1):
            link = ((lons[i], lats[i]), (lons[i+1], lats[i+1]))
            link_list.append(link)

    link_counter = Counter(link_list)

    link_df = pd.DataFrame([
        {'start_lon': s[0], 'start_lat': s[1],
        'end_lon': e[0], 'end_lat': e[1],
        'count': count}
        for ((s, e), count) in link_counter.items()
    ])

    return link_df, pd.to_datetime(temp_route_df.sort_values('destDeptTime_datetime')['destDeptTime_datetime'].values[-1]).to_pydatetime()