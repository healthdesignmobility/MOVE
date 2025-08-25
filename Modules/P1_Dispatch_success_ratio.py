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
from pathlib import Path
import streamlit as st

def parse_onboarding_time(t):
    try:
        t_str = str(int(t)).zfill(12)
        return datetime.strptime(t_str, "%Y%m%d%H%M")
    except:
        return np.nan

HERE = Path(__file__).resolve().parent        # .../MOVE/Modules
ROOT = HERE.parent                            # .../MOVE

request_df = pd.read_csv(ROOT/"data"/"request_df.csv")

def return_dispatch_ratio(current_time, days_interval, sevice_Type=[1, 2]):

    request_df['messageTime'] = pd.to_datetime(request_df['messageTime'], unit='ms', utc=True)
    request_df['messageTime'] = request_df['messageTime'].dt.tz_convert('Asia/Seoul')

    temp_request_df = request_df[request_df['messageTime'] < pd.to_datetime(current_time, utc=True).tz_convert('Asia/Seoul')]
    temp_request_df = temp_request_df[temp_request_df['messageTime'] >= pd.to_datetime(current_time - dt.timedelta(days=days_interval*2), utc=True).tz_convert('Asia/Seoul')].reset_index(drop=True)
    temp_request_df['Day'] = [(temp_request_df['messageTime'][i] - pd.to_datetime(current_time, utc=True).tz_convert('Asia/Seoul')).days for i in range(len(temp_request_df))]
    temp_request_df = temp_request_df[['Day', 'reserveType', 'confirmCheck', 'serviceType']]
    temp_request_df = temp_request_df[temp_request_df['serviceType'].isin(sevice_Type)]

    past_df = temp_request_df[temp_request_df['Day'] < -days_interval].reset_index(drop=True)
    last_df = temp_request_df[temp_request_df['Day'] >= -days_interval].reset_index(drop=True)

    last_success_rate = np.round(np.nansum(last_df['confirmCheck']) / len(last_df) * 100, 2)
    past_success_rate = np.round(np.nansum(past_df['confirmCheck']) / len(past_df) * 100, 2)

    def summarize_df(df):
        temp_df = df[df['reserveType'] == 1]
        total_counts = temp_df.groupby('Day').size()
        confirm_counts = temp_df[temp_df['confirmCheck'] == 1].groupby('Day').size()
        confirm_rate_real = (confirm_counts / total_counts)
        temp_df = df[df['reserveType'] == 2]
        total_counts = temp_df.groupby('Day').size()
        confirm_counts = temp_df[temp_df['confirmCheck'] == 1].groupby('Day').size()
        confirm_rate_pre = (confirm_counts / total_counts)
        
        summary_df = pd.DataFrame({
            "실시간": np.round(confirm_rate_real*100, 2),
            "사전예약": np.round(confirm_rate_pre*100, 2)
        }).reset_index().rename(columns={"Day": "day"})
        return summary_df

    past_summary_df = summarize_df(past_df)
    last_summary_df = summarize_df(last_df)

    window_size = math.ceil(days_interval / 2)
    combined_df = pd.concat([past_summary_df, last_summary_df], ignore_index=True).sort_values('day').reset_index(drop=True)

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

    target_days_success = last_summary_df['day'].values
    ma_real = compute_centered_moving_average(combined_df, '실시간', target_days_success, window_size)
    ma_reserved = compute_centered_moving_average(combined_df, '사전예약', target_days_success, window_size)

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

        chart = base.encode(
            y=alt.Y('value:Q', axis=alt.Axis(title=f'배차 성공률 ({unit})')),
            opacity=alt.condition(
                alt.FieldOneOfPredicate(field='type', oneOf=['실시간-추세', '사전예약-추세']),
                alt.value(0.5),
                alt.value(1.0)
            )
        ).mark_line(point=True).properties(
            width=300,
            height=250
        )
        return chart

    chart_success = generating_chart(last_summary_df, ma_real, ma_reserved, '#ED553B', '#3CAEA3', '%')

    return chart_success, [last_success_rate, past_success_rate]