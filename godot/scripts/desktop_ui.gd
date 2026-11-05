extends CanvasLayer

class_name BangkahDesktop

## Bangkah OS: the desktop shown on a physical office workstation. It talks to the
## real backend over HTTP; every action requires a desktop session from
## /api/workstations/<id>/login. No office state is invented in this layer.

signal close_requested
signal company_requested
signal toast_requested(message: String)

const TEXT := Color("#e8ece8")
const MUTED := Color("#9aa8a1")
const ACCENT := Color("#8fb59a")
const WARN := Color("#e4c99b")
const DANGER := Color("#e0a09a")
const PANEL_BG := Color("#0a1012")
const PANEL_BORDER := Color("#2d423a")

var _server_url: String = "http://127.0.0.1:8765"
var _api_token: String = ""
var _desktop_token: String = ""
var _session: Dictionary = {}
var _workstation_id: String = ""
var _workstation_label: String = ""
var _active_app: String = "files"
var _current_path: String = "."
var _current_file: String = ""
var _busy_files: bool = false
var _busy_terminal: bool = false
var _clock_elapsed: float = 0.0

var _root: Control
var _login_view: Control
var _os_view: Control
var _login_workstation: Label
var _login_account: LineEdit
var _login_password: LineEdit
var _login_error: Label
var _login_button: Button
var _session_label: Label
var _clock_label: Label
var _app_title: Label
var _app_subtitle: Label
var _content: VBoxContainer
var _status_label: Label
var _nav_buttons: Dictionary = {}
var _terminal_log: TextEdit
var _terminal_input: LineEdit
var _file_path_label: Label
var _file_list: VBoxContainer
var _file_editor: TextEdit
var _file_editor_path: Label
var _file_save_button: Button

func _ready() -> void:
	layer = 30
	_build()
	visible = false
	set_process(false)

func set_server_url(url: String) -> void:
	_server_url = url.trim_suffix("/")

func set_api_token(token: String) -> void:
	_api_token = token.strip_edges()

func is_open() -> bool:
	return visible

func has_session() -> bool:
	return not _desktop_token.is_empty()

func session_workstation() -> String:
	return _workstation_id

# ---------------------------------------------------------------------------
# Public lifecycle
# ---------------------------------------------------------------------------
func open_for(workstation_id: String, label: String) -> void:
	_workstation_id = workstation_id
	_workstation_label = label
	visible = true
	set_process(true)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if _desktop_token.is_empty():
		_show_login()
	else:
		_show_os()
		_refresh_session()

func hide_ui() -> void:
	visible = false

func show_ui() -> void:
	visible = true
	set_process(true)
	if _desktop_token.is_empty():
		_show_login()
	else:
		_show_os()

func _process(delta: float) -> void:
	if not visible:
		return
	_clock_elapsed += delta
	if _clock_elapsed >= 1.0 and is_instance_valid(_clock_label):
		_clock_elapsed = 0.0
		_clock_label.text = Time.get_time_string_from_system().left(5)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
func _build() -> void:
	_root = Control.new()
	_root.name = "DesktopRoot"
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_root)
	_build_os_view()
	_build_login_view()

