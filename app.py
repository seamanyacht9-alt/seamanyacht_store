import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
from supabase import create_client, Client

st.set_page_config(page_title="Shipyard Inventory", layout="wide")

# ==========================================
# 1. ตั้งค่าเชื่อมต่อ Supabase
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# ฟังก์ชันดึงข้อมูลแบบ Real-time (ดัก Error เผื่อไว้)
def load_inventory():
    try:
        res = supabase.table("inventory_db").select("*").order("id").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"🚨 แจ้งเตือนจาก Supabase (inventory_db): {e}")
        return pd.DataFrame()

def load_transactions():
    try:
        res = supabase.table("transaction_log").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"🚨 แจ้งเตือนจาก Supabase (transaction_log): {e}")
        return pd.DataFrame()

# ดึงข้อมูลมาเก็บไว้ใช้งาน
inventory_df = load_inventory()
transaction_df = load_transactions()

# ตะกร้าพักรายการ
if 'pending_cart' not in st.session_state:
    st.session_state.pending_cart = []

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการคลังอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", ["📦 สต๊อกสินค้าหลัก", "🛒 เบิก-รับของ (ตะกร้า)", "📝 ประวัติ & ยกเลิกรายการ (Void)"])

# ==========================================
# หน้า 1: สต๊อกสินค้าหลัก (เพิ่ม/แก้ไข/ลบ)
# ==========================================
if menu == "📦 สต๊อกสินค้าหลัก":
    st.header("📦 สต๊อกสินค้าคงเหลือ (Master Inventory)")
    
    # --- ฟอร์มสร้างสินค้าชนิดใหม่ ---
    with st.expander("➕ สร้างทะเบียนสินค้าใหม่ (New Item)"):
        with st.form("add_new_item_form", clear_on_submit=True):
            col1, col2 = st.columns(
