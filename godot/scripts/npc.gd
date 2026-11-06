extends CharacterBody3D
class_name OfficeNPC

const CHARACTER_FACTORY = preload("res://scripts/character_factory.gd")

@export var employee_id: String = "employee"
@export var display_name: String = "Employee"
@export var job_title: String = "Team Member"
@export var shirt_color: Color = Color("#638a81")
@export var hair_color: Color = Color("#30383a")
@export var gender: String = "male"
@export var wear_hijab: bool = false
@export var skin_color: Color = Color("#c89e84")
@export var body_type: String = "average" # slim | average | stocky | tall | short
@export var is_receptionist: bool = false
@export var home_position: Vector3 = Vector3.ZERO # workstation/desk home (work)

# Backend-owned status. Ambient actions below never promote an idle employee to
# "working"; only an employee record from the backend may do that.
var office_status: String = "idle"
var backend_record_received: bool = false
var room_id: String = "corridor"
var activity_text: String = "Menunggu pekerjaan"
var _visual: Node3D
var _arms: Array = []
var _legs: Array = []
var _eyes: Array = []
var _head_pivot: Node3D
var _labels: Dictionary = {}
var _plans: Array = []
var _route: Array = []
var _route_index: int = 0
var _routine_timer: float = 4.0
var _phase: float = 0.0
var _rng := RandomNumberGenerator.new()
var _is_walking: bool = false
var _ambient_phase: String = "home" # home -> outbound -> at_destination -> returning (+ commute phases)
var _activity_mode: String = "idle"
var _last_ambient_plan: int = -1
var _blink_timer: float = 3.0
var _blink_duration: float = 0.0
var _greeting_lock: float = 0.0
var _avoidance_side: float = 1.0
var _stuck_elapsed: float = 0.0
var _last_waypoint_distance: float = INF
var _meeting_active: bool = false
var _meeting_facing_yaw: float = 0.0
var _meeting_return_route: Array = []
var _external_animation_player: AnimationPlayer
var _external_animation_name: String = ""
var _sitting: bool = false
var _sit_transition: float = 0.0
var _idle_variant: int = 0
var _idle_timer: float = 0.0

@onready var _player: Node3D = get_node_or_null("../Player_Owner")

# Small-town commute: each employee has a residence and may travel between
# house and HQ. Commute is visual only and never fabricates backend work state.
var house_position: Vector3 = Vector3.INF
var commute_to_work: Array = []
var commute_to_home: Array = []
# Town residents/family/citizens: stay in the town (home/market), never join
# office work/meetings/commute, and remain interactable for visits.
@export var is_resident: bool = false
var resident_home: Vector3 = Vector3.INF
var _at_residence: bool = false
var _commuting: bool = false
var _shift_on_duty: bool = true # set from activity_engine/main; default true preserves old behavior
var _commute_cooldown: float = 0.0

func _ready() -> void:
	_rng.randomize()
	add_to_group("office_npcs")
	var collision := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.30
	capsule.height = 2.18
	collision.shape = capsule
	collision.position.y = 1.10
	add_child(collision)

	_visual = Node3D.new()
	_visual.name = "CharacterVisual"
	add_child(_visual)
	var visual_data = CHARACTER_FACTORY.build(_visual, shirt_color, hair_color, display_name, employee_id, skin_color, gender, wear_hijab, body_type, 1)
	_arms = visual_data.get("arms", [])
	_legs = visual_data.get("legs", [])
	_eyes = visual_data.get("eyes", [])
	_head_pivot = visual_data.get("head_pivot")
	_external_animation_player = visual_data.get("animation_player") as AnimationPlayer
	_labels = visual_data
	global_position = home_position + Vector3(0, 0.01, 0)
	_blink_timer = _rng.randf_range(2.0, 5.0)

	if is_receptionist:
		_activity_mode = "typing"
		activity_text = "Front desk Â· mengelola kunjungan"
		_routine_timer = 4.0
	elif is_resident:
		_activity_mode = "idle"
		activity_text = "Beraktivitas di rumah"
		_routine_timer = _rng.randf_range(4.0, 8.0)
	else:
		_activity_mode = "idle"
		activity_text = "Menunggu pekerjaan"
		_routine_timer = _rng.randf_range(4.0, 8.0)
	_update_status_label()

func set_commute(home_pos: Vector3, to_work_route: Array, to_home_route: Array) -> void:
	house_position = home_pos
	commute_to_work = to_work_route.duplicate()
	commute_to_home = to_home_route.duplicate()

func set_shift_on_duty(on_duty: bool) -> void:
	_shift_on_duty = on_duty
	if is_receptionist or is_resident or _meeting_active:
		return
	if not _shift_on_duty and _can_leave_for_home():
		_begin_commute_home()
	elif _shift_on_duty and _at_residence and office_status not in ["talking", "listening"]:
		_begin_commute_to_work()

func _can_leave_for_home() -> bool:
	return not _meeting_active and not _is_walking and not _commuting and not _sitting and office_status in ["idle", "completed"] and not commute_to_home.is_empty()

func is_away_from_office() -> bool:
	return _at_residence or _commuting or (house_position != Vector3.INF and global_position.distance_to(home_position) > 30.0)

func set_ambient_plans(plans: Array) -> void:
	_plans = plans

