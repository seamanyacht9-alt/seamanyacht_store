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
            col1, col2 = st.columns(2)
            new_code = col1.text_input("รหัสสินค้า (Item Code) *")
            new_name = col2.text_input("ชื่ออุปกรณ์ (Item Name) *")
            
            existing_zones = list(inventory_df['Zone'].unique()) if not inventory_df.empty else []
            selected_zone = col1.selectbox("เลือกโซนที่มีอยู่", existing_zones)
            custom_zone = col1.text_input("➕ หรือ พิมพ์ชื่อโซนใหม่")
            
            new_stock = col2.number_input("จำนวนรับเข้าล็อตแรก (ใส่ 0 ถ้าแค่สร้างชื่อเตรียมไว้)", min_value=0, step=1)
            submit_new = st.form_submit_button("💾 บันทึกสินค้าใหม่เข้าคลัง")
            
            if submit_new:
                final_zone = custom_zone.strip() if custom_zone.strip() != "" else selected_zone
                
                if not new_code or not new_name:
                    st.error("❌ กรุณากรอกรหัสสินค้าและชื่ออุปกรณ์ให้ครบถ้วน")
                elif not inventory_df.empty and new_code in inventory_df['Item_Code'].values:
                    st.error(f"❌ รหัสสินค้า '{new_code}' มีในระบบแล้ว")
                elif not inventory_df.empty and new_name in inventory_df['Item_Name'].values:
                    st.error(f"❌ ชื่ออุปกรณ์ '{new_name}' มีในระบบแล้ว")
                else:
                    try:
                        supabase.table("inventory_db").insert({
                            "Item_Code": new_code,
                            "Item_Name": new_name,
                            "Zone": final_zone,
                            "Stock": int(new_stock)
                        }).execute()
                        st.success(f"✅ เพิ่มทะเบียน '{new_name}' เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 เกิดข้อผิดพลาดจากฐานข้อมูล: {e}")

    # --- ระบบแก้ไข / ลบ ข้อมูลสินค้า ---
    with st.expander("🛠️ แก้ไข / ลบ ทะเบียนสินค้า (Edit & Delete)"):
        if not inventory_df.empty:
            edit_action = st.radio("เลือกโหมดการทำงาน", ["✏️ แก้ไขข้อมูล", "🗑️ ลบสินค้า"], horizontal=True)
            
            item_list = sorted(inventory_df['Item_Name'].tolist())
            selected_edit_item = st.selectbox("ค้นหาสินค้าที่ต้องการจัดการ", item_list, index=None, placeholder="🔍 พิมพ์หรือเลือกชื่ออุปกรณ์...")
            
            if selected_edit_item:
                target_row = inventory_df[inventory_df['Item_Name'] == selected_edit_item].iloc[0]
                target_id = int(target_row['id']) 
                
                if edit_action == "✏️ แก้ไขข้อมูล":
                    with st.form("edit_item_form"):
                        st.info("แก้คำผิด เปลี่ยนหมวดหมู่ หรือปรับยอดสต๊อกที่นับพลาดได้เลย")
                        col1, col2 = st.columns(2)
                        edit_code = col1.text_input("รหัสสินค้า", value=target_row['Item_Code'])
                        edit_name = col2.text_input("ชื่ออุปกรณ์", value=target_row['Item_Name'])
                        
                        existing_zones_edit = list(inventory_df['Zone'].unique())
                        zone_idx = existing_zones_edit.index(target_row['Zone']) if target_row['Zone'] in existing_zones_edit else 0
                        edit_zone = col1.selectbox("โซน/หมวดหมู่", existing_zones_edit, index=zone_idx)
                        
                        edit_stock = col2.number_input("ยอดสต๊อก (ปัจจุบัน)", value=int(target_row['Stock']), min_value=0, step=1)
                        
                        if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                            try:
                                supabase.table("inventory_db").update({
                                    "Item_Code": edit_code,
                                    "Item_Name": edit_name,
                                    "Zone": edit_zone,
                                    "Stock": edit_stock
                                }).eq("id", target_id).execute()
                                st.success("✅ อัปเดตข้อมูลเรียบร้อยแล้ว!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"🚨 อัปเดตไม่สำเร็จ: {e}")
                                
                elif edit_action == "🗑️ ลบสินค้า":
                    st.warning(f"⚠️ คุณกำลังจะลบ **{selected_edit_item}** หากลบแล้วจะไม่สามารถกู้คืนได้!")
                    if st.button("🚨 ยืนยันการลบสินค้านี้ ถาวร", type="primary"):
                        try:
                            supabase.table("inventory_db").delete().eq("id", target_id).execute()
                            st.success("✅ ลบทิ้งเรียบร้อยแล้ว!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"🚨 ลบไม่สำเร็จ: {e}")

    # --- ตารางแสดงผลสต๊อกหลัก ---
    st.markdown("---")
    st.dataframe(inventory_df, use_container_width=True, hide_index=True)

# ==========================================
# หน้า 2: ระบบเบิก-รับของ
# ==========================================
elif menu == "🛒 เบิก-รับของ (ตะกร้า)":
    st.header("🛒 ฟอร์มทำรายการ & ตะกร้าพักของ")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. เพิ่มรายการลงตะกร้า")
        all_zones = ["แสดงทุกโซน"] + list(inventory_df['Zone'].unique()) if not inventory_df.empty else ["แสดงทุกโซน"]
        selected_zone_filter = st.selectbox("📌 กรองตามโซน (หมวดหมู่)", all_zones)
        
        if selected_zone_filter == "แสดงทุกโซน":
            filtered_items = inventory_df['Item_Name'] if not inventory_df.empty else []
        else:
            filtered_items = inventory_df[inventory_df['Zone'] == selected_zone_filter]['Item_Name']

        with st.form("add_to_cart_form", clear_on_submit=True):
            action = st.radio("ประเภท", ["เบิกออก", "รับเข้า"], horizontal=True)
            item = st.selectbox("เลือกอุปกรณ์", filtered_items, index=None, placeholder="🔍 พิมพ์ค้นหา...")
            qty = st.number_input("จำนวน", min_value=1, step=1)
            worker = st.text_input("ชื่อผู้เบิก/ผู้รับ")
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item or not worker:
                    st.error("❌ กรุณาเลือกอุปกรณ์และใส่ชื่อผู้เบิก")
                else:
                    current_stock = inventory_df.loc[inventory_df['Item_Name'] == item, 'Stock'].values[0]
                    if action == "เบิกออก" and qty > current_stock:
                        st.error(f"เบิกไม่ได้! {item} มีของในสต๊อกแค่ {current_stock}")
                    else:
                        st.session_state.pending_cart.append({
                            "Action": action, "Item_Name": item, "Qty": qty, "Worker": worker
                        })
                        st.success("✅ เพิ่มลงตะกร้าสำเร็จ")

    with col2:
        st.subheader("2. ตะกร้าของวันนี้ (รอตัดสต๊อก)")
        if not st.session_state.pending_cart:
            st.info("ยังไม่มีรายการในตะกร้า")
        else:
            cart_df = pd.DataFrame(st.session_state.pending_cart)
            st.dataframe(cart_df, use_container_width=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🗑️ ล้างตะกร้าทั้งหมด", type="secondary"):
                    st.session_state.pending_cart = []
                    st.rerun()
            with col_b:
                if st.button("💾 ยืนยันตัดสต๊อก (Commit)", type="primary"):
                    for row in st.session_state.pending_cart:
                        target_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']].iloc[0]
                        new_stock = target_item['Stock'] - row['Qty'] if row['Action'] == "เบิกออก" else target_item['Stock'] + row['Qty']
                        
                        supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                        
                        supabase.table("transaction_log").insert({
                            "TxID": str(uuid.uuid4())[:8],
                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Action": row['Action'],
                            "Item_Name": row['Item_Name'],
                            "Qty": int(row['Qty']),
                            "Worker": row['Worker'],
                            "Status": "Completed"
                        }).execute()
                        
                    st.session_state.pending_cart = [] 
                    st.success("✅ ตัดสต๊อกและบันทึกประวัติเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 3: ประวัติ และระบบ Void
# ==========================================
elif menu == "📝 ประวัติ & ยกเลิกรายการ (Void)":
    st.header("📝 ประวัติทำรายการ & ยกเลิกบิล")
    
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        st.dataframe(transaction_df.iloc[::-1], use_container_width=True, hide_index=True)
        st.markdown("---")
        st.subheader("ดึงสต๊อกกลับ (Void Transaction)")
        
        valid_tx = transaction_df[transaction_df['Status'] == 'Completed']
        if not valid_tx.empty:
            with st.form("void_form"):
                tx_to_void = st.selectbox("เลือก รหัสทำรายการ (TxID) ที่ต้องการยกเลิก", valid_tx['TxID'])
                if st.form_submit_button("⚠️ ยืนยันการยกเลิกรายการ"):
                    tx_data = transaction_df[transaction_df['TxID'] == tx_to_void].iloc[0]
                    target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']].iloc[0]
                    
                    new_stock = target_item['Stock'] + int(tx_data['Qty']) if tx_data['Action'] == "เบิกออก" else target_item['Stock'] - int(tx_data['Qty'])
                    supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                    
                    supabase.table("transaction_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", tx_to_void).execute()
                    
                    st.success(f"✅ ยกเลิกรายการ {tx_to_void} และคืนสต๊อกเรียบร้อยแล้ว")
                    st.rerun()
