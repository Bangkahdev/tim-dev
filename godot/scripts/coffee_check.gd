extends SceneTree

## Headless validation for the pantry coffee flow:
## - coffee station interactable exists, lounge/pantry drop points exist
## - taking coffee attaches one cup to the player (never duplicate)
## - prompt tells the player when the cup is in hand
## - placing drops a static cup at the table/bar and clears the carried state
## - placing without coffee is rejected without spawning a cup
##
## Usage (from repo root):
##   godot --headless --path godot --script "res://scripts/coffee_check.gd"

func _count_cups(node: Node) -> int:
	var count := 0
	if str(node.name).begins_with("CoffeeCup"):
		count += 1
	for child in node.get_children():
		count += _count_cups(child)
	return count

func _find_interactable(main, id: String) -> Dictionary:
	for item in main._interactables:
		if str(item.get("id", "")) == id:
			return item
	return {}

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var failures := 0
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main = scene.instantiate()
	root.add_child(main)
	for i in range(60):
		await process_frame

	var station := _find_interactable(main, "coffee")
	var lounge := _find_interactable(main, "coffee_lounge_table")
	var pantry := _find_interactable(main, "coffee_pantry_bar")
	if not station.is_empty() and not lounge.is_empty() and not pantry.is_empty():
		print("PASS coffee station and 2 drop points registered")
	else:
		print("FAIL coffee interactables missing: station=%s lounge=%s pantry=%s" % [
			str(not station.is_empty()), str(not lounge.is_empty()), str(not pantry.is_empty())])
		failures += 1
		print("RESULT failures=%d" % failures)
		quit()
		return

	# Prompt sebelum membawa kopi: tawaran mengambil kopi.
	main.player.global_position = Vector3(22.5, 0.05, 33.0)
	main.player.rotation.y = PI
	await process_frame
	main._update_interaction_prompt()
	if "kopi" in main._prompt_label.text.to_lower() or "coffee" in main._prompt_label.text.to_lower():
		print("PASS prompt offers coffee at station: '%s'" % main._prompt_label.text)
	else:
		print("FAIL prompt at station: '%s'" % main._prompt_label.text)
		failures += 1

	# Ambil kopi.
	var cups_before := _count_cups(main)
	main._take_coffee()
	var cups_after := _count_cups(main)
	if main._coffee_carried and cups_after == cups_before + 1:
		print("PASS taking coffee attaches exactly one cup")
	else:
		print("FAIL take coffee carried=%s cups=%d→%d" % [
			str(main._coffee_carried), cups_before, cups_after])
		failures += 1
	if is_instance_valid(main._coffee_cup) and main._coffee_cup.get_parent() == main.player:
		print("PASS carried cup is parented to the player")
	else:
		print("FAIL carried cup parent/instance invalid")
		failures += 1

	# Ambil lagi tidak boleh menduplikasi cangkir.
	main._take_coffee()
	if _count_cups(main) == cups_after and main._coffee_carried:
		print("PASS second take does not duplicate the cup")
	else:
		print("FAIL second take duplicated cup")
		failures += 1

	# Prompt saat membawa kopi berubah menjadi arahan menaruh.
	main._update_interaction_prompt()
	if "membawa kopi" in main._prompt_label.text.to_lower():
		print("PASS prompt switches to carrying hint: '%s'" % main._prompt_label.text)
	else:
		print("FAIL carrying prompt: '%s'" % main._prompt_label.text)
		failures += 1

	# Taruh di meja lounge.
	var lounge_drop: Vector3 = lounge.get("drop_position", Vector3.ZERO)
	main._place_coffee(lounge)
	await process_frame
	var placed_node: Node3D = null
	for child in main.get_children():
		if child is Node3D and str(child.name).begins_with("CoffeeCup") and child.global_position.distance_to(lounge_drop) < 0.2:
			placed_node = child
	if not main._coffee_carried and placed_node != null:
		print("PASS coffee placed on lounge table at %s" % str(placed_node.global_position))
	else:
		print("FAIL place on lounge: carried=%s placed=%s" % [
			str(main._coffee_carried), str(placed_node != null)])
		failures += 1
	if not is_instance_valid(main._coffee_cup):
		print("PASS carried cup removed after placement")
	else:
		print("FAIL carried cup still valid after placement")
		failures += 1

	# Taruh tanpa membawa kopi ditolak dan tidak menambah cangkir.
	var cups_now := _count_cups(main)
	main._place_coffee(pantry)
	await process_frame
	if _count_cups(main) == cups_now:
		print("PASS placing without coffee spawns nothing")
	else:
		print("FAIL placing without coffee spawned a cup")
		failures += 1

	# Ambil lagi lalu taruh di bar pantry.
	main._take_coffee()
	main._place_coffee(pantry)
	await process_frame
	var pantry_drop: Vector3 = pantry.get("drop_position", Vector3.ZERO)
	var found_bar := false
	for child in main.get_children():
		if child is Node3D and str(child.name).begins_with("CoffeeCup") and child.global_position.distance_to(pantry_drop) < 0.2:
			found_bar = true
	if found_bar and not main._coffee_carried:
		print("PASS coffee placed on pantry bar at %s" % str(pantry_drop))
	else:
		print("FAIL place on pantry bar (carried=%s drop=%s)" % [str(main._coffee_carried), str(pantry_drop)])
		failures += 1

	print("RESULT failures=%d" % failures)
	quit()
