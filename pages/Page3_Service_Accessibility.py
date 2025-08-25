import streamlit as st
import streamlit.components.v1 as components
import altair as alt
import numpy as np
import json, geopandas as gpd, pandas as pd
from Modules.P3_Kakao_population_loader import return_last_population_df, return_last_past_population_df
from utils.maps import polygons_map_html, default_map_html
import datetime as dt

mode = st.secrets["mode"]

if mode == 'static':
    st.session_state.current_time = dt.datetime.strptime(st.secrets["current_time_test"], "%Y-%m-%d %H:%M")
elif mode == 'dynamic':
    st.session_state.current_time = dt.datetime.now()
st.session_state.current_time = st.session_state.current_time.replace(second=0, microsecond=0)

st.session_state.temp_interval = st.secrets["previous_days"]
st.session_state.PAGES_URL = "https://healthdesignmobility.github.io/move/kakao_map/"
st.session_state.KAKAO_API_KEY = st.secrets["kakao_api_key"]

current_time  = st.session_state.current_time
temp_interval = st.session_state.temp_interval
PAGES_URL     = st.session_state.PAGES_URL
kakao_api_key = st.session_state.KAKAO_API_KEY

st.header(f"♿ MOVE / 서비스 접근성")
st.markdown('---')

# 서비스 지역 & ODD 지역 면적 랜덤 설정 -> secrets.toml 파일 참고
service_population = st.secrets["service_population"]
ODD_population = st.secrets["ODD_population"]
service_area = st.secrets["service_area"]
ODD_area = st.secrets["ODD_area"]

formatted_service_population = f"{service_population:,}"
formatted_ODD_population = f"{ODD_population:,}"
formatted_service_area = f"{service_area:,}"
formatted_ODD_area = f"{ODD_area:,}"

col = st.columns((1, 1, 1), gap='large')
with col[0]:
    st.markdown('#### **|** 서비스 수혜율 (%)')
    col_sub = st.columns((0.3, 1), gap='small')
    with col_sub[0]:
        st.metric(label="서비스 수혜율", value=int(ODD_population/service_population * 100), delta=3.6, label_visibility='hidden')
        st.markdown('###### 지난 1년 대비')
    with col_sub[1]:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        st.markdown(f"""
            <div style='font-size: 16px; color: gray;'>
                서비스 지역 인구수: {formatted_service_population} 명<br>
                ODD 범위권 인구수: {formatted_ODD_population} 명
            </div>
        """, unsafe_allow_html=True)

with col[1]:
    st.markdown('#### **|** 서비스 커버리지 (%)')
    col_sub = st.columns((0.3, 1), gap='small')
    with col_sub[0]:
        st.metric(label="서비스 커버리지", value=int(ODD_area/service_area * 100), delta=2.1, label_visibility='hidden')
        st.markdown('###### 지난 1년 대비')
    with col_sub[1]:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        st.markdown(f"""
            <div style='font-size: 16px; color: gray;'>
                서비스 지역 면적: {formatted_service_area} m²<br>
                ODD 범위권 면적: {formatted_ODD_area} m²
            </div>
        """, unsafe_allow_html=True)

st.markdown('---')

# 임의의 숫자 선정: ex) 서비스 지역에 총 몇명씩 살고 있다.
total_people_count = st.secrets["total_people_count"] # 총 사람 수
total_diabled_count = st.secrets["total_diabled_count"] # 장애인 수
total_olderadults_count = st.secrets["total_olderadults_count"] # 고령자 수

last_df, past_df, result_list = return_last_past_population_df(current_time, temp_interval, total_people_count, total_diabled_count, total_olderadults_count)

col = st.columns((1, 1, 1), gap='large')
with col[0]:
    st.markdown('#### **|** 서비스 이용률 (%)')
    col_sub = st.columns((0.3, 1), gap='small')
    with col_sub[0]:
        st.metric(label="서서비스 이용률(%)", value=int(result_list[0]), delta=int(result_list[0] - result_list[1]), label_visibility='hidden')
        st.markdown('###### 지난 {}일 평균'.format(temp_interval))
    with col_sub[1]:
        temp_last_df = last_df[["day","total_count"]]
        temp_past_df = past_df[["day","total_count"]]
        temp_last_df["day"] = temp_last_df["day"].astype(int)
        temp_past_df["day"] = temp_past_df["day"].astype(int)
        merged_df = pd.concat([temp_past_df, temp_last_df], ignore_index=True)
        merged_df["day"] = pd.to_numeric(merged_df["day"], errors="coerce")
        merged_df = merged_df.sort_values("day").reset_index(drop=True)
        window_size = int(np.round(len(temp_last_df) / 2, 0))
        merged_df["이동평균"] = merged_df["total_count"].iloc[::-1].rolling(window=window_size, min_periods=1).mean().iloc[::-1]
        moving_avg_df = merged_df[merged_df["day"].isin(temp_last_df["day"])].copy()
        area = alt.Chart(temp_last_df).mark_area(opacity=0.8, color="#173F5F").encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("total_count:Q", title="서비스 이용률 (%)")
        )
        line = alt.Chart(moving_avg_df).mark_line(color='#ED553B', strokeWidth=3, strokeDash=[4, 2],
        point=alt.OverlayMarkDef(
            filled=True,
            fill='#ED553B',
            stroke='#ED553B',
            strokeWidth=0.5,
            size=50
        )).encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("이동평균:Q")
        )
        chart = (area + line).properties(height=200)
        st.altair_chart(chart, use_container_width=True)