func _build_login_view() -> void:
	_login_view = Control.new()
	_login_view.name = "DesktopLogin"
	_login_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.add_child(_login_view)

	var backdrop := ColorRect.new()
	backdrop.color = Color(0.012, 0.018, 0.021, 0.98)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_login_view.add_child(backdrop)

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_login_view.add_child(center)

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(560, 470)
	panel.add_theme_stylebox_override("panel", _panel_style(PANEL_BG, PANEL_BORDER, 18))
	center.add_child(panel)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)

	box.add_child(_label("BANGKAH  OS", 30, TEXT, true, false))
	box.add_child(_label("WORKSTATION  ACCESS", 11, ACCENT, false, false))
	box.add_child(_label("Masuk dengan akun yang ditugaskan ke workstation ini. "
		+ "Setiap login, perintah terminal, dan perubahan file tercatat di audit perusahaan.",
		12, MUTED))
	box.add_child(_spacer(6))
	_login_workstation = _label("OWNER-PC-001", 15, TEXT, true, false)
	box.add_child(_login_workstation)
	box.add_child(_label("AKUN", 10, MUTED, false, false))
	_login_account = LineEdit.new()
	_login_account.text = "owner"
	_login_account.placeholder_text = "account id"
	_style_input(_login_account)
	box.add_child(_login_account)
	box.add_child(_label("KATA SANDI", 10, MUTED, false, false))
	_login_password = LineEdit.new()
	_login_password.secret = true
	_login_password.placeholder_text = "kata sandi workstation"
	_style_input(_login_password)
	_login_password.text_submitted.connect(func(_text): _submit_login())
	box.add_child(_login_password)
	_login_error = _label("", 11, DANGER)
	_login_error.visible = false
	box.add_child(_login_error)
	_login_button = _button("MASUK  /  LOGIN", true)
	_login_button.pressed.connect(_submit_login)
	box.add_child(_login_button)
	box.add_child(_label("Kata sandi Owner dibuat oleh backend pada data/owner_credentials.local "
		+ "atau mengikuti BANGKAH_OWNER_PASSWORD. Akun karyawan belum diaktifkan pada slice ini.",
		10, MUTED))
	box.add_child(_label("ESC  ·  berdiri dan kembali ke kantor", 10, WARN, false, false))

func _build_os_view() -> void:
	_os_view = Control.new()
	_os_view.name = "DesktopOS"
	_os_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_os_view.visible = false
	_root.add_child(_os_view)

	var backdrop := ColorRect.new()
	backdrop.color = Color(0.016, 0.024, 0.027, 0.99)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_os_view.add_child(backdrop)

	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 26)
	margin.add_theme_constant_override("margin_right", 26)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 18)
	_os_view.add_child(margin)

	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 12)
	margin.add_child(outer)

	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 14)
	outer.add_child(top)
	top.add_child(_label("BANGKAH  OS", 20, TEXT, true, false))
	var divider := ColorRect.new()
	divider.color = Color(0.30, 0.42, 0.36, 0.55)
	divider.custom_minimum_size = Vector2(1, 26)
	divider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	top.add_child(divider)
	_session_label = _label("MEMUAT SESI", 11, MUTED, false, false)
	_session_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	top.add_child(_session_label)
	var stretch := Control.new()
	stretch.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(stretch)
	_clock_label = _label("--:--", 11, MUTED, false, false)
	_clock_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	top.add_child(_clock_label)
	var logout_button := _button("LOGOUT")
	logout_button.pressed.connect(_logout)
	top.add_child(logout_button)
	var close_button := _button("TUTUP  ESC")
	close_button.pressed.connect(func(): close_requested.emit())
	top.add_child(close_button)

	var line := ColorRect.new()
	line.color = Color(0.16, 0.24, 0.21, 0.8)
	line.custom_minimum_size = Vector2(0, 1)
	outer.add_child(line)

	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation", 14)
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer.add_child(body)

	var dock := VBoxContainer.new()
	dock.custom_minimum_size = Vector2(196, 0)
	dock.add_theme_constant_override("separation", 6)
	body.add_child(dock)
	dock.add_child(_label("APLIKASI", 9, MUTED, false, false))
	_add_nav(dock, "files", "01  FILES", "Berkas workstation")
	_add_nav(dock, "terminal", "02  TERMINAL", "Shell sandbox")
	_add_nav(dock, "infrastructure", "03  INFRASTRUCTURE", "Status integrasi")
	_add_nav(dock, "company", "04  COMPANY", "Ringkasan perusahaan")
	dock.add_child(_spacer(8))
	dock.add_child(_label("Sesi desktop hanya berlaku untuk satu workstation. "
		+ "Semua akses dibatasi folder kerja workstation.", 10, MUTED))

	var content_panel := PanelContainer.new()
	content_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content_panel.add_theme_stylebox_override("panel", _panel_style(Color("#0c1214"), Color("#24332d"), 14))
	body.add_child(content_panel)
	var content_box := VBoxContainer.new()
	content_box.add_theme_constant_override("separation", 8)
	content_panel.add_child(content_box)
	_app_title = _label("FILES", 17, TEXT, true, false)
	_app_subtitle = _label("", 11, MUTED)
	content_box.add_child(_app_title)
	content_box.add_child(_app_subtitle)
	var content_line := ColorRect.new()
	content_line.color = Color(0.16, 0.24, 0.21, 0.7)
	content_line.custom_minimum_size = Vector2(0, 1)
	content_box.add_child(content_line)
	_content = VBoxContainer.new()
	_content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_theme_constant_override("separation", 8)
	content_box.add_child(_content)

	_status_label = _label("", 10, MUTED, false, false)
	outer.add_child(_status_label)

