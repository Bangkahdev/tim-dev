extends CharacterBody3D

class_name OfficePlayer

const CHARACTER_FACTORY = preload("res://scripts/character_factory.gd")

signal interact_requested
signal ui_requested(page_id: String)

@export var walk_speed: float = 4.4
@export var sprint_speed: float = 6.8
@export var jump_velocity: float = 4.8
@export var mouse_sensitivity: float = 0.0019
@export var eye_height: float = 1.66

func _enter_tree() -> void:
	# Reliable stair/ramp climbing across HQ floors.
	floor_snap_length = 0.55
	floor_max_angle = deg_to_rad(62.0)
	floor_stop_on_slope = false
	floor_constant_speed = true
	floor_block_on_wall = false
	wall_min_slide_angle = deg_to_rad(12.0)

var controls_enabled: bool = true
var is_moving: bool = false
var activity: String = "idle"
var _collision: CollisionShape3D
var _camera: Camera3D
var _camera_mount: Node3D
var _third_person_camera: Camera3D
var _third_person_pivot: Node3D
var _third_person_spring: SpringArm3D
var _world_visual: Node3D
var _viewmodel: Node3D
var _view_mode: String = "third_person"
var _iso_enabled: bool = false
var _iso_tween: Tween = null
var _walk_phase: float = 0.0
var _head_bob: float = 0.0
var _external_animation_player: AnimationPlayer
var _external_animation_name: String = ""
# Procedural animation parts (same interface as NPC).
var _arms: Array = []
var _legs: Array = []
var _eyes: Array = []
var _head_pivot: Node3D
var _phase: float = 0.0
var _blink_timer: float = 3.0
var _blink_duration: float = 0.0
var _idle_variant: int = 0
var _idle_timer: float = 0.0
var _visual_yaw: float = 0.0
var _target_visual_yaw: float = 0.0
var _rng := RandomNumberGenerator.new()
var is_seated: bool = false
var _saved_transform: Transform3D
var _seated_blend: float = 0.0
# Drivable vehicle (visual): player drives a simple car node around town/HQ.
var is_driving: bool = false
var _drive_node: Node3D = null
var _drive_speed: float = 0.0
var _drive_seat_offset: Vector3 = Vector3(0.0, 0.95, -0.25)
var _drive_exit_offset: Vector3 = Vector3(1.65, 0.0, 0.0)
var _drive_saved_tp_spring: float = 5.0

func _ready() -> void:
	_rng.randomize()
	_ensure_inputs()
	var collision := CollisionShape3D.new()
	_collision = collision
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.32
	capsule.height = 2.26
	collision.shape = capsule
	collision.position.y = 1.14
	add_child(collision)

	# Camera setup FIRST — ensures cameras exist even if character creation has issues.
	var camera_mount := Node3D.new()
	camera_mount.name = "FirstPersonCameraMount"
	camera_mount.position = Vector3(0.0, eye_height, 0.0)
	add_child(camera_mount)
	_camera_mount = camera_mount

	_camera = Camera3D.new()
	_camera.name = "OwnerFirstPersonCamera"
	_camera.current = true
	_camera.fov = 72.0
	_camera.near = 0.06
	_camera.far = 420.0
	camera_mount.add_child(_camera)

	_viewmodel = Node3D.new()
	_viewmodel.name = "FirstPersonViewModel"
	_camera.add_child(_viewmodel)
	_add_viewmodel_arm(_viewmodel, -1.0)
	_add_viewmodel_arm(_viewmodel, 1.0)

	# Over-the-shoulder third-person camera.
	_third_person_pivot = Node3D.new()
	_third_person_pivot.name = "ThirdPersonPivot"
	_third_person_pivot.position = Vector3(0.0, 1.48, 0.0)
	add_child(_third_person_pivot)
	_third_person_spring = SpringArm3D.new()
	_third_person_spring.spring_length = 5.0
	_third_person_spring.margin = 0.18
	_third_person_spring.add_excluded_object(get_rid())
	_third_person_pivot.add_child(_third_person_spring)
	_third_person_camera = Camera3D.new()
	_third_person_camera.name = "OwnerFollowCamera"
	_third_person_camera.fov = 72.0
	_third_person_camera.current = false
	_third_person_camera.near = 0.1
	_third_person_camera.far = 420.0
	_third_person_camera.position = Vector3(0.42, 0.12, 0.0)
	_third_person_spring.add_child(_third_person_camera)
	_third_person_pivot.rotation.x = deg_to_rad(-7.0)

	# Camera attributes — Design Bible: FAR DoF DISABLED (sharp distant city).
	var cam_attrs := CameraAttributesPractical.new()
	cam_attrs.set("dof_blur_far_enabled", false)
	cam_attrs.set("dof_blur_near_enabled", false)
	_camera.attributes = cam_attrs
	_third_person_camera.attributes = cam_attrs

	_set_view_mode("third_person")
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

	# Character visual — created AFTER cameras so camera is never null.
	var character_data: Dictionary = CHARACTER_FACTORY.build(self, Color("#3d5a55"), Color("#26292a"), "OWNER", "owner")
	_world_visual = character_data.get("visual")
	_arms = character_data.get("arms", [])
	_legs = character_data.get("legs", [])
	_eyes = character_data.get("eyes", [])
	_head_pivot = character_data.get("head_pivot")
	_external_animation_player = character_data.get("animation_player") as AnimationPlayer
	if _world_visual != null:
		_world_visual.visible = true

