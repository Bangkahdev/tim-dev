extends SceneTree
func _initialize() -> void:
	var m := TextMesh.new()
	print("HAS depth: ", m.get("depth") != null)
	for p in m.get_property_list():
		if str(p.name) in ["depth", "pixel_size", "font_size", "text", "curve_step", "horizontal_alignment"]:
			print(p.name, " = ", p.type, " value=", m.get(p.name))
	quit()
