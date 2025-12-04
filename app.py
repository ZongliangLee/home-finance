import streamlit as st
import pandas as pd
import google.generativeai as genai
import io

# --- 設定頁面 ---
st.set_page_config(
    page_title="AI 家庭財務管理",
    layout="wide",
    initial_sidebar_state="collapsed",  # 預設折疊側邊欄
)
st.title("📊 AI 家庭財務管理")

# --- 讀取 Secrets ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except KeyError as e:
    st.error(f"缺少 GOOGLE_API_KEY 設定: {e}。請至 Streamlit Cloud 設定 Secrets。")
    st.stop()

# --- 對話狀態（在同一個瀏覽器分頁期間持續） ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- 側邊欄：模型選擇邏輯 ---
DEFAULT_MODEL_NAME = "models/gemini-2.5-flash-lite"

# 初始化狀態變數
if "show_model_list" not in st.session_state:
    st.session_state.show_model_list = False
if "selected_model_name" not in st.session_state:
    st.session_state.selected_model_name = DEFAULT_MODEL_NAME
if "dev_unlock_count" not in st.session_state:
    st.session_state.dev_unlock_count = 0

with st.sidebar:
    st.header("設定")
    st.subheader("🤖 模型選擇")
    
    # 讀取目前選用的模型
    current_model = st.session_state.selected_model_name

    # --- 隱藏觸發邏輯 ---
    # 如果還沒顯示清單，顯示一個按鈕讓使用者點擊以累積次數
    if not st.session_state.show_model_list:
        # 使用按鈕模擬點擊事件
        # 移除了 help 提示，也不顯示 toast
        if st.button(f"目前模型：\n{current_model.split('/')[-1]}"):
            st.session_state.dev_unlock_count += 1
            
            # 判斷是否達到解鎖次數 (5次)
            if st.session_state.dev_unlock_count >= 5:
                st.session_state.show_model_list = True
                st.session_state.dev_unlock_count = 0 # 重置計數
                st.rerun() # 立即重新整理以顯示選單
    
    # --- 進階選單顯示邏輯 ---
    else:
        st.caption(f"目前使用模型：`{current_model}`")
        
        if api_key:
            try:
                genai.configure(api_key=api_key)
                available_models = [
                    m.name
                    for m in genai.list_models()
                    if "generateContent" in m.supported_generation_methods
                ]
                if available_models:
                    # 預設選目前已選用的模型
                    default_index = 0
                    for i, name in enumerate(available_models):
                        if name == st.session_state.selected_model_name:
                            default_index = i
                            break
                    
                    selected_model_name = st.selectbox(
                        "選擇 AI 模型（進階）", available_models, index=default_index
                    )
                    
                    # 若模型變更，更新 session_state 並重新整理以即時更新上方的顯示
                    if selected_model_name != st.session_state.selected_model_name:
                        st.session_state.selected_model_name = selected_model_name
                        st.rerun()
                        
            except Exception as e:
                st.error(f"模型載入失敗: {e}")
        
        # 已移除「隱藏進階選項」按鈕

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
        # 建立範例資料內容
        sample_csv_content = """Category,Item,Amount,Currency,Frequency
資產,銀行存款,500000,TWD,
資產,台股投資,1200000,TWD,
資產,美股 ETF,30000,USD,
負債,房屋貸款,8000000,TWD,
收入,薪資收入,70000,TWD,Monthly
支出,伙食費,15000,TWD,Monthly
支出,房貸月付,35000,TWD,Monthly
支出,保險費,40000,TWD,Yearly
"""
        st.download_button(
            label="⬇️ 下載範例 CSV",
            data=sample_csv_content.encode("utf-8-sig"),
            file_name="financial_data_sample.csv",
            mime="text/csv",
        )

if uploaded_file is None:
    st.info("請先上傳 CSV 檔以進行編輯與分析（如需範例，右側可下載範例 CSV）。")
    st.stop()

try:
    df = pd.read_csv(uploaded_file)
except Exception as e:
    st.error(f"讀取 CSV 失敗: {e}")
    st.stop()

# 將頻率欄位統一轉為中文，支援舊檔案中的英文寫法
freq_display_map = {
    "Monthly": "每月",
    "Quarterly": "每季",
    "Yearly": "每年",
    "One-time": "單次",
}
if "Frequency" in df.columns:
    df["Frequency"] = df["Frequency"].replace(freq_display_map)

# 2. 以類別分頁顯示/編輯（編輯僅在本次瀏覽器工作階段內有效）
st.markdown("#### 資料編輯區（依類別分頁）")
primary_categories = ["資產", "收入", "負債", "支出"]
tabs = st.tabs([f"{cat}" for cat in primary_categories])
edited_sections = []