func _add_nav(parent: VBoxContainer, app_id: String, title: String, subtitle: String) -> void:
	var button := Button.new()
	button.toggle_mode = true
	button.text = title
	button.tooltip_text = subtitle
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.custom_minimum_size = Vector2(190, 38)
	_style_button(button, false)
	button.pressed.connect(func(): _select_app(app_id))
	parent.add_child(button)
	_nav_buttons[app_id] = button

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
func _submit_login() -> void:
	if _login_button == null or _login_button.disabled:
		return
	var account := _login_account.text.strip_edges().to_lower()
	var password := _login_password.text
	if account.is_empty():
		_set_login_error("Akun wajib diisi.")
		return
	if password.is_empty():
		_set_login_error("Kata sandi wajib diisi.")
		return
	_set_login_error("")
	_login_button.disabled = true
	_login_button.text = "MENGHUBUNGKAN..."
	_request(HTTPClient.METHOD_POST, "/api/workstations/%s/login" % _workstation_id,
		{"account_id": account, "password": password}, _on_login_response, false)

func _on_login_response(result: int, code: int, data: Variant) -> void:
	if not is_instance_valid(_login_button):
		return
	_login_button.disabled = false
	_login_button.text = "MASUK  /  LOGIN"
	if result != HTTPRequest.RESULT_SUCCESS:
		_set_login_error("Backend workstation tidak dapat dihubungi.")
		return
	if code == 201 and data is Dictionary:
		_desktop_token = str(data.get("token", ""))
		_session = {
			"session_id": str(data.get("session_id", "")),
			"expires_at": str(data.get("expires_at", "")),
			"workstation": data.get("workstation", {}),
			"account": data.get("account", {}),
			"apps": data.get("apps", []),
		}
		_login_password.text = ""
		_apply_session()
		_show_os()
		_select_app("files")
		toast_requested.emit("Login berhasil. Sesi desktop tercatat di audit.")
		return
	var message := "Login ditolak."
	if data is Dictionary:
		message = str(data.get("error", message))
	_set_login_error(message)

func _refresh_session() -> void:
	_request(HTTPClient.METHOD_GET, "/api/desktop/session", null,
		func(result, code, data):
			if result != HTTPRequest.RESULT_SUCCESS:
				toast_requested.emit("Backend workstation tidak dapat dihubungi.")
				return
			if code == 401:
				_lose_session(data)
				return
			if code == 200 and data is Dictionary and data.get("session") is Dictionary:
				_session = data.session
				_apply_session()
				_select_app(_active_app))

func _apply_session() -> void:
	var workstation: Dictionary = _session.get("workstation", {})
	var account: Dictionary = _session.get("account", {})
	var account_name := str(account.get("name", "?"))
	var account_role := str(account.get("role", "?"))
	var workstation_label := str(workstation.get("label", _workstation_label))
	var session_head := str(workstation.get("id", _workstation_id)).to_upper()
	var session_end := _friendly_time(str(_session.get("expires_at", "")))
	_session_label.text = "%s  ·  %s (%s)  ·  sesi berakhir %s" % [session_head, account_name, account_role, session_end]
	if is_instance_valid(_status_label):
		_status_label.text = "WORKDIR  %s  ·  TEKAN ESC UNTUK BERDIRI  ·  SESI TETAP AKTIF SAMPAI LOGOUT" % _workstation_id

func _lose_session(data: Variant) -> void:
	_desktop_token = ""
	_session = {}
	_show_login()
	var message := "Sesi workstation berakhir. Login ulang."
	if data is Dictionary and data.has("error"):
		message = str(data.error)
	_set_login_error(message)

