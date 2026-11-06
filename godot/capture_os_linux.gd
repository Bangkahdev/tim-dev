extends SceneTree

const OUT := "/tmp/opencode/shots/"
var _main

func _initialize() -> void:
	call_deferred("_run")

func _capture(file_name: String) -> void:
	await process_frame
	await process_frame
	var image := root.get_texture().get_image()
	image.save_png(OUT + file_name)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var scene: PackedScene = load("res://scenes/main.tscn")
	_main = scene.instantiate()
	root.add_child(_main)
	for i in range(30):
		await process_frame
	var desktop = _main._desktop_ui

	# Masuk ke workstation Owner untuk membuka layar desktop asli.
	var target: Dictionary = {}
	for item in _main._interactables:
		if str(item.get("id", "")) == "workstation":
			target = item
	_main._enter_workstation(target)
	for i in range(10):
		await process_frame
	await _capture("os-login.png")
	print("CAPTURE: os-login")

	# Login sukses (bentuk respons backend asli).
	desktop._on_login_response(HTTPRequest.RESULT_SUCCESS, 201, {
		"session_id": "WSS-CHECK",
		"token": "sesi-uji",
		"expires_at": "2026-01-01T00:00:00+00:00",
		"workstation": {"id": "OWNER-PC-001", "label": "Owner Workstation", "room_id": "owner"},
		"account": {"id": "owner", "name": "Owner", "role": "owner"},
		"apps": ["files", "terminal", "infrastructure", "company"],
	})
	for i in range(10):
		await process_frame

	# App: files — daftar direktori + isi file.
	desktop._select_app("files")
	for i in range(8):
		await process_frame
	desktop._on_directory_loaded(".", HTTPRequest.RESULT_SUCCESS, 200, {
		"workstation_id": "OWNER-PC-001",
		"path": ".",
		"entries": [
			{"name": "docs", "path": "docs", "type": "directory", "size": 0, "modified": "2026-11-04 09:12"},
			{"name": "notes.txt", "path": "notes.txt", "type": "file", "size": 419, "modified": "2026-11-04 10:02"},
			{"name": "README.md", "path": "README.md", "type": "file", "size": 2033, "modified": "2026-11-05 07:44"},
			{"name": "laporan-qa.pdf", "path": "laporan-qa.pdf", "type": "file", "size": 183204, "modified": "2026-11-05 08:17"},
		],
	})
	for i in range(8):
		await process_frame
	await _capture("os-files.png")
	print("CAPTURE: os-files")

	# App: terminal — echo + hasil perintah.
	desktop._select_app("terminal")
	for i in range(8):
		await process_frame
	desktop._terminal_log.text = "$ whoami\nowner\n$ ls docs\n> laporan-qa.pdf  notes.txt\n$ exit code: 0\n"
	await _capture("os-terminal.png")
	print("CAPTURE: os-terminal")

	# App: infrastructure — status sistem + integrasi absen.
	desktop._select_app("infrastructure")
	for i in range(8):
		await process_frame
	desktop._on_system_loaded(desktop._content, HTTPRequest.RESULT_SUCCESS, 200, {
		"workstation": {"id": "OWNER-PC-001", "label": "Owner Workstation"},
		"account": {"id": "owner", "name": "Owner", "role": "owner"},
		"session": {"id": "WSS-CHECK", "expires_at": "2026-01-01T00:00:00+00:00"},
		"terminal": {"mode": "sandboxed-argv", "builtins": ["ls", "cat", "whoami"], "external_binaries": [],
			"workdir": "OWNER-PC-001", "limits": {"command_chars": 500, "file_bytes": 65536, "output_chars": 16000}},
		"integrations": {
			"smtp": {"configured": false, "detail": "SMTP belum dikonfigurasi"},
			"deploy_webhook": {"configured": false, "detail": "Webhook deploy belum dikonfigurasi"},
			"api_token": {"enabled": false, "detail": "Token API tidak aktif"},
			"domain": {"name": "bangkah.web.id", "dns_managed": false, "email_provisioned": false, "detail": "DNS tidak dikelola (OVH)"},
		},
	})
	desktop._on_audit_loaded(desktop._content, HTTPRequest.RESULT_SUCCESS, 200, {
		"events": [{"id": 1, "event_type": "desktop_login", "detail": "login Owner di OWNER-PC-001", "created_at": "2026-11-05T08:17:00"}],
	})
	for i in range(8):
		await process_frame
	await _capture("os-infrastructure.png")
	print("CAPTURE: os-infrastructure")

	# App: company — Command Center dari dalam OS.
	desktop._select_app("company")
	for i in range(8):
		await process_frame
	await _capture("os-company.png")
	print("CAPTURE: os-company")
	print("CAPTURE_OK")
	quit()
