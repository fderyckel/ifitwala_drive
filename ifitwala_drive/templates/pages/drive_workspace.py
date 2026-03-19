from __future__ import annotations

import os

import frappe

from ifitwala_drive.website.vite_utils import get_vite_assets

APP = "ifitwala_drive"
VITE_DIR = os.path.join(frappe.get_app_path(APP), "public", "vite")
MANIFEST_PATHS = [
	os.path.join(VITE_DIR, "manifest.json"),
	os.path.join(VITE_DIR, ".vite", "manifest.json"),
]
PUBLIC_BASE = f"/assets/{APP}/vite/"
ENTRY_KEYS = [
	"src/apps/workspace/main.ts",
	"src/apps/workspace/main.js",
	"index.html",
]


def get_context(context):
	context.no_cache = 1
	context.title = "Drive Workspace"
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.vite_js, context.vite_css, context.vite_preload = get_vite_assets(
		app_name=APP,
		manifest_paths=MANIFEST_PATHS,
		public_base=PUBLIC_BASE,
		entry_keys=ENTRY_KEYS,
	)
	context.has_vite_workspace = context.vite_js != f"{PUBLIC_BASE}main.js"