func _logout() -> void:
	if _desktop_token.is_empty():
		_show_login()
		return
	_request(HTTPClient.METHOD_POST, "/api/desktop/session/close", {},
		func(_result, _code, _data):
			toast_requested.emit("Sesi desktop ditutup dan tercatat di audit."))
	_desktop_token = ""
	_session = {}
	_show_login()

func _show_login() -> void:
	_os_view.visible = false
	_login_view.visible = true
	_login_workstation.text = "%s  ·  %s" % [_workstation_id, _workstation_label]
	if is_instance_valid(_login_password):
		_login_password.text = ""
		_login_password.grab_focus()
	_set_login_error("")

func _show_os() -> void:
	_login_view.visible = false
	_os_view.visible = true
	_apply_session()

func _set_login_error(message: String) -> void:
	if not is_instance_valid(_login_error):
		return
	_login_error.text = message
	_login_error.visible = not message.is_empty()

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
func _select_app(app_id: String) -> void:
	if _desktop_token.is_empty():
		_show_login()
		return
	_active_app = app_id
	for id in _nav_buttons:
		var button: Button = _nav_buttons[id]
		button.button_pressed = str(id) == app_id
	_clear_children(_content)
	match app_id:
		"files": _render_files()
		"terminal": _render_terminal()
		"infrastructure": _render_infrastructure()
		"company": _render_company()
		_: _render_files()

func _render_files() -> void:
	_app_title.text = "FILES"
	_app_subtitle.text = "Folder kerja workstation. Path absolut dan keluar folder ditolak backend."
	_current_file = ""
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	_file_path_label = _label(_current_path, 11, ACCENT, true, false)
	_file_path_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(_file_path_label)
	var up_button := _button("NAIK")
	up_button.pressed.connect(_go_up_directory)
	head.add_child(up_button)
	var refresh_button := _button("REFRESH")
	refresh_button.pressed.connect(func(): _load_directory(_current_path))
	head.add_child(refresh_button)
	_content.add_child(head)

	var split := HBoxContainer.new()
	split.add_theme_constant_override("separation", 12)
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(split)

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(330, 0)
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	split.add_child(scroll)
	_file_list = VBoxContainer.new()
	_file_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_file_list.add_theme_constant_override("separation", 4)
	scroll.add_child(_file_list)

	var editor_box := VBoxContainer.new()
	editor_box.add_theme_constant_override("separation", 6)
	editor_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	split.add_child(editor_box)
	_file_editor_path = _label("Pilih file teks untuk dibuka.", 11, MUTED, false, false)
	editor_box.add_child(_file_editor_path)
	_file_editor = TextEdit.new()
	_file_editor.editable = false
	_file_editor.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_file_editor.custom_minimum_size = Vector2(0, 260)
	_file_editor.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_input(_file_editor)
	editor_box.add_child(_file_editor)
	_file_save_button = _button("SIMPAN FILE", true)
	_file_save_button.disabled = true
	_file_save_button.pressed.connect(_save_file)
	editor_box.add_child(_file_save_button)

	_load_directory(_current_path)

func _load_directory(path: String) -> void:
	if _busy_files:
		return
	_busy_files = true
	_request(HTTPClient.METHOD_GET, "/api/desktop/files?path=" + path.uri_encode(), null,
		func(result, code, data): _on_directory_loaded(path, result, code, data))

func _on_directory_loaded(path: String, result: int, code: int, data: Variant) -> void:
	_busy_files = false
	if not _handle_desktop_response(result, code, data):
		return
	if not data is Dictionary:
		return
	_current_path = str(data.get("path", path))
	if is_instance_valid(_file_path_label):
		_file_path_label.text = "/" + _current_path if _current_path != "." else "/"
	if not is_instance_valid(_file_list):
		return
	_clear_children(_file_list)
	var entries: Array = data.get("entries", [])
	if entries.is_empty():
		_file_list.add_child(_label("Folder kosong.", 11, MUTED))
		return
	for entry in entries:
		if not entry is Dictionary:
			continue
		var is_directory := str(entry.get("type", "file")) == "directory"
		var button := Button.new()
		button.text = ("[DIR]   " if is_directory else "[FILE]  ") + str(entry.get("name", "?"))
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size = Vector2(0, 32)
		_style_button(button, false)
		button.pressed.connect(func(): _open_entry(entry))
		_file_list.add_child(button)

