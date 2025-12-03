import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- 設定頁面 ---
st.set_page_config(page_title="家庭財務AI中控台 (Gemini版)", layout="wide")
st.title("📊 家庭財務 AI 中控台")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("設定")
    # 從 Streamlit Secrets 讀取 Google API Key
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("Gemini API Key 已載入")
    else:
        api_key = st.text_input("輸入 Google Gemini API Key", type="password")
    
    st.markdown("---")
    st.info("💡 數據修改說明：\n在右側表格修改數據暫時僅對本次計算有效。若要永久保存，請更新 GitHub 上的 CSV 檔案。")

# 匯率設定 (可手動調整)
col1, col2 = st.columns(2)
with col1:
    USDTWD = st.number_input("USD/TWD 匯率", value=32.5)
with col2:
    THBTWD = st.number_input("THB/TWD 匯率", value=0.92)

# --- 1. 數據讀取 ---
try:
    df = pd.read_csv("financial_data.csv")
except FileNotFoundError:
    st.error("找不到 financial_data.csv，請確認檔案已上傳至 GitHub。")
    st.stop()

# --- 2. 數據編輯區 ---
st.subheader("1. 資產與收支明細")
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

# --- 3. 計算邏輯 ---
def calculate_metrics(df, usdtwd, thbtwd):
    total_asset = 0
    total_liability = 0
    monthly_income = 0
    monthly_expense = 0
    
    for _, row in df.iterrows():
        # 匯率轉換
        amount = row['Amount']
        if row['Currency'] == 'USD': amount *= usdtwd
        elif row['Currency'] == 'THB': amount *= thbtwd
        
        cat = row['Category']
        freq = row['Frequency']
        
        # 資產負債計算
        if cat == 'Asset':
            total_asset += amount
        elif cat == 'Liability':
            total_liability += amount
            
        # 現金流計算 (全部標準化為月)
        elif cat == 'Income':
            if freq == 'Monthly': monthly_income += amount
            elif freq == 'Quarterly': monthly_income += amount / 3
            elif freq == 'Yearly': monthly_income += amount / 12
        elif cat == 'Expense':
            if freq == 'Monthly': monthly_expense += amount
            elif freq == 'Quarterly': monthly_expense += amount / 3
            elif freq == 'Yearly': monthly_expense += amount / 12

    return total_asset, total_liability, monthly_income, monthly_expense

t_asset, t_liability, m_income, m_expense = calculate_metrics(edited_df, USDTWD, THBTWD)
net_worth = t_asset - t_liability
monthly_net_flow = m_income - m_expense

# --- 4. 儀表板顯示 ---
st.markdown("---")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("總資產 (TWD)", f"${t_asset:,.0f}")
kpi2.metric("總負債 (TWD)", f"${t_liability:,.0f}", delta_color="inverse")
kpi3.metric("淨資產 (TWD)", f"${net_worth:,.0f}", delta=f"負債比: {t_liability/t_asset*100:.1f}%")
kpi4.metric("每月正向現金流 (預估)", f"${monthly_net_flow:,.0f}", help="包含將年終獎金/配息攤提至每月的平均值")

# --- 5. AI 分析報告 (Gemini) ---
st.markdown("---")
st.subheader("2. Gemini 財務顧問")

user_question = st.text_area("您想分析什麼？", "請分析目前的財務結構風險，並預測若維持現狀，10年後的資產變化。")

if st.button("🚀 啟動 Gemini 分析"):
    if not api_key:
        st.warning("請先輸入 Google API Key")
    else:
        # 設定 Gemini
        try:
            genai.configure(api_key=api_key)
            # 使用最新的 flash 模型，速度快且便宜(免費額度內)
            model = genai.GenerativeModel('gemini-1.5-pro')
            
            # 準備資料給 AI
            data_context = edited_df.to_csv(index=False)
            prompt = f"""
            角色：專業私人財務顧問。
            任務：根據以下用戶財務數據(CSV)回答問題。
            匯率參考：USD={USDTWD}, THB={THBTWD}
            
            數據：
            {data_context}
            
            用戶問題：
            {user_question}
            
            要求：
            1. 用繁體中文回答。
            2. 數據引用需精確。
            3. 請使用 Markdown 格式排版，讓報告易讀。
            4. 針對未來預測請給出樂觀與保守兩種情境。
            """
            
            with st.spinner("Gemini 正在分析您的資產配置..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
        except Exception as e:
            st.error(f"發生錯誤: {e}")