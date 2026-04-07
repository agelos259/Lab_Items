"""
Shared constants for the Lab Inventory app.
"""

CATEGORIES = [
    "Capital Equipment",
    "Electronics/Sensors",
    "IT/Computing",
    "Tools/Hardware",
    "Consumables",
]

CONDITIONS       = ["Available", "In Use", "Broken", "Needs Repair"]
PROJECT_STATUSES = ["Active", "Completed"]

# Maps Excel Greek column headers → internal field names
EXCEL_COL_MAP = {
    "A/A":                              "row_num",
    "ΕΙΔΟΣ":                            "excel_category",
    "ΜΟΝΤΕΛΟ":                          "item_name",
    "ΤΕΜΑΧΙΑ":                          "quantity",
    "S/N":                              "manufacturer_sn",
    "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΧΩΡΙΣ ΦΠΑ":        "unit_price_ex_vat",
    "ΤΙΜΗ ΤΕΜΑΧΙΟΥ ΜΕ ΦΠΑ":           "unit_price_inc_vat",
    "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΧΩΡΙΣ ΦΠΑ":       "total_price_ex_vat",
    "ΤΙΜΗ ΠΟΣΟΤΗΤΑΣ ΜΕ ΦΠΑ":          "total_price_inc_vat",
    "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ ΟΧΙ)":            "received",
    "ΠΑΡΑΛΑΒΗ (ΝΑΙ/ΟΧΙ)":             "received",
    "ΤΟΠΟΘΕΣΙΑ":                        "location_name",
}
