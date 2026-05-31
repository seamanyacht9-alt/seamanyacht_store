import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="SEAMAN-YACHT Dashboard", layout="wide")

# ==========================================
# 1. ตั้งค่าเชื่อมต่อ Supabase
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

def load_data(table_name):
    try:
        res = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

# ดึงข้อมูลสำหรับแดชบอร์ด
inventory_df = load_data("inventory_db")
transaction_df = load_data("transaction_log")
po_log_df = load_data("po_log")

# ==========================================
# แดชบอร์ดภาพรวม
# ==========================================
st.sidebar.success("👆 เลือกระบบของแต่ละแผนกจากเมนูด้านบน")

# --- เปลี่ยนหัวเว็บตามที่ขอ ---
st.title("🛥️ SEAMAN-YACHT Dashboard")
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
total_items = len(inventory_df) if not inventory_df.empty else 0

low_stock_count = 0
if not inventory_df.empty:
    inventory_df['Min_Stock'] = inventory_df.get('Min_Stock', 0).fillna(0).astype(int)
    low_stock_count = len(inventory_df[inventory_df['Stock'] <= inventory_df['Min_Stock']])
    
if not po_log_df.empty:
    valid_po_spent = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
    total_po_spent = valid_po_spent['Net_Price'].sum()
else:
    total_po_spent = 0
    
if not transaction_df.empty:
    total_withdraws = len(transaction_df[(transaction_df['Action'] == 'เบิกออก') & (transaction_df['Status'] == 'Completed')])
else:
    total_withdraws = 0

with col1:
    st.metric("📦 รายการวัสดุทั้งหมด", f"{total_items} รายการ")
with col2:
    st.metric("⚠️ วัสดุใกล้หมดสต๊อก", f"{low_stock_count} รายการ")
with col3:
    st.metric("💸 ยอดสั่งซื้อทั้งหมด", f"฿ {total_po_spent:,.2f}")
with col4:
    st.metric("🔧 จำนวนครั้งที่เบิกของ", f"{total_withdraws} ครั้ง")

st.markdown("---")

# ปรับคอลัมน์ให้แบ่งครึ่งเท่าๆ กัน สำหรับโชว์ 2 กราฟ
c_graph1, c_graph2 = st.columns(2)

with c_graph1:
    st.subheader("📈 ยอดการสั่งซื้อแยกตามร้านค้า")
    if not po_log_df.empty:
        valid_po = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
        if not valid_po.empty:
            shop_spent = valid_po.groupby('Shop_Name')['Net_Price'].sum().reset_index()
            shop_spent.set_index('Shop_Name', inplace=True)
            st.bar_chart(shop_spent)
        else:
            st.info("ยังไม่มีข้อมูลค่าใช้จ่าย")
    else:
        st.info("ยังไม่มีข้อมูลประวัติจัดซื้อ")

with c_graph2:
    st.subheader("📅 สรุปยอดค่าใช้จ่ายรายเดือน")
    if not po_log_df.empty:
        # กรองเอาเฉพาะบิลที่ไม่ถูกยกเลิก
        valid_po = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])].copy()
        if not valid_po.empty:
            # แปลง Timestamp เป็นรูปแบบ เดือน-ปี (เช่น 2026-05)
            valid_po['Timestamp'] = pd.to_datetime(valid_po['Timestamp'])
            valid_po['Month_Year'] = valid_po['Timestamp'].dt.strftime('%Y-%m')
            
            # รวมยอดเงินตามเดือน
            monthly_spent = valid_po.groupby('Month_Year')['Net_Price'].sum().reset_index()
            monthly_spent = monthly_spent.sort_values('Month_Year')
            
            # สร้างช่องเลือกเดือน เพื่อดูยอดเจาะจง (ตั้งค่าเริ่มต้นให้เป็นเดือนล่าสุด)
            selected_month = st.selectbox("📌 เลือกระบุเดือนที่ต้องการดูยอด", monthly_spent['Month_Year'].tolist(), index=len(monthly_spent)-1)
            
            if selected_month:
                month_total = monthly_spent[monthly_spent['Month_Year'] == selected_month]['Net_Price'].values[0]
                st.markdown(f"<h3 style='color: #2e7d32;'>ยอดรวมเดือน {selected_month}: ฿ {month_total:,.2f}</h3>", unsafe_allow_html=True)
            
            # สร้างกราฟแท่งรายเดือน
            chart_data = monthly_spent.set_index('Month_Year')
            st.bar_chart(chart_data)
        else:
            st.info("ยังไม่มีข้อมูลสำหรับสร้างกราฟรายเดือน")
    else:
        st.info("ยังไม่มีข้อมูลประวัติจัดซื้อ")
