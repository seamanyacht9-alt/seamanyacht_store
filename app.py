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

# ตั้งค่าสถานะหน้า
if 'page_inv' not in st.session_state: st.session_state.page_inv = 1
if 'page_hist' not in st.session_state: st.session_state.page_hist = 1
if 'page_po_hist' not in st.session_state: st.session_state.page_po_hist = 1

def change_page_inv(delta): st.session_state.page_inv += delta
def change_page_hist(delta): st.session_state.page_hist += delta
def change_page_po_hist(delta): st.session_state.page_po_hist += delta

# ==========================================
# เมนูด้านข้าง
# ==========================================
st.sidebar.title("🛥️ ระบบจัดการอู่เรือ")
menu = st.sidebar.radio("เมนูหลัก", [
    "📊 แดชบอร์ด (ภาพรวม)",
    "📦 สต๊อกวัสดุ", 
    "🛒 เบิก-รับของ (หน้างาน)", 
    "📋 ระบบจัดซื้อ (PO)", 
    "📝 ประวัติ & ยกเลิกรายการ",
    "📑 ประวัติจัดซื้อ & พิมพ์บิล"
])

# ==========================================
# หน้า 0: แดชบอร์ดภาพรวม (ใหม่ล่าสุด)
# ==========================================
if menu == "📊 แดชบอร์ด (ภาพรวม)":
    st.header("📊 แดชบอร์ดสรุปข้อมูลอู่เรือ")
    
    # 1. กล่องสรุปตัวเลข (Metrics)
    col1, col2, col3, col4 = st.columns(4)
    
    total_items = len(inventory_df) if not inventory_df.empty else 0
    
    low_stock_count = 0
    if not inventory_df.empty:
        inventory_df['Min_Stock'] = inventory_df['Min_Stock'].fillna(0).astype(int)
        low_stock_count = len(inventory_df[inventory_df['Stock'] <= inventory_df['Min_Stock']])
        
    total_po_spent = po_log_df[po_log_df['Status'] != 'Voided (ยกเลิก)']['Net_Price'].sum() if not po_log_df.empty else 0
    
    total_withdraws = 0
    if not transaction_df.empty:
        total_withdraws = len(transaction_df[(transaction_df['Action'] == 'เบิกออก') & (transaction_df['Status'] == 'Completed')])

    with col1: st.metric("📦 รายการวัสดุทั้งหมด", f"{total_items} รายการ")
    with col2: st.metric("⚠️ วัสดุใกล้หมดสต๊อก", f"{low_stock_count} รายการ")
    with col3: st.metric("💸 ยอดจัดซื้อสะสม", f"฿ {total_po_spent:,.2f}")
    with col4: st.metric("🔧 จำนวนครั้งที่เบิกของ", f"{total_withdraws} ครั้ง")

    st.markdown("---")

    # 2. กราฟและตารางแจ้งเตือน
    c_graph, c_alert = st.columns([2, 1])
    
    with c_graph:
        st.subheader("📈 ยอดการสั่งซื้อแยกตามร้านค้า")
        if not po_log_df.empty:
            valid_po = po_log_df[po_log_df['Status'] != 'Voided (ยกเลิก)']
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
            st.error("กรุณาทำใบขอซื้อสำหรับรายการด้านบนโดยด่วน!")
        else:
            st.success("✅ สต๊อกวัสดุทุกรายการอยู่ในเกณฑ์ปกติ")

