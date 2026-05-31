import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client

st.set_page_config(page_title="Accounting Department", layout="wide")

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

po_log_df = load_data("po_log")
po_payments_df = load_data("po_payments")

st.title("💳 แผนกบัญชีและการเงิน (Payment & Credit)")

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
                                "PO_ID": target_poid, "Timestamp": current_time, 
                                "Amount_Paid": float(pay_amount), "Note": pay_note
                            }).execute()
                            st.success(f"บันทึกยอดชำระ {pay_amount:,.2f} บาท เรียบร้อย!")
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
                
            display_finance = view_df.rename(columns={"PO_ID": "เลขที่ PO", "Shop_Name": "ร้านค้า", "Net_Price": "ยอดรวมบิล", "Amount_Paid": "จ่ายแล้ว", "Balance": "ยอดคงค้าง", "Pay_Status": "สถานะการจ่าย"})
            st.dataframe(display_finance[['เลขที่ PO', 'ร้านค้า', 'ยอดรวมบิล', 'จ่ายแล้ว', 'ยอดคงค้าง', 'สถานะการจ่าย']], use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("⚠️ ยกเลิกประวัติการจ่ายเงิน (Void Payment)")
        st.caption("ดึงยอดค้างชำระกลับคืน ในกรณีที่ลงบันทึกการโอนเงินผิดพลาด")
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
        else:
            st.info("ยังไม่มีประวัติการจ่ายเงินให้ยกเลิก")