func apply_employee_record(record: Dictionary) -> void:
	if is_receptionist or is_resident:
		return
	backend_record_received = true
	var previous_status := office_status
	var incoming_status := str(record.get("status", "idle"))
	if _meeting_active and incoming_status not in ["idle", "completed"]:
		# Backend task state wins over a local visual meeting preview. Keep the
		# meeting's corridor waypoints so this employee can return safely.
		end_local_meeting()
		office_status = incoming_status
		_update_status_label()
		return
	# Backend status wins over a visual commute: bring the employee to the
	# office context (they may still be mid-route; route completes to desk).
	if _commuting and incoming_status in ["working", "talking", "listening", "blocked", "failed"]:
		_commuting = false
		_at_residence = false
		office_status = incoming_status
		_update_status_label()
		return
	office_status = incoming_status
	room_id = str(record.get("room_id", room_id))
	if record.has("name"):
		display_name = str(record.get("name", display_name))
		_labels.label.text = display_name
	if record.has("role"):
		job_title = str(record.get("role", job_title))

	if office_status == "working":
		_activity_mode = "typing"
		activity_text = "Bekerja · tugas aktif"
		if _at_residence and not commute_to_work.is_empty():
			_begin_commute_to_work()
		elif previous_status != "working":
			_ambient_phase = "returning"
			if global_position.distance_to(home_position) > 0.55:
				_set_route([home_position])
			else:
				_ambient_phase = "home"
				_clear_route()
	elif office_status == "talking":
		_activity_mode = "talking"
		activity_text = "Berbicara"
		_clear_route()
	elif office_status == "listening":
		_activity_mode = "listening"
		activity_text = "Mendengarkan"
		_clear_route()
	elif office_status == "failed":
		_activity_mode = "concerned"
		activity_text = "Perlu perhatian"
		_clear_route()
	elif office_status == "blocked":
		_activity_mode = "thinking"
		activity_text = "Terhambat"
		_clear_route()
	elif office_status == "completed":
		_activity_mode = "reviewing"
		activity_text = "Tugas selesai"
		if previous_status != "completed":
			_ambient_phase = "home"
			_routine_timer = 2.5
	else:
		_activity_mode = "idle"
		activity_text = "Menunggu instruksi"
		if previous_status != "idle":
			_ambient_phase = "home"
			if global_position.distance_to(home_position) > 0.55 and not _at_residence:
				_ambient_phase = "returning"
				_set_route([home_position])
			else:
				_clear_route()
			_routine_timer = _rng.randf_range(3.0, 6.0)
	_update_status_label()

func set_speech(message: String) -> void:
	if message.is_empty():
		_activity_mode = "idle" if office_status == "idle" else _activity_mode
		activity_text = _default_activity()
	else:
		_activity_mode = "talking"
		activity_text = "Sedang berkomunikasi"
	_update_status_label()

func trigger_greeting() -> void:
	if not is_receptionist:
		return
	_activity_mode = "greeting"
	_greeting_lock = 3.8
	_routine_timer = 3.8
	activity_text = "Menyambut tamu · Welcome to Bangkah"
	_update_status_label()

func _default_activity() -> String:
	if is_receptionist:
		return "Front desk Â· mengelola kunjungan"
	if is_resident:
		return "Di rumah Â· beraktivitas"
	if office_status == "working":
		return "Bekerja Â· tugas aktif"
	if office_status in ["talking", "listening"]:
		return "Berkomunikasi"
	if office_status == "failed":
		return "Perlu perhatian"
	if office_status == "blocked":
		return "Menunggu penyelesaian hambatan"
	if office_status == "completed":
		return "Tugas selesai · menunggu arahan"
	return "Menunggu instruksi"

func _update_status_label() -> void:
	if not _labels.is_empty():
		_labels.status_label.text = activity_text.to_upper()

func _clear_route() -> void:
	_route.clear()
	_route_index = 0
	_is_walking = false
	_stuck_elapsed = 0.0
	_last_waypoint_distance = INF
	velocity.x = 0.0
	velocity.z = 0.0

func _set_route(points: Array) -> void:
	_route.clear()
	for point in points:
		if point is Vector3:
			_route.append(point)
	_route_index = 0
	_stuck_elapsed = 0.0
	_last_waypoint_distance = INF
	_is_walking = not _route.is_empty()
	if _is_walking:
		activity_text = "Berjalan"
		_update_status_label()

func can_join_local_meeting() -> bool:
	return not is_receptionist and not is_resident and not _meeting_active and office_status in ["idle", "completed"] and not _commuting and not _at_residence

func begin_local_meeting(route_points: Array, facing_yaw: float) -> bool:
	if not can_join_local_meeting() or route_points.is_empty():
		return false
	_meeting_active = true
	_meeting_facing_yaw = facing_yaw
	_meeting_return_route.clear()
	for index in range(route_points.size() - 2, -1, -1):
		if route_points[index] is Vector3:
			_meeting_return_route.append(route_points[index])
	_meeting_return_route.append(home_position)
	_ambient_phase = "meeting_approach"
	_activity_mode = "meeting_travel"
	activity_text = "Menuju ruang rapat · simulasi lokal"
	_set_route(route_points)
	activity_text = "Menuju ruang rapat · simulasi lokal"
	_update_status_label()
	return true

func is_local_meeting_seated() -> bool:
	return _meeting_active and _ambient_phase == "meeting_seated"

