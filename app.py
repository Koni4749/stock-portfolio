import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import os

# -----------------------------------------------------------------------------
# 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="개인 주식 포트폴리오 대시보드", layout="wide")
st.title("📈 개인 주식 포트폴리오 대시보드")
st.markdown("yfinance와 Plotly를 활용한 실시간 포트폴리오 성과 분석 및 위험 관리 대시보드입니다.")

# -----------------------------------------------------------------------------
# 데이터 캐싱 및 데이터 수집 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1시간 동안 데이터 캐싱
def fetch_current_prices_and_fx(tickers):
    """현재 주가 및 현재 환율(USD/KRW)을 가져오는 함수"""
    data = {}
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            history = ticker_obj.history(period="1d")
            if not history.empty:
                data[ticker] = history['Close'].iloc[-1]
            else:
                data[ticker] = None
        except Exception:
            data[ticker] = None
            
    try:
        fx_history = yf.Ticker("USDKRW=X").history(period="1d")
        usd_krw = fx_history['Close'].iloc[-1]
    except:
        usd_krw = 1300.0 # API 실패 시 기본 환율
        
    return data, usd_krw

@st.cache_data(ttl=3600)
def fetch_historical_data(tickers, index_tickers, period="1y"):
    """과거 1년 시계열 데이터를 다운로드하는 함수"""
    all_tickers = tickers + index_tickers + ["USDKRW=X"]
    hist_data = yf.download(all_tickers, period=period)['Close']
    
    if isinstance(hist_data, pd.Series):
        hist_data = pd.DataFrame(hist_data, columns=all_tickers)
        
    hist_data.fillna(method='ffill', inplace=True)
    hist_data.fillna(method='bfill', inplace=True)
    return hist_data

# -----------------------------------------------------------------------------
# 메인 로직: 데이터 로드 (자동 로드 + 선택적 업로드)
# -----------------------------------------------------------------------------
st.sidebar.header("📁 데이터 소스 설정")

# 깃허브에 올라간 기본 파일 경로
default_csv_path = "portfolio.csv"

# 사용자가 원하면 다른 파일을 테스트해볼 수 있도록 업로더는 남겨둠 (선택사항)
uploaded_file = st.sidebar.file_uploader("다른 포트폴리오 테스트 (선택사항)", type=["csv"])

df = None

if uploaded_file is not None:
    # 1. 사용자가 직접 업로드한 파일이 우선
    df = pd.read_csv(uploaded_file)
    st.sidebar.success("업로드된 파일을 적용했습니다.")
elif os.path.exists(default_csv_path):
    # 2. 업로드한 파일이 없으면 깃허브에 있는 portfolio.csv 자동 로드
    df = pd.read_csv(default_csv_path)
    st.sidebar.success("기본 포트폴리오(portfolio.csv)를 자동으로 불러왔습니다.")
else:
    # 3. 파일이 둘 다 없는 경우 경고 메시지
    st.error("오류: 깃허브 저장소에서 'portfolio.csv' 파일을 찾을 수 없습니다. 파일 이름과 위치를 확인해주세요.")

