import streamlit as st
import pandas as pd
import google.generativeai as genai
from github import Github # 引入 GitHub 套件
from datetime import datetime
import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# --- 設定頁面 ---
st.set_page_config(page_title="家庭財務AI中控台", layout="wide")
st.title("📊 家庭財務 AI 中控台")

# --- 讀取 Secrets ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    github_token = st.secrets["GITHUB_TOKEN"]
    repo_name = st.secrets["GITHUB_REPO"]
    file_path = st.secrets["CSV_FILE_PATH"]
except KeyError as e:
    st.error(f"缺少 Secrets 設定: {e}。請至 Streamlit Cloud 設定 Secrets。")
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

# --- 函數：從 GitHub 讀取 CSV ---
# 使用 @st.cache_data 避免每次動作都重新抓取 GitHub，只有在存檔後清除快取
@st.cache_data(ttl=600) 
def load_data_from_github():
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(file_path)
        # 解碼 CSV 內容
        decoded_content = contents.decoded_content.decode("utf-8")
        return pd.read_csv(io.StringIO(decoded_content))
    except Exception as e:
        st.error(f"無法從 GitHub 讀取數據: {e}")
        return pd.DataFrame()

# --- 函數：寫入數據回 GitHub ---
def save_data_to_github(df):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(file_path) # 取得目前檔案資訊(為了拿到sha)
        
        # 將 DataFrame 轉回 CSV 字串
        csv_content = df.to_csv(index=False)
        
        # 更新 GitHub 檔案
        repo.update_file(
            path=contents.path,
            message="Update via Streamlit App", # Commit message
            content=csv_content,
            sha=contents.sha # 必須提供原本的 sha 才能覆蓋
        )
        return True
    except Exception as e:
        st.error(f"儲存失敗: {e}")
        return False

# --- 主程式邏輯 ---

# 1. 載入數據
if 'data_loaded' not in st.session_state:
    st.session_state.df = load_data_from_github()
    st.session_state.data_loaded = True

# 2. 顯示編輯器
st.subheader("1. 資產與收支明細管理")
col_edit, col_save = st.columns([4, 1])

with col_edit:
    # 這裡讓使用者編輯，並將結果存到 edited_df
    edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True, key="editor")

with col_save:
    st.write(" ") # 排版用
    st.write(" ") 
    # 存檔按鈕
    if st.button("💾 儲存至雲端 (GitHub)", type="primary"):
        with st.spinner("正在寫入 GitHub..."):
            if save_data_to_github(edited_df):
                st.success("✅ 儲存成功！數據已更新。")
                # 更新 session state 並清除快取，確保下次讀取是新的
                st.session_state.df = edited_df
                load_data_from_github.clear()
            else:
                st.error("儲存失敗，請檢查 Token 權限。")

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

# --- PDF 報告生成 ---
def create_financial_report_pdf(df, asset, liability, net, income, expense, net_flow, usdtwd, thbtwd):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    def next_line(text="", font="Helvetica", size=11, leading=16):
        nonlocal y
        if y < 60:
            pdf.showPage()
            y = height - 50
        pdf.setFont(font, size)
        pdf.drawString(50, y, text)
        y -= leading

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    next_line("家庭財務報告", "Helvetica-Bold", 18, 26)
    next_line(f"生成時間：{generated_at}", leading=20)
    next_line(f"USD/TWD：{usdtwd}    THB/TWD：{thbtwd}", leading=20)
    next_line()

    next_line("核心指標", "Helvetica-Bold", 14, 22)
    next_line(f"總資產：NT$ {asset:,.0f}")
    next_line(f"總負債：NT$ {liability:,.0f}")
    next_line(f"淨資產：NT$ {net:,.0f}")
    next_line(f"每月收入：NT$ {income:,.0f}")
    next_line(f"每月支出：NT$ {expense:,.0f}")
    next_line(f"每月現金流：NT$ {net_flow:,.0f}")
    next_line()

    next_line("數據概覽", "Helvetica-Bold", 14, 22)
    next_line(f"資料筆數：{len(df)}")
    if not df.empty:
        category_counts = df['Category'].value_counts().to_dict()
        for cat, count in category_counts.items():
            next_line(f"{cat}：{count} 筆")
        next_line()

        next_line("最高金額項目 (前 5)", "Helvetica-Bold", 12, 18)
        top_rows = df.copy()
        top_rows['AmountNumeric'] = pd.to_numeric(top_rows['Amount'], errors='coerce')
        top_rows = top_rows.dropna(subset=['AmountNumeric']).sort_values(by='AmountNumeric', ascending=False).head(5)
        for _, row in top_rows.iterrows():
            amount = row['AmountNumeric']
            next_line(f"{row['Name']} - {row['Category']} - {row['Currency']} {amount:,.2f}")
    else:
        next_line("目前沒有可用的數據。")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

# --- 4. 儀表板顯示 ---
st.markdown("---")
kpi_toggle_col, _ = st.columns([1, 5])

if 'hide_kpi' not in st.session_state:
    st.session_state.hide_kpi = False

with kpi_toggle_col:
    if st.button("顯示金額", help="點擊以隱藏或顯示 KPI 數值"):
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
            要求：繁體中文，Markdown，精確數據，針對未來預測給出樂觀/保守情境。
            """
            with st.spinner(f"正在分析..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
        except Exception as e: st.error(f"錯誤: {e}")

# --- 6. 財務報告下載 ---
st.markdown("---")
st.subheader("3. 財務報告 PDF 下載")
pdf_bytes = create_financial_report_pdf(
    edited_df,
    t_asset,
    t_liability,
    net_worth,
    m_income,
    m_expense,
    monthly_net_flow,
    USDTWD,
    THBTWD,
)
st.download_button(
    label="📄 下載財務報告 PDF",
    data=pdf_bytes,
    file_name=f"financial_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
    mime="application/pdf",
)