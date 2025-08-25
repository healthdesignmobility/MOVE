import streamlit as st
import datetime as dt
import mysql.connector
import altair as alt
import streamlit_option_menu
from streamlit_option_menu import option_menu

mode = st.secrets["mode"]

if mode == 'static':
    st.session_state.current_time = dt.datetime.strptime(st.secrets["current_time_test"], "%Y-%m-%d %H:%M")
elif mode == 'dynamic':
    st.session_state.current_time = dt.datetime.now()
st.session_state.current_time = st.session_state.current_time.replace(second=0, microsecond=0)

st.session_state.temp_interval = st.secrets["previous_days"]
st.session_state.PAGES_URL = "https://healthdesignmobility.github.io/move/kakao_map/"
st.session_state.KAKAO_API_KEY = st.secrets["kakao_api_key"]

# 페이지 정의
st.set_page_config(
    page_title="MOVE Dashboard",
    page_icon="♿",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        'Get Help': 'https://www.healthdesign.kaist.ac.kr/',
        'Report a bug': "https://www.healthdesign.kaist.ac.kr/",
        'About': "# 교통약자 이동지원 시스템\n이 대시보드는 교통약자의 이동 패턴을 분석하고, 실시간 지원 정보를 제공합니다."
        }
    )
alt.themes.enable("dark")

########## 여기부터 대시보드 제작 ##########
# 사이드바 정의
with st.sidebar:
    selected = option_menu(
        menu_title = "MOVE Dashboard",
        options = ["이용자 경험", "운영 효율", "서비스 접근성", "실시간 시뮬레이터", "메세지 모니터링"],
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
    st.sidebar.caption("🕒 업데이트: {}".format(st.session_state.current_time))
    st.sidebar.caption("🛠️ 버전: v1.3.0")
    st.sidebar.caption("📬 문의: jungyubaik@kaist.ac.kr")
    st.sidebar.info("⚠️ 시범 운영 중입니다.\n의견은 언제든 환영합니다!")