func set_local_meeting_speaker(is_speaker: bool) -> void:
	if not _meeting_active or _ambient_phase != "meeting_seated":
		return
	_activity_mode = "meeting_speaking" if is_speaker else "meeting_listening"
	activity_text = "Menyampaikan pendapat · rapat lokal" if is_speaker else "Mendengarkan rekan · rapat lokal"
	_update_status_label()

func end_local_meeting() -> void:
	if not _meeting_active:
		return
	_meeting_active = false
	_ambient_phase = "meeting_return"
	_activity_mode = "walking"
	activity_text = "Kembali ke workstation"
	_set_route(_meeting_return_route)
	activity_text = "Kembali ke workstation"
	_update_status_label()

func _begin_commute_to_work() -> void:
	if commute_to_work.is_empty() or _meeting_active or _commuting:
		return
	_at_residence = false
	_commuting = true
	_stand_if_needed()
	_ambient_phase = "commute_to_work"
	_activity_mode = "commute"
	activity_text = "Berangkat ke kantor"
	_set_route(commute_to_work)
	_update_status_label()

func _begin_commute_home() -> void:
	if commute_to_home.is_empty() or _meeting_active or _commuting or not _can_leave_for_home():
		return
	_commuting = true
	_at_residence = false
	_stand_if_needed()
	_ambient_phase = "commute_home"
	_activity_mode = "commute"
	activity_text = "Pulang ke rumah"
	_set_route(commute_to_home)
	_update_status_label()

func _stand_if_needed() -> void:
	if _sitting:
		stand()
	_sit_transition = 0.0

func sit() -> void:
	if _sitting:
		return
	_sitting = true
	_sit_transition = 0.0
	_activity_mode = "sitting"
	activity_text = "Bekerja di meja"
	_update_status_label()

func stand() -> void:
	if not _sitting:
		return
	_sitting = false
	_sit_transition = 0.0
	_activity_mode = "idle"
	activity_text = _default_activity()
	_update_status_label()

func is_sitting() -> bool:
	return _sitting

func _raycast_ahead(direction: Vector3, distance: float) -> Dictionary:
	var origin := global_position + Vector3(0.0, 0.95, 0.0)
	var destination := origin + direction.normalized() * distance
	var query := PhysicsRayQueryParameters3D.create(origin, destination, 1)
	query.exclude = [get_rid()]
	query.collide_with_areas = false
	return get_world_3d().direct_space_state.intersect_ray(query)

func _steer_around_obstacles(desired: Vector3) -> Vector3:
	var direction := desired.normalized()
	if direction.length_squared() < 0.001:
		return Vector3.ZERO
	var separation := Vector3.ZERO
	for other in get_tree().get_nodes_in_group("office_npcs"):
		if other == self or not is_instance_valid(other):
			continue
		var offset: Vector3 = global_position - other.global_position
		offset.y = 0.0
		var distance := offset.length()
		if distance > 0.01 and distance < 0.95:
			separation += offset.normalized() * (0.95 - distance)
	if separation.length_squared() > 0.001:
		direction = (direction + separation.normalized() * 1.15).normalized()

	var hit := _raycast_ahead(direction, 1.05)
	if not hit.is_empty():
		var collider: Object = hit.get("collider")
		var is_other_npc := false
		if collider is Node:
			is_other_npc = (collider as Node).is_in_group("office_npcs")
		if not is_other_npc:
			var side := Vector3(-direction.z, 0.0, direction.x)
			var left_hit := _raycast_ahead((direction + side * 0.75).normalized(), 1.15)
			var right_hit := _raycast_ahead((direction - side * 0.75).normalized(), 1.15)
			if left_hit.is_empty() and not right_hit.is_empty():
				_avoidance_side = 1.0
			elif right_hit.is_empty() and not left_hit.is_empty():
				_avoidance_side = -1.0
			var chosen_side := side * _avoidance_side
			var normal: Vector3 = hit.get("normal", Vector3.ZERO)
			normal.y = 0.0
			var tangent := direction.slide(normal)
			if tangent.length_squared() < 0.04:
				tangent = chosen_side
			direction = (direction * 0.28 + tangent.normalized() * 0.92).normalized()
	return direction

func _update_stuck_recovery(delta: float, target_distance: float) -> void:
	if target_distance >= _last_waypoint_distance - 0.018:
		_stuck_elapsed += delta
	else:
		_stuck_elapsed = 0.0
	if _stuck_elapsed >= 1.15:
		_avoidance_side *= -1.0
		_stuck_elapsed = 0.0
	_last_waypoint_distance = target_distance

