import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client
import io
import math

st.set_page_config(page_title="Store Department", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def load_data(table_name):
    try:
        res = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# ดึงข้อมูล
inventory_df = load_data("inventory_db")
cart_df = load_data("cart_db")
transaction_df = load_data("transaction_log")
po_log_df = load_data("po_log")

# ตั้งค่า Pagination
if 'page_inv' not in st.session_state: st.session_state.page_inv = 1
if 'page_hist' not in st.session_state: st.session_state.page_hist = 1
def change_page_inv(delta): st.session_state.page_inv += delta
def change_page_hist(delta): st.session_state.page_hist += delta

st.title("📦 แผนกสโตร์ (Store Management)")

tab1, tab2, tab3, tab4 = st.tabs(["📋 สต๊อกวัสดุ", "🛒 เบิก-รับของ (หน้างาน)", "📥 ตรวจรับของ (จากจัดซื้อ)", "📝 ประวัติเบิกงาน & ยกเลิก"])

# ==========================================
# TAB 1: สต๊อกวัสดุ
# ==========================================
with tab1:
    if not inventory_df.empty:
        inventory_df['Min_Stock'] = inventory_df.get('Min_Stock', 0).fillna(0).astype(int)
        inventory_df['Unit'] = inventory_df.get('Unit', 'ชิ้น').fillna('ชิ้น').astype(str)
        def get_status(row):
            if row['Stock'] <= 0: return "🔴 หมดแล้ว"
            elif row['Stock'] <= row['Min_Stock']: return "🟡 ใกล้หมด"
            return "🟢 ปกติ"
        inventory_df['Status'] = inventory_df.apply(get_status, axis=1)

    with st.expander("➕ สร้างทะเบียนวัสดุใหม่ (New Item)"):
        with st.form("add_new_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            new_code = col1.text_input("รหัสวัสดุ (Item Code) *")
            new_name = col2.text_input("ชื่อวัสดุ/อุปกรณ์ (Item Name) *")
            
            existing_zones = list(inventory_df['Zone'].unique()) if not inventory_df.empty else []
            selected_zone = col1.selectbox("เลือกโซนที่มีอยู่", existing_zones, index=None)
            custom_zone = col1.text_input("➕ หรือ พิมพ์ชื่อโซนใหม่")
            new_unit = col2.text_input("หน่วยนับ *", value="ชิ้น")
            
            cs1, cs2 = st.columns(2)
            new_stock = cs1.number_input("จำนวนรับเข้าล็อตแรก", min_value=0, step=1)
            new_min_stock = cs2.number_input("สต๊อกขั้นต่ำ", min_value=0, step=1, value=0)
            
            if st.form_submit_button("💾 บันทึกวัสดุใหม่เข้าคลัง"):
                final_zone = custom_zone.strip() if custom_zone.strip() != "" else selected_zone
                if not new_code or not new_name or not final_zone or not new_unit.strip():
                    st.error("❌ กรุณากรอกข้อมูลให้ครบถ้วน")
                else:
                    supabase.table("inventory_db").insert({
                        "Item_Code": new_code, "Item_Name": new_name, "Zone": final_zone, 
                        "Stock": int(new_stock), "Min_Stock": int(new_min_stock), "Unit": new_unit.strip()
                    }).execute()
                    st.success("✅ เพิ่มทะเบียนเรียบร้อยแล้ว!")
                    st.rerun()

    with st.expander("🛠️ แก้ไข / ลบ ทะเบียนวัสดุ"):
        if not inventory_df.empty:
            edit_action = st.radio("เลือกโหมดการทำงาน", ["✏️ แก้ไขข้อมูล", "🗑️ ลบวัสดุ"], horizontal=True)
            selected_edit_item = st.selectbox("ค้นหาวัสดุที่ต้องการจัดการ", sorted(inventory_df['Item_Name'].tolist()), index=None)
            
            if selected_edit_item:
                target_row = inventory_df[inventory_df['Item_Name'] == selected_edit_item].iloc[0]
                if edit_action == "✏️ แก้ไขข้อมูล":
                    with st.form("edit_item_form"):
                        c1, c2 = st.columns(2)
                        edit_code = c1.text_input("รหัสวัสดุ", value=target_row['Item_Code'])
                        edit_name = c2.text_input("ชื่อวัสดุ", value=target_row['Item_Name'])
                        
                        ez_list = list(inventory_df['Zone'].unique())
                        edit_zone = c1.selectbox("โซน/หมวดหมู่", ez_list, index=ez_list.index(target_row['Zone']))
                        edit_unit = c2.text_input("หน่วยนับ", value=target_row.get('Unit', 'ชิ้น'))
                        
                        cs1, cs2 = st.columns(2)
                        edit_stock = cs1.number_input("ยอดสต๊อก (ปัจจุบัน)", value=int(target_row['Stock']))
                        edit_min_stock = cs2.number_input("สต๊อกขั้นต่ำ", value=int(target_row.get('Min_Stock', 0)))
                        
                        if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                            supabase.table("inventory_db").update({
                                "Item_Code": edit_code, "Item_Name": edit_name, "Zone": edit_zone, 
                                "Stock": edit_stock, "Min_Stock": edit_min_stock, "Unit": edit_unit.strip()
                            }).eq("id", int(target_row['id'])).execute()
                            st.success("✅ อัปเดตข้อมูลเรียบร้อยแล้ว!")
                            st.rerun()
                elif edit_action == "🗑️ ลบวัสดุ":
                    if st.button("🚨 ยืนยันการลบวัสดุนี้ ถาวร", type="primary"):
                        supabase.table("inventory_db").delete().eq("id", int(target_row['id'])).execute()
                        st.success("✅ ลบทิ้งเรียบร้อยแล้ว!")
                        st.rerun()

    st.subheader("📋 ตารางสต๊อกวัสดุ")
    if not inventory_df.empty:
        if 'stock_filter' not in st.session_state: st.session_state.stock_filter = "แสดงทั้งหมด"
        
        low_stock_cnt = len(inventory_df[inventory_df['Status'] == '🟡 ใกล้หมด'])
        out_stock_cnt = len(inventory_df[inventory_df['Status'] == '🔴 หมดแล้ว'])

        dash1, dash2, dash3 = st.columns(3)
        with dash1:
            st.metric("🟡 ใกล้หมดสต๊อก", f"{low_stock_cnt} รายการ")
            if st.button("🔍 ดูที่ใกล้หมด", use_container_width=True): 
                st.session_state.stock_filter = "🟡 ใกล้หมด"
                st.rerun()
        with dash2:
            st.metric("🔴 หมดสต๊อก", f"{out_stock_cnt} รายการ")
            if st.button("🔍 ดูที่หมดแล้ว", use_container_width=True): 
                st.session_state.stock_filter = "🔴 หมดแล้ว"
                st.rerun()
        with dash3:
            st.metric("🟢 วัสดุทั้งหมด", f"{len(inventory_df)} รายการ")
            if st.button("📋 ดูทั้งหมด", use_container_width=True): 
                st.session_state.stock_filter = "แสดงทั้งหมด"
                st.rerun()

        filtered_by_status = inventory_df[inventory_df['Status'] == st.session_state.stock_filter] if st.session_state.stock_filter != "แสดงทั้งหมด" else inventory_df
        all_zones_display = ["แสดงทุกโซน"] + sorted(list(filtered_by_status['Zone'].unique()))
        selected_zone_view = st.selectbox("📌 ค้นหาเพิ่มเติมตามโซน/ห้อง", all_zones_display, index=None)
        
        view_inv_df = filtered_by_status if not selected_zone_view or selected_zone_view == "แสดงทุกโซน" else filtered_by_status[filtered_by_status['Zone'] == selected_zone_view]
        display_inv_df = view_inv_df.rename(columns={
            "Status": "สถานะ", "Item_Code": "รหัสวัสดุ", "Item_Name": "ชื่อวัสดุ", 
            "Zone": "โซน", "Stock": "ยอดคงเหลือ", "Unit": "หน่วยนับ", "Min_Stock": "ขั้นต่ำ"
        }).drop(columns=['id'], errors='ignore')
        
        display_inv_df = display_inv_df[["สถานะ", "รหัสวัสดุ", "ชื่อวัสดุ", "โซน", "ยอดคงเหลือ", "หน่วยนับ", "ขั้นต่ำ"]]

        total_rows = len(display_inv_df)
        total_pages = max(1, math.ceil(total_rows / 20))
        if st.session_state.page_inv > total_pages or st.session_state.page_inv < 1: st.session_state.page_inv = 1
        start_idx = (st.session_state.page_inv - 1) * 20
        end_idx = start_idx + 20

        st.dataframe(display_inv_df.iloc[start_idx:end_idx], use_container_width=True, hide_index=True)
        
        pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
        with pg_col1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_inv, args=(-1,), disabled=(st.session_state.page_inv <= 1), use_container_width=True, key="prev_inv")
        with pg_col2: st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_idx + 1 if total_rows > 0 else 0} - {min(end_idx, total_rows)} <br>(จากทั้งหมด {total_rows} รายการ)</div>", unsafe_allow_html=True)
        with pg_col3: st.button("หน้าถัดไป ➡️", on_click=change_page_inv, args=(1,), disabled=(st.session_state.page_inv >= total_pages), use_container_width=True, key="next_inv")
        
        st.download_button("📥 ดาวน์โหลดไฟล์ Excel", data=to_excel(display_inv_df), file_name="Stock_Export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

# ==========================================
# TAB 2: เบิก-รับของ (หน้างาน)
# ==========================================
with tab2:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. ข้อมูลบิล")
        with st.container(border=True):
            action = st.radio("ประเภท", ["เบิกออก", "รับเข้า (คืนคลัง)"], horizontal=True)
            worker = st.text_input("ชื่อผู้เบิก/ผู้รับ")
            boat_name = st.text_input("⚓ ชื่อเรือที่ปฏิบัติงาน") 

        st.subheader("2. เลือกวัสดุลงตะกร้า")
        all_zones = ["แสดงทุกโซน"] + list(inventory_df['Zone'].unique()) if not inventory_df.empty else ["แสดงทุกโซน"]
        selected_zone_filter = st.selectbox("📌 กรองตามโซน", all_zones, index=None)
        
        filtered_items = inventory_df['Item_Name'] if not selected_zone_filter or selected_zone_filter == "แสดงทุกโซน" else inventory_df[inventory_df['Zone'] == selected_zone_filter]['Item_Name']

        with st.form("add_to_cart_form", clear_on_submit=True):
            item = st.selectbox("เลือกวัสดุ", filtered_items, index=None)
            qty = st.number_input("จำนวน", min_value=1, step=1)
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item or not worker:
                    st.error("❌ กรุณาเลือกวัสดุ และระบุชื่อให้ครบถ้วน")
                else:
                    current_stock = inventory_df.loc[inventory_df['Item_Name'] == item, 'Stock'].values[0]
                    if action == "เบิกออก" and qty > current_stock:
                        st.error(f"เบิกไม่ได้! {item} มีของแค่ {current_stock}")
                    else:
                        supabase.table("cart_db").insert({
                            "Action": action, "Item_Name": item, "Qty": int(qty), 
                            "Worker": worker, "Boat_Name": boat_name if boat_name else "-" 
                        }).execute()
                        st.success(f"✅ เพิ่ม {item} ลงตะกร้าแล้ว")
                        st.rerun()

    with col2:
        st.subheader("3. ตะกร้าของวันนี้ (รอตัดสต๊อก)")
        if cart_df.empty:
            st.info("ยังไม่มีรายการในตะกร้า")
        else:
            display_cart_df = cart_df.rename(columns={"Action": "ประเภท", "Item_Name": "ชื่อวัสดุ", "Qty": "จำนวน", "Worker": "ผู้เบิก/รับ", "Boat_Name": "ชื่อเรือ"}).drop(columns=['id'])
            st.dataframe(display_cart_df, use_container_width=True, hide_index=True)
            
            c_a, c_b = st.columns(2)
            if c_a.button("🗑️ ล้างตะกร้าทั้งหมด", type="secondary", use_container_width=True):
                supabase.table("cart_db").delete().gte("id", 0).execute()
                st.rerun()
            if c_b.button("💾 ยืนยันตัดสต๊อก", type="primary", use_container_width=True):
                next_bill_num = 1
                if not transaction_df.empty:
                    smy_rows = transaction_df[transaction_df['TxID'].str.startswith('SMY_', na=False)]
                    if not smy_rows.empty:
                        nums = smy_rows['TxID'].apply(lambda x: int(str(x).split('-')[0].replace('SMY_', '')) if '-' in str(x) else 0)
                        next_bill_num = nums.max() + 1
                
                bill_id = f"SMY_{next_bill_num:04d}" 
                tz_th = timezone(timedelta(hours=7))
                current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

                for idx, row in cart_df.iterrows():
                    target_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']].iloc[0]
                    new_stock = target_item['Stock'] - row['Qty'] if row['Action'] == "เบิกออก" else target_item['Stock'] + row['Qty']
                    supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                    
                    supabase.table("transaction_log").insert({
                        "TxID": f"{bill_id}-{idx+1}", "Timestamp": current_time, "Action": row['Action'],
                        "Item_Name": row['Item_Name'], "Qty": int(row['Qty']), "Worker": row['Worker'], 
                        "Boat_Name": row['Boat_Name'], "Status": "Completed"
                    }).execute()
                    
                supabase.table("cart_db").delete().gte("id", 0).execute()
                st.success(f"✅ ตัดสต๊อกเรียบร้อยแล้ว!")
                st.rerun()

# ==========================================
# TAB 3: ตรวจรับของ (จากจัดซื้อ)
# ==========================================
with tab3:
    st.subheader("📦 ตรวจรับของเข้าคลัง (จาก PO)")
    st.caption("เมื่อร้านมาส่งของ ให้สโตร์กดรับของที่นี่ ของจะเข้าสต๊อกอัตโนมัติ")
    
    pending_po = po_log_df[po_log_df['Status'] == 'รอรับของ'].copy() if not po_log_df.empty else pd.DataFrame()
    if not pending_po.empty:
        pending_po['Display_Recv'] = pending_po.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']}) จาก: {row['Shop_Name']}", axis=1)
        
        with st.form("receive_po_form"):
            item_to_receive = st.selectbox("เลือกรายการที่มาส่งแล้ว", pending_po['Display_Recv'], index=None)
            if st.form_submit_button("✅ ยืนยันรับของเข้าสต๊อก"):
                if item_to_receive:
                    target_txid = item_to_receive.split(" | ")[0]
                    tx_data = pending_po[pending_po['TxID'] == target_txid].iloc[0]
                    
                    supabase.table("po_log").update({"Status": "✅ รับแล้ว (เข้าคลัง)"}).eq("TxID", target_txid).execute()
                    
                    target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                    if not target_item.empty:
                        new_stock = target_item.iloc[0]['Stock'] + int(tx_data['Qty'])
                        supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                        st.success(f"🎉 รับ {tx_data['Item_Name']} เข้าสต๊อกเรียบร้อยแล้ว!")
                    st.rerun()
    else:
        st.success("✅ ตอนนี้ไม่มีของค้างส่ง (รับเข้าคลังครบหมดแล้ว)")

# ==========================================
# TAB 4: ประวัติเบิกงาน & ยกเลิก
# ==========================================
with tab4:
    st.subheader("📝 ประวัติเบิก-รับของ & ยกเลิกรายการ")
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        hide_voided = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว", value=True)
        display_df = transaction_df.copy()
        
        if hide_voided:
            display_df = display_df[display_df['Status'] != 'Voided (ยกเลิก)']
            
        display_history_df = display_df.iloc[::-1].rename(columns={
            "TxID": "รหัสบิล", "Timestamp": "เวลา", "Action": "ประเภท", "Item_Name": "ชื่อวัสดุ", 
            "Qty": "จำนวน", "Worker": "ผู้เบิก/ผู้รับ", "Status": "สถานะ", "Boat_Name": "ชื่อเรือ"
        })
        
        total_hist_rows = len(display_history_df)
        total_hist_pages = max(1, math.ceil(total_hist_rows / 20))
        if st.session_state.page_hist > total_hist_pages or st.session_state.page_hist < 1: st.session_state.page_hist = 1
            
        start_h_idx = (st.session_state.page_hist - 1) * 20
        end_h_idx = start_h_idx + 20

        st.dataframe(display_history_df.iloc[start_h_idx:end_h_idx], use_container_width=True, hide_index=True)
        
        pg_h1, pg_h2, pg_h3 = st.columns([1, 2, 1])
        with pg_h1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_hist, args=(-1,), disabled=(st.session_state.page_hist <= 1), use_container_width=True, key="prev_hist")
        with pg_h2: st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการ {start_h_idx + 1 if total_hist_rows > 0 else 0} - {min(end_h_idx, total_hist_rows)}</div>", unsafe_allow_html=True)
        with pg_h3: st.button("หน้าถัดไป ➡️", on_click=change_page_hist, args=(1,), disabled=(st.session_state.page_hist >= total_hist_pages), use_container_width=True, key="next_hist")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ ยกเลิกบิล (ดึงสต๊อกกลับ)")
            valid_tx = transaction_df[transaction_df['Status'] == 'Completed'].copy()
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมด", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True, key="tx_void_mode")
                
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']}", axis=1)
                    with st.form("void_single_form"):
                        tx_to_void = st.selectbox("เลือกรายการ", valid_tx['Display_Single'], index=None)
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if tx_to_void:
                                target_txid = tx_to_void.split(" | ")[0]
                                tx_data = valid_tx[valid_tx['TxID'] == target_txid].iloc[0]
                                
                                target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']].iloc[0]
                                new_stock = target_item['Stock'] + int(tx_data['Qty']) if tx_data['Action'] == "เบิกออก" else target_item['Stock'] - int(tx_data['Qty'])
                                
                                supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                                supabase.table("transaction_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", target_txid).execute()
                                st.success("✅ คืนสต๊อกเรียบร้อย")
                                st.rerun()
                else:
                    valid_tx['Bill_Group'] = valid_tx['TxID'].apply(lambda x: str(x).split('-')[0])
                    group_summary = valid_tx.groupby('Bill_Group').agg({'Worker': 'first', 'Item_Name': 'count'}).reset_index()
                    group_summary['Display_Bulk'] = group_summary.apply(lambda row: f"{row['Bill_Group']} ({row['Item_Name']} รายการ)", axis=1)
                    
                    with st.form("void_bulk_form"):
                        tx_to_void = st.selectbox("เลือกบิล", group_summary['Display_Bulk'], index=None)
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            if tx_to_void:
                                selected_bill_group = tx_to_void.split(" ")[0]
                                tx_to_cancel = valid_tx[valid_tx['Bill_Group'] == selected_bill_group]
                                
                                for _, tx_data in tx_to_cancel.iterrows():
                                    target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']].iloc[0]
                                    new_stock = target_item['Stock'] + int(tx_data['Qty']) if tx_data['Action'] == "เบิกออก" else target_item['Stock'] - int(tx_data['Qty'])
                                    supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item['Item_Code']).execute()
                                    supabase.table("transaction_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", tx_data['TxID']).execute()
                                st.success("✅ ยกเลิกบิลเรียบร้อย")
                                st.rerun()