func _add_viewmodel_arm(parent: Node3D, side: float) -> void:
	var arm := MeshInstance3D.new()
	var sleeve := CapsuleMesh.new()
	sleeve.radius = 0.095
	sleeve.height = 0.48
	sleeve.radial_segments = 16
	sleeve.rings = 6
	arm.mesh = sleeve
	arm.material_override = _view_material(Color("#344b49"), 0.85)
	arm.position = Vector3(side * 0.31, -0.39, -0.48)
	arm.rotation = Vector3(-0.54, side * -0.08, side * -0.20)
	arm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(arm)

	var forearm := MeshInstance3D.new()
	var forearm_mesh := CapsuleMesh.new()
	forearm_mesh.radius = 0.072
	forearm_mesh.height = 0.38
	forearm_mesh.radial_segments = 16
	forearm_mesh.rings = 6
	forearm.mesh = forearm_mesh
	forearm.material_override = _view_material(Color("#bd9277"), 0.65)
	forearm.position = Vector3(side * 0.34, -0.68, -0.58)
	forearm.rotation = Vector3(-0.38, 0.0, side * -0.12)
	forearm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(forearm)

	var hand := MeshInstance3D.new()
	var hand_mesh := SphereMesh.new()
	hand_mesh.radius = 0.075
	hand_mesh.height = 0.14
	hand_mesh.radial_segments = 16
	hand_mesh.rings = 8
	hand.mesh = hand_mesh
	hand.material_override = _view_material(Color("#bd9277"), 0.65)
	hand.scale = Vector3(1.0, 0.82, 0.72)
	hand.position = Vector3(side * 0.36, -0.87, -0.70)
	hand.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(hand)

func _view_material(color: Color, roughness: float = 0.88) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	material.metallic = 0.0
	material.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material

func _ensure_inputs() -> void:
	var mappings := {
		"move_forward": [KEY_W, KEY_UP],
		"move_back": [KEY_S, KEY_DOWN],
		"move_left": [KEY_A, KEY_LEFT],
		"move_right": [KEY_D, KEY_RIGHT],
		"jump": [KEY_SPACE],
		"sprint": [KEY_SHIFT]
	}
	for action_name in mappings:
		if not InputMap.has_action(action_name):
			InputMap.add_action(action_name)
		for key_code in mappings[action_name]:
			var event := InputEventKey.new()
			event.physical_keycode = key_code
			if not InputMap.action_has_event(action_name, event):
				InputMap.action_add_event(action_name, event)

func _process(_delta: float) -> void:
	if _world_visual == null:
		return
	if is_driving or is_seated:
		_world_visual.visible = false
	else:
		_world_visual.visible = (_view_mode == "third_person")