# ==========================================
# หน้า 1: สต๊อกวัสดุ
# ==========================================
elif menu == "📦 สต๊อกวัสดุ":
    st.header("📦 สต๊อกวัสดุคงเหลือ")
    
    if not inventory_df.empty:
        if 'Min_Stock' not in inventory_df.columns: inventory_df['Min_Stock'] = 0
        if 'Unit' not in inventory_df.columns: inventory_df['Unit'] = 'ชิ้น'
        inventory_df['Min_Stock'] = inventory_df['Min_Stock'].fillna(0).astype(int)
        inventory_df['Unit'] = inventory_df['Unit'].fillna('ชิ้น').astype(str)
        
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
                            "Item_Code": new_code, "Item_Name": new_name, "Zone": final_zone, 
                            "Stock": int(new_stock), "Min_Stock": int(new_min_stock), "Unit": new_unit.strip()
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
                                    "Item_Code": edit_code, "Item_Name": edit_name, "Zone": edit_zone, 
                                    "Stock": edit_stock, "Min_Stock": edit_min_stock, "Unit": edit_unit.strip()
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
        if 'stock_filter' not in st.session_state: st.session_state.stock_filter = "แสดงทั้งหมด"
        
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
            "Status": "สถานะ", "Item_Code": "รหัสวัสดุ", "Item_Name": "ชื่อวัสดุ", 
            "Zone": "โซน/หมวดหมู่", "Stock": "ยอดคงเหลือ", "Unit": "หน่วยนับ", "Min_Stock": "ขั้นต่ำ"
        }).drop(columns=['id'], errors='ignore')
        cols = ["สถานะ", "รหัสวัสดุ", "ชื่อวัสดุ", "โซน/หมวดหมู่", "ยอดคงเหลือ", "หน่วยนับ", "ขั้นต่ำ"]
        display_inv_df = display_inv_df[cols]

        total_rows = len(display_inv_df)
        total_pages = max(1, math.ceil(total_rows / 20))
        
        if st.session_state.page_inv > total_pages or st.session_state.page_inv < 1: st.session_state.page_inv = 1
        start_idx = (st.session_state.page_inv - 1) * 20
        end_idx = start_idx + 20

        st.dataframe(display_inv_df.iloc[start_idx:end_idx], use_container_width=True, hide_index=True)
        
        pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
        with pg_col1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_inv, args=(-1,), disabled=(st.session_state.page_inv <= 1), use_container_width=True, key="prev_inv")
        with pg_col2:
            st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_idx + 1 if total_rows > 0 else 0} - {min(end_idx, total_rows)} <br>(จากทั้งหมด {total_rows} รายการ)</div>", unsafe_allow_html=True)
            st.selectbox("เลือกหน้า", range(1, total_pages + 1), key="page_inv", label_visibility="collapsed")
        with pg_col3: st.button("หน้าถัดไป ➡️", on_click=change_page_inv, args=(1,), disabled=(st.session_state.page_inv >= total_pages), use_container_width=True, key="next_inv")
        
        excel_data_inv = to_excel(display_inv_df)
        st.download_button("📥 ดาวน์โหลดไฟล์ Excel", data=excel_data_inv, file_name=file_name_inv, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

# ==========================================
# หน้า 2: ระบบเบิก-รับของ
# ==========================================
elif menu == "🛒 เบิก-รับของ (หน้างาน)":
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
                                "Action": action, "Item_Name": item, "Qty": int(qty), 
                                "Worker": worker, "Boat_Name": boat_name if boat_name else "-" 
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
            display_cart_df = cart_df.rename(columns={"Action": "ประเภท", "Item_Name": "ชื่อวัสดุ", "Qty": "จำนวน", "Worker": "ผู้เบิก/รับ", "Boat_Name": "ชื่อเรือ"}).drop(columns=['id'])
            st.dataframe(display_cart_df, use_container_width=True, hide_index=True)
            
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("🗑️ ล้างตะกร้าทั้งหมด", type="secondary"):
                    supabase.table("cart_db").delete().gte("id", 0).execute()
                    st.rerun()
            with c_b:
                if st.button("💾 ยืนยันตัดสต๊อก 1 บิล", type="primary"):
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
                            "TxID": item_txid, "Timestamp": current_time, "Action": row['Action'],
                            "Item_Name": row['Item_Name'], "Qty": int(row['Qty']),
                            "Worker": row['Worker'], "Boat_Name": row['Boat_Name'], "Status": "Completed"
                        }).execute()
                        
                    supabase.table("cart_db").delete().gte("id", 0).execute()
                    st.success(f"✅ ตัดสต๊อกเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 3: ระบบจัดซื้อ (PO) 
# ==========================================
elif menu == "📋 ระบบจัดซื้อ (PO)":
    st.header("📋 ระบบออกใบขอซื้อ / ใบสั่งซื้อ (PO)")
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        st.subheader("1. ข้อมูลบิล (ระบุครั้งเดียว)")
        with st.container(border=True):
            requester = st.text_input("ชื่อผู้ขอซื้อ / แผนก", placeholder="เช่น สโตร์, พี่ต๋อง, พ่อพี่เทิด")
            shop_name = st.text_input("ซื้อจากร้าน (ชื่อร้าน)", placeholder="พิมพ์ชื่อร้านค้า...")

        st.subheader("2. เพิ่มรายการลงใบสั่งซื้อ")
        all_items = inventory_df['Item_Name'].tolist() if not inventory_df.empty else []
        with st.form("add_po_form", clear_on_submit=True):
            selected_item = st.selectbox("เลือกรายการวัสดุ", all_items, index=None, placeholder="🔍 พิมพ์ค้นหารายการ...")
            c1, c2 = st.columns(2)
            qty = c1.number_input("จำนวน", min_value=1, step=1)
            price_per_unit = c2.number_input("ราคา/หน่วย (บาท)", min_value=0.0, step=1.0)
            c3, c4 = st.columns(2)
            discount = c3.number_input("ส่วนลดรวมรายการนี้ (บาท)", min_value=0.0, step=1.0)
            shipping = c4.number_input("ค่าส่ง/VAT รายการนี้ (บาท)", min_value=0.0, step=1.0)
            
            if st.form_submit_button("➕ นำลงใบสั่งซื้อ"):
                if not requester or not selected_item or not shop_name:
                    st.error("❌ กรุณากรอก ชื่อผู้ขอซื้อ, ชื่อร้าน และเลือกรายการ ให้ครบถ้วน")
                else:
                    unit_val = inventory_df.loc[inventory_df['Item_Name'] == selected_item, 'Unit'].values[0]
                    net_price = (qty * price_per_unit) - discount + shipping
                    try:
                        supabase.table("po_cart_db").insert({
                            "Requester": requester, "Item_Name": selected_item, "Qty": int(qty), 
                            "Unit": str(unit_val), "Price_Per_Unit": float(price_per_unit),
                            "Discount": float(discount), "Shipping": float(shipping),
                            "Net_Price": float(net_price), "Shop_Name": shop_name
                        }).execute()
                        st.success(f"✅ เพิ่ม {selected_item} ลงใบสั่งซื้อแล้ว")
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 นำลงตะกร้าสั่งซื้อไม่สำเร็จ: {e}")

    with col2:
        st.subheader("3. รายการที่รอสั่งซื้อ")
        if po_cart_df.empty:
            st.info("ยังไม่มีรายการในตะกร้าจัดซื้อ")
        else:
            display_po_cart = po_cart_df.rename(columns={"Requester": "ผู้ขอซื้อ", "Item_Name": "รายการ", "Qty": "จำนวน", "Unit": "หน่วย", "Price_Per_Unit": "ราคา/หน่วย", "Discount": "ส่วนลด", "Shipping": "ค่าส่ง", "Net_Price": "ราคาสุทธิ", "Shop_Name": "ชื่อร้าน"}).drop(columns=['id'])
            st.dataframe(display_po_cart, use_container_width=True, hide_index=True)
            total_po_amount = po_cart_df['Net_Price'].sum()
            st.markdown(f"<h4 style='text-align: right; color: green;'>รวมยอดบิลนี้: ฿ {total_po_amount:,.2f}</h4>", unsafe_allow_html=True)
            
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("🗑️ ล้างตะกร้าสั่งซื้อ", type="secondary"):
                    supabase.table("po_cart_db").delete().gte("id", 0).execute()
                    st.rerun()
            with c_b:
                if st.button("💾 บันทึกใบสั่งซื้อ (Save PO)", type="primary"):
                    next_po_num = 1
                    if not po_log_df.empty:
                        po_rows = po_log_df['PO_ID'].unique()
                        nums = [int(str(x).replace('PO_', '')) for x in po_rows if 'PO_' in str(x)]
                        if nums: next_po_num = max(nums) + 1
                    po_id = f"PO_{next_po_num:04d}" 
                    tz_th = timezone(timedelta(hours=7))
                    current_time = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

                    for idx, row in po_cart_df.iterrows():
                        tx_id = f"{po_id}-{idx+1}"
                        supabase.table("po_log").insert({
                            "TxID": tx_id, "PO_ID": po_id, "Timestamp": current_time, 
                            "Requester": row['Requester'], "Item_Name": row['Item_Name'], 
                            "Qty": int(row['Qty']), "Unit": str(row['Unit']),
                            "Price_Per_Unit": float(row['Price_Per_Unit']), "Discount": float(row['Discount']),
                            "Shipping": float(row['Shipping']), "Net_Price": float(row['Net_Price']),
                            "Shop_Name": row['Shop_Name'], "Status": "รอรับของ"
                        }).execute()
                    supabase.table("po_cart_db").delete().gte("id", 0).execute()
                    st.success(f"✅ บันทึกใบสั่งซื้อ {po_id} เข้าสู่ระบบประวัติเรียบร้อยแล้ว!")
                    st.rerun()

# ==========================================
# หน้า 4: ประวัติเบิก-รับ
# ==========================================
elif menu == "📝 ประวัติ & ยกเลิกรายการ":
    st.header("📝 ประวัติเบิก-รับของ & ยกเลิกบิล")
    if transaction_df.empty:
        st.info("ยังไม่มีประวัติการทำรายการ")
    else:
        if 'Boat_Name' in transaction_df.columns:
            unique_boats = [b for b in transaction_df['Boat_Name'].unique() if pd.notna(b) and b != "-"]
            all_boat_options = ["📋 ดูประวัติทั้งหมด"] + unique_boats
            selected_boat_filter = st.selectbox("⚓ ค้นหาประวัติการเบิกตามชื่อเรือ", all_boat_options, index=None, placeholder="🔍 พิมพ์ชื่อเรือ...")
            if not selected_boat_filter or selected_boat_filter == "📋 ดูประวัติทั้งหมด":
                base_df = transaction_df
                file_name_hist = "History.xlsx"
            else:
                base_df = transaction_df[transaction_df['Boat_Name'] == selected_boat_filter]
                file_name_hist = f"History_{selected_boat_filter}.xlsx"
        else:
            base_df = transaction_df 
            file_name_hist = "History.xlsx"
            
        hide_voided = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว (Voided) จากตารางด้านล่าง", value=True)
        display_df = base_df.copy()
        if hide_voided: display_df = display_df[display_df['Status'] != 'Voided (ยกเลิก)']
            
        display_history_df = display_df.iloc[::-1].rename(columns={"TxID": "รหัสบิล", "Timestamp": "วันเวลาที่ทำรายการ", "Action": "ประเภท", "Item_Name": "ชื่อวัสดุ", "Qty": "จำนวน", "Worker": "ผู้เบิก/ผู้รับ", "Status": "สถานะ", "Boat_Name": "ชื่อเรือ"})
        total_hist_rows = len(display_history_df)
        total_hist_pages = max(1, math.ceil(total_hist_rows / 20))
        
        if st.session_state.page_hist > total_hist_pages or st.session_state.page_hist < 1: st.session_state.page_hist = 1
        start_h_idx = (st.session_state.page_hist - 1) * 20
        end_h_idx = start_h_idx + 20

        st.dataframe(display_history_df.iloc[start_h_idx:end_h_idx], use_container_width=True, hide_index=True)
        
        pg_h1, pg_h2, pg_h3 = st.columns([1, 2, 1])
        with pg_h1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_hist, args=(-1,), disabled=(st.session_state.page_hist <= 1), use_container_width=True, key="prev_hist")
        with pg_h2: st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_h_idx + 1 if total_hist_rows > 0 else 0} - {min(end_h_idx, total_hist_rows)} <br>(จากทั้งหมด {total_hist_rows} รายการ)</div>", unsafe_allow_html=True)
        with pg_h3: st.button("หน้าถัดไป ➡️", on_click=change_page_hist, args=(1,), disabled=(st.session_state.page_hist >= total_hist_pages), use_container_width=True, key="next_hist")
        
        excel_data_hist = to_excel(display_history_df) 
        st.download_button("📥 ดาวน์โหลดไฟล์ Excel", data=excel_data_hist, file_name=file_name_hist, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ ดึงสต๊อกกลับ (Void)")
            valid_tx = base_df[base_df['Status'] == 'Completed'].copy()
            if not valid_tx.empty:
                void_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละชิ้น", "เหมาทั้งบิล"], horizontal=True)
                if void_mode == "ทีละชิ้น":
                    valid_tx['Display_Single'] = valid_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} ชิ้น)", axis=1)
                    with st.form("void_single_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการ", valid_tx['Display_Single'], index=None)
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if tx_to_void_display:
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
                        tx_to_void_display = st.selectbox("เลือกบิล", group_summary['Display_Bulk'], index=None)
                        if st.form_submit_button("ยกเลิกทั้งบิล"):
                            if tx_to_void_display:
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
            base_df['Display_Del'] = base_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            with st.form("hard_delete_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", base_df['Display_Del'], index=None)
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if tx_to_delete:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("transaction_log").delete().eq("TxID", target_txid).execute()
                        st.success("✅ ลบถาวรแล้ว!")
                        st.rerun()

