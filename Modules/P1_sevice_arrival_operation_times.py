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


def return_graphs_and_stats(current_time, days_interval):

    temp_operation_df = operation_df[(operation_df['endTime_datetime'] >= current_time - dt.timedelta(days=days_interval*2)) & (operation_df['endTime_datetime'] < current_time)].sort_values("endTime_datetime").reset_index(drop=True)
    temp_operation_df['Day'] = [(temp_operation_df['endTime_datetime'][i] - current_time).days for i in range(len(temp_operation_df))]
    temp_operation_df['Hour'] = [temp_operation_df['endTime_datetime'][i].hour for i in range(len(temp_operation_df))]
    temp_operation_df['Operation_vehicle'] = [str(temp_operation_df['operationID'][i]) + '_' + str(temp_operation_df['vehicleID'][i]) for i in range(len(temp_operation_df))]
    temp_operation_df = temp_operation_df[['Operation_vehicle', 'VehicleType', 'Day', 'Hour']]
    dispatch_df['Operation_vehicle'] = [str(dispatch_df['operationID'][i]) + '_' + str(dispatch_df['vehicleID'][i]) for i in range(len(dispatch_df))]
    temp_operations = temp_operation_df.Operation_vehicle.tolist()
    temp_dispatch_df = dispatch_df[dispatch_df['Operation_vehicle'].isin(temp_operations)].reset_index(drop=True)
    temp_merged = pd.merge(left = temp_dispatch_df , right = temp_operation_df, how = "inner", on = "Operation_vehicle")

    temp_dispatchIDs = temp_merged.dispatchID.tolist()
    temp_request_df = request_df[request_df['dispatchID'].isin(temp_dispatchIDs)].reset_index(drop=True)
    temp_request_df['messageTime_Request'] = temp_request_df['messageTime']
    temp_request_df['messageTime_Request'] = pd.to_datetime(temp_request_df['messageTime_Request'], unit='ms', utc=True)
    temp_request_df['messageTime_Request'] = temp_request_df['messageTime_Request'].dt.tz_convert('Asia/Seoul')

    temp_request_df = temp_request_df[['dispatchID', 'messageTime_Request', 'pickupTimeRequest']]
    final_merged = pd.merge(left = temp_merged , right = temp_request_df, how = "inner", on = "dispatchID").sort_values('Day').reset_index(drop=True)
    FFinal_merged = final_merged[['Day', 'VehicleType', 'onboarding_datetime', 'dropoff_datetime']]
    FFinal_merged['Expected_operation_time'] = [(FFinal_merged['dropoff_datetime'][i] - FFinal_merged['onboarding_datetime'][i]).total_seconds()/60 for i in range(len(FFinal_merged))]
    FFinal_merged = FFinal_merged.dropna().reset_index(drop=True)

    # 실제 승차 시간과 하차 시간을 알 수 없으니, 랜덤 값으로 대체
    np.random.seed(1996)
    onboarding_late = np.random.randint(-10, 30, size=len(FFinal_merged)).tolist()
    np.random.seed(1107)
    dropoff_late = np.random.randint(-10, 30, size=len(FFinal_merged)).tolist()

    actual_onboarding = []
    actual_dropoff = []

    for i in range(len(FFinal_merged)):

        temp_time_1 = FFinal_merged['onboarding_datetime'][i] + dt.timedelta(minutes=onboarding_late[i])
        temp_time_2 = FFinal_merged['dropoff_datetime'][i] + dt.timedelta(minutes=dropoff_late[i])

        if temp_time_1 < temp_time_2:
            actual_onboarding.append(temp_time_1)
            actual_dropoff.append(temp_time_2)
        else:
            actual_onboarding.append(temp_time_2)
            actual_dropoff.append(temp_time_1)

    FFinal_merged['Actual_onboarding_time'] = actual_onboarding
    FFinal_merged['Actual_dropoff_time'] = actual_dropoff
    FFinal_merged['Actual_use_time'] = [(FFinal_merged['Actual_dropoff_time'][i] - FFinal_merged['Actual_onboarding_time'][i]).total_seconds()/60 for i in range(len(FFinal_merged))]
    FFinal_merged['pickup_delay'] = [(FFinal_merged['Actual_onboarding_time'][i] - FFinal_merged['onboarding_datetime'][i]).total_seconds()/60 for i in range(len(FFinal_merged))]
    FFinal_merged['operation_delay'] = [(FFinal_merged['Actual_use_time'][i] - FFinal_merged['Expected_operation_time'][i]) for i in range(len(FFinal_merged))]
    FFinal_merged = FFinal_merged[['Day', 'VehicleType', 'Actual_use_time', 'pickup_delay', 'operation_delay']]

    past_df = FFinal_merged[FFinal_merged['Day'] < -days_interval].reset_index(drop=True)
    last_df = FFinal_merged[FFinal_merged['Day'] >= -days_interval].reset_index(drop=True)

    mean_last_Actual_use_time = np.nanmean(last_df['Actual_use_time'])
    mean_past_Actual_use_time = np.nanmean(past_df['Actual_use_time'])
    mean_last_pickup_delay = np.nanmean(last_df['pickup_delay'])
    mean_past_pickup_delay = np.nanmean(past_df['pickup_delay'])
    mean_last_operation_delay = np.nanmean(last_df['operation_delay'])
    mean_past_operation_delay = np.nanmean(past_df['operation_delay'])

    def summarize_df(df, temp_col):
        
        temp_df = df[df['VehicleType'] == 'carnivalReg']
        all_days = sorted(temp_df["Day"].unique())
        response_carnivalReg = temp_df.groupby("Day")[temp_col].mean().reindex(all_days, fill_value=0)

        temp_df = df[df['VehicleType'] == 'carnivalWheel']
        all_days = sorted(temp_df["Day"].unique())
        response_carnivalWheel = temp_df.groupby("Day")[temp_col].mean().reindex(all_days, fill_value=0)

        temp_df = df[df['VehicleType'] == 'IONIQ5']
        all_days = sorted(temp_df["Day"].unique())
        response_IONIQ5 = temp_df.groupby("Day")[temp_col].mean().reindex(all_days, fill_value=0)

        summary_df = pd.DataFrame({
            '카니발(일반)': np.round(response_carnivalReg, 2),
            '카니발(휠체어)': np.round(response_carnivalWheel, 2),
            '아이오닉5': np.round(response_IONIQ5, 2)
        }).reset_index().rename(columns={"Day": "day"})
        return summary_df

    last_summary_Actual_use_time_df = summarize_df(last_df, "Actual_use_time")
    past_summary_Actual_use_time_df = summarize_df(past_df, "Actual_use_time")
    last_summary_pickup_delay_df = summarize_df(last_df, "pickup_delay")
    past_summary_pickup_delay_df = summarize_df(past_df, "pickup_delay")
    last_summary_operation_delay_df = summarize_df(last_df, "operation_delay")
    past_summary_operation_delay_df = summarize_df(past_df, "operation_delay")

    window_size = math.ceil(days_interval / 2)

    combined_Actual_use_time_df = pd.concat([past_summary_Actual_use_time_df, last_summary_Actual_use_time_df], ignore_index=True).sort_values('day').reset_index(drop=True)
    combined_pickup_delay_df = pd.concat([past_summary_pickup_delay_df, last_summary_pickup_delay_df], ignore_index=True).sort_values('day').reset_index(drop=True)
    combined_operation_delay_df = pd.concat([past_summary_operation_delay_df, last_summary_operation_delay_df], ignore_index=True).sort_values('day').reset_index(drop=True)

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
            ma_values.append(np.round(ma, 1))

        return ma_values[-len(target_days):]

    target_days_Actual_use_time = last_summary_Actual_use_time_df['day'].values
    ma_carnivalReg_Actual_use_time = compute_centered_moving_average(combined_Actual_use_time_df, '카니발(일반)', target_days_Actual_use_time, window_size)
    ma_carnivalWheel_Actual_use_time = compute_centered_moving_average(combined_Actual_use_time_df, '카니발(휠체어)', target_days_Actual_use_time, window_size)
    ma_IONIQ5_Actual_use_time = compute_centered_moving_average(combined_Actual_use_time_df, '아이오닉5', target_days_Actual_use_time, window_size)

    target_days_pickup_delay = last_summary_pickup_delay_df['day'].values
    ma_carnivalReg_pickup_delay = compute_centered_moving_average(combined_pickup_delay_df, '카니발(일반)', target_days_pickup_delay, window_size)
    ma_carnivalWheel_pickup_delay = compute_centered_moving_average(combined_pickup_delay_df, '카니발(휠체어)', target_days_pickup_delay, window_size)
    ma_IONIQ5_pickup_delay = compute_centered_moving_average(combined_pickup_delay_df, '아이오닉5', target_days_pickup_delay, window_size)

    target_days_operation_delay = last_summary_operation_delay_df['day'].values
    ma_carnivalReg_operation_delay = compute_centered_moving_average(combined_operation_delay_df, '카니발(일반)', target_days_operation_delay, window_size)
    ma_carnivalWheel_operation_delay = compute_centered_moving_average(combined_operation_delay_df, '카니발(휠체어)', target_days_operation_delay, window_size)
    ma_IONIQ5_operation_delay = compute_centered_moving_average(combined_operation_delay_df, '아이오닉5', target_days_operation_delay, window_size)

    def generating_chart(temp_df, ma_carnivalReg, ma_carnivalWheel, ma_IONIQ5, temp_color_1, temp_color_2, temp_color_3, feature, unit):
        plot_df = temp_df.copy()
        plot_df['카니발(일반)-추세'] = ma_carnivalReg
        plot_df['카니발(휠체어)-추세'] = ma_carnivalWheel
        plot_df['아이오닉5-추세'] = ma_IONIQ5

        carnivalReg_df = plot_df[['day', '카니발(일반)']].rename(columns={'카니발(일반)': 'value'})
        carnivalReg_df['type'] = '카니발(일반)'

        carnivalWheel_df = plot_df[['day', '카니발(휠체어)']].rename(columns={'카니발(휠체어)': 'value'})
        carnivalWheel_df['type'] = '카니발(휠체어)'

        IONIQ5_df = plot_df[['day', '아이오닉5']].rename(columns={'아이오닉5': 'value'})
        IONIQ5_df['type'] = '아이오닉5'

        carnivalReg_df_ma = plot_df[['day', '카니발(일반)-추세']].rename(columns={'카니발(일반)-추세': 'value'})
        carnivalReg_df_ma['type'] = '카니발(일반)-추세'

        carnivalWheel_df_ma = plot_df[['day', '카니발(휠체어)-추세']].rename(columns={'카니발(휠체어)-추세': 'value'})
        carnivalWheel_df_ma['type'] = '카니발(휠체어)-추세'

        IONIQ5_df_ma = plot_df[['day', '아이오닉5-추세']].rename(columns={'아이오닉5-추세': 'value'})
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
            x=alt.X('day:O', title='Day', axis=alt.Axis(labelAngle=0)),
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

    chart_Actual_use_time = generating_chart(last_summary_Actual_use_time_df, ma_carnivalReg_Actual_use_time, ma_carnivalWheel_Actual_use_time, ma_IONIQ5_Actual_use_time, '#006ACD', '#FFB1B0', '#7CBEF2', '서비스 이용시간', '분')
    chart_pickup_delay = generating_chart(last_summary_pickup_delay_df, ma_carnivalReg_pickup_delay, ma_carnivalWheel_pickup_delay, ma_IONIQ5_pickup_delay, '#006ACD', '#FFB1B0', '#7CBEF2', '차량 도착 정시성', '분')
    chart_Actual_operation_delay = generating_chart(last_summary_operation_delay_df, ma_carnivalReg_operation_delay, ma_carnivalWheel_operation_delay, ma_IONIQ5_operation_delay, '#006ACD', '#FFB1B0', '#7CBEF2', '차량 주행 정시성', '분')

    return chart_Actual_use_time, chart_pickup_delay, chart_Actual_operation_delay, [mean_last_Actual_use_time, mean_past_Actual_use_time, mean_last_pickup_delay, mean_past_pickup_delay, mean_last_operation_delay, mean_past_operation_delay]