func _open_entry(entry: Dictionary) -> void:
	if str(entry.get("type", "file")) == "directory":
		_load_directory(str(entry.get("path", ".")))
	else:
		_open_file(str(entry.get("path", "")))

func _go_up_directory() -> void:
	if _current_path == "." or _current_path.is_empty():
		return
	var parts := _current_path.split("/")
	if parts.size() <= 1:
		_load_directory(".")
	else:
		parts.remove_at(parts.size() - 1)
		_load_directory("/".join(parts))

func _open_file(path: String) -> void:
	if path.is_empty():
		return
	_request(HTTPClient.METHOD_GET, "/api/desktop/files/content?path=" + path.uri_encode(), null,
		func(result, code, data): _on_file_loaded(path, result, code, data))

func _on_file_loaded(path: String, result: int, code: int, data: Variant) -> void:
	if not _handle_desktop_response(result, code, data):
		return
	if not data is Dictionary or not data.get("file") is Dictionary:
		return
	_current_file = path
	_file_editor.text = str(data.file.get("content", ""))
	_file_editor.editable = true
	_file_editor_path.text = path + "  ·  " + str(data.file.get("size", 0)) + " bytes"
	_file_save_button.disabled = false

func _save_file() -> void:
	if _current_file.is_empty() or _busy_files:
		return
	_busy_files = true
	_request(HTTPClient.METHOD_POST, "/api/desktop/files/write",
		{"path": _current_file, "content": _file_editor.text},
		func(result, code, data):
			_busy_files = false
			if not _handle_desktop_response(result, code, data):
				return
			toast_requested.emit("File tersimpan di workstation dan tercatat di audit.")
			_load_directory(_current_path))

func _render_terminal() -> void:
	_app_title.text = "TERMINAL"
	_app_subtitle.text = "Shell sandbox berbasis argv. Tidak ada shell host; akses dibatasi folder workstation."
	_terminal_log = TextEdit.new()
	_terminal_log.editable = false
	_terminal_log.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_terminal_log.custom_minimum_size = Vector2(0, 300)
	_terminal_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_style_input(_terminal_log)
	_content.add_child(_terminal_log)
	_append_terminal("Bangkah workstation terminal. Ketik 'help' untuk melihat perintah yang tersedia.\n")

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	_content.add_child(row)
	var prompt := _label("$", 13, ACCENT, true, false)
	prompt.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(prompt)
	_terminal_input = LineEdit.new()
	_terminal_input.placeholder_text = "owner@%s:~$" % _workstation_id
	_terminal_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_terminal_input.text_submitted.connect(func(text): _submit_terminal(text))
	_style_input(_terminal_input)
	row.add_child(_terminal_input)
	var clear_button := _button("BERSIHKAN")
	clear_button.pressed.connect(func(): _terminal_log.text = "")
	row.add_child(clear_button)
	_terminal_input.grab_focus()

func _submit_terminal(command: String) -> void:
	var raw := command.strip_edges()
	if raw.is_empty() or _busy_terminal:
		return
	_busy_terminal = true
	_terminal_input.text = ""
	_append_terminal("$ " + raw + "\n")
	_request(HTTPClient.METHOD_POST, "/api/terminal/exec", {"command": raw},
		func(result, code, data):
			_busy_terminal = false
			if result != HTTPRequest.RESULT_SUCCESS:
				_append_terminal("SYSTEM: backend tidak dapat dihubungi.\n")
				return
			if code == 401:
				_lose_session(data)
				return
			if not data is Dictionary:
				_append_terminal("SYSTEM: respons tidak valid.\n")
				return
			var stdout := str(data.get("stdout", ""))
			var stderr := str(data.get("stderr", ""))
			if not stdout.is_empty():
				_append_terminal(stdout.rstrip("\n") + "\n")
			if not stderr.is_empty():
				_append_terminal(stderr.rstrip("\n") + "\n")
			_append_terminal("[exit %s]\n" % str(data.get("exit_code", "?")))
			if is_instance_valid(_terminal_input):
				_terminal_input.grab_focus())

