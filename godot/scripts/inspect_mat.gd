extends SceneTree
func _initialize() -> void:
	var m := StandardMaterial3D.new()
	for p in m.get_property_list():
		var n := str(p.name)
		if "subsurf" in n or "normal" in n and "enabled" in n or "bump" in n:
			print(n, " = ", m.get(n))
	quit()