func _input(event: InputEvent) -> void:
	# Camera look — processed in _input (before UI) so it always works.
	if event is InputEventMouseMotion and controls_enabled:
		if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			rotate_y(-event.relative.x * mouse_sensitivity)
			var pitch_delta: float = -event.relative.y * mouse_sensitivity
			if is_instance_valid(_camera):
				_camera.rotation.x = clampf(_camera.rotation.x + pitch_delta, deg_to_rad(-82.0), deg_to_rad(82.0))
			if is_instance_valid(_third_person_pivot) and not _iso_enabled:
				_third_person_pivot.rotation.x = clampf(_third_person_pivot.rotation.x + pitch_delta, deg_to_rad(-35.0), deg_to_rad(25.0))
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			# Drag-to-look for touchpad / non-captured mode.
			rotate_y(-event.relative.x * mouse_sensitivity * 1.5)
			var pitch_delta2: float = -event.relative.y * mouse_sensitivity * 1.5
			if is_instance_valid(_camera):
				_camera.rotation.x = clampf(_camera.rotation.x + pitch_delta2, deg_to_rad(-82.0), deg_to_rad(82.0))
			if is_instance_valid(_third_person_pivot) and not _iso_enabled:
				_third_person_pivot.rotation.x = clampf(_third_person_pivot.rotation.x + pitch_delta2, deg_to_rad(-35.0), deg_to_rad(25.0))

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		elif controls_enabled and event.keycode == KEY_E:
			interact_requested.emit()
		elif controls_enabled and event.keycode == KEY_F1:
			ui_requested.emit("overview")
		elif controls_enabled and event.keycode == KEY_F2:
			ui_requested.emit("documents")
		elif controls_enabled and event.keycode == KEY_F3:
			ui_requested.emit("projects")
		elif controls_enabled and event.keycode == KEY_F4:
			ui_requested.emit("team")
		elif controls_enabled and event.keycode == KEY_V:
			if _view_mode == "first_person":
				_iso_enabled = false
				_set_view_mode("third_person")
			elif not _iso_enabled:
				set_camera_mode(true)
			else:
				set_camera_mode(false)
				_set_view_mode("first_person")
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_LEFT and Input.mouse_mode == Input.MOUSE_MODE_VISIBLE and controls_enabled:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		elif _view_mode == "third_person" and event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_third_person_spring.spring_length = maxf(2.5, _third_person_spring.spring_length - 0.45)
		elif _view_mode == "third_person" and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_third_person_spring.spring_length = minf(9.5, _third_person_spring.spring_length + 0.45)