for tab, category in zip(tabs, primary_categories):
    with tab:
        # 過濾該類別的資料
        if "Category" in df.columns:
            cat_df = df[df["Category"] == category].copy()
        else:
            cat_df = pd.DataFrame(columns=["Category", "Item", "Amount", "Currency", "Frequency"])

        if cat_df.empty:
            st.info(f"目前沒有 {category} 資料，可直接於下表新增列。")
            # 確保有欄位結構
            if cat_df.empty and not df.empty:
                 cat_df = pd.DataFrame(columns=df.columns)
            elif cat_df.empty:
                 cat_df = pd.DataFrame(columns=["Category", "Item", "Amount", "Currency", "Frequency"])

        # 確保欄位順序與原始資料一致
        cat_df = cat_df.reindex(columns=df.columns)
        
        edited_cat = st.data_editor(
            cat_df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"editor_{category.lower()}",
        )
        # 強制寫回類別，避免新增列失去類別資訊
        if not edited_cat.empty:
            edited_cat["Category"] = category
        edited_sections.append(edited_cat)

# 處理不在主要四類中的資料，避免遺失
if "Category" in df.columns:
    others_df = df[~df["Category"].isin(primary_categories)]
    if not others_df.empty:
        st.warning("偵測到非 資產/收入/負債/支出 類別資料，將維持原狀。")
        edited_sections.append(others_df)

edited_df = pd.concat(edited_sections, ignore_index=True) if edited_sections else pd.DataFrame(columns=df.columns)

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
FREQ_TO_MONTHS = {
    "每月": 1,
    "Monthly": 1,
    "每季": 3,
    "Quarterly": 3,
    "每年": 12,
    "Yearly": 12,
}

def calculate_metrics(df, usdtwd, thbtwd):
    total_asset = 0; total_liability = 0; monthly_income = 0; monthly_expense = 0
    if df.empty: return 0,0,0,0
    
    for _, row in df.iterrows():
        # 簡單防呆：若 Amount 非數字則跳過
        amount = pd.to_numeric(row.get('Amount', 0), errors='coerce')
        if pd.isna(amount): continue
        
        curr = row.get('Currency', 'TWD')
        if curr == 'USD': amount *= usdtwd
        elif curr == 'THB': amount *= thbtwd
        
        cat = row.get('Category', '')
        freq = row.get('Frequency', '')
        
        if cat == '資產': total_asset += amount
        elif cat == '負債': total_liability += amount
        elif cat == '收入':
            months = FREQ_TO_MONTHS.get(freq)
            if months == 1: monthly_income += amount
            elif months == 3: monthly_income += amount / 3
            elif months == 12: monthly_income += amount / 12
        elif cat == '支出':
            months = FREQ_TO_MONTHS.get(freq)
            if months == 1: monthly_expense += amount
            elif months == 3: monthly_expense += amount / 3
            elif months == 12: monthly_expense += amount / 12
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
current_model_short = st.session_state.selected_model_name.replace('models/', '')
st.subheader(f"2. Gemini 財務顧問 (模型: {current_model_short})")

user_question = st.text_area("您想分析什麼？", "請進行整體的財務狀況分析與建議，並預估10年後的資產變化。")

if st.button("Gemini 分析"):
    if not api_key:
        st.warning("請先輸入 Google API Key")
    else:
        try:
            model = genai.GenerativeModel(st.session_state.selected_model_name)
            data_context = edited_df.to_csv(index=False)

            # 把過往對話整理成文字加入系統脈絡
            history_text = ""
            for turn in st.session_state.chat_history:
                history_text += f"使用者：{turn['question']}\nAI：{turn['answer']}\n\n"

            prompt = f"""
            角色：專業財務顧問。
            既有對話紀錄：
            {history_text}

            最新財務數據（CSV）：
            {data_context}

            匯率：USD={USDTWD}, THB={THBTWD}。
            本輪使用者問題：{user_question}。
            要求：繁體中文，Markdown，精確數據，針對未來預測給出樂觀/保守情境，呈現理專或是顧問公司專業報告的格式。
            """
            with st.spinner("正在分析本次問題（會一併考慮同一頁面中的歷史對話）..."):
                response = model.generate_content(prompt)

            # 儲存到 session_state
            st.session_state.chat_history.append(
                {"question": user_question, "answer": response.text}
            )
        except Exception as e:
            st.error(f"錯誤: {e}")

# 顯示目前對話紀錄
if st.session_state.chat_history:
    st.markdown("#### 對話紀錄")
    total_rounds = len(st.session_state.chat_history)
    for i, turn in enumerate(st.session_state.chat_history, start=1):
        is_latest = (i == total_rounds)
        title = f"第 {i} 輪：{turn['question'][:30]}..." if len(turn['question']) > 30 else f"第 {i} 輪：{turn['question']}"
        with st.expander(title, expanded=is_latest):
            st.markdown(f"**你問：** {turn['question']}")
            st.markdown("**AI 回答：**")
            st.markdown(turn['answer'])