import streamlit as st
import datetime as dt
import mysql.connector
import altair as alt
import streamlit_option_menu
from streamlit_option_menu import option_menu

# ✅ set_page_config는 가장 먼저!
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

# 공통 초기화 (세션 키)
mode = st.secrets.get("mode", "static")
if "current_time" not in st.session_state:
    st.session_state.current_time = (
        dt.datetime.strptime(st.secrets["current_time_test"], "%Y-%m-%d %H:%M")
        if mode == "static" else dt.datetime.now()
    ).replace(second=0, microsecond=0)
st.session_state.setdefault("temp_interval", st.secrets.get("previous_days", 7))
st.session_state.setdefault("KAKAO_API_KEY", st.secrets.get("kakao_api_key", ""))

alt.themes.enable("dark")

st.session_state.temp_interval = st.secrets["previous_days"]
st.session_state.PAGES_URL = "https://healthdesignmobility.github.io/move/kakao_map/"
st.session_state.KAKAO_API_KEY = st.secrets["kakao_api_key"]

current_time  = st.session_state.current_time
temp_interval = st.session_state.temp_interval
PAGES_URL     = st.session_state.PAGES_URL
kakao_api_key = st.session_state.KAKAO_API_KEY



# 페이지 별로 라우팅
from configPages import Page1_User_Experience as P1
from configPages import Page2_Operation_Efficiency as P2
from configPages import Page3_Service_Accessibility as P3
from configPages import Page4_Real_Time_Simulator as P4
from configPages import Page5_Message_Monitoring as P5

PAGE_MAP = {
    "이용자 경험":         P1.render,
    "운영 효율":           P2.render,
    "서비스 접근성":        P3.render,
    "실시간 시뮬레이터":    P4.render,
    "메세지 모니터링":      P5.render,
}

# 사이드바
with st.sidebar:
    
    selected = option_menu(
        menu_title="MOVE Dashboard",
        options=list(PAGE_MAP.keys()),
        icons=["emoji-smile", "graph-up", "geo-alt", "map", "chat-dots"],
        menu_icon="cast",
        orientation="vertical",
        default_index=0,
        styles={
            "icon": {"color": "#ffffff", "font-size": "20px"},
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#000000"},
            "nav-link-selected": {"background-color": "#468186", "font-weight": "bold", "color": "#ffffff"},
        },
    )
    st.markdown("<div style='height:570px;'></div>", unsafe_allow_html=True)
    st.markdown("---")
    st.caption(f"📊 데이터 출처: 한국과학기술원 건설및환경공학과")
    st.caption(f"🕒 업데이트: {current_time}")
    st.caption("🛠️ 버전: v1.3.0")
    st.caption("📬 문의: jungyubaik@kaist.ac.kr")
    st.info("⚠️ 시범 운영 중입니다.\n의견은 언제든 환영합니다!")

# 페이지 렌더
PAGE_MAP[selected](
    current_time=current_time,
    temp_interval=temp_interval,
    PAGES_URL = PAGES_URL,
    kakao_api_key=kakao_api_key
)