func _physics_process(delta: float) -> void:
	_phase += delta
	if is_driving and is_instance_valid(_drive_node):
		if _world_visual != null:
			_world_visual.visible = false
		_drive_physics(delta)
		return
	if is_seated:
		velocity = Vector3.ZERO
		_animate_seated(delta)
		_update_external_animation()
		return
	var gravity: float = float(ProjectSettings.get_setting("physics/3d/default_gravity", 18.0))
	if not is_on_floor():
		velocity.y -= gravity * delta
	elif controls_enabled and Input.is_action_just_pressed("jump"):
		velocity.y = jump_velocity

	# Movement works with or without mouse capture — only need controls enabled.
	var input_vector := Vector2.ZERO
	if controls_enabled:
		input_vector = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var forward := -global_transform.basis.z
	var right := global_transform.basis.x
	forward.y = 0.0
	right.y = 0.0
	forward = forward.normalized()
	right = right.normalized()
	var direction := (right * input_vector.x) + (forward * -input_vector.y)
	if direction.length_squared() > 1.0:
		direction = direction.normalized()

	is_moving = direction.length_squared() > 0.012
	var is_sprinting := Input.is_action_pressed("sprint") and controls_enabled and is_moving
	var speed := sprint_speed if is_sprinting else walk_speed
	var accel := 14.0 if is_moving else 10.0
	velocity.x = lerpf(velocity.x, direction.x * speed, minf(1.0, delta * accel))
	velocity.z = lerpf(velocity.z, direction.z * speed, minf(1.0, delta * accel))
	if not controls_enabled:
		velocity.x = move_toward(velocity.x, 0.0, walk_speed * 8.0 * delta)
		velocity.z = move_toward(velocity.z, 0.0, walk_speed * 8.0 * delta)
	move_and_slide()

	# In third-person, rotate the character visual to face movement direction.
	# When idle, face the camera direction (where the player is looking).
	if _view_mode == "third_person" and _world_visual != null:
		if is_moving:
			# Convert world direction to local space (relative to player body).
			var local_dir := direction.rotated(Vector3.UP, -global_rotation.y)
			_target_visual_yaw = atan2(-local_dir.x, -local_dir.z)
		else:
			_target_visual_yaw = 0.0  # Face same direction as player when idle.
		_visual_yaw = lerp_angle(_visual_yaw, _target_visual_yaw, minf(1.0, delta * 10.0))
		_world_visual.rotation.y = _visual_yaw

	# Head bob.
	if is_moving:
		_walk_phase += delta * (10.0 if is_sprinting else 7.5)
		var bob_amount := 0.028 if is_sprinting else 0.016
		_head_bob = sin(_walk_phase * 2.0) * bob_amount
	else:
		_head_bob = lerpf(_head_bob, 0.0, delta * 7.0)
		_walk_phase = lerpf(_walk_phase, 0.0, delta * 5.0)
	activity = "walking" if is_moving else "idle"
	if is_instance_valid(_camera):
		_camera.position.y = _head_bob if _view_mode == "first_person" else 0.0
		if _view_mode == "first_person" and is_moving:
			_camera.rotation.z = lerpf(_camera.rotation.z, sin(_walk_phase) * 0.006, delta * 4.0)
		else:
			_camera.rotation.z = lerpf(_camera.rotation.z, 0.0, delta * 4.0)

	# Animate the character body.
	_animate_player(delta, is_sprinting)
	_update_external_animation()

