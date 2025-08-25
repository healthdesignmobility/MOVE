import streamlit as st
import streamlit.components.v1 as components


st.header(f"♿ MOVE / 실시간 시뮬레이터")
st.markdown('---')

st.subheader("🔍 실시간 시뮬레이터 시각화")
components.iframe("https://drt-simulator.vercel.app/", height=800, scrolling=True)