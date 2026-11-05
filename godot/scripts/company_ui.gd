extends CanvasLayer

signal panel_visibility_changed(is_visible: bool)
signal employee_chat_requested(employee_id: String)
signal demo_action_requested(message: String)
signal connect_backend_requested(url: String, token: String)
signal company_action_requested(action: String, payload: Dictionary)

# Refined palette
const BG := Color("#0f1315")
const SURFACE := Color("#1c2224")
const SURFACE_ALT := Color("#232b2e")
const SURFACE_ELEVATED := Color("#2a3336")
const BORDER := Color("#3d4a4d")
const BORDER_SUBTLE := Color("#2f3b3e")
const TEXT := Color("#eef1ee")
const TEXT_SECONDARY := Color("#c4cac6")
const MUTED := Color("#8a9690")
const ACCENT := Color("#8fb59a")
const ACCENT_DARK := Color("#2d403b")
const AMBER := Color("#d4a96a")
const RED := Color("#d98072")
const BLUE := Color("#8da9b4")
const FOCUS_BORDER := Color("#8fb59a")
const GLOW := Color("#8fb59a")

var is_open := false
var company_snapshot: Dictionary = {}
var active_page := "overview"
var selected_paper_id := ""
var connection_online := false
var shell: PanelContainer
var shell_margin_container: MarginContainer
var backdrop: ColorRect
var nav_buttons: Dictionary = {}
var content_box: VBoxContainer
var page_title: Label
var connection_badge: Label
var data_badge: Label
var launcher: PanelContainer
var overlay_root: Control
var toast_label: Label
var backend_url_input: LineEdit
var api_token_input: LineEdit
var toast_timer: Timer
var scroll_container: ScrollContainer
var header_tray_button: Button
var nav_meta: Dictionary = {}
var last_snapshot_signature: String = ""
var current_server_url: String = "http://127.0.0.1:8765"
var _open_tween: Tween
var _content_tween: Tween
var _last_page_intro: String = ""
var launcher_tray_button: Button
var toast_panel: PanelContainer
var _clock_label: Label
var _connection_dot: Label
var _clock_elapsed: float = 0.0

const PAGE_ORDER := ["overview", "projects", "team", "documents", "meetings", "secretary", "archive", "settings"]

func _ready() -> void:
	layer = 20
	_build_interface()
	toast_timer = Timer.new()
	toast_timer.one_shot = true
	toast_timer.wait_time = 2.8
	toast_timer.timeout.connect(_hide_toast)
	add_child(toast_timer)
	is_open = true
	_set_open(false, true)

func _process(delta: float) -> void:
	_clock_elapsed += delta
	if _clock_elapsed < 1.0:
		return
	_clock_elapsed = 0.0
	if is_instance_valid(_clock_label):
		_clock_label.text = Time.get_time_string_from_system().left(5)