func _animate_player(delta: float, is_sprinting: bool) -> void:
	if _external_animation_player != null:
		return
	if _arms.is_empty() or _world_visual == null:
		return

	# Idle variation.
	_idle_timer -= delta
	if _idle_timer <= 0.0:
		_idle_variant = _rng.randi_range(0, 4)
		_idle_timer = _rng.randf_range(3.0, 7.0)

	var walking := is_moving
	var sprinting := is_sprinting

	# Base Y offset so feet rest on the floor.
	const BASE_Y := 0.20

	# Body position — walk bob and idle breathing.
	if walking:
		var stride := _phase * (10.0 if sprinting else 7.5)
		var bob := absf(sin(stride)) * (0.038 if sprinting else 0.024)
		var lean := 0.08 if sprinting else 0.05
		var sway := sin(stride * 0.5) * 0.020
		var side_sway := sin(stride) * 0.014
		_world_visual.position.y = lerpf(_world_visual.position.y, BASE_Y + bob, minf(1.0, delta * 12.0))
		_world_visual.rotation.x = lerpf(_world_visual.rotation.x, lean, minf(1.0, delta * 7.0))
		_world_visual.rotation.z = lerpf(_world_visual.rotation.z, sway, minf(1.0, delta * 7.0))
		_world_visual.position.x = lerpf(_world_visual.position.x, side_sway, minf(1.0, delta * 8.0))
	else:
		var breath := sin(_phase * 1.2) * 0.009
		var weight_shift := sin(_phase * 0.45) * 0.008
		var idle_y: float = BASE_Y + breath
		var idle_rz := weight_shift * 0.5
		match _idle_variant:
			0: idle_y = BASE_Y + breath
			1:
				idle_y = BASE_Y + breath * 0.8 + 0.003
				idle_rz = weight_shift
			2:
				idle_y = BASE_Y + breath * 0.6 - 0.002
				idle_rz = -weight_shift
			3:
				idle_y = BASE_Y + breath * 0.9 + 0.001
				idle_rz = weight_shift * 1.5
			_:
				idle_y = BASE_Y + breath * 0.7
				idle_rz = sin(_phase * 0.55) * 0.006
		_world_visual.position.y = lerpf(_world_visual.position.y, idle_y, minf(1.0, delta * 5.0))
		_world_visual.rotation.x = lerpf(_world_visual.rotation.x, 0.0, minf(1.0, delta * 4.0))
		_world_visual.rotation.z = lerpf(_world_visual.rotation.z, idle_rz, minf(1.0, delta * 3.0))
		_world_visual.position.x = lerpf(_world_visual.position.x, 0.0, minf(1.0, delta * 3.0))
	_world_visual.rotation.z = lerpf(_world_visual.rotation.z, sin(_phase * 0.55) * 0.004 if not walking else 0.0, minf(1.0, delta * 4.0))

	# Head — follows camera pitch (look up/down) + subtle idle motion.
	if _head_pivot != null:
		var cam_pitch: float = 0.0
		if _view_mode == "first_person":
			cam_pitch = _camera.rotation.x
		else:
			cam_pitch = _third_person_pivot.rotation.x
		var head_x := cam_pitch * 0.6 + sin(_phase * 0.42) * 0.015
		var head_y := sin(_phase * 0.35) * 0.025
		if walking:
			head_x += 0.03
		_head_pivot.rotation.x = lerpf(_head_pivot.rotation.x, head_x, minf(1.0, delta * 6.0))
		_head_pivot.rotation.y = lerpf(_head_pivot.rotation.y, head_y, minf(1.0, delta * 5.0))

	# Arms — walk swing or idle relaxation.
	for index in range(_arms.size()):
		var arm: Node3D = _arms[index]
		var side := -1.0 if index == 0 else 1.0
		var target_rotation := Vector3.ZERO
		if walking:
			var swing_speed := 10.0 if sprinting else 7.5
			var swing_amount := 0.46 if sprinting else 0.35
			var elbow_flex := absf(cos(_phase * swing_speed + float(index) * PI)) * 0.12
			target_rotation = Vector3(
				sin(_phase * swing_speed + float(index) * PI) * swing_amount + elbow_flex * 0.3,
				sin(_phase * swing_speed * 0.5 + float(index)) * 0.035,
				side * (0.03 + sin(_phase * swing_speed * 0.5) * 0.015)
			)
		else:
			# Relaxed idle with subtle micro-movements.
			var micro := sin(_phase * 0.3 + float(index)) * 0.005
			target_rotation = Vector3(
				0.06 + sin(_phase * 0.8 + float(index) * PI) * 0.028 + micro,
				sin(_phase * 0.4 + float(index)) * 0.018,
				side * (0.014 + micro)
			)
		arm.rotation = arm.rotation.lerp(target_rotation, minf(1.0, delta * 7.0))

	# Legs — walk cycle or idle.
	for index in range(_legs.size()):
		var leg: Node3D = _legs[index]
		var target_angle := 0.0
		if walking:
			var stride := _phase * (10.0 if sprinting else 7.5)
			var swing := sin(stride + float(index) * PI) * (0.44 if sprinting else 0.32)
			var knee_flex := maxf(0.0, cos(stride + float(index) * PI)) * 0.10
			target_angle = swing + knee_flex
		else:
			# Subtle weight shift.
			target_angle = sin(_phase * 0.6 + float(index) * PI) * 0.012
			if _idle_variant == 3:
				target_angle += sin(_phase * 0.3) * 0.008
		leg.rotation.x = lerpf(leg.rotation.x, target_angle, minf(1.0, delta * 8.0))

	# Blink.
	_blink_timer -= delta
	if _blink_timer <= 0.0 and _blink_duration <= 0.0:
		_blink_duration = 0.13
		_blink_timer = _rng.randf_range(2.5, 5.5)
	if _blink_duration > 0.0:
		_blink_duration = maxf(0.0, _blink_duration - delta)
	var blink_target := 0.15 if _blink_duration > 0.0 else 1.0
	for eye in _eyes:
		if eye is Node3D:
			(eye as Node3D).scale.y = lerpf((eye as Node3D).scale.y, blink_target, minf(1.0, delta * 30.0))

