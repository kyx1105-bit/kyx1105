from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 제목
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide"
)

st.title("🎬 일별 박스오피스 조회")

# -----------------------------------------------------------------------------
# 2. 날짜 선택기 (KST 기준 어제까지만 선택 가능)
# -----------------------------------------------------------------------------
# 한국 표준시(KST) 기준으로 오늘과 어제 날짜 계산
kst_timezone = zoneinfo.ZoneInfo("Asia/Seoul")
now_in_kst = datetime.now(kst_timezone).date()
max_allowed_date = now_in_kst - timedelta(days=1)

# 달력(st.date_input)으로 날짜 선택 (최대 선택 가능 날짜: 어제)
selected_date = st.date_input(
    label="📅 조회할 날짜를 선택하세요",
    value=max_allowed_date,
    max_value=max_allowed_date,
    help="오늘 박스오피스는 아직 집계 전이므로 어제 날짜까지만 선택 가능합니다.",
)

# KOBIS API 형식(YYYYMMDD) 및 화면 표시용 문자열 변환
target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"📌 선택한 날짜: **{display_date}**")

# -----------------------------------------------------------------------------
# 3. KOBIS API 인증키 설정
# -----------------------------------------------------------------------------
api_key = "1c5660416dea1b03251c2612dd008243"

# -----------------------------------------------------------------------------
# 4. KOBIS API 데이터 요청
# -----------------------------------------------------------------------------
url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
params = {"key": api_key, "targetDt": target_dt}


@st.cache_data(ttl=3600)  # 1시간 동안 API 호출 결과 캐싱
def fetch_box_office_data(api_url, api_params):
    try:
        response = requests.get(api_url, params=api_params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error_type": "network", "details": str(e)}


data = fetch_box_office_data(url, params)

# -----------------------------------------------------------------------------
# 5. 예외 및 오류 처리
# -----------------------------------------------------------------------------
# 네트워크 오류 처리
if "error_type" in data and data["error_type"] == "network":
    st.error("🌐 **네트워크 통신 오류**")
    st.info(
        f"API 서버에 연결할 수 없습니다. 인터넷 연결 및 요청 주소를 확인해 주세요.\n\n세부 오류: `{data['details']}`"
    )
    st.stop()

# API 인증 오류 처리
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("🔑 **KOBIS API 인증 오류 (faultInfo)**")
    st.warning(
        f"""
        API 키 발급 상태 또는 키 문자열이 올바른지 확인해 주세요.
        
        - **오류 코드:** `{fault.get('errorCode', 'N/A')}`
        - **오류 메시지:** `{fault.get('message', '인증 실패')}`
        """
    )
    st.stop()

# 영화 목록이 비어 있는 경우
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ **그날은 아직 집계 전입니다.**")
    st.info(
        f"**{display_date}**의 박스오피스 데이터가 존재하지 않거나 정산 중입니다. 다른 날짜를 선택해 주세요."
    )
    st.stop()

# -----------------------------------------------------------------------------
# 6. 데이터 전처리 (숫자 변환 및 기호/이모지 가공)
# -----------------------------------------------------------------------------
df = pd.DataFrame(daily_list)

# 숫자로 변환할 컬럼 지정
numeric_columns = [
    "rank",
    "rankInten",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt",
]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)


# 1) 순위 증감 표시 가공 (양수: 🔺, 음수: 🔹, 0: -)
def format_rank_inten(val):
    val = int(val)
    if val > 0:
        return f"🔺 {val}"
    elif val < 0:
        return f"🔹 {abs(val)}"
    else:
        return "-"


df["rankIntenDisplay"] = df["rankInten"].apply(format_rank_inten)


# 2) 영화명 가공 (누적관객 100만 명 이상 시 🏆 트로피 이모지 부착)
def format_movie_title(row):
    title = str(row["movieNm"])
    if row["audiAcc"] >= 1000000:
        return f"🏆 {title}"
    return title


df["displayMovieNm"] = df.apply(format_movie_title, axis=1)

# -----------------------------------------------------------------------------
# 7. 화면 구성: 1위 영화 핵심 지표 (Metrics)
# -----------------------------------------------------------------------------
top_1 = df.iloc[0]

st.subheader(f"🥇 {display_date} 1위 영화")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="🎬 영화명", value=str(top_1["displayMovieNm"]))

with col2:
    st.metric(
        label="🎟️ 당일 관객수",
        value=f"{int(top_1['audiCnt']):,} 명",
        delta=f"전날 대비 {int(top_1['rankInten']):+} 위"
        if top_1["rankInten"] != 0
        else "순위 유지",
    )

with col3:
    st.metric(
        label="🍿 누적 관객수", value=f"{int(top_1['audiAcc']):,} 명"
    )

st.divider()

# -----------------------------------------------------------------------------
# 8. 화면 구성: TOP 5 관객수 막대그래프
# -----------------------------------------------------------------------------
st.subheader("📊 관객수 상위 TOP 5 영화")

df_top5 = df.head(5).copy()
chart_data = pd.DataFrame(
    {"영화명": df_top5["movieNm"], "당일 관객수": df_top5["audiCnt"]}
).set_index("영화명")

st.bar_chart(chart_data)

st.divider()

# -----------------------------------------------------------------------------
# 9. 화면 구성: 박스오피스 전체 순위표
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위")

# 표 출력을 위한 데이터프레임 구성
display_df = df[
    [
        "rank",
        "rankIntenDisplay",
        "displayMovieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()
display_df.columns = [
    "순위",
    "순위증감",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

st.dataframe(
    display_df,
    use_container_width=True,
    column_config={
        "순위": st.column_config.NumberColumn(format="%d위"),
        "관객수": st.column_config.NumberColumn(format="%d명"),
        "누적관객": st.column_config.NumberColumn(format="%d명"),
        "스크린수": st.column_config.NumberColumn(format="%d개"),
    },
    hide_index=True,
)