func _append_terminal(text: String) -> void:
	if not is_instance_valid(_terminal_log):
		return
	_terminal_log.text += text
	_terminal_log.scroll_vertical = _terminal_log.get_line_count()

func _render_infrastructure() -> void:
	_app_title.text = "INFRASTRUCTURE"
	_app_subtitle.text = "Status ini dibaca langsung dari backend. Integrasi yang belum dikonfigurasi ditandai jujur."
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 6)
	scroll.add_child(column)
	var system_box := VBoxContainer.new()
	system_box.add_theme_constant_override("separation", 6)
	column.add_child(system_box)
	var audit_box := VBoxContainer.new()
	audit_box.add_theme_constant_override("separation", 6)
	column.add_child(audit_box)
	system_box.add_child(_label("Memuat status workstation...", 11, MUTED))
	_request(HTTPClient.METHOD_GET, "/api/desktop/system", null,
		func(result, code, data): _on_system_loaded(system_box, result, code, data))
	_request(HTTPClient.METHOD_GET, "/api/desktop/audit?limit=12", null,
		func(result, code, data): _on_audit_loaded(audit_box, result, code, data))

func _on_system_loaded(box: VBoxContainer, result: int, code: int, data: Variant) -> void:
	if not _handle_desktop_response(result, code, data):
		return
	_clear_children(box)
	if not data is Dictionary:
		box.add_child(_label("Status tidak tersedia.", 11, DANGER))
		return
	_render_system_info(box, data)

func _on_audit_loaded(box: VBoxContainer, result: int, code: int, data: Variant) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		return
	if not data is Dictionary:
		return
	var events: Array = data.get("events", [])
	box.add_child(_label("AKTIVITAS TERAKHIR", 10, MUTED, false, false))
	if events.is_empty():
		box.add_child(_label("Belum ada aktivitas tercatat.", 11, MUTED))
	for event in events:
		if not event is Dictionary:
			continue
		var event_time := _friendly_time(str(event.get("created_at", "")))
		var event_detail := str(event.get("detail", event.get("event_type", "")))
		box.add_child(_label("%s  ·  %s" % [event_time, event_detail], 10, MUTED))

func _render_system_info(box: VBoxContainer, info: Dictionary) -> void:
	var workstation: Dictionary = info.get("workstation", {})
	var account: Dictionary = info.get("account", {})
	var session: Dictionary = info.get("session", {})
	var terminal: Dictionary = info.get("terminal", {})
	box.add_child(_label("WORKSTATION", 10, MUTED, false, false))
	box.add_child(_label("%s  ·  %s" % [str(workstation.get("id", "?")), str(workstation.get("label", ""))], 13, TEXT, true))
	var account_line := "Akun %s (%s)  ·  sesi %s  ·  berakhir %s" % [str(account.get("name", "?")), str(account.get("role", "?")), str(session.get("id", "?")), _friendly_time(str(session.get("expires_at", "")))]
	box.add_child(_label(account_line, 11, MUTED))
	box.add_child(_spacer(6))
	box.add_child(_label("TERMINAL", 10, MUTED, false, false))
	var terminal_line := "Mode %s  ·  workdir %s" % [str(terminal.get("mode", "?")), str(terminal.get("workdir", "?"))]
	box.add_child(_label(terminal_line, 11, TEXT))
	box.add_child(_label("Builtin: " + ", ".join(_string_array(terminal.get("builtins", []))), 10, MUTED))
	var external: Array = terminal.get("external_binaries", [])
	if external.is_empty():
		box.add_child(_label("Binary eksternal: tidak ada yang diizinkan (allowlist kosong).", 10, WARN))
	else:
		box.add_child(_label("Binary eksternal diizinkan: " + ", ".join(_string_array(external)), 10, ACCENT))
	var limits: Dictionary = terminal.get("limits", {})
	var limits_line := "Batas: %s karakter perintah  ·  %s byte per file  ·  %s karakter output" % [str(limits.get("command_chars", "?")), str(limits.get("file_bytes", "?")), str(limits.get("output_chars", "?"))]
	box.add_child(_label(limits_line, 10, MUTED))
	box.add_child(_spacer(6))
	box.add_child(_label("INTEGRASI PERUSAHAAN", 10, MUTED, false, false))
	var integrations: Dictionary = info.get("integrations", {})
	_add_integration_row(box, "SMTP / email keluar", integrations.get("smtp", {}))
	_add_integration_row(box, "Deploy webhook", integrations.get("deploy_webhook", {}))
	_add_integration_row(box, "API bearer token", integrations.get("api_token", {}))
	var domain: Dictionary = integrations.get("domain", {})
	var domain_state := "DNS tidak dikelola" if not bool(domain.get("dns_managed", false)) else "DNS dikelola"
	var email_state := "email belum disediakan" if not bool(domain.get("email_provisioned", false)) else "email aktif"
	box.add_child(_label("Domain  ·  %s  ·  %s  ·  %s" % [str(domain.get("name", "?")), domain_state, email_state], 11, WARN))
	box.add_child(_label(str(domain.get("detail", "")), 10, MUTED))