func _build_interface() -> void:
	overlay_root = Control.new()
	overlay_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(overlay_root)

	# Subtle vignette overlay for depth — only visible when panel is open
	var vignette := ColorRect.new()
	vignette.color = Color(0.02, 0.03, 0.025, 0.35)
	vignette.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	vignette.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vignette.visible = false
	overlay_root.add_child(vignette)

	launcher = _panel(overlay_root, Vector2.ZERO, Vector2(326, 44), SURFACE, BORDER, 11)
	launcher.anchor_left = 1.0
	launcher.anchor_right = 1.0
	launcher.offset_left = -348
	launcher.offset_right = -22
	launcher.offset_top = 84
	launcher.offset_bottom = 128
	var launch_style := _style(SURFACE, BORDER, 11, 1)
	launch_style.shadow_color = Color(0, 0, 0, 0.34)
	launch_style.shadow_size = 8
	launch_style.shadow_offset = Vector2(0, 3)
	launcher.add_theme_stylebox_override("panel", launch_style)
	var launch_row := HBoxContainer.new()
	launch_row.add_theme_constant_override("separation", 8)
	launcher.add_child(launch_row)
	var brand := _label("BANGKAH", 10, TEXT, true, false)
	brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	launch_row.add_child(brand)
	var open_button := _button("PUSAT KOMANDO  ↗", Callable(self, "open_panel").bind("overview"), "primary")
	open_button.custom_minimum_size = Vector2(158, 30)
	# Hover scale for primary launcher button.
	open_button.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(open_button, "scale", Vector2(1.03, 1.03), 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	open_button.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(open_button, "scale", Vector2(1.0, 1.0), 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	launch_row.add_child(open_button)
	launcher_tray_button = _button("KOTAK  03", Callable(self, "open_panel").bind("documents"), "quiet")
	launcher_tray_button.custom_minimum_size = Vector2(88, 30)
	launch_row.add_child(launcher_tray_button)
	launcher.visible = false

	var veil := ColorRect.new()
	veil.color = Color(0.025, 0.04, 0.035, 0.88)
	veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay_root.add_child(veil)
	veil.mouse_filter = Control.MOUSE_FILTER_STOP
	veil.visible = false
	backdrop = veil

	shell_margin_container = MarginContainer.new()
	shell_margin_container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shell_margin_container.add_theme_constant_override("margin_left", 30)
	shell_margin_container.add_theme_constant_override("margin_top", 28)
	shell_margin_container.add_theme_constant_override("margin_right", 30)
	shell_margin_container.add_theme_constant_override("margin_bottom", 28)
	overlay_root.add_child(shell_margin_container)
	shell = PanelContainer.new()
	shell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shell.size_flags_vertical = Control.SIZE_EXPAND_FILL
	shell.add_theme_stylebox_override("panel", _style(SURFACE, BORDER, 14, 1))
	shell_margin_container.add_child(shell)

	var shell_box := VBoxContainer.new()
	shell_box.add_theme_constant_override("separation", 0)
	shell.add_child(shell_box)
	_build_header(shell_box)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 0)
	shell_box.add_child(body)
	_build_sidebar(body)
	var separator := ColorRect.new()
	separator.color = BORDER_SUBTLE
	separator.custom_minimum_size = Vector2(1, 0)
	separator.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(separator)
	var page_margin := MarginContainer.new()
	page_margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	page_margin.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page_margin.add_theme_constant_override("margin_left", 26)
	page_margin.add_theme_constant_override("margin_right", 26)
	page_margin.add_theme_constant_override("margin_top", 22)
	page_margin.add_theme_constant_override("margin_bottom", 18)
	body.add_child(page_margin)
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	page_margin.add_child(scroll)
	content_box = VBoxContainer.new()
	content_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_box.add_theme_constant_override("separation", 16)
	scroll.add_child(content_box)
	scroll_container = scroll
	_style_scrollbar(scroll)

	toast_panel = PanelContainer.new()
	toast_panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	toast_panel.offset_left = 330
	toast_panel.offset_right = -330
	toast_panel.offset_top = -66
	toast_panel.offset_bottom = -20
	toast_panel.visible = false
	var toast_style := _style(Color("#141b1d"), Color("#4a6a55"), 10, 1)
	toast_style.shadow_color = Color(0, 0, 0, 0.38)
	toast_style.shadow_size = 8
	toast_style.shadow_offset = Vector2(0, 3)
	toast_panel.add_theme_stylebox_override("panel", toast_style)
	var toast_row := HBoxContainer.new()
	toast_row.add_theme_constant_override("separation", 10)
	toast_panel.add_child(toast_row)
	var toast_accent := ColorRect.new()
	toast_accent.color = ACCENT
	toast_accent.custom_minimum_size = Vector2(3, 0)
	toast_accent.size_flags_vertical = Control.SIZE_EXPAND_FILL
	toast_row.add_child(toast_accent)
	toast_label = _label("", 12, TEXT, true)
	toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	toast_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toast_row.add_child(toast_label)
	overlay_root.add_child(toast_panel)
	_render_page()

func _build_header(parent: VBoxContainer) -> void:
	var header_margin := MarginContainer.new()
	header_margin.add_theme_constant_override("margin_left", 24)
	header_margin.add_theme_constant_override("margin_right", 20)
	header_margin.add_theme_constant_override("margin_top", 15)
	header_margin.add_theme_constant_override("margin_bottom", 15)
	parent.add_child(header_margin)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	header_margin.add_child(row)
	var mark := PanelContainer.new()
	mark.custom_minimum_size = Vector2(42, 42)
	mark.add_theme_stylebox_override("panel", _style(ACCENT_DARK, ACCENT_DARK, 10, 0))
	row.add_child(mark)
	var mark_label := _label("B", 22, ACCENT, true)
	mark_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	mark_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	mark.add_child(mark_label)
	var brand_box := VBoxContainer.new()
	brand_box.add_theme_constant_override("separation", 1)
	row.add_child(brand_box)
	brand_box.add_child(_label("BANGKAH  /  KANTOR PERUSAHAAN", 12, MUTED, true, false))
	page_title = _label("Ringkasan perusahaan", 19, TEXT, true, false)
	brand_box.add_child(page_title)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	_clock_label = _label(Time.get_time_string_from_system().left(5), 11, TEXT_SECONDARY, true, false)
	_clock_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(_clock_label)
	_connection_dot = _label("●", 10, MUTED, true, false)
	_connection_dot.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(_connection_dot)
	# Subtle pulse for connection indicator.
	var pulse := create_tween()
	pulse.set_loops()
	pulse.tween_property(_connection_dot, "modulate:a", 0.5, 1.2).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	pulse.tween_property(_connection_dot, "modulate:a", 1.0, 1.2).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	data_badge = _label("DATA CONTOH", 10, AMBER, true, false)
	data_badge.add_theme_stylebox_override("normal", _style(Color("#3b3020"), Color("#6b5230"), 9, 1))
	row.add_child(data_badge)
	connection_badge = _label("OFFLINE", 10, MUTED, true, false)
	row.add_child(connection_badge)
	header_tray_button = _button("KOTAK MASUK", Callable(self, "open_panel").bind("documents"), "secondary")
	header_tray_button.custom_minimum_size = Vector2(132, 38)
	row.add_child(header_tray_button)
	var close := _button("CLOSE  ×", Callable(self, "close_panel"), "quiet")
	close.custom_minimum_size = Vector2(88, 38)
	# Hover effect for close button.
	close.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(close, "modulate:a", 0.7, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	close.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(close, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.add_child(close)
	var line := ColorRect.new()
	line.color = BORDER_SUBTLE
	line.custom_minimum_size = Vector2(0, 1)
	parent.add_child(line)

func _build_sidebar(parent: HBoxContainer) -> void:
	var side_margin := MarginContainer.new()
	side_margin.custom_minimum_size.x = 214
	side_margin.add_theme_constant_override("margin_left", 14)
	side_margin.add_theme_constant_override("margin_right", 14)
	side_margin.add_theme_constant_override("margin_top", 20)
	side_margin.add_theme_constant_override("margin_bottom", 18)
	parent.add_child(side_margin)
	var side := VBoxContainer.new()
	side.add_theme_constant_override("separation", 6)
	side_margin.add_child(side)
	side.add_child(_label("OPERASIONAL", 9, MUTED, true))
	_add_nav(side, "overview", "Ringkasan", "01")
	_add_nav(side, "projects", "Proyek & Tugas", "02")
	_add_nav(side, "team", "Karyawan & Tim", "03")
	side.add_child(_spacer(8))
	side.add_child(_label("KOMUNIKASI & ARSIP", 9, MUTED, true))
	_add_nav(side, "documents", "Kotak Masuk Owner", "04")
	_add_nav(side, "meetings", "Rapat", "05")
	_add_nav(side, "secretary", "Sekretaris", "06")
	_add_nav(side, "archive", "Arsip Perusahaan", "07")
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	side.add_child(spacer)
	var divider := ColorRect.new()
	divider.color = BORDER_SUBTLE
	divider.custom_minimum_size = Vector2(0, 1)
	side.add_child(divider)
	side.add_child(_label("OWNER SESSION", 9, MUTED, true))
	side.add_child(_label("Owner · Administrator", 12, TEXT, true))
	side.add_child(_label("Local desktop instance", 10, MUTED))
	var settings := _button("PENGATURAN  ⚙", Callable(self, "open_panel").bind("settings"), "quiet")
	settings.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.add_child(settings)

func _add_nav(parent: VBoxContainer, page_id: String, title: String, number: String, _badge: String = "") -> void:
	nav_meta[page_id] = {"number": number, "title": title}
	var button := _button(_nav_text(page_id, 0), Callable(self, "open_panel").bind(page_id), "nav")
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.custom_minimum_size = Vector2(0, 42)
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.tooltip_text = _shortcut_for(page_id)
	# Hover feedback for nav items.
	button.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(button, "modulate:a", 0.8, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	button.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(button, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	parent.add_child(button)
	nav_buttons[page_id] = button

func _shortcut_for(page_id: String) -> String:
	match page_id:
		"overview": return "F1 atau 1"
		"documents": return "F2 atau 4"
		"projects": return "F3 atau 2"
		"team": return "F4 atau 3"
		"meetings": return "5"
		"secretary": return "6"
		"archive": return "7"
		"settings": return "8"
		_: return ""

func _spacer(height: float) -> Control:
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, height)
	return spacer

func _nav_text(page_id: String, badge_count: int) -> String:
	var meta: Dictionary = nav_meta.get(page_id, {})
	var text := "%s   %s" % [str(meta.get("number", "")), str(meta.get("title", ""))]
	if badge_count > 0:
		text += "     %02d" % badge_count
	return text

func _inbox_count() -> int:
	var count := 0
	for paper in _company_rows("papers"):
		if str(paper.get("status", "")) == "unread":
			count += 1
	for approval in _company_rows("approvals"):
		if str(approval.get("status", "")) == "pending":
			count += 1
	return count

func _refresh_nav_buttons() -> void:
	var unread := _inbox_count()
	for page_id in nav_buttons:
		var button: Button = nav_buttons[page_id]
		var selected := str(page_id) == active_page
		var badge := unread if str(page_id) == "documents" else 0
		button.text = ("•  " if selected else "    ") + _nav_text(str(page_id), badge)
		button.add_theme_color_override("font_color", ACCENT if selected else TEXT_SECONDARY)
	if is_instance_valid(header_tray_button):
		header_tray_button.text = ("KOTAK MASUK  ·  %02d" % unread) if unread > 0 else "KOTAK MASUK"
	if is_instance_valid(launcher_tray_button):
		launcher_tray_button.text = ("KOTAK  %02d" % unread) if unread > 0 else "KOTAK"

func _update_inbox_badge() -> void:
	_refresh_nav_buttons()

func open_panel(page_id: String = "overview") -> void:
	active_page = page_id
	last_snapshot_signature = JSON.stringify(company_snapshot)
	_set_open(true)
	_render_page(true, true)

func close_panel() -> void:
	_set_open(false)

func is_panel_open() -> bool:
	return is_open

func set_connection_state(online: bool) -> void:
	connection_online = online
	if not is_instance_valid(connection_badge):
		return
	connection_badge.text = "BACKEND TERHUBUNG" if online else "BACKEND OFFLINE"
	connection_badge.add_theme_color_override("font_color", ACCENT if online else AMBER)
	if is_instance_valid(_connection_dot):
		_connection_dot.add_theme_color_override("font_color", ACCENT if online else AMBER)
	if is_instance_valid(data_badge):
		data_badge.text = "DATA OPERASIONAL" if online else "MODE LOKAL"
		data_badge.add_theme_color_override("font_color", ACCENT if online else AMBER)
		data_badge.add_theme_stylebox_override("normal", _style(Color("#22322c"), Color("#4a6a55"), 9, 1) if online else _style(Color("#3b3020"), Color("#6b5230"), 9, 1))

func set_company_snapshot(data: Dictionary) -> void:
	company_snapshot = data.duplicate(true)
	var papers := _company_rows("papers")
	if not selected_paper_id.is_empty() and _paper_by_id(selected_paper_id).is_empty():
		selected_paper_id = str(papers[0].get("id", "")) if not papers.is_empty() else ""
	_update_inbox_badge()
	if not is_open:
		return
	if _ui_busy():
		return
	var signature := JSON.stringify(company_snapshot)
	if signature == last_snapshot_signature:
		return
	last_snapshot_signature = signature
	_render_page(false)

func _ui_busy() -> bool:
	for child in get_children():
		if child is AcceptDialog and child.visible:
			return true
	var focus := get_viewport().gui_get_focus_owner()
	if focus is LineEdit or focus is TextEdit or focus is OptionButton:
		var node: Node = focus
		while node != null:
			if node == content_box:
				return true
			node = node.get_parent()
	return false

func _company_data() -> Dictionary:
	var value: Variant = company_snapshot.get("company", {})
	return value if value is Dictionary else {}

func _company_rows(key: String) -> Array:
	var value: Variant = _company_data().get(key, [])
	return value if value is Array else []

func _employee_name(employee_id: String) -> String:
	for employee in _company_rows("employees"):
		if str(employee.get("id", "")) == employee_id:
			return str(employee.get("name", employee_id))
	return "Belum ditentukan" if employee_id.is_empty() else employee_id

func _status_color(status: String) -> Color:
	match status.to_lower():
		"working", "in_progress", "completed", "approved", "read": return ACCENT
		"blocked", "failed", "rejected", "urgent": return RED
		"pending", "unread", "queued", "scheduled", "deferred", "awaiting_executor": return AMBER
		"archived", "cancelled": return MUTED
		_: return MUTED

func _set_open(value: bool, instant: bool = false) -> void:
	if is_open == value:
		return
	is_open = value
	if is_instance_valid(shell_margin_container):
		shell_margin_container.visible = true
		shell_margin_container.mouse_filter = Control.MOUSE_FILTER_STOP if value else Control.MOUSE_FILTER_IGNORE
	if is_instance_valid(backdrop):
		backdrop.visible = true
		backdrop.mouse_filter = Control.MOUSE_FILTER_STOP if value else Control.MOUSE_FILTER_IGNORE
	if is_instance_valid(launcher):
		launcher.visible = not value
	if instant:
		if is_instance_valid(shell_margin_container):
			shell_margin_container.modulate.a = 1.0 if value else 0.0
		if is_instance_valid(backdrop):
			backdrop.modulate.a = 1.0 if value else 0.0
		panel_visibility_changed.emit(value)
		return
	if _open_tween and _open_tween.is_valid():
		_open_tween.kill()
	_open_tween = create_tween()
	_open_tween.set_parallel(true)
	if value:
		if is_instance_valid(shell_margin_container):
			shell_margin_container.modulate.a = 0.0
			_open_tween.tween_property(shell_margin_container, "modulate:a", 1.0, 0.22).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		if is_instance_valid(backdrop):
			backdrop.modulate.a = 0.0
			_open_tween.tween_property(backdrop, "modulate:a", 1.0, 0.28).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		# Subtle scale pop on open.
		if is_instance_valid(shell):
			shell.scale = Vector2(0.98, 0.98)
			_open_tween.parallel().tween_property(shell, "scale", Vector2(1.0, 1.0), 0.25).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	else:
		if is_instance_valid(shell_margin_container):
			_open_tween.tween_property(shell_margin_container, "modulate:a", 0.0, 0.18).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		if is_instance_valid(backdrop):
			_open_tween.tween_property(backdrop, "modulate:a", 0.0, 0.22).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		var t = _open_tween
		_open_tween.tween_callback(func(): panel_visibility_changed.emit(value))
		_open_tween = t
	panel_visibility_changed.emit(value)

func _render_page(reset_scroll: bool = true, animate: bool = false) -> void:
	if not is_instance_valid(content_box):
		return
	var previous_scroll := scroll_container.scroll_vertical if is_instance_valid(scroll_container) else 0
	var should_animate := animate and is_open and content_box.get_child_count() > 0
	if should_animate:
		var fade := create_tween()
		fade.tween_property(content_box, "modulate:a", 0.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		fade.tween_callback(func():
			for child in content_box.get_children():
				child.queue_free()
			var titles := {
				"overview":"Ringkasan perusahaan", "projects":"Proyek & tugas", "team":"Karyawan & tim",
				"documents":"Kotak masuk Owner", "meetings":"Rapat & keputusan", "secretary":"Asisten eksekutif",
				"archive":"Arsip perusahaan", "settings":"Pengaturan workspace"
			}
			page_title.text = str(titles.get(active_page, "Ringkasan perusahaan"))
			for page_id in nav_buttons:
				var nav_button: Button = nav_buttons[page_id]
				var selected := str(page_id) == active_page
				var base_color := Color("#2b4134") if selected else SURFACE_ALT
				var base_border := Color("#66856b") if selected else BORDER_SUBTLE
				nav_button.add_theme_stylebox_override("normal", _style(base_color, base_border, 8, 1))
			_update_inbox_badge()
			match active_page:
				"overview": _render_overview()
				"projects": _render_projects()
				"team": _render_team()
				"documents": _render_documents()
				"meetings": _render_meetings()
				"secretary": _render_secretary()
				"archive": _render_archive()
				"settings": _render_settings()
				_: _render_overview()
		)
		fade.tween_property(content_box, "modulate:a", 1.0, 0.18).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	else:
		for child in content_box.get_children():
			child.queue_free()
		var titles := {
			"overview":"Ringkasan perusahaan", "projects":"Proyek & tugas", "team":"Karyawan & tim",
			"documents":"Kotak masuk Owner", "meetings":"Rapat & keputusan", "secretary":"Asisten eksekutif",
			"archive":"Arsip perusahaan", "settings":"Pengaturan workspace"
		}
		page_title.text = str(titles.get(active_page, "Ringkasan perusahaan"))
		for page_id in nav_buttons:
			var nav_button: Button = nav_buttons[page_id]
			var selected := str(page_id) == active_page
			var base_color := Color("#2b4134") if selected else SURFACE_ALT
			var base_border := Color("#66856b") if selected else BORDER_SUBTLE
			nav_button.add_theme_stylebox_override("normal", _style(base_color, base_border, 8, 1))
		_update_inbox_badge()
		match active_page:
			"overview": _render_overview()
			"projects": _render_projects()
			"team": _render_team()
			"documents": _render_documents()
			"meetings": _render_meetings()
			"secretary": _render_secretary()
			"archive": _render_archive()
			"settings": _render_settings()
			_: _render_overview()
	if is_instance_valid(scroll_container):
		if reset_scroll:
			scroll_container.scroll_vertical = 0
		else:
			scroll_container.set_deferred("scroll_vertical", previous_scroll)

func _animate_content_in() -> void:
	if _content_tween and _content_tween.is_valid():
		_content_tween.kill()
	content_box.modulate.a = 0.0
	_content_tween = create_tween()
	_content_tween.tween_property(content_box, "modulate:a", 1.0, 0.20).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _hide_toast() -> void:
	if is_instance_valid(toast_label):
		toast_label.visible = false
	if is_instance_valid(toast_panel):
		toast_panel.visible = false

func _style_scrollbar(scroll: ScrollContainer) -> void:
	var bar := scroll.get_v_scroll_bar()
	bar.custom_minimum_size.x = 10
	var track := StyleBoxFlat.new()
	track.bg_color = Color(0, 0, 0, 0.18)
	track.set_corner_radius_all(5)
	bar.add_theme_stylebox_override("scroll", track)
	var grabber := StyleBoxFlat.new()
	grabber.bg_color = Color("#3f5148")
	grabber.set_corner_radius_all(5)
	bar.add_theme_stylebox_override("grabber", grabber)
	var grabber_hover := StyleBoxFlat.new()
	grabber_hover.bg_color = Color("#52695d")
	grabber_hover.set_corner_radius_all(5)
	bar.add_theme_stylebox_override("grabber_highlight", grabber_hover)
	var grabber_pressed := StyleBoxFlat.new()
	grabber_pressed.bg_color = ACCENT.darkened(0.25)
	grabber_pressed.set_corner_radius_all(5)
	bar.add_theme_stylebox_override("grabber_pressed", grabber_pressed)

func _render_projects() -> void:
	_page_intro("Workspace aktif, task, acceptance criteria dan evidence dari backend.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Tidak ada data proyek yang dapat dimuat.", AMBER); return
	var projects: Variant = company_snapshot.get("projects", [])
	var project_card := _section_card(content_box, "WORKSPACE PROYEK", "Direktori proyek yang terdeteksi backend")
	if projects is Array and not projects.is_empty():
		for project in projects:
			var title := str(project.get("name", project.get("project_name", project.get("directory", "Project"))))
			_add_project_entry(project_card, title, str(project.get("directory", "Workspace")), str(project.get("status", "UNKNOWN")).to_upper(), 0.0, str(project.get("current_phase", "Status belum dilaporkan")))
	else:
		project_card.add_child(_label("Belum ada workspace proyek yang terdaftar.", 12, MUTED))
	var tasks := _company_rows("tasks")
	var task_card := _section_card(content_box, "DAFTAR TASK", "Task persisten dan transisi tervalidasi")
	task_card.add_child(_button("BUAT TASK  +", Callable(self, "_open_task_dialog"), "primary"))
	if tasks.is_empty(): task_card.add_child(_label("Belum ada task.", 12, MUTED))
	for task in tasks:
		var task_id := str(task.get("id", ""))
		var state := str(task.get("status", "pending"))
		_add_task_line(task_card, str(task.get("title", "Task")), _employee_name(str(task.get("assignee_id", ""))), state.to_upper(), _status_color(state))
		var criteria := str(task.get("acceptance_criteria", ""))
		if not criteria.is_empty(): task_card.add_child(_label("Acceptance: " + criteria, 10, MUTED))
		var evidence: Variant = task.get("evidence", [])
		if evidence is Array:
			for item in evidence:
				task_card.add_child(_label("Evidence · " + str(item.get("evidence_type", "note")) + ": " + str(item.get("reference", "")), 10, BLUE))
		var actions := HBoxContainer.new()
		actions.add_theme_constant_override("separation", 6)
		match state:
			"pending":
				actions.add_child(_button("MULAI", func(): _request_task_transition(task_id, "in_progress"), "secondary"))
				actions.add_child(_button("BATALKAN", func(): _request_task_transition(task_id, "cancelled"), "quiet"))
			"in_progress":
				actions.add_child(_button("LENGKAPI DENGAN BUKTI", func(): _open_task_evidence_dialog(task_id), "primary"))
				actions.add_child(_button("BLOKIR", func(): _request_task_transition(task_id, "blocked", "Diblokir oleh Owner."), "danger"))
			"blocked":
				actions.add_child(_button("LANJUTKAN", func(): _request_task_transition(task_id, "in_progress", "Hambatan telah ditangani."), "secondary"))
				actions.add_child(_button("BATALKAN", func(): _request_task_transition(task_id, "cancelled"), "quiet"))
			"failed":
				actions.add_child(_button("KEMBALIKAN KE PENDING", func(): _request_task_transition(task_id, "pending", "Owner meminta percobaan ulang."), "secondary"))
		if actions.get_child_count() > 0:
			task_card.add_child(actions)

func _request_task_transition(task_id: String, target: String, note: String = "") -> void:
	company_action_requested.emit("task_transition", {"task_id":task_id, "status":target, "note":note, "evidence":[]})

func _open_task_evidence_dialog(task_id: String) -> void:
	var dialog := ConfirmationDialog.new()
	dialog.title = "Bukti penyelesaian task"
	dialog.ok_button_text = "KIRIM HASIL"
	dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new()
	form.add_theme_constant_override("separation", 8)
	dialog.add_child(form)
	form.add_child(_label("Penyelesaian membutuhkan referensi bukti, misalnya URL pull request, commit, hasil build, laporan QA, atau catatan verifikasi.", 11, MUTED))
	var evidence_type := LineEdit.new(); evidence_type.text = "owner_note"; evidence_type.placeholder_text = "Jenis bukti"; form.add_child(evidence_type)
	var reference := LineEdit.new(); reference.placeholder_text = "URL / commit hash / referensi hasil"; form.add_child(reference)
	var note := TextEdit.new(); note.placeholder_text = "Ringkasan hasil dan acceptance criteria yang terpenuhi"; note.custom_minimum_size = Vector2(430, 100); form.add_child(note)
	dialog.confirmed.connect(func():
		if reference.text.strip_edges().is_empty():
			_demo_action("Referensi bukti wajib diisi.")
			return
		company_action_requested.emit("task_transition", {"task_id":task_id, "status":"completed", "note":note.text,
			"evidence":[{"type":evidence_type.text.strip_edges(), "reference":reference.text.strip_edges(), "note":note.text}]})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog)
	_style_form(form)
	add_child(dialog)
	dialog.popup_centered(Vector2i(590, 370))

func _render_team() -> void:
	_page_intro("Status, departemen dan task aktif dari roster backend.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Roster tidak tersedia dalam mode lokal.", AMBER); return
	var employees := _company_rows("employees")
	var departments := _company_rows("departments")
	for department in departments:
		var department_id := str(department.get("id", ""))
		var card := _section_card(content_box, str(department.get("name", department_id)).to_upper(), str(department.get("description", "")))
		var count := 0
		for employee in employees:
			if str(employee.get("department_id", "")) == department_id:
				_add_team_row(card, employee)
				count += 1
		if count == 0: card.add_child(_label("Belum ada karyawan AI terdaftar di departemen ini.", 11, MUTED))

func _render_documents() -> void:
	_page_intro("Paper, approval dan hasil cetak yang tersimpan di database perusahaan.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Kotak masuk dan persetujuan hanya dapat dibuka ketika backend tersambung.", AMBER); return
	var papers := _company_rows("papers")
	if selected_paper_id.is_empty() and not papers.is_empty():
		selected_paper_id = str(papers[0].get("id", ""))
	var approvals := _company_rows("approvals")
	var split := HBoxContainer.new()
	split.add_theme_constant_override("separation", 14)
	content_box.add_child(split)
	var list_card := _section_card(split, "PAPER TRAY", "Dokumen terbaru")
	list_card.custom_minimum_size.x = 350
	list_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list_card.add_child(_button("BUAT PAPER  +", Callable(self, "_open_paper_dialog"), "secondary"))
	if papers.is_empty(): list_card.add_child(_label("Tray masih kosong.", 11, MUTED))
	for paper in papers:
		var selected := str(paper.get("id", "")) == selected_paper_id
		var button := _button(str(paper.get("title", "Paper")) + "\n" + str(paper.get("origin", "Owner")) + " · " + str(paper.get("status", "unread")).to_upper(), Callable(self, "_select_paper").bind(str(paper.get("id", ""))), "selected" if selected else "nav")
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size = Vector2(0, 72)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		# Hover feedback for paper buttons.
		button.mouse_entered.connect(func():
			var t := create_tween()
			t.tween_property(button, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		)
		button.mouse_exited.connect(func():
			var t := create_tween()
			t.tween_property(button, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		)
		list_card.add_child(button)
	var detail := _paper_by_id(selected_paper_id)
	var detail_card := _section_card(split, "PEMBACA PAPER", str(detail.get("id", "Pilih dokumen")))
	detail_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if detail.is_empty():
		detail_card.add_child(_label("Pilih dokumen dari daftar Paper Tray.", 12, MUTED))
	else:
		detail_card.add_child(_label(str(detail.get("title", "")), 18, TEXT, true))
		detail_card.add_child(_label("Dari: %s\nJenis: %s\nPrioritas: %s\nStatus: %s" % [str(detail.get("origin", "")), str(detail.get("paper_type", "")), str(detail.get("priority", "")), str(detail.get("status", ""))], 11, MUTED))
		detail_card.add_child(_divider())
		detail_card.add_child(_label(str(detail.get("body", "")), 12, TEXT))
		var paper_id := str(detail.get("id", ""))
		var approval_id := str(detail.get("approval_id", ""))
		var actions := GridContainer.new(); actions.columns = 2; detail_card.add_child(actions)
		if str(detail.get("status", "")) == "unread":
			actions.add_child(_button("TANDAI DIBACA", func(): company_action_requested.emit("paper_read", {"paper_id":paper_id}), "secondary"))
		actions.add_child(_button("BUAT PDF", func(): company_action_requested.emit("print_paper", {"paper_id":paper_id}), "primary"))
		if not approval_id.is_empty():
			actions.add_child(_button("SETUJUI", func(): company_action_requested.emit("approve", {"approval_id":approval_id}), "primary"))
			actions.add_child(_button("TOLAK", func(): company_action_requested.emit("reject", {"approval_id":approval_id}), "danger"))
	var approval_card := _section_card(content_box, "PERSETUJUAN", "Payload hash terikat pada permintaan")
	approval_card.add_child(_button("BUAT PERMINTAAN PERSETUJUAN  +", Callable(self, "_open_approval_dialog"), "secondary"))
	if approvals.is_empty(): approval_card.add_child(_label("Belum ada permintaan persetujuan.", 11, MUTED))
	for approval in approvals:
		approval_card.add_child(_label(str(approval.get("summary", "Approval")), 12, TEXT, true))
		approval_card.add_child(_label("%s · %s · SHA256 %s" % [str(approval.get("action_type", "")), str(approval.get("status", "")), str(approval.get("payload_sha256", "")).left(16)], 10, MUTED))
		var approved_payload: Variant = approval.get("payload", {})
		if approved_payload is Dictionary:
			approval_card.add_child(_label("PAYLOAD YANG AKAN DIEKSEKUSI\n" + JSON.stringify(approved_payload, "  "), 10, BLUE))
		if str(approval.get("status", "")) == "pending":
			var approval_id := str(approval.get("id", ""))
			var row := HBoxContainer.new(); approval_card.add_child(row)
			row.add_child(_button("SETUJUI", func(): company_action_requested.emit("approve", {"approval_id":approval_id}), "primary"))
			row.add_child(_button("TOLAK", func(): company_action_requested.emit("reject", {"approval_id":approval_id}), "danger"))
	var outbox_card := _section_card(content_box, "OUTBOX", "Pengiriman baru dapat dimulai setelah approval disetujui")
	var outbox := _company_rows("outbox")
	if outbox.is_empty(): outbox_card.add_child(_label("Belum ada item outbox.", 11, MUTED))
	for item in outbox:
		_add_task_line(outbox_card, str(item.get("summary", item.get("id", "Outbox"))), str(item.get("action_type", "")), str(item.get("status", "")).to_upper(), _status_color(str(item.get("status", ""))))
		if str(item.get("status", "")) in ["queued", "failed"]:
			var outbox_id := str(item.get("id", ""))
			outbox_card.add_child(_button("EKSEKUSI OUTBOX YANG DISETUJUI", func(): company_action_requested.emit("execute_outbox", {"outbox_id":outbox_id}), "primary"))
		elif str(item.get("status", "")) == "awaiting_executor":
			outbox_card.add_child(_label("Memerlukan proses manual di luar aplikasi. Sistem tidak menandainya selesai secara otomatis.", 10, AMBER))

func _open_approval_dialog() -> void:
	var dialog := ConfirmationDialog.new(); dialog.title = "Buat permintaan approval"; dialog.ok_button_text = "KIRIM UNTUK DITINJAU"; dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new(); form.add_theme_constant_override("separation", 8); dialog.add_child(form)
	var kind := OptionButton.new()
	kind.add_item("Email keluar · email.send", 0)
	kind.add_item("Website deployment · website.deploy", 1)
	kind.add_item("Pengeluaran · expense.purchase", 2)
	form.add_child(kind)
	var summary := LineEdit.new(); summary.placeholder_text = "Ringkasan aksi dan alasan"; form.add_child(summary)
	var payload := TextEdit.new(); payload.custom_minimum_size = Vector2(460, 170)
	payload.text = "{\n  \"to\": \"recipient@example.com\",\n  \"subject\": \"Subject\",\n  \"body\": \"Message\"\n}"
	form.add_child(payload)
	kind.item_selected.connect(func(index: int):
		if index == 0: payload.text = "{\n  \"to\": \"recipient@example.com\",\n  \"subject\": \"Subject\",\n  \"body\": \"Message\"\n}"
		elif index == 1: payload.text = "{\n  \"repository\": \"https://example.com/org/repository.git\",\n  \"ref\": \"main\",\n  \"target\": \"staging\"\n}"
		else: payload.text = "{\n  \"vendor\": \"Vendor\",\n  \"amount\": 100000,\n  \"currency\": \"IDR\"\n}"
	)
	dialog.confirmed.connect(func():
		var parsed: Variant = JSON.parse_string(payload.text)
		if summary.text.strip_edges().is_empty() or not parsed is Dictionary:
			_demo_action("Ringkasan wajib diisi dan payload harus berupa JSON object."); return
		var action_types := ["email.send", "website.deploy", "expense.purchase"]
		company_action_requested.emit("create_approval", {"action_type":action_types[kind.selected], "summary":summary.text, "payload":parsed})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog); _style_form(form)
	add_child(dialog); dialog.popup_centered(Vector2i(600, 430))

func _paper_by_id(paper_id: String) -> Dictionary:
	for paper in _company_rows("papers"):
		if str(paper.get("id", "")) == paper_id: return paper
	return {}

func _open_paper_dialog() -> void:
	var dialog := ConfirmationDialog.new(); dialog.title = "Buat dokumen Paper"; dialog.ok_button_text = "SIMPAN"; dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new(); form.add_theme_constant_override("separation", 8); dialog.add_child(form)
	var title_input := LineEdit.new(); title_input.placeholder_text = "Judul dokumen"; form.add_child(title_input)
	var body_input := TextEdit.new(); body_input.placeholder_text = "Isi dokumen"; body_input.custom_minimum_size = Vector2(430, 150); form.add_child(body_input)
	dialog.confirmed.connect(func():
		if title_input.text.strip_edges().is_empty() or body_input.text.strip_edges().is_empty(): _demo_action("Judul dan isi Paper wajib diisi."); return
		company_action_requested.emit("create_paper", {"title":title_input.text, "body":body_input.text, "paper_type":"memo", "origin":"Owner"})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog); _style_form(form)
	add_child(dialog); dialog.popup_centered(Vector2i(560, 400))

func _render_meetings() -> void:
	_page_intro("Agenda, peserta, notulen, keputusan dan tindak lanjut rapat persisten.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Rapat tidak dapat dibuat atau diperbarui.", AMBER); return
	var meetings := _company_rows("meetings")
	var card := _section_card(content_box, "AGENDA RAPAT", "Meeting records")
	card.add_child(_button("JADWALKAN RAPAT  +", Callable(self, "_open_meeting_dialog"), "primary"))
	if meetings.is_empty(): card.add_child(_label("Belum ada agenda rapat.", 12, MUTED))
	for meeting in meetings:
		var attendees: Array = meeting.get("attendee_ids", [])
		var names: Array[String] = []
		for id in attendees: names.append(_employee_name(str(id)))
		_add_meeting(card, str(meeting.get("created_at", "")), str(meeting.get("title", "Meeting")), ", ".join(names), str(meeting.get("room_id", "meeting")), _status_color(str(meeting.get("status", ""))), str(meeting.get("status", "scheduled")))
		card.add_child(_label("STATUS · " + str(meeting.get("status", "")).to_upper() + "  |  " + str(meeting.get("agenda", "")), 10, MUTED))
		if not str(meeting.get("minutes", "")).is_empty(): card.add_child(_label("NOTULEN · " + str(meeting.get("minutes", "")), 11, TEXT))
		var meeting_id := str(meeting.get("id", ""))
		var state := str(meeting.get("status", ""))
		if state == "scheduled":
			card.add_child(_button("MULAI RAPAT", func(): company_action_requested.emit("meeting_start", {"meeting_id":meeting_id}), "secondary"))
			card.add_child(_button("BATALKAN AGENDA", func(): company_action_requested.emit("meeting_cancel", {"meeting_id":meeting_id}), "quiet"))
		elif state == "in_progress":
			card.add_child(_button("SELESAIKAN & SIMPAN NOTULEN", func(): _open_meeting_minutes_dialog(meeting_id), "primary"))
			card.add_child(_button("BATALKAN RAPAT", func(): company_action_requested.emit("meeting_cancel", {"meeting_id":meeting_id}), "danger"))
		card.add_child(_divider())

func _open_meeting_dialog() -> void:
	var dialog := ConfirmationDialog.new(); dialog.title = "Jadwalkan rapat"; dialog.ok_button_text = "BUAT AGENDA"; dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new(); form.add_theme_constant_override("separation", 8); dialog.add_child(form)
	var title_input := LineEdit.new(); title_input.placeholder_text = "Judul rapat"; form.add_child(title_input)
	var agenda_input := TextEdit.new(); agenda_input.placeholder_text = "Agenda dan tujuan rapat"; agenda_input.custom_minimum_size = Vector2(430, 110); form.add_child(agenda_input)
	dialog.confirmed.connect(func():
		if title_input.text.strip_edges().is_empty(): _demo_action("Judul rapat wajib diisi."); return
		company_action_requested.emit("create_meeting", {"title":title_input.text, "agenda":agenda_input.text,
			"attendee_ids":["lead", "coo", "architect", "backend", "api", "frontend", "qa"], "room_id":"meeting"})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog); _style_form(form)
	add_child(dialog); dialog.popup_centered(Vector2i(560, 340))

func _open_meeting_minutes_dialog(meeting_id: String) -> void:
	var dialog := ConfirmationDialog.new(); dialog.title = "Notulen dan keputusan rapat"; dialog.ok_button_text = "SELESAIKAN RAPAT"; dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new(); form.add_theme_constant_override("separation", 7); dialog.add_child(form)
	var minutes_input := TextEdit.new(); minutes_input.placeholder_text = "Ringkasan pembahasan rapat"; minutes_input.custom_minimum_size = Vector2(460, 125); form.add_child(minutes_input)
	var decisions_input := TextEdit.new(); decisions_input.placeholder_text = "Keputusan, satu per baris"; decisions_input.custom_minimum_size = Vector2(460, 70); form.add_child(decisions_input)
	var followups_input := TextEdit.new(); followups_input.placeholder_text = "Tindak lanjut, satu per baris"; followups_input.custom_minimum_size = Vector2(460, 70); form.add_child(followups_input)
	dialog.confirmed.connect(func():
		if minutes_input.text.strip_edges().is_empty(): _demo_action("Notulen wajib diisi."); return
		company_action_requested.emit("meeting_complete", {"meeting_id":meeting_id, "minutes":minutes_input.text,
			"decisions":_lines_to_array(decisions_input.text), "followups":_lines_to_array(followups_input.text)})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog); _style_form(form)
	add_child(dialog); dialog.popup_centered(Vector2i(590, 470))

func _lines_to_array(value: String) -> Array[String]:
	var result: Array[String] = []
	for line in value.split("\n", false):
		var item := line.strip_edges()
		if not item.is_empty(): result.append(item)
	return result

func _render_secretary() -> void:
	_page_intro("Jalur koordinasi Owner ke Lead Manager Bangkah.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Hubungkan backend untuk mengirim instruksi perusahaan.", AMBER); return
	var card := _section_card(content_box, "KOORDINASI INSTRUKSI", "Instruksi diteruskan ke Orchestrator melalui Arman")
	card.add_child(_label("Gunakan ruang diskusi Arman untuk merencanakan pekerjaan, meminta laporan, membuat task, dan mengarahkan tim. Aksi eksternal tetap membutuhkan approval Owner.", 12, TEXT))
	card.add_child(_button("BUKA DISKUSI DENGAN ARMAN", func(): employee_chat_requested.emit("lead"), "primary"))
	var pending := _company_rows("approvals")
	var count := 0
	for approval in pending:
		if str(approval.get("status", "")) == "pending": count += 1
	card.add_child(_label("Approval menunggu keputusan: %d" % count, 11, MUTED))

func _render_archive() -> void:
	_page_intro("Dokumen knowledge base yang tersimpan dan diindeks backend.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Arsip tidak tersedia dalam mode lokal.", AMBER); return
	var card := _section_card(content_box, "KNOWLEDGE BASE", "Index dokumen perusahaan")
	var docs: Variant = _company_data().get("knowledge_documents", [])
	if docs is Array and not docs.is_empty():
		for doc in docs:
			_add_task_line(card, str(doc.get("title", "Dokumen")), str(doc.get("source", "")), "%s CHUNKS" % str(doc.get("chunks", 0)), ACCENT)
	else:
		card.add_child(_label("Belum ada dokumen terindeks.", 12, MUTED))
	var prints := _company_rows("print_jobs")
	var print_card := _section_card(content_box, "RIWAYAT CETAK", "Print job dan PDF")
	if prints.is_empty(): print_card.add_child(_label("Belum ada dokumen dicetak.", 11, MUTED))
	for job in prints:
		_add_task_line(print_card, str(job.get("id", "Print job")), str(job.get("paper_id", "")), str(job.get("status", "")).to_upper(), _status_color(str(job.get("status", ""))))
		if str(job.get("status", "")) == "completed":
			var job_id := str(job.get("id", ""))
			print_card.add_child(_button("SIMPAN PDF KE KOMPUTER", func(): company_action_requested.emit("download_print_job", {"print_job_id":job_id}), "secondary"))

func _render_overview() -> void:
	_page_intro("Ringkasan kesehatan perusahaan, status tim dan aktivitas terkini.")
	if not connection_online:
		_add_notice(content_box, "BACKEND OFFLINE", "Hubungkan backend untuk melihat data operasional.", AMBER)
		return
	var company := _company_data()
	var employees := _company_rows("employees")
	var tasks := _company_rows("tasks")
	var meetings := _company_rows("meetings")
	var completed := 0
	var pending := 0
	var in_progress := 0
	for task in tasks:
		var status := str(task.get("status", "pending"))
		if status == "completed":
			completed += 1
		elif status == "in_progress":
			in_progress += 1
		else:
			pending += 1
	var health_card := _section_card(content_box, "KESEHATAN PERUSAHAAN", "Status otomatis dari backend AI Office")
	var grid := GridContainer.new()
	grid.columns = 4
	health_card.add_child(grid)
	_add_stat(grid, "KARYAWAN", str(employees.size()), "TIM", ACCENT)
	_add_stat(grid, "TASK", str(tasks.size()), "PENDING %d" % pending, AMBER)
	_add_stat(grid, "SELESAI", str(completed), "DONE", ACCENT)
	_add_stat(grid, "RAPAT", str(meetings.size()), "SCHEDULED", BLUE)
	var pending_approvals := 0
	for approval in _company_rows("approvals"):
		if str(approval.get("status", "")) == "pending":
			pending_approvals += 1
	var unread_papers := 0
	for paper in _company_rows("papers"):
		if str(paper.get("status", "")) == "unread":
			unread_papers += 1
	var blocked_tasks := 0
	for task in tasks:
		if str(task.get("status", "")) in ["blocked", "failed"]:
			blocked_tasks += 1
	var attention := _section_card(content_box, "PERLU PERHATIAN", "Tindakan Owner yang belum selesai")
	if pending_approvals + unread_papers + blocked_tasks == 0:
		attention.add_child(_empty_state("Tidak ada tindakan mendesak. Semua antrean bersih."))
	else:
		if pending_approvals > 0:
			_add_attention_row(attention, "PERSETUJUAN", "%d permintaan menunggu keputusan" % pending_approvals, "documents", AMBER)
		if unread_papers > 0:
			_add_attention_row(attention, "KOTAK MASUK", "%d paper belum dibaca" % unread_papers, "documents", BLUE)
		if blocked_tasks > 0:
			_add_attention_row(attention, "TASK TERHAMBAT", "%d task perlu ditinjau" % blocked_tasks, "projects", RED)
	var activity_card := _section_card(content_box, "AKTIVITAS TERKINI", "Event dari backend")
	var events: Variant = company.get("events", [])
	if events is Array and not events.is_empty():
		for event in events:
			if event is Dictionary:
				_add_activity(activity_card, str(event.get("actor", "system")), str(event.get("detail", "")), str(event.get("created_at", "")), ACCENT)
	else:
		activity_card.add_child(_empty_state("Belum ada aktivitas tercatat."))

func _short_timestamp(value: String) -> String:
	if value.is_empty():
		return ""
	var cleaned := value.strip_edges()
	if cleaned.length() >= 16 and cleaned[10] == "T":
		var date_part := cleaned.left(10)
		var time_part := cleaned.substr(11, 5)
		return "%s/%s · %s" % [date_part.substr(8, 2), date_part.substr(5, 2), time_part]
	if cleaned.length() > 16:
		cleaned = cleaned.left(16)
	return cleaned.replace("T", " ").replace("-", "/")

func _render_settings() -> void:
	_page_intro("Konfigurasi koneksi, sesi Owner, dan preferensi antarmuka.")
	_add_notice(content_box, "KEAMANAN KONEKSI", "API lokal default hanya terikat ke loopback. Untuk server remote, aktifkan BANGKAH_API_TOKEN dan gunakan HTTPS melalui reverse proxy. Token yang dimasukkan di sini hanya disimpan dalam memori sesi game.", AMBER)
	var card := _section_card(content_box, "KONEKSI BACKEND", "Konfigurasi server AI Office")
	card.add_child(_label("Alamat backend", 11, MUTED))
	backend_url_input = LineEdit.new()
	backend_url_input.text = current_server_url
	backend_url_input.custom_minimum_size.y = 40
	card.add_child(backend_url_input)
	card.add_child(_label("API token (opsional untuk loopback)", 11, MUTED))
	api_token_input = LineEdit.new()
	api_token_input.placeholder_text = "Bearer token dari konfigurasi backend"
	api_token_input.secret = true
	api_token_input.custom_minimum_size.y = 40
	card.add_child(api_token_input)
	card.add_child(_button("SAMBUNG KE BACKEND", Callable(self, "_request_backend_connection"), "primary"))
	card.add_child(_label("Token tidak ditulis ke file konfigurasi dan hilang ketika game ditutup.", 11, MUTED))
	_style_form(card)
	var preferences := _section_card(content_box, "ANTARMUKA", "Preferensi Owner")
	_add_task_line(preferences, "Bahasa", "Indonesia", "DEFAULT", ACCENT)
	_add_task_line(preferences, "Resolusi dasar", "1600 × 900", "DEFAULT", ACCENT)
	_add_task_line(preferences, "Notifikasi persetujuan", "Lencana HUD pasif", "DEFAULT", ACCENT)
	var shortcuts := _section_card(content_box, "PINTASAN", "Navigasi cepat Command Center")
	_add_task_line(shortcuts, "Ringkasan perusahaan", "F1 / 1", "BUKA", ACCENT)
	_add_task_line(shortcuts, "Kotak masuk Owner", "F2 / 4", "BUKA", ACCENT)
	_add_task_line(shortcuts, "Proyek & tugas", "F3 / 2", "BUKA", ACCENT)
	_add_task_line(shortcuts, "Karyawan & tim", "F4 / 3", "BUKA", ACCENT)
	_add_task_line(shortcuts, "Tutup panel", "ESC", "TUTUP", MUTED)

func _page_intro(subtitle: String) -> void:
	_last_page_intro = subtitle
	content_box.add_child(_label(subtitle, 13, MUTED))

func _add_notice(parent: Control, heading: String, body: String, tone: Color) -> void:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _style(Color("#252a21"), Color("#66543a"), 10, 1))
	parent.add_child(card)
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 13)
	margin.add_theme_constant_override("margin_right", 13)
	margin.add_theme_constant_override("margin_top", 10)
	margin.add_theme_constant_override("margin_bottom", 10)
	card.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 3)
	margin.add_child(box)
	box.add_child(_label(heading, 11, tone, true))
	box.add_child(_label(body, 12, TEXT))
	# Hover feedback for notice cards.
	card.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 0.88, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	card.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_stat(parent: GridContainer, title: String, value: String, note: String, tone: Color) -> void:
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(150, 104)
	card.add_theme_stylebox_override("panel", _style(SURFACE_ELEVATED, BORDER, 11, 1))
	parent.add_child(card)
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 13)
	margin.add_theme_constant_override("margin_right", 13)
	margin.add_theme_constant_override("margin_top", 10)
	margin.add_theme_constant_override("margin_bottom", 10)
	card.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	margin.add_child(box)
	box.add_child(_label(title, 10, MUTED, true))
	box.add_child(_label(value, 27, tone, true))
	box.add_child(_label(note, 11, MUTED))
	# Hover lift for stat cards.
	card.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 0.88, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	card.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_attention_row(parent: VBoxContainer, title: String, detail: String, page_id: String, tone: Color) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var dot := _label("●", 10, tone, true)
	dot.custom_minimum_size.x = 16
	dot.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(dot)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(_label(title, 11, tone, true))
	info.add_child(_label(detail, 11, MUTED))
	row.add_child(info)
	var open_button := _button("BUKA", func(): open_panel(page_id), "quiet")
	open_button.custom_minimum_size = Vector2(76, 32)
	row.add_child(open_button)
	parent.add_child(row)
	# Hover feedback for attention row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _empty_state(text_value: String) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _style(SURFACE, BORDER_SUBTLE, 9, 1))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	row.add_child(_label("—", 14, MUTED, true))
	var text_label := _label(text_value, 11, MUTED)
	text_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(text_label)
	panel.add_child(row)
	# Subtle hover lift for empty state.
	panel.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(panel, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	panel.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(panel, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	return panel

func _section_card(parent: Control, title: String, subtitle: String = "") -> VBoxContainer:
	var card := PanelContainer.new()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.add_theme_stylebox_override("panel", _style(SURFACE_ALT, BORDER, 12, 1))
	parent.add_child(card)
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 15)
	margin.add_theme_constant_override("margin_right", 15)
	margin.add_theme_constant_override("margin_top", 13)
	margin.add_theme_constant_override("margin_bottom", 13)
	card.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	margin.add_child(box)
	box.add_child(_label(title, 12, ACCENT, true))
	if not subtitle.is_empty():
		box.add_child(_label(subtitle, 11, MUTED))
	box.add_child(_divider())
	# Hover lift feedback for cards.
	card.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 0.92, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	card.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(card, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	return box

func _add_project_entry(parent: VBoxContainer, title: String, owner: String, status: String, progress: float, description: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	parent.add_child(row)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(_label(title, 14, TEXT, true))
	info.add_child(_label(owner + " · " + description, 11, MUTED))
	if progress > 0.0:
		info.add_child(_progress(progress))
	row.add_child(info)
	row.add_child(_pill(status, ACCENT if status == "IN_PROGRESS" else AMBER))
	parent.add_child(_divider())
	# Hover feedback for project row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_team_row(parent: VBoxContainer, employee: Dictionary) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	var avatar := PanelContainer.new()
	avatar.custom_minimum_size = Vector2(40, 40)
	avatar.add_theme_stylebox_override("panel", _style(ACCENT_DARK, BORDER, 20, 1))
	row.add_child(avatar)
	var employee_name := str(employee.get("name", employee.get("id", "Employee")))
	var initials := _label(_initials(employee_name), 12, ACCENT, true)
	initials.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	initials.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	avatar.add_child(initials)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(_label(employee_name, 13, TEXT, true))
	info.add_child(_label(str(employee.get("role", "Team Member")) + " · " + str(employee.get("department_name", employee.get("department_id", ""))), 11, MUTED))
	var active_task: Variant = employee.get("active_task", {})
	if active_task is Dictionary and not active_task.is_empty():
		info.add_child(_label("Task · " + str(active_task.get("title", "")), 11, MUTED))
	else:
		info.add_child(_label("Tidak ada task aktif.", 11, MUTED))
	row.add_child(info)
	var status := str(employee.get("status", "idle"))
	row.add_child(_pill(status.to_upper(), _status_color(status)))
	var employee_id := str(employee.get("id", ""))
	if not employee_id.is_empty():
		var chat := _button("CHAT", Callable(self, "_request_chat").bind(employee_id), "quiet")
		chat.custom_minimum_size.x = 62
		row.add_child(chat)
	parent.add_child(row)
	parent.add_child(_divider())
	# Hover feedback for team row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_person_line(parent: VBoxContainer, employee: Dictionary) -> void:
	var row := HBoxContainer.new()
	var name := _label(str(employee.get("name", employee.get("id", "Employee"))), 12, TEXT, true)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name)
	var status := str(employee.get("status", "idle"))
	row.add_child(_pill(status.to_upper(), _status_color(status)))
	parent.add_child(row)
	# Hover feedback for person line.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_task_line(parent: VBoxContainer, title: String, owner: String, status: String, tone: Color) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var name := _label(title, 12, TEXT, true)
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name)
	row.add_child(_label(owner, 11, MUTED, false, false))
	row.add_child(_pill(status, tone))
	parent.add_child(row)
	# Hover feedback for task row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_activity(parent: VBoxContainer, person: String, action: String, time: String, tone: Color) -> void:
	var row := HBoxContainer.new()
	var dot := _label("●", 12, tone, true)
	dot.custom_minimum_size.x = 15
	row.add_child(dot)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(_label(person + "  ·  " + action, 12, TEXT))
	row.add_child(info)
	row.add_child(_label(_short_timestamp(time).replace("\n", "  "), 10, MUTED, false, false))
	parent.add_child(row)
	# Hover feedback for activity row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _add_meeting(parent: VBoxContainer, time: String, title: String, participants: String, room: String, tone: Color, status: String = "SCHEDULED") -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	var time_box := PanelContainer.new()
	time_box.custom_minimum_size = Vector2(78, 48)
	time_box.add_theme_stylebox_override("panel", _style(SURFACE, BORDER, 8, 1))
	row.add_child(time_box)
	var time_label := _label(_short_timestamp(time), 11, tone, true, false)
	time_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	time_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	time_box.add_child(time_label)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(_label(title, 13, TEXT, true))
	info.add_child(_label(participants, 11, MUTED))
	info.add_child(_label(room, 11, MUTED))
	row.add_child(info)
	row.add_child(_pill(status.to_upper(), tone))
	parent.add_child(row)
	parent.add_child(_divider())
	# Hover feedback for meeting row.
	row.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 0.85, 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	row.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(row, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _progress(value: float) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size.y = 8
	bar.max_value = 1.0
	bar.value = value
	bar.show_percentage = false
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color("#34423b")
	bg.set_corner_radius_all(6)
	bar.add_theme_stylebox_override("background", bg)
	var fill := StyleBoxFlat.new()
	fill.bg_color = ACCENT
	fill.set_corner_radius_all(6)
	bar.add_theme_stylebox_override("fill", fill)
	return bar

func _pill(text_value: String, foreground: Color) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	panel.add_theme_stylebox_override("panel", _style(foreground.darkened(0.72), foreground.darkened(0.45), 7, 1))
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 3)
	margin.add_theme_constant_override("margin_bottom", 3)
	panel.add_child(margin)
	var label := _label(text_value, 10, foreground.lightened(0.12), true, false)
	margin.add_child(label)
	return panel

func _button(text_value: String, callback: Callable, kind: String = "secondary") -> Button:
	var button := Button.new()
	button.text = text_value
	_apply_button_theme(button, kind)
	if callback.is_valid():
		button.pressed.connect(callback)
	return button

func _apply_button_theme(button: Button, kind: String = "secondary") -> void:
	button.focus_mode = Control.FOCUS_ALL
	button.custom_minimum_size = Vector2(0, 38)
	button.add_theme_font_size_override("font_size", 11)
	button.add_theme_color_override("font_color", TEXT)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	var normal := SURFACE_ALT if kind in ["secondary", "quiet", "nav"] else ACCENT_DARK
	var border := BORDER
	if kind == "primary":
		normal = ACCENT_DARK
		border = Color("#52775a")
	elif kind == "danger":
		normal = Color("#472d2a")
		border = Color("#78433d")
	elif kind == "selected":
		normal = Color("#2b4134")
		border = Color("#66856b")
	elif kind in ["quiet", "nav"]:
		border = normal
	var hover_bg: Color = normal.lightened(0.1)
	var hover_border: Color = border.lightened(0.2)
	var pressed_bg: Color = normal.darkened(0.12)
	var pressed_border: Color = border.lightened(0.3)
	button.add_theme_stylebox_override("normal", _style(normal, border, 8, 1))
	button.add_theme_stylebox_override("hover", _style(hover_bg, hover_border, 8, 1))
	button.add_theme_stylebox_override("pressed", _style(pressed_bg, pressed_border, 8, 1))
	button.add_theme_stylebox_override("disabled", _style(normal.darkened(0.2), border.darkened(0.2), 8, 1))
	var focus_style := _style(Color(0, 0, 0, 0), FOCUS_BORDER, 8, 2)
	focus_style.draw_center = false
	button.add_theme_stylebox_override("focus", focus_style)
	# Tactile hover feedback for launcher/primary buttons.
	if kind in ["primary", "secondary"]:
		button.mouse_entered.connect(func():
			var t := create_tween()
			t.tween_property(button, "scale", Vector2(1.015, 1.015), 0.08).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		)
		button.mouse_exited.connect(func():
			var t := create_tween()
			t.tween_property(button, "scale", Vector2(1.0, 1.0), 0.1).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		)

func _label(text_value: String, size: int = 12, color: Color = TEXT, bold: bool = false, wrap: bool = true) -> Label:
	var label := Label.new()
	label.text = text_value
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	if bold:
		label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.25))
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if wrap else TextServer.AUTOWRAP_OFF
	return label

func _panel(parent: Control, position: Vector2, minimum_size: Vector2, background: Color, border: Color, radius: int) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = position
	panel.custom_minimum_size = minimum_size
	panel.size = minimum_size
	panel.add_theme_stylebox_override("panel", _style(background, border, radius, 1))
	parent.add_child(panel)
	return panel

func _style(background: Color, border: Color, radius: int, border_width: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(border_width)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 7
	style.content_margin_bottom = 7
	return style

func _divider() -> ColorRect:
	var divider := ColorRect.new()
	divider.color = BORDER_SUBTLE
	divider.custom_minimum_size = Vector2(0, 1)
	return divider

func _style_dialog(dialog: AcceptDialog) -> void:
	dialog.add_theme_stylebox_override("panel", _style(SURFACE, BORDER, 12, 1))
	dialog.add_theme_color_override("font_color", TEXT)
	var ok_button: Button = dialog.get_ok_button()
	if ok_button != null:
		_apply_button_theme(ok_button, "primary")
	var cancel_button: Button = dialog.get_cancel_button()
	if cancel_button != null:
		_apply_button_theme(cancel_button, "secondary")

func _style_form(node: Node) -> void:
	for child in node.get_children():
		if child is Control:
			_style_input(child as Control)
		_style_form(child)

func _style_input(control: Control) -> void:
	if control is LineEdit:
		var line := control as LineEdit
		line.custom_minimum_size.y = 38
		line.add_theme_font_size_override("font_size", 12)
		line.add_theme_color_override("font_color", TEXT)
		line.add_theme_color_override("font_placeholder_color", MUTED)
		line.add_theme_color_override("caret_color", ACCENT)
		line.add_theme_stylebox_override("normal", _style(SURFACE, BORDER, 8, 1))
		line.add_theme_stylebox_override("focus", _style(SURFACE, FOCUS_BORDER, 8, 1))
	elif control is TextEdit:
		var edit := control as TextEdit
		edit.add_theme_font_size_override("font_size", 12)
		edit.add_theme_color_override("font_color", TEXT)
		edit.add_theme_color_override("font_placeholder_color", MUTED)
		edit.add_theme_color_override("caret_color", ACCENT)
		edit.add_theme_stylebox_override("normal", _style(SURFACE, BORDER, 8, 1))
		edit.add_theme_stylebox_override("focus", _style(SURFACE, FOCUS_BORDER, 8, 1))
	elif control is OptionButton:
		var option := control as OptionButton
		option.custom_minimum_size.y = 38
		option.add_theme_font_size_override("font_size", 12)
		option.add_theme_color_override("font_color", TEXT)
		option.add_theme_stylebox_override("normal", _style(SURFACE, BORDER, 8, 1))
		option.add_theme_stylebox_override("hover", _style(SURFACE_ALT, FOCUS_BORDER, 8, 1))
		option.add_theme_stylebox_override("pressed", _style(SURFACE_ALT, FOCUS_BORDER, 8, 1))
		option.add_theme_stylebox_override("focus", _style(SURFACE, FOCUS_BORDER, 8, 1))

func _selected_paper() -> Dictionary:
	return _paper_by_id(selected_paper_id)

func _select_paper(paper_id: String) -> void:
	selected_paper_id = paper_id
	if is_open: _render_page()

func _request_chat(employee_id: String) -> void:
	if employee_id in ["secretary", "reception"]:
		_demo_action("Agen ini belum tersedia pada endpoint chat backend versi saat ini.")
		return
	_set_open(false)
	employee_chat_requested.emit(employee_id)

func set_server_url(url: String) -> void:
	var value := url.strip_edges()
	if not value.is_empty():
		current_server_url = value
	if is_instance_valid(backend_url_input):
		backend_url_input.text = current_server_url

func _request_backend_connection() -> void:
	if not is_instance_valid(backend_url_input):
		return
	var url := backend_url_input.text.strip_edges().trim_suffix("/")
	if not (url.begins_with("http://") or url.begins_with("https://")):
		_demo_action("Alamat backend harus diawali http:// atau https://.")
		return
	current_server_url = url
	connect_backend_requested.emit(url, api_token_input.text.strip_edges() if is_instance_valid(api_token_input) else "")

func _demo_action(message: String) -> void:
	demo_action_requested.emit(message)
	if is_instance_valid(toast_label):
		toast_label.text = message
		toast_label.visible = true
		if is_instance_valid(toast_panel):
			toast_panel.visible = true
			# Slide-in toast animation.
			toast_panel.modulate.a = 0.0
			toast_panel.position.y = 20
			var t := create_tween()
			t.tween_property(toast_panel, "modulate:a", 1.0, 0.2).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
			t.parallel().tween_property(toast_panel, "position:y", 0.0, 0.25).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		if is_instance_valid(toast_timer):
			toast_timer.start()

func _unhandled_input(event: InputEvent) -> void:
	if not (is_open and event is InputEventKey and event.pressed and not event.echo):
		return
	var key_event := event as InputEventKey
	if key_event.keycode == KEY_ESCAPE:
		close_panel()
		get_viewport().set_input_as_handled()
		return
	var focus := get_viewport().gui_get_focus_owner()
	if focus is LineEdit or focus is TextEdit or focus is OptionButton:
		return
	var page := ""
	match key_event.keycode:
		KEY_F1, KEY_1: page = "overview"
		KEY_F2, KEY_4: page = "documents"
		KEY_F3, KEY_2: page = "projects"
		KEY_F4, KEY_3: page = "team"
		KEY_5: page = "meetings"
		KEY_6: page = "secretary"
		KEY_7: page = "archive"
		KEY_8: page = "settings"
	if not page.is_empty():
		open_panel(page)
		get_viewport().set_input_as_handled()

func _initials(full_name: String) -> String:
	var parts := full_name.split(" ", false)
	if parts.is_empty():
		return "?"
	var result := str(parts[0]).left(1)
	if parts.size() > 1:
		result += str(parts[1]).left(1)
	return result.to_upper()

func _open_task_dialog() -> void:
	var dialog := ConfirmationDialog.new()
	dialog.title = "Buat task perusahaan"
	dialog.ok_button_text = "BUAT TASK"
	dialog.dialog_hide_on_ok = false
	var form := VBoxContainer.new()
	form.add_theme_constant_override("separation", 8)
	dialog.add_child(form)
	var title_input := LineEdit.new()
	title_input.placeholder_text = "Judul pekerjaan"
	form.add_child(title_input)
	var description_input := TextEdit.new()
	description_input.placeholder_text = "Deskripsi dan konteks pekerjaan"
	description_input.custom_minimum_size = Vector2(430, 100)
	form.add_child(description_input)
	var acceptance_input := LineEdit.new()
	acceptance_input.placeholder_text = "Acceptance criteria / definisi selesai (opsional)"
	form.add_child(acceptance_input)
	var assignee := OptionButton.new()
	assignee.add_item("Belum ditentukan")
	assignee.set_item_metadata(0, "")
	for employee in _company_rows("employees"):
		assignee.add_item(str(employee.get("name", employee.get("id", ""))))
		assignee.set_item_metadata(assignee.item_count - 1, str(employee.get("id", "")))
	form.add_child(assignee)
	var priority := OptionButton.new()
	for value in ["normal", "low", "high", "urgent"]: priority.add_item(value.to_upper())
	form.add_child(priority)
	dialog.confirmed.connect(func():
		var title := title_input.text.strip_edges()
		if title.is_empty(): _demo_action("Judul task wajib diisi."); return
		company_action_requested.emit("create_task", {"title":title, "description":description_input.text,
			"acceptance_criteria":acceptance_input.text.strip_edges(),
			"assignee_id":assignee.get_item_metadata(assignee.selected), "priority":priority.get_item_text(priority.selected).to_lower()})
		dialog.queue_free()
	)
	dialog.canceled.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
	_style_dialog(dialog)
	_style_form(form)
	add_child(dialog)
	dialog.popup_centered(Vector2i(560, 360))
