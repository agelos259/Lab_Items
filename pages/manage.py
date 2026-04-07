import streamlit as st
import psycopg2
import psycopg2.errors

from config import PROJECT_STATUSES
from db import get_connection
from queries import fetch_df


def page_manage() -> None:
    st.title("Manage Lookups")
    tab_cat, tab_loc, tab_usr, tab_proj = st.tabs(
        ["Categories", "Locations", "Users", "Projects"]
    )

    # ── Categories ────────────────────────────────────────────────────────
    with tab_cat:
        st.subheader("All Categories")
        st.dataframe(
            fetch_df("SELECT category_id AS ID, category_name AS Name FROM categories ORDER BY category_name"),
            use_container_width=True, hide_index=True,
        )
        st.divider()

        st.markdown("##### Add New Category")
        with st.form("add_category"):
            new_cat = st.text_input("Category Name *")
            if st.form_submit_button("Add Category"):
                if new_cat.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO categories (category_name) VALUES (?)", (new_cat.strip(),))
                        conn.commit()
                        st.success(f"Category '{new_cat.strip()}' added.")
                        st.rerun()
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        st.error("A category with that name already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("Name cannot be blank.")
        st.divider()

        st.markdown("##### Edit or Delete a Category")
        cats_df = fetch_df("SELECT category_id, category_name FROM categories ORDER BY category_name")
        if not cats_df.empty:
            sel_cat_name = st.selectbox("Select category", cats_df["category_name"].tolist(), key="sel_cat_edit")
            sel_cat_id   = int(cats_df.loc[cats_df["category_name"] == sel_cat_name, "category_id"].iloc[0])
            with st.form("edit_category"):
                edited_cat = st.text_input("New Name *", value=sel_cat_name)
                if st.form_submit_button("Save Changes"):
                    if edited_cat.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE categories SET category_name=? WHERE category_id=?",
                                         (edited_cat.strip(), sel_cat_id))
                            conn.execute("UPDATE items SET category=? WHERE category_id=?",
                                         (edited_cat.strip(), sel_cat_id))
                            conn.commit()
                            st.success("Category updated.")
                            st.rerun()
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()
                            st.error("That name already exists.")
                        finally:
                            conn.close()
                    else:
                        st.error("Name cannot be blank.")
            confirm_cat = st.checkbox(f"Confirm deletion of **{sel_cat_name}**", key="del_cat_chk")
            if st.button("Delete Category", type="primary", disabled=not confirm_cat, key="del_cat_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM categories WHERE category_id=?", (sel_cat_id,))
                    conn.commit()
                    st.success(f"Category '{sel_cat_name}' deleted.")
                    st.rerun()
                except psycopg2.Error:
                    conn.rollback()
                    st.error("Cannot delete: items are still linked to this category.")
                finally:
                    conn.close()

    # ── Locations ─────────────────────────────────────────────────────────
    with tab_loc:
        st.subheader("All Locations")
        st.dataframe(
            fetch_df("SELECT location_id AS ID, location_name AS Name FROM locations ORDER BY location_name"),
            use_container_width=True, hide_index=True,
        )
        st.divider()

        st.markdown("##### Add New Location")
        with st.form("add_location"):
            new_loc = st.text_input("Location Name *")
            if st.form_submit_button("Add Location"):
                if new_loc.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO locations (location_name) VALUES (?)", (new_loc.strip(),))
                        conn.commit()
                        st.success(f"Location '{new_loc.strip()}' added.")
                        st.rerun()
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        st.error("A location with that name already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("Name cannot be blank.")
        st.divider()

        st.markdown("##### Edit or Delete a Location")
        locs_df = fetch_df("SELECT location_id, location_name FROM locations ORDER BY location_name")
        if not locs_df.empty:
            sel_loc_name = st.selectbox("Select location", locs_df["location_name"].tolist(), key="sel_loc_edit")
            sel_loc_id   = int(locs_df.loc[locs_df["location_name"] == sel_loc_name, "location_id"].iloc[0])
            with st.form("edit_location"):
                edited_name = st.text_input("New Name *", value=sel_loc_name)
                if st.form_submit_button("Save Changes"):
                    if edited_name.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE locations SET location_name=? WHERE location_id=?",
                                         (edited_name.strip(), sel_loc_id))
                            conn.commit()
                            st.success("Location updated.")
                            st.rerun()
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()
                            st.error("That name already exists.")
                        finally:
                            conn.close()
                    else:
                        st.error("Name cannot be blank.")
            confirm_loc = st.checkbox(f"Confirm deletion of **{sel_loc_name}**", key="del_loc_chk")
            if st.button("Delete Location", type="primary", disabled=not confirm_loc, key="del_loc_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM locations WHERE location_id=?", (sel_loc_id,))
                    conn.commit()
                    st.success(f"Location '{sel_loc_name}' deleted.")
                    st.rerun()
                except psycopg2.Error:
                    conn.rollback()
                    st.error("Cannot delete: items are still assigned to this location.")
                finally:
                    conn.close()

    # ── Users ─────────────────────────────────────────────────────────────
    with tab_usr:
        st.subheader("All Users")
        st.dataframe(
            fetch_df("SELECT user_id AS ID, name AS Name, role AS Role, email AS Email FROM users ORDER BY name"),
            use_container_width=True, hide_index=True,
        )
        st.divider()

        st.markdown("##### Add New User")
        with st.form("add_user"):
            c1, c2 = st.columns(2)
            u_name  = c1.text_input("Full Name *")
            u_role  = c2.text_input("Role *")
            u_email = st.text_input("Email *")
            if st.form_submit_button("Add User"):
                if u_name.strip() and u_role.strip() and u_email.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO users (name, role, email) VALUES (?,?,?)",
                                     (u_name.strip(), u_role.strip(), u_email.strip()))
                        conn.commit()
                        st.success(f"User '{u_name.strip()}' added.")
                        st.rerun()
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        st.error("A user with that email already exists.")
                    finally:
                        conn.close()
                else:
                    st.error("All fields are required.")
        st.divider()

        st.markdown("##### Edit or Delete a User")
        users_df = fetch_df("SELECT user_id, name, role, email FROM users ORDER BY name")
        if not users_df.empty:
            sel_user_name = st.selectbox("Select user", users_df["name"].tolist(), key="sel_usr_edit")
            sel_user_row  = users_df[users_df["name"] == sel_user_name].iloc[0]
            sel_user_id   = int(sel_user_row["user_id"])
            with st.form("edit_user"):
                c1, c2 = st.columns(2)
                e_name  = c1.text_input("Full Name *", value=sel_user_row["name"])
                e_role  = c2.text_input("Role *",      value=sel_user_row["role"])
                e_email = st.text_input("Email *",     value=sel_user_row["email"])
                if st.form_submit_button("Save Changes"):
                    if e_name.strip() and e_role.strip() and e_email.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE users SET name=?, role=?, email=? WHERE user_id=?",
                                         (e_name.strip(), e_role.strip(), e_email.strip(), sel_user_id))
                            conn.commit()
                            st.success("User updated.")
                            st.rerun()
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()
                            st.error("That email is already used by another user.")
                        finally:
                            conn.close()
                    else:
                        st.error("All fields are required.")
            confirm_usr = st.checkbox(f"Confirm deletion of **{sel_user_name}**", key="del_usr_chk")
            if st.button("Delete User", type="primary", disabled=not confirm_usr, key="del_usr_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM users WHERE user_id=?", (sel_user_id,))
                    conn.commit()
                    st.success(f"User '{sel_user_name}' deleted.")
                    st.rerun()
                except psycopg2.Error:
                    conn.rollback()
                    st.error("Cannot delete: items are still assigned to this user.")
                finally:
                    conn.close()

    # ── Projects ──────────────────────────────────────────────────────────
    with tab_proj:
        st.subheader("All Projects")
        st.dataframe(
            fetch_df("SELECT project_id AS ID, project_name AS Project, grant_code AS \"Grant Code\", status AS Status FROM projects ORDER BY project_name"),
            use_container_width=True, hide_index=True,
        )
        st.divider()

        st.markdown("##### Add New Project")
        with st.form("add_project"):
            c1, c2, c3 = st.columns(3)
            p_name   = c1.text_input("Project Name *")
            p_grant  = c2.text_input("Grant Code")
            p_status = c3.selectbox("Status", PROJECT_STATUSES)
            if st.form_submit_button("Add Project"):
                if p_name.strip():
                    conn = get_connection()
                    try:
                        conn.execute("INSERT INTO projects (project_name, grant_code, status) VALUES (?,?,?)",
                                     (p_name.strip(), p_grant.strip() or None, p_status))
                        conn.commit()
                        st.success(f"Project '{p_name.strip()}' added.")
                        st.rerun()
                    except psycopg2.Error as e:
                        conn.rollback()
                        st.error(f"Database error: {e}")
                    finally:
                        conn.close()
                else:
                    st.error("Project Name is required.")
        st.divider()

        st.markdown("##### Edit or Delete a Project")
        projs_df = fetch_df("SELECT project_id, project_name, grant_code, status FROM projects ORDER BY project_name")
        if not projs_df.empty:
            sel_proj_name = st.selectbox("Select project", projs_df["project_name"].tolist(), key="sel_proj_edit")
            sel_proj_row  = projs_df[projs_df["project_name"] == sel_proj_name].iloc[0]
            sel_proj_id   = int(sel_proj_row["project_id"])
            with st.form("edit_project"):
                c1, c2, c3 = st.columns(3)
                e_pname  = c1.text_input("Project Name *", value=sel_proj_row["project_name"])
                e_grant  = c2.text_input("Grant Code",     value=sel_proj_row["grant_code"] or "")
                cur_idx  = PROJECT_STATUSES.index(sel_proj_row["status"]) \
                           if sel_proj_row["status"] in PROJECT_STATUSES else 0
                e_status = c3.selectbox("Status", PROJECT_STATUSES, index=cur_idx)
                if st.form_submit_button("Save Changes"):
                    if e_pname.strip():
                        conn = get_connection()
                        try:
                            conn.execute("UPDATE projects SET project_name=?, grant_code=?, status=? WHERE project_id=?",
                                         (e_pname.strip(), e_grant.strip() or None, e_status, sel_proj_id))
                            conn.commit()
                            st.success("Project updated.")
                            st.rerun()
                        except psycopg2.Error as e:
                            conn.rollback()
                            st.error(f"Database error: {e}")
                        finally:
                            conn.close()
                    else:
                        st.error("Project Name is required.")
            confirm_proj = st.checkbox(f"Confirm deletion of **{sel_proj_name}**", key="del_proj_chk")
            if st.button("Delete Project", type="primary", disabled=not confirm_proj, key="del_proj_btn"):
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM projects WHERE project_id=?", (sel_proj_id,))
                    conn.commit()
                    st.success(f"Project '{sel_proj_name}' deleted.")
                    st.rerun()
                except psycopg2.Error:
                    conn.rollback()
                    st.error("Cannot delete: items are still linked to this project.")
                finally:
                    conn.close()
