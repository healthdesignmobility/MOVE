import streamlit as st
import numpy as np
import pandas as pd
import snowflake.connector
import streamlit_option_menu
from streamlit_option_menu import option_menu
import altair as alt
import streamlit.components.v1 as components
import datetime as dt
from datetime import datetime, timedelta
from collections import defaultdict
import json
import geopandas as gpd
import plotly.graph_objects as go
   
# 정의해둔 함수 import
from Modules.N1_Kakao_data_loader import return_pickup_station_count
from Modules.N2_Kakao_realtime_loader import return_realtime_operations
from Modules.P3_Kakao_population_loader import return_last_population_df, return_last_past_population_df
from Modules.P2_Kakao_link_loader import return_link_frequency
from Modules.P2_Donuts import return_reserveType, return_serviceType, operation_vehicle, return_failinfo
from Modules.P1_Kakao_service_waiting import return_waitings
from Modules.P1_Dispatch_success_ratio import return_dispatch_ratio
from Modules.P1_sevice_arrival_operation_times import return_graphs_and_stats
from Modules.P2_operation_percentage import return_boaring_rates
from Modules.P2_service_capacity import return_service_capacity
from Modules.P2_boarding_vehicle_rate import return_boaring_vehicle_rates


############# 기본 파라미터 설정 #############

# 시간 고정하고 싶을 때
current_time = dt.datetime.strptime("2025-05-05 14:32", "%Y-%m-%d %H:%M")

# 현재 시간을 기준으로
# current_time = datetime.now()

current_time = current_time.replace(second=0, microsecond=0)

# 전체 그래프에서: 최근 n일과 이전 n일을 비교
temp_interval = 7

# 페이지 정의
st.set_page_config(
    page_title="교통약자 이동지원 대시보드",
    page_icon="♿",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        'Get Help': 'https://www.healthdesign.kaist.ac.k'
        'r/',
        'Report a bug': "mailto:support@yourdomain.com",
        'About': "# 교통약자 이동지원 시스템\n이 대시보드는 교통약자의 이동 패턴을 분석하고, 실시간 지원 정보를 제공합니다."
        }
    )
alt.themes.enable("dark")


############# 카카오맵 연동 및 표출 함수 정의 #############

# 카카오맵 API key
kakao_api_key = "fc1c450fc44c5cda47534a556fe9b4f2"

# 카카오맵 마커(포인트) 크기 정규화하는 함수 정의
def normalize_weights(locations, min_size=20, max_size=40):
    weights = [loc["weight"] for loc in locations]
    min_w, max_w = min(weights), max(weights)
    for loc in locations:
        norm = (loc["weight"] - min_w) / (max_w - min_w) if max_w > min_w else 0.5
        scaled = norm * (max_size - min_size) + min_size
        loc["scaled_weight"] = round(scaled, 2)
    return locations

# 기본 지도 표출: 표출할 정보가 없을 때 활용
def default_map_html(api_key):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map</title>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={api_key}"></script>
    </head>
    <body>
        <div id="map" style="width:95%;height:600px;"></div>
        <script>
            if (typeof kakao !== 'undefined') {{
                var mapContainer = document.getElementById('map'), 
                mapOption = {{ 
                    center: new kakao.maps.LatLng(36.502306, 127.264738),
                    level: 4
                }};
                var map = new kakao.maps.Map(mapContainer, mapOption); 

            }} else {{
                document.body.innerHTML = "<h3>Kakao Maps API 로드 실패</h3>";
            }}
        </script>
    </body>
    </html>
    """
    return html_code

# Page 1. 서비스 대기 시간 지도 마커 표출
# Page 3. 출발 정류장 이용 빈도 마커 표출
def create_map_html(api_key, locations):
    locations_js = ""
    for loc in locations:
        locations_js += f"""
        var markerPosition = new kakao.maps.LatLng({loc['lat']}, {loc['lng']});
        var markerImage = new kakao.maps.MarkerImage(
            'http://t1.daumcdn.net/localimg/localimages/07/2018/pc/img/marker_spot.png',
            new kakao.maps.Size({loc['scaled_weight']}, {loc['scaled_weight']*1.35}),
            {{
                offset: new kakao.maps.Point({loc['scaled_weight']/2}, {loc['scaled_weight']*1.35})
            }}
        );
        var marker = new kakao.maps.Marker({{
            position: markerPosition,
            image: markerImage,
            title: "{loc['station']}: {loc['weight']}"
        }});
        marker.setMap(map);
        """
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map</title>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={api_key}"></script>
    </head>
    <body>
        <div id="map" style="width:95%;height:600px;"></div>
        <script>
            if (typeof kakao !== 'undefined') {{
                var mapContainer = document.getElementById('map'), 
                mapOption = {{ 
                    center: new kakao.maps.LatLng(36.502306, 127.264738),
                    level: 4
                }};
                var map = new kakao.maps.Map(mapContainer, mapOption); 
                {locations_js}
            }} else {{
                document.body.innerHTML = "<h3>Kakao Maps API 로드 실패</h3>";
            }}
        </script>
    </body>
    </html>
    """
    return html_code

