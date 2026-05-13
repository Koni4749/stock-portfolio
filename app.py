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
@st.cache_data(ttl=3600)
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
        usd_krw = 1300.0
        
    return data, usd_krw

@st.cache_data(ttl=3600)
def fetch_historical_data(tickers, index_tickers, period="1y"):
    """과거 1년 시계열 데이터를 다운로드하는 함수"""
    all_tickers = tickers + index_tickers + ["USDKRW=X"]
    hist_data = yf.download(all_tickers, period=period)['Close']
    
    if isinstance(hist_data, pd.Series):
        hist_data = pd.DataFrame(hist_data, columns=all_tickers)
        
    hist_data = hist_data.ffill()
    hist_data = hist_data.bfill()
    return hist_data

# -----------------------------------------------------------------------------
# 메인 로직: 데이터 로드
# -----------------------------------------------------------------------------
st.sidebar.header("📁 데이터 소스 설정")

default_csv_path = "portfolio.csv"
uploaded_file = st.sidebar.file_uploader("다른 포트폴리오 테스트 (선택사항)", type=["csv"])

df = None

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    # [수정됨] 잠깐 떴다가 사라지는 팝업 알림(Toast) 적용
    st.toast("업로드된 파일을 적용했습니다.", icon="📁")
elif os.path.exists(default_csv_path):
    df = pd.read_csv(default_csv_path)
    # [수정됨] 문구 변경 및 자동으로 사라지는 알림 적용
    st.toast("견본 포트폴리오입니다.", icon="✅")
else:
    st.error("오류: 깃허브 저장소에서 'portfolio.csv' 파일을 찾을 수 없습니다. 파일 이름과 위치를 확인해주세요.")

if df is not None:
    required_columns = ['종목명', '티커', '매수단가', '수량', '섹터']
    if not all(col in df.columns for col in required_columns):
        st.error(f"CSV 파일에 다음 필수 컬럼이 포함되어야 합니다: {', '.join(required_columns)}")
        st.stop()

    df = df.dropna(subset=['티커'])
    df['티커'] = df['티커'].astype(str)

    with st.spinner('실시간 금융 데이터를 불러오는 중입니다... (약 5~10초 소요)'):
        tickers = df['티커'].unique().tolist()
        current_prices, current_fx = fetch_current_prices_and_fx(tickers)
        
        df['현재가'] = df['티커'].map(current_prices)
        df['국가'] = df['티커'].apply(lambda x: 'KR' if '.KS' in str(x) or '.KQ' in str(x) else 'US')
        
        # [수정됨] 환율 계산 후 발생하는 무한 소수점을 방지하기 위해 반올림(round) 처리
        df['매수금액'] = df.apply(lambda row: row['매수단가'] * row['수량'] * (current_fx if row['국가'] == 'US' else 1), axis=1).round(0)
        df['평가금액'] = df.apply(lambda row: row['현재가'] * row['수량'] * (current_fx if row['국가'] == 'US' else 1), axis=1).round(0)
        
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
        # [수정됨] 툴팁(Hover) 소수점 깔끔하게 정리
        fig_treemap.update_traces(hovertemplate='<b>%{label}</b><br>평가금액: ₩%{value:,.0f}')
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
        
        # [수정됨] 글씨 잘림 방지를 위해 cliponaxis=False 설정 및 X축 여유 공간 확보
        fig_bar_ret.update_traces(marker_color=df_sorted['색상'], texttemplate='%{text:.2f}%', textposition='outside', cliponaxis=False)
        x_min = df_sorted['수익률(%)'].min()
        x_max = df_sorted['수익률(%)'].max()
        x_padding = (x_max - x_min) * 0.2  # 20% 여백 추가
        fig_bar_ret.update_xaxes(range=[x_min - x_padding, x_max + x_padding])
        st.plotly_chart(fig_bar_ret, use_container_width=True)

    with row2_col2:
        df_melted = df.melt(id_vars=['종목명'], value_vars=['매수금액', '평가금액'], 
                            var_name='구분', value_name='금액')
        fig_grouped_bar = px.bar(df_melted, x='종목명', y='금액', color='구분', barmode='group',
                                 title='매수금액 vs 현재 평가금액')
        # [수정됨] 그룹 막대 차트 호버 툴팁 깔끔하게 콤마+정수 처리
        fig_grouped_bar.update_traces(hovertemplate='%{x}<br>금액: ₩%{y:,.0f}')
        st.plotly_chart(fig_grouped_bar, use_container_width=True)

    # --- 버블 차트 ---
    df_bubble = df.sort_values(by='평가금액', ascending=False)
    fig_bubble = px.scatter(df_bubble, x='종목명', y='수익률(%)', size='평가금액', color='섹터',
                            hover_name='종목명', text='종목명', 
                            hover_data={
                                '종목명': False,
                                '수익률(%)': ':.2f',
                                '비중(%)': ':.2f',
                                '평가금액': ':,.0f'
                            },
                            title='종목별 수익률 버블 차트 (버블 크기: 비중)',
                            size_max=60)
    
    # [수정됨] 큰 버블이나 텍스트가 위로 잘리지 않도록 여백 확보 및 cliponaxis 해제
    fig_bubble.update_traces(textposition='top center', cliponaxis=False)
    y_min = df_bubble['수익률(%)'].min()
    y_max = df_bubble['수익률(%)'].max()
    y_padding = (y_max - y_min) * 0.25 if (y_max - y_min) != 0 else 10 # 25% 상하 여백 추가
    fig_bubble.update_yaxes(range=[y_min - y_padding, y_max + y_padding])
    
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
