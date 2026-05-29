import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
from supabase import create_client, Client
import io

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

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

inventory_df = load_inventory()
transaction_df = load_transactions()

if 'pending_cart' not in st.session_state:
    st.session_state.pending_cart = []

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการคลังอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", ["📦 สต๊อกสินค้าหลัก", "🛒 เบิก-รับของ (ตะกร้า)", "📝 ประวัติ & ยกเลิกรายการ (Void)"])

# ==========================================
# หน้า 1: สต๊อกสินค้าหลัก
# ==========================================
if menu == "📦 สต๊อกสินค้าหลัก":
    st.header("📦 สต๊อกสินค้าคงเหลือ (Master Inventory)")
    
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
                            "Item_Code": new_code, "Item_Name": new_name, "Zone": final_zone, "Stock": int(new_stock)
                        }).execute()
                        st.success(f"✅ เพิ่มทะเบียน '{new_name}' เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 เกิดข้อผิดพลาดจากฐานข้อมูล: {e}")

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
                                    "Item_Code": edit_code, "Item_Name": edit_name, "Zone": edit_zone, "Stock": edit_stock
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

    st.markdown("---")
    st.subheader("📋 ตารางสต๊อกสินค้า")
    
    if not inventory_df.empty:
        all_zones_display = ["แสดงทุกโซน"] + sorted(list(inventory_df['Zone'].unique()))
        selected_zone_view = st.selectbox("📌 ค้นหาของตามโซน/ห้อง", all_zones_display)
        
        if selected_zone_view == "แสดงทุกโซน":
            view_inv_df = inventory_df
            file_name_inv = "Stock_All_Zones.xlsx"
        else:
            view_inv_df = inventory_df[inventory_df['Zone'] == selected_zone_view]
            file_name_inv = f"Stock_{selected_zone_view}.xlsx"

        display_inv_df = view_inv_df.rename(columns={
            "Item_Code": "รหัสสินค้า", "Item_Name": "ชื่ออุปกรณ์", 
            "Zone": "โซน/หมวดหมู่", "Stock": "ยอดคงเหลือ"
        }).drop(columns=['id'], errors='ignore')
        
        st.dataframe(display_inv_df, use_container_width=True, hide_index=True)
        
        excel_data_inv = to_excel(display_inv_df)
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ Excel (ตารางสต๊อกนี้)", 
            data=excel_data_inv, 
            file_name=file_name_inv, 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

