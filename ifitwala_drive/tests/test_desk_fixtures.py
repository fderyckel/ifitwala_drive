import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))


def test_desktop_icon_is_public_and_points_to_workspace_sidebar():
	icon = _load_json(ROOT / "desktop_icon" / "ifitwala_drive.json")

	assert icon["doctype"] == "Desktop Icon"
	assert icon["hidden"] == 0
	assert icon["label"] == "Ifitwala Drive"
	assert icon["link_type"] == "Workspace Sidebar"
	assert icon["link_to"] == "Ifitwala Drive"
	assert "roles" not in icon


def test_workspace_sidebar_exposes_drive_navigation():
	sidebar = _load_json(ROOT / "workspace_sidebar" / "ifitwala_drive.json")

	assert sidebar["doctype"] == "Workspace Sidebar"
	assert sidebar["title"] == "Ifitwala Drive"
	assert [item["label"] for item in sidebar["items"]] == [
		"Home",
		"Folders",
		"Files",
		"Upload Sessions",
		"Processing Jobs",
	]
	assert sidebar["items"][0]["link_type"] == "Workspace"
	assert sidebar["items"][0]["link_to"] == "Ifitwala Drive"


def test_workspace_is_public_and_links_to_drive_workspace():
	workspace = _load_json(ROOT / "ifitwala_drive" / "workspace" / "ifitwala_drive" / "ifitwala_drive.json")

	assert workspace["doctype"] == "Workspace"
	assert workspace["public"] == 1
	assert workspace["for_user"] == ""
	assert "roles" not in workspace
	assert any(
		shortcut.get("label") == "Drive Workspace" and shortcut.get("url") == "/drive_workspace"
		for shortcut in workspace["shortcuts"]
	)
