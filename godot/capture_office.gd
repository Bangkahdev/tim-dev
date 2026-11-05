extends SceneTree

const OUT := "C:/Users/atha/AppData/Local/Temp/opencode/shots/"
const SHOTS := [
	{"name": "office-exterior.png", "pos": Vector3(0, 3.2, 54), "look": Vector3(0, 2.8, 38)},
	{"name": "office-lobby.png", "pos": Vector3(-10, 1.75, 29), "look": Vector3(0, 1.6, 8)},
	{"name": "office-reception.png", "pos": Vector3(4.5, 1.75, 27.5), "look": Vector3(0, 1.5, 19)},
	{"name": "office-leadership.png", "pos": Vector3(8, 1.7, -21), "look": Vector3(8, 1.5, -32)},
	{"name": "office-frontend.png", "pos": Vector3(-29.5, 1.7, -2), "look": Vector3(-29.5, 1.4, -10)},
	{"name": "office-qa.png", "pos": Vector3(-6.5, 1.7, -2), "look": Vector3(-6.5, 1.4, -10)},
	{"name": "office-backend.png", "pos": Vector3(24, 1.7, -2), "look": Vector3(27, 1.4, -9)},
	{"name": "office-meeting.png", "pos": Vector3(-29.5, 1.7, 6), "look": Vector3(-29.5, 1.4, 14)},
	{"name": "office-api.png", "pos": Vector3(29, 1.7, 7), "look": Vector3(29, 1.4, 13)},
	{"name": "office-lounge.png", "pos": Vector3(9, 1.7, 27), "look": Vector3(9, 1.4, 34)},
	{"name": "office-archive.png", "pos": Vector3(-29.5, 1.7, 26), "look": Vector3(-29.5, 1.4, 33)},
]

func _initialize() -> void:
	call_deferred("_run")

func _hide_labels(node: Node) -> void:
	for child in node.get_children():
		if child is Label3D:
			child.visible = false
		else:
			_hide_labels(child)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var scene: PackedScene = load("res://scenes/main.tscn")
	print("CAPTURE: instancing")
	var main = scene.instantiate()
	root.add_child(main)
	print("CAPTURE: ready")
	for i in range(45):
		await process_frame
	if is_instance_valid(main.get("_hud_layer")):
		main.get("_hud_layer").visible = false
	if is_instance_valid(main.get("_company_ui")):
		main.get("_company_ui").visible = false
	for child in main.get_children():
		if child is WorldEnvironment and child.environment != null:
			child.environment.tonemap_exposure = 0.62
			child.environment.ambient_light_energy = 0.55
			child.environment.glow_enabled = false
	var cam := Camera3D.new()
	cam.fov = 66.0
	cam.near = 0.05
	cam.far = 200.0
	root.add_child(cam)
	var index := 0
	for shot in SHOTS:
		cam.global_position = shot["pos"]
		cam.look_at(shot["look"], Vector3.UP)
		cam.current = true
		for i in range(10):
			await process_frame
		var image := root.get_texture().get_image()
		image.save_png(OUT + shot["name"])
		print("CAPTURE: " + shot["name"])
		index += 1
		if index == 1:
			_hide_labels(main)
	print("CAPTURE_OK")
	quit()