func _add_integration_row(box: VBoxContainer, title: String, entry: Variant) -> void:
	var data: Dictionary = entry if entry is Dictionary else {}
	var configured := bool(data.get("configured", data.get("enabled", false)))
	var state := "CONFIGURED" if configured else "ABSENT"
	var color := ACCENT if configured else WARN
	box.add_child(_label("%s  ·  %s" % [title, state], 11, color))
	var detail := str(data.get("detail", ""))
	if not detail.is_empty():
		box.add_child(_label(detail, 10, MUTED))

func _render_company() -> void:
	_app_title.text = "COMPANY"
	_app_subtitle.text = "Ringkasan live dari API perusahaan. Dashboard lengkap tetap memakai panel yang ada."
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_content.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 6)
	scroll.add_child(box)
	box.add_child(_label("Memuat ringkasan perusahaan...", 11, MUTED))
	var open_button := _button("BUKA DASHBOARD PERUSAHAAN", true)
	open_button.pressed.connect(func(): company_requested.emit())
	_content.add_child(open_button)
	_request(HTTPClient.METHOD_GET, "/api/status", null,
		func(result, code, data):
			if result != HTTPRequest.RESULT_SUCCESS or code != 200 or not data is Dictionary:
				_clear_children(box)
				box.add_child(_label("Backend perusahaan tidak dapat dihubungi.", 11, WARN))
				return
			_clear_children(box)
			_render_company_snapshot(box, data))

func _render_company_snapshot(box: VBoxContainer, data: Dictionary) -> void:
	var project: Variant = data.get("project", null)
	var project_name := "Belum ada proyek aktif"
	if project is Dictionary:
		project_name = str(project.get("name", project_name))
	box.add_child(_label("PROYEK AKTIF", 10, MUTED, false, false))
	box.add_child(_label(project_name, 15, TEXT, true))
	var company: Dictionary = data.get("company", {})
	var office: Dictionary = data.get("office", {})
	var employees: Array = office.get("employees", [])
	var team_line := "%d karyawan di kantor  ·  %d task  ·  %d rapat  ·  %d paper menunggu" % [employees.size(), _array_size(company.get("tasks", [])), _array_size(company.get("meetings", [])), int(company.get("papers_pending", 0))]
	box.add_child(_label(team_line, 11, TEXT))
	var ops_line := "%d approval menunggu  ·  %d outbox  ·  %d print job" % [int(company.get("approvals_pending", 0)), _array_size(company.get("outbox", [])), _array_size(company.get("print_jobs", []))]
	box.add_child(_label(ops_line, 11, MUTED))
	box.add_child(_spacer(6))
	box.add_child(_label("Semua aksi perusahaan tetap melewati approval dan outbox. "
		+ "Tidak ada email, deployment, atau domain yang dikirim tanpa persetujuan.", 10, MUTED))

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
func _request(method: int, path: String, body: Variant, callback: Callable,
		include_desktop: bool = true) -> void:
	var http := HTTPRequest.new()
	http.timeout = 15.0
	add_child(http)
	http.request_completed.connect(func(result, code, _headers, payload):
		http.queue_free()
		var data: Variant = null
		if payload.size() > 0:
			data = JSON.parse_string(payload.get_string_from_utf8())
		callback.call(result, code, data))
	var headers := PackedStringArray(["Content-Type: application/json"])
	if not _api_token.is_empty():
		headers.append("Authorization: Bearer " + _api_token)
	if include_desktop and not _desktop_token.is_empty():
		headers.append("X-Desktop-Session: " + _desktop_token)
	var payload_text := "" if body == null else JSON.stringify(body)
	var error := http.request(_server_url + path, headers, method, payload_text)
	if error != OK:
		http.queue_free()
		callback.call(HTTPRequest.RESULT_CANT_CONNECT, 0, null)

