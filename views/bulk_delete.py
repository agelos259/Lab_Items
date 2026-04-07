import streamlit as st
import psycopg2

from config import CONDITIONS, CATEGORIES
from db import get_connection
from queries import fetch_df, ITEMS_FULL_QUERY


def _bulk_delete_panel(
    df,
    id_col: str,
    label_col: str,
    table: str,
    editor_key: str,
    label_singular: str,
    db_id_col: str | None = None,
) -> None:
    if df.empty:
        st.info(f"No {label_singular.lower()}s found.")
        return

    df = df.copy().reset_index(drop=True)
    st.dataframe(df, use_container_width=True, hide_index=True)

    option_map: dict[str, str] = {
        str(row[id_col]): f"{row[id_col]} — {row[label_col]}"
        for _, row in df.iterrows()
    }
    all_labels = list(option_map.values())
    ms_key     = f"{editor_key}_ms"

    b1, b2, _ = st.columns([1, 1, 6])
    if b1.button("Select All", key=f"{editor_key}_sel_all"):
        st.session_state[ms_key] = all_labels
    if b2.button("Clear All", key=f"{editor_key}_clr_all"):
        st.session_state[ms_key] = []

    selected_labels = st.multiselect(
        f"Choose {label_singular.lower()}(s) to delete",
        options=all_labels,
        default=st.session_state.get(ms_key, []),
        key=ms_key,
    )

    label_to_id  = {v: k for k, v in option_map.items()}
    selected_ids = [label_to_id[lbl] for lbl in selected_labels]
    n            = len(selected_ids)
    st.caption(f"{n} of {len(df)} {label_singular.lower()}(s) selected")

    if n == 0:
        return

    st.warning(
        f"About to permanently delete **{n} {label_singular.lower()}(s)**: "
        + ", ".join(f"`{lbl.split(' — ', 1)[-1]}`" for lbl in selected_labels)
    )
    confirm = st.checkbox(
        f"Yes, delete these {n} {label_singular.lower()}(s)", key=f"{editor_key}_chk"
    )

    if st.button(
        f"Delete {n} Selected {label_singular}(s)",
        type="primary", disabled=not confirm, key=f"{editor_key}_btn",
    ):
        real_id_col = db_id_col if db_id_col else id_col
        conn        = get_connection()
        deleted, failed = [], []
        try:
            for rid, lbl in zip(selected_ids, selected_labels):
                display = lbl.split(" — ", 1)[-1]
                try:
                    conn.execute(f"DELETE FROM {table} WHERE {real_id_col} = ?", (rid,))
                    conn.commit()
                    deleted.append(display)
                except psycopg2.Error:
                    conn.rollback()
                    failed.append(display)
        finally:
            conn.close()

        if deleted:
            st.success(f"Deleted {len(deleted)}: {', '.join(deleted)}")
            st.session_state.pop(ms_key, None)
        if failed:
            st.error(
                f"Could not delete {len(failed)} (still referenced by items): "
                + ", ".join(failed)
            )
        if deleted:
            st.rerun()


def page_bulk_delete() -> None:
    st.title("Bulk Delete")
    st.markdown(
        "Tick the **Select** checkbox on the rows you want to remove, "
        "then confirm and click the delete button."
    )

    tab_items, tab_cats, tab_locs, tab_users, tab_projs = st.tabs(
        ["Items", "Categories", "Locations", "Users", "Projects"]
    )

    with tab_items:
        c1, c2, c3  = st.columns([3, 2, 2])
        search      = c1.text_input("Search name / model / ID", "", key="bd_search")
        cond_filter = c2.selectbox("Condition", ["All"] + CONDITIONS, key="bd_cond")
        cat_filter  = c3.selectbox("Category",  ["All"] + CATEGORIES, key="bd_cat")
        query  = ITEMS_FULL_QUERY + " WHERE 1=1"
        params: list = []
        if search:
            query  += " AND (i.item_name ILIKE ? OR i.internal_id ILIKE ? OR i.model ILIKE ?)"
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if cond_filter != "All":
            query += " AND i.condition = ?"
            params.append(cond_filter)
        if cat_filter != "All":
            query += " AND i.category = ?"
            params.append(cat_filter)
        query += " ORDER BY CAST(SUBSTR(i.internal_id, 5) AS INTEGER)"
        df_items = fetch_df(query, tuple(params))
        _bulk_delete_panel(df_items, "ID", "Item Name", "items",
                           "bd_items", "Item", db_id_col="internal_id")

    with tab_cats:
        df_cats = fetch_df(
            """SELECT c.category_id, c.category_name AS "Category Name",
                      COUNT(i.internal_id) AS "Items Linked"
               FROM categories c
               LEFT JOIN items i ON i.category_id = c.category_id
               GROUP BY c.category_id ORDER BY c.category_name"""
        )
        blocked = df_cats[df_cats["Items Linked"] > 0]
        if not blocked.empty:
            st.warning("Categories with items linked cannot be deleted: "
                       + ", ".join(f"**{r}**" for r in blocked["Category Name"].tolist()))
        _bulk_delete_panel(df_cats, "category_id", "Category Name", "categories", "bd_cats", "Category")

    with tab_locs:
        df_locs = fetch_df(
            """SELECT l.location_id, l.location_name AS "Location Name",
                      COUNT(i.internal_id) AS "Items Assigned"
               FROM locations l
               LEFT JOIN items i ON i.location_id = l.location_id
               GROUP BY l.location_id ORDER BY l.location_name"""
        )
        blocked = df_locs[df_locs["Items Assigned"] > 0]
        if not blocked.empty:
            st.warning("Locations with items cannot be deleted: "
                       + ", ".join(f"**{r}**" for r in blocked["Location Name"].tolist()))
        _bulk_delete_panel(df_locs, "location_id", "Location Name", "locations", "bd_locs", "Location")

    with tab_users:
        df_users = fetch_df(
            """SELECT u.user_id, u.name AS "Name", u.role AS "Role", u.email AS "Email",
                      COUNT(i.internal_id) AS "Items Assigned"
               FROM users u
               LEFT JOIN items i ON i.user_id = u.user_id
               GROUP BY u.user_id ORDER BY u.name"""
        )
        blocked = df_users[df_users["Items Assigned"] > 0]
        if not blocked.empty:
            st.warning("Users with items assigned cannot be deleted: "
                       + ", ".join(f"**{r}**" for r in blocked["Name"].tolist()))
        _bulk_delete_panel(df_users, "user_id", "Name", "users", "bd_users", "User")

    with tab_projs:
        df_projs = fetch_df(
            """SELECT p.project_id, p.project_name AS "Project Name",
                      p.grant_code AS "Grant Code", p.status AS "Status",
                      COUNT(i.internal_id) AS "Items Linked"
               FROM projects p
               LEFT JOIN items i ON i.project_id = p.project_id
               GROUP BY p.project_id ORDER BY p.project_name"""
        )
        blocked = df_projs[df_projs["Items Linked"] > 0]
        if not blocked.empty:
            st.warning("Projects with items cannot be deleted: "
                       + ", ".join(f"**{r}**" for r in blocked["Project Name"].tolist()))
        _bulk_delete_panel(df_projs, "project_id", "Project Name", "projects", "bd_projs", "Project")