func _update_external_animation() -> void:
	if _external_animation_player == null:
		return
	var desired := "idle"
	if is_seated:
		desired = "sit"
	elif is_moving:
		desired = "run" if Input.is_action_pressed("sprint") else "walk"
	var candidates := {
		"idle": ["Idle", "idle", "Standing"],
		"walk": ["Walk", "Walking", "walk"],
		"run": ["Run", "Running", "Sprint"],
		"sit": ["Sit", "Sitting", "SitIdle", "Seated", "ChairIdle"]
	}
	for animation_name in candidates.get(desired, ["Idle"]):
		if _external_animation_player.has_animation(animation_name):
			if _external_animation_name != animation_name:
				_external_animation_name = animation_name
				_external_animation_player.play(animation_name)
			return

## Seat the Owner at a workstation. The caller owns the desktop session; this
## function only saves the standing transform and disables movement.
func sit_at(seat_position: Vector3, seat_yaw: float) -> void:
	if is_seated:
		return
	_saved_transform = global_transform
	is_seated = true
	_seated_blend = 0.0
	velocity = Vector3.ZERO
	set_input_enabled(false)
	global_position = seat_position
	rotation = Vector3(0.0, seat_yaw, 0.0)
	if is_instance_valid(_camera):
		_camera.current = false
	if is_instance_valid(_third_person_camera):
		_third_person_camera.current = false

## Return to the exact standing spot and facing direction used before sitting.
func stand_up() -> void:
	if not is_seated:
		return
	is_seated = false
	_seated_blend = 0.0
	global_transform = _saved_transform
	velocity = Vector3.ZERO
	if _world_visual != null:
		_world_visual.position = Vector3(0.0, 0.20, 0.0)
		_world_visual.rotation = Vector3.ZERO
	for leg in _legs:
		if leg is Node3D:
			(leg as Node3D).rotation = Vector3.ZERO
	for arm in _arms:
		if arm is Node3D:
			(arm as Node3D).rotation = Vector3.ZERO
	_set_view_mode(_view_mode)

func _animate_seated(delta: float) -> void:
	if _world_visual == null:
		return
	_seated_blend = minf(1.0, _seated_blend + delta * 5.0)
	_world_visual.position.x = lerpf(_world_visual.position.x, 0.0, minf(1.0, delta * 8.0))
	_world_visual.position.y = lerpf(_world_visual.position.y, -0.08, minf(1.0, delta * 8.0))
	_world_visual.rotation.x = lerpf(_world_visual.rotation.x, 0.0, minf(1.0, delta * 8.0))
	_world_visual.rotation.z = lerpf(_world_visual.rotation.z, 0.0, minf(1.0, delta * 8.0))
	for index in range(_legs.size()):
		var leg: Node3D = _legs[index]
		var side := -1.0 if index == 0 else 1.0
		leg.rotation.x = lerpf(leg.rotation.x, 0.88, minf(1.0, delta * 7.0))
		leg.rotation.z = lerpf(leg.rotation.z, side * 0.06, minf(1.0, delta * 7.0))
	for index in range(_arms.size()):
		var arm: Node3D = _arms[index]
		var side := -1.0 if index == 0 else 1.0
		arm.rotation.x = lerpf(arm.rotation.x, 0.95, minf(1.0, delta * 7.0))
		arm.rotation.y = lerpf(arm.rotation.y, side * -0.12, minf(1.0, delta * 7.0))
		arm.rotation.z = lerpf(arm.rotation.z, side * 0.16, minf(1.0, delta * 7.0))
	if _head_pivot != null:
		_head_pivot.rotation.x = lerpf(_head_pivot.rotation.x, -0.12, minf(1.0, delta * 5.0))
		_head_pivot.rotation.y = lerpf(_head_pivot.rotation.y, 0.0, minf(1.0, delta * 5.0))
	_blink_timer -= delta
	if _blink_timer <= 0.0 and _blink_duration <= 0.0:
		_blink_duration = 0.13
		_blink_timer = _rng.randf_range(2.5, 5.5)
	if _blink_duration > 0.0:
		_blink_duration = maxf(0.0, _blink_duration - delta)
	var blink_target := 0.15 if _blink_duration > 0.0 else 1.0
	for eye in _eyes:
		if eye is Node3D:
			(eye as Node3D).scale.y = lerpf((eye as Node3D).scale.y, blink_target, minf(1.0, delta * 30.0))