with col[1]:
    st.markdown('#### **|** 장애인 이용률 (%)')
    col_sub = st.columns((0.3, 1), gap='small')
    with col_sub[0]:
        st.metric(label="장애인 이용률(%)", value=int(result_list[2]), delta=int(result_list[2] - result_list[3]), label_visibility='hidden')
        st.markdown('###### 지난 {}일 평균'.format(temp_interval))
    with col_sub[1]:
        temp_last_df = last_df[["day","disabled_count"]]
        temp_past_df = past_df[["day","disabled_count"]]
        temp_last_df["day"] = temp_last_df["day"].astype(int)
        temp_past_df["day"] = temp_past_df["day"].astype(int)
        merged_df = pd.concat([temp_past_df, temp_last_df], ignore_index=True)
        merged_df["day"] = pd.to_numeric(merged_df["day"], errors="coerce")
        merged_df = merged_df.sort_values("day").reset_index(drop=True)
        window_size = int(np.round(len(temp_last_df) / 2, 0))
        merged_df["이동평균"] = merged_df["disabled_count"].iloc[::-1].rolling(window=window_size, min_periods=1).mean().iloc[::-1]
        moving_avg_df = merged_df[merged_df["day"].isin(temp_last_df["day"])].copy()
        area = alt.Chart(temp_last_df).mark_area(opacity=0.7, color="#3CAEA3").encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("disabled_count:Q", title="장애인 이용률 (%)")
        )
        line = alt.Chart(moving_avg_df).mark_line(color='#ED553B', strokeWidth=3, strokeDash=[4, 2],
        point=alt.OverlayMarkDef(
            filled=True,
            fill='#ED553B',
            stroke='#ED553B',
            strokeWidth=0.5,
            size=50
        )).encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("이동평균:Q")
        )
        chart = (area + line).properties(height=200)
        st.altair_chart(chart, use_container_width=True)

with col[2]:
    st.markdown('#### **|** 고령자 이용률 (%)')
    col_sub = st.columns((0.3, 1), gap='small')
    with col_sub[0]:
        st.metric(label="고령자 이용률(%)", value=int(result_list[4]), delta=int(result_list[4] - result_list[5]), label_visibility='hidden')
        st.markdown('###### 지난 {}일 평균'.format(temp_interval))
    with col_sub[1]:
        temp_last_df = last_df[["day","older_adults_count"]]
        temp_past_df = past_df[["day","older_adults_count"]]
        temp_last_df["day"] = temp_last_df["day"].astype(int)
        temp_past_df["day"] = temp_past_df["day"].astype(int)
        merged_df = pd.concat([temp_past_df, temp_last_df], ignore_index=True)
        merged_df["day"] = pd.to_numeric(merged_df["day"], errors="coerce")
        merged_df = merged_df.sort_values("day").reset_index(drop=True)
        window_size = int(np.round(len(temp_last_df) / 2, 0))
        merged_df["이동평균"] = merged_df["older_adults_count"].iloc[::-1].rolling(window=window_size, min_periods=1).mean().iloc[::-1]
        moving_avg_df = merged_df[merged_df["day"].isin(temp_last_df["day"])].copy()
        area = alt.Chart(temp_last_df).mark_area(opacity=0.7, color="#F6D55C").encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("older_adults_count:Q", title="고령자 이용률 (%)")
        )
        line = alt.Chart(moving_avg_df).mark_line(color='#ED553B', strokeWidth=3, strokeDash=[4, 2],
        point=alt.OverlayMarkDef(
            filled=True,
            fill='#ED553B',
            stroke='#ED553B',
            strokeWidth=0.5,
            size=50
        )).encode(
            x=alt.X("day:Q", title="Day", scale=alt.Scale(nice=True), axis=alt.Axis(format=".0f")),
            y=alt.Y("이동평균:Q")
        )
        chart = (area + line).properties(height=200)
        st.altair_chart(chart, use_container_width=True)

st.markdown('---')
options = {
    "최근 1일": 1,
    "최근 3일": 3,
    "최근 7일": 7,
    "최근 14일": 14
}
option_labels = list(options.keys())
default_index = option_labels.index("최근 7일")
selected_label = st.selectbox(f"🕒 현재 시간: {current_time} ", option_labels, index=default_index)
selected_days = options[selected_label]

col = st.columns((1, 1, 1), gap='large')
with col[0]:
    st.markdown('#### **|** 서비스 이용률 지도')
with col[1]:
    st.markdown('#### **|** 장애인 이용률 지도')
with col[2]:
    st.markdown('#### **|** 고령자 이용률 지도')

population_df = return_last_population_df(current_time=current_time, days_interval=selected_days)

col = st.columns((1, 1, 1), gap='large')
with col[0]:
    if population_df is not None and not population_df.empty:
        map_html = polygons_map_html(kakao_api_key, population_df, 'total_percent')
    else:
        map_html = default_map_html(kakao_api_key)
    components.html(map_html, height=750)
with col[1]:
    if population_df is not None and not population_df.empty:
        map_html = polygons_map_html(kakao_api_key, population_df, 'disabled_percent')
    else:
        map_html = default_map_html(kakao_api_key)
    components.html(map_html, height=750)
with col[2]:
    if population_df is not None and not population_df.empty:
        map_html = polygons_map_html(kakao_api_key, population_df, 'olderadults_percent')
    else:
        map_html = default_map_html(kakao_api_key)
    components.html(map_html, height=750)