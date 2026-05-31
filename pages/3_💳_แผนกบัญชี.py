import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client
import requests
import base64
import io
from PIL import Image

st.set_page_config(page_title="Accounting Department", layout="wide")

# 👇👇👇 วางลิงก์ Google Apps Script ของคุณตรงนี้ 👇👇👇
GAS_URL = "วางลิงก์_WEB_APP_URL_ของคุณตรงนี้"
# 👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆👆

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

# ฟังก์ชันบีบอัดรูปภาพ
def compress_image(uploaded_file):
    img = Image.open(uploaded_file)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img.thumbnail((800, 800))
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=60) 
    
    return base64.b64encode(output.getvalue()).decode('utf-8')

po_log_df = load_data("po_log")
po_payments_df = load_data("po_payments")
receipts_df = load_data("accounting_receipts")

st.title("💳 แผนกบัญชีและการเงิน (Accounting & Finance)")

tab1, tab2, tab3 = st.tabs(["🧾 บันทึกค่าใช้จ่ายทั่วไป (อัปโหลดบิล)", "💳 จัดการหนี้ร้านค้า (จากใบ PO)", "🗂️ คลังเอกสารบิล"])

# ==========================================
# TAB 1: บันทึกค่าใช้จ่ายทั่วไป (อัปโหลดรูปบิล)
# ==========================================
with tab1:
    st.subheader("🧾 บันทึกค่าใช้จ่ายทั่วไป (เงินสดย่อย / บิลที่ไม่มี PO)")
    st.caption("อัปโหลดรูปบิลที่นี่ ระบบจะบีบอัดรูปอัตโนมัติและส่งไปเก็บใน Google Drive ให้ทันที")
    
    col_f1, col_f2 = st.columns([1.2, 1])
    
    with col_f1:
        with st.form("receipt_upload_form", clear_on_submit=True):
            r_date = st.date_input("วันที่ในบิล")
            r_shop = st.text_input("ชื่อร้านค้า / ผู้รับเงิน *")
            
            # --- แก้ไข: เพิ่มระบบกรอกหมวดหมู่เพิ่มเติม ---
            c_cat1, c_cat2 = st.columns(2)
            categories = ["ค่าวัสดุ/อุปกรณ์", "ค่าแรงช่าง", "ค่าขนส่ง", "ค่าอาหาร/รับรอง", "ค่าใช้จ่ายเบ็ดเตล็ด", "อื่นๆ"]
            r_category = c_cat1.selectbox("หมวดหมู่ค่าใช้จ่าย", categories)
            r_custom_cat = c_cat2.text_input("พิมพ์หมวดหมู่ใหม่ (กรณีเลือก 'อื่นๆ')")
            
            r_amount = st.number_input("จำนวนเงินรวม (บาท) *", min_value=0.0, step=1.0)
            r_note = st.text_input("หมายเหตุเพิ่มเติม (ถ้ามี)")
            
            st.markdown("---")
            st.write("📷 **แนบรูปภาพบิล/สลิปโอนเงิน**")
            uploaded_file = st.file_uploader("รองรับไฟล์ JPG, PNG", type=['jpg', 'jpeg', 'png'])
            
            submit_btn = st.form_submit_button("💾 บันทึกค่าใช้จ่าย & อัปโหลดรูป", type="primary", use_container_width=True)
            
            if submit_btn:
                # จัดการหมวดหมู่
                final_category = r_custom_cat.strip() if r_category == "อื่นๆ" else r_category
                
                if not r_shop or r_amount <= 0:
                    st.error("❌ กรุณากรอกชื่อร้านค้า และ จำนวนเงินให้ถูกต้อง")
                elif r_category == "อื่นๆ" and not r_custom_cat.strip():
                    st.error("❌ กรุณาพิมพ์ระบุหมวดหมู่ในช่อง 'พิมพ์หมวดหมู่ใหม่' ด้วยครับ")
                elif not uploaded_file:
                    st.error("❌ กรุณาแนบรูปภาพบิล/สลิปโอนเงินด้วยครับ")
                elif GAS_URL == "วางลิงก์_WEB_APP_URL_ของคุณตรงนี้":
                    st.error("❌ ยังไม่ได้ใส่ลิงก์ Google Apps Script ในโค้ดครับ")
                else:
                    with st.spinner('กำลังบีบอัดรูปภาพและอัปโหลดไปที่ Google Drive... ⏳'):
                        try:
                            base64_img = compress_image(uploaded_file)
                            
                            payload = {
                                "base64": base64_img,
                                "filename": f"BILL_{r_date}_{r_shop}.jpg",
                                "mimeType": "image/jpeg"
                            }
                            response = requests.post(GAS_URL, json=payload)
                            res_data = response.json()
                            
                            if res_data.get('status') == 'success':
                                image_url = res_data.get('url')
                                
                                supabase.table("accounting_receipts").insert({
                                    "Date": str(r_date),
                                    "Shop_Name": r_shop,
                                    "Category": final_category,
                                    "Amount": float(r_amount),
                                    "Note": r_note,
                                    "Receipt_URL": image_url
                                }).execute()
                                
                                st.success("✅ บันทึกข้อมูลและอัปโหลดรูปบิลเสร็จสมบูรณ์!")
                                st.rerun()
                            else:
                                st.error(f"🚨 อัปโหลดรูปไม่สำเร็จ: {res_data.get('message')}")
                                
                        except Exception as e:
                            st.error(f"🚨 เกิดข้อผิดพลาดของระบบ: {e}")

    with col_f2:
        st.info("💡 **รู้หรือไม่?** ระบบจะทำการย่อขนาดรูปภาพของคุณจากขนาดเต็ม (เช่น 3-5 MB) ให้เหลือเพียงประมาณ **50-100 KB** ก่อนส่งขึ้น Cloud เสมอ ทำให้คุณประหยัดพื้นที่จัดเก็บได้มากกว่า 50 เท่า!")
        
        st.write("📊 **สรุปยอดค่าใช้จ่ายทั่วไป (บิลที่ไม่มี PO)**")
        
        # --- แก้ไข: เพิ่มการโชว์ยอดเงินรวม ---
        total_receipts = len(receipts_df) if not receipts_df.empty else 0
        total_amount = receipts_df['Amount'].sum() if not receipts_df.empty else 0.0
        
        c_m1, c_m2 = st.columns(2)
        c_m1.metric("จำนวนบิลในระบบ", f"{total_receipts} ใบ")
        c_m2.metric("ยอดรวมทั้งหมด", f"฿ {total_amount:,.2f}")

