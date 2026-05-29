import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import uuid
from supabase import create_client, Client
import io
import math

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

def change_page_inv(delta):
    st.session_state.page_inv += delta

def change_page_hist(delta):
    st.session_state.page_hist += delta

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการคลังอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", ["📦 สต๊อกวัสดุ", "🛒 เบิก-รับของ (ตะกร้า)", "📝 ประวัติ & ยกเลิกรายการ (Void)"])

# ==========================================
# หน้า 1: สต๊อกวัสดุ
# ==========================================
if menu == "📦 สต๊อกวัสดุ":
    st.header("📦 สต๊อกวัสดุคงเหลือ (Master Inventory)")
    
    if not inventory_df.empty:
        if 'Min_Stock' not in inventory_df.columns:
            inventory_df['Min_Stock'] = 0
        inventory_df['Min_Stock'] = inventory_df['Min_Stock'].fillna(0).astype(int)
        
        def get_status(row):
            if row['Stock'] <= 0:
                return "🔴 หมดแล้ว"
            elif row['Stock'] <= row['Min_Stock']:
                return "🟡 ใกล้หมด"
            return "🟢 ปกติ"
        inventory_df['Status'] = inventory_df.apply(get_status, axis=1)
    
    with st.expander("➕ สร้างทะเบียนวัสดุใหม่ (New Item)"):
        with st.form("add_new_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            new_code = col1.text_input("รหัสวัสดุ (Item Code) *")
            new_name = col2.text_input("ชื่อวัสดุ/อุปกรณ์ (Item Name) *")
            
            existing_zones = list(inventory_df['Zone'].unique()) if not inventory_df.empty else []
            selected_zone = col1.selectbox("เลือกโซนที่มีอยู่", existing_zones, index=None, placeholder="พิมพ์หรือเลือกโซน...")
            custom_zone = col1.text_input("➕ หรือ พิมพ์ชื่อโซนใหม่")
            
            col_s1, col_s2 = st.columns(2)
            new_stock = col_s1.number_input("จำนวนรับเข้าล็อตแรก (ใส่ 0 ถ้าแค่สร้างชื่อเตรียมไว้)", min_value=0, step=1)
            new_min_stock = col_s2.number_input("สต๊อกขั้นต่ำ (ใส่ 0 ถ้าระบบไม่ต้องแจ้งเตือน)", min_value=0, step=1, value=0)
            
            submit_new = st.form_submit_button("💾 บันทึกวัสดุใหม่เข้าคลัง")
            
            if submit_new:
                final_zone = custom_zone.strip() if custom_zone.strip() != "" else selected_zone
                if not new_code or not new_name or not final_zone:
                    st.error("❌ กรุณากรอกรหัสวัสดุ ชื่อวัสดุ และโซนให้ครบถ้วน")
                elif not inventory_df.empty and new_code in inventory_df['Item_Code'].values:
                    st.error(f"❌ รหัสวัสดุ '{new_code}' มีในระบบแล้ว")
                elif not inventory_df.empty and new_name in inventory_df['Item_Name'].values:
                    st.error(f"❌ ชื่อวัสดุ '{new_name}' มีในระบบแล้ว")
                else:
                    try:
                        supabase.table("inventory_db").insert({
                            "Item_Code": new_code, "Item_Name": new_name, "Zone": final_zone, 
                            "Stock": int(new_stock), "Min_Stock": int(new_min_stock)
                        }).execute()
                        st.success(f"✅ เพิ่มทะเบียน '{new_name}' เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 เกิดข้อผิดพลาดจากฐานข้อมูล: {e}")

    with st.expander("🛠️ แก้ไข / ลบ ทะเบียนวัสดุ (Edit & Delete)"):
        if not inventory_df.empty:
            edit_action = st.radio("เลือกโหมดการทำงาน", ["✏️ แก้ไขข้อมูล", "🗑️ ลบวัสดุ"], horizontal=True)
            item_list = sorted(inventory_df['Item_Name'].tolist())
            selected_edit_item = st.selectbox("ค้นหาวัสดุที่ต้องการจัดการ", item_list, index=None, placeholder="🔍 พิมพ์ชื่อวัสดุ...")
            
            if selected_edit_item:
                target_row = inventory_df[inventory_df['Item_Name'] == selected_edit_item].iloc[0]
                target_id = int(target_row['id']) 
                
                if edit_action == "✏️ แก้ไขข้อมูล":
                    with st.form("edit_item_form"):
                        col1, col2 = st.columns(2)
                        edit_code = col1.text_input("รหัสวัสดุ", value=target_row['Item_Code'])
                        edit_name = col2.text_input("ชื่อวัสดุ", value=target_row['Item_Name'])
                        
                        existing_zones_edit = list(inventory_df['Zone'].unique())
                        zone_idx = existing_zones_edit.index(target_row['Zone']) if target_row['Zone'] in existing_zones_edit else 0
                        edit_zone = col1.selectbox("โซน/หมวดหมู่", existing_zones_edit, index=zone_idx)
                        
                        col_s1, col_s2 = st.columns(2)
                        edit_stock = col_s1.number_input("ยอดสต๊อก (ปัจจุบัน)", value=int(target_row['Stock']), min_value=0, step=1)
                        edit_min_stock = col_s2.number_input("สต๊อกขั้นต่ำ", value=int(target_row.get('Min_Stock', 0)), min_value=0, step=1)
                        
                        if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                            try:
                                supabase.table("inventory_db").update({
                                    "Item_Code": edit_code, "Item_Name": edit_name, "Zone": edit_zone, 
                                    "Stock": edit_stock, "Min_Stock": edit_min_stock
                                }).eq("id", target_id).execute()
                                st.success("✅ อัปเดตข้อมูลเรียบร้อยแล้ว!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"🚨 อัปเดตไม่สำเร็จ: {e}")
                                
                elif edit_action == "🗑️ ลบวัสดุ":
                    st.warning(f"⚠️ คุณกำลังจะลบ **{selected_edit_item}** หากลบแล้วจะไม่สามารถกู้คืนได้!")
                    if st.button("🚨 ยืนยันการลบวัสดุนี้ ถาวร", type="primary"):
                        try:
                            supabase.table("inventory_db").delete().eq("id", target_id).execute()
                            st.success("✅ ลบทิ้งเรียบร้อยแล้ว!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"🚨 ลบไม่สำเร็จ: {e}")

    st.markdown("---")
    st.subheader("📋 ตารางสต๊อกวัสดุ")
    
    if not inventory_df.empty:
        if 'stock_filter' not in st.session_state:
            st.session_state.stock_filter = "แสดงทั้งหมด"

        low_stock_cnt = len(inventory_df[inventory_df['Status'] == '🟡 ใกล้หมด'])
        out_stock_cnt = len(inventory_df[inventory_df['Status'] == '🔴 หมดแล้ว'])
        all_stock_cnt = len(inventory_df)

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
            st.metric("🟢 วัสดุทั้งหมด", f"{all_stock_cnt} รายการ")
            if st.button("📋 ดูทั้งหมด", use_container_width=True): 
                st.session_state.stock_filter = "แสดงทั้งหมด"
                st.rerun()

        st.caption(f"📌 กำลังแสดงผล: **{st.session_state.stock_filter}**")

        if st.session_state.stock_filter != "แสดงทั้งหมด":
            filtered_by_status = inventory_df[inventory_df['Status'] == st.session_state.stock_filter]
        else:
            filtered_by_status = inventory_df

        all_zones_display = ["แสดงทุกโซน"] + sorted(list(filtered_by_status['Zone'].unique()))
        selected_zone_view = st.selectbox("📌 ค้นหาเพิ่มเติมตามโซน/ห้อง", all_zones_display, index=None, placeholder="🔍 พิมพ์โซนที่ต้องการ (เว้นว่าง = ดูทั้งหมด)")
        
        if not selected_zone_view or selected_zone_view == "แสดงทุกโซน":
            view_inv_df = filtered_by_status
            file_name_inv = "Stock_Export.xlsx"
        else:
            view_inv_df = filtered_by_status[filtered_by_status['Zone'] == selected_zone_view]
            file_name_inv = f"Stock_{selected_zone_view}.xlsx"

        display_inv_df = view_inv_df.rename(columns={
            "Status": "สถานะ", "Item_Code": "รหัสวัสดุ", "Item_Name": "ชื่อวัสดุ", 
            "Zone": "โซน/หมวดหมู่", "Stock": "ยอดคงเหลือ", "Min_Stock": "ขั้นต่ำ"
        }).drop(columns=['id'], errors='ignore')
        
        cols = ["สถานะ", "รหัสวัสดุ", "ชื่อวัสดุ", "โซน/หมวดหมู่", "ยอดคงเหลือ", "ขั้นต่ำ"]
        display_inv_df = display_inv_df[cols]

        total_rows = len(display_inv_df)
        total_pages = max(1, math.ceil(total_rows / 20))
        
        if 'page_inv' not in st.session_state:
            st.session_state.page_inv = 1
        
        if st.session_state.page_inv > total_pages or st.session_state.page_inv < 1:
            st.session_state.page_inv = 1

        start_idx = (st.session_state.page_inv - 1) * 20
        end_idx = start_idx + 20

        st.dataframe(display_inv_df.iloc[start_idx:end_idx], use_container_width=True, hide_index=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])

        with pg_col1:
            st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_inv, args=(-1,), disabled=(st.session_state.page_inv <= 1), use_container_width=True, key="prev_inv")
        with pg_col2:
            start_item = start_idx + 1 if total_rows > 0 else 0
            end_item = min(end_idx, total_rows)
            st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_item} - {end_item} <br>(จากทั้งหมด {total_rows} รายการ)</div>", unsafe_allow_html=True)
            st.selectbox("เลือกหน้า", range(1, total_pages + 1), key="page_inv", label_visibility="collapsed")
        with pg_col3:
            st.button("หน้าถัดไป ➡️", on_click=change_page_inv, args=(1,), disabled=(st.session_state.page_inv >= total_pages), use_container_width=True, key="next_inv")
        st.markdown("---")

        excel_data_inv = to_excel(display_inv_df)
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ Excel (ตามที่กรองไว้)", 
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

        st.subheader("2. เลือกวัสดุลงตะกร้า")
        all_zones = ["แสดงทุกโซน"] + list(inventory_df['Zone'].unique()) if not inventory_df.empty else ["แสดงทุกโซน"]
        selected_zone_filter = st.selectbox("📌 กรองตามโซน (หมวดหมู่)", all_zones, index=None, placeholder="🔍 พิมพ์โซน (เว้นว่าง = ค้นหาจากทุกโซน)")
        
        if not selected_zone_filter or selected_zone_filter == "แสดงทุกโซน":
            filtered_items = inventory_df['Item_Name'] if not inventory_df.empty else []
        else:
            filtered_items = inventory_df[inventory_df['Zone'] == selected_zone_filter]['Item_Name']

        with st.form("add_to_cart_form", clear_on_submit=True):
            item = st.selectbox("เลือกวัสดุ", filtered_items, index=None, placeholder="🔍 พิมพ์ค้นหาวัสดุ...")
            qty = st.number_input("จำนวน", min_value=1, step=1)
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item or not worker:
                    st.error("❌ กรุณาเลือกวัสดุ และระบุชื่อผู้เบิก (ในกรอบด้านบน) ให้ครบถ้วน")
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
                "Action": "ประเภท", "Item_Name": "ชื่อวัสดุ", "Qty": "จำนวน", 
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
                    
                    # --- แก้ไขเวลาให้เป็นโซนประเทศไทย (UTC+7) ---
                    tz_th = timezone(timedelta(hours=7))
                    current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

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
# หน้า 3: ประวัติ (ยกเลิกและลบถาวร)
# ==========================================
elif menu == "📝 ประวัติ & ยกเลิกรายการ (Void)":
    st.header("📝 ประวัติทำรายการ & ยกเลิกบิล")
    
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        if 'Boat_Name' in transaction_df.columns:
            unique_boats = [b for b in transaction_df['Boat_Name'].unique() if pd.notna(b) and b != "-"]
            all_boat_options = ["📋 ดูประวัติทั้งหมด"] + unique_boats
            selected_boat_filter = st.selectbox("⚓ ค้นหาประวัติการเบิกตามชื่อเรือ", all_boat_options, index=None, placeholder="🔍 พิมพ์ชื่อเรือ (เว้นว่าง = ดูทั้งหมด)")
            
            if not selected_boat_filter or selected_boat_filter == "📋 ดูประวัติทั้งหมด":
                base_df = transaction_df
                file_name_hist = "History_All_Boats.xlsx"
            else:
                base_df = transaction_df[transaction_df['Boat_Name'] == selected_boat_filter]
                file_name_hist = f"History_Boat_{selected_boat_filter}.xlsx"
        else:
            base_df = transaction_df 
            file_name_hist = "History_All.xlsx"
            
        hide_voided = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว (Voided) จากตารางด้านล่าง", value=True)
        
        display_df = base_df.copy()
        if hide_voided:
            display_df = display_df[display_df['Status'] != 'Voided (ยกเลิก)']
            
        display_history_df = display_df.iloc[::-1].rename(columns={
            "TxID": "รหัสบิล", "Timestamp": "วันเวลาที่ทำรายการ", "Action": "ประเภท",
            "Item_Name": "ชื่อวัสดุ", "Qty": "จำนวน", "Worker": "ผู้เบิก/ผู้รับ",
            "Status": "สถานะ", "Boat_Name": "ชื่อเรือ"
        })
        
        total_hist_rows = len(display_history_df)
        total_hist_pages = max(1, math.ceil(total_hist_rows / 20))
        
        if 'page_hist' not in st.session_state:
            st.session_state.page_hist = 1
            
        if st.session_state.page_hist > total_hist_pages or st.session_state.page_hist < 1:
            st.session_state.page_hist = 1

        start_h_idx = (st.session_state.page_hist - 1) * 20
        end_h_idx = start_h_idx + 20

        st.dataframe(display_history_df.iloc[start_h_idx:end_h_idx], use_container_width=True, hide_index=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        pg_h1, pg_h2, pg_h3 = st.columns([1, 2, 1])

        with pg_h1:
            st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_hist, args=(-1,), disabled=(st.session_state.page_hist <= 1), use_container_width=True, key="prev_hist")
        with pg_h2:
            start_h_item = start_h_idx + 1 if total_hist_rows > 0 else 0
            end_h_item = min(end_h_idx, total_hist_rows)
            st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_h_item} - {end_h_item} <br>(จากทั้งหมด {total_hist_rows} รายการ)</div>", unsafe_allow_html=True)
            st.selectbox("เลือกหน้า", range(1, total_hist_pages + 1), key="page_hist", label_visibility="collapsed")
        with pg_h3:
            st.button("หน้าถัดไป ➡️", on_click=change_page_hist, args=(1,), disabled=(st.session_state.page_hist >= total_hist_pages), use_container_width=True, key="next_hist")
        st.markdown("---")

        excel_data_hist = to_excel(display_history_df) 
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ Excel (ประวัติทั้งหมดตามที่กรองนี้)", 
            data=excel_data_hist, file_name=file_name_hist, 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary"
        )
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚠️ ดึงสต๊อกกลับ (Void)")
            st.caption("สถานะจะเปลี่ยนเป็นยกเลิก และของจะเด้งกลับเข้าคลัง")
            valid_tx = base_df[base_df['Status'] == 'Completed'].copy()
            
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True)
                
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} ชิ้น)", axis=1)
                    with st.form("void_single_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการ", valid_tx['Display_Single'], index=None, placeholder="🔍 พิมพ์รหัสบิล หรือ ชื่อวัสดุ...")
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกรายการก่อนกดตกลง")
                            else:
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
                        tx_to_void_display = st.selectbox("เลือกบิล", group_summary['Display_Bulk'], index=None, placeholder="🔍 พิมพ์รหัสบิล หรือ ชื่อคนเบิก...")
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกบิลก่อนกดตกลง")
                            else:
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
            
            base_df['Display_Del'] = base_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            
            with st.form("hard_delete_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", base_df['Display_Del'], index=None, placeholder="🔍 พิมพ์รหัสบิล หรือ ชื่อวัสดุ...")
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if not tx_to_delete:
                        st.error("❌ กรุณาเลือกรายการก่อนกดตกลง")
                    else:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("transaction_log").delete().eq("TxID", target_txid).execute()
                        st.success(f"✅ ลบประวัติ {target_txid} ออกจากระบบถาวรแล้ว!")
                        st.rerun()
