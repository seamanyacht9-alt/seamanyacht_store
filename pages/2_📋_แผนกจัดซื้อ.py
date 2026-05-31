import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta, timezone
from supabase import create_client
import io
import math

st.set_page_config(page_title="Purchasing Department", layout="wide")

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

inventory_df = load_data("inventory_db")
po_cart_df = load_data("po_cart_db")
po_log_df = load_data("po_log")

st.title("📋 แผนกจัดซื้อ")

tab1, tab2, tab3, tab4 = st.tabs(["🛒 สร้างใบสั่งซื้อ (PO)", "📑 ประวัติจัดซื้อ & พิมพ์ PDF", "✏️ แก้ไขข้อมูลบิล", "🛠️ จัดการบิล (ยกเลิก/ตีกลับ)"])

# ==========================================
# TAB 1: สร้างใบสั่งซื้อ (PO)
# ==========================================
with tab1:
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.subheader("1. ข้อมูลบิล")
        with st.container(border=True):
            requester = st.text_input("ชื่อผู้ขอซื้อ / แผนก", placeholder="เช่น พี่ต๋อง, สโตร์")
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
                selected_item = st.selectbox("เลือกรายการวัสดุที่มีในคลัง", all_items, index=None)
                unit_input = "" 
                
            c1, c2 = st.columns(2)
            qty = c1.number_input("จำนวน", min_value=1, step=1)
            price_per_unit = c2.number_input("ราคา/หน่วย (บาท)", min_value=0.0, step=1.0)
            
            c3, c4, c5 = st.columns(3)
            discount = c3.number_input("ส่วนลด (บาท)", min_value=0.0, step=1.0)
            shipping = c4.number_input("ค่าส่ง (บาท)", min_value=0.0, step=1.0)
            vat = c5.number_input("ภาษี VAT (บาท)", min_value=0.0, step=1.0)
            
            if st.form_submit_button("➕ นำลงใบสั่งซื้อ"):
                if not requester or not selected_item or not shop_name:
                    st.error("❌ กรุณากรอก ชื่อผู้ขอซื้อ, ชื่อร้าน และรายการ ให้ครบถ้วน")
                else:
                    unit_val = unit_input.strip() if is_new_item else inventory_df.loc[inventory_df['Item_Name'] == selected_item, 'Unit'].values[0]
                    net_price = (qty * price_per_unit) - discount + shipping + vat
                    
                    supabase.table("po_cart_db").insert({
                        "Requester": requester, "Item_Name": selected_item, "Qty": int(qty), 
                        "Unit": str(unit_val), "Price_Per_Unit": float(price_per_unit),
                        "Discount": float(discount), "Shipping": float(shipping), "VAT": float(vat),
                        "Net_Price": float(net_price), "Shop_Name": shop_name
                    }).execute()
                    st.success(f"✅ เพิ่ม {selected_item} ลงใบสั่งซื้อแล้ว")
                    st.rerun()

    with col2:
        st.subheader("3. รายการที่รอสั่งซื้อ")
        if po_cart_df.empty:
            st.info("ยังไม่มีรายการในตะกร้าจัดซื้อ")
        else:
            po_cart_df['VAT'] = po_cart_df.get('VAT', 0)
            display_po_cart = po_cart_df.rename(columns={"Item_Name": "รายการ", "Qty": "จำนวน", "Unit": "หน่วย", "Price_Per_Unit": "ราคา", "Net_Price": "สุทธิ"}).drop(columns=['id', 'Requester', 'Discount', 'Shipping', 'VAT', 'Shop_Name'], errors='ignore')
            st.dataframe(display_po_cart, use_container_width=True, hide_index=True)
            st.markdown(f"<h4 style='text-align: right; color: green;'>รวมยอดบิล: ฿ {po_cart_df['Net_Price'].sum():,.2f}</h4>", unsafe_allow_html=True)
            
            with st.expander("🗑️ ลบเฉพาะบางรายการ"):
                po_cart_df['Display_Cart'] = po_cart_df.apply(lambda r: f"{r['id']} | {r['Item_Name']} ({r['Qty']})", axis=1)
                with st.form("del_po_cart_item"):
                    item_to_del = st.selectbox("เลือกรายการที่จะลบ", po_cart_df['Display_Cart'], index=None)
                    if st.form_submit_button("❌ ลบรายการนี้", use_container_width=True):
                        if item_to_del:
                            supabase.table("po_cart_db").delete().eq("id", int(item_to_del.split(" | ")[0])).execute()
                            st.rerun()

            c_a, c_b = st.columns(2)
            if c_a.button("🗑️ ล้างตะกร้า", use_container_width=True):
                supabase.table("po_cart_db").delete().gte("id", 0).execute()
                st.rerun()
            if c_b.button("💾 บันทึก PO", type="primary", use_container_width=True):
                next_po_num = 1
                if not po_log_df.empty:
                    po_rows = po_log_df['PO_ID'].unique()
                    nums = [int(str(x).replace('PO_', '')) for x in po_rows if 'PO_' in str(x)]
                    if nums: next_po_num = max(nums) + 1
                        
                po_id = f"PO_{next_po_num:04d}" 
                tz_th = timezone(timedelta(hours=7))
                ctime = datetime.now(tz_th).strftime("%Y-%m-%d %H:%M:%S")

                for idx, row in po_cart_df.iterrows():
                    tx_id = f"{po_id}-{idx+1}"
                    if row['Item_Name'] not in inventory_df['Item_Name'].values:
                        supabase.table("inventory_db").insert({"Item_Code": f"NEW-{tx_id}", "Item_Name": row['Item_Name'], "Zone": "รอจัดหมวดหมู่", "Stock": 0, "Min_Stock": 0, "Unit": row['Unit']}).execute()

                    supabase.table("po_log").insert({
                        "TxID": tx_id, "PO_ID": po_id, "Timestamp": ctime, "Requester": row['Requester'], 
                        "Item_Name": row['Item_Name'], "Qty": int(row['Qty']), "Unit": str(row['Unit']),
                        "Price_Per_Unit": float(row['Price_Per_Unit']), "Discount": float(row['Discount']),
                        "Shipping": float(row['Shipping']), "VAT": float(row.get('VAT', 0)),
                        "Net_Price": float(row['Net_Price']), "Shop_Name": row['Shop_Name'], "Status": "รอรับของ"
                    }).execute()
                supabase.table("po_cart_db").delete().gte("id", 0).execute()
                st.success(f"บันทึก {po_id} เรียบร้อย!")
                st.rerun()

