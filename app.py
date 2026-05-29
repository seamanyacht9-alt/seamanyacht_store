import streamlit as st
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Shipyard Inventory", layout="wide")

# ==========================================
# 1. จำลองฐานข้อมูล (Session State)
# ==========================================
if 'inventory_db' not in st.session_state:
    st.session_state.inventory_db = pd.DataFrame({
        "Item_Code": ["ENG-001", "CAP-002", "BED-001", "MAT-001"],
        "Item_Name": ["ปั๊มไดโว่สูบน้ำท้องเรือ 24V", "จอ GPS แผนที่ 9 นิ้ว", "ไฟดาวน์ไลท์ LED", "น้ำยาเจลโค้ทสีขาว"],
        "Zone": ["ห้องเครื่อง", "ห้องกัปตัน", "ห้องนอน", "โครงสร้าง/ไฟเบอร์"],
        "Stock": [10, 2, 50, 15]
    })

# ตะกร้าพักรายการ (รอตรวจสอบก่อนตัดสต๊อก)
if 'pending_cart' not in st.session_state:
    st.session_state.pending_cart = []

# ประวัติการทำรายการ (ไว้สำหรับ Void)
if 'transaction_log' not in st.session_state:
    st.session_state.transaction_log = pd.DataFrame(columns=["TxID", "Timestamp", "Action", "Item_Name", "Qty", "Worker", "Status"])

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการคลังอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", ["📦 สต๊อกสินค้าหลัก", "🛒 เบิก-รับของ (ตะกร้า)", "📝 ประวัติ & ยกเลิกรายการ (Void)"])

# ==========================================
# หน้า 1: สต๊อกสินค้าหลัก & ฟอร์มสร้างสินค้าใหม่
# ==========================================
if menu == "📦 สต๊อกสินค้าหลัก":
    st.header("📦 สต๊อกสินค้าคงเหลือ (Master Inventory)")
    
    # --- ฟอร์มสร้างสินค้าชนิดใหม่ (ซ่อนในแถบกดขยายได้) ---
    with st.expander("➕ สร้างทะเบียนสินค้าใหม่ (New Item)"):
        with st.form("add_new_item_form", clear_on_submit=True):
            st.info("ใช้ฟอร์มนี้เมื่อต้องการเพิ่ม 'สินค้าชนิดใหม่' ที่ยังไม่เคยมีในตารางเท่านั้น (ถ้ารับของเข้าปกติ ให้ไปที่เมนูเบิก-รับของ)")
            
            col1, col2 = st.columns(2)
            new_code = col1.text_input("รหัสสินค้า (Item Code) *")
            new_name = col2.text_input("ชื่ออุปกรณ์ (Item Name) *")
            
            # --- ระบบเลือกโซนใหม่ที่อัปเดตแล้ว ---
            existing_zones = list(st.session_state.inventory_db['Zone'].unique())
            selected_zone = col1.selectbox("เลือกโซนที่มีอยู่", existing_zones)
            custom_zone = col1.text_input("➕ หรือ พิมพ์ชื่อโซนใหม่ (ถ้าไม่มีในตัวเลือกด้านบน)")
            # --------------------------------
            
            new_stock = col2.number_input("จำนวนรับเข้าล็อตแรก (ใส่ 0 ถ้าแค่สร้างชื่อเตรียมไว้)", min_value=0, step=1)
            
            submit_new = st.form_submit_button("💾 บันทึกสินค้าใหม่เข้าคลัง")
            
            if submit_new:
                # ลอจิก: ถ้าช่อง custom_zone มีการพิมพ์ข้อความ ให้ใช้โซนใหม่ ถ้าไม่พิมพ์ ให้ใช้ selected_zone
                final_zone = custom_zone.strip() if custom_zone.strip() != "" else selected_zone
                
                if not new_code or not new_name:
                    st.error("❌ กรุณากรอกรหัสสินค้าและชื่ออุปกรณ์ให้ครบถ้วน")
                elif new_code in st.session_state.inventory_db['Item_Code'].values:
                    st.error(f"❌ รหัสสินค้า '{new_code}' มีในระบบแล้ว กรุณาใช้รหัสอื่น")
                elif new_name in st.session_state.inventory_db['Item_Name'].values:
                    st.error(f"❌ ชื่ออุปกรณ์ '{new_name}' มีในระบบแล้ว")
                else:
                    # สร้างข้อมูลแถวใหม่โดยใช้ final_zone
                    new_row = pd.DataFrame({
                        "Item_Code": [new_code],
                        "Item_Name": [new_name],
                        "Zone": [final_zone],
                        "Stock": [new_stock]
                    })
                    
                    st.session_state.inventory_db = pd.concat([st.session_state.inventory_db, new_row], ignore_index=True)
                    st.success(f"✅ เพิ่มทะเบียน '{new_name}' โซน '{final_zone}' เรียบร้อยแล้ว!")
                    st.rerun()

    # --- ตารางแสดงผลสต๊อกหลัก ---
    st.markdown("---")
    st.dataframe(st.session_state.inventory_db, use_container_width=True, hide_index=True)

