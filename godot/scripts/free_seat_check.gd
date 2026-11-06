extends SceneTree

## Headless check sistem duduk bebas + pintu interaktif:
## - office_environment mendaftarkan semua kursi (kantor/rapat/sofa)
## - setiap kursi & pintu muncul sebagai interactable di main.gd
## - duduk/berdiri bekerja untuk contoh seat tiap jenis
## - pintu toggle: daun pintu beranimasi ke yaw tertutup lalu terbuka
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

	# --- Registry kursi ---
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

	# --- Geometri kursi kantor lengkap (dudukan & sandaran) ---
	var chair_acc := [0, 0]  # [cushions, office_chair_roots]
	_collect_chair_parts(main, chair_acc)
	var cushions: int = chair_acc[0]
	var office_chair_roots: int = chair_acc[1]
	if cushions >= office_chair_roots:
		print("PASS chair cushions present: %d seats padded on %d chairs" % [cushions, office_chair_roots])
	else:
		print("FAIL chair cushions %d < expected for %d chairs" % [cushions, office_chair_roots])
		failures += 1

	# --- Interactable kursi & pintu ---
	var seat_interactables := 0
	var door_interactables := 0
	for item in main._interactables:
		if str(item.get("kind", "")) in ["office", "meeting", "sofa"]:
			seat_interactables += 1
		elif str(item.get("kind", "")) == "door":
			door_interactables += 1
	if seat_interactables == seats.size():
		print("PASS all %d seats interactable" % seat_interactables)
	else:
		print("FAIL seats %d registered but %d interactable" % [seats.size(), seat_interactables])
		failures += 1

	# --- Registry pintu & daun ---
	var door_count: int = 0
	if "doors" in office_world:
		door_count = (office_world.doors as Array).size()
	var node_acc := [0, 0]  # [leaves, signs]
	_count_nodes(main, node_acc)
	var leaves: int = node_acc[0]
	var signs: int = node_acc[1]
	if door_count >= 18:
		print("PASS doors registered: %d" % door_count)
	else:
		print("FAIL doors registered: %d" % door_count)
		failures += 1
	if leaves >= 36:
		print("PASS door leaves: %d, sign plates: %d" % [leaves, signs])
	else:
		print("FAIL door leaves only %d" % leaves)
		failures += 1

	# --- Toggle pintu (interaktif buka/tutup) ---
	var door_target: Dictionary = {}
	for item in main._interactables:
		if str(item.get("kind", "")) == "door":
			door_target = item
			break
	if door_target.is_empty():
		print("FAIL door interactable missing")
		failures += 1
	else:
		var idx: int = int(door_target.get("door_index", -1))
		var door: Dictionary = office_world.doors[idx]
		var leaf_node: Node = door["leaves"][0]["node"]
		var closed_yaw: float = float(door["leaves"][0]["closed"])
		# Awal pintu terbuka ajar; toggle sekali -> menutup.
		main._toggle_free_door(door_target)
		for i in range(90):
			await process_frame
		if absf(leaf_node.rotation.y - closed_yaw) < 0.06:
			print("PASS door closes to yaw %.2f (got %.2f)" % [closed_yaw, leaf_node.rotation.y])
		else:
			print("FAIL door close yaw %.2f expected %.2f" % [leaf_node.rotation.y, closed_yaw])
			failures += 1
		main._toggle_free_door(door_target)
		for i in range(90):
			await process_frame
		var open_yaw: float = float(door["leaves"][0]["open"])
		if absf(leaf_node.rotation.y - open_yaw) < 0.06:
			print("PASS door reopens to yaw %.2f (got %.2f)" % [open_yaw, leaf_node.rotation.y])
		else:
			print("FAIL door open yaw %.2f expected %.2f" % [leaf_node.rotation.y, open_yaw])
			failures += 1

	# --- Duduk tiap jenis seat (office, meeting, sofa) ---
	if main.player == null or not is_instance_valid(main.player):
		print("FAIL player missing")
		failures += 1
		print("RESULT failures=%d" % failures)
		quit()
		return
	for wanted_kind in ["office", "meeting", "sofa"]:
		var seat_target: Dictionary = {}
		for item in main._interactables:
			if str(item.get("kind", "")) == wanted_kind:
				seat_target = item
				break
		if seat_target.is_empty():
			print("FAIL %s seat interactable missing" % wanted_kind)
			failures += 1
			continue
		main._take_free_seat(seat_target)
		for i in range(15):
			await process_frame
		var ok_sit: bool = main.player.is_seated and main.player.global_position.distance_to(Vector3(seat_target["seat"])) < 0.45
		if ok_sit:
			print("PASS sit %s seat" % wanted_kind)
		else:
			print("FAIL sit %s seat (is_seated=%s pos=%s seat=%s)" % [
				wanted_kind, str(main.player.is_seated), str(main.player.global_position), str(seat_target["seat"])])
			failures += 1
		main._on_player_interact()
		for i in range(15):
			await process_frame
		if not main.player.is_seated:
			print("PASS stand up from %s seat" % wanted_kind)
		else:
			print("FAIL stand up from %s seat" % wanted_kind)
			failures += 1

	print("RESULT failures=%d" % failures)
	quit()

## Hitung node daun pintu & plakat via nama unik. acc = [leaves, signs].
func _count_nodes(node: Node, acc: Array) -> void:
	var node_name := String(node.name)
	if node_name.contains("DoorLeaf_"):
		acc[0] += 1
	elif node_name.contains("Door_sign_plate_"):
		acc[1] += 1
	for child in node.get_children():
		_count_nodes(child, acc)

## Kumpulkan kusen kursi kantor: root "OfficeChair" + child mesh "Chair cushion".
## acc = [cushions, office_chair_roots].
func _collect_chair_parts(node: Node, acc: Array) -> void:
	var node_name := String(node.name)
	if node_name.contains("OfficeChair_"):
		acc[1] += 1
	if node_name.begins_with("Chair_cushion") or node_name.contains("Chair_cushion"):
		acc[0] += 1
	for child in node.get_children():
		_collect_chair_parts(child, acc)
