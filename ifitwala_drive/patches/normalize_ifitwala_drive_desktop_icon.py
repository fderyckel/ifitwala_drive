import frappe


ICON_NAME = "Ifitwala Drive"
EXPECTED_LINK_TYPE = "Workspace Sidebar"


def execute():
	if not frappe.db.exists("Desktop Icon", ICON_NAME):
		return

	doc = frappe.get_doc("Desktop Icon", ICON_NAME)
	if getattr(doc, "app", None) != "ifitwala_drive":
		return

	changed = False

	if getattr(doc, "link_type", None) != EXPECTED_LINK_TYPE:
		doc.link_type = EXPECTED_LINK_TYPE
		changed = True

	if getattr(doc, "link_to", None) != ICON_NAME:
		doc.link_to = ICON_NAME
		changed = True

	if getattr(doc, "icon_type", None) != "Link":
		doc.icon_type = "Link"
		changed = True

	if not changed:
		return

	doc.save(ignore_permissions=True)

	cache_factory = getattr(frappe, "cache", None)
	if callable(cache_factory):
		try:
			cache = cache_factory()
		except Exception:
			cache = None
		if cache and hasattr(cache, "delete_key"):
			cache.delete_key("desktop_icons")
			cache.delete_key("bootinfo")
