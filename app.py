import streamlit as st
import pandas as pd
import google.generativeai as genai
import io

# --- 設定頁面 ---
st.set_page_config(page_title="AI 家庭財務管理", layout="wide")
st.title("📊 AI 家庭財務管理")

# --- 讀取 Secrets ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except KeyError as e:
    st.error(f"缺少 GOOGLE_API_KEY 設定: {e}。請至 Streamlit Cloud 設定 Secrets。")
    st.stop()

# --- 側邊欄：模型選擇 ---
with st.sidebar:
    st.header("設定")
    st.subheader("🤖 模型選擇")
    
    selected_model_name = "gemini-1.5-flash"
    if api_key:
        try:
            genai.configure(api_key=api_key)
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if available_models:
                # 自動找 Pro
                default_index = 0
                for i, name in enumerate(available_models):
                    if "1.5-pro" in name and "latest" in name:
                        default_index = i
                        break
                selected_model_name = st.selectbox("選擇 AI 模型", available_models, index=default_index)
        except Exception as e:
            st.error(f"模型載入失敗: {e}")

# --- 主程式邏輯 ---

# 1. 上傳並載入 CSV 數據
st.subheader("1. 資產與收支明細管理")

col_upload, col_sample = st.columns([4, 1], vertical_alignment="bottom")
with col_upload:
    uploaded_file = st.file_uploader(
        label="📁 上傳財務 CSV 檔",
        type=["csv"],
    )

with col_sample:
    # 只有尚未成功上傳檔案時，才顯示「下載範例」按鈕
    if uploaded_file is None:
        with open("financial_data_sample.csv", "rb") as f:
            sample_bytes = f.read()
        st.download_button(
            label="⬇️ 下載範例 CSV",
            data=sample_bytes,
            file_name="financial_data_sample.csv",
            mime="text/csv",
        )

if uploaded_file is None:
    st.info("請先上傳 CSV 檔以進行編輯與分析（如需範例，右側可下載範例 CSV）。")
    st.stop()

df = pd.read_csv(uploaded_file)

# 2. 顯示編輯器（不再提供雲端儲存，編輯僅在本次瀏覽器工作階段內有效）
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="editor")

# 2-1. 下載編輯後的 CSV
csv_bytes = edited_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="💾 下載編輯後 CSV",
    data=csv_bytes,
    file_name="financial_data_edited.csv",
    mime="text/csv",
    help="下載目前表格中（已編輯）的內容為 CSV 檔案",
)

# 匯率設定
col1, col2 = st.columns(2)
with col1: USDTWD = st.number_input("USD/TWD 匯率", value=31.5)
with col2: THBTWD = st.number_input("THB/TWD 匯率", value=0.96)

# --- 3. 計算邏輯 (使用 edited_df 進行即時計算) ---
def calculate_metrics(df, usdtwd, thbtwd):
    total_asset = 0; total_liability = 0; monthly_income = 0; monthly_expense = 0
    if df.empty: return 0,0,0,0
    
    for _, row in df.iterrows():
        amount = pd.to_numeric(row['Amount'], errors='coerce')
        if pd.isna(amount): continue
        
        if row['Currency'] == 'USD': amount *= usdtwd
        elif row['Currency'] == 'THB': amount *= thbtwd
        
        cat = row['Category']; freq = row['Frequency']
        
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
kpi_toggle_col, _ = st.columns([1, 5])

if 'hide_kpi' not in st.session_state:
    st.session_state.hide_kpi = False

with kpi_toggle_col:
    if st.button("顯示金額", help="點擊以隱藏或顯示金額"):
        st.session_state.hide_kpi = not st.session_state.hide_kpi

def masked_value(value: float) -> str:
    return "••••" if st.session_state.hide_kpi else f"${value:,.0f}"

kpi_delta = (
    "••••" if st.session_state.hide_kpi or t_asset == 0
    else f"負債比: {t_liability / t_asset * 100:.1f}%"
)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("總資產 (TWD)", masked_value(t_asset))
kpi2.metric("總負債 (TWD)", masked_value(t_liability), delta_color="inverse")
kpi3.metric("淨資產 (TWD)", masked_value(net_worth), delta=kpi_delta)
kpi4.metric("每月正向現金流", masked_value(monthly_net_flow))

# --- 5. AI 分析 ---
st.markdown("---")
st.subheader(f"2. Gemini 財務顧問 (模型: {selected_model_name.replace('models/', '')})")
user_question = st.text_area("您想分析什麼？", "請進行整體的財務狀況分析與建議，並預估10年後的資產變化。")

if st.button("Gemini 分析"):
    if not api_key: st.warning("請先輸入 Google API Key")
    else:
        try:
            model = genai.GenerativeModel(selected_model_name)
            data_context = edited_df.to_csv(index=False)
            prompt = f"""
            角色：專業財務顧問。數據：{data_context}。
            匯率：USD={USDTWD}, THB={THBTWD}。
            問題：{user_question}。
            要求：繁體中文，Markdown，精確數據，針對未來預測給出樂觀/保守情境，呈現理專或是顧問公司專業報告的格式。
            """
            with st.spinner(f"正在分析..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
        except Exception as e: st.error(f"錯誤: {e}")