# ==========================================
# หน้า 2: ระบบเบิก-รับของ แบบพักตะกร้า (ค้นหา + กรองโซน)
# ==========================================
elif menu == "🛒 เบิก-รับของ (ตะกร้า)":
    st.header("🛒 ฟอร์มทำรายการ & ตะกร้าพักของ")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. เพิ่มรายการลงตะกร้า")
        
        # --- ดึงรายชื่อโซนอัตโนมัติ (วางไว้นอก Form เพื่อให้กดปุ๊บกรองปั๊บ) ---
        all_zones = ["แสดงทุกโซน"] + list(st.session_state.inventory_db['Zone'].unique())
        selected_zone_filter = st.selectbox("📌 กรองตามโซน (หมวดหมู่)", all_zones)
        
        if selected_zone_filter == "แสดงทุกโซน":
            filtered_items = st.session_state.inventory_db['Item_Name']
        else:
            filtered_items = st.session_state.inventory_db[st.session_state.inventory_db['Zone'] == selected_zone_filter]['Item_Name']
        # -----------------------------------------------------------

        with st.form("add_to_cart_form", clear_on_submit=True):
            action = st.radio("ประเภท", ["เบิกออก", "รับเข้า"], horizontal=True)
            
            # --- ปรับแก้ selectbox ตรงนี้ (ค้นหาได้) ---
            item = st.selectbox(
                "เลือกอุปกรณ์", 
                filtered_items,
                index=None, 
                placeholder="🔍 พิมพ์ค้นหา หรือคลิกเพื่อเลื่อนดู..." 
            )
            # -----------------------------
            
            qty = st.number_input("จำนวน", min_value=1, step=1)
            worker = st.text_input("ชื่อผู้เบิก/ผู้รับ")
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item:
                    st.error("❌ กรุณาเลือกอุปกรณ์ก่อนกดเพิ่มลงตะกร้า")
                elif not worker:
                    st.error("❌ กรุณาใส่ชื่อผู้เบิก/ผู้รับ")
                else:
                    # เช็คสต๊อกก่อนเบิก
                    current_stock = st.session_state.inventory_db.loc[st.session_state.inventory_db['Item_Name'] == item, 'Stock'].values[0]
                    if action == "เบิกออก" and qty > current_stock:
                        st.error(f"เบิกไม่ได้! {item} มีของในสต๊อกแค่ {current_stock}")
                    else:
                        st.session_state.pending_cart.append({
                            "Action": action,
                            "Item_Name": item,
                            "Qty": qty,
                            "Worker": worker
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
                    new_logs = []
                    for row in st.session_state.pending_cart:
                        idx = st.session_state.inventory_db[st.session_state.inventory_db['Item_Name'] == row['Item_Name']].index[0]
                        if row['Action'] == "เบิกออก":
                            st.session_state.inventory_db.at[idx, 'Stock'] -= row['Qty']
                        else:
                            st.session_state.inventory_db.at[idx, 'Stock'] += row['Qty']
                            
                        new_logs.append({
                            "TxID": str(uuid.uuid4())[:8],
                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Action": row['Action'],
                            "Item_Name": row['Item_Name'],
                            "Qty": row['Qty'],
                            "Worker": row['Worker'],
                            "Status": "Completed"
                        })
                    
                    st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, pd.DataFrame(new_logs)], ignore_index=True)
                    st.session_state.pending_cart = [] 
                    st.success("✅ ตัดสต๊อกและบันทึกประวัติเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 3: ประวัติ และระบบ Void
# ==========================================
elif menu == "📝 ประวัติ & ยกเลิกรายการ (Void)":
    st.header("📝 ประวัติทำรายการ & ยกเลิกบิล")
    
    if st.session_state.transaction_log.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        # แสดงตารางประวัติเรียงจากล่าสุด
        st.dataframe(st.session_state.transaction_log.iloc[::-1], use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("ดึงสต๊อกกลับ (Void Transaction)")
        st.warning("การ Void จะคืนยอดสต๊อกกลับไปยังคลังหลักโดยอัตโนมัติ")
        
        # กรองเฉพาะรายการที่ยังไม่ได้ Void
        valid_tx = st.session_state.transaction_log[st.session_state.transaction_log['Status'] == 'Completed']
        
        if not valid_tx.empty:
            with st.form("void_form"):
                tx_to_void = st.selectbox("เลือก รหัสทำรายการ (TxID) ที่ต้องการยกเลิก", valid_tx['TxID'])
                if st.form_submit_button("⚠️ ยืนยันการยกเลิกรายการ"):
                    # หาข้อมูลรายการนั้น
                    tx_idx = st.session_state.transaction_log[st.session_state.transaction_log['TxID'] == tx_to_void].index[0]
                    tx_data = st.session_state.transaction_log.iloc[tx_idx]
                    
                    item_idx = st.session_state.inventory_db[st.session_state.inventory_db['Item_Name'] == tx_data['Item_Name']].index[0]
                    
                    # คืนค่าสต๊อก (สลับเครื่องหมาย)
                    if tx_data['Action'] == "เบิกออก":
                        st.session_state.inventory_db.at[item_idx, 'Stock'] += tx_data['Qty'] # คืนของเข้า
                    else:
                        st.session_state.inventory_db.at[item_idx, 'Stock'] -= tx_data['Qty'] # ดึงของออก
                        
                    # เปลี่ยนสถานะบิล
                    st.session_state.transaction_log.at[tx_idx, 'Status'] = 'Voided (ยกเลิก)'
                    
                    st.success(f"✅ ยกเลิกรายการ {tx_to_void} และคืนสต๊อกเรียบร้อยแล้ว")
                    st.rerun()