func _physics_process(delta: float) -> void:
	_phase += delta
	_commute_cooldown = maxf(0.0, _commute_cooldown - delta)
	if is_receptionist:
		_update_receptionist(delta)
	elif is_resident:
		_update_ambient(delta)
	elif office_status in ["idle", "completed"]:
		_update_ambient(delta)
	elif not _commuting and _at_residence and office_status == "working":
		# Backend reports active work while we are visually at home: commute in.
		_begin_commute_to_work()

	var was_walking := _is_walking
	if _is_walking and _route_index < _route.size():
		var target: Vector3 = _route[_route_index]
		var flat_target := Vector3(target.x, global_position.y, target.z)
		var to_target := flat_target - global_position
		if to_target.length() < 0.42:
			_route_index += 1
			if _route_index >= _route.size():
				_is_walking = false
				velocity.x = 0.0
				velocity.z = 0.0
				_on_route_completed()
		else:
			var direction := _steer_around_obstacles(to_target.normalized())
			var move_speed := 1.45 if is_receptionist else (1.72 if _meeting_active else (2.05 if _commuting else 1.38))
			velocity.x = move_toward(velocity.x, direction.x * move_speed, 7.0 * delta)
			velocity.z = move_toward(velocity.z, direction.z * move_speed, 7.0 * delta)
			_visual.rotation.y = lerp_angle(_visual.rotation.y, atan2(-direction.x, -direction.z), 7.0 * delta)
			move_and_slide()
			_update_stuck_recovery(delta, to_target.length())
	else:
		velocity.x = move_toward(velocity.x, 0.0, 8.0 * delta)
		velocity.z = move_toward(velocity.z, 0.0, 8.0 * delta)
		move_and_slide()

	# Auto-sit when at workstation and working, auto-stand when leaving
	if was_walking and not _is_walking:
		stand()  # Reset sit state when arriving at destination
	if not _is_walking and office_status == "working":
		var dist_to_home := global_position.distance_to(home_position)
		if dist_to_home < 1.8:
			sit()
		elif dist_to_home >= 1.8 and _sitting:
			stand()
	elif _sitting and not _is_walking:
		stand()

	_animate_character(delta)
	_update_head_tracking(delta)

func _update_head_tracking(delta: float) -> void:
	# IK Head Tracking: leher mengikuti pemain saat dekat (natural, halus).
	if _head_pivot == null or _player == null or not is_instance_valid(_player):
		return
	var to_player := _player.global_position - _head_pivot.global_position
	var dist := to_player.length()
	if dist > 8.0 or dist < 0.5:
		return
	# Only track when facing roughly toward player.
	var forward := -_visual.global_transform.basis.z
	var to_dir := to_player.normalized()
	if forward.dot(to_dir) < 0.3:
		return
	var target_yaw := atan2(to_dir.x, to_dir.z)
	var target_pitch := -atan2(to_dir.y, Vector2(to_dir.x, to_dir.z).length())
	# Clamp to natural neck range.
	target_pitch = clampf(target_pitch, -0.5, 0.5)
	target_yaw = clampf(lerp_angle(_head_pivot.rotation.y, target_yaw, 0.0), -0.6, 0.6)
	_head_pivot.rotation.y = lerpf(_head_pivot.rotation.y, target_yaw, minf(1.0, delta * 4.0))
	_head_pivot.rotation.x = lerpf(_head_pivot.rotation.x, target_pitch, minf(1.0, delta * 4.0))

func _on_route_completed() -> void:
	if _ambient_phase == "meeting_approach":
		_ambient_phase = "meeting_seated"
		_activity_mode = "meeting_listening"
		_visual.rotation.y = _meeting_facing_yaw
		activity_text = "Mendengarkan rekan · rapat lokal"
		_update_status_label()
	elif _ambient_phase == "meeting_return":
		_ambient_phase = "home"
		match office_status:
			"working":
				_activity_mode = "typing"
				activity_text = "Bekerja · tugas aktif"
			"failed":
				_activity_mode = "concerned"
				activity_text = "Perlu perhatian"
			"blocked":
				_activity_mode = "thinking"
				activity_text = "Menunggu penyelesaian hambatan"
			"talking":
				_activity_mode = "talking"
				activity_text = "Berbicara"
			"listening":
				_activity_mode = "listening"
				activity_text = "Mendengarkan"
			_:
				_activity_mode = "reviewing" if office_status == "completed" else "idle"
				activity_text = _default_activity()
		_routine_timer = _rng.randf_range(4.0, 8.0)
		_update_status_label()
	elif _ambient_phase == "commute_to_work":
		_commuting = false
		_at_residence = false
		_ambient_phase = "returning"
		_activity_mode = "walking"
		activity_text = "Masuk ke area kerja"
		if global_position.distance_to(home_position) > 0.55:
			_set_route([home_position])
		else:
			_ambient_phase = "home"
			_clear_route()
			activity_text = _default_activity() if office_status != "working" else "Bekerja · tugas aktif"
		_update_status_label()
	elif _ambient_phase == "commute_home":
		_commuting = false
		_at_residence = true
		_ambient_phase = "at_home"
		_activity_mode = "resting_home"
		activity_text = "Di rumah · istirahat"
		_clear_route()
		_routine_timer = _rng.randf_range(6.0, 12.0)
		_commute_cooldown = 8.0
		_update_status_label()
	elif _ambient_phase == "outbound":
		_ambient_phase = "at_destination"
		activity_text = "Sedang " + _activity_description(_activity_mode)
		_routine_timer = _rng.randf_range(3.5, 6.5)
	elif _ambient_phase == "returning":
		_ambient_phase = "home"
		if office_status == "working":
			_activity_mode = "typing"
			activity_text = "Bekerja · tugas aktif"
			sit()
		else:
			_activity_mode = "idle"
			activity_text = _default_activity()
			_routine_timer = _rng.randf_range(5.0, 9.0)
	else:
		activity_text = _default_activity()
	_update_status_label()

