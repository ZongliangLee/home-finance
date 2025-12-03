import streamlit as st
import pandas as pd
import google.generativeai as genai

# --- 設定頁面 ---
st.set_page_config(page_title="家庭財務AI中控台 (Gemini版)", layout="wide")
st.title("📊 家庭財務 AI 中控台")

# --- 側邊欄設定 (更新：加入模型選擇器) ---
with st.sidebar:
    st.header("設定")
    
    # 1. 處理 API Key
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("Gemini API Key 已載入")
    else:
        api_key = st.text_input("輸入 Google Gemini API Key", type="password")

    # 2. 動態抓取並選擇模型
    st.markdown("---")
    st.subheader("🤖 模型選擇")
    
    selected_model_name = "gemini-1.5-flash" # 預設值，防呆用

    if api_key:
        try:
            genai.configure(api_key=api_key)
            # 抓取所有支援 'generateContent' (文字生成) 的模型
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            
            # 讓用戶選擇，並嘗試自動預選 Pro 模型
            if available_models:
                # 嘗試找到 pro 模型的 index
                default_index = 0
                for i, name in enumerate(available_models):
                    if "1.5-pro" in name and "latest" in name: # 優先選最新的 Pro
                        default_index = i
                        break
                
                selected_model_name = st.selectbox(
                    "選擇 AI 模型版本", 
                    available_models, 
                    index=default_index,
                    help="Pro 模型邏輯強但較慢；Flash 模型速度快。"
                )
            else:
                st.warning("找不到可用模型，請檢查 API Key 權限。")
                
        except Exception as e:
            st.error(f"無法載入模型清單: {e}")
    else:
        st.info("請輸入 API Key 以載入模型清單")

    st.markdown("---")
    st.info("💡 數據修改說明：\n在右側表格修改數據暫時僅對本次計算有效。若要永久保存，請更新 GitHub 上的 CSV 檔案。")

# 匯率設定
col1, col2 = st.columns(2)
with col1:
    USDTWD = st.number_input("USD/TWD 匯率", value=32.5)
with col2:
    THBTWD = st.number_input("THB/TWD 匯率", value=0.92)

# --- 1. 數據讀取 ---
try:
    df = pd.read_csv("financial_data.csv")
except FileNotFoundError:
    st.error("找不到 financial_data.csv")
    st.stop()

# --- 2. 數據編輯區 ---
st.subheader("1. 資產與收支明細")
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

# --- 3. 計算邏輯 (保持不變) ---
def calculate_metrics(df, usdtwd, thbtwd):
    total_asset = 0
    total_liability = 0
    monthly_income = 0
    monthly_expense = 0
    for _, row in df.iterrows():
        amount = row['Amount']
        if row['Currency'] == 'USD': amount *= usdtwd
        elif row['Currency'] == 'THB': amount *= thbtwd
        
        cat = row['Category']
        freq = row['Frequency']
        
        if cat == 'Asset': total_asset += amount
        elif cat == 'Liability': total_liability += amount
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
kpi4.metric("每月正向現金流 (預估)", f"${monthly_net_flow:,.0f}")

# --- 5. AI 分析報告 (使用選單選取的模型) ---
st.markdown("---")
st.subheader(f"2. Gemini 財務顧問 (使用模型: {selected_model_name.replace('models/', '')})")

user_question = st.text_area("您想分析什麼？", "請分析目前的財務結構風險，並預測若維持現狀，10年後的資產變化。")

if st.button("🚀 啟動 Gemini 分析"):
    if not api_key:
        st.warning("請先輸入 Google API Key")
    else:
        try:
            # 使用側邊欄選取的模型名稱
            model = genai.GenerativeModel(selected_model_name)
            
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
            3. 請使用 Markdown 格式排版。
            4. 針對未來預測請給出樂觀與保守兩種情境。
            """
            
            with st.spinner(f"正在使用 {selected_model_name} 分析中..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
        except Exception as e:
            st.error(f"發生錯誤: {e}")