# ==========================================
# TAB 2: จัดการหนี้ร้านค้า (จากใบ PO)
# ==========================================
with tab2:
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
                st.subheader("💵 บันทึกการจ่ายเงิน (ชำระหนี้ PO)")
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
                                    "PO_ID": target_poid, "Timestamp": current_time, 
                                    "Amount_Paid": float(pay_amount), "Note": pay_note
                                }).execute()
                                st.success(f"บันทึกยอดชำระ {pay_amount:,.2f} บาท เรียบร้อย!")
                                st.rerun()
                else:
                    st.success("🎉 ไม่มีบิล PO ค้างชำระเลยครับ!")

            with col2:
                st.subheader("📋 สถานะหนี้และการชำระเงินของทุก PO")
                filter_status = st.radio("ตัวกรองสถานะ", ["แสดงทั้งหมด", "ค้างชำระ/ทยอยจ่าย", "จ่ายครบแล้ว"], horizontal=True)
                
                view_df = merged_df.copy()
                if filter_status == "ค้างชำระ/ทยอยจ่าย":
                    view_df = view_df[view_df['Pay_Status'].isin(["🔴 ค้างชำระ", "⏳ ทยอยจ่าย (Partial)"])]
                elif filter_status == "จ่ายครบแล้ว":
                    view_df = view_df[view_df['Pay_Status'] == "✅ จ่ายครบแล้ว"]
                    
                display_finance = view_df.rename(columns={"PO_ID": "เลขที่ PO", "Shop_Name": "ร้านค้า", "Net_Price": "ยอดรวมบิล", "Amount_Paid": "จ่ายแล้ว", "Balance": "ยอดคงค้าง", "Pay_Status": "สถานะการจ่าย"})
                st.dataframe(display_finance[['เลขที่ PO', 'ร้านค้า', 'ยอดรวมบิล', 'จ่ายแล้ว', 'ยอดคงค้าง', 'สถานะการจ่าย']], use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("⚠️ ยกเลิกประวัติการจ่ายเงิน (Void Payment)")
            if not po_payments_df.empty:
                po_payments_df['Display_Pay'] = po_payments_df.apply(lambda row: f"รหัส: {row['id']} | PO: {row['PO_ID']} | จ่าย: ฿{row['Amount_Paid']:,.2f} | วันที่: {str(row['Timestamp']).split(' ')[0]}", axis=1)
                
                with st.form("void_payment_form"):
                    pay_to_void = st.selectbox("เลือกรายการโอนเงินที่ต้องการยกเลิก", po_payments_df['Display_Pay'], index=None)
                    if st.form_submit_button("❌ ยกเลิกการโอนเงินนี้ (ดึงยอดหนี้กลับ)"):
                        if not pay_to_void:
                            st.error("❌ กรุณาเลือกรายการที่ต้องการยกเลิก")
                        else:
                            pay_id = pay_to_void.split(" | ")[0].replace("รหัส: ", "")
                            supabase.table("po_payments").delete().eq("id", int(pay_id)).execute()
                            st.success("✅ ยกเลิกการจ่ายเงินเรียบร้อย ยอดหนี้ถูกปรับกลับอัตโนมัติ")
                            st.rerun()

# ==========================================
# TAB 3: คลังเอกสารบิล (ดูรูปบิล)
# ==========================================
with tab3:
    st.subheader("🗂️ คลังเอกสารบิลและค่าใช้จ่ายทั่วไป")
    if receipts_df.empty:
        st.info("ยังไม่มีประวัติการอัปโหลดบิลทั่วไป")
    else:
        display_receipts = receipts_df.sort_values(by='id', ascending=False).rename(columns={
            "Date": "วันที่", "Shop_Name": "ร้านค้า", "Category": "หมวดหมู่", "Amount": "ยอดเงิน", "Note": "หมายเหตุ"
        })
        
        st.dataframe(
            display_receipts[['วันที่', 'ร้านค้า', 'หมวดหมู่', 'ยอดเงิน', 'หมายเหตุ']], 
            use_container_width=True, hide_index=True
        )
        
        st.markdown("---")
        st.subheader("🔍 ค้นหาและดูรูปภาพบิล")
        
        receipts_df['Display_Select'] = receipts_df.apply(lambda r: f"{r['Date']} - {r['Shop_Name']} (฿{r['Amount']:,.2f})", axis=1)
        selected_to_view = st.selectbox("เลือกบิลที่ต้องการดูรูปภาพ", receipts_df['Display_Select'], index=None)
        
        if selected_to_view:
            target_row = receipts_df[receipts_df['Display_Select'] == selected_to_view].iloc[0]
            img_url = target_row['Receipt_URL']
            
            st.write(f"**กำลังแสดงบิลของร้าน:** {target_row['Shop_Name']}")
            st.markdown(f"[🔗 คลิกลิงก์นี้ หากรูปไม่แสดง หรือต้องการดูรูปเต็มๆ ในหน้าต่างใหม่]({img_url})")
            
            try:
                st.image(img_url, caption=f"บิลวันที่ {target_row['Date']}", width=500)
            except:
                st.warning("⚠️ ไม่สามารถโหลดรูปพรีวิวได้ กรุณากดที่ลิงก์ด้านบนเพื่อดูรูป")
                
        # --- ฟีเจอร์ลบประวัติบิล ---
        with st.expander("🗑️ ลบประวัติค่าใช้จ่ายทั่วไป (ระวัง: ลบแล้วกู้คืนไม่ได้)"):
            with st.form("del_receipt_form"):
                item_to_del = st.selectbox("เลือกลายการที่จะลบทิ้ง", receipts_df['Display_Select'], index=None)
                if st.form_submit_button("❌ ลบรายการนี้ถาวร"):
                    if item_to_del:
                        target_id = receipts_df[receipts_df['Display_Select'] == item_to_del].iloc[0]['id']
                        supabase.table("accounting_receipts").delete().eq("id", int(target_id)).execute()
                        st.success("✅ ลบข้อมูลออกจากฐานข้อมูลเรียบร้อยแล้ว!")
                        st.rerun()