func _activity_description(mode: String) -> String:
	match mode:
		"commute": return "perjalanan pulang-pergi kantor/rumah"
		"resting_home": return "beristirahat di rumah"
		"review_board": return "meninjau papan sprint"
		"review_documents": return "membaca dokumen"
		"inspect_diagram": return "memeriksa diagram sistem"
		"inspect_design": return "meninjau desain antarmuka"
		"inspect_test_bench": return "memeriksa hasil pengujian"
		"inspect_logs": return "membaca service log"
		"inspect_server": return "memeriksa perangkat infrastruktur"
		"talking": return "berdiskusi dengan rekan"
		_: return "meninjau area kerja"

func _update_receptionist(delta: float) -> void:
	if _greeting_lock > 0.0:
		_greeting_lock = maxf(0.0, _greeting_lock - delta)
		if _greeting_lock > 0.0:
			return
	_routine_timer -= delta
	if _routine_timer > 0.0:
		return
	var routines := [
		{"mode": "typing", "text": "Front desk · memperbarui data kunjungan", "duration": 5.5},
		{"mode": "writing", "text": "Front desk · mencatat jadwal tamu", "duration": 4.0},
		{"mode": "phone", "text": "Front desk · mengonfirmasi janji temu", "duration": 5.0},
		{"mode": "reviewing", "text": "Front desk · memeriksa daftar kunjungan", "duration": 4.5},
		{"mode": "greeting", "text": "Front desk · menyambut pengunjung", "duration": 3.5}
	]
	var next_index := _rng.randi_range(0, routines.size() - 1)
	if _activity_mode == str(routines[next_index].mode):
		next_index = (next_index + 1) % routines.size()
	var routine: Dictionary = routines[next_index]
	_activity_mode = str(routine.mode)
	activity_text = str(routine.text)
	_routine_timer = float(routine.duration)
	_update_status_label()

func _update_ambient(delta: float) -> void:
	if _meeting_active or _is_walking or _commuting:
		return
	# While off-duty and idle at the office, head home once (visual commute).
	if not _shift_on_duty and _can_leave_for_home() and _commute_cooldown <= 0.0:
		_begin_commute_home()
		return
	# While on-duty at home, return to work.
	if _shift_on_duty and _at_residence and office_status in ["idle", "completed"] and _commute_cooldown <= 0.0:
		_begin_commute_to_work()
		return
	_routine_timer -= delta
	if _routine_timer > 0.0:
		return
	if _ambient_phase == "at_home":
		# Stay home during off-duty; nudge back to work when shift opens.
		if _shift_on_duty and office_status in ["idle", "completed"] and _commute_cooldown <= 0.0:
			_begin_commute_to_work()
		else:
			_routine_timer = _rng.randf_range(6.0, 12.0)
			activity_text = "Di rumah · istirahat" if not _shift_on_duty else "Bersiap berangkat"
			_update_status_label()
		return
	if _ambient_phase == "at_destination":
		_ambient_phase = "returning"
		_activity_mode = "walking"
		activity_text = "Kembali ke workstation"
		_set_route([home_position])
		activity_text = "Kembali ke workstation"
		_update_status_label()
		return
	if _plans.is_empty():
		_routine_timer = 7.0
		_activity_mode = "idle"
		return

	var next_index := _rng.randi_range(0, _plans.size() - 1)
	if _plans.size() > 1 and next_index == _last_ambient_plan:
		next_index = (next_index + 1) % _plans.size()
	_last_ambient_plan = next_index
	var plan: Dictionary = _plans[next_index]
	var target: Vector3 = plan.get("target", home_position)
	if target.distance_to(home_position) < 0.75:
		_routine_timer = 8.0
		return
	_activity_mode = str(plan.get("mode", "review_documents"))
	_ambient_phase = "outbound"
	activity_text = str(plan.get("label", "Berjalan ke area kerja"))
	_set_route([target])
	activity_text = str(plan.get("label", "Berjalan ke area kerja"))
	_update_status_label()

