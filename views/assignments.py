import streamlit as st
import psycopg2

from db import get_connection
from queries import fetch_df, fetch_lookup


def page_assignments() -> None:
    st.title("Item Assignments")

    users = fetch_lookup("users", "user_id", "name")

    df = fetch_df(
        """
        SELECT
            i.internal_id                                 AS "ID",
            i.item_name                                   AS "Item Name",
            COALESCE(cat.category_name, i.category, '—') AS "Category",
            l.location_name                               AS "Location",
            COALESCE(u.name, '— Unassigned —')            AS "Assigned To",
            i.condition                                   AS "Condition",
            i.user_id                                     AS _user_id
        FROM items i
        JOIN locations l         ON i.location_id  = l.location_id
        LEFT JOIN categories cat ON i.category_id  = cat.category_id
        LEFT JOIN users u        ON i.user_id      = u.user_id
        ORDER BY l.location_name,
                 CAST(SUBSTR(i.internal_id, 5) AS INTEGER)
        """
    )

    if df.empty:
        st.info("No items in the database.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([3, 2, 2])
    search      = c1.text_input("Search by name or ID", "")
    loc_options = ["All"] + sorted(df["Location"].unique().tolist())
    user_options_f = ["All", "Unassigned"] + list(users.values())
    loc_filter  = c2.selectbox("Location", loc_options)
    user_filter = c3.selectbox("Assigned To", user_options_f)

    filtered = df.copy()
    if search:
        mask = (
            filtered["Item Name"].str.contains(search, case=False, na=False) |
            filtered["ID"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if loc_filter != "All":
        filtered = filtered[filtered["Location"] == loc_filter]
    if user_filter == "Unassigned":
        filtered = filtered[filtered["Assigned To"] == "— Unassigned —"]
    elif user_filter != "All":
        filtered = filtered[filtered["Assigned To"] == user_filter]

    display = filtered.drop(columns=["_user_id"])
    st.caption(f"{len(filtered)} item(s)")
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.divider()

    # ── Bulk assign ───────────────────────────────────────────────────────────
    st.subheader("Assign Items")

    item_labels = [
        f"{r['ID']} — {r['Item Name']} · {r['Location']}"
        for _, r in filtered.iterrows()
    ]
    selected_labels = st.multiselect(
        "Select items to assign",
        options=item_labels,
        placeholder="Search or pick items…",
    )
    selected_ids = [lbl.split(" — ")[0] for lbl in selected_labels]

    col_a, col_b = st.columns(2)
    assign_to = col_a.selectbox(
        "Assign to user",
        ["— Select —", "— Unassign —"] + list(users.values()),
    )

    if col_b.button("Apply", type="primary", disabled=not selected_ids or assign_to == "— Select —"):
        if assign_to == "— Unassign —":
            new_user_id = None
            new_condition = "Available"
        else:
            new_user_id   = [k for k, v in users.items() if v == assign_to][0]
            new_condition = "In Use"

        conn = get_connection()
        saved, failed = [], []
        try:
            for iid in selected_ids:
                try:
                    conn.execute(
                        "UPDATE items SET user_id=?, condition=? WHERE internal_id=?",
                        (new_user_id, new_condition, iid),
                    )
                    saved.append(iid)
                except psycopg2.Error:
                    conn.rollback()
                    failed.append(iid)
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            st.error(f"Database error: {e}")
        finally:
            conn.close()

        if saved:
            action = f"unassigned" if assign_to == "— Unassign —" else f"assigned to **{assign_to}**"
            st.success(f"{len(saved)} item(s) {action}: {', '.join(f'`{i}`' for i in saved)}")
            st.rerun()
        if failed:
            st.error(f"Failed for: {', '.join(failed)}")
