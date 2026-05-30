import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client
import io
import math

st.set_page_config(page_title="Shipyard Inventory System", layout="wide")

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

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# ดึงข้อมูลทั้งหมดจากฐานข้อมูล
inventory_df = load_data("inventory_db")
transaction_df = load_data("transaction_log")
cart_df = load_data("cart_db")
po_cart_df = load_data("po_cart_db")
po_log_df = load_data("po_log")
po_payments_df = load_data("po_payments") 

# ตั้งค่าสถานะหน้าสำหรับการแบ่งหน้า (Pagination)
if 'page_inv' not in st.session_state:
    st.session_state.page_inv = 1
if 'page_hist' not in st.session_state:
    st.session_state.page_hist = 1
if 'page_po_hist' not in st.session_state:
    st.session_state.page_po_hist = 1

def change_page_inv(delta):
    st.session_state.page_inv += delta

def change_page_hist(delta):
    st.session_state.page_hist += delta

def change_page_po_hist(delta):
    st.session_state.page_po_hist += delta

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", [
    "📊 แดชบอร์ด (ภาพรวม)",
    "📦 สต๊อกวัสดุ", 
    "🛒 เบิก-รับของ (หน้างาน)", 
    "📋 ระบบจัดซื้อ (PO)", 
    "📑 ประวัติจัดซื้อ & รับของ",
    "💳 ระบบจ่ายเงิน & เครดิต",
    "📝 ประวัติเบิกงาน & ยกเลิก"
])

# ==========================================
# หน้า 0: แดชบอร์ดภาพรวม
# ==========================================
if menu == "📊 แดชบอร์ด (ภาพรวม)":
    st.header("📊 แดชบอร์ดสรุปข้อมูลอู่เรือ")
    
    col1, col2, col3, col4 = st.columns(4)
    total_items = len(inventory_df) if not inventory_df.empty else 0
    
    low_stock_count = 0
    if not inventory_df.empty:
        inventory_df['Min_Stock'] = inventory_df['Min_Stock'].fillna(0).astype(int)
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

