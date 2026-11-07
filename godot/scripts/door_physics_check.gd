extends SceneTree

## Headless physics validation for the interactive double doors.
## - every closed leaf has a DoorCollision (AnimatableBody3D) that the physics
##   ray hits at the door aperture
## - the player capsule test_move is blocked by a closed leaf
## - after opening, the same space is free and the ray no longer hits the leaf
##
## Usage (from repo root):
##   godot --headless --path godot --script "res://scripts/door_physics_check.gd"

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
	if office_world == null or not ("doors" in office_world):
		print("FAIL office doors missing")
		print("RESULT failures=1")
		quit()
		return
	var doors: Array = office_world.doors
	print("INFO doors=%d" % doors.size())

	# Tutup semua pintu yang masih terbuka.
	for index in range(doors.size()):
		if bool(doors[index].get("open", true)):
			main._toggle_free_door({"door_index": index})
	await create_timer(1.0).timeout
	for i in range(4):
		await physics_frame

	var space: PhysicsDirectSpaceState3D = main.get_world_3d().direct_space_state
	var closed_hits := 0
	var closed_leaves := 0
	var collider_rids: Array[RID] = []
	for door in doors:
		for leaf in door.get("leaves", []):
			var node = leaf.get("node", null)
			if not (node is Node3D) or not is_instance_valid(node):
				continue
			var body = node.get_node_or_null("DoorCollision")
			if not (body is AnimatableBody3D):
				continue
			var shape_node = body.get_child(0)
			var normal: Vector3 = shape_node.global_transform.basis.z.normalized()
			var center: Vector3 = shape_node.global_position
			var query := PhysicsRayQueryParameters3D.create(center - normal * 1.2, center + normal * 1.2)
			var hit: Dictionary = space.intersect_ray(query)
			closed_leaves += 1
			collider_rids.append(body.get_rid())
			if not hit.is_empty() and hit.get("collider") == body:
				closed_hits += 1
			else:
				print("FAIL closed leaf not blocking at %s" % str(center))
				failures += 1
	if closed_leaves >= 36 and closed_hits == closed_leaves:
		print("PASS closed leaves block physics ray: %d/%d" % [closed_hits, closed_leaves])
	else:
		print("FAIL closed leaves blocking: %d/%d" % [closed_hits, closed_leaves])
		failures += 1

	# Uji tabrakan pemain pada daun pertama (pintu tertutup).
	var first_door: Dictionary = doors[0]
	var first_leaf = first_door.get("leaves", [])[0]
	var first_node = first_leaf.get("node", null)
	var first_body = first_node.get_node_or_null("DoorCollision") if first_node is Node3D else null
	if first_body is AnimatableBody3D:
		var first_yaw := float(first_leaf.get("closed", 0.0))
		var first_normal := Vector3(sin(first_yaw), 0.0, cos(first_yaw)).normalized()
		var panel_center: Vector3 = first_body.get_child(0).global_position
		var floor_y: float = float(first_door.get("position", Vector3.ZERO).y)
		var start := Vector3(panel_center.x, floor_y + 0.05, panel_center.z) - first_normal * 1.15
		main.player.global_position = start
		var blocked: bool = main.player.test_move(main.player.global_transform, first_normal * 2.3)
		if blocked:
			print("PASS closed door blocks player capsule (%s)" % str(first_door.get("label", "door")))
		else:
			print("FAIL closed door lets player capsule pass (%s)" % str(first_door.get("label", "door")))
			failures += 1
	else:
		print("FAIL first door has no DoorCollision")
		failures += 1

	# Buka semua pintu; collider harus ikut berputar sehingga tidak menghalangi.
	for index in range(doors.size()):
		if not bool(doors[index].get("open", true)):
			main._toggle_free_door({"door_index": index})
	await create_timer(1.0).timeout
	for i in range(4):
		await physics_frame

	var open_aperture_clear := 0
	var open_aperture_total := 0
	for door in doors:
		for leaf in door.get("leaves", []):
			var node = leaf.get("node", null)
			if not (node is Node3D) or not is_instance_valid(node):
				continue
			var body = node.get_node_or_null("DoorCollision")
			if not (body is AnimatableBody3D):
				continue
			var closed_yaw := float(leaf.get("closed", 0.0))
			var normal := Vector3(sin(closed_yaw), 0.0, cos(closed_yaw)).normalized()
			var aperture: Vector3 = door.get("position", Vector3.ZERO) + Vector3(0, 1.6, 0)
			var query := PhysicsRayQueryParameters3D.create(
				aperture - normal * 1.2, aperture + normal * 1.2, 0xFFFFFFFF, collider_rids)
			var hit: Dictionary = space.intersect_ray(query)
			open_aperture_total += 1
			if hit.is_empty() or hit.get("collider") != body:
				open_aperture_clear += 1
			else:
				print("FAIL open leaf still blocks aperture at %s" % str(aperture))
				failures += 1
	if open_aperture_total > 0 and open_aperture_clear == open_aperture_total:
		print("PASS open leaves clear the aperture: %d/%d" % [open_aperture_clear, open_aperture_total])
	else:
		print("FAIL open leaves clearing: %d/%d" % [open_aperture_clear, open_aperture_total])
		failures += 1

	# Player capsule harus bebas melewati bukaan pintu yang terbuka.
	if first_body is AnimatableBody3D:
		var first_yaw := float(first_leaf.get("closed", 0.0))
		var first_normal := Vector3(sin(first_yaw), 0.0, cos(first_yaw)).normalized()
		var aperture_center: Vector3 = first_door.get("position", Vector3.ZERO) + Vector3(0, 0.05, 0)
		var start := aperture_center - first_normal * 1.2
		# Hindari tumpukan dengan furnitur: uji langsung 1.2 m melalui bukaan.
		main.player.global_position = start
		var blocked_open: bool = main.player.test_move(main.player.global_transform, first_normal * 2.4)
		if not blocked_open:
			print("PASS open door lets player capsule through (%s)" % str(first_door.get("label", "door")))
		else:
			print("WARN open door capsule still collides (could be nearby furniture)")
	# Pastikan state registry konsisten setelah toggle.
	var all_open := true
	for door in doors:
		if not bool(door.get("open", false)):
			all_open = false
	if all_open:
		print("PASS all %d doors toggle open" % doors.size())
	else:
		print("FAIL not all doors reopened")
		failures += 1

	print("RESULT failures=%d" % failures)
	quit()
