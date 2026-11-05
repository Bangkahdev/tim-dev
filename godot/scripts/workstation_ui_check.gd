extends SceneTree

## Headless validation for the workstation / Bangkah OS UI flow.
## It loads the real main scene, walks the Owner into OWNER-PC-001 and drives
## the desktop state machine with captured backend response shapes. HTTP itself
## is exercised by backend/tools/check_desktop_api.py; this script verifies the
## Godot-side rendering, session handling and seat/exit transitions.
##
## Usage (from godot/):
##   godot --headless --path . --script "res://scripts/workstation_ui_check.gd"

var failures := 0

func _initialize() -> void:
	_run()

func _check(name: String, ok: bool) -> void:
	print(("PASS " if ok else "FAIL ") + name)
	if not ok:
		failures += 1

func _text_of(node: Node) -> String:
	var text := ""
	if node is Label:
		text += (node as Label).text + "\n"
	elif node is Button:
		text += (node as Button).text + "\n"
	for child in node.get_children():
		text += _text_of(child)
	return text

func _run() -> void:
	var scene = load("res://scenes/main.tscn").instantiate()
	root.add_child(scene)
	await create_timer(0.4).timeout
	var desktop = scene._desktop_ui
	var target: Dictionary = {}
	for item in scene._interactables:
		if str(item.get("id", "")) == "workstation":
			target = item
	if target.is_empty():
		print("FAIL workstation interactable missing")
		quit(1)
		return

	scene._enter_workstation(target)
	await create_timer(0.3).timeout
	_check("workstation opens on login view", desktop._login_view.visible and not desktop._os_view.visible)
	_check("player seated at workstation", scene.player.is_seated)

	desktop._on_login_response(HTTPRequest.RESULT_SUCCESS, 400, {"error": "Kata sandi workstation salah."})
	_check("rejected login stays on login view", desktop._login_view.visible and not desktop.has_session())
	_check("rejected login shows backend message", desktop._login_error.visible and desktop._login_error.text.contains("salah"))

	var login := {
		"session_id": "WSS-CHECK",
		"token": "sesi-uji",
		"expires_at": "2026-01-01T00:00:00+00:00",
		"workstation": {"id": "OWNER-PC-001", "label": "Owner Workstation", "room_id": "owner"},
		"account": {"id": "owner", "name": "Owner", "role": "owner"},
		"apps": ["files", "terminal", "infrastructure", "company"],
	}
	desktop._on_login_response(HTTPRequest.RESULT_SUCCESS, 201, login)
	await create_timer(0.2).timeout
	_check("accepted login shows desktop", desktop._os_view.visible and not desktop._login_view.visible)
	_check("accepted login stores session", desktop.has_session())
	_check("session label from backend", desktop._session_label.text.contains("OWNER-PC-001") and desktop._session_label.text.contains("Owner"))
	_check("four apps in dock", desktop._nav_buttons.size() == 4)

	var files := {
		"workstation_id": "OWNER-PC-001",
		"path": ".",
		"entries": [
			{"name": "docs", "path": "docs", "type": "directory", "size": 0, "modified": "-"},
			{"name": "notes.txt", "path": "notes.txt", "type": "file", "size": 9, "modified": "-"},
			{"name": "README.md", "path": "README.md", "type": "file", "size": 33, "modified": "-"},
		],
	}
	desktop._on_directory_loaded(".", HTTPRequest.RESULT_SUCCESS, 200, files)
	await create_timer(0.1).timeout
	var listing := _text_of(desktop._file_list)
	_check("directory listing renders files", listing.contains("README.md") and listing.contains("notes.txt") and listing.contains("docs"))

	desktop._on_file_loaded("README.md", HTTPRequest.RESULT_SUCCESS, 200, {
		"file": {"path": "README.md", "content": "# OWNER-PC-001 sandbox", "size": 19},
	})
	_check("file content renders", desktop._file_editor.text.contains("OWNER-PC-001") and not desktop._file_save_button.disabled)

	var system_box := VBoxContainer.new()
	desktop._content.add_child(system_box)
	desktop._on_system_loaded(system_box, HTTPRequest.RESULT_SUCCESS, 200, {
		"workstation": {"id": "OWNER-PC-001", "label": "Owner Workstation"},
		"account": {"id": "owner", "name": "Owner", "role": "owner"},
		"session": {"id": "WSS-CHECK", "expires_at": "2026-01-01T00:00:00+00:00"},
		"terminal": {"mode": "sandboxed-argv", "builtins": ["ls"], "external_binaries": [],
			"workdir": "OWNER-PC-001", "limits": {"command_chars": 500, "file_bytes": 65536, "output_chars": 16000}},
		"integrations": {
			"smtp": {"configured": false, "detail": "-"},
			"deploy_webhook": {"configured": false, "detail": "-"},
			"api_token": {"enabled": false, "detail": "-"},
			"domain": {"name": "bangkah.my.id", "dns_managed": false, "email_provisioned": false, "detail": "-"},
		},
	})
	var system_text := _text_of(system_box)
	_check("system info shows terminal mode", system_text.contains("sandboxed-argv") and system_text.contains("Builtin"))
	_check("system info is honest about domain", system_text.contains("DNS tidak dikelola"))
	_check("system info marks integrations absent", system_text.contains("ABSENT"))

	var audit_box := VBoxContainer.new()
	desktop._content.add_child(audit_box)
	desktop._on_audit_loaded(audit_box, HTTPRequest.RESULT_SUCCESS, 200, {
		"events": [{"id": 1, "event_type": "desktop_login", "detail": "login Owner", "created_at": "2026-01-01T00:00:00+00:00"}],
	})
	_check("audit history renders", _text_of(audit_box).contains("AKTIVITAS TERAKHIR"))

	desktop._select_app("terminal")
	await create_timer(0.1).timeout
	desktop._submit_terminal("whoami")
	await create_timer(0.1).timeout
	_check("terminal echoes submitted command", desktop._terminal_log.text.contains("$ whoami"))
	_check("terminal input cleared after submit", desktop._terminal_input.text.is_empty())

	var handled: bool = desktop._handle_desktop_response(HTTPRequest.RESULT_SUCCESS, 401, {"error": "Sesi workstation tidak valid."})
	_check("401 response ends session", not handled and not desktop.has_session() and desktop._login_view.visible)

	desktop._desktop_token = "sesi-uji"
	desktop._show_os()
	desktop._logout()
	_check("logout clears session immediately", not desktop.has_session() and desktop._login_view.visible)

	scene._exit_workstation()
	await create_timer(0.3).timeout
	_check("exit returns to office", not scene._desktop_active and not scene.player.is_seated)
	_check("exit restores standing player", not scene.player.is_seated)

	print("RESULT failures=", failures)
	quit(1 if failures > 0 else 0)