# ==========================================
# หน้า 1: สต๊อกวัสดุ
# ==========================================
elif menu == "📦 สต๊อกวัสดุ":
    st.header("📦 สต๊อกวัสดุคงเหลือ")
    
    if not inventory_df.empty:
        if 'Min_Stock' not in inventory_df.columns:
            inventory_df['Min_Stock'] = 0
        if 'Unit' not in inventory_df.columns:
            inventory_df['Unit'] = 'ชิ้น'
            
        inventory_df['Min_Stock'] = inventory_df['Min_Stock'].fillna(0).astype(int)
        inventory_df['Unit'] = inventory_df['Unit'].fillna('ชิ้น').astype(str)
        
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
            
            new_unit = col2.text_input("หน่วยนับ (เช่น อัน, ใบ, เมตร, ลิตร) *", value="ชิ้น")
            
            col_s1, col_s2 = st.columns(2)
            new_stock = col_s1.number_input("จำนวนรับเข้าล็อตแรก", min_value=0, step=1)
            new_min_stock = col_s2.number_input("สต๊อกขั้นต่ำ (แจ้งเตือนเมื่อใกล้หมด)", min_value=0, step=1, value=0)
            
            submit_new = st.form_submit_button("💾 บันทึกวัสดุใหม่เข้าคลัง")
            
            if submit_new:
                final_zone = custom_zone.strip() if custom_zone.strip() != "" else selected_zone
                
                if not new_code or not new_name or not final_zone or not new_unit.strip():
                    st.error("❌ กรุณากรอกรหัสวัสดุ ชื่อวัสดุ โซน และหน่วยนับให้ครบถ้วน")
                elif not inventory_df.empty and new_code in inventory_df['Item_Code'].values:
                    st.error(f"❌ รหัสวัสดุ '{new_code}' มีในระบบแล้ว")
                elif not inventory_df.empty and new_name in inventory_df['Item_Name'].values:
                    st.error(f"❌ ชื่อวัสดุ '{new_name}' มีในระบบแล้ว")
                else:
                    try:
                        supabase.table("inventory_db").insert({
                            "Item_Code": new_code, 
                            "Item_Name": new_name, 
                            "Zone": final_zone, 
                            "Stock": int(new_stock), 
                            "Min_Stock": int(new_min_stock), 
                            "Unit": new_unit.strip()
                        }).execute()
                        st.success(f"✅ เพิ่มทะเบียน '{new_name}' เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 เกิดข้อผิดพลาดจากฐานข้อมูล: {e}")

    with st.expander("🛠️ แก้ไข / ลบ ทะเบียนวัสดุ"):
        if not inventory_df.empty:
            edit_action = st.radio("เลือกโหมดการทำงาน", ["✏️ แก้ไขข้อมูล", "🗑️ ลบวัสดุ"], horizontal=True)
            item_list = sorted(inventory_df['Item_Name'].tolist())
            selected_edit_item = st.selectbox("ค้นหาวัสดุที่ต้องการจัดการ", item_list, index=None, placeholder="🔍 พิมพ์ชื่อวัสดุ...")
            
            if selected_edit_item:
                target_row = inventory_df[inventory_df['Item_Name'] == selected_edit_item].iloc[0]
                target_id = int(target_row['id']) 
                
                if edit_action == "✏️ แก้ไขข้อมูล":
                    with st.form("edit_item_form"):
                        c1, c2 = st.columns(2)
                        edit_code = c1.text_input("รหัสวัสดุ", value=target_row['Item_Code'])
                        edit_name = c2.text_input("ชื่อวัสดุ", value=target_row['Item_Name'])
                        
                        existing_zones_edit = list(inventory_df['Zone'].unique())
                        zone_idx = existing_zones_edit.index(target_row['Zone']) if target_row['Zone'] in existing_zones_edit else 0
                        edit_zone = c1.selectbox("โซน/หมวดหมู่", existing_zones_edit, index=zone_idx)
                        edit_unit = c2.text_input("หน่วยนับ", value=target_row.get('Unit', 'ชิ้น'))
                        
                        cs1, cs2 = st.columns(2)
                        edit_stock = cs1.number_input("ยอดสต๊อก (ปัจจุบัน)", value=int(target_row['Stock']), min_value=0, step=1)
                        edit_min_stock = cs2.number_input("สต๊อกขั้นต่ำ", value=int(target_row.get('Min_Stock', 0)), min_value=0, step=1)
                        
                        if st.form_submit_button("💾 บันทึกการเปลี่ยนแปลง"):
                            try:
                                supabase.table("inventory_db").update({
                                    "Item_Code": edit_code, 
                                    "Item_Name": edit_name, 
                                    "Zone": edit_zone, 
                                    "Stock": edit_stock, 
                                    "Min_Stock": edit_min_stock, 
                                    "Unit": edit_unit.strip()
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
            "Status": "สถานะ", 
            "Item_Code": "รหัสวัสดุ", 
            "Item_Name": "ชื่อวัสดุ", 
            "Zone": "โซน/หมวดหมู่", 
            "Stock": "ยอดคงเหลือ", 
            "Unit": "หน่วยนับ", 
            "Min_Stock": "ขั้นต่ำ"
        }).drop(columns=['id'], errors='ignore')
        
        cols = ["สถานะ", "รหัสวัสดุ", "ชื่อวัสดุ", "โซน/หมวดหมู่", "ยอดคงเหลือ", "หน่วยนับ", "ขั้นต่ำ"]
        display_inv_df = display_inv_df[cols]

        total_rows = len(display_inv_df)
        total_pages = max(1, math.ceil(total_rows / 20))
        
        if st.session_state.page_inv > total_pages or st.session_state.page_inv < 1:
            st.session_state.page_inv = 1
            
        start_idx = (st.session_state.page_inv - 1) * 20
        end_idx = start_idx + 20

        st.dataframe(display_inv_df.iloc[start_idx:end_idx], use_container_width=True, hide_index=True)
        
        pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
        with pg_col1:
            st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_inv, args=(-1,), disabled=(st.session_state.page_inv <= 1), use_container_width=True, key="prev_inv")
        with pg_col2:
            st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_idx + 1 if total_rows > 0 else 0} - {min(end_idx, total_rows)} <br>(จากทั้งหมด {total_rows} รายการ)</div>", unsafe_allow_html=True)
            st.selectbox("เลือกหน้า", range(1, total_pages + 1), key="page_inv", label_visibility="collapsed")
        with pg_col3:
            st.button("หน้าถัดไป ➡️", on_click=change_page_inv, args=(1,), disabled=(st.session_state.page_inv >= total_pages), use_container_width=True, key="next_inv")
        
        excel_data_inv = to_excel(display_inv_df)
        st.download_button("📥 ดาวน์โหลดไฟล์ Excel", data=excel_data_inv, file_name=file_name_inv, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

# ==========================================
# หน้า 2: ระบบเบิก-รับของ (หน้างาน)
# ==========================================
elif menu == "🛒 เบิก-รับของ (หน้างาน)":
    st.header("🛒 ฟอร์มทำรายการ & ตะกร้าพักของ")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. ข้อมูลบิล (ระบุครั้งเดียว)")
        with st.container(border=True):
            action = st.radio("ประเภท", ["เบิกออก", "รับเข้า (คืนคลัง)"], horizontal=True)
            worker = st.text_input("ชื่อผู้เบิก/ผู้รับ")
            boat_name = st.text_input("⚓ ชื่อเรือที่ปฏิบัติงาน (ใส่หรือไม่ใส่ก็ได้)") 

        st.subheader("2. เลือกวัสดุลงตะกร้า")
        all_zones = ["แสดงทุกโซน"] + list(inventory_df['Zone'].unique()) if not inventory_df.empty else ["แสดงทุกโซน"]
        selected_zone_filter = st.selectbox("📌 กรองตามโซน", all_zones, index=None, placeholder="🔍 พิมพ์โซน...")
        
        if not selected_zone_filter or selected_zone_filter == "แสดงทุกโซน":
            filtered_items = inventory_df['Item_Name'] if not inventory_df.empty else []
        else:
            filtered_items = inventory_df[inventory_df['Zone'] == selected_zone_filter]['Item_Name']

        with st.form("add_to_cart_form", clear_on_submit=True):
            item = st.selectbox("เลือกวัสดุ", filtered_items, index=None, placeholder="🔍 พิมพ์ค้นหาวัสดุ...")
            qty = st.number_input("จำนวน", min_value=1, step=1)
            
            if st.form_submit_button("➕ เพิ่มลงตะกร้า"):
                if not item or not worker:
                    st.error("❌ กรุณาเลือกวัสดุ และระบุชื่อผู้เบิกให้ครบถ้วน")
                else:
                    current_stock = inventory_df.loc[inventory_df['Item_Name'] == item, 'Stock'].values[0]
                    
                    if action == "เบิกออก" and qty > current_stock:
                        st.error(f"เบิกไม่ได้! {item} มีของในสต๊อกแค่ {current_stock}")
                    else:
                        try:
                            supabase.table("cart_db").insert({
                                "Action": action, 
                                "Item_Name": item, 
                                "Qty": int(qty), 
                                "Worker": worker, 
                                "Boat_Name": boat_name if boat_name else "-" 
                            }).execute()
                            st.success(f"✅ เพิ่ม {item} ลงตะกร้าแล้ว")
                            st.rerun()
                        except Exception as e:
                            st.error(f"🚨 นำลงตะกร้าไม่สำเร็จ: {e}")

    with col2:
        st.subheader("3. ตะกร้าของวันนี้ (รอตัดสต๊อก)")
        if cart_df.empty:
            st.info("ยังไม่มีรายการในตะกร้า")
        else:
            display_cart_df = cart_df.rename(columns={
                "Action": "ประเภท", 
                "Item_Name": "ชื่อวัสดุ", 
                "Qty": "จำนวน", 
                "Worker": "ผู้เบิก/รับ", 
                "Boat_Name": "ชื่อเรือ"
            }).drop(columns=['id'])
            
            st.dataframe(display_cart_df, use_container_width=True, hide_index=True)
            
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("🗑️ ล้างตะกร้าทั้งหมด", type="secondary", use_container_width=True):
                    supabase.table("cart_db").delete().gte("id", 0).execute()
                    st.rerun()
            with c_b:
                if st.button("💾 ยืนยันตัดสต๊อก 1 บิล", type="primary", use_container_width=True):
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
                        
                        item_txid = f"{bill_id}-{idx+1}" 
                        
                        supabase.table("transaction_log").insert({
                            "TxID": item_txid, 
                            "Timestamp": current_time, 
                            "Action": row['Action'],
                            "Item_Name": row['Item_Name'], 
                            "Qty": int(row['Qty']),
                            "Worker": row['Worker'], 
                            "Boat_Name": row['Boat_Name'], 
                            "Status": "Completed"
                        }).execute()
                        
                    supabase.table("cart_db").delete().gte("id", 0).execute()
                    st.success(f"✅ ตัดสต๊อกเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 3: ระบบจัดซื้อ (PO) 
# ==========================================
elif menu == "📋 ระบบจัดซื้อ (PO)":
    st.header("📋 ระบบออกใบสั่งซื้อ (PO)")
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        st.subheader("1. ข้อมูลบิล (ระบุครั้งเดียว)")
        with st.container(border=True):
            requester = st.text_input("ชื่อผู้ขอซื้อ / แผนก", placeholder="เช่น สโตร์, พี่ต๋อง")
            shop_name = st.text_input("ซื้อจากร้าน (ชื่อร้าน)", placeholder="พิมพ์ชื่อร้านค้า...")

        st.subheader("2. เพิ่มรายการลงใบสั่งซื้อ")
        all_items = inventory_df['Item_Name'].tolist() if not inventory_df.empty else []
        
        is_new_item = st.checkbox("➕ เป็นรายการวัสดุใหม่ (ยังไม่มีชื่อในระบบคลัง)")
        
        with st.form("add_po_form", clear_on_submit=True):
            if is_new_item:
                st.info("💡 ระบบจะสร้างชื่อวัสดุนี้ในคลังให้อัตโนมัติเมื่อกด 'บันทึกใบสั่งซื้อ'")
                selected_item = st.text_input("พิมพ์ชื่อวัสดุใหม่ *", placeholder="ระบุชื่อวัสดุ...")
                unit_input = st.text_input("หน่วยนับ *", value="ชิ้น")
            else:
                selected_item = st.selectbox("เลือกรายการวัสดุที่มีในคลัง", all_items, index=None, placeholder="🔍 พิมพ์ค้นหารายการ...")
                unit_input = "" 
                
            c1, c2 = st.columns(2)
            qty = c1.number_input("จำนวน", min_value=1, step=1)
            price_per_unit = c2.number_input("ราคา/หน่วย (บาท)", min_value=0.0, step=1.0)
            
            c3, c4, c5 = st.columns(3)
            discount = c3.number_input("ส่วนลดรวมรายการนี้ (บาท)", min_value=0.0, step=1.0)
            shipping = c4.number_input("ค่าส่ง (บาท)", min_value=0.0, step=1.0)
            vat = c5.number_input("ภาษี VAT (บาท)", min_value=0.0, step=1.0)
            
            if st.form_submit_button("➕ นำลงใบสั่งซื้อ"):
                if not requester or not selected_item or not shop_name:
                    st.error("❌ กรุณากรอก ชื่อผู้ขอซื้อ, ชื่อร้าน และรายการ ให้ครบถ้วน")
                else:
                    if is_new_item:
                        unit_val = unit_input.strip()
                    else:
                        unit_val = inventory_df.loc[inventory_df['Item_Name'] == selected_item, 'Unit'].values[0]
                        
                    net_price = (qty * price_per_unit) - discount + shipping + vat
                    
                    try:
                        supabase.table("po_cart_db").insert({
                            "Requester": requester, 
                            "Item_Name": selected_item, 
                            "Qty": int(qty), 
                            "Unit": str(unit_val), 
                            "Price_Per_Unit": float(price_per_unit),
                            "Discount": float(discount), 
                            "Shipping": float(shipping), 
                            "VAT": float(vat),
                            "Net_Price": float(net_price), 
                            "Shop_Name": shop_name
                        }).execute()
                        st.success(f"✅ เพิ่ม {selected_item} ลงใบสั่งซื้อแล้ว")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 นำลงตะกร้าสั่งซื้อไม่สำเร็จ: โปรดตรวจสอบฐานข้อมูลและ RLS")

    with col2:
        st.subheader("3. รายการที่รอสั่งซื้อ")
        if po_cart_df.empty:
            st.info("ยังไม่มีรายการในตะกร้าจัดซื้อ")
        else:
            po_cart_df['VAT'] = po_cart_df.get('VAT', 0)
            display_po_cart = po_cart_df.rename(columns={
                "Requester": "ผู้ขอซื้อ", 
                "Item_Name": "รายการ", 
                "Qty": "จำนวน", 
                "Unit": "หน่วย", 
                "Price_Per_Unit": "ราคา", 
                "Net_Price": "สุทธิ", 
                "Shop_Name": "ร้านค้า"
            }).drop(columns=['id', 'Discount', 'Shipping', 'VAT'], errors='ignore')
            
            st.dataframe(display_po_cart, use_container_width=True, hide_index=True)
            total_po_amount = po_cart_df['Net_Price'].sum()
            st.markdown(f"<h4 style='text-align: right; color: green;'>รวมยอดบิลนี้: ฿ {total_po_amount:,.2f}</h4>", unsafe_allow_html=True)
            
            with st.expander("🗑️ ลบเฉพาะบางรายการในตะกร้า"):
                po_cart_df['Display_Cart'] = po_cart_df.apply(lambda row: f"{row['id']} | {row['Item_Name']} ({row['Qty']} {row['Unit']})", axis=1)
                with st.form("del_po_cart_item"):
                    col_d1, col_d2 = st.columns([3, 1])
                    item_to_del = col_d1.selectbox("เลือกรายการที่จะลบออก", po_cart_df['Display_Cart'], index=None, label_visibility="collapsed")
                    
                    if col_d2.form_submit_button("❌ ลบรายการนี้", use_container_width=True):
                        if item_to_del:
                            del_id = item_to_del.split(" | ")[0]
                            supabase.table("po_cart_db").delete().eq("id", int(del_id)).execute()
                            st.success("✅ ลบรายการออกจากตะกร้าเรียบร้อย")
                            st.rerun()

            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("🗑️ ล้างตะกร้า (ทั้งหมด)", type="secondary", use_container_width=True):
                    supabase.table("po_cart_db").delete().gte("id", 0).execute()
                    st.rerun()
            with c_b:
                if st.button("💾 บันทึกใบสั่งซื้อ (Save PO)", type="primary", use_container_width=True):
                    next_po_num = 1
                    if not po_log_df.empty:
                        po_rows = po_log_df['PO_ID'].unique()
                        nums = [int(str(x).replace('PO_', '')) for x in po_rows if 'PO_' in str(x)]
                        if nums:
                            next_po_num = max(nums) + 1
                            
                    po_id = f"PO_{next_po_num:04d}" 
                    tz_th = timezone(timedelta(hours=7))
                    current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

                    for idx, row in po_cart_df.iterrows():
                        tx_id = f"{po_id}-{idx+1}"
                        
                        if row['Item_Name'] not in inventory_df['Item_Name'].values:
                            new_code = f"NEW-{tx_id}"
                            supabase.table("inventory_db").insert({
                                "Item_Code": new_code, 
                                "Item_Name": row['Item_Name'], 
                                "Zone": "รอจัดหมวดหมู่", 
                                "Stock": 0, 
                                "Min_Stock": 0, 
                                "Unit": row['Unit']
                            }).execute()

                        supabase.table("po_log").insert({
                            "TxID": tx_id, 
                            "PO_ID": po_id, 
                            "Timestamp": current_time, 
                            "Requester": row['Requester'], 
                            "Item_Name": row['Item_Name'], 
                            "Qty": int(row['Qty']), 
                            "Unit": str(row['Unit']),
                            "Price_Per_Unit": float(row['Price_Per_Unit']), 
                            "Discount": float(row['Discount']),
                            "Shipping": float(row['Shipping']), 
                            "VAT": float(row.get('VAT', 0)),
                            "Net_Price": float(row['Net_Price']), 
                            "Shop_Name": row['Shop_Name'], 
                            "Status": "รอรับของ"
                        }).execute()
                        
                    supabase.table("po_cart_db").delete().gte("id", 0).execute()
                    st.success(f"✅ บันทึกใบสั่งซื้อ {po_id} เข้าสู่ระบบประวัติเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 4: ประวัติจัดซื้อ & รับของ
# ==========================================
elif menu == "📑 ประวัติจัดซื้อ & รับของ":
    st.header("📑 ประวัติจัดซื้อ & รับของเข้าสต๊อก (Receive PO)")
    
    if po_log_df.empty:
        st.info("ยังไม่มีประวัติการจัดซื้อในระบบ")
    else:
        st.subheader("🖨️ พิมพ์ใบสั่งซื้อ (Print / Save as PDF)")
        po_list = sorted(po_log_df['PO_ID'].unique(), reverse=True)
        selected_po_to_print = st.selectbox("เลือกเลขที่ PO ที่ต้องการพิมพ์", po_list, index=None, placeholder="🔍 พิมพ์เพื่อค้นหาเลข PO...")
        
        if selected_po_to_print:
            po_data = po_log_df[po_log_df['PO_ID'] == selected_po_to_print]
            total_net = po_data['Net_Price'].sum()
            date_str = str(po_data.iloc[0]['Timestamp']).split(' ')[0]
            
            html_invoice = f"""
            <html><head>
            <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
            <style>
                body {{ font-family: 'Sarabun', sans-serif; color: #333; padding: 20px; }}
                h2 {{ text-align: center; color: #1a365d; margin-bottom: 5px; }}
                .info-box {{ width: 100%; margin-bottom: 15px; border-bottom: 2px solid #ddd; padding-bottom: 10px; text-align: center; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #1a365d; color: white; text-align: center; }}
                .total-row td {{ font-weight: bold; background-color: #f7fafc; }}
                .total-amt {{ color: #e53e3e; text-align: right; }}
                .btn-container {{ display: flex; justify-content: center; gap: 15px; margin-top: 20px; }}
                .btn-print, .btn-download {{ padding: 10px 20px; color: white; text-decoration: none; border-radius: 5px; cursor: pointer; font-weight: bold; border: none; font-family: 'Sarabun', sans-serif; font-size: 14px; }}
                .btn-print {{ background-color: #3182ce; }} 
                .btn-download {{ background-color: #38a169; }}
                @media print {{ 
                    .btn-container {{ display: none; }} 
                    @page {{ margin-top: 0; margin-bottom: 0; }} 
                    body {{ padding-top: 2cm; padding-bottom: 2cm; }}
                }}
            </style></head>
            <body>
                <div id="invoice-content">
                    <h2>ใบสั่งซื้อ (Purchase Order)</h2>
                    <div class="info-box">
                        <strong>เลขที่เอกสาร:</strong> {selected_po_to_print} &nbsp;&nbsp;|&nbsp;&nbsp;
                        <strong>วันที่:</strong> {date_str} &nbsp;&nbsp;|&nbsp;&nbsp;
                        <strong>ผู้ขอซื้อ:</strong> {po_data.iloc[0]['Requester']}
                    </div>
                    <table>
                        <tr>
                            <th style="width: 5%;">ลำดับ</th>
                            <th style="width: 35%;">รายการสินค้า</th>
                            <th style="width: 15%;">ร้านค้า</th>
                            <th style="width: 8%;">จำนวน</th>
                            <th style="width: 8%;">หน่วย</th>
                            <th style="width: 12%;">ราคา/หน่วย</th>
                            <th style="width: 12%;">ราคาสุทธิ</th>
                        </tr>
            """
            
            counter = 1
            for idx, row in po_data.iterrows():
                item_code_val = "-"
                if not inventory_df.empty:
                    match_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']]
                    if not match_item.empty:
                        item_code_val = match_item.iloc[0]['Item_Code']
                
                html_invoice += f"""
                    <tr>
                        <td style='text-align: center;'>{counter}</td>
                        <td>[{item_code_val}] {row['Item_Name']}</td>
                        <td style='text-align: center;'>{row['Shop_Name']}</td>
                        <td style='text-align: center;'>{row['Qty']}</td>
                        <td style='text-align: center;'>{row['Unit']}</td>
                        <td style='text-align: right;'>{row['Price_Per_Unit']:,.2f}</td>
                        <td style='text-align: right;'>{row['Net_Price']:,.2f}</td>
                    </tr>
                """
                counter += 1
                
            html_invoice += f"""
                        <tr class="total-row">
                            <td colspan="6" style='text-align: right;'>ยอดรวมสุทธิ (Grand Total):</td>
                            <td class="total-amt">฿ {total_net:,.2f}</td>
                        </tr>
                    </table>
                    <br><br><br>
                    <table style="border: none; margin-top: 40px; text-align: center;">
                        <tr style="border: none;">
                            <td style="border: none;">________________________<br><br>ผู้จัดทำ / ฝ่ายจัดซื้อ</td>
                            <td style="border: none;">________________________<br><br>ผู้อนุมัติสั่งซื้อ</td>
                        </tr>
                    </table>
                </div>
                
                <div class="btn-container">
                    <button class="btn-print" onclick="window.print()">🖨️ พิมพ์ (Print)</button>
                    <button class="btn-download" onclick="downloadPDF()">📥 ดาวน์โหลด PDF</button>
                </div>

                <script>
                    function downloadPDF() {{
                        var element = document.getElementById('invoice-content');
                        var opt = {{
                            margin:       10,
                            filename:     '{selected_po_to_print}.pdf',
                            image:        {{ type: 'jpeg', quality: 0.98 }},
                            html2canvas:  {{ scale: 2, useCORS: true }},
                            jsPDF:        {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                        }};
                        html2pdf().set(opt).from(element).save();
                    }}
                </script>
            </body></html>
            """
            components.html(html_invoice, height=500, scrolling=True)

        st.markdown("---")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📦 กดรับของเข้าคลัง (Receive)")
            st.caption("เมื่อร้านมาส่งของ ให้กดรับของที่นี่ ของจะเข้าสต๊อกอัตโนมัติ")
            
            pending_po = po_log_df[po_log_df['Status'] == 'รอรับของ'].copy()
            if not pending_po.empty:
                pending_po['Display_Recv'] = pending_po.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']}) จาก: {row['Shop_Name']}", axis=1)
                
                with st.form("receive_po_form"):
                    item_to_receive = st.selectbox("เลือกรายการที่มาส่งแล้ว", pending_po['Display_Recv'], index=None, placeholder="🔍 ค้นหารายการรอรับของ...")
                    
                    if st.form_submit_button("✅ ยืนยันรับของเข้าสต๊อก"):
                        if not item_to_receive:
                            st.error("❌ กรุณาเลือกรายการก่อน")
                        else:
                            target_txid = item_to_receive.split(" | ")[0]
                            tx_data = pending_po[pending_po['TxID'] == target_txid].iloc[0]
                            
                            supabase.table("po_log").update({"Status": "✅ รับแล้ว (เข้าคลัง)"}).eq("TxID", target_txid).execute()
                            
                            target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                            if not target_item.empty:
                                new_stock = target_item.iloc[0]['Stock'] + int(tx_data['Qty'])
                                supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                                st.success(f"🎉 รับ {tx_data['Item_Name']} เข้าสต๊อกเรียบร้อยแล้ว!")
                            else:
                                st.warning("⚠️ เปลี่ยนสถานะเป็น 'รับแล้ว' แต่หาวัสดุชื่อนี้ในคลังหลักไม่เจอ (ไม่ได้บวกสต๊อกให้)")
                            st.rerun()
            else:
                st.success("✅ ตอนนี้ไม่มีของค้างส่ง (รับเข้าคลังครบหมดแล้ว)")

        with col2:
            st.subheader("📋 ตารางประวัติการสั่งซื้อ (PO)")
            hide_voided_po = st.checkbox("👁️ ซ่อนรายการที่ถูกยกเลิก/ตีกลับ", value=True)
            base_po_df = po_log_df.copy()
            
            if hide_voided_po: 
                base_po_df = base_po_df[~base_po_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
            
            if 'VAT' not in base_po_df.columns:
                base_po_df['VAT'] = 0
            if 'Shipping' not in base_po_df.columns:
                base_po_df['Shipping'] = 0
                
            display_po_df = base_po_df.iloc[::-1].rename(columns={
                "TxID": "รหัสรายการ", 
                "PO_ID": "เลขที่ PO", 
                "Timestamp": "วันเวลา", 
                "Requester": "ผู้ขอซื้อ", 
                "Item_Name": "รายการ", 
                "Qty": "จำนวน", 
                "Unit": "หน่วย", 
                "Price_Per_Unit": "ราคา/หน่วย", 
                "Discount": "ส่วนลด", 
                "Shipping": "ค่าส่ง", 
                "Net_Price": "ราคาสุทธิ", 
                "Shop_Name": "ร้านค้า", 
                "Status": "สถานะ"
            })
            
            total_po_rows = len(display_po_df)
            total_po_pages = max(1, math.ceil(total_po_rows / 20))
            if st.session_state.page_po_hist > total_po_pages or st.session_state.page_po_hist < 1: 
                st.session_state.page_po_hist = 1

            start_po_idx = (st.session_state.page_po_hist - 1) * 20
            end_po_idx = start_po_idx + 20

            st.dataframe(display_po_df.iloc[start_po_idx:end_po_idx][['รหัสรายการ', 'เลขที่ PO', 'ผู้ขอซื้อ', 'รายการ', 'จำนวน', 'ค่าส่ง', 'VAT', 'ราคาสุทธิ', 'ร้านค้า', 'สถานะ']], use_container_width=True, hide_index=True)
            
            pg_p1, pg_p2, pg_p3 = st.columns([1, 2, 1])
            with pg_p1:
                st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_po_hist, args=(-1,), disabled=(st.session_state.page_po_hist <= 1), use_container_width=True, key="prev_po_hist")
            with pg_p2:
                st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_po_idx + 1 if total_po_rows > 0 else 0} - {min(end_po_idx, total_po_rows)} <br>(จากทั้งหมด {total_po_rows} รายการ)</div>", unsafe_allow_html=True)
            with pg_p3:
                st.button("หน้าถัดไป ➡️", on_click=change_page_po_hist, args=(1,), disabled=(st.session_state.page_po_hist >= total_po_pages), use_container_width=True, key="next_po_hist")
            
            excel_data_po = to_excel(display_po_df)
            st.download_button("📥 ดาวน์โหลดไฟล์ Excel (ประวัติจัดซื้อ)", data=excel_data_po, file_name="PO_History.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

        st.markdown("---")
        
        # ---------------------------------------------
        # โซน แท็บจัดการบิล (แก้ไขกดรับผิด / ตีกลับ / ยกเลิก / ลบ)
        # ---------------------------------------------
        st.subheader("🛠️ จัดการสถานะรายการสั่งซื้อ (แก้ไข / ตีกลับ / ยกเลิก)")
        tab1, tab2, tab3, tab4 = st.tabs(["↩️ ยกเลิกการรับของ (กดผิด)", "📦 ตีกลับสินค้า (ไม่ตรงปก)", "⚠️ ยกเลิกบิล (Void)", "🗑️ ลบประวัติถาวร"])

        with tab1:
            st.caption("ใช้เมื่อเผลอกด 'รับของเข้าคลัง' ผิดรายการ (ระบบจะหักของออกจากสต๊อก และเปลี่ยนสถานะกลับเป็น 'รอรับของ' เพื่อให้รอรับใหม่)")
            received_po = po_log_df[po_log_df['Status'] == '✅ รับแล้ว (เข้าคลัง)'].copy()
            if not received_po.empty:
                received_po['Display_Undo'] = received_po.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']})", axis=1)
                
                with st.form("undo_receive_form"):
                    undo_item = st.selectbox("เลือกรายการที่กดรับผิด", received_po['Display_Undo'], index=None)
                    
                    if st.form_submit_button("↩️ ดึงของออก & เปลี่ยนเป็น 'รอรับของ'"):
                        if not undo_item:
                            st.error("❌ กรุณาเลือกรายการ")
                        else:
                            target_txid = undo_item.split(" | ")[0]
                            tx_data = received_po[received_po['TxID'] == target_txid].iloc[0]
                            
                            target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                            if not target_item.empty:
                                new_stock = target_item.iloc[0]['Stock'] - int(tx_data['Qty'])
                                supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                                
                            supabase.table("po_log").update({"Status": "รอรับของ"}).eq("TxID", target_txid).execute()
                            st.success(f"✅ ดึงของออกจากสต๊อกและเปลี่ยนเป็น 'รอรับของ' เรียบร้อย")
                            st.rerun()
            else:
                st.info("ไม่มีรายการที่รับของเข้าคลังแล้ว")

        with tab2:
            st.caption("ใช้เมื่อร้านส่งของมาไม่ตรงสเปก ชำรุด และต้องส่งคืนเพื่อขอเงินคืน (หากเคยกดรับเข้าคลังไปแล้ว ระบบจะหักสต๊อกออกให้อัตโนมัติ)")
            valid_return = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])].copy()
            if not valid_return.empty:
                valid_return['Display_Return'] = valid_return.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']}) [สถานะ: {row['Status']}]", axis=1)
                
                with st.form("return_po_form"):
                    return_item = st.selectbox("เลือกรายการที่ต้องการตีกลับ", valid_return['Display_Return'], index=None)
                    
                    if st.form_submit_button("📦 ยืนยันตีกลับสินค้า"):
                        if not return_item:
                            st.error("❌ กรุณาเลือกรายการ")
                        else:
                            target_txid = return_item.split(" | ")[0]
                            tx_data = valid_return[valid_return['TxID'] == target_txid].iloc[0]
                            
                            if tx_data['Status'] == '✅ รับแล้ว (เข้าคลัง)':
                                target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                                if not target_item.empty:
                                    new_stock = target_item.iloc[0]['Stock'] - int(tx_data['Qty'])
                                    supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                            
                            supabase.table("po_log").update({"Status": "❌ ตีกลับ (ขอเงินคืน)"}).eq("TxID", target_txid).execute()
                            st.success(f"✅ บันทึกการตีกลับรายการ {target_txid} เรียบร้อย")
                            st.rerun()
            else:
                st.info("ไม่มีรายการให้ตีกลับ")

        with tab3:
            st.caption("ใช้เมื่อต้องการยกเลิกบิลสั่งซื้อ (เช่น พิมพ์ผิด หรือ ยกเลิกการสั่งกับร้านค้า)")
            valid_po_tx = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])].copy()
            if not valid_po_tx.empty:
                void_po_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละรายการ", "เหมาทั้งบิล (PO)"], horizontal=True, key="po_void_mode")
                
                if void_po_mode == "ทีละรายการ":
                    valid_po_tx['Display_Single'] = valid_po_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']})", axis=1)
                    
                    with st.form("void_single_po_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการ", valid_po_tx['Display_Single'], index=None)
                        
                        if st.form_submit_button("ยกเลิกรายการนี้ (Void)"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกรายการ")
                            else:
                                target_txid = tx_to_void_display.split(" | ")[0]
                                tx_data = valid_po_tx[valid_po_tx['TxID'] == target_txid].iloc[0]
                                
                                if tx_data['Status'] == '✅ รับแล้ว (เข้าคลัง)':
                                    target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                                    if not target_item.empty:
                                        new_stock = target_item.iloc[0]['Stock'] - int(tx_data['Qty'])
                                        supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                                        
                                supabase.table("po_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", target_txid).execute()
                                st.success("✅ ยกเลิกรายการเรียบร้อย")
                                st.rerun()
                else:
                    group_po_summary = valid_po_tx.groupby('PO_ID').agg({'Requester': 'first', 'Item_Name': 'count'}).reset_index()
                    group_po_summary['Display_Bulk'] = group_po_summary.apply(lambda row: f"{row['PO_ID']} ({row['Item_Name']} รายการ)", axis=1)
                    
                    with st.form("void_bulk_po_form"):
                        po_to_void_display = st.selectbox("เลือกบิล PO", group_po_summary['Display_Bulk'], index=None)
                        
                        if st.form_submit_button("ยกเลิกทั้งบิล PO"):
                            if not po_to_void_display:
                                st.error("❌ กรุณาเลือกบิล")
                            else:
                                selected_po_group = po_to_void_display.split(" | ")[0]
                                tx_to_cancel = valid_po_tx[valid_po_tx['PO_ID'] == selected_po_group]
                                
                                for _, tx_data in tx_to_cancel.iterrows():
                                    if tx_data['Status'] == '✅ รับแล้ว (เข้าคลัง)':
                                        target_item = inventory_df[inventory_df['Item_Name'] == tx_data['Item_Name']]
                                        if not target_item.empty:
                                            new_stock = target_item.iloc[0]['Stock'] - int(tx_data['Qty'])
                                            supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", target_item.iloc[0]['Item_Code']).execute()
                                            
                                supabase.table("po_log").update({"Status": "Voided (ยกเลิก)"}).eq("PO_ID", selected_po_group).execute()
                                st.success("✅ ยกเลิกบิลเรียบร้อย")
                                st.rerun()
            else:
                st.info("ไม่มีรายการให้ยกเลิก")

        with tab4:
            st.caption("ลบข้อมูลออกจากฐานข้อมูลแบบถาวร (แนะนำให้ใช้สำหรับเคลียร์ข้อมูลเทสต์เท่านั้น)")
            po_log_df['Display_Del'] = po_log_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            
            with st.form("hard_delete_po_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", po_log_df['Display_Del'], index=None)
                
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if not tx_to_delete:
                        st.error("❌ กรุณาเลือกรายการ")
                    else:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("po_log").delete().eq("TxID", target_txid).execute()
                        st.success("✅ ลบประวัติถาวรแล้ว!")
                        st.rerun()

# ==========================================
# หน้า 5: ระบบจ่ายเงิน & เครดิต
# ==========================================
elif menu == "💳 ระบบจ่ายเงิน & เครดิต":
    st.header("💳 ระบบจัดการบัญชี (Payment & Credit)")
    
    if po_log_df.empty:
        st.info("ยังไม่มีข้อมูลใบสั่งซื้อในระบบ")
    else:
        valid_pos = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
        
        if valid_pos.empty:
            st.info("ไม่มีรายการสั่งซื้อที่ต้องชำระเงิน")
        else:
            po_summary = valid_pos.groupby('PO_ID').agg({'Net_Price': 'sum', 'Shop_Name': 'first', 'Timestamp': 'first'}).reset_index()
            
            if not po_payments_df.empty:
                paid_summary = po_payments_df.groupby('PO_ID')['Amount_Paid'].sum().reset_index()
                merged_df = pd.merge(po_summary, paid_summary, on='PO_ID', how='left').fillna(0)
            else:
                merged_df = po_summary.copy()
                merged_df['Amount_Paid'] = 0
                
            merged_df['Balance'] = merged_df['Net_Price'] - merged_df['Amount_Paid']
            
            def get_pay_status(row):
                if row['Balance'] <= 0: return "✅ จ่ายครบแล้ว"
                elif row['Amount_Paid'] > 0: return "⏳ ทยอยจ่าย (Partial)"
                else: return "🔴 ค้างชำระ"
                
            merged_df['Pay_Status'] = merged_df.apply(get_pay_status, axis=1)
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("💵 บันทึกการจ่ายเงิน (ชำระหนี้)")
                pending_bills = merged_df[merged_df['Balance'] > 0].copy()
                
                if not pending_bills.empty:
                    pending_bills['Display_Bill'] = pending_bills.apply(lambda row: f"{row['PO_ID']} ({row['Shop_Name']}) | ค้าง: ฿{row['Balance']:,.2f}", axis=1)
                    
                    with st.form("make_payment_form"):
                        selected_bill = st.selectbox("เลือกบิลที่ต้องการชำระ", pending_bills['Display_Bill'], index=None)
                        pay_amount = st.number_input("จำนวนเงินที่จ่าย (บาท)", min_value=0.0, step=100.0)
                        pay_note = st.text_input("หมายเหตุ (เช่น โอนเข้ากสิกร, จ่ายสด)")
                        
                        if st.form_submit_button("✅ บันทึกการโอนเงิน"):
                            if not selected_bill or pay_amount <= 0:
                                st.error("❌ กรุณาเลือกบิลและใส่จำนวนเงินให้ถูกต้อง")
                            else:
                                target_poid = selected_bill.split(" ")[0]
                                tz_th = timezone(timedelta(hours=7))
                                current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")
                                
                                supabase.table("po_payments").insert({
                                    "PO_ID": target_poid, 
                                    "Timestamp": current_time, 
                                    "Amount_Paid": float(pay_amount), 
                                    "Note": pay_note
                                }).execute()
                                
                                st.success(f"บันทึกยอดชำระ {pay_amount:,.2f} บาท ของบิล {target_poid} เรียบร้อย!")
                                st.rerun()
                else:
                    st.success("🎉 ไม่มีบิลค้างชำระเลยครับ!")

            with col2:
                st.subheader("📋 สถานะหนี้และการชำระเงินของทุก PO")
                filter_status = st.radio("ตัวกรองสถานะ", ["แสดงทั้งหมด", "ค้างชำระ/ทยอยจ่าย", "จ่ายครบแล้ว"], horizontal=True)
                
                view_df = merged_df.copy()
                if filter_status == "ค้างชำระ/ทยอยจ่าย":
                    view_df = view_df[view_df['Pay_Status'].isin(["🔴 ค้างชำระ", "⏳ ทยอยจ่าย (Partial)"])]
                elif filter_status == "จ่ายครบแล้ว":
                    view_df = view_df[view_df['Pay_Status'] == "✅ จ่ายครบแล้ว"]
                    
                display_finance = view_df.rename(columns={
                    "PO_ID": "เลขที่ PO", 
                    "Shop_Name": "ร้านค้า", 
                    "Net_Price": "ยอดรวมบิล", 
                    "Amount_Paid": "จ่ายแล้ว", 
                    "Balance": "ยอดคงค้าง", 
                    "Pay_Status": "สถานะการจ่าย"
                })
                
                st.dataframe(display_finance[['เลขที่ PO', 'ร้านค้า', 'ยอดรวมบิล', 'จ่ายแล้ว', 'ยอดคงค้าง', 'สถานะการจ่าย']], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("⚠️ ยกเลิกประวัติการจ่ายเงิน (Void Payment)")
            st.caption("ดึงยอดค้างชำระกลับคืน ในกรณีที่ลงบันทึกการโอนเงินผิดพลาด")
            
            if not po_payments_df.empty:
                po_payments_df['Display_Pay'] = po_payments_df.apply(lambda row: f"{row['id']} | PO: {row['PO_ID']} | จ่าย: ฿{row['Amount_Paid']:,.2f} | วันที่: {str(row['Timestamp']).split(' ')[0]}", axis=1)
                
                with st.form("void_payment_form"):
                    pay_to_void = st.selectbox("เลือกรายการโอนเงินที่ต้องการยกเลิก", po_payments_df['Display_Pay'], index=None, placeholder="🔍 เลือกลายการจ่ายเงิน...")
                    
                    if st.form_submit_button("❌ ยกเลิกการโอนเงินนี้ (ดึงยอดหนี้กลับ)"):
                        if not pay_to_void:
                            st.error("❌ กรุณาเลือกรายการที่ต้องการยกเลิก")
                        else:
                            pay_id = pay_to_void.split(" | ")[0]
                            supabase.table("po_payments").delete().eq("id", int(pay_id)).execute()
                            st.success("✅ ยกเลิกการจ่ายเงินเรียบร้อย ยอดหนี้ถูกปรับกลับอัตโนมัติ")
                            st.rerun()
            else:
                st.info("ยังไม่มีประวัติการจ่ายเงินให้ยกเลิก")

# ==========================================
# หน้า 6: ประวัติเบิกงาน & ยกเลิก
# ==========================================
elif menu == "📝 ประวัติเบิกงาน & ยกเลิก":
    st.header("📝 ประวัติเบิก-รับของ & ยกเลิกรายการ")
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        hide_voided = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว", value=True)
        display_df = transaction_df.copy()
        
        if hide_voided:
            display_df = display_df[display_df['Status'] != 'Voided (ยกเลิก)']
            
        display_history_df = display_df.iloc[::-1].rename(columns={
            "TxID": "รหัสบิล", 
            "Timestamp": "เวลา", 
            "Action": "ประเภท", 
            "Item_Name": "ชื่อวัสดุ", 
            "Qty": "จำนวน", 
            "Worker": "ผู้เบิก/ผู้รับ", 
            "Status": "สถานะ", 
            "Boat_Name": "ชื่อเรือ"
        })
        
        total_hist_rows = len(display_history_df)
        total_hist_pages = max(1, math.ceil(total_hist_rows / 20))
        
        if st.session_state.page_hist > total_hist_pages or st.session_state.page_hist < 1:
            st.session_state.page_hist = 1
            
        start_h_idx = (st.session_state.page_hist - 1) * 20
        end_h_idx = start_h_idx + 20

        st.dataframe(display_history_df.iloc[start_h_idx:end_h_idx], use_container_width=True, hide_index=True)
        
        pg_h1, pg_h2, pg_h3 = st.columns([1, 2, 1])
        with pg_h1:
            st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_hist, args=(-1,), disabled=(st.session_state.page_hist <= 1), use_container_width=True, key="prev_hist")
        with pg_h2:
            st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_h_idx + 1 if total_hist_rows > 0 else 0} - {min(end_h_idx, total_hist_rows)} <br>(จากทั้งหมด {total_hist_rows} รายการ)</div>", unsafe_allow_html=True)
        with pg_h3:
            st.button("หน้าถัดไป ➡️", on_click=change_page_hist, args=(1,), disabled=(st.session_state.page_hist >= total_hist_pages), use_container_width=True, key="next_hist")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ ยกเลิกบิล / ดึงสต๊อกกลับ (Void)")
            valid_tx = transaction_df[transaction_df['Status'] == 'Completed'].copy()
            
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True, key="tx_void_mode")
                
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} ชิ้น)", axis=1)
                    
                    with st.form("void_single_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการเบิกที่ต้องการยกเลิก", valid_tx['Display_Single'], index=None)
                        
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกรายการ")
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
                        tx_to_void_display = st.selectbox("เลือกบิลที่ต้องการยกเลิก", group_summary['Display_Bulk'], index=None)
                        
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกบิล")
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
            transaction_df['Display_Del'] = transaction_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            
            with st.form("hard_delete_tx_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", transaction_df['Display_Del'], index=None)
                
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if not tx_to_delete:
                        st.error("❌ กรุณาเลือกรายการ")
                    else:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("transaction_log").delete().eq("TxID", target_txid).execute()
                        st.success("✅ ลบประวัติถาวรแล้ว!")
                        st.rerun()
                        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ ยกเลิกบิล / ดึงสต๊อกกลับ (Void)")
            valid_tx = transaction_df[transaction_df['Status'] == 'Completed'].copy()
            
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True, key="tx_void_mode")
                
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} ชิ้น)", axis=1)
                    
                    with st.form("void_single_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการเบิกที่ต้องการยกเลิก", valid_tx['Display_Single'], index=None)
                        
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกรายการ")
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
                        tx_to_void_display = st.selectbox("เลือกบิลที่ต้องการยกเลิก", group_summary['Display_Bulk'], index=None)
                        
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            if not tx_to_void_display:
                                st.error("❌ กรุณาเลือกบิล")
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
            transaction_df['Display_Del'] = transaction_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            
            with st.form("hard_delete_tx_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", transaction_df['Display_Del'], index=None)
                
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if not tx_to_delete:
                        st.error("❌ กรุณาเลือกรายการ")
                    else:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("transaction_log").delete().eq("TxID", target_txid).execute()
                        st.success("✅ ลบประวัติถาวรแล้ว!")
                        st.rerun()