if df is not None:
    # 필수 컬럼 체크
    required_columns = ['종목명', '티커', '매수단가', '수량', '섹터', '매수일자']
    if not all(col in df.columns for col in required_columns):
        st.error(f"CSV 파일에 다음 필수 컬럼이 포함되어야 합니다: {', '.join(required_columns)}")
        st.stop()

    with st.spinner('실시간 금융 데이터를 불러오는 중입니다... (약 5~10초 소요)'):
        # 현재 가격 및 환율 데이터 가져오기
        tickers = df['티커'].unique().tolist()
        current_prices, current_fx = fetch_current_prices_and_fx(tickers)
        
        # 데이터프레임에 계산된 지표 추가
        df['현재가'] = df['티커'].map(current_prices)
        df['국가'] = df['티커'].apply(lambda x: 'KR' if '.KS' in x or '.KQ' in x else 'US')
        
        # 평가금액 계산
        df['매수금액'] = df.apply(lambda row: row['매수단가'] * row['수량'] * (current_fx if row['국가'] == 'US' else 1), axis=1)
        df['평가금액'] = df.apply(lambda row: row['현재가'] * row['수량'] * (current_fx if row['국가'] == 'US' else 1), axis=1)
        
        df['수익률(%)'] = ((df['평가금액'] - df['매수금액']) / df['매수금액']) * 100
        total_evaluation = df['평가금액'].sum()
        df['비중(%)'] = (df['평가금액'] / total_evaluation) * 100

    # -----------------------------------------------------------------------------
    # 상단 요약 지표 (KPI)
    # -----------------------------------------------------------------------------
    total_invested = df['매수금액'].sum()
    total_profit = total_evaluation - total_invested
    total_return_pct = (total_profit / total_invested) * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 매수금액", f"₩{total_invested:,.0f}")
    col2.metric("총 평가금액", f"₩{total_evaluation:,.0f}", f"{total_return_pct:+.2f}%")
    col3.metric("총 손익", f"₩{total_profit:,.0f}")
    col4.metric("적용 환율 (USD/KRW)", f"₩{current_fx:,.2f}")
    
    st.markdown("---")

    # -----------------------------------------------------------------------------
    # 시각화 Section 1: 비중 분석
    # -----------------------------------------------------------------------------
    st.subheader("📊 포트폴리오 비중 분석")
    row1_col1, row1_col2, row1_col3 = st.columns(3)

    with row1_col1:
        fig_donut = px.pie(df, values='평가금액', names='종목명', hole=0.4, title='종목별 투자 비중')
        fig_donut.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_donut, use_container_width=True)

    with row1_col2:
        sector_df = df.groupby('섹터')['평가금액'].sum().reset_index()
        fig_pie = px.pie(sector_df, values='평가금액', names='섹터', title='업종별 투자 비중')
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)

    with row1_col3:
        fig_treemap = px.treemap(df, path=['섹터', '종목명'], values='평가금액', title='섹터 및 종목별 계층 비중')
        fig_treemap.update_layout(margin=dict(t=50, l=25, r=25, b=25))
        st.plotly_chart(fig_treemap, use_container_width=True)

    st.markdown("---")

    # -----------------------------------------------------------------------------
    # 시각화 Section 2: 성과 분석
    # -----------------------------------------------------------------------------
    st.subheader("📈 개별 종목 성과 분석")
    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        df_sorted = df.sort_values(by='수익률(%)', ascending=True)
        df_sorted['색상'] = df_sorted['수익률(%)'].apply(lambda x: 'red' if x >= 0 else 'blue')
        
        fig_bar_ret = px.bar(df_sorted, x='수익률(%)', y='종목명', orientation='h',
                             title='종목별 수익률 (%)', text='수익률(%)')
        fig_bar_ret.update_traces(marker_color=df_sorted['색상'], texttemplate='%{text:.2f}%', textposition='outside')
        st.plotly_chart(fig_bar_ret, use_container_width=True)

    with row2_col2:
        df_melted = df.melt(id_vars=['종목명'], value_vars=['매수금액', '평가금액'], 
                            var_name='구분', value_name='금액')
        fig_grouped_bar = px.bar(df_melted, x='종목명', y='금액', color='구분', barmode='group',
                                 title='매수금액 vs 현재 평가금액')
        st.plotly_chart(fig_grouped_bar, use_container_width=True)

    fig_bubble = px.scatter(df, x='비중(%)', y='수익률(%)', size='평가금액', color='섹터',
                            hover_name='종목명', text='종목명', title='비중 vs 수익률 버블 차트 (버블 크기: 평가금액)',
                            size_max=60)
    fig_bubble.update_traces(textposition='top center')
    fig_bubble.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_bubble, use_container_width=True)

    st.markdown("---")

    # -----------------------------------------------------------------------------
    # 시각화 Section 3: 시계열 분석 및 지수 비교
    # -----------------------------------------------------------------------------
    st.subheader("시간 경과에 따른 포트폴리오 성과 및 위험도 (최근 1년)")
    tab1, tab2 = st.tabs(["누적 수익률 비교", "MDD (최대 낙폭) 비교"])
    
    with st.spinner('과거 시계열 데이터를 분석 중입니다...'):
        index_mapping = {
            '^KS11': '코스피',
            '^KQ11': '코스닥',
            '^DJI': '다우존스',
            '^IXIC': '나스닥',
            '^GSPC': 'S&P 500'
        }
        index_tickers = list(index_mapping.keys())
        
        hist_data = fetch_historical_data(tickers, index_tickers)
        
        daily_portfolio_value = pd.Series(0.0, index=hist_data.index)
        
        for idx, row in df.iterrows():
            tkr = row['티커']
            qty = row['수량']
            nat = row['국가']
            
            if tkr in hist_data.columns:
                daily_price = hist_data[tkr]
                if nat == 'US':
                    daily_portfolio_value += daily_price * qty * hist_data["USDKRW=X"]
                else:
                    daily_portfolio_value += daily_price * qty
        
        my_cum_return = (daily_portfolio_value / daily_portfolio_value.iloc[0]) - 1
        
        indices_cum_return = pd.DataFrame(index=hist_data.index)
        for tkr, name in index_mapping.items():
            if tkr in hist_data.columns:
                indices_cum_return[name] = (hist_data[tkr] / hist_data[tkr].iloc[0]) - 1

        cum_return_df = indices_cum_return.copy()
        cum_return_df['내 포트폴리오'] = my_cum_return

        portfolio_value_df = cum_return_df + 1
        rolling_max = portfolio_value_df.cummax()
        drawdown_df = (portfolio_value_df - rolling_max) / rolling_max
        
    with tab1:
        fig_line = px.line(cum_return_df * 100, 
                           title='내 포트폴리오 vs 주요 지수 누적 수익률 비교 (%)',
                           labels={'value': '누적 수익률 (%)', 'Date': '날짜', 'variable': '자산군'})
        fig_line.update_traces(patch={"line": {"width": 4}}, selector={"name": "내 포트폴리오"})
        st.plotly_chart(fig_line, use_container_width=True)

    with tab2:
        fig_mdd_custom = go.Figure()
        
        fig_mdd_custom.add_trace(go.Scatter(x=drawdown_df.index, y=drawdown_df['내 포트폴리오']*100,
                                            fill='tozeroy', mode='lines', name='내 포트폴리오',
                                            line=dict(width=3, color='rgba(255, 0, 0, 0.7)')))
        
        colors = ['blue', 'green', 'orange', 'purple', 'cyan']
        for i, col in enumerate(index_mapping.values()):
            fig_mdd_custom.add_trace(go.Scatter(x=drawdown_df.index, y=drawdown_df[col]*100,
                                                mode='lines', name=col,
                                                line=dict(width=1, color=colors[i], dash='dot')))
            
        fig_mdd_custom.update_layout(title='MDD (Maximum Drawdown) 흐름 비교',
                                     yaxis_title='낙폭 (%)', xaxis_title='날짜',
                                     hovermode='x unified')
        st.plotly_chart(fig_mdd_custom, use_container_width=True)
        
        mdd_summary = (drawdown_df.min() * 100).round(2)
        st.markdown("### 📉 자산별 최대 낙폭 (MDD) 요약")
        st.dataframe(pd.DataFrame(mdd_summary, columns=['최대 낙폭 (%)']).T)
