from datetime import datetime, timedelta
import zoneinfo
import pandas as pd
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 제목
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스", page_icon="🎬", layout="wide"
)

st.title("🎬 어제의 일별 박스오피스")

# -----------------------------------------------------------------------------
# 2. 한국 표준시(KST) 기준 어제 날짜 계산
# -----------------------------------------------------------------------------
# 배포 서버(Streamlit Cloud)의 시계가 UTC(세계협정시)로 되어 있어도
# 항상 한국 표준시(Asia/Seoul) 기준으로 어제 날짜(YYYYMMDD)를 구합니다.
kst_timezone = zoneinfo.ZoneInfo("Asia/Seoul")
now_in_kst = datetime.now(kst_timezone)
yesterday = now_in_kst - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 기준일: **{display_date}** (한국 시간 기준 어제)")

# -----------------------------------------------------------------------------
# 3. Streamlit Secrets에서 API 인증키 불러오기
# -----------------------------------------------------------------------------
# .streamlit/secrets.toml 파일 또는 Streamlit Cloud의 Secrets 설정에서
# KOBIS_KEY 값을 안전하게 읽어옵니다.
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("🔒 **인증키 미설치 오류**")
    st.warning(
        """
        KOBIS API 인증키가 설정되지 않았습니다.
        
        **확인 및 해결 방법:**
        1. [KOBIS Open API](https://www.kobis.or.kr/kobisopenapi/) 사이트에서 회원가입 후 키를 발급받으세요.
        2. 로컬 실행 시: `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = "발급받은_키"`를 추가해 주세요.
        3. Streamlit Cloud 배포 시: 앱 설정의 **Secrets** 항목에 `KOBIS_KEY = "발급받은_키"`를 등록해 주세요.
        """
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

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
# Network 오류 처리
if "error_type" in data and data["error_type"] == "network":
    st.error("🌐 **네트워크 통신 오류**")
    st.info(
        f"API 서버에 연결할 수 없습니다. 인터넷 연결 및 요청 주소를 확인해 주세요.\n\n세부 오류: `{data['details']}`"
    )
    st.stop()

# API 인증 오류 처리 (KOBIS는 키가 틀려도 HTTP 200으로 faultInfo를 반환함)
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

# 응답 데이터 파싱 및 데이터 유무 확인
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ **박스오피스 데이터 없음**")
    st.info(
        f"""
        **{display_date}**의 박스오피스 데이터가 비어 있습니다.
        
        - KOBIS 서버에서 아직 어제자 정산 데이터 작성을 완료하지 않았을 수 있습니다.
        - 잠시 후 다시 시도하시거나 KOBIS 공식 홈페이지의 정시 업데이트 여부를 확인해 주세요.
        """
    )
    st.stop()

# -----------------------------------------------------------------------------
# 6. 데이터 전처리 (문자열 -> 숫자 변환)
# -----------------------------------------------------------------------------
df = pd.DataFrame(daily_list)

# KOBIS 응답값(문자열)을 숫자로 안전하게 변환
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

# -----------------------------------------------------------------------------
# 7. 화면 구성: 1위 영화 핵심 지표 (Metrics)
# -----------------------------------------------------------------------------
top_1 = df.iloc[0]

st.subheader("🥇 어제의 1위 영화")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="🎬 영화명", value=str(top_1["movieNm"]))

with col2:
    st.metric(
        label="🎟️ 어제 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=f"전날 대비 {top_1['rankInten']:+} 위"
        if top_1["rankInten"] != 0
        else "순위 유지",
    )

with col3:
    st.metric(
        label="🍿 누적 관객수", value=f"{top_1['audiAcc']:,} 명"
    )

st.divider()

# -----------------------------------------------------------------------------
# 8. 화면 구성: TOP 5 관객수 막대그래프
# -----------------------------------------------------------------------------
st.subheader("📊 관객수 상위 TOP 5 영화")

# 상위 5개 데이터 추출
df_top5 = df.head(5).copy()

# Streamlit 기본 차트(st.bar_chart)에 맞게 데이터프레임 구조 생성
chart_data = pd.DataFrame(
    {"영화명": df_top5["movieNm"], "어제 관객수": df_top5["audiCnt"]}
).set_index("영화명")

st.bar_chart(chart_data)

st.divider()

# -----------------------------------------------------------------------------
# 9. 화면 구성: 박스오피스 전체 순위표
# -----------------------------------------------------------------------------
st.subheader("📋 전체 박스오피스 순위")

# 표에 보여줄 컬럼 선택 및 이름 변경
display_df = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()
display_df.columns = [
    "순위",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

# 깔끔한 표 출력을 위해 정수형 컬럼 formatting 설정 후 출력
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