# Page 1. 실시간 운행 정보 표출 (30분 전/후 포함 총 운행 모두 표출)
def create_map_routes_html(api_key, routes, pickup_stations):
    color_segments = defaultdict(list)
    for route in routes:
        if not route:
            continue
        current_color = route[0]['color']
        current_segment = [route[0]]
        for point in route[1:]:
            if point['color'] == current_color:
                current_segment.append(point)
            else:
                if len(current_segment) >= 2:
                    color_segments[current_color].append(current_segment)
                current_segment = [point]
                current_color = point['color']
        if len(current_segment) >= 2:
            color_segments[current_color].append(current_segment)

    color_counts = {color: len(segments) for color, segments in color_segments.items()}
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    routes_js = ""
    for color, _ in sorted_colors:
        for segment in color_segments[color]:
            path_js = ",\n".join([
                f"new kakao.maps.LatLng({pt['lat']}, {pt['lng']})"
                for pt in segment
            ])
            routes_js += f"""
            var polyline = new kakao.maps.Polyline({{
                path: [{path_js}],
                strokeWeight: 3,
                strokeColor: '{color}',
                strokeOpacity: 0.9,
                strokeStyle: 'shortdash'
            }});
            polyline.setMap(map);
            """

    pickup_js = ""
    for i, loc in enumerate(pickup_stations):
        pickup_js += f"""

        var markerPosition = new kakao.maps.LatLng({loc['lat']}, {loc['lng']});

        var markerImage = new kakao.maps.MarkerImage(
            'http://t1.daumcdn.net/localimg/localimages/07/2018/pc/img/marker_spot.png',
            new kakao.maps.Size({30}, {30*1.35}),
            {{
                offset: new kakao.maps.Point({30/2}, {30*1.35})
            }}
        );
        var marker = new kakao.maps.Marker({{
            position: markerPosition,
            image: markerImage, // 이미지 설정
            title: "탑승순서: {i+1}\\n탑승시간: {loc['onboardingTime']}\\n승객 수: {loc['passengerCount']}\\n휠체어 수: {loc['wheelchairCount']}\\n서비스 유형: {loc['serviceType']} "
        }});
        marker.setMap(map);
        """

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map</title>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={api_key}"></script>
    </head>
    <body>
        <div id="map" style="width:95%;height:600px;"></div>
        <script>
            if (typeof kakao !== 'undefined') {{
                var mapContainer = document.getElementById('map'), 
                mapOption = {{ 
                    center: new kakao.maps.LatLng(36.502306, 127.264738),
                    level: 4
                }};
                var map = new kakao.maps.Map(mapContainer, mapOption); 
                {routes_js}
                {pickup_js}
            }} else {{
                document.body.innerHTML = "<h3>Kakao Maps API 로드 실패</h3>";
            }}
        </script>
    </body>
    </html>
    """
    return html_code

# Page 2. 운행 경로 빈도 표출
def create_map_links_html(api_key, link_df):
    max_count = link_df['count'].max()
    min_count = link_df['count'].min()
    norm = lambda c: int(np.interp(c, [min_count, max_count], [5, 30]))
    routes_js = ""
    for _, row in link_df.iterrows():
        weight = norm(row['count'])
        opacity = float(np.interp(row['count'], [min_count, max_count], [0.5, 1.0]))
        path_js = f"""
        new kakao.maps.LatLng({row['start_lat']}, {row['start_lon']}),
        new kakao.maps.LatLng({row['end_lat']}, {row['end_lon']})
        """
        routes_js += f"""
        var polyline = new kakao.maps.Polyline({{
            path: [{path_js}],
            strokeWeight: {weight},
            strokeColor: '#002642',
            strokeOpacity: {opacity},
            strokeStyle: 'solid'
        }});
        polyline.setMap(map);
        """
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map</title>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={api_key}"></script>
    </head>
    <body>
        <div id="map" style="width:95%;height:600px;"></div>
        <script>
            if (typeof kakao !== 'undefined') {{
                var mapContainer = document.getElementById('map'), 
                mapOption = {{ 
                    center: new kakao.maps.LatLng(36.502306, 127.264738),
                    level: 4
                }};
                var map = new kakao.maps.Map(mapContainer, mapOption); 
                {routes_js}
            }} else {{
                document.body.innerHTML = "<h3>Kakao Maps API 로드 실패</h3>";
            }}
        </script>
    </body>
    </html>
    """
    return html_code