func set_camera_mode(is_isometric: bool) -> void:
	_iso_enabled = is_isometric
	if _iso_tween and _iso_tween.is_valid(): _iso_tween.kill()
	_iso_tween = create_tween().set_parallel(true)
	if is_isometric:
		_set_view_mode("third_person")
		_iso_tween.tween_property(_third_person_pivot, "rotation_degrees", Vector3(-60.0, 45.0, 0.0), 0.35)
		_iso_tween.tween_property(_third_person_spring, "spring_length", 18.0, 0.35)
	else:
		# restore chase defaults
		_iso_tween.tween_property(_third_person_pivot, "rotation_degrees", Vector3(-7.0, 0.0, 0.0), 0.35)
		_iso_tween.tween_property(_third_person_spring, "spring_length", 5.0, 0.35)

func _set_view_mode(mode: String) -> void:
	_view_mode = mode
	var first_person := mode == "first_person"
	if is_instance_valid(_camera):
		_camera.current = first_person
	if is_instance_valid(_third_person_camera):
		_third_person_camera.current = not first_person
	if _world_visual != null:
		_world_visual.visible = (not first_person) and not is_driving and not is_seated
	if _viewmodel != null:
		_viewmodel.visible = first_person

func get_view_forward() -> Vector3:
	var active_camera := _camera if _view_mode == "first_person" else _third_person_camera
	if not is_instance_valid(active_camera):
		return -global_transform.basis.z.normalized()
	return -active_camera.global_transform.basis.z.normalized()

func get_camera() -> Camera3D:
	var active_camera := _camera if _view_mode == "first_person" else _third_person_camera
	return active_camera if is_instance_valid(active_camera) else _camera

func is_isometric() -> bool:
	return _iso_enabled

func get_view_mode() -> String:
	return _view_mode

func set_input_enabled(enabled: bool) -> void:
	controls_enabled = enabled
	if not enabled:
		velocity.x = 0.0
		velocity.z = 0.0
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif is_inside_tree():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func enter_vehicle(vehicle_node: Node3D, seat_offset: Vector3 = Vector3(-0.38, 0.0, 0.05), exit_offset: Vector3 = Vector3(1.85, 0.0, 0.0)) -> void:
	if is_driving or not is_instance_valid(vehicle_node) or is_seated:
		return
	_drive_node = vehicle_node
	_drive_seat_offset = seat_offset
	_drive_exit_offset = exit_offset
	_drive_speed = 0.0
	is_driving = true
	activity = "driving"
	velocity = Vector3.ZERO
	_saved_transform = global_transform
	# Character sits inside the car: hide on-foot visual and disable body collision.
	if _world_visual != null:
		_world_visual.visible = false
	if _viewmodel != null:
		_viewmodel.visible = false
	if _collision != null:
		_collision.disabled = true
	if is_instance_valid(_camera_mount):
		_camera_mount.position = Vector3(-0.34, 1.02, 0.18)
	if is_instance_valid(_third_person_spring):
		_drive_saved_tp_spring = _third_person_spring.spring_length
		_third_person_spring.spring_length = 7.2

		# exclude car static bodies
		var st := [_drive_node]
		while st:
			var n = st.pop_back()
			if n is CollisionObject3D:
				_third_person_spring.add_excluded_object((n as CollisionObject3D).get_rid())
			for c in n.get_children(): st.append(c)
	if is_instance_valid(_third_person_pivot):
		_third_person_pivot.position = Vector3(0.0, 1.05, 0.0)
	# Default to first-person "inside car" view; V toggles to chase cam.
	_iso_enabled = false
	_set_view_mode("first_person")
	set_input_enabled(true)

