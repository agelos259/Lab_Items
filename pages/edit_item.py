from datetime import date

import streamlit as st
import psycopg2

from config import CONDITIONS
from db import get_connection
from queries import fetch_df, fetch_lookup


def page_edit_item() -> None:
    st.title("Edit Item")

    all_ids = fetch_df(
        "SELECT internal_id, item_name FROM items "
        "ORDER BY CAST(SUBSTR(internal_id, 5) AS INTEGER)"
    )
    if all_ids.empty:
        st.info("No items in database.")
        return

    id_labels = [f"{r['internal_id']} — {r['item_name']}" for _, r in all_ids.iterrows()]
    choice    = st.selectbox("Select item to edit", id_labels)
    chosen_id = choice.split(" — ")[0]

    conn  = get_connection()
    row   = conn.execute("SELECT * FROM items WHERE internal_id = ?", (chosen_id,)).fetchone()
    conn.close()

    locs  = fetch_lookup("locations", "location_id", "location_name")
    users = fetch_lookup("users",     "user_id",     "name")
    projs = fetch_lookup("projects",  "project_id",  "project_name")
    cats  = fetch_lookup("categories","category_id", "category_name")

    if not row:
        st.error("Item not found.")
        return

    cat_names    = list(cats.values())
    cur_cat_name = cats.get(row["category_id"], row["category"] or (cat_names[0] if cat_names else ""))
    cur_cat_idx  = cat_names.index(cur_cat_name) if cur_cat_name in cat_names else 0

    with st.form("edit_item_form"):
        c1, c2    = st.columns(2)
        item_name = c1.text_input("Item Name *", value=row["item_name"])
        model     = c2.text_input("Model",       value=row["model"] or "")

        c3, c4, c5 = st.columns(3)
        cat_label  = c3.selectbox("Category *", cat_names, index=cur_cat_idx)
        cat_id     = [k for k, v in cats.items() if v == cat_label][0]
        condition  = c4.selectbox("Condition *", CONDITIONS,
                                   index=CONDITIONS.index(row["condition"]))
        recv_opts  = ["—", "ΝΑΙ", "ΟΧΙ"]
        cur_recv   = row["received"] if row["received"] in recv_opts else "—"
        received   = c5.selectbox("Received", recv_opts, index=recv_opts.index(cur_recv))

        c6, c7 = st.columns(2)
        sn  = c6.text_input("Serial Number / S/N", value=row["manufacturer_sn"] or "")
        qty = c7.number_input("Quantity", min_value=1, value=int(row["quantity"] or 1), step=1)

        st.markdown("**Pricing** (optional)")
        p1, p2, p3, p4 = st.columns(4)
        unit_ex  = p1.number_input("Unit Price ex VAT",  min_value=0.0,
                                    value=float(row["unit_price_ex_vat"]  or 0), step=0.01, format="%.2f")
        unit_inc = p2.number_input("Unit Price inc VAT", min_value=0.0,
                                    value=float(row["unit_price_inc_vat"] or 0), step=0.01, format="%.2f")
        tot_ex   = p3.number_input("Total Price ex VAT", min_value=0.0,
                                    value=float(row["total_price_ex_vat"]  or 0), step=0.01, format="%.2f")
        tot_inc  = p4.number_input("Total Price inc VAT",min_value=0.0,
                                    value=float(row["total_price_inc_vat"] or 0), step=0.01, format="%.2f")

        loc_names   = list(locs.values())
        loc_ids     = list(locs.keys())
        cur_loc_idx = loc_ids.index(row["location_id"]) if row["location_id"] in loc_ids else 0
        loc_label   = st.selectbox("Location *", loc_names, index=cur_loc_idx)
        loc_id      = [k for k, v in locs.items() if v == loc_label][0]

        proj_options = ["— None —"] + list(projs.values())
        cur_proj     = projs.get(row["project_id"], "— None —")
        proj_label   = st.selectbox("Project", proj_options,
                                     index=proj_options.index(cur_proj) if cur_proj in proj_options else 0)
        proj_id      = None if proj_label == "— None —" \
                       else [k for k, v in projs.items() if v == proj_label][0]

        user_options = ["— Unassigned —"] + list(users.values())
        cur_user     = users.get(row["user_id"], "— Unassigned —")
        user_label   = st.selectbox("Assigned To", user_options,
                                     index=user_options.index(cur_user) if cur_user in user_options else 0)
        user_id      = None if user_label == "— Unassigned —" \
                       else [k for k, v in users.items() if v == user_label][0]

        cur_ret = None
        if row["expected_return_date"]:
            try:
                cur_ret = date.fromisoformat(row["expected_return_date"])
            except ValueError:
                pass
        ret_date  = st.date_input("Expected Return Date (optional)", value=cur_ret)
        submitted = st.form_submit_button("Save Changes", type="primary")

    if submitted:
        if not item_name.strip():
            st.error("Item Name is required.")
            return
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE items SET
                   item_name=?, category=?, category_id=?, model=?, manufacturer_sn=?,
                   quantity=?, condition=?, received=?,
                   unit_price_ex_vat=?, unit_price_inc_vat=?,
                   total_price_ex_vat=?, total_price_inc_vat=?,
                   expected_return_date=?, project_id=?, user_id=?, location_id=?
                   WHERE internal_id=?""",
                (item_name.strip(), cat_label, cat_id,
                 model.strip() or None, sn.strip() or None, qty,
                 condition, None if received == "—" else received,
                 unit_ex or None, unit_inc or None, tot_ex or None, tot_inc or None,
                 ret_date.isoformat() if ret_date else None,
                 proj_id, user_id, loc_id, chosen_id),
            )
            conn.commit()
            st.success(f"Item **{chosen_id}** updated.")
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error: {e}")
        finally:
            conn.close()

    st.divider()
    st.subheader("Delete Item")
    confirm_del = st.checkbox(f"I confirm I want to permanently delete **{chosen_id}**")
    if st.button("Delete Item", type="primary", disabled=not confirm_del):
        conn = get_connection()
        try:
            conn.execute("DELETE FROM items WHERE internal_id = ?", (chosen_id,))
            conn.commit()
            st.success(f"Item **{chosen_id}** deleted.")
            st.rerun()
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error: {e}")
        finally:
            conn.close()