# ==========================================
# หน้า 5: ประวัติการจัดซื้อ & พิมพ์บิล (ใหม่ล่าสุด)
# ==========================================
elif menu == "📑 ประวัติจัดซื้อ & พิมพ์บิล":
    st.header("📑 ประวัติจัดซื้อ & พิมพ์ใบสั่งซื้อ (PO)")
    
    if po_log_df.empty:
        st.info("ยังไม่มีประวัติการจัดซื้อในระบบ")
    else:
        # ฟีเจอร์: เลือก PO เพื่อเปิดดูและพิมพ์เป็น PDF
        st.subheader("🖨️ พิมพ์ใบสั่งซื้อ (Print / Save as PDF)")
        po_list = sorted(po_log_df['PO_ID'].unique(), reverse=True)
        selected_po_to_print = st.selectbox("เลือกเลขที่ PO ที่ต้องการพิมพ์", po_list, index=None, placeholder="🔍 พิมพ์เพื่อค้นหาเลข PO...")
        
        if selected_po_to_print:
            po_data = po_log_df[po_log_df['PO_ID'] == selected_po_to_print]
            total_net = po_data['Net_Price'].sum()
            vendor = po_data.iloc[0]['Shop_Name']
            requester = po_data.iloc[0]['Requester']
            date_str = str(po_data.iloc[0]['Timestamp']).split(' ')[0]
            
            # โค้ดสร้างเอกสาร HTML ใบสั่งซื้อ เพื่อใช้สำหรับสั่ง Print > Save as PDF
            html_invoice = f"""
            <html><head><style>
                body {{ font-family: 'Sarabun', 'Arial', sans-serif; color: #333; padding: 20px; }}
                h2 {{ text-align: center; color: #1a365d; }}
                .info-box {{ width: 100%; margin-bottom: 20px; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
                .info-box div {{ margin-bottom: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 14px; }}
                th {{ background-color: #1a365d; color: white; }}
                .total-row td {{ font-weight: bold; background-color: #f7fafc; }}
                .total-amt {{ color: #e53e3e; text-align: right; }}
                .btn-print {{ display: block; width: 200px; margin: 20px auto; padding: 10px; text-align: center; background-color: #3182ce; color: white; text-decoration: none; border-radius: 5px; cursor: pointer; font-weight: bold; border: none; }}
                .btn-print:hover {{ background-color: #2b6cb0; }}
                @media print {{ .btn-print {{ display: none; }} }}
            </style></head>
            <body>
                <h2>ใบสั่งซื้อ (Purchase Order)</h2>
                <div class="info-box">
                    <div><strong>เลขที่เอกสาร:</strong> {selected_po_to_print}</div>
                    <div><strong>วันที่สั่งซื้อ:</strong> {date_str}</div>
                    <div><strong>สั่งซื้อจากร้าน:</strong> {vendor}</div>
                    <div><strong>ผู้ขอซื้อ:</strong> {requester}</div>
                </div>
                <table>
                    <tr>
                        <th>ลำดับ</th><th>รายการสินค้า</th><th>จำนวน</th><th>หน่วย</th><th>ราคา/หน่วย</th><th>ราคาสุทธิ</th>
                    </tr>
            """
            
            for idx, row in po_data.iterrows():
                # ดึงรหัสวัสดุมาแสดง (ถ้ามี)
                item_code_val = "-"
                if not inventory_df.empty:
                    match_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']]
                    if not match_item.empty:
                        item_code_val = match_item.iloc[0]['Item_Code']
                        
                html_invoice += f"""
                    <tr>
                        <td style='text-align: center;'>{str(idx).split('-')[-1] if '-' in str(idx) else '-'}</td>
                        <td>[{item_code_val}] {row['Item_Name']}</td>
                        <td style='text-align: center;'>{row['Qty']}</td>
                        <td style='text-align: center;'>{row['Unit']}</td>
                        <td style='text-align: right;'>{row['Price_Per_Unit']:,.2f}</td>
                        <td style='text-align: right;'>{row['Net_Price']:,.2f}</td>
                    </tr>
                """
                
            html_invoice += f"""
                    <tr class="total-row">
                        <td colspan="5" style='text-align: right;'>ยอดรวมสุทธิ (Grand Total):</td>
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
                <button class="btn-print" onclick="window.print()">🖨️ พิมพ์ / Save PDF (กดตรงนี้)</button>
            </body></html>
            """
            
            st.info("👇 คุณสามารถเลื่อนดูเอกสารด้านล่าง แล้วกดปุ่มพิมพ์ (Print) ในกรอบเพื่อ Save เป็นไฟล์ PDF ได้เลยครับ (ในหน้าต่างปริ้นให้เลือก Destination เป็น 'Save as PDF')")
            components.html(html_invoice, height=600, scrolling=True)

        st.markdown("---")
        
        # ตารางแสดงประวัติแบบเดิม
        hide_voided_po = st.checkbox("👁️ ซ่อนรายการที่ยกเลิกไปแล้ว (Voided) จากตารางด้านล่าง", value=True)
        base_po_df = po_log_df.copy()
        if hide_voided_po: base_po_df = base_po_df[base_po_df['Status'] != 'Voided (ยกเลิก)']
            
        display_po_df = base_po_df.iloc[::-1].rename(columns={"TxID": "รหัสรายการ", "PO_ID": "เลขที่ PO", "Timestamp": "วันเวลา", "Requester": "ผู้ขอซื้อ", "Item_Name": "รายการ", "Qty": "จำนวน", "Unit": "หน่วย", "Price_Per_Unit": "ราคา/หน่วย", "Discount": "ส่วนลด", "Shipping": "ค่าส่ง", "Net_Price": "ราคาสุทธิ", "Shop_Name": "ร้านค้า", "Status": "สถานะ"})
        
        total_po_rows = len(display_po_df)
        total_po_pages = max(1, math.ceil(total_po_rows / 20))
        if st.session_state.page_po_hist > total_po_pages or st.session_state.page_po_hist < 1: st.session_state.page_po_hist = 1

        start_po_idx = (st.session_state.page_po_hist - 1) * 20
        end_po_idx = start_po_idx + 20

        st.dataframe(display_po_df.iloc[start_po_idx:end_po_idx], use_container_width=True, hide_index=True)
        
        pg_p1, pg_p2, pg_p3 = st.columns([1, 2, 1])
        with pg_p1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_po_hist, args=(-1,), disabled=(st.session_state.page_po_hist <= 1), use_container_width=True, key="prev_po_hist")
        with pg_p2: st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการลำดับที่ {start_po_idx + 1 if total_po_rows > 0 else 0} - {min(end_po_idx, total_po_rows)} <br>(จากทั้งหมด {total_po_rows} รายการ)</div>", unsafe_allow_html=True)
        with pg_p3: st.button("หน้าถัดไป ➡️", on_click=change_page_po_hist, args=(1,), disabled=(st.session_state.page_po_hist >= total_po_pages), use_container_width=True, key="next_po_hist")
        
        excel_data_po = to_excel(display_po_df)
        st.download_button("📥 ดาวน์โหลดไฟล์ Excel (ประวัติจัดซื้อ)", data=excel_data_po, file_name="PO_History.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        
        st.markdown("---")
        
        # ระบบยกเลิก (Void) สำหรับ PO
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ ยกเลิกรายการสั่งซื้อ (Void)")
            valid_po_tx = po_log_df[po_log_df['Status'] != 'Voided (ยกเลิก)'].copy()
            if not valid_po_tx.empty:
                void_po_mode = st.radio("เลือกโหมดการยกเลิก", ["ทีละรายการ", "เหมาทั้งบิล (PO)"], horizontal=True, key="po_void_mode")
                if void_po_mode == "ทีละรายการ":
                    valid_po_tx['Display_Single'] = valid_po_tx.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} ({row['Qty']} {row['Unit']})", axis=1)
                    with st.form("void_single_po_form"):
                        tx_to_void_display = st.selectbox("เลือกรายการ", valid_po_tx['Display_Single'], index=None)
                        if st.form_submit_button("ยกเลิกรายการนี้"):
                            if tx_to_void_display:
                                target_txid = tx_to_void_display.split(" | ")[0]
                                supabase.table("po_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", target_txid).execute()
                                st.success("✅ ยกเลิกรายการเรียบร้อย")
                                st.rerun()
                else:
                    group_po_summary = valid_po_tx.groupby('PO_ID').agg({'Requester': 'first', 'Item_Name': 'count'}).reset_index()
                    group_po_summary['Display_Bulk'] = group_po_summary.apply(lambda row: f"{row['PO_ID']} | ขอโดย: {row['Requester']} ({row['Item_Name']} รายการ)", axis=1)
                    with st.form("void_bulk_po_form"):
                        po_to_void_display = st.selectbox("เลือกบิล PO", group_po_summary['Display_Bulk'], index=None)
                        if st.form_submit_button("ยกเลิกทั้งบิล PO"):
                            if po_to_void_display:
                                selected_po_group = po_to_void_display.split(" | ")[0]
                                supabase.table("po_log").update({"Status": "Voided (ยกเลิก)"}).eq("PO_ID", selected_po_group).execute()
                                st.success("✅ ยกเลิกบิลเรียบร้อย")
                                st.rerun()
        with col2:
            st.subheader("🗑️ ลบประวัติถาวร (Hard Delete)")
            po_log_df['Display_Del'] = po_log_df.apply(lambda row: f"{row['TxID']} | {row['Item_Name']} | {row['Status']}", axis=1)
            with st.form("hard_delete_po_form"):
                tx_to_delete = st.selectbox("เลือกประวัติที่ต้องการลบทิ้ง", po_log_df['Display_Del'], index=None)
                if st.form_submit_button("❌ ลบทิ้งถาวร"):
                    if tx_to_delete:
                        target_txid = tx_to_delete.split(" | ")[0]
                        supabase.table("po_log").delete().eq("TxID", target_txid).execute()
                        st.success("✅ ลบประวัติถาวรแล้ว!")
                        st.rerun()
