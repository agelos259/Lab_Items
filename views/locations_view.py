import streamlit as st

from queries import fetch_df


def page_locations() -> None:
    st.title("Item Locations")

    df = fetch_df(
        """
        SELECT
            l.location_name                              AS "Location",
            i.internal_id                                AS "ID",
            i.item_name                                  AS "Item Name",
            COALESCE(cat.category_name, i.category, '—') AS "Category",
            i.condition                                  AS "Condition",
            COALESCE(u.name, '—')                        AS "Assigned To",
            COALESCE(p.project_name, '—')                AS "Project"
        FROM items i
        JOIN locations l      ON i.location_id  = l.location_id
        LEFT JOIN categories cat ON i.category_id = cat.category_id
        LEFT JOIN users u     ON i.user_id      = u.user_id
        LEFT JOIN projects p  ON i.project_id   = p.project_id
        ORDER BY l.location_name,
                 CAST(SUBSTR(i.internal_id, 5) AS INTEGER)
        """
    )

    if df.empty:
        st.info("No items found.")
        return

    locations = df["Location"].unique().tolist()
    total     = len(df)

    # Summary bar
    cols = st.columns(len(locations) if len(locations) <= 6 else 6)
    for i, loc in enumerate(locations):
        count = len(df[df["Location"] == loc])
        cols[i % 6].metric(loc, count)
    st.divider()

    # Search / filter
    c1, c2 = st.columns([3, 2])
    search   = c1.text_input("Search by name or ID", "")
    loc_filter = c2.selectbox("Filter by location", ["All"] + locations)

    filtered = df.copy()
    if search:
        mask = (
            filtered["Item Name"].str.contains(search, case=False, na=False) |
            filtered["ID"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if loc_filter != "All":
        filtered = filtered[filtered["Location"] == loc_filter]

    st.caption(f"Showing {len(filtered)} of {total} item(s)")
    st.divider()

    # One expander per location
    for loc in filtered["Location"].unique().tolist():
        loc_df = filtered[filtered["Location"] == loc].drop(columns=["Location"])
        count  = len(loc_df)
        with st.expander(f"**{loc}** — {count} item(s)", expanded=True):
            st.dataframe(loc_df, use_container_width=True, hide_index=True)