# ==========================================
# TAB 2: ประวัติจัดซื้อ & พิมพ์ PDF
# ==========================================
with tab2:
    if po_log_df.empty:
        st.info("ยังไม่มีประวัติการจัดซื้อ")
    else:
        st.subheader("🖨️ ดาวน์โหลด / พิมพ์ใบสั่งซื้อ (PDF)")
        po_list = sorted(po_log_df['PO_ID'].unique(), reverse=True)
        selected_po_to_print = st.selectbox("เลือกเลขที่ PO", po_list, index=None)
        
        if selected_po_to_print:
            po_data = po_log_df[po_log_df['PO_ID'] == selected_po_to_print]
            total_net = po_data['Net_Price'].sum()
            date_str = str(po_data.iloc[0]['Timestamp']).split(' ')[0]
            
            html_invoice = f"""
            <!DOCTYPE html>
            <html lang="th">
            <head>
                <meta charset="UTF-8">
                <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
                <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
                <style>
                    /* ใส่ฟอนต์สำรอง Tahoma เผื่อกรณี html2pdf โหลดฟอนต์หลักไม่ทัน */
                    body {{ font-family: 'Sarabun', 'Tahoma', sans-serif; color: #333; padding: 10px; background-color: white; line-height: 1.4; }}
                    #invoice-content {{ padding: 10px; background-color: white; }}
                    h2 {{ text-align: center; color: #1a365d; margin-bottom: 5px; font-size: 22px; }}
                    .info-box {{ width: 100%; margin-bottom: 10px; border-bottom: 2px solid #ddd; padding-bottom: 5px; text-align: center; font-size: 14px; }}
                    
                    /* ปรับสัดส่วนตารางให้พอดี */
                    table {{ width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 11.5px; }}
                    th, td {{ border: 1px solid #ddd; padding: 5px; text-align: left; word-wrap: break-word; }}
                    th {{ background-color: #1a365d; color: white; text-align: center; padding: 6px; }}
                    .total-row td {{ font-weight: bold; background-color: #f7fafc; padding: 8px; }}
                    .total-amt {{ color: #e53e3e; text-align: right; }}
                    .signature-box {{ page-break-inside: avoid; margin-top: 20px; font-size: 13px; }}
                    
                    /* ปุ่มกด */
                    .btn-container {{ display: flex; justify-content: center; gap: 15px; margin-top: 20px; }}
                    .btn-print, .btn-download {{ padding: 10px 20px; color: white; text-decoration: none; border-radius: 5px; cursor: pointer; font-weight: bold; border: none; font-family: inherit; font-size: 14px; transition: 0.3s; }}
                    .btn-print {{ background-color: #3182ce; }} .btn-print:hover {{ background-color: #2b6cb0; }}
                    .btn-download {{ background-color: #38a169; }} .btn-download:hover {{ background-color: #2f855a; }}
                    
                    /* ซ่อนปุ่มเวลากดปริ้นแบบ Native */
                    @media print {{
                        .btn-container {{ display: none !important; }}
                        @page {{ margin: 10mm; }}
                        body {{ padding: 0; }}
                    }}
                </style>
            </head>
            <body>
                <div id="invoice-content">
                    <h2>ใบสั่งซื้อ (Purchase Order)</h2>
                    <div class="info-box">
                        <strong>เลขที่เอกสาร:</strong> {selected_po_to_print} &nbsp;&nbsp;|&nbsp;&nbsp;
                        <strong>วันที่:</strong> {date_str} &nbsp;&nbsp;|&nbsp;&nbsp;
                        <strong>ผู้ขอซื้อ:</strong> จัดซื้อ
                    </div>
                    <table>
                        <tr>
                            <th style="width: 5%;">ลำดับ</th>
                            <th style="width: 25%;">รายการสินค้า</th>
                            <th style="width: 10%;">ผู้ขอซื้อ</th>
                            <th style="width: 14%;">ร้านค้า</th>
                            <th style="width: 6%;">จำนวน</th>
                            <th style="width: 6%;">หน่วย</th>
                            <th style="width: 9%;">ราคา/หน่วย</th>
                            <th style="width: 7%;">ค่าส่ง</th>
                            <th style="width: 7%;">VAT</th>
                            <th style="width: 11%;">ราคาสุทธิ</th>
                        </tr>
            """
            
            counter = 1
            for idx, row in po_data.iterrows():
                item_code_val = "-"
                if not inventory_df.empty:
                    m_item = inventory_df[inventory_df['Item_Name'] == row['Item_Name']]
                    if not m_item.empty: item_code_val = m_item.iloc[0]['Item_Code']
                
                req_val = row.get('Requester', '-')
                ship_val = row.get('Shipping', 0)
                vat_val = row.get('VAT', 0)
                
                html_invoice += f"""
                        <tr>
                            <td style='text-align: center;'>{counter}</td>
                            <td>[{item_code_val}] {row['Item_Name']}</td>
                            <td style='text-align: center;'>{req_val}</td>
                            <td style='text-align: center;'>{row['Shop_Name']}</td>
                            <td style='text-align: center;'>{row['Qty']}</td>
                            <td style='text-align: center;'>{row['Unit']}</td>
                            <td style='text-align: right;'>{row['Price_Per_Unit']:,.2f}</td>
                            <td style='text-align: right;'>{ship_val:,.2f}</td>
                            <td style='text-align: right;'>{vat_val:,.2f}</td>
                            <td style='text-align: right;'>{row['Net_Price']:,.2f}</td>
                        </tr>
                """
                counter += 1
                
            html_invoice += f"""
                        <tr class="total-row">
                            <td colspan="9" style='text-align: right;'>ยอดรวมสุทธิ (Grand Total):</td>
                            <td class="total-amt">฿ {total_net:,.2f}</td>
                        </tr>
                    </table>
                    
                    <table class="signature-box" style="width: 100%; border: none; text-align: center;">
                        <tr style="border: none;">
                            <td style="border: none; padding-top: 30px;">________________________<br><br>ผู้จัดทำ / ฝ่ายจัดซื้อ</td>
                            <td style="border: none; padding-top: 30px;">________________________<br><br>ผู้อนุมัติสั่งซื้อ</td>
                        </tr>
                    </table>
                </div>
                
                <div class="btn-container">
                    <button class="btn-print" onclick="nativePrint()">🖨️ เปิดดู / พิมพ์ (Print)</button>
                    <button class="btn-download" onclick="downloadPDF()">📥 ดาวน์โหลด PDF</button>
                </div>

                <script>
                    function getPDFOptions() {{
                        return {{
                            margin:       [5, 5, 5, 5],
                            filename:     '{selected_po_to_print}.pdf',
                            image:        {{ type: 'jpeg', quality: 1.0 }},
                            html2canvas:  {{ scale: 2, useCORS: true, scrollY: 0, windowY: 0 }},
                            jsPDF:        {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
                        }};
                    }}

                    // ดาวน์โหลดผ่านปลั๊กอิน (มีโอกาสภาษาไทยเพี้ยน)
                    function downloadPDF() {{
                        window.scrollTo(0, 0);
                        var element = document.getElementById('invoice-content');
                        html2pdf().set(getPDFOptions()).from(element).save();
                    }}

                    // ใช้ระบบ Print ของเบราว์เซอร์ (ภาษาไทยสมบูรณ์ 100%)
                    function nativePrint() {{
                        window.print();
                    }}
                </script>
            </body></html>
            """
            components.html(html_invoice, height=650, scrolling=True)

        st.markdown("---")
        st.subheader("📋 ตารางประวัติการสั่งซื้อ (PO)")
        hide_voided_po = st.checkbox("👁️ ซ่อนรายการที่ถูกยกเลิก/ตีกลับ", value=True)
        b_po_df = po_log_df.copy()
        if hide_voided_po: b_po_df = b_po_df[~b_po_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
        
        if 'VAT' not in b_po_df.columns: b_po_df['VAT'] = 0
        if 'Shipping' not in b_po_df.columns: b_po_df['Shipping'] = 0
            
        d_po_df = b_po_df.iloc[::-1].rename(columns={"TxID": "รหัส", "PO_ID": "PO", "Requester": "ผู้ขอ", "Item_Name": "รายการ", "Qty": "จำนวน", "Shipping":"ค่าส่ง", "Net_Price": "ราคาสุทธิ", "Shop_Name": "ร้านค้า", "Status": "สถานะ"})
        
        if 'page_po_hist' not in st.session_state: st.session_state.page_po_hist = 1
        def change_page_po_hist(delta): st.session_state.page_po_hist += delta
        
        total_po_rows = len(d_po_df)
        total_po_pages = max(1, math.ceil(total_po_rows / 20))
        if st.session_state.page_po_hist > total_po_pages or st.session_state.page_po_hist < 1: st.session_state.page_po_hist = 1
        start_po_idx = (st.session_state.page_po_hist - 1) * 20
        end_po_idx = start_po_idx + 20
        
        st.dataframe(d_po_df.iloc[start_po_idx:end_po_idx][['รหัส', 'PO', 'ผู้ขอ', 'รายการ', 'จำนวน', 'ค่าส่ง', 'VAT', 'ราคาสุทธิ', 'ร้านค้า', 'สถานะ']], use_container_width=True, hide_index=True)
        
        pg_p1, pg_p2, pg_p3 = st.columns([1, 2, 1])
        with pg_p1: st.button("⬅️ หน้าก่อนหน้า", on_click=change_page_po_hist, args=(-1,), disabled=(st.session_state.page_po_hist <= 1), use_container_width=True, key="prev_po")
        with pg_p2: st.markdown(f"<div style='text-align: center; color: gray;'>แสดงรายการ {start_po_idx + 1 if total_po_rows > 0 else 0} - {min(end_po_idx, total_po_rows)}</div>", unsafe_allow_html=True)
        with pg_p3: st.button("หน้าถัดไป ➡️", on_click=change_page_po_hist, args=(1,), disabled=(st.session_state.page_po_hist >= total_po_pages), use_container_width=True, key="next_po")
        
        st.download_button("📥 ดาวน์โหลด Excel", data=to_excel(d_po_df), file_name="PO_History.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# TAB 3: ✏️ แก้ไขข้อมูลบิล
# ==========================================
with tab3:
    st.subheader("✏️ แก้ไขข้อมูลบิลสั่งซื้อ")
    st.caption("ใช้แก้ไขกรณีคีย์ราคา, จำนวน, ค่าส่ง, หรือ VAT ผิดพลาด โดยไม่ต้องยกเลิกทั้งบิล")
    
    if po_log_df.empty:
        st.info("ยังไม่มีประวัติการจัดซื้อ")
    else:
        valid_edit_po = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])].copy()
        
        if not valid_edit_po.empty:
            valid_edit_po['Display_Edit'] = valid_edit_po.apply(lambda r: f"{r['TxID']} | {r['Item_Name']} (PO: {r['PO_ID']})", axis=1)
            selected_edit_tx = st.selectbox("🔍 ค้นหา/เลือกรายการที่ต้องการแก้ไข", valid_edit_po['Display_Edit'].iloc[::-1], index=None, placeholder="พิมพ์ค้นหารหัสรายการ หรือ ชื่อวัสดุ...")
            
            if selected_edit_tx:
                t_txid = selected_edit_tx.split(" | ")[0]
                t_data = valid_edit_po[valid_edit_po['TxID'] == t_txid].iloc[0]
                
                with st.form("edit_po_form"):
                    st.markdown(f"**กำลังแก้ไขรายการ:** {t_data['Item_Name']} *(สถานะปัจจุบัน: {t_data['Status']})*")
                    
                    c1, c2 = st.columns(2)
                    e_requester = c1.text_input("ผู้ขอซื้อ / แผนก", value=t_data.get('Requester', ''))
                    e_shop = c2.text_input("ร้านค้า", value=t_data.get('Shop_Name', ''))
                    
                    c3, c4 = st.columns(2)
                    e_qty = c3.number_input("จำนวน", min_value=1, step=1, value=int(t_data['Qty']))
                    e_price = c4.number_input("ราคา/หน่วย (บาท)", min_value=0.0, step=1.0, value=float(t_data['Price_Per_Unit']))
                    
                    c5, c6, c7 = st.columns(3)
                    e_discount = c5.number_input("ส่วนลด (บาท)", min_value=0.0, step=1.0, value=float(t_data.get('Discount', 0)))
                    e_shipping = c6.number_input("ค่าส่ง (บาท)", min_value=0.0, step=1.0, value=float(t_data.get('Shipping', 0)))
                    e_vat = c7.number_input("ภาษี VAT (บาท)", min_value=0.0, step=1.0, value=float(t_data.get('VAT', 0)))
                    
                    if st.form_submit_button("💾 บันทึกการแก้ไข", type="primary", use_container_width=True):
                        e_net_price = (e_qty * e_price) - e_discount + e_shipping + e_vat
                        old_qty = int(t_data['Qty'])
                        
                        if t_data['Status'] == '✅ รับแล้ว (เข้าคลัง)' and e_qty != old_qty:
                            qty_diff = e_qty - old_qty
                            t_item = inventory_df[inventory_df['Item_Name'] == t_data['Item_Name']]
                            if not t_item.empty:
                                new_stock = t_item.iloc[0]['Stock'] + qty_diff
                                supabase.table("inventory_db").update({"Stock": int(new_stock)}).eq("Item_Code", t_item.iloc[0]['Item_Code']).execute()
                                
                        supabase.table("po_log").update({
                            "Requester": e_requester, "Shop_Name": e_shop, "Qty": int(e_qty),
                            "Price_Per_Unit": float(e_price), "Discount": float(e_discount),
                            "Shipping": float(e_shipping), "VAT": float(e_vat), "Net_Price": float(e_net_price)
                        }).eq("TxID", t_txid).execute()
                        
                        st.success(f"✅ แก้ไขรายการ {t_txid} สำเร็จ! ราคาสุทธิใหม่คือ ฿{e_net_price:,.2f}")
                        st.rerun()
        else:
            st.info("ไม่มีรายการที่สามารถแก้ไขได้")

# ==========================================
# TAB 4: จัดการบิล (ยกเลิก / ตีกลับ)
# ==========================================
with tab4:
    st.subheader("🛠️ ยกเลิก หรือ ตีกลับสินค้า")
    c_ret, c_void = st.columns(2)
    
    with c_ret:
        valid_return = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
        valid_return['Display_Return'] = valid_return.apply(lambda r: f"{r['TxID']} | {r['Item_Name']} [{r['Status']}]", axis=1)
        with st.form("return_po_form"):
            return_item = st.selectbox("📦 ตีกลับสินค้า (เคลม)", valid_return['Display_Return'], index=None)
            if st.form_submit_button("ยืนยันตีกลับ", use_container_width=True):
                if return_item:
                    t_txid = return_item.split(" | ")[0]
                    t_data = valid_return[valid_return['TxID'] == t_txid].iloc[0]
                    if t_data['Status'] == '✅ รับแล้ว (เข้าคลัง)':
                        t_item = inventory_df[inventory_df['Item_Name'] == t_data['Item_Name']]
                        if not t_item.empty:
                            n_stock = t_item.iloc[0]['Stock'] - int(t_data['Qty'])
                            supabase.table("inventory_db").update({"Stock": int(n_stock)}).eq("Item_Code", t_item.iloc[0]['Item_Code']).execute()
                    supabase.table("po_log").update({"Status": "❌ ตีกลับ (ขอเงินคืน)"}).eq("TxID", t_txid).execute()
                    st.success("ตีกลับเรียบร้อย")
                    st.rerun()
                    
    with c_void:
        valid_po_tx = po_log_df[~po_log_df['Status'].isin(['Voided (ยกเลิก)', '❌ ตีกลับ (ขอเงินคืน)'])]
        valid_po_tx['Display_Single'] = valid_po_tx.apply(lambda r: f"{r['TxID']} | {r['Item_Name']}", axis=1)
        with st.form("void_single_po_form"):
            tx_to_void = st.selectbox("⚠️ ยกเลิกรายการสั่งซื้อ (Void)", valid_po_tx['Display_Single'], index=None)
            if st.form_submit_button("ยกเลิกรายการนี้", use_container_width=True):
                if tx_to_void:
                    t_txid = tx_to_void.split(" | ")[0]
                    t_data = valid_po_tx[valid_po_tx['TxID'] == t_txid].iloc[0]
                    if t_data['Status'] == '✅ รับแล้ว (เข้าคลัง)':
                        t_item = inventory_df[inventory_df['Item_Name'] == t_data['Item_Name']]
                        if not t_item.empty:
                            n_stock = t_item.iloc[0]['Stock'] - int(t_data['Qty'])
                            supabase.table("inventory_db").update({"Stock": int(n_stock)}).eq("Item_Code", t_item.iloc[0]['Item_Code']).execute()
                    supabase.table("po_log").update({"Status": "Voided (ยกเลิก)"}).eq("TxID", t_txid).execute()
                    st.success("ยกเลิกเรียบร้อย")
                    st.rerun()
