extends SceneTree

const OUT := "/tmp/opencode/shots/"
const SHOTS := [
	{"name": "office-exterior.png", "pos": Vector3(0, 4.0, 54), "look": Vector3(0, 3.6, 38)},
	{"name": "office-lobby.png", "pos": Vector3(-10, 1.75, 29), "look": Vector3(0, 1.6, 8)},
	{"name": "office-lobby-south.png", "pos": Vector3(5.2, 1.85, 24.0), "look": Vector3(1.6, 1.3, 33.0)},
	{"name": "office-doors.png", "pos": Vector3(-13.8, 1.72, 14.5), "look": Vector3(-19.8, 2.6, 14.5)},
	{"name": "office-doors-north.png", "pos": Vector3(8.0, 1.72, -15.6), "look": Vector3(8.0, 2.7, -20.1)},
	{"name": "office-logo-exterior.png", "pos": Vector3(0, 4.4, 49.5), "look": Vector3(0, 5.0, 40.3)},
	{"name": "office-info-board.png", "pos": Vector3(0.0, 1.75, 38.8), "look": Vector3(0, 1.5, 34.2)},
	{"name": "office-board-front.png", "pos": Vector3(10.8, 1.55, 38.2), "look": Vector3(10.8, 1.5, 34.4)},
	{"name": "office-board-announce.png", "pos": Vector3(-10.8, 1.55, 38.2), "look": Vector3(-10.8, 1.5, 34.4)},
	{"name": "office-board-boardroom.png", "pos": Vector3(-14.2, 1.7, 17.8), "look": Vector3(-19.35, 1.5, 17.8)},
	{"name": "office-reception.png", "pos": Vector3(4.5, 1.75, 27.5), "look": Vector3(0, 1.9, 17.4)},
	{"name": "office-leadership.png", "pos": Vector3(8, 1.7, -21), "look": Vector3(8, 1.5, -32)},
	{"name": "office-frontend.png", "pos": Vector3(-29.5, 1.7, -2), "look": Vector3(-29.5, 1.4, -10)},
	{"name": "office-qa.png", "pos": Vector3(-6.5, 1.7, -2), "look": Vector3(-6.5, 1.4, -10)},
	{"name": "office-backend.png", "pos": Vector3(24, 1.7, -2), "look": Vector3(27, 1.4, -9)},
	{"name": "office-meeting.png", "pos": Vector3(-29.5, 1.7, 6), "look": Vector3(-29.5, 1.4, 14)},
	{"name": "office-api.png", "pos": Vector3(29, 1.7, 7), "look": Vector3(29, 1.4, 13)},
	{"name": "office-lounge.png", "pos": Vector3(9, 1.7, 27), "look": Vector3(9, 1.4, 34)},
	{"name": "office-archive.png", "pos": Vector3(-29.5, 1.7, 26), "look": Vector3(-29.5, 1.4, 33)},
	{"name": "office-owner-lounge.png", "pos": Vector3(-9.5, 1.8, 22.5), "look": Vector3(-11, 1.3, 34)},
	{"name": "office-owner-lounge-b.png", "pos": Vector3(-3.5, 1.7, 27.5), "look": Vector3(-14, 1.2, 33)},
	{"name": "office-character.png", "pos": Vector3(-4.6, 1.78, 17.5), "look": Vector3(0.3, 1.25, 13.55)},
	{"name": "office-char-face.png", "pos": Vector3(0.2, 2.2, 14.9), "look": Vector3(0.2, 2.18, 13.5)},
	{"name": "office-char-half.png", "pos": Vector3(1.6, 1.9, 15.1), "look": Vector3(0.2, 1.7, 13.6)},
]

func _spawn_cast(host: Node) -> Node3D:
	var factory := preload("res://scripts/character_factory.gd")
	var cast := Node3D.new()
	cast.name = "CaptureCast"
	# Palet dari EMPLOYEES (main.gd) supaya shot memakai warna gameplay sungguhan.
	var entries := [
		{"shirt": Color("#466d68"), "hair": Color("#28343b"), "skin": Color("#c89e84"), "pos": Vector3(-2.0, 0.19, 13.65)},
		{"shirt": Color("#8b6d83"), "hair": Color("#3a3036"), "skin": Color("#a87854"), "pos": Vector3(0.2, 0.19, 13.3)},
		{"shirt": Color("#b17d62"), "hair": Color("#40352d"), "skin": Color("#e0b698"), "pos": Vector3(2.2, 0.19, 13.7)},
	]
	for entry in entries:
		var pivot := Node3D.new()
		pivot.position = entry["pos"]
		pivot.rotation.y = PI # karakter menghadap -z, diputar agar wajah ke kamera
		cast.add_child(pivot)
		factory.build(pivot, entry["shirt"], entry["hair"], "CAST", "cast-test", entry["skin"])
	host.add_child(cast)
	return cast

func _initialize() -> void:
	call_deferred("_run")

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
			# Volumetric fog membuat shot ruangan tampak milky; matikan hanya untuk capture.
			child.environment.volumetric_fog_enabled = false
	var cam := Camera3D.new()
	cam.fov = 66.0
	cam.near = 0.05
	cam.far = 200.0
	root.add_child(cam)
	var cast_root: Node3D = null
	var prev_char := false
	for shot in SHOTS:
		var char_shot: bool = String(shot["name"]).begins_with("office-char")
		if char_shot and not prev_char and cast_root == null:
			cast_root = _spawn_cast(main)
			for i in range(5):
				await process_frame
		if prev_char and not char_shot and cast_root != null:
			cast_root.queue_free()
			cast_root = null
			for i in range(10):
				await process_frame
		prev_char = char_shot
		cam.global_position = shot["pos"]
		cam.look_at(shot["look"], Vector3.UP)
		cam.current = true
		for i in range(10):
			await process_frame
		var image := root.get_texture().get_image()
		image.save_png(OUT + shot["name"])
		print("CAPTURE: " + shot["name"])
	print("CAPTURE_OK")
	quit()
