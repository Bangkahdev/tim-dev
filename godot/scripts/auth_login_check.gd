extends SceneTree
## Headless end-to-end check for the Godot Owner session login.
##
## Requires a running backend with a known Owner password:
##   BANGKAH_TEST_URL=http://127.0.0.1:<port>
##   BANGKAH_TEST_USER=owner
##   BANGKAH_TEST_PASSWORD=<password>
##
## The check drives the real company_ui login form, verifies the returned
## session token against /api/auth/me, logs out, and verifies the token is
## revoked. It prints AUTH-CHECK: PASS or FAIL and exits accordingly.

var _ui: CanvasLayer
var _connected_token := ""
var _disconnected := false
var _messages: Array[String] = []


func _initialize() -> void:
	var url := OS.get_environment("BANGKAH_TEST_URL").strip_edges()
	var user := OS.get_environment("BANGKAH_TEST_USER").strip_edges()
	var password := OS.get_environment("BANGKAH_TEST_PASSWORD")
	if url.is_empty() or user.is_empty() or password.is_empty():
		_finish("FAIL missing BANGKAH_TEST_URL/USER/PASSWORD")
		return

	_ui = preload("res://scripts/company_ui.gd").new()
	_ui.connect_backend_requested.connect(_on_connect)
	_ui.disconnect_backend_requested.connect(_on_disconnect)
	_ui.demo_action_requested.connect(_on_message)
	root.add_child(_ui)
	await process_frame
	_ui.open_panel("settings")
	# The panel animates its page swap; the settings form is created in the tween
	# callback. Wait for it like a real user would instead of assuming one frame.
	var field_deadline := Time.get_ticks_msec() + 5000
	while (not is_instance_valid(_ui.auth_username_input) or not is_instance_valid(_ui.auth_password_input)) and Time.get_ticks_msec() < field_deadline:
		await create_timer(0.05).timeout

	if not is_instance_valid(_ui.auth_username_input) or not is_instance_valid(_ui.auth_password_input):
		_finish("FAIL settings login fields were not created")
		return
	_ui.backend_url_input.text = url
	_ui.auth_username_input.text = user

	# A wrong password must not connect and must report a failure to the user.
	_ui.auth_password_input.text = password + "-wrong"
	_ui._request_backend_connection()
	var deadline := Time.get_ticks_msec() + 20000
	while not _ui._auth_action.is_empty() and Time.get_ticks_msec() < deadline:
		await create_timer(0.1).timeout
	if not _connected_token.is_empty():
		_finish("FAIL wrong password produced a session")
		return
	if _messages.is_empty():
		_finish("FAIL wrong password produced no user-visible error")
		return

	_ui.auth_password_input.text = password
	_ui._request_backend_connection()

	deadline = Time.get_ticks_msec() + 20000
	while _connected_token.is_empty() and Time.get_ticks_msec() < deadline:
		await create_timer(0.1).timeout
	if _connected_token.is_empty():
		_finish("FAIL login did not return a session token")
		return

	var me_code := await _request_code(url + "/api/auth/me", _connected_token)
	if me_code != 200:
		_finish("FAIL session token rejected by /api/auth/me (HTTP %d)" % me_code)
		return

	_ui._request_logout()
	deadline = Time.get_ticks_msec() + 20000
	while not _disconnected and Time.get_ticks_msec() < deadline:
		await create_timer(0.1).timeout
	if not _disconnected:
		_finish("FAIL logout did not emit disconnect")
		return

	var revoked_code := await _request_code(url + "/api/auth/me", _connected_token)
	if revoked_code != 401:
		_finish("FAIL old session token still accepted after logout (HTTP %d)" % revoked_code)
		return

	_finish("PASS")


func _on_connect(_url: String, token: String) -> void:
	if not token.is_empty():
		_connected_token = token


func _on_disconnect() -> void:
	_disconnected = true


func _on_message(message: String) -> void:
	_messages.append(str(message))


func _request_code(request_url: String, token: String) -> int:
	var http := HTTPRequest.new()
	root.add_child(http)
	var error := http.request(request_url, PackedStringArray(["Authorization: Bearer " + token]))
	if error != OK:
		http.queue_free()
		return -1
	var result: Array = await http.request_completed
	http.queue_free()
	if int(result[0]) != HTTPRequest.RESULT_SUCCESS:
		return -1
	return int(result[1])


func _finish(verdict: String) -> void:
	print("AUTH-CHECK: " + verdict)
	for message in _messages:
		print("AUTH-CHECK-DETAIL: " + message)
	quit(0 if verdict.begins_with("PASS") else 1)