# Page 3. 이용률 지도 그리드에 색상 넣어 표출
def create_map_with_geojson(api_key, pop_df, opacity_col):
    features = []
    for _, row in pop_df.iterrows():
        if row["geometry"] is None:
            continue
        geometry = json.loads(gpd.GeoSeries([row["geometry"]]).to_json())["features"][0]["geometry"]
        properties = {
            "opacity_value": min(max(float(row.get(opacity_col, 0)), 0), 1)
        }
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties
        })
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map with Polygons</title>
        <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={api_key}"></script>
    </head>
    <body>
        <div id="map" style="width:100%;height:700px;"></div>
        <script>
            var mapContainer = document.getElementById('map'),
                mapOption = {{
                    center: new kakao.maps.LatLng(36.502306, 127.264738),
                    level: 5
                }};
            var map = new kakao.maps.Map(mapContainer, mapOption);
            var geojson = {json.dumps(geojson)};
            geojson.features.forEach(function(feature) {{
                var coords = feature.geometry.coordinates[0];
                var path = coords.map(function(coord) {{
                    return new kakao.maps.LatLng(coord[1], coord[0]);
                }});
                var polygon = new kakao.maps.Polygon({{
                    path: path,
                    strokeWeight: 1,
                    strokeColor: '#000000',
                    strokeOpacity: 0.1,
                    fillColor: '#ED553B',
                    fillOpacity: feature.properties.opacity_value
                }});
                polygon.setMap(map);
            }});
        </script>
    </body>
    </html>
    """
    return html_code


########## 여기부터 대시보드 제작 ##########

# 사이드바 정의
with st.sidebar:
    selected = option_menu(
        menu_title = "교통약자 이동지원 모빌리티 서비스",
        options = ["이용자 경험","운영 효율","서비스 접근성", "시뮬레이션 시각화", "메세지 모니터링"],
        icons=["emoji-smile", "graph-up", "geo-alt", "map", "chat-dots"],
        menu_icon = "cast",
        orientation="vertical",
        default_index = 0,
        styles = {
                "icon": {"color": "#ffffff", "font-size": "20px"}, 
                "nav-link": {
                    "font-size": "16px", 
                    "text-align": "left", 
                    "margin":"0px", 
                    "--hover-color": "#000000"
                },
                "nav-link-selected": {
                    "background-color": "#468186", 
                    "font-weight": "bold", 
                    "color": "#ffffff"
                }
        }
    )
    st.markdown("<div style='height:570px;'></div>", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.caption("📊 데이터 출처: 한국과학기술원 건설및환경공학과")
    st.sidebar.caption("🕒 업데이트: {}".format(current_time))
    st.sidebar.caption("🛠️ 버전: v1.0.0")
    st.sidebar.caption("📬 문의: jungyubaik@kaist.ac.kr")
    st.sidebar.info("⚠️ 시범 운영 중입니다.\n의견은 언제든 환영합니다!")

### Page 1. 이용자 경험

if selected == "이용자 경험":
    st.header(f"♿ 교통약자 이동지원 모빌리티 서비스 | {selected}")
    st.markdown('---')

    col = st.columns((1, 1, 1), gap='large')
    with col[0]:
        st.markdown('#### **|** 배차 소요시간 (초)')
        chart_response, _, _, stats, _ = return_waitings(current_time=current_time, days_interval=temp_interval, reserveType=None)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="배차 소요시간 (초)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_response, use_container_width=True)

    with col[1]:
        st.markdown('#### **|** 서비스 대기시간 (분)')
        _, chart_waiting, _, stats, _ = return_waitings(current_time=current_time, days_interval=temp_interval, reserveType=None)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="서비스 대기시간 (분)", value=np.round(stats[2]/60, 2), delta=np.round((stats[2] - stats[3])/60, 2), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_waiting, use_container_width=True)
            
    with col[2]:
        st.markdown('#### **|** 배차 성공률 (%)')
        chart_success, stats = return_dispatch_ratio(current_time=current_time, days_interval=temp_interval)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="배차 성공률 (%)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_success, use_container_width=True)

    st.markdown('---')

    col = st.columns((1, 1, 1), gap='large')
    with col[0]:
        st.markdown('#### **|** 서비스 이용시간 (분)')
        chart_Actual_use_time, _, _, stats = return_graphs_and_stats(current_time=current_time, days_interval=temp_interval)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="서비스 이용시간 (분)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_Actual_use_time, use_container_width=True)

    with col[1]:
        st.markdown('#### **|** 차량 도착 정시성 (분)')
        _, chart_pickup_delay, _, stats = return_graphs_and_stats(current_time=current_time, days_interval=temp_interval)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="차량 도착 정시성 (분)", value=np.round(stats[2], 1), delta=np.round((stats[2] - stats[3]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_pickup_delay, use_container_width=True)

    with col[2]:
        st.markdown('#### **|** 차량 주행 정시성 (분)')
        _, _, chart_Actual_operation_delay, stats = return_graphs_and_stats(current_time=current_time, days_interval=temp_interval)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="차량 주행 정시성 (분)", value=np.round(stats[4], 1), delta=np.round((stats[4] - stats[5]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_Actual_operation_delay, use_container_width=True)

    st.markdown('---')

    col = st.columns((1, 0.05, 1), gap='large')
    with col[0]:
        st.markdown('#### **|** 서비스 대기 시간 지도')
        options = {
            "사전 예약": 1,
            "실시간 예약": 2,
        }
        option_labels = list(options.keys())
        default_index = option_labels.index("실시간 예약")
        selected_label = st.selectbox(f"🕒 현재 시간: {current_time}", option_labels, index=default_index)
        _, _, _, _, locations = return_waitings(current_time=current_time, days_interval=temp_interval, reserveType=selected_label)
        if len(locations) > 0:
            map_html = create_map_html(kakao_api_key, normalize_weights(locations))
            components.html(map_html, height=700)
        else:
            map_html = default_map_html(kakao_api_key)
            components.html(map_html, height=700)

    with col[2]:
        st.markdown('#### **|** 실시간 운행 정보 - 30분 전후 포함')
        temp_oper_info, temp_routes, temp_pickup_info, temp_dropoff_info = return_realtime_operations(current_time, minutes_interval=30)
        selected_index = st.selectbox(f"🕒 현재 시간: {current_time} ", 
                                      range(len(temp_routes)), 
                                      format_func=lambda i: f"운행 #{i+1} | 차량 : {temp_oper_info[i][0]} - 운행시간 : 총 {int(temp_oper_info[i][1])}분 - 총 요청수 : {temp_oper_info[i][2]}개 - 총 승객수 : {temp_oper_info[i][3]} - 총 휠체어수 : {temp_oper_info[i][4]}")
        if len(temp_routes) > 0:
            temp_routes = [temp_routes[selected_index]]
            temp_pickup_info = temp_pickup_info[selected_index]
            map_html = create_map_routes_html(kakao_api_key, temp_routes, temp_pickup_info)
            components.html(map_html, height=700)
        else:
            map_html = default_map_html(kakao_api_key)
            components.html(map_html, height=700)


### Page 2. 운영 효율

if selected == "운영 효율":
    st.header(f"♿ 교통약자 이동지원 모빌리티 서비스 | {selected}")
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

    col = st.columns((1, 1, 1, 1), gap='large')
    with col[0]:
        st.markdown('#### **|** 예약 유형')
        temp_dispatch_df = return_reserveType(current_time=current_time, day_interval=selected_days)
        reserve_counts = temp_dispatch_df['reserveType'].value_counts().sort_index()
        reserve_labels = reserve_counts.index.tolist()
        hovertext = [
            f"{rtype}<br>{count}건<br>{count / reserve_counts.sum():.1%}"
            for rtype, count in reserve_counts.items()
        ]
        colors = ['#4A90E2', '#F5A623']
        fig = go.Figure(data=[go.Pie(
            labels=reserve_labels,
            values=reserve_counts.values,
            hole=.45,
            textinfo='percent',
            textfont=dict(size=20),
            hoverinfo='text',
            hovertext=hovertext,
            marker=dict(colors=colors, line=dict(color='white', width=0))
        )])
        fig.update_layout(
            annotations=[dict(text='예약<br>유형', x=0.5, y=0.5, font_size=24, showarrow=False)],
            showlegend=True,
            legend=dict(font=dict(size=18)),
            hoverlabel=dict(font_size=16),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col[1]:
        st.markdown('#### **|** 서비스 유형')
        temp_dispatch_df = return_serviceType(current_time=current_time, day_interval=selected_days)
        reserve_counts = temp_dispatch_df['serviceType'].value_counts().sort_index()
        reserve_labels = reserve_counts.index.tolist()
        hovertext = [
            f"{rtype}<br>{count}건<br>{count / reserve_counts.sum():.1%}"
            for rtype, count in reserve_counts.items()
        ]
        colors = ['#F6D55C', '#173F5F']
        fig = go.Figure(data=[go.Pie(
            labels=reserve_labels,
            values=reserve_counts.values,
            hole=.45,
            textinfo='percent',
            textfont=dict(size=20),
            hoverinfo='text',
            hovertext=hovertext,
            marker=dict(colors=colors, line=dict(color='white', width=0))
        )])
        fig.update_layout(
            annotations=[dict(text='서비스<br>유형', x=0.5, y=0.5, font_size=24, showarrow=False)],
            showlegend=True,
            legend=dict(font=dict(size=18)),
            hoverlabel=dict(font_size=16),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col[2]:
        st.markdown('#### **|** 운행 차량')
        temp_request_df = operation_vehicle(current_time=current_time, day_interval=selected_days)
        reserve_counts = temp_request_df['VehicleType'].value_counts().sort_index()
        reserve_labels = reserve_counts.index.tolist()
        hovertext = [
            f"{rtype}<br>{count}건<br>{count / reserve_counts.sum():.1%}"
            for rtype, count in reserve_counts.items()
        ]
        colors = ['#20639B', '#3CAEA3', '#F6D55C']
        fig = go.Figure(data=[go.Pie(
            labels=reserve_labels,
            values=reserve_counts.values,
            hole=.45,
            textinfo='percent',
            textfont=dict(size=20),
            hoverinfo='text',
            hovertext=hovertext,
            marker=dict(colors=colors, line=dict(color='white', width=0))
        )])
        fig.update_layout(
            annotations=[dict(text='운행<br>차량', x=0.5, y=0.5, font_size=24, showarrow=False)],
            showlegend=True,
            legend=dict(font=dict(size=18)),
            hoverlabel=dict(font_size=16),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col[3]:
        st.markdown('#### **|** 배차 거절 사유')
        temp_request_df = return_failinfo(current_time=current_time, day_interval=selected_days)
        reserve_counts = temp_request_df['failInfo_Main'].value_counts().sort_index()
        reserve_labels = reserve_counts.index.tolist()
        hovertext = [
            f"{rtype}<br>{count}건<br>{count / reserve_counts.sum():.1%}"
            for rtype, count in reserve_counts.items()
        ]
        colors = ['#840032', '#002642', '#E59500', '#02040F', '#253D5B']
        fig = go.Figure(data=[go.Pie(
            labels=reserve_labels,
            values=reserve_counts.values,
            hole=.45,
            textinfo='percent',
            textfont=dict(size=20),
            hoverinfo='text',
            hovertext=hovertext,
            marker=dict(colors=colors, line=dict(color='white', width=0))
        )])
        fig.update_layout(
            annotations=[dict(text='배차거절<br>사유', x=0.5, y=0.5, font_size=24, showarrow=False)],
            showlegend=True,
            legend=dict(font=dict(size=18)),
            hoverlabel=dict(font_size=16),
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown('---')

    col = st.columns((2, 0.2, 1.2), gap='small')
    with col[0]:
        st.markdown('#### **|** 실차 탑승시간 비율 (%)')
        chart_daily, chart_hourly, stats = return_boaring_rates(current_time=current_time, days_interval=temp_interval)

        col_sub = st.columns((0.3, 1, 1), gap='small')
        with col_sub[0]:
            st.metric(label="실차 운행률 (%)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_daily, use_container_width=True)
        with col_sub[2]:
            st.altair_chart(chart_hourly, use_container_width=True)
    
        st.markdown('---')

        st.markdown('#### **|** 실차 운행률 (%)')
        chart_daily, chart_hourly, stats = return_boaring_vehicle_rates(current_time=current_time, days_interval=temp_interval)
        
        col_sub = st.columns((0.3, 1, 1), gap='small')
        with col_sub[0]:
            st.metric(label="실차 운행률 (%)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_daily, use_container_width=True)
        with col_sub[2]:
            st.altair_chart(chart_hourly, use_container_width=True)

    with col[2]:
        st.markdown('#### **|** 승객 탑승률 (%)')
        chart_daily, stats = return_service_capacity(current_time=current_time, days_interval=temp_interval)
        col_sub = st.columns((0.3, 1), gap='small')
        with col_sub[0]:
            st.metric(label="승객 탑승률 (%)", value=np.round(stats[0], 1), delta=np.round((stats[0] - stats[1]), 1), label_visibility='hidden')
            st.markdown(f'###### 지난 {temp_interval}일 평균')
        with col_sub[1]:
            st.altair_chart(chart_daily, use_container_width=True)

    st.markdown('---')

    col = st.columns((1, 0.05, 1), gap='large')
    with col[0]:
        st.markdown('#### **|** 출발 정류장 이용 빈도')
        locations, last_log = return_pickup_station_count(current_time, days_interval=14)
        options = {
            "최근 1일": 1,
            "최근 3일": 3,
            "최근 7일": 7,
            "최근 14일": 14
        }
        option_labels = list(options.keys())
        default_index = option_labels.index("최근 3일")
        selected_label = st.selectbox(f"🕒 마지막 업데이트: {last_log}", option_labels, index=default_index)
        selected_days = options[selected_label]
        locations, last_log = return_pickup_station_count(current_time, days_interval=selected_days)
        if len(locations) > 0:
            map_html = create_map_html(kakao_api_key, normalize_weights(locations))
            components.html(map_html, height=700)
        else:
            map_html = default_map_html(kakao_api_key)
            components.html(map_html, height=700)

    with col[2]:
        st.markdown('#### **|** 운행 경로 빈도')
        temp_df, last_log = return_link_frequency(current_time, day_interval=14)
        options = {
            "최근 1일": 1,
            "최근 3일": 3,
            "최근 7일": 7,
            "최근 14일": 14
        }
        option_labels = list(options.keys())
        default_index = option_labels.index("최근 3일")
        selected_label = st.selectbox(f"🕒 마지막 업데이트: {last_log}", option_labels, index=default_index)
        selected_days = options[selected_label]
        link_df, last_log = return_link_frequency(current_time, day_interval=selected_days)
        map_html = create_map_links_html(kakao_api_key, link_df)
        components.html(map_html, height=700)

### Page 3. 서비스 접근성
if selected == "서비스 접근성":
    st.header(f"♿ 교통약자 이동지원 모빌리티 서비스 | {selected}")
    st.markdown('---')

    # 서비스 지역 & ODD 지역 면적 랜덤 설정
    service_population = 18642
    ODD_population = 12468
    service_area = 2154953
    ODD_area = 1654749
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
    total_people_count = 50 # 총 사람 수
    total_diabled_count = 28 # 장애인 수
    total_olderadults_count = 22 # 고령자 수

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
        map_html = create_map_with_geojson(kakao_api_key, population_df, 'total_percent')
        components.html(map_html, height=750)
    with col[1]:
        map_html = create_map_with_geojson(kakao_api_key, population_df, 'disabled_percent')
        components.html(map_html, height=750)
    with col[2]:
        map_html = create_map_with_geojson(kakao_api_key, population_df, 'olderadults_percent')
        components.html(map_html, height=750)

### Page 4. 시뮬레이션 시각화
if selected == "시뮬레이션 시각화":
    st.header(f"♿ 교통약자 이동지원 모빌리티 서비스 | {selected}")
    st.markdown('---')

        # 외부 시뮬레이터 삽입
    st.subheader("🔍 실시간 시뮬레이터 시각화")
    components.iframe("https://drt-simulator.vercel.app/", height=800, scrolling=True)


### Page 5. 메세지 모니터링
if selected == "메세지 모니터링":
    st.header(f"♿ 교통약자 이동지원 모빌리티 서비스 | {selected}")
    st.markdown('---')

    # 혜진: Kafka 메세지 모니터링 여기! - 정엽