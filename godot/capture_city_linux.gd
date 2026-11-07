extends SceneTree

## City / town verification shots.
const OUT := "/tmp/opencode/shots/"
const SHOTS := [
	{"name": "city-aerial.png", "pos": Vector3(60, 120, 190), "look": Vector3(80, 0, 60)},
	{"name": "city-boulevard.png", "pos": Vector3(-30, 8, 90), "look": Vector3(60, 1.5, 55)},
	{"name": "city-spine.png", "pos": Vector3(104, 7, 150), "look": Vector3(104, 1.5, 55)},
	{"name": "city-residential.png", "pos": Vector3(58, 18, 150), "look": Vector3(58, 0, 76)},
	{"name": "city-commercial.png", "pos": Vector3(170, 24, 120), "look": Vector3(132, 0, 58)},
	{"name": "city-mall-front.png", "pos": Vector3(180, 7, 151), "look": Vector3(180, 3, 122)},
	{"name": "city-mall-rear.png", "pos": Vector3(180, 8, 58), "look": Vector3(180, 1, 79)},
	{"name": "city-promenade.png", "pos": Vector3(142, 4, 150), "look": Vector3(142, 1.5, 88)},
	{"name": "city-mansion.png", "pos": Vector3(132, 14, 40), "look": Vector3(132, 0, 0)},
]

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main = scene.instantiate()
	root.add_child(main)
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
			child.environment.volumetric_fog_enabled = false
	var cam := Camera3D.new()
	cam.fov = 62.0
	cam.near = 0.1
	cam.far = 420.0
	root.add_child(cam)
	for shot in SHOTS:
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
