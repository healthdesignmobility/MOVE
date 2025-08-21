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
import plotly.graph_objects as go
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

dispatch_df = pd.read_csv("{}/data/dispatch_df.csv".format(script_dir))
dispatch_df['onboarding_datetime'] = dispatch_df['onboardingTime'].apply(parse_onboarding_time)
dispatch_df['dropoff_datetime'] = dispatch_df['dropoffTime'].apply(parse_onboarding_time)

operation_df = pd.read_csv("{}/data/operation_df.csv".format(script_dir))
operation_df['startTime_datetime'] = operation_df['startTime'].apply(parse_onboarding_time)
operation_df['endTime_datetime'] = operation_df['endTime'].apply(parse_onboarding_time)

route_df = pd.read_csv("{}/data/route_df.csv".format(script_dir))
route_df['originDeptTime_datetime'] = route_df['originDeptTime'].apply(parse_onboarding_time)
route_df['destDeptTime_datetime'] = route_df['destDeptTime'].apply(parse_onboarding_time)

request_df = pd.read_csv("{}/data/request_df.csv".format(script_dir))

def return_reserveType(current_time, day_interval):

    temp_dispatch_df = dispatch_df[(dispatch_df['onboarding_datetime'] <= current_time)&(dispatch_df['onboarding_datetime'] >= current_time - dt.timedelta(days=day_interval))].reset_index(drop=True)
    temp_dispatch_ids = temp_dispatch_df.dispatchID.tolist()
    temp_request_df = request_df[(request_df['dispatchID'].isin(temp_dispatch_ids))].reset_index(drop=True)
    temp_request_df['reserveType'] = temp_request_df['reserveType'].map({1: '사전예약', 2: '실시간'})

    return temp_request_df[['reserveType']]

def return_serviceType(current_time, day_interval):

    temp_dispatch_df = dispatch_df[(dispatch_df['onboarding_datetime'] <= current_time)&(dispatch_df['onboarding_datetime'] >= current_time - dt.timedelta(days=day_interval))].reset_index(drop=True)
    temp_dispatch_ids = temp_dispatch_df.dispatchID.tolist()
    temp_request_df = request_df[(request_df['dispatchID'].isin(temp_dispatch_ids))].reset_index(drop=True)
    temp_request_df['serviceType'] = temp_request_df['serviceType'].map({1: '교통약자', 2: '소외지역'})

    return temp_request_df[['serviceType']]

def return_failinfo(current_time, day_interval):
    request_df['messageTime'] = pd.to_datetime(request_df['messageTime'], unit='ms')
    temp_request_df = request_df[(request_df['messageTime'] <= current_time)&(request_df['messageTime'] >= current_time - dt.timedelta(days=day_interval))].reset_index(drop=True)
    temp_request_df = temp_request_df.dropna(subset=['failInfoList']).reset_index(drop=True)
    temp_request_df['failInfoList'] = temp_request_df['failInfoList'].apply(lambda x: np.nan if None else ast.literal_eval(x))

    def extract_failinfo(temp_list):
        if len(temp_list) == 0:
            return('원인미상')
        elif 503 in temp_list:
            return('경로 없음')
        elif 501 in temp_list:
            return('배터리 부족')
        elif 302 in temp_list:
            return('차량 부족')
        elif 301 in temp_list:
            return('좌석 부족')
        elif 202 in temp_list:
            return('대기시간 초과')
        elif 201 in temp_list:
            return('우회시간 초과')
        else:
            return('기타')

    temp_request_df['failInfo_Main'] = temp_request_df['failInfoList'].apply(lambda x: extract_failinfo(x))

    return temp_request_df[['failInfo_Main']]

def operation_vehicle(current_time, day_interval):
    temp_operation_df = operation_df[(operation_df['startTime_datetime'] <= current_time)&(operation_df['startTime_datetime'] >= current_time - dt.timedelta(days=day_interval))].reset_index(drop=True)
    temp_operation_df['VehicleType'] = temp_operation_df['VehicleType'].map({'carnivalReg': '카니발(일반)', 'carnivalWheel': '카니발(휠체어)', 'IONIQ5': '아이오닉5'})
    
    return temp_operation_df[['VehicleType']]
