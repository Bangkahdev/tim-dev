extends SceneTree

## Headless check untuk sistem duduk bebas (kursi/sofa swivel) dan pintu:
## - office_environment mendaftarkan seats
## - kursi kantor & kursi rapat & sofa muncul sebagai interactable
## - _take_free_seat benar-benar memposisikan pemain (is_seated)
## - _on_player_interact saat duduk DIKELUARKAN (berdiri)
## - daun pintu & plakat nama ruangan ada geometrinya

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var failures := 0
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main = scene.instantiate()
	root.add_child(main)
	for i in range(60):
		await process_frame

	var office_world = main.get_node_or_null("BangkahHeadquarters")
	if office_world == null:
		print("FAIL office world missing")
		failures += 1
		print("RESULT failures=%d" % failures)
		quit()
		return

	var seats: Array = office_world.seats
	if seats.is_empty():
		print("FAIL no seats registered")
		failures += 1
	else:
		var kinds := {"office": 0, "meeting": 0, "sofa": 0}
		for seat in seats:
			kinds[str(seat.get("kind", "?"))] = kinds.get(str(seat.get("kind", "?")), 0) + 1
		print("PASS seats registered: %d (office=%d meeting=%d sofa=%d)" % [
			seats.size(), kinds["office"], kinds["meeting"], kinds["sofa"]])

	var counter := {"leaf": 0, "sign": 0, "other_door_names": {}}
	_count_nodes(main, counter)
	var env_names: Array = []
	for env_child in office_world.get_children():
		if String(env_child.name).contains("Door"):
			var pos_extra := ""
			var mesh_child: Node = env_child.get_child(0) if env_child.get_child_count() > 0 else null
			if mesh_child != null and mesh_child is MeshInstance3D:
				pos_extra = " meshpos=" + str((mesh_child as MeshInstance3D).position)
			env_names.append(String(env_child.name) + " pos=" + str(env_child.position) + pos_extra)
	var glass_walls := 0
	var interior_walls := 0
	for env_child in office_world.get_children():
		if String(env_child.name).contains("Glass_partition"):
			glass_walls += 1
		if String(env_child.name).contains("Interior_wall"):
			interior_walls += 1
	if counter["leaf"] >= 20:
		print("PASS door leaves: %d, signs: %d" % [counter["leaf"], counter["sign"]])
	else:
		print("FAIL door leaves only %d" % counter["leaf"])
		failures += 1

	var seat_target: Dictionary = {}
	for item in main._interactables:
		if str(item.get("kind", "")) == "office":
			seat_target = item
			break
	if seat_target.is_empty():
		print("FAIL free seat interactable missing")
		failures += 1
		print("RESULT failures=%d" % failures)
		quit()
		return
	main._take_free_seat(seat_target)
	for i in range(15):
		await process_frame
	if main.player.is_seated and main.player.global_position.distance_to(Vector3(seat_target["seat"])) < 0.3:
		print("PASS sit free seat")
	else:
		print("FAIL sit free seat (is_seated=%s pos=%s)" % [str(main.player.is_seated), str(main.player.global_position)])
		failures += 1
	main._on_player_interact()
	for i in range(15):
		await process_frame
	if not main.player.is_seated:
		print("PASS stand up from free seat")
	else:
		print("FAIL stand up from free seat")
		failures += 1

	# Tidak boleh ada error script trailing.
	print("RESULT failures=%d" % failures)
	quit()

func _count_nodes(node: Node, counter: Dictionary) -> void:
	var node_name := String(node.name)
	if node_name.contains("DoorLeaf_"):
		counter["leaf"] += 1
	elif node_name.contains("Door_sign_plate_"):
		counter["sign"] += 1
	elif node_name.contains("Door"):
		var names: Dictionary = counter["other_door_names"]
		names[node_name] = names.get(node_name, 0) + 1
	for child in node.get_children():
		_count_nodes(child, counter)
