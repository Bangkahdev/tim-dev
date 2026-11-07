extends SceneTree
func _initialize() -> void:
	call_deferred("_run")
func _run() -> void:
	var scene: PackedScene = load("res://scenes/main.tscn")
	var main = scene.instantiate()
	root.add_child(main)
	for i in range(45):
		await process_frame
	var office = main.get_node("BangkahHeadquarters")
	var stations := []
	for item in main._interactables:
		if item.has("workstation_id"):
			stations.append({"id": item.get("id"), "seat": item.get("seat"), "y": item.get("position").y})
	print("STATIONS=%d" % stations.size())
	for s in stations:
		var best_dist := 999.0
		var best_label := ""
		for seat in office.seats:
			if str(seat.get("kind", "")) != "office":
				continue
			var d: float = (seat.get("position", Vector3.ZERO) as Vector3).distance_to(s["seat"])
			if d < best_dist:
				best_dist = d
				best_label = str(seat.get("label"))
		print("STATION %-22s seat=%s y=%.2f nearest='%s' dist=%.3f" % [str(s["id"]), str(s["seat"]), s["y"], best_label, best_dist])
	# juga cetak beberapa kursi per lantai
	var shown := 0
	for seat in office.seats:
		if str(seat.get("kind", "")) == "office" and shown < 8:
			print("SEAT '%s' pos=%s" % [str(seat.get("label")), str(seat.get("position"))])
			shown += 1
	quit()
