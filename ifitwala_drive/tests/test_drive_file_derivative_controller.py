from __future__ import annotations

import importlib
import sys
import types


def _load_controller(monkeypatch):
	module_name = "ifitwala_drive.ifitwala_drive.doctype.drive_file_derivative.drive_file_derivative"
	monkeypatch.delitem(sys.modules, module_name, raising=False)

	frappe = types.ModuleType("frappe")
	frappe._ = lambda message: message

	def fake_throw(message, exc=None):
		raise RuntimeError(message)

	frappe.throw = fake_throw

	class FakeDB:
		def exists(self, doctype, name=None):
			return doctype in {"Drive File", "Drive File Version"} and bool(name)

	frappe.db = FakeDB()

	model_module = types.ModuleType("frappe.model")
	document_module = types.ModuleType("frappe.model.document")

	class FakeDocument:
		def get(self, key, default=None):
			return getattr(self, key, default)

	document_module.Document = FakeDocument

	monkeypatch.setitem(sys.modules, "frappe", frappe)
	monkeypatch.setitem(sys.modules, "frappe.model", model_module)
	monkeypatch.setitem(sys.modules, "frappe.model.document", document_module)

	return importlib.import_module(module_name)


def test_pdf_card_derivative_role_is_valid(monkeypatch):
	module = _load_controller(monkeypatch)
	doc = module.DriveFileDerivative()
	doc.drive_file = "DF-0001"
	doc.drive_file_version = "DFV-0001"
	doc.derivative_role = "pdf_card"
	doc.status = "pending"

	doc.validate()


def test_unknown_derivative_role_is_rejected(monkeypatch):
	module = _load_controller(monkeypatch)
	doc = module.DriveFileDerivative()
	doc.drive_file = "DF-0001"
	doc.drive_file_version = "DFV-0001"
	doc.derivative_role = "unknown_card"
	doc.status = "pending"

	try:
		doc.validate()
	except RuntimeError as exc:
		assert "Invalid derivative role" in str(exc)
	else:
		raise AssertionError("Expected invalid derivative role to be rejected.")
