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
import math
import altair as alt
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

# 차량별 최대 좌석수
max_seats = {
    'carnivalReg': 6,
    'carnivalWheel': 2,
    'IONIQ5': 3    
}
vehicle_types = list(max_seats.keys())

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


def return_boaring_vehicle_rates(current_time, days_interval):

    temp_operation_df = operation_df[(operation_df['endTime_datetime'] >= current_time - dt.timedelta(days=days_interval*2)) & (operation_df['endTime_datetime'] < current_time)].sort_values("endTime_datetime").reset_index(drop=True)
    unique_combinations = temp_operation_df[['vehicleID', 'VehicleType']].drop_duplicates()
    vehicle_dict = dict(zip(unique_combinations['vehicleID'], unique_combinations['VehicleType']))

    temp_operation_df['Operation_vehicle'] = [str(temp_operation_df['operationID'][i]) + '_' + str(temp_operation_df['vehicleID'][i]) for i in range(len(temp_operation_df))]
    route_df['Operation_vehicle'] = [str(route_df['operationID'][i]) + '_' + str(route_df['vehicleID'][i]) for i in range(len(route_df))]
    temp_route_df = route_df[route_df['Operation_vehicle'].isin(temp_operation_df['Operation_vehicle'].unique().tolist())].reset_index(drop=True)
    temp_route_df['vehicleType'] = [vehicle_dict[temp_route_df['vehicleID'][i]] for i in range(len(temp_route_df))]
    temp_route_df = temp_route_df[['originDeptTime_datetime', 'destDeptTime_datetime', 'vehicleType', 'onboardingNum']]
    temp_route_df['Capacity'] = [max_seats[temp_route_df['vehicleType'][i]] for i in range(len(temp_route_df))]

    temp_route_df['trip_duration'] = (temp_route_df['destDeptTime_datetime'] - temp_route_df['originDeptTime_datetime']).dt.total_seconds()
    temp_route_df['boarded'] = temp_route_df['onboardingNum'] > 0
    temp_route_df['date'] = temp_route_df['originDeptTime_datetime'].dt.date
    temp_route_df['Hour'] = temp_route_df['originDeptTime_datetime'].dt.hour
    temp_route_df['Day'] = [(temp_route_df['originDeptTime_datetime'][i] - current_time).days for i in range(len(temp_route_df))]

    past_df = temp_route_df[temp_route_df['Day'] < -days_interval].reset_index(drop=True)
    last_df = temp_route_df[temp_route_df['Day'] >= -days_interval].reset_index(drop=True)

    daily_past_df = (
        past_df
        .groupby('Day')['boarded']
        .agg(['sum', 'count'])
        .rename(columns={'sum': 'boarded_count', 'count': 'total_count'})
        .reset_index()
    )
    daily_past_df['boarding_rate'] = np.round(daily_past_df['boarded_count'] / daily_past_df['total_count'] * 100, 1)
    daily_past_df = daily_past_df[['Day', 'boarding_rate']].reset_index(drop=True)

    daily_last_df = (
        last_df
        .groupby('Day')['boarded']
        .agg(['sum', 'count'])
        .rename(columns={'sum': 'boarded_count', 'count': 'total_count'})
        .reset_index()
    )
    daily_last_df['boarding_rate'] = np.round(daily_last_df['boarded_count'] / daily_last_df['total_count'] * 100, 1)
    daily_last_df = daily_last_df[['Day', 'boarding_rate']].reset_index(drop=True)

    hourly_df = (
        last_df
        .groupby('Hour')['boarded']
        .agg(['sum', 'count'])
        .rename(columns={'sum': 'boarded_count', 'count': 'total_count'})
        .reset_index()
    )
    hourly_df['boarding_rate'] = np.round(hourly_df['boarded_count'] / hourly_df['total_count'] * 100, 1)
    hourly_df = hourly_df[['Hour', 'boarding_rate']].reset_index(drop=True)

    mean_last_occupancy = np.nanmean(daily_last_df['boarding_rate'])
    mean_past_occupancy = np.nanmean(daily_past_df['boarding_rate'])

    window_size = math.ceil(days_interval / 2)
    combined_df = pd.concat([daily_past_df, daily_last_df], ignore_index=True).sort_values('Day').reset_index(drop=True)

    def compute_centered_moving_average(df, col_name, target_days, window_size=3):
        if window_size % 2 != 1:
            radius = (window_size // 2) + 1
        else:
            radius = window_size // 2
        values = df[col_name].values
        ma_values = []

        for i in range(len(values)):
            start = max(0, i - radius)
            end = min(len(values), i + radius + 1)
            window = values[start:end]
            ma = np.nanmean(window)
            ma_values.append(np.round(ma, 2))

        return ma_values[-len(target_days):]

    target_days = daily_last_df['Day'].values
    ma_carnivalReg = compute_centered_moving_average(combined_df, 'boarding_rate', target_days, window_size)

    hourly_target_days = hourly_df['Hour'].values
    hourly_ma_carnivalReg = compute_centered_moving_average(hourly_df, 'boarding_rate', hourly_target_days, window_size)

    def draw_boarding_rate_area_chart(daily_last_df, ma_carnivalReg, color, feature, unit, code_unit):

        plot_df = daily_last_df.copy()
        plot_df['추세'] = ma_carnivalReg

        area = alt.Chart(plot_df).mark_area(
            opacity=0.3,
            color=color
        ).encode(
            x=alt.X(f'{code_unit}:O', title=code_unit, axis=alt.Axis(labelAngle=0)),
            y=alt.Y('boarding_rate:Q', title=f'{feature} ({unit})')
        )

        trend_line = alt.Chart(plot_df).mark_line(
            color='#ED553B', 
            strokeWidth=3,
            strokeDash=[4, 2],
            point=alt.OverlayMarkDef(
                filled=True,
                fill='#ED553B',
                stroke='#ED553B',
                strokeWidth=0.5,
                size=50
            )
        ).encode(
            x=f'{code_unit}:O',
            y='추세:Q'
        )

        chart = (area + trend_line).properties(
            width=400,
            height=200
        )

        return chart

    chart_daily = draw_boarding_rate_area_chart(daily_last_df, ma_carnivalReg, '#7CBEF2', '실차 운행률', '%', 'Day')
    chart_hourly = draw_boarding_rate_area_chart(hourly_df, hourly_ma_carnivalReg, '#FFB1B0', '실차 운행률', '%', 'Hour')

    return chart_daily, chart_hourly, [mean_last_occupancy, mean_past_occupancy]