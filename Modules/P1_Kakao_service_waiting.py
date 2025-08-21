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

reservetype_dict = {
    '사전 예약': 1,
    '실시간 예약' : 2,
}

def return_waitings(current_time, days_interval, reserveType=None):

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
    final_merged['messageTime'] = pd.to_datetime(final_merged['messageTime'], unit='ms', utc=True)
    final_merged['messageTime'] = final_merged['messageTime'].dt.tz_convert('Asia/Seoul')
    response_gaps = [(final_merged['messageTime'][i] - final_merged['messageTime_Request'][i]).total_seconds() for i in range(len(final_merged))]
    response_gaps = [x if x>0 else x+9*60*60 for x in response_gaps]
    final_merged['Response_time'] = response_gaps

    pickup_time_list = []
    for i in range(len(final_merged)):
        temp_pickup_time = final_merged['pickupTimeRequest'][i]
        try:
            time_str = str(temp_pickup_time)
            converted_time = dt.datetime.strptime("{}-{}-{} {}:{}".format(time_str[0:4], time_str[4:6], time_str[6:8], time_str[8:10], time_str[10:12]), "%Y-%m-%d %H:%M")
            pickup_time_list.append(converted_time)

        except:
            pickup_time_list.append(np.nan)

    final_merged['pickup_request_datetime'] = pickup_time_list

    final_merged['Waiting_Time'] = [(final_merged['onboarding_datetime'][i].tz_localize("Asia/Seoul") - final_merged['messageTime_Request'][i]).total_seconds()/60 if final_merged['reserveType'][i] == 2 else (final_merged['onboarding_datetime'][i].tz_localize("Asia/Seoul") - final_merged['pickup_request_datetime'][i].tz_localize("Asia/Seoul")).total_seconds()/60 for i in range(len(final_merged))]
    final_merged['StationID'] = final_merged['pickupStationID']
    temp_gdf = gdf[['StationID', 'StationLat', 'StationLon']]
    FFinal_merged = pd.merge(left = final_merged, right = temp_gdf, how = "inner", on = "StationID")
    FFinal_merged['Use_Time'] = [(FFinal_merged['dropoff_datetime'][i] - FFinal_merged['onboarding_datetime'][i]).total_seconds()/60 for i in range(len(FFinal_merged))]
    FFinal_merged = FFinal_merged[["Day", "reserveType", "VehicleType", "StationID", "StationLat", "StationLon", "Response_time", "Waiting_Time", "Use_Time"]]

    past_df = FFinal_merged[final_merged['Day'] < -days_interval].reset_index(drop=True)
    last_df = FFinal_merged[FFinal_merged['Day'] >= -days_interval].reset_index(drop=True)

    if reserveType is not None:
        last_df_type = last_df[last_df['reserveType'] == reservetype_dict[reserveType]]
        last_df_type = last_df_type.sort_values('StationLon', ascending=False).reset_index(drop=True)
        last_df_type['Waiting_Time'] = (last_df_type['Waiting_Time'])

        locations = [
            {"lat": row.StationLat, "lng": row.StationLon, "weight": np.round(row['Waiting_Time'], 1), "station": row['StationID']}
            for _, row in last_df_type.iterrows()
        ]
    else:
        last_df_type = None
        locations = None

    mean_last_response_time = np.nanmean(last_df['Response_time'])
    mean_past_response_time = np.nanmean(past_df['Response_time'])
    mean_last_waiting_time = np.nanmean(last_df['Waiting_Time'])
    mean_past_waiting_time = np.nanmean(past_df['Waiting_Time'])
    mean_last_use_time = np.nanmean(last_df['Use_Time'])
    mean_past_use_time = np.nanmean(past_df['Use_Time'])

    def summarize_df(df, temp_col):
        
        temp_df = df[df['reserveType'] == 1]
        all_days = sorted(temp_df["Day"].unique())
        response_real = temp_df.groupby("Day")[temp_col].mean().reindex(all_days, fill_value=0)

        temp_df = df[df['reserveType'] == 2]
        all_days = sorted(temp_df["Day"].unique())
        response_pre = temp_df.groupby("Day")[temp_col].mean().reindex(all_days, fill_value=0)
        
        summary_df = pd.DataFrame({
            "실시간": np.round(response_real, 1),
            "사전예약": np.round(response_pre, 1)
        }).reset_index().rename(columns={"Day": "day"})
        return summary_df

    last_summary_response_df = summarize_df(last_df, "Response_time")
    past_summary_response_df = summarize_df(past_df, "Response_time")
    last_summary_waiting_df = summarize_df(last_df, "Waiting_Time")
    past_summary_waiting_df = summarize_df(past_df, "Waiting_Time")
    last_summary_use_df = summarize_df(last_df, "Use_Time")
    past_summary_use_df = summarize_df(past_df, "Use_Time")

    window_size = math.ceil(days_interval / 2)

    combined_response_df = pd.concat([past_summary_response_df, last_summary_response_df], ignore_index=True).sort_values('day').reset_index(drop=True)
    combined_waiting_df = pd.concat([last_summary_waiting_df, past_summary_waiting_df], ignore_index=True).sort_values('day').reset_index(drop=True)
    combined_use_df = pd.concat([last_summary_use_df, past_summary_use_df], ignore_index=True).sort_values('day').reset_index(drop=True)

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

    target_days_response = last_summary_response_df['day'].values
    ma_real_response = compute_centered_moving_average(combined_response_df, '실시간', target_days_response, window_size)
    ma_reserved_response = compute_centered_moving_average(combined_response_df, '사전예약', target_days_response, window_size)

    target_days_waiting = last_summary_waiting_df['day'].values
    ma_real_waiting = compute_centered_moving_average(combined_waiting_df, '실시간', target_days_waiting, window_size)
    ma_reserved_waiting = compute_centered_moving_average(combined_waiting_df, '사전예약', target_days_waiting, window_size)

    target_days_use = last_summary_use_df['day'].values
    ma_real_use = compute_centered_moving_average(combined_use_df, '실시간', target_days_use, window_size)
    ma_reserved_use = compute_centered_moving_average(combined_use_df, '사전예약', target_days_use, window_size)

    def generating_chart(temp_df, ma_real, ma_reserved, temp_color_1, temp_color_2, unit):
        plot_df = temp_df.copy()
        plot_df['실시간-추세'] = ma_real
        plot_df['사전예약-추세'] = ma_reserved

        real_df = plot_df[['day', '실시간']].rename(columns={'실시간': 'value'})
        real_df['type'] = '실시간'
        real_df['y_axis'] = 'left'

        reserved_df = plot_df[['day', '사전예약']].rename(columns={'사전예약': 'value'})
        reserved_df['type'] = '사전예약'
        reserved_df['y_axis'] = 'right'

        real_ma_df = plot_df[['day', '실시간-추세']].rename(columns={'실시간-추세': 'value'})
        real_ma_df['type'] = '실시간-추세'
        real_ma_df['y_axis'] = 'left'

        reserved_ma_df = plot_df[['day', '사전예약-추세']].rename(columns={'사전예약-추세': 'value'})
        reserved_ma_df['type'] = '사전예약-추세'
        reserved_ma_df['y_axis'] = 'right'

        long_df = pd.concat([real_df, reserved_df, real_ma_df, reserved_ma_df])

        color_scale = alt.Scale(
            domain=['실시간', '실시간-추세', '사전예약', '사전예약-추세'],
            range=[temp_color_1, temp_color_1, temp_color_2, temp_color_2]
        )

        stroke_dash_scale = alt.Scale(
            domain=['실시간', '실시간-추세', '사전예약', '사전예약-추세'],
            range=[[0], [4, 4], [0], [4, 4]]
        )

        base = alt.Chart(long_df).encode(
            x=alt.X('day:O', title='Day', axis=alt.Axis(labelAngle=0)),
            color=alt.Color('type:N', scale=color_scale, legend=alt.Legend(
                title=None,
                orient='top',
                direction='vertical',
                columns=2,
                symbolSize=10,
                labelExpr="indexof(datum.label, '-추세') < 0 ? datum.label : '| 추세'"
            )),
            strokeDash=alt.StrokeDash('type:N', scale=stroke_dash_scale)
        )

        left_y = base.transform_filter(
            alt.datum.y_axis == 'left'
        ).encode(
            y=alt.Y('value:Q', axis=alt.Axis(title=f'실시간 ({unit})')),
            opacity=alt.condition(
                alt.FieldOneOfPredicate(field='type', oneOf=['실시간-추세']),
                alt.value(0.5),
                alt.value(1.0)
            )
        ).mark_line(point=True)

        right_y = base.transform_filter(
            alt.datum.y_axis == 'right'
        ).encode(
            y=alt.Y('value:Q', axis=alt.Axis(title=f'사전예약 ({unit})')),
            opacity=alt.condition(
                alt.FieldOneOfPredicate(field='type', oneOf=['사전예약-추세']),
                alt.value(0.5),
                alt.value(1.0)
            )
        ).mark_line(point=True)

        chart = alt.layer(left_y, right_y).resolve_scale(
            y='independent'
        ).properties(
            width=300,
            height=250
        )

        return chart

    chart_response = generating_chart(last_summary_response_df, ma_real_response, ma_reserved_response, '#ED553B', '#3CAEA3', '초')
    chart_waiting = generating_chart(last_summary_waiting_df, ma_real_waiting, ma_reserved_waiting, '#ED553B', '#3CAEA3', '분')
    chart_use = generating_chart(last_summary_use_df, ma_real_use, ma_reserved_use, '#ED553B', '#3CAEA3', '분')

    return chart_response, chart_waiting, chart_use, [mean_last_response_time, mean_past_response_time, mean_last_waiting_time, mean_past_waiting_time, mean_last_use_time, mean_past_use_time], locations