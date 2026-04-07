import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_lookup, get_next_lab_id


def page_add_item() -> None:
    st.title("Add New Item")

    conn    = get_connection()
    next_id = get_next_lab_id(conn)
    conn.close()

    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")
    projs = fetch_lookup("projects",  "project_id",  "project_name")
    cats  = fetch_lookup("categories","category_id", "category_name")

    st.info(f"Next available ID: **{next_id}**")

    with st.form("add_item_form", clear_on_submit=True):
        c1, c2    = st.columns(2)
        item_name = c1.text_input("Item Name *")
        model     = c2.text_input("Model")

        c3, c4, c5 = st.columns(3)
        cat_names  = list(cats.values())
        cat_label  = c3.selectbox("Category *", cat_names)
        cat_id     = [k for k, v in cats.items() if v == cat_label][0]
        condition  = c4.selectbox("Condition *", CONDITIONS)
        received   = c5.selectbox("Received", ["—", "ΝΑΙ", "ΟΧΙ"])

        c6, c7 = st.columns(2)
        sn  = c6.text_input("Serial Number / S/N (optional)")
        qty = c7.number_input("Quantity", min_value=1, value=1, step=1)

        st.markdown("**Pricing** (optional)")
        p1, p2, p3, p4 = st.columns(4)
        unit_ex  = p1.number_input("Unit Price ex VAT",  min_value=0.0, value=0.0, step=0.01, format="%.2f")
        unit_inc = p2.number_input("Unit Price inc VAT", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        tot_ex   = p3.number_input("Total Price ex VAT", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        tot_inc  = p4.number_input("Total Price inc VAT",min_value=0.0, value=0.0, step=0.01, format="%.2f")

        loc_label    = st.selectbox("Location *", list(locs.values()))
        loc_id       = [k for k, v in locs.items() if v == loc_label][0]
        proj_options = ["— None —"] + list(projs.values())
        proj_label   = st.selectbox("Project", proj_options)
        proj_id      = None if proj_label == "— None —" \
                       else [k for k, v in projs.items() if v == proj_label][0]
        user_options = ["— Unassigned —"] + list(users.values())
        user_label   = st.selectbox("Assigned To", user_options)
        user_id      = None if user_label == "— Unassigned —" \
                       else [k for k, v in users.items() if v == user_label][0]
        ret_date  = st.date_input("Expected Return Date (optional)", value=None)
        submitted = st.form_submit_button("Add Item", type="primary")

    if submitted:
        if not item_name.strip():
            st.error("Item Name is required.")
            return
        conn   = get_connection()
        new_id = get_next_lab_id(conn)
        try:
            conn.execute(
                """INSERT INTO items
                   (internal_id, item_name, category, category_id, model, manufacturer_sn,
                    quantity, condition, received,
                    unit_price_ex_vat, unit_price_inc_vat,
                    total_price_ex_vat, total_price_inc_vat,
                    expected_return_date, project_id, user_id, location_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id, item_name.strip(), cat_label, cat_id,
                 model.strip() or None, sn.strip() or None, qty,
                 condition, None if received == "—" else received,
                 unit_ex or None, unit_inc or None, tot_ex or None, tot_inc or None,
                 ret_date.isoformat() if ret_date else None,
                 proj_id, user_id, loc_id),
            )
            conn.commit()
            st.success(f"Item added with ID **{new_id}**.")
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error: {e}")
        finally:
            conn.close()
