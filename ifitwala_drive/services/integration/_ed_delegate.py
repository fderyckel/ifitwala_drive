from __future__ import annotations

import importlib
import sys
from pathlib import Path

import frappe
from frappe import _


def load_ed_drive_module(module_name: str):
	try:
		return importlib.import_module(module_name)
	except ImportError as exc:
		ed_repo_root = Path(__file__).resolve().parents[3].parent / "ifitwala_ed"
		ed_package_root = ed_repo_root / "ifitwala_ed"
		if ed_repo_root.exists():
			ed_repo_root_text = str(ed_repo_root)
			if ed_repo_root_text not in sys.path:
				sys.path.insert(0, ed_repo_root_text)

			root_module = sys.modules.get("ifitwala_ed")
			if root_module is not None and not getattr(root_module, "__path__", None):
				root_module.__path__ = [str(ed_package_root)]

			try:
				return importlib.import_module(module_name)
			except ImportError:
				pass

		frappe.throw(
			_(
				"Ifitwala_Ed Drive bridge module '{0}' is unavailable. Ensure the Ed app is installed with the matching bridge implementation: {1}"
			).format(module_name, exc)
		)
