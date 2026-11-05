extends Node3D

class_name WorkstationSystem

## Moves the Owner from standing in front of a desk to a seated workstation
## view without reloading the scene. The desktop UI is rendered by
## desktop_ui.gd; this node only owns the physical transition and camera.

signal entered(workstation_id: String)
signal exited(workstation_id: String)

const SEAT_TWEEN_SECONDS := 0.55

var _camera: Camera3D
var _player: Node3D
var _active_id: String = ""
var _look_target: Vector3 = Vector3.ZERO
var _tween: Tween

func _ready() -> void:
	_camera = Camera3D.new()
	_camera.name = "WorkstationCamera"
	_camera.fov = 71.0
	_camera.near = 0.05
	_camera.far = 220.0
	_camera.current = false
	add_child(_camera)
	set_process(false)

func is_active() -> bool:
	return not _active_id.is_empty()

func active_workstation_id() -> String:
	return _active_id

func enter(player: Node3D, workstation_id: String, seat_position: Vector3,
		seat_yaw: float, camera_position: Vector3, camera_target: Vector3) -> void:
	if is_active() or player == null:
		return
	_player = player
	_active_id = workstation_id
	_look_target = camera_target

	var start_position := camera_position
	var player_camera: Camera3D = player.get_camera()
	if is_instance_valid(player_camera):
		start_position = player_camera.global_position

	player.sit_at(seat_position, seat_yaw)
	_camera.global_position = start_position
	_camera.current = true
	_camera.look_at(_look_target, Vector3.UP)
	set_process(true)

	if is_instance_valid(_tween):
		_tween.kill()
	_tween = create_tween()
	_tween.set_trans(Tween.TRANS_CUBIC)
	_tween.set_ease(Tween.EASE_OUT)
	_tween.tween_property(_camera, "global_position", camera_position, SEAT_TWEEN_SECONDS)
	entered.emit(workstation_id)

func exit() -> void:
	if not is_active():
		return
	var workstation_id := _active_id
	_active_id = ""
	set_process(false)
	if is_instance_valid(_tween):
		_tween.kill()
	if is_instance_valid(_player):
		_player.stand_up()
		var player_camera: Camera3D = _player.get_camera()
		if is_instance_valid(player_camera):
			player_camera.current = true
	_player = null
	_camera.current = false
	exited.emit(workstation_id)

func _process(_delta: float) -> void:
	if is_active():
		_camera.look_at(_look_target, Vector3.UP)
