extends SceneTree

# Automated headless check for Bangkah Company Simulator v1.1 extensions:
# - Drivable vehicles registration and player enter/exit vehicle mechanics
# - Town District landmarks interactables
# - Dynamic day/night cycle & sky lighting (WLD-07)
# - Coffee drinking & stamina sprint boost (OBJ-03)
# - Bangkah OS terminal commands (status, sysinfo)

var _failures: int = 0

func _check(condition: bool, label: String) -> void:
	if condition:
		print("PASS ", label)
	else:
		_failures += 1
		print("FAIL ", label)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene: PackedScene = load("res://scenes/main.tscn")
	var root_node = scene.instantiate()
	root.add_child(root_node)

	for i in range(30):
		await process_frame

	var player = root_node.player
	var office_world = root_node.get_node_or_null("BangkahHeadquarters")

	# 1. Vehicles registration check
	_check(is_instance_valid(office_world) and office_world.vehicles.size() > 0,
		"HQ and Town have registered vehicles (count: %d)" % (office_world.vehicles.size() if is_instance_valid(office_world) else 0))

	var car_interactables: Array = []
	for item in root_node._interactables:
		if str(item.get("kind", "")) == "vehicle":
			car_interactables.append(item)
	_check(car_interactables.size() >= 8,
		"all parked employee and town cars registered as interactables (found: %d)" % car_interactables.size())

	# 2. Player vehicle entry and exit check
	if car_interactables.size() > 0:
		var car = car_interactables[0]
		var car_node = car.get("node", null)
		_check(is_instance_valid(car_node), "first car node valid")
		player.enter_vehicle(car_node)
		_check(player.is_in_vehicle(), "player successfully entered vehicle")
		_check(player.activity == "driving", "player activity set to driving")
		player.exit_vehicle()
		_check(not player.is_in_vehicle(), "player successfully exited vehicle")
		_check(player.activity == "idle", "player activity returned to idle")

	# 3. Town landmarks interactables check
	var town_landmarks := ["town_mansion", "town_market", "town_mall", "town_kopdes"]
	var found_landmarks := 0
	for item in root_node._interactables:
		if item.get("id", "") in town_landmarks:
			found_landmarks += 1
	_check(found_landmarks == town_landmarks.size(),
		"all 4 Town District landmarks registered (found: %d/4)" % found_landmarks)

	# 4. Coffee drinking and stamina sprint boost check
	root_node._take_coffee()
	_check(root_node._coffee_carried, "taking coffee attaches cup and sets carried state")
	_check(player.activity == "carrying_coffee", "player activity is carrying_coffee")

	root_node._drink_coffee()
	_check(not root_node._coffee_carried, "drinking coffee clears carried state")
	_check(player.sprint_speed > 7.0, "drinking coffee boosts player sprint speed (got: %.1f)" % player.sprint_speed)

	# 5. Day/Night simulation check (WLD-07)
	_check(is_instance_valid(root_node._sun_light), "sun directional light reference valid")
	_check(is_instance_valid(root_node._sky_material), "sky material reference valid")

	# Simulate noon (12:00)
	root_node._day_cycle_time = 12.0
	root_node._update_day_night_cycle(0.1)
	var noon_sun_energy: float = root_node._sun_light.light_energy
	_check(noon_sun_energy >= 1.0, "noon sun light energy high (energy: %.2f)" % noon_sun_energy)

	# Simulate night (23:00)
	root_node._day_cycle_time = 23.0
	root_node._update_day_night_cycle(0.1)
	var night_sun_energy: float = root_node._sun_light.light_energy
	_check(night_sun_energy < 0.5, "night sun drops to moonlight levels (energy: %.2f)" % night_sun_energy)

	# 6. Bangkah OS terminal local command check
	var desktop = root_node._desktop_ui
	_check(is_instance_valid(desktop), "desktop UI initialized")
	desktop.set_offline_mode(true)
	desktop.open_for("OWNER-PC-001", "Owner Workstation", "owner")
	var login := {
		"session_id": "WSS-CHECK",
		"token": "sesi-uji",
		"expires_at": "2026-01-01T00:00:00+00:00",
		"workstation": {"id": "OWNER-PC-001", "label": "Owner Workstation", "room_id": "owner"},
		"account": {"id": "owner", "name": "Owner", "role": "owner"},
		"apps": ["files", "terminal", "infrastructure", "company"],
	}
	desktop._on_login_response(HTTPRequest.RESULT_SUCCESS, 201, login)
	desktop._select_app("terminal")

	desktop._submit_terminal("status")
	_check("Workstation:" in desktop._terminal_log.text, "terminal handles 'status' command")
	desktop._submit_terminal("sysinfo")
	_check("Bangkah OS" in desktop._terminal_log.text, "terminal handles 'sysinfo' command")

	print("RESULT failures=", _failures)
	quit(1 if _failures > 0 else 0)