# ==========================================
# หน้า 2: ระบบเบิก-รับของ
# ==========================================
elif menu == "🛒 เบิก-รับของ (ตะกร้า)":
    st.header("🛒 ฟอร์มทำรายการ & ตะกร้าพักของ")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. ข้อมูลบิล (ระบุครั้งเดียว)")
        with st.container(border=True):
            action = st.radio("ประเภท", ["เบิกออก", "รับเข้า"], horizontal=True)
            worker = st.text_input("ชื่อผู้เบิก/ผู้รับ")
            boat_name = st.text_input("⚓ ชื่อเรือที่ปฏิบัติงาน (ใส่หรือไม่ใส่ก็ได้)") 

        st.subheader("2. เลือกอุปกรณ์ลงตะกร้า")
        all_zones = ["แสดงทุกโซน"] + list(inventory_df['Zone'].unique()) if not inventory_df.empty else ["แสดงทุกโซน"]
        selected_zone_filter = st.selectbox("📌 กรองตามโซน (หมวดหมู่)", all_zones)
        
        if selected_zone_filter == "แสดงทุกโซน":
            filtered_items = inventory_df['Item_Name'] if not inventory_df.empty else []
        else:
            filtered_items = inventory_df[inventory_df['Zone'] == selected_zone_filter]['Item_Name']

        with st.form("add_to_cart_form", clear_on_submit=True):
            item = st.selectbox("เลือกอุปกรณ์", filtered_items, index=None, placeholder="🔍 พิมพ์ค้นหา...")
            qty = st.number_input("จำนวน", min_value=1, step=1)
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item or not worker:
                    st.error("❌ กรุณาเลือกอุปกรณ์ และระบุชื่อผู้เบิก (ในกรอบด้านบน) ให้ครบถ้วน")
                else:
                    current_stock = inventory_df.loc[inventory_df['Item_Name'] == item, 'Stock'].values[0]
                    if action == "เบิกออก" and qty > current_stock:
                        st.error(f"เบิกไม่ได้! {item} มีของในสต๊อกแค่ {current_stock}")
                    else:
                        st.session_state.pending_cart.append({
                            "Action": action, "Item_Name": item, "Qty": qty, 
                            "Worker": worker, "Boat_Name": boat_name if boat_name else "-" 
                        })
                        st.success(f"✅ เพิ่ม {item} ลงตะกร้าแล้ว (เลือกชิ้นต่อไปต่อได้เลย)")

    with col2:
        st.subheader("3. ตะกร้าของวันนี้ (รอตัดสต๊อก)")
        if not st.session_state.pending_cart:
            st.info("ยังไม่มีรายการในตะกร้า")
        else:
            cart_df = pd.DataFrame(st.session_state.pending_cart)
            display_cart_df = cart_df.rename(columns={
                "Action": "ประเภท", "Item_Name": "ชื่ออุปกรณ์", "Qty": "จำนวน", 
                "Worker": "ผู้เบิก/รับ", "Boat_Name": "ชื่อเรือ"
            })
            st.dataframe(display_cart_df, use_container_width=True, hide_index=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🗑️ ล้างตะกร้าทั้งหมด", type="secondary"):
                    st.session_state.pending_cart = []
                    st.rerun()
            with col_b:
                if st.button("💾 ยืนยันตัดสต๊อก 1 บิล (Commit)", type="primary"):
                    
                    next_bill_num = 1
                    if not transaction_df.empty:
                        smy_rows = transaction_df[transaction_df['TxID'].str.startswith('SMY_', na=False)]
                        if not smy_rows.empty:
                            nums = smy_rows['TxID'].apply(lambda x: int(str(x).split('-')[0].replace('SMY_', '')) if '-' in str(x) else 0)
                            next_bill_num = nums.max() + 1
                    
                    bill_id = f"SMY_{next_bill_num:04d}" 
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    for idx, row in enumerate(st.session_state.pending_cart):
                        target_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']].iloc[0]
                        new_stock = target_item['Stock'] - row['Qty'] if row['Action'] == "เบิกออก" else target_item['Stock'] + row['Qty']
                        
                        supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                        item_txid = f"{bill_id}-{idx+1}" 

                        supabase.table("transaction_log").insert({
                            "TxID": item_txid, "Timestamp": current_time, "Action": row['Action'],
                            "Item_Name": row['Item_Name'], "Qty": int(row['Qty']),
                            "Worker": row['Worker'], "Boat_Name": row['Boat_Name'], "Status": "Completed"
                        }).execute()
                        
                    st.session_state.pending_cart = [] 
                    st.success(f"✅ ตัดสต๊อกและบันทึกรหัสบิล {bill_id} เรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 3: ประวัติ (เพิ่มปุ่มลบถาวร & ซ่อนบิล Void)
# ==========================================
elif menu == "📝 ประวัติ & ยกเลิกรายการ (Void)":
    st.header("📝 ประวัติทำรายการ & ยกเลิกบิล")
    
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        # ฟิลเตอร์กรองตามชื่อเรือ
        if 'Boat_Name' in transaction_df.columns:
            unique_boats = [b for b in transaction_df['Boat_Name'].unique() if pd.notna(b) and b != "-"]
            all_boat_options = ["📋 ดูประวัติทั้งหมด"] + unique_boats
            selected_boat_filter = st.selectbox("⚓ ค้นหาประวัติการเบิกตามชื่อเรือ", all_boat_options)
            
            if selected_boat_filter == "📋 ดูประวัติทั้งหมด":
                base_df = transaction_df
                file_name_hist = "History_All_Boats.xlsx"
            else:
                base_df = transaction_df[transaction_df['Boat_Name'] == selected_boat_filter]
                file_name_hist = f"History_Boat_{selected_boat_filter}.xlsx"
        else:
            base_df = transaction_df 
            file_name_hist = "History_All.xlsx"
            
        # สวิตช์เปิด-ปิด การซ่อนบิลที่ยกเลิกแล้ว
        hide_voided = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว (Voided) จากตารางด้านล่าง", value=True)
        
        display_df = base_df.copy()
        if hide_voided:
            display_df = display_df[display_df['Status'] != 'Voided (ยกเลิก)']
            
        display_history_df = display_df.iloc[::-1].rename(columns={
            "TxID": "รหัสบิล", "Timestamp": "วันเวลาที่ทำรายการ", "Action": "ประเภท",
            "Item_Name": "ชื่ออุปกรณ์", "Qty": "จำนวน", "Worker": "ผู้เบิก/ผู้รับ",
            "Status": "สถานะ", "Boat_Name": "ชื่อเรือ"
        })
        
        st.dataframe(display_history_df, use_container_width=True, hide_index=True)
        
        excel_data_hist = to_excel(display_history_df)
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ Excel (ประวัติที่แสดงนี้)", 
            data=excel_data_hist, file_name=file_name_hist, 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary"
        )
        
        st.markdown("---")
        
        # --- แบ่งเป็น 2 คอลัมน์: ยกเลิก(คืนสต๊อก) vs ลบทิ้งถาวร ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚠️ ดึงสต๊อกกลับ (Void Transaction)")
            st.caption("สถานะจะเปลี่ยนเป็นยกเลิก และของจะเด้งกลับเข้าคลัง")
            valid_tx = base_df[base_df['Status'] == 'Completed'].copy()
            
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True)
                
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} ชิ้น)", axis=1)
                    with st.form("void_single_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการ", valid_tx['Display_Single'])
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            target_txid = tx_to_void_display.split(" | ")[0]
                            tx_data = valid_tx[valid_tx['TxID'] == target_txid].iloc[0]
                            target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']].iloc[0]
                            
                            new_stock = target_item['Stock'] + int(tx_data['Qty']) if tx_data['Action'] == "เบิกออก" else target_item['Stock'] - int(tx_data['Qty'])
                            supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                            supabase.table("transaction_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", target_txid).execute()
                            
                            st.success(f"✅ ยกเลิกรายการ {target_txid} และคืนสต๊อกเรียบร้อย")
                            st.rerun()

                else:
                    valid_tx['Bill_Group'] = valid_tx['TxID'].apply(lambda x: str(x).split('-')[0])
                    group_summary = valid_tx.groupby('Bill_Group').agg({'Worker': 'first', 'Item_Name': 'count'}).reset_index()
                    group_summary['Display_Bulk'] = group_summary.apply(lambda row: f"{row['Bill_Group']} | โดย: {row['Worker']} ({row['Item_Name']} รายการ)", axis=1)

                    with st.form("void_bulk_form"):
                        tx_to_void_display = st.selectbox("เลือกบิล", group_summary['Display_Bulk'])
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            selected_bill_group = tx_to_void_display.split(" | ")[0]
                            tx_to_cancel = valid_tx[valid_tx['Bill_Group'] == selected_bill_group]
                            
                            for _, tx_data in tx_to_cancel.iterrows():
                                target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']].iloc[0]
                                new_stock = target_item['Stock'] + int(tx_data['Qty']) if tx_data['Action'] == "เบิกออก" else target_item['Stock'] - int(tx_data['Qty'])
                                supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                                supabase.table("transaction_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", tx_data['TxID']).execute()
                                
                            st.success(f"✅ ยกเลิกบิล {selected_bill_group} เรียบร้อย")
                            st.rerun()

        with col2:
            st.subheader("🗑️ ลบประวัติถาวร (Hard Delete)")
            st.caption("ลบหายไปจากระบบ (ไม่ดึงสต๊อกกลับ ใช้สำหรับลบขยะ)")
            
            # ดึงข้อมูลมาโชว์ในกล่องลบถาวร (แสดงทั้งบิลปกติและบิล Void)
            base_df['Display_Del'] = base_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            
            with st.form("hard_delete_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", base_df['Display_Del'])
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    target_txid = tx_to_delete.split(" | ")[0]
                    # ยิงคำสั่ง Delete ไปที่ Supabase
                    supabase.table("transaction_log").delete().eq("TxID", target_txid).execute()
                    
                    st.success(f"✅ ลบประวัติ {target_txid} ออกจากระบบถาวรแล้ว!")
                    st.rerun()