func exit_vehicle() -> void:
	if not is_driving:
		return
	var exit_pos := global_position + _drive_exit_offset
	if is_instance_valid(_drive_node):
		exit_pos = _drive_node.global_transform * _drive_exit_offset
	exit_pos.y = 0.0
	global_position = exit_pos
	is_driving = false
	_drive_node = null
	_drive_speed = 0.0
	velocity = Vector3.ZERO
	activity = "idle"
	if _collision != null:
		_collision.disabled = false
	if is_instance_valid(_camera_mount):
		_camera_mount.position = Vector3(0.0, eye_height, 0.0)
	if is_instance_valid(_third_person_pivot):
		_third_person_pivot.position = Vector3(0.0, 1.48, 0.0)
	if is_instance_valid(_third_person_spring):
		_third_person_spring.spring_length = _drive_saved_tp_spring
	_iso_enabled = false
	_set_view_mode("third_person")
	if _world_visual != null:
		_world_visual.visible = true
		_world_visual.position = Vector3(0.0, 0.20, 0.0)
		_world_visual.rotation = Vector3.ZERO
	# let physics settle onto ground
	set_input_enabled(true)

func is_in_vehicle() -> bool:
	return is_driving and is_instance_valid(_drive_node)

func get_drive_node() -> Node3D:
	return _drive_node if is_in_vehicle() else null

func get_drive_exit_position() -> Vector3:
	if not is_in_vehicle():
		return global_position
	var p: Vector3 = _drive_node.global_transform * _drive_exit_offset
	p.y = 0.0
	return p

func _drive_physics(delta: float) -> void:
	if not is_in_vehicle():
		is_driving = false
		return
	var input_vector := Vector2.ZERO
	if controls_enabled:
		input_vector = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var accel_input := -input_vector.y
	var steer_input := input_vector.x
	var max_fwd := 12.5
	var max_rev := -4.8
	var target_speed := max_fwd * accel_input if accel_input >= 0.0 else max_rev * absf(accel_input)
	if absf(accel_input) > 0.01:
		var rate := 10.5 if accel_input > 0.0 else 13.5
		_drive_speed = move_toward(_drive_speed, target_speed, rate * delta)
	else:
		_drive_speed = move_toward(_drive_speed, 0.0, 5.8 * delta)
	if absf(_drive_speed) > 0.2:
		var steer_dir := 1.0 if _drive_speed >= 0.0 else -1.0
		var steer_factor := clampf(absf(_drive_speed) / max_fwd, 0.18, 1.0)
		_drive_node.rotate_y(-steer_input * 1.7 * delta * steer_dir * steer_factor)
	var forward := -_drive_node.global_transform.basis.z
	forward.y = 0.0
	if forward.length_squared() > 0.0001:
		forward = forward.normalized()
	var motion := forward * _drive_speed * delta
	var from := _drive_node.global_position + Vector3(0.0, 0.55, 0.0)
	var to := from + motion.normalized() * (motion.length() + 1.25) if motion.length() > 0.0001 else from
	var space := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(from, to, 1)
	query.collide_with_areas = false
	if space != null and motion.length() > 0.0001 and space.intersect_ray(query).is_empty() == false:
		_drive_speed = move_toward(_drive_speed, 0.0, 22.0 * delta)
	else:
		_drive_node.global_position += motion
	_spin_drive_wheels(_drive_speed, delta)
	var seat_world: Vector3 = _drive_node.global_transform * _drive_seat_offset
	global_position = seat_world
	velocity = Vector3.ZERO
	is_moving = absf(_drive_speed) > 0.35
	_animate_player(delta, absf(_drive_speed) > 7.5)
	_update_external_animation()


func _spin_drive_wheels(speed: float, delta: float) -> void:
	if not is_instance_valid(_drive_node):
		return
	var rot := speed * delta * 0.9
	var stack: Array = [_drive_node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is Node3D and str(n.name) == "Wheel":
			(n as Node3D).rotate_x(rot)
		for c in n.get_children():
			stack.append(c)