func _animate_character(delta: float) -> void:
	if _external_animation_player != null:
		_update_external_animation()
		return

	var walking := _is_walking
	var working := office_status == "working" and not walking
	var meeting_seated := _meeting_active and _ambient_phase == "meeting_seated"
	var mode := _activity_mode

	# Base Y offset so feet rest on the floor, not through it.
	const BASE_Y := 0.20

	# --- Smooth sit/stand transition ---
	if _sitting:
		_sit_transition = minf(1.0, _sit_transition + delta * 3.5)
	else:
		_sit_transition = maxf(0.0, _sit_transition - delta * 3.5)
	var sit_factor := ease(_sit_transition, 1.5)

	# --- Idle variation timer ---
	_idle_timer -= delta
	if _idle_timer <= 0.0:
		_idle_variant = _rng.randi_range(0, 4)
		_idle_timer = _rng.randf_range(3.0, 7.0)

	# === BODY POSITION & ROTATION ===
	var target_y := 0.0
	var target_rx := 0.0
	var target_rz := 0.0

	if walking:
		# Natural walk: vertical bob matches footfall, forward lean, hip sway.
		var stride := _phase * 7.0
		var bob := absf(sin(stride)) * 0.045
		var lean := 0.07
		var sway := sin(stride * 0.5) * 0.022
		# Subtle horizontal sway for natural gait.
		var side_sway := sin(stride) * 0.012
		target_y = BASE_Y + bob
		target_rx = lean
		target_rz = sway
		_visual.position.y = lerpf(_visual.position.y, target_y, minf(1.0, delta * 12.0))
		_visual.rotation.x = lerpf(_visual.rotation.x, target_rx, minf(1.0, delta * 7.0))
		_visual.rotation.z = lerpf(_visual.rotation.z, target_rz, minf(1.0, delta * 7.0))
		# Subtle horizontal position offset for natural gait.
		_visual.position.x = lerpf(_visual.position.x, side_sway, minf(1.0, delta * 8.0))
	elif working and sit_factor > 0.15:
		# Seated typing — forward lean, subtle body movement.
		var sit_depth := sit_factor
		target_y = BASE_Y - 0.10 - sit_depth * 0.22
		target_rx = sit_depth * 0.30
		target_rz = sin(_phase * 1.3) * 0.006
		# Subtle breathing while seated.
		var breath := sin(_phase * 1.6) * 0.005
		_visual.position.y = lerpf(_visual.position.y, target_y + breath, minf(1.0, delta * 9.0))
		_visual.rotation.x = lerpf(_visual.rotation.x, target_rx, minf(1.0, delta * 6.0))
		_visual.rotation.z = lerpf(_visual.rotation.z, target_rz, minf(1.0, delta * 5.0))
		_visual.position.x = lerpf(_visual.position.x, 0.0, minf(1.0, delta * 4.0))
	elif working:
		# Standing work — slight forward lean.
		target_y = BASE_Y - 0.06 + sin(_phase * 1.8) * 0.008
		target_rx = 0.02
		_visual.position.y = lerpf(_visual.position.y, target_y, minf(1.0, delta * 8.0))
		_visual.rotation.x = lerpf(_visual.rotation.x, target_rx, minf(1.0, delta * 5.0))
		_visual.rotation.z = lerpf(_visual.rotation.z, 0.0, minf(1.0, delta * 5.0))
		_visual.position.x = lerpf(_visual.position.x, 0.0, minf(1.0, delta * 4.0))
	elif meeting_seated:
		# Meeting seated — subtle movements, engaged posture.
		target_y = BASE_Y - 0.08 + sin(_phase * 1.4) * 0.005
		var lean_meeting := 0.04 if _activity_mode == "meeting_speaking" else 0.0
		_visual.position.y = lerpf(_visual.position.y, target_y, minf(1.0, delta * 8.0))
		_visual.rotation.x = lerpf(_visual.rotation.x, lean_meeting, minf(1.0, delta * 5.0))
		_visual.rotation.z = lerpf(_visual.rotation.z, 0.0, minf(1.0, delta * 5.0))
		_visual.position.x = lerpf(_visual.position.x, 0.0, minf(1.0, delta * 4.0))
	else:
		# Idle with weight shifting — different micro-poses for variety.
		var breath := sin(_phase * 1.2) * 0.009
		var weight_shift := sin(_phase * 0.45) * 0.008
		match _idle_variant:
			0:
				target_y = BASE_Y + breath
				target_rz = weight_shift * 0.5
			1:
				target_y = BASE_Y + breath * 0.8 + 0.003
				target_rz = weight_shift
			2:
				target_y = BASE_Y + breath * 0.6 - 0.002
				target_rz = -weight_shift
			3:
				# Occasional subtle hip cock.
				target_y = BASE_Y + breath * 0.9 + 0.001
				target_rz = weight_shift * 1.5
			_:
				target_y = BASE_Y + breath * 0.7
				target_rz = sin(_phase * 0.55) * 0.006
		_visual.position.y = lerpf(_visual.position.y, target_y, minf(1.0, delta * 5.0))
		_visual.rotation.x = lerpf(_visual.rotation.x, 0.0, minf(1.0, delta * 4.0))
		_visual.rotation.z = lerpf(_visual.rotation.z, target_rz, minf(1.0, delta * 3.0))
		_visual.position.x = lerpf(_visual.position.x, 0.0, minf(1.0, delta * 3.0))

	# === HEAD MOVEMENT ===
	var head_x := 0.0
	var head_y := sin(_phase * 0.42) * 0.030
	if working and sit_factor > 0.15:
		# Seated: look slightly down at screen, occasional glances.
		head_x = sit_factor * 0.12 + sin(_phase * 0.6) * 0.014
		head_y += sin(_phase * 0.35) * 0.028
		# Occasional glance to the side.
		if sin(_phase * 0.15) > 0.85:
			head_y += 0.08
	elif working:
		head_x = 0.07 + sin(_phase * 0.6) * 0.016
		head_y += sin(_phase * 0.35) * 0.038
	elif mode in ["review_board", "inspect_diagram", "inspect_design"]:
		# Looking up at boards.
		head_x = -0.03
		head_y += 0.14 + sin(_phase * 0.5) * 0.025
		# Occasional nod.
		head_x += sin(_phase * 0.25) * 0.01
	elif mode in ["review_documents", "writing", "inspect_test_bench", "inspect_logs", "inspect_server"]:
		# Looking down at documents/devices.
		head_x = 0.10 + sin(_phase * 0.5) * 0.014
		head_y += sin(_phase * 0.4) * 0.020
	elif mode == "phone":
		# Head tilted to hold phone.
		head_y += -0.12 + sin(_phase * 0.8) * 0.025
		head_x = 0.04
		# Slight nod while listening.
		head_x += sin(_phase * 0.6) * 0.008
	elif mode == "thinking" or mode == "concerned":
		# Head tilted, looking up slightly.
		head_x = 0.07
		head_y += 0.10 + sin(_phase * 0.3) * 0.018
		# Subtle head shake.
		head_y += sin(_phase * 0.2) * 0.04
	elif mode == "greeting":
		# Animated, welcoming nods.
		head_y += sin(_phase * 1.5) * 0.09
		head_x = -0.03 + sin(_phase * 0.8) * 0.01
	elif mode in ["talking", "meeting_speaking"]:
		# Expressive head movement while speaking.
		var freq := 1.8 if mode == "meeting_speaking" else 1.2
		head_y += sin(_phase * freq) * 0.07
		head_x = sin(_phase * 0.3) * 0.018
		# Occasional nod for emphasis.
		head_x += absf(sin(_phase * 0.4)) * 0.02
	elif mode in ["listening", "meeting_listening"]:
		# Subtle attentive movements.
		head_y += sin(_phase * 0.35) * 0.025
		head_x = 0.02 + sin(_phase * 0.25) * 0.008
		# Occasional slow nod.
		if sin(_phase * 0.18) > 0.5:
			head_x += 0.015
	elif mode == "sitting":
		head_x = 0.06 + sin(_phase * 0.4) * 0.012
		head_y += 0.03 + sin(_phase * 0.3) * 0.018
	if _head_pivot != null:
		_head_pivot.rotation.x = lerpf(_head_pivot.rotation.x, head_x, minf(1.0, delta * 5.5))
		_head_pivot.rotation.y = lerpf(_head_pivot.rotation.y, head_y, minf(1.0, delta * 4.5))

	# === ARM ANIMATION ===
	for index in range(_arms.size()):
		var arm: Node3D = _arms[index]
		var side := -1.0 if index == 0 else 1.0
		var target_rotation := Vector3.ZERO

		if walking:
			# Natural arm counter-swing with elbow flex, opposite to leg.
			var swing := sin(_phase * 7.0 + float(index) * PI) * 0.42
			var elbow_flex := absf(cos(_phase * 7.0 + float(index) * PI)) * 0.12
			target_rotation = Vector3(
				swing + elbow_flex * 0.3,
				sin(_phase * 3.5 + float(index)) * 0.04,
				side * (0.03 + sin(_phase * 3.5) * 0.015)
			)
		elif working and sit_factor > 0.15:
			# Typing: both arms forward, fast finger-like jitter.
			var type_speed := 9.0 + sin(_phase * 1.1) * 3.0
			var base_fwd := sit_factor * 0.88
			# Occasional pause in typing.
			var typing_active := 1.0 if sin(_phase * 0.18) > -0.3 else 0.3
			target_rotation = Vector3(
				base_fwd + 0.14 + sin(_phase * type_speed * typing_active + float(index) * 1.3) * 0.07,
				sin(_phase * 2.1 + float(index)) * 0.028,
				side * (0.03 + sin(_phase * type_speed * 0.5 * typing_active + float(index)) * 0.028)
			)
		elif working:
			# Standing work — arms at desk height.
			var type_speed := 8.0 + sin(_phase * 1.0) * 2.0
			target_rotation = Vector3(
				0.95 + sin(_phase * type_speed + float(index) * 1.4) * 0.07,
				sin(_phase * 2.5 + float(index)) * 0.025,
				side * 0.025
			)
		else:
			match mode:
				"typing", "inspect_logs":
					target_rotation = Vector3(0.80 + sin(_phase * 7.0 + float(index)) * 0.06, sin(_phase * 2.0 + float(index)) * 0.025, side * 0.028)
				"writing", "review_documents", "inspect_test_bench":
					# One hand writing, other holding document.
					if index == 0:
						target_rotation = Vector3(0.95 + sin(_phase * 2.5) * 0.04, 0.02, 0.03)
					else:
						target_rotation = Vector3(0.45 + sin(_phase * 1.5) * 0.03, -0.02, -0.05)
				"phone":
					# One hand to ear, the other gesturing.
					if index == 0:
						target_rotation = Vector3(0.65 + sin(_phase * 0.8) * 0.02, sin(_phase * 1.2) * 0.03, -0.16)
					else:
						target_rotation = Vector3(0.35 + sin(_phase * 1.5) * 0.08, 0.03, 0.06)
				"greeting":
					# Enthusiastic wave with the right arm.
					if index == 1:
						target_rotation = Vector3(
							1.95 + sin(_phase * 6.0) * 0.15,
							sin(_phase * 2.0) * 0.05,
							-0.10
						)
					else:
						target_rotation = Vector3(0.18, 0.01, 0.03)
				"thinking", "concerned":
					# Hand to chin — contemplative pose.
					if index == 0:
						target_rotation = Vector3(0.28 + sin(_phase * 0.8) * 0.02, 0.02, 0.08)
					else:
						target_rotation = Vector3(1.45 + sin(_phase * 0.5) * 0.02, 0.01, -0.12)
						# Slight head-touching motion.
						target_rotation.x += sin(_phase * 0.3) * 0.01
				"review_board", "inspect_diagram", "inspect_design", "inspect_server":
					# Pointing or gesturing toward boards.
					if index == 1:
						target_rotation = Vector3(0.48 + sin(_phase * 1.2 + float(index)) * 0.08, 0.02, -0.25)
					else:
						target_rotation = Vector3(0.42 + sin(_phase * 1.0) * 0.05, -0.01, 0.04)
				"talking":
					# Expressive hand gestures, alternating emphasis.
					var gesture_freq := 2.8
					target_rotation = Vector3(
						0.32 + sin(_phase * gesture_freq + float(index) * 1.5) * 0.28,
						sin(_phase * 1.2 + float(index)) * 0.06,
						side * 0.10
					)
				"listening":
					# Hands relaxed, occasional subtle nod gesture.
					target_rotation = Vector3(0.12 + sin(_phase * 0.9 + float(index)) * 0.025, 0.0, side * 0.018)
				"meeting_speaking":
					# More expressive — leaning forward with gestures.
					var meeting_freq := 3.8
					target_rotation = Vector3(
						0.50 + sin(_phase * meeting_freq + float(index)) * 0.20,
						sin(_phase * 1.5 + float(index)) * 0.04,
						side * (0.08 if index == 1 else 0.02)
					)
				"meeting_listening":
					# Hands on table, attentive.
					target_rotation = Vector3(0.25 + sin(_phase * 0.8 + float(index)) * 0.02, 0.0, side * 0.025)
				_:
					# Relaxed idle: subtle arm breathing with occasional micro-movement.
					var micro := sin(_phase * 0.3 + float(index)) * 0.005
					target_rotation = Vector3(
						0.07 + sin(_phase * 0.8 + float(index) * PI) * 0.028 + micro,
						sin(_phase * 0.4 + float(index)) * 0.018,
						side * (0.014 + micro)
					)

		arm.rotation = arm.rotation.lerp(target_rotation, minf(1.0, delta * 6.5))

	# === LEG ANIMATION ===
	for index in range(_legs.size()):
		var leg: Node3D = _legs[index]
		var target_angle := 0.0
		if working and sit_factor > 0.15:
			# Bent sitting legs — natural knee angle.
			target_angle = sit_factor * 1.05 + sin(_phase * 0.8 + float(index) * PI) * 0.04
		elif working:
			# Standing — legs slightly bent, weight shift.
			target_angle = PI * 0.42 + sin(_phase * 0.5 + float(index) * PI) * 0.02
		elif walking:
			# Alternating leg swing with natural knee flex.
			var stride := _phase * 7.0
			var swing := sin(stride + float(index) * PI) * 0.42
			var knee_flex := maxf(0.0, cos(stride + float(index) * PI)) * 0.08
			target_angle = swing + knee_flex
		elif meeting_seated:
			# Seated — legs under chair.
			target_angle = -0.85 + sin(_phase * 0.6 + float(index) * PI) * 0.025
		else:
			# Idle — subtle weight shift.
			target_angle = sin(_phase * 0.6 + float(index) * PI) * 0.012
			# Occasional subtle knee bend.
			if _idle_variant == 3:
				target_angle += sin(_phase * 0.3) * 0.008
		leg.rotation.x = lerpf(leg.rotation.x, target_angle, minf(1.0, delta * 7.5))

	# === BLINKING ===
	_blink_timer -= delta
	if _blink_timer <= 0.0 and _blink_duration <= 0.0:
		_blink_duration = 0.13
		_blink_timer = _rng.randf_range(2.5, 6.0)
	if _blink_duration > 0.0:
		_blink_duration = maxf(0.0, _blink_duration - delta)
	var blink_target := 0.15 if _blink_duration > 0.0 else 1.0
	for eye in _eyes:
		if eye is Node3D:
			(eye as Node3D).scale.y = lerpf((eye as Node3D).scale.y, blink_target, minf(1.0, delta * 30.0))

	# === BREATHING (subtle, always on) ===
	var breath_z := sin(_phase * 0.9) * 0.004
	if not walking and not working:
		_visual.rotation.z = lerpf(_visual.rotation.z, breath_z + target_rz, minf(1.0, delta * 2.5))
	elif walking:
		_visual.rotation.z = lerpf(_visual.rotation.z, target_rz, minf(1.0, delta * 7.0))

	_update_external_animation()

func _update_external_animation() -> void:
	if _external_animation_player == null:
		return
	var desired := "idle"
	if _is_walking:
		desired = "walk"
	elif office_status == "working":
		desired = "type"
	elif _meeting_active and _ambient_phase == "meeting_seated":
		desired = "talk" if _activity_mode == "meeting_speaking" else "listen"
	elif _activity_mode in ["talking", "greeting"]:
		desired = "talk"
	elif _activity_mode in ["writing", "review_documents"]:
		desired = "write"
	elif _activity_mode == "phone":
		desired = "phone"
	var candidates := {
		"idle": ["Idle", "idle", "Standing"],
		"walk": ["Walk", "Walking", "walk"],
		"type": ["Type", "Typing", "Sitting_Computer"],
		"talk": ["Talk", "Talking", "Conversation"],
		"listen": ["Listen", "Listening", "Idle_Seated"],
		"write": ["Write", "Writing", "Reading"],
		"phone": ["Phone", "TalkingOnPhone", "Call"]
	}
	for animation_name in candidates.get(desired, ["Idle"]):
		if _external_animation_player.has_animation(animation_name):
			if _external_animation_name != animation_name:
				_external_animation_name = animation_name
				_external_animation_player.play(animation_name)
			return
