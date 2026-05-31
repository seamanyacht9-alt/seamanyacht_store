import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Shipyard Dashboard", layout="wide")

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

st.header("📊 แดชบอร์ดสรุปข้อมูลอู่เรือ")

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

c_graph, c_alert = st.columns([2, 1])

with c_graph:
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

with c_alert:
    st.subheader("🚨 แจ้งเตือนของใกล้หมด")
    if not inventory_df.empty and low_stock_count > 0:
        low_stock_df = inventory_df[inventory_df['Stock'] <= inventory_df['Min_Stock']][['Item_Name', 'Stock', 'Min_Stock', 'Unit']]
        st.dataframe(low_stock_df.rename(columns={"Item_Name":"ชื่อวัสดุ", "Stock":"คงเหลือ", "Min_Stock":"ขั้นต่ำ", "Unit":"หน่วย"}), hide_index=True, use_container_width=True)
        st.error("กรุณาทำใบขอซื้อสำหรับรายการนี้โดยด่วน!")
    else:
        st.success("✅ สต๊อกวัสดุทุกรายการอยู่ในเกณฑ์ปกติ")
