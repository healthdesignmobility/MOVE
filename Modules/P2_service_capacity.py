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
import streamlit as st

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

sejong_gdf = gpd.read_file("{}/../data/ODD/sejong/Station.shp".format(script_dir))
daejeon_gdf = gpd.read_file("{}/../data/ODD/daejeon/Station.shp".format(script_dir))
gdf = pd.concat([sejong_gdf, daejeon_gdf]).reset_index(drop=True)
gdf['pickupStationID'] = gdf['StationID']

# 차량별 최대 좌석 수
max_seats = {
    'carnivalReg': 6,
    'carnivalWheel': 2,
    'IONIQ5': 3    
}
vehicle_types = list(max_seats.keys())

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

def return_service_capacity(current_time, days_interval):

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
    temp_route_df['hour'] = temp_route_df['originDeptTime_datetime'].dt.hour
    temp_route_df['Day'] = [(temp_route_df['originDeptTime_datetime'][i] - current_time).days for i in range(len(temp_route_df))]

    temp_route_df = temp_route_df[temp_route_df['onboardingNum'] <= temp_route_df['Capacity']].reset_index(drop=True)
    temp_route_df['service_capacity'] = (temp_route_df['onboardingNum'] / temp_route_df['Capacity']) * 100

    past_df = temp_route_df[temp_route_df['Day'] < -days_interval].reset_index(drop=True)
    last_df = temp_route_df[temp_route_df['Day'] >= -days_interval].reset_index(drop=True)

    daily_service_last_df = (
        last_df
        .groupby(['Day', 'vehicleType'])['service_capacity']
        .mean()
        .reset_index()
    )

    daily_last_pivot = daily_service_last_df.pivot(index='Day', columns='vehicleType', values='service_capacity')
    daily_last_pivot = daily_last_pivot.reindex(columns=vehicle_types)

    daily_last_pivot.columns.name = None
    daily_last_pivot = daily_last_pivot.reset_index()

    daily_last_df = daily_last_pivot[['Day', 'carnivalReg', 'carnivalWheel', 'IONIQ5']]

    daily_service_past_df = (
        past_df
        .groupby(['Day', 'vehicleType'])['service_capacity']
        .mean()
        .reset_index()
    )

    daily_past_pivot = daily_service_past_df.pivot(index='Day', columns='vehicleType', values='service_capacity')
    daily_past_pivot = daily_past_pivot.reindex(columns=vehicle_types)

    daily_past_pivot.columns.name = None
    daily_past_pivot = daily_past_pivot.reset_index()

    daily_past_df = daily_past_pivot[['Day', 'carnivalReg', 'carnivalWheel', 'IONIQ5']]

    mean_last_capacity = np.nanmean(daily_last_df[vehicle_types])
    mean_past_capacity = np.nanmean(daily_past_df[vehicle_types])

    daily_last_df = daily_last_df.rename(columns={
        'carnivalReg': '카니발(일반)',
        'carnivalWheel': '카니발(휠체어)',
        'IONIQ5': '아이오닉5'
    })

    daily_past_df = daily_past_df.rename(columns={
        'carnivalReg': '카니발(일반)',
        'carnivalWheel': '카니발(휠체어)',
        'IONIQ5': '아이오닉5'
    })

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
    ma_carnivalReg = compute_centered_moving_average(combined_df, '카니발(일반)', target_days, window_size)
    ma_carnivalWheel = compute_centered_moving_average(combined_df, '카니발(휠체어)', target_days, window_size)
    ma_IONIQ5 = compute_centered_moving_average(combined_df, '아이오닉5', target_days, window_size)

    def generating_chart(temp_df, ma_carnivalReg, ma_carnivalWheel, ma_IONIQ5, temp_color_1, temp_color_2, temp_color_3, feature, unit, code_unit):
        plot_df = temp_df.copy()
        plot_df['카니발(일반)-추세'] = ma_carnivalReg
        plot_df['카니발(휠체어)-추세'] = ma_carnivalWheel
        plot_df['아이오닉5-추세'] = ma_IONIQ5

        carnivalReg_df = plot_df[[code_unit, '카니발(일반)']].rename(columns={'카니발(일반)': 'value'})
        carnivalReg_df['type'] = '카니발(일반)'

        carnivalWheel_df = plot_df[[code_unit, '카니발(휠체어)']].rename(columns={'카니발(휠체어)': 'value'})
        carnivalWheel_df['type'] = '카니발(휠체어)'

        IONIQ5_df = plot_df[[code_unit, '아이오닉5']].rename(columns={'아이오닉5': 'value'})
        IONIQ5_df['type'] = '아이오닉5'

        carnivalReg_df_ma = plot_df[[code_unit, '카니발(일반)-추세']].rename(columns={'카니발(일반)-추세': 'value'})
        carnivalReg_df_ma['type'] = '카니발(일반)-추세'

        carnivalWheel_df_ma = plot_df[[code_unit, '카니발(휠체어)-추세']].rename(columns={'카니발(휠체어)-추세': 'value'})
        carnivalWheel_df_ma['type'] = '카니발(휠체어)-추세'

        IONIQ5_df_ma = plot_df[[code_unit, '아이오닉5-추세']].rename(columns={'아이오닉5-추세': 'value'})
        IONIQ5_df_ma['type'] = '아이오닉5-추세'

        long_df = pd.concat([carnivalReg_df, carnivalWheel_df, IONIQ5_df, carnivalReg_df_ma, carnivalWheel_df_ma, IONIQ5_df_ma])

        color_scale = alt.Scale(
            domain=['카니발(일반)', '카니발(일반)-추세', '카니발(휠체어)', '카니발(휠체어)-추세', '아이오닉5', '아이오닉5-추세'],
            range=[temp_color_1, temp_color_1, temp_color_2, temp_color_2, temp_color_3, temp_color_3]
        )

        stroke_dash_scale = alt.Scale(
            domain=['카니발(일반)', '카니발(일반)-추세', '카니발(휠체어)', '카니발(휠체어)-추세', '아이오닉5', '아이오닉5-추세'],
            range=[[0], [4, 4], [0], [4, 4], [0], [4, 4]]
        )

        base = alt.Chart(long_df).encode(
            x=alt.X(f'{code_unit}:O', title=code_unit, axis=alt.Axis(labelAngle=0)),

            color=alt.Color('type:N',
                scale=color_scale,
                legend=alt.Legend(
                    title=None,
                    orient='top',
                    direction='vertical',
                    columns=3,
                    symbolSize=10,
                    labelExpr="indexof(datum.label, '-추세') < 0 ? datum.label : '| 추세'"
                )
            ),
            strokeDash=alt.StrokeDash('type:N', scale=stroke_dash_scale)
        )
        
        chart = base.encode(
            y=alt.Y('value:Q', axis=alt.Axis(title=f'{feature} ({unit})')),
            opacity=alt.condition(
                alt.FieldOneOfPredicate(field='type', oneOf=['카니발(일반)-추세', '카니발(휠체어)-추세', '아이오닉5-추세']),
                alt.value(0.5),
                alt.value(1.0)
            )
        ).mark_line(point=True).properties(
            width=400,
            height=300
        )

        return chart

    chart_daily = generating_chart(daily_last_df, ma_carnivalReg, ma_carnivalWheel, ma_IONIQ5, '#006ACD', '#FFB1B0', '#7CBEF2', '서비스 수송률', '%', 'Day')

    return chart_daily, [mean_last_capacity, mean_past_capacity]