func _handle_desktop_response(result: int, code: int, data: Variant) -> bool:
	if result != HTTPRequest.RESULT_SUCCESS:
		toast_requested.emit("Backend workstation tidak dapat dihubungi.")
		return false
	if code == 401:
		_lose_session(data)
		return false
	if code < 200 or code >= 300:
		var message := "Operasi workstation ditolak."
		if data is Dictionary:
			message = str(data.get("error", message))
		toast_requested.emit(message)
		return false
	return true

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
func _label(text_value: String, size: int, color: Color, bold: bool = false,
		wrap: bool = true) -> Label:
	var label := Label.new()
	label.text = text_value
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	if bold:
		label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.35))
		label.add_theme_constant_override("outline_size", 1)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if wrap else TextServer.AUTOWRAP_OFF
	return label

func _spacer(height: float) -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, height)
	return spacer

func _panel_style(background: Color, border: Color, radius: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 18
	style.content_margin_bottom = 18
	return style

func _button(text_value: String, primary: bool = false) -> Button:
	var button := Button.new()
	button.text = text_value
	button.focus_mode = Control.FOCUS_ALL
	_style_button(button, primary)
	return button

func _style_button(button: Button, primary: bool) -> void:
	button.add_theme_font_size_override("font_size", 11)
	button.add_theme_color_override("font_color", TEXT)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	button.add_theme_stylebox_override("normal", _button_style(
		Color("#243b31") if primary else Color("#141c1e"),
		Color("#4f7a5d") if primary else Color("#2d3a3c")))
	button.add_theme_stylebox_override("hover", _button_style(Color("#2c4a3c"), Color("#6d9877")))
	button.add_theme_stylebox_override("pressed", _button_style(Color("#1d3329"), Color("#7fae8a")))
	button.add_theme_stylebox_override("disabled", _button_style(Color("#121819"), Color("#25302f")))
	button.add_theme_color_override("font_disabled_color", Color("#5e6b66"))

func _button_style(background: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 7
	style.content_margin_bottom = 7
	return style

func _style_input(control: Control) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#0a1113")
	style.border_color = Color("#2d3a3c")
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 7
	style.content_margin_bottom = 7
	if control is LineEdit:
		var line := control as LineEdit
		line.custom_minimum_size.y = 38
		line.add_theme_font_size_override("font_size", 12)
		line.add_theme_color_override("font_color", TEXT)
		line.add_theme_color_override("font_placeholder_color", Color("#70807a"))
		line.add_theme_color_override("caret_color", ACCENT)
		line.add_theme_stylebox_override("normal", style)
		line.add_theme_stylebox_override("focus", _button_style(Color("#0a1113"), ACCENT))
	elif control is TextEdit:
		var edit := control as TextEdit
		edit.add_theme_font_size_override("font_size", 12)
		edit.add_theme_color_override("font_color", TEXT)
		edit.add_theme_color_override("caret_color", ACCENT)
		edit.add_theme_stylebox_override("normal", style)
		edit.add_theme_stylebox_override("focus", _button_style(Color("#0a1113"), ACCENT))

func _clear_children(node: Node) -> void:
	if not is_instance_valid(node):
		return
	for child in node.get_children():
		node.remove_child(child)
		child.queue_free()

func _friendly_time(value: String) -> String:
	if value.is_empty():
		return "-"
	return value.replace("T", " ").replace("+00:00", " UTC").left(19)

func _string_array(value: Variant) -> Array:
	var result: Array = []
	if value is Array:
		for item in value:
			result.append(str(item))
	return result

func _array_size(value: Variant) -> int:
	if value is Array:
		return value.size()
	return int(value) if value is float or value is int else 0
