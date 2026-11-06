extends Node3D

## Design tokens / constants used across the office build. Raised ceiling
## heights keep first-person sightlines airy instead of cramped.
const WALL_H := 5.6			# exterior wall height
const PART_H := 5.30		# interior partition glass height
const CEIL_Y := 5.45		# acoustic ceiling panel plane
const DOOR_H := 3.02		# door opening height
const DOOR_W := 2.9			# door opening width

# Procedural interior for Bangkah HQ. All objects are native Godot meshes so the
# project opens without paid asset packs or external downloads.

var _materials: Dictionary = {}
var _material_cache: Dictionary = {}
# Registrasi titik makan duduk (kursi/sofa) untuk sistem interaksi di main.gd.
# Isi: {"position": Vector3, "yaw": float, "kind": String, "pivot": Node3D or null}
var seats: Array[Dictionary] = []
# Registrasi pintu interaktif: {"position", "label", "open", "leaves": [{"node", "closed", "open"}]}
var doors: Array[Dictionary] = []

const MAT := {
	"concrete": Color("#b0bab3"),
	"floor": Color("#cdcbc4"),
	"wall": Color("#eeebe2"),
	"wall_warm": Color("#e8e0d0"),
	"dark_wall": Color("#2d4438"),
	"accent_wall": Color("#3a5a4a"),
	"glass": Color(0.48, 0.66, 0.68, 0.20),
	"glass_tinted": Color(0.40, 0.56, 0.62, 0.28),
	"wood": Color("#9a7958"),
	"wood_light": Color("#cbac88"),
	"wood_dark": Color("#6b5238"),
	"metal": Color("#5a6862"),
	"metal_brushed": Color("#6e7a74"),
	"fabric": Color("#82978c"),
	"fabric_warm": Color("#a07e62"),
	"screen": Color("#1e3239"),
	"green": Color("#6f9275"),
	"gold": Color("#c5a366"),
	"gold_bright": Color("#d4b878"),
	"leather": Color("#5a4838"),
	"marble": Color("#dcd8cc"),
	"plant_dark": Color("#5a7a60"),
	"plant_light": Color("#7ba380"),
}

func build() -> void:
	_build_site()
	_build_shell()
	_build_room_partitions()
	_build_room_floors()
	_build_ceiling_and_lighting()
	_build_reception()
	_build_owner_suite()
	_build_secretary_office()
	_build_management_offices()
	_build_engineering_floor()
	_build_meeting_room()
	_build_api_lab()
	_build_archive_and_print()
	_build_pantry_and_lounge()
	_build_free_seating()
	_build_information_boards()
	_build_accent_walls()
	_build_corridor_details()
	_build_office_accessories()
	_build_landscape()
	_add_dust_particles()

func _mat(color: Color, roughness: float = 0.78, metallic: float = 0.0, transparent: bool = false, emission: Color = Color.BLACK) -> StandardMaterial3D:
	var key := "%s|%.2f|%.2f|%s|%s" % [color.to_html(true), roughness, metallic, str(transparent), emission.to_html(true)]
	if _materials.has(key):
		return _materials[key]
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	material.metallic = metallic
	# Proper specular mode for realistic light response on all surfaces.
	material.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	if transparent:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_ALWAYS
	if emission != Color.BLACK:
		material.emission_enabled = true
		material.emission = emission
		material.emission_energy_multiplier = 0.65
	_materials[key] = material
	return material

func _create_noise_texture(size: int, base: Color, strength: float) -> ImageTexture:
	var image := Image.create(size, size, false, Image.FORMAT_RGB8)
	for y in range(size):
		for x in range(size):
			var n1: float = (randf() - 0.5) * strength
			var n2: float = (randf() - 0.5) * strength * 0.5
			var n: float = n1 + n2
			var r: float = clamp(base.r + n, 0.0, 1.0)
			var g: float = clamp(base.g + n * 0.96, 0.0, 1.0)
			var b: float = clamp(base.b + n * 0.94, 0.0, 1.0)
			image.set_pixel(x, y, Color(r, g, b))
	var texture := ImageTexture.new()
	texture.set_image(image)
	return texture

func _create_grid_texture(size: int, color_a: Color, color_b: Color, cell: int) -> ImageTexture:
	var image := Image.create(size, size, false, Image.FORMAT_RGB8)
	for y in range(size):
		for x in range(size):
			var use_a := (x % cell < cell / 2) == (y % cell < cell / 2)
			var edge_noise := (randf() - 0.5) * 0.03
			if use_a:
				image.set_pixel(x, y, Color(
					clamp(color_a.r + edge_noise, 0.0, 1.0),
					clamp(color_a.g + edge_noise, 0.0, 1.0),
					clamp(color_a.b + edge_noise, 0.0, 1.0)
				))
			else:
				image.set_pixel(x, y, Color(
					clamp(color_b.r + edge_noise, 0.0, 1.0),
					clamp(color_b.g + edge_noise, 0.0, 1.0),
					clamp(color_b.b + edge_noise, 0.0, 1.0)
				))
	var texture := ImageTexture.new()
	texture.set_image(image)
	return texture

func _box(label: String, position: Vector3, size: Vector3, color: Color, collision: bool = false, parent: Node3D = null, roughness: float = 0.78, metallic: float = 0.0, transparent: bool = false, emission: Color = Color.BLACK, material_override: StandardMaterial3D = null) -> Node3D:
	var root: Node3D
	if collision:
		root = StaticBody3D.new()
	else:
		root = Node3D.new()
	root.name = label.replace(" ", "_")
	root.position = position
	if parent != null:
		parent.add_child(root)
	else:
		add_child(root)
	var mesh := MeshInstance3D.new()
	mesh.name = "Mesh"
	var resource := BoxMesh.new()
	resource.size = size
	mesh.mesh = resource
	mesh.material_override = material_override if material_override != null else _mat(color, roughness, metallic, transparent, emission)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	root.add_child(mesh)
	if collision:
		var shape := CollisionShape3D.new()
		var box_shape := BoxShape3D.new()
		box_shape.size = size
		shape.shape = box_shape
		root.add_child(shape)
	return root

func _cylinder(label: String, position: Vector3, radius: float, height: float, color: Color, parent: Node3D = null, collision: bool = false, metallic: float = 0.0) -> Node3D:
	var root: Node3D = StaticBody3D.new() if collision else Node3D.new()
	root.name = label.replace(" ", "_")
	root.position = position
	if parent != null:
		parent.add_child(root)
	else:
		add_child(root)
	var mesh := MeshInstance3D.new()
	var shape_mesh := CylinderMesh.new()
	shape_mesh.top_radius = radius * 0.94
	shape_mesh.bottom_radius = radius
	shape_mesh.height = height
	shape_mesh.radial_segments = 20
	mesh.mesh = shape_mesh
	mesh.material_override = _mat(color, 0.72, metallic)
	root.add_child(mesh)
	if collision:
		var collision_node := CollisionShape3D.new()
		var cylinder_shape := CylinderShape3D.new()
		cylinder_shape.radius = radius
		cylinder_shape.height = height
		collision_node.shape = cylinder_shape
		root.add_child(collision_node)
	return root

func _sphere(label: String, position: Vector3, radius: float, color: Color, scale: Vector3 = Vector3.ONE, parent: Node3D = null) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	var resource := SphereMesh.new()
	resource.radius = radius
	resource.height = radius * 2.0
	resource.radial_segments = 16
	resource.rings = 8
	mesh.mesh = resource
	mesh.name = label.replace(" ", "_")
	mesh.position = position
	mesh.scale = scale
	mesh.material_override = _mat(color)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	if parent != null:
		parent.add_child(mesh)
	else:
		add_child(mesh)
	return mesh

func _label(text_value: String, position: Vector3, size: float = 0.007, color: Color = Color("#f4f2e9"), parent: Node3D = null) -> Label3D:
	var label := Label3D.new()
	label.text = text_value.to_upper()
	label.position = position
	label.font_size = 38
	label.outline_size = 9
	label.modulate = color
	label.outline_modulate = Color(0.04, 0.08, 0.075, 0.92)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.pixel_size = size
	if parent != null:
		parent.add_child(label)
	else:
		add_child(label)
	return label

## Teks 3D TIMBUL (embossed): huruf di-extrude dengan TextMesh sehingga punya
## kedalaman fisik — dipakai untuk papan nama perusahaan.
func _raised_text(text_value: String, position: Vector3, yaw: float, letter_height: float, depth: float, color: Color, parent: Node3D = null) -> Node3D:
	var root := Node3D.new()
	root.name = "EmbossedText"
	root.position = position
	root.rotation.y = yaw
	(parent if parent != null else self).add_child(root)
	var mesh := TextMesh.new()
	mesh.text = text_value.to_upper()
	mesh.font = ThemeDB.fallback_font
	var font_size := clampi(int(letter_height * 278.0), 24, 320)
	mesh.font_size = font_size
	mesh.set("pixel_size", letter_height / (float(font_size) * 0.72))
	mesh.depth = depth
	mesh.curve_step = 0.7
	mesh.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	mesh.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.mesh = mesh
	# Logam agak kusam + sedikit glow lembut supaya huruf timbul tetap terbaca.
	mesh_instance.material_override = _mat(color, 0.36, 0.55, false, color.darkened(0.35))
	root.add_child(mesh_instance)
	return root

## Papan informasi berdiri bebas: bingkai gelap, panel terang, header berwarna,
## dan isi multi-baris yang dibaca dari sisi lokal -Z.
func _info_board(board_name: String, position: Vector3, yaw: float, title: String, lines: Array, width: float = 2.4, height: float = 2.1) -> void:
	var root := Node3D.new()
	root.name = "%s_%02d" % [board_name, _door_sign_index]
	_door_sign_index += 1
	root.position = position
	root.rotation.y = yaw
	add_child(root)
	# Plinth dan dua tiang pendukung.
	_box("Info board base", Vector3(0, 0.07, 0), Vector3(width * 0.55, 0.14, 0.7), Color("#3f4a45"), true, root, 0.45, 0.2)
	for x in [-width * 0.5 + 0.12, width * 0.5 - 0.12]:
		_cylinder("Info board post", Vector3(x, 0.62, 0.0), 0.055, 1.1, Color("#5a6862"), root, false, 0.6)
	# Bingkai dan panel isi — muka papan menghadap lokal +Z (pintu masuk tamu).
	_box("Info frame", Vector3(0, 1.75, 0), Vector3(width + 0.14, height, 0.11), Color("#2e443c"), false, root, 0.38, 0.25)
	_box("Info panel", Vector3(0, 1.72, 0.062), Vector3(width, height - 0.12, 0.02), Color("#efe9db"), false, root, 0.75)
	_box("Info header plate", Vector3(0, 1.75 + height * 0.5 - 0.22, 0.075), Vector3(width - 0.36, 0.42, 0.03), Color("#3f5a4e"), false, root, 0.35, 0.28)
	# Teks papan: Label3D langsung anak env dengan yaw di label sendiri
	# muka teks +Z mengikuti muka papan (tanpa billboard, tanpa parent berputar).
	var text_basis := Basis(Vector3.UP, yaw)
	var title_label := Label3D.new()
	title_label.text = title.to_upper()
	title_label.font_size = 44
	title_label.outline_size = 5
	title_label.modulate = Color("#f2ecda")
	title_label.outline_modulate = Color(0.06, 0.10, 0.08, 0.9)
	title_label.pixel_size = 0.0040
	title_label.no_depth_test = false
	title_label.position = position + text_basis * Vector3(0, 1.75 + height * 0.5 - 0.22, 0.108)
	title_label.rotation.y = yaw
	add_child(title_label)
	var body := Label3D.new()
	body.text = "\n".join(lines)
	body.font_size = 40
	body.outline_size = 0
	body.modulate = Color("#2c3a34")
	body.outline_modulate = Color(0, 0, 0, 0)
	body.pixel_size = 0.0032
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	body.autowrap_mode = TextServer.AUTOWRAP_OFF
	body.no_depth_test = false
	body.position = position + text_basis * Vector3(0, 1.35, 0.09)
	body.rotation.y = yaw
	add_child(body)

func _wall_segment_x(x1: float, x2: float, z: float, y: float, height: float, color: Color, glass: bool = false) -> void:
	if x2 <= x1:
		return
	_box("Glass partition" if glass else "Interior wall", Vector3((x1 + x2) * 0.5, y, z), Vector3(x2 - x1, height, 0.16), color, true, null, 0.16 if glass else 0.84, 0.05 if glass else 0.0, glass)
	if glass:
		for x in [x1 + 0.08, x2 - 0.08]:
			_box("Glass mullion", Vector3(x, y, z), Vector3(0.075, height, 0.20), Color("#758982"), false, null, 0.34, 0.48)

func _wall_segment_z(x: float, z1: float, z2: float, y: float, height: float, color: Color, glass: bool = false) -> void:
	if z2 <= z1:
		return
	_box("Glass partition" if glass else "Interior wall", Vector3(x, y, (z1 + z2) * 0.5), Vector3(0.16, height, z2 - z1), color, true, null, 0.16 if glass else 0.84, 0.05 if glass else 0.0, glass)
	if glass:
		for z in [z1 + 0.08, z2 - 0.08]:
			_box("Glass mullion", Vector3(x, y, z), Vector3(0.20, height, 0.075), Color("#758982"), false, null, 0.34, 0.48)

func _partition_x_with_door(x1: float, x2: float, z: float, door_center: float, door_width: float = DOOR_W, door_label: String = "", swing_north: bool = true) -> void:
	var left_end := door_center - door_width * 0.5
	var right_start := door_center + door_width * 0.5
	_wall_segment_x(x1, left_end, z, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true)
	_wall_segment_x(right_start, x2, z, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true)
	# Frame kayu: post kiri/kanan + header, bukaan setinggi DOOR_H.
	_box("Door frame left", Vector3(left_end + 0.03, DOOR_H * 0.5, z), Vector3(0.14, DOOR_H + 0.05, 0.28), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door frame right", Vector3(right_start - 0.03, DOOR_H * 0.5, z), Vector3(0.14, DOOR_H + 0.05, 0.28), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door header", Vector3(door_center, DOOR_H + 0.09, z), Vector3(door_width + 0.30, 0.18, 0.26), Color("#574132"), false, null, 0.50, 0.1)
	# Transom kaca susu di atas daun pintu sampai atap partisi.
	var transom_h := PART_H - (DOOR_H + 0.18)
	_box("Door transom", Vector3(door_center, DOOR_H + 0.18 + transom_h * 0.5, z),
		Vector3(door_width + 0.34, transom_h, 0.10), Color(0.72, 0.82, 0.78, 0.38), false, null, 0.28, 0.0, true)
	# Daun pintu ganda membuka ajar (swing north = ke ruang utara). Daun
	# didaftarkan ke registry `doors` supaya main.gd bisa membuka/menutupnya.
	var open_amount := 0.62
	var leaf_left := _add_door_leaf(Vector3(left_end, 0, z), 0.0, open_amount * (1.0 if swing_north else -1.0), door_width * 0.5 - 0.02)
	var leaf_right := _add_door_leaf(Vector3(right_start, 0, z), PI, open_amount * (-1.0 if swing_north else 1.0), door_width * 0.5 - 0.02)
	doors.append({
		"position": Vector3(door_center, 0.0, z),
		"label": door_label,
		"open": true,
		"leaves": [
			{"node": leaf_left, "closed": 0.0, "open": open_amount * (1.0 if swing_north else -1.0)},
			{"node": leaf_right, "closed": PI, "open": PI + open_amount * (-1.0 if swing_north else 1.0)},
		],
	})
	if door_label != "":
		_add_door_sign(door_center, z, true, swing_north, door_label)

func _partition_z_with_door(x: float, z1: float, z2: float, door_center: float, door_width: float = DOOR_W, door_label: String = "", open_east: bool = true) -> void:
	var left_end := door_center - door_width * 0.5
	var right_start := door_center + door_width * 0.5
	_wall_segment_z(x, z1, left_end, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true)
	_wall_segment_z(x, right_start, z2, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true)
	_box("Door frame left", Vector3(x, DOOR_H * 0.5, left_end + 0.03), Vector3(0.28, DOOR_H + 0.05, 0.14), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door frame right", Vector3(x, DOOR_H * 0.5, right_start - 0.03), Vector3(0.28, DOOR_H + 0.05, 0.14), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door header", Vector3(x, DOOR_H + 0.09, door_center), Vector3(0.26, 0.18, door_width + 0.30), Color("#574132"), false, null, 0.50, 0.1)
	var transom_h := PART_H - (DOOR_H + 0.18)
	_box("Door transom", Vector3(x, DOOR_H + 0.18 + transom_h * 0.5, door_center),
		Vector3(0.10, transom_h, door_width + 0.34), Color(0.72, 0.82, 0.78, 0.38), false, null, 0.28, 0.0, true)
	var open_amount := 0.62
	var leaf_left := _add_door_leaf(Vector3(x, 0, left_end), -PI * 0.5, open_amount * (1.0 if open_east else -1.0), door_width * 0.5 - 0.02)
	var leaf_right := _add_door_leaf(Vector3(x, 0, right_start), PI * 0.5, open_amount * (-1.0 if open_east else 1.0), door_width * 0.5 - 0.02)
	doors.append({
		"position": Vector3(x, 0.0, door_center),
		"label": door_label,
		"open": true,
		"leaves": [
			{"node": leaf_left, "closed": -PI * 0.5, "open": -PI * 0.5 + open_amount * (1.0 if open_east else -1.0)},
			{"node": leaf_right, "closed": PI * 0.5, "open": PI * 0.5 + open_amount * (-1.0 if open_east else 1.0)},
		],
	})
	if door_label != "":
		_add_door_sign(x, door_center, false, not open_east, door_label)

## Daun pintu ganda: pivot di engsel, panel kayu dengan pegangan kuningan di
## kedua sisi. Membuka ajar yang terlihat arsitiktural namun tidak menghalangi
## jalur (tanpa collision). bearing = yaw arah tertutup; offset = bukaan radian.
# Registrasi daun pintu & plakat terpakai untuk penamaan unik.
var _door_leaf_index := 0
var _door_sign_index := 0
var _office_chair_index := 0

func _add_door_leaf(hinge: Vector3, bearing: float, open_offset: float, leaf_length: float) -> Node3D:
	var leaf := Node3D.new()
	leaf.name = "DoorLeaf_%02d" % _door_leaf_index
	_door_leaf_index += 1
	leaf.position = hinge
	leaf.rotation.y = bearing + open_offset
	add_child(leaf)
	var panel := MeshInstance3D.new()
	var panel_mesh := BoxMesh.new()
	panel_mesh.size = Vector3(leaf_length, DOOR_H - 0.16, 0.055)
	panel.mesh = panel_mesh
	panel.material_override = _mat(Color("#6b5138"), 0.42, 0.05)
	panel.position = Vector3(leaf_length * 0.5 + 0.05, (DOOR_H - 0.16) * 0.5 + 0.02, 0)
	leaf.add_child(panel)
	# Inset panel dekoratif.
	var inset := MeshInstance3D.new()
	var inset_mesh := BoxMesh.new()
	inset_mesh.size = Vector3(leaf_length * 0.62, DOOR_H - 0.72, 0.02)
	inset.mesh = inset_mesh
	inset.material_override = _mat(Color("#755a41"), 0.44, 0.05)
	inset.position = Vector3(leaf_length * 0.5 + 0.05, (DOOR_H - 0.16) * 0.5 + 0.02, -0.010)
	leaf.add_child(inset)
	# Pegangan kuningan vertikal di sisi luar tiap daun.
	for side_z in [-0.055, 0.055]:
		var handle := MeshInstance3D.new()
		var handle_mesh := CylinderMesh.new()
		handle_mesh.top_radius = 0.022
		handle_mesh.bottom_radius = 0.022
		handle_mesh.height = 0.72
		handle_mesh.radial_segments = 12
		handle.mesh = handle_mesh
		handle.material_override = _mat(Color("#c5a366"), 0.25, 0.75)
		handle.position = Vector3(leaf_length - 0.10, (DOOR_H - 0.16) * 0.5 + 0.02, side_z)
		leaf.add_child(handle)
	return leaf

## Plakat nama ruangan di atas header pintu, sisi belakang partisi dipilih oleh
## caller (corridor side).
func _add_door_sign(wall_pos: float, along_pos: float, axis_x: bool, face_south_or_east: bool, text: String) -> void:
	var plate_position := Vector3(wall_pos, DOOR_H + 0.42, along_pos)
	var offset := 0.15
	if axis_x:
		plate_position.z += offset if face_south_or_east else -offset
	else:
		plate_position.x += offset if face_south_or_east else -offset
	_box("Door sign plate %02d" % _door_sign_index, plate_position, Vector3(1.7, 0.36, 0.035) if axis_x else Vector3(0.035, 0.36, 1.7), Color("#3f5a4e"), false, null, 0.35, 0.28)
	_box("Door sign trim %02d" % _door_sign_index, plate_position, Vector3(1.5, 0.24, 0.04) if axis_x else Vector3(0.04, 0.24, 1.5), Color("#283b33"), false, null, 0.30, 0.35)
	_door_sign_index += 1
	var label := Label3D.new()
	label.text = text.to_upper()
	label.font_size = 44
	label.outline_size = 6
	label.modulate = Color("#ece6d4")
	label.outline_modulate = Color(0.05, 0.09, 0.07, 0.95)
	label.pixel_size = 0.0042
	label.no_depth_test = false
	# Label3D punya muka teks +Z lokal (sama seperti TextMesh): putar yaw agar
	# muka teks benar menunjuk sisi koridor/timur.
	if axis_x:
		label.rotation.y = 0.0 if face_south_or_east else PI
	else:
		# Untuk dinding sisi timur: mukanya menuju +X butuh yaw +PI/2.
		label.rotation.y = PI * 0.5 if face_south_or_east else -PI * 0.5
	if axis_x:
		label.position = plate_position + Vector3(0, 0, 0.030 if face_south_or_east else -0.030)
	else:
		label.position = plate_position + Vector3(0.030 if face_south_or_east else -0.030, 0, 0)
	add_child(label)

func _build_site() -> void:
	_box("Site ground", Vector3(0, -0.62, 0), Vector3(150, 0.7, 150), Color("#839582"), true)
	_box("HQ apron", Vector3(0, -0.27, 0), Vector3(98, 0.18, 92), Color("#adb5aa"), false)
	_box("Main foundation", Vector3(0, -0.10, 0), Vector3(86, 0.24, 82), Color("#89958e"), true)
	_box("Road south", Vector3(0, -0.20, 55), Vector3(100, 0.12, 13), Color("#5b6663"), false)
	_box("Road marking", Vector3(0, -0.12, 55), Vector3(90, 0.025, 0.16), Color("#e7d8ad"), false)
	for x in [-34, -18, 18, 34]:
		_box("Parking bay", Vector3(x, -0.105, 47), Vector3(0.12, 0.025, 8), Color("#eee8d5"), false)
	_box("Entry walkway", Vector3(0, -0.015, 43.5), Vector3(15, 0.07, 12), Color("#c4c9bf"), false)
	for z in [38.5, 40.5, 42.5]:
		_box("Walkway joint", Vector3(0, 0.026, z), Vector3(14, 0.018, 0.045), Color("#9ca69c"), false)


func _add_dust_particles() -> void:
	var dust := GPUParticles3D.new()
	dust.name = "AmbientDust"
	dust.position = Vector3(0, 2.2, 0)
	dust.amount = 80
	dust.lifetime = 18.0
	dust.preprocess = 5.0
	dust.explosiveness = 0.05
	dust.randomness = 0.8
	dust.draw_pass_1 = SphereMesh.new()
	dust.draw_pass_1.radius = 0.015
	dust.draw_pass_1.height = 0.015
	dust.draw_pass_1.radial_segments = 6
	dust.draw_pass_1.rings = 2
	var dust_mat := ParticleProcessMaterial.new()
	dust_mat.direction = Vector3(0, 0.1, 0)
	dust_mat.spread = 40.0
	dust_mat.initial_velocity_min = 0.02
	dust_mat.initial_velocity_max = 0.06
	dust_mat.gravity = Vector3(0, -0.005, 0)
	dust_mat.scale_min = 0.8
	dust_mat.scale_max = 1.4
	dust_mat.color = Color(0.85, 0.82, 0.75, 0.25)
	dust.process_material = dust_mat
	dust.draw_pass_1.material = StandardMaterial3D.new()
	dust.draw_pass_1.material.albedo_color = Color(0.9, 0.87, 0.8, 0.3)
	dust.draw_pass_1.material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	dust.draw_pass_1.material.disable_receive_shadows = true
	add_child(dust)

func _build_shell() -> void:
	_box("Office floor slab", Vector3(0, 0, 0), Vector3(84, 0.22, 80), MAT.floor, true)
	# Exterior walls, raised to a double-height office proportion.
	_box("North exterior wall", Vector3(0, WALL_H * 0.5, -40), Vector3(84, WALL_H, 0.34), MAT.wall, true)
	_box("West exterior wall", Vector3(-42, WALL_H * 0.5, 0), Vector3(0.34, WALL_H, 80), MAT.wall, true)
	_box("East exterior wall", Vector3(42, WALL_H * 0.5, 0), Vector3(0.34, WALL_H, 80), MAT.wall, true)
	_wall_segment_x(-42, -5.2, 40, WALL_H * 0.5, WALL_H, MAT.wall, false)
	_wall_segment_x(5.2, 42, 40, WALL_H * 0.5, WALL_H, MAT.wall, false)
	_box("Entrance canopy", Vector3(0, 4.15, 42.8), Vector3(20, 0.38, 5.4), Color("#344b43"), true)
	for x in [-9.1, 9.1]:
		_box("Canopy pillar", Vector3(x, 2.05, 43.6), Vector3(0.38, 4.1, 0.38), Color("#73857c"), true)
	# Full-height windows along side and rear facades.
	for x in [-34, -25, -16, -7, 2, 11, 20, 29, 38]:
		_box("North glazing", Vector3(x, 2.45, -39.78), Vector3(5.6, 3.4, 0.06), MAT.glass, false, null, 0.16, 0.12, true)
		_box("North window sill", Vector3(x, 0.78, -39.68), Vector3(5.8, 0.10, 0.20), Color("#9ca9a2"), false)
		_box("North glazing header", Vector3(x, 4.28, -39.78), Vector3(5.6, 0.10, 0.12), Color("#7d8b84"), false)
	for z in [-32, -21, -10, 1, 12, 23, 34]:
		for x in [-41.78, 41.78]:
			_box("Side glazing", Vector3(x, 2.45, z), Vector3(0.06, 3.4, 7.3), MAT.glass, false, null, 0.16, 0.12, true)
			_box("Side window sill", Vector3(x * 0.999, 0.78, z), Vector3(0.20, 0.1, 7.5), Color("#9ca9a2"), false)
			_box("Side glazing header", Vector3(x * 0.999, 4.28, z), Vector3(0.12, 0.10, 7.3), Color("#7d8b84"), false)
	# South lobby storefront glass and sliding doors, plus a clerestory band
	# above the shopfront so the expanded lobby stays bright.
	for x in [-15, -10, -5, 5, 10, 15]:
		_box("Lobby storefront glass", Vector3(x, 2.0, 39.78), Vector3(4.55, 3.0, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
		_box("Storefront mullion", Vector3(x, 2.0, 39.68), Vector3(0.09, 3.15, 0.16), Color("#71847b"), false, null, 0.35, 0.5)
		_box("Lobby clerestory glass", Vector3(x, 4.5, 39.78), Vector3(4.55, 1.8, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
		_box("Clerestory mullion", Vector3(x, 4.5, 39.68), Vector3(0.09, 1.95, 0.16), Color("#71847b"), false, null, 0.35, 0.5)
	_box("Entry left door", Vector3(-2.25, 1.7, 39.5), Vector3(2.0, 3.25, 0.11), Color(0.44, 0.65, 0.65, 0.34), false, null, 0.12, 0.1, true)
	_box("Entry right door", Vector3(2.25, 1.7, 39.5), Vector3(2.0, 3.25, 0.11), Color(0.44, 0.65, 0.65, 0.34), false, null, 0.12, 0.1, true)
	_box("Entry transom glass", Vector3(0, 4.5, 39.78), Vector3(4.4, 1.8, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
	_box("Entry pull left", Vector3(-1.25, 1.7, 39.38), Vector3(0.05, 1.15, 0.08), Color("#c5aa7a"), false, null, 0.28, 0.75)
	_box("Entry pull right", Vector3(1.25, 1.7, 39.38), Vector3(0.05, 1.15, 0.08), Color("#c5aa7a"), false, null, 0.28, 0.75)
	# Structural columns and a visible roof edge keep the building architectural, not a floating floorplan.
	for x in [-39, -20, 0, 20, 39]:
		for z in [-37, -18, 4, 25, 37]:
			_box("Structural column", Vector3(x, WALL_H * 0.5, z), Vector3(0.42, WALL_H, 0.42), Color("#c5cec7"), true)
	_box("North roof edge", Vector3(0, 5.62, -40), Vector3(84, 0.30, 0.52), Color("#718179"), false)
	_box("West roof edge", Vector3(-42, 5.62, 0), Vector3(0.52, 0.30, 80), Color("#718179"), false)
	_box("East roof edge", Vector3(42, 5.62, 0), Vector3(0.52, 0.30, 80), Color("#718179"), false)
	_box("South roof edge", Vector3(0, 5.62, 40), Vector3(84, 0.30, 0.52), Color("#718179"), false)
	# Papan nama perusahaan eksterior: panel perunggu + huruf timbul (embossed).
	_box("Exterior logo panel", Vector3(0, 4.95, 40.44), Vector3(14.0, 1.62, 0.14), Color("#2f4339"), false, null, 0.34, 0.55)
	_box("Exterior logo trim", Vector3(0, 4.20, 40.44), Vector3(14.0, 0.10, 0.16), Color("#c2a36e"), false, null, 0.32, 0.7)
	_raised_text("BANGKAH", Vector3(0, 5.06, 40.53), 0, 0.66, 0.09, Color("#e8d3a0"))
	_label("HEADQUARTERS", Vector3(0, 4.56, 40.53), 0.0056, Color("#dbe4d8"))

func _build_room_partitions() -> void:
	# North executive wing: Owner, Secretary, Management and Architecture.
	# Semua pintu membuka KE DALAM ruangan yang dilabelinya (tidak menyapu koridor).
	_partition_z_with_door(-19.5, -39.8, -20.0, -29.5, DOOR_W, "OWNER OFFICE", false)
	_partition_z_with_door(-2.0, -39.8, -20.0, -29.5, DOOR_W, "SECRETARIAT", false)
	_partition_z_with_door(18.5, -39.8, -20.0, -29.5, DOOR_W, "ARCHITECTURE", true)
	_partition_x_with_door(-39.8, -19.8, -20.0, -29.5, DOOR_W, "OWNER OFFICE", true)
	_partition_x_with_door(-19.2, -2.2, -20.0, -10.8, DOOR_W, "SECRETARIAT", true)
	_partition_x_with_door(-1.8, 18.2, -20.0, 8.0, DOOR_W, "MANAGEMENT", true)
	_partition_x_with_door(18.8, 39.8, -20.0, 29.0, DOOR_W, "ARCHITECTURE", true)
	# Engineering wing, meeting room, public lobby, QA, backend and API lab.
	_partition_z_with_door(-19.5, -19.8, 4.0, -7.0, DOOR_W, "FRONTEND", false)
	_partition_z_with_door(6.5, -19.8, 4.0, -7.0, DOOR_W, "BACKEND", true)
	_partition_z_with_door(18.5, -19.8, 4.0, -7.0, DOOR_W, "API LAB", true)
	_partition_x_with_door(-39.8, -19.8, 4.0, -29.5, DOOR_W, "BOARDROOM", false)
	_partition_x_with_door(-19.2, 6.2, 4.0, -6.5, DOOR_W, "QA ENGINEERING", true)
	_partition_x_with_door(6.8, 18.2, 4.0, 13.0, DOOR_W, "BACKEND", true)
	_partition_x_with_door(18.8, 39.8, 4.0, 29.0, DOOR_W, "API LAB", true)
	# South rooms: archive/print remain; area selatan-tengah menyatu dengan
	# LOBBY (dinding lama x=-19.8..18.8 dihapus) supaya lobi lebih luas.
	_partition_z_with_door(-19.5, 4.0, 25.0, 14.5, DOOR_W, "BOARDROOM", false)
	_partition_z_with_door(18.5, 4.0, 25.0, 14.5, DOOR_W, "API LAB", true)
	_partition_x_with_door(-39.8, -19.8, 25.0, -29.5, DOOR_W, "ARCHIVE & PRINT", false)
	_partition_x_with_door(18.8, 39.8, 25.0, 29.0, DOOR_W, "PANTRY & LOUNGE", false)
	# Pemisah ruang pribadi owner dari lobby baru.
	_partition_z_with_door(-0.5, 25.0, 39.8, 32.5, DOOR_W, "OWNER LOUNGE", true)
	_partition_x_with_door(-19.8, -0.5, 25.0, -12.5, 3.1, "OWNER SUITE", false)
	# Frosted lower bands and door signage details.
	for x in [-29, -11, 8, 29]:
		_box("Glass privacy band", Vector3(x, 0.62, -20.0), Vector3(2.2, 0.36, 0.19), Color(0.72, 0.78, 0.73, 0.56), false, null, 0.28, 0.0, true)

func _build_room_floors() -> void:
	# Distinct materials make the department layout readable at player height.
	var carpet_tex = _create_noise_texture(128, Color("#9ca99a"), 0.05)
	var carpet_mat = StandardMaterial3D.new()
	carpet_mat.albedo_texture = carpet_tex
	carpet_mat.roughness = 0.94
	carpet_mat.metallic = 0.0
	carpet_mat.uv1_scale = Vector3(4.0, 4.0, 1.0)
	_material_cache["carpet"] = carpet_mat

	var stone_tex = _create_grid_texture(128, Color("#c8c4b8"), Color("#d3d2c8"), 32)
	var stone_mat = StandardMaterial3D.new()
	stone_mat.albedo_texture = stone_tex
	stone_mat.roughness = 0.35
	stone_mat.metallic = 0.05
	stone_mat.uv1_scale = Vector3(6.0, 6.0, 1.0)
	_material_cache["stone"] = stone_mat

	var tile_tex = _create_grid_texture(128, Color("#b8b4a8"), Color("#c6c8bf"), 32)
	var tile_mat = StandardMaterial3D.new()
	tile_mat.albedo_texture = tile_tex
	tile_mat.roughness = 0.28
	tile_mat.metallic = 0.08
	tile_mat.uv1_scale = Vector3(5.0, 5.0, 1.0)
	_material_cache["tile"] = tile_mat

	var carpet_material: StandardMaterial3D = _material_cache["carpet"]
	var stone_material: StandardMaterial3D = _material_cache["stone"]
	var tile_material: StandardMaterial3D = _material_cache["tile"]

	_box("Owner carpet", Vector3(-29.5, 0.126, -29.7), Vector3(18.0, 0.035, 17.8), Color("#9ca99a"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Secretary carpet", Vector3(-10.8, 0.126, -29.7), Vector3(16.5, 0.035, 17.8), Color("#b2b9ad"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Manager carpet", Vector3(8.0, 0.126, -29.7), Vector3(19.8, 0.035, 17.8), Color("#aab5a9"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Architect carpet", Vector3(29.0, 0.126, -29.7), Vector3(20.4, 0.035, 17.8), Color("#a8b4bb"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Frontend carpet", Vector3(-29.5, 0.126, -7.8), Vector3(18.0, 0.035, 21.0), Color("#b1aaa0"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("QA carpet", Vector3(-6.5, 0.126, -7.8), Vector3(25.0, 0.035, 21.0), Color("#a9b8ad"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Backend carpet", Vector3(24.0, 0.126, -7.8), Vector3(30.0, 0.035, 21.0), Color("#a9b1ad"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Meeting carpet", Vector3(-29.5, 0.126, 14.5), Vector3(18.0, 0.035, 20.0), Color("#a8a2b0"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Lobby stone floor", Vector3(-0.4, 0.126, 14.5), Vector3(38.0, 0.035, 20.0), Color("#d3d2c8"), false, null, 0.38, 0.05, false, Color.BLACK, stone_material)
	_box("API lab floor", Vector3(29.0, 0.126, 14.5), Vector3(20.0, 0.035, 20.0), Color("#a8b6b8"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Archive floor", Vector3(-29.5, 0.126, 32.0), Vector3(18.0, 0.035, 14.0), Color("#b9ad9e"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Owner lounge floor", Vector3(-10.0, 0.126, 32.0), Vector3(18.7, 0.035, 14.0), Color("#b0987e"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Staff lounge floor", Vector3(9.0, 0.126, 32.0), Vector3(18.5, 0.035, 14.0), Color("#b9c6b8"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Pantry tile floor", Vector3(30.0, 0.126, 32.0), Vector3(23.5, 0.035, 14.0), Color("#c6c8bf"), false, null, 0.32, 0.08, false, Color.BLACK, tile_material)
	# Flooring insets / transition strips.
	for z in [-19.75, 4.2, 25.2]:
		_box("Floor transition strip", Vector3(0, 0.15, z), Vector3(82, 0.045, 0.22), Color("#7e8b81"), false, null, 0.5, 0.18)

func _build_ceiling_and_lighting() -> void:
	# Suspended acoustic ceiling: the roof is now present from first-person eye level.
	# Individual panels leave narrow service gaps and recessed light channels.
	for z in [-37.5, -18.5, 4.0, 25.0, 37.5]:
		_box("Ceiling cross beam", Vector3(0, 5.22, z), Vector3(82, 0.18, 0.32), Color("#87948d"), false, null, 0.72, 0.12)
	for x in [-40, -19.5, -2.0, 18.5, 40]:
		_box("Ceiling spine", Vector3(x, 5.22, 0), Vector3(0.28, 0.18, 78), Color("#87948d"), false, null, 0.72, 0.12)
	for tile_x in range(-38, 39, 4):
		for tile_z in range(-37, 38, 5):
			_box("Acoustic ceiling panel", Vector3(float(tile_x) + 2.0, CEIL_Y, float(tile_z) + 2.5), Vector3(3.70, 0.075, 4.68), Color("#e2e5df"), false, null, 0.92)
	# HVAC return grilles add scale and break up the broad ceiling plane.
	for point in [Vector3(-34,5.39,-27), Vector3(-14,5.39,-27), Vector3(8,5.39,-27), Vector3(30,5.39,-27), Vector3(-33,5.39,-4), Vector3(5,5.39,-4), Vector3(31,5.39,16), Vector3(8,5.39,34)]:
		_box("HVAC ceiling grille", point, Vector3(0.95, 0.018, 0.42), Color("#87918c"), false, null, 0.62, 0.22)
	var light_points := [Vector3(-29,-29, -28), Vector3(-10,-29,-28), Vector3(8,-29,-28), Vector3(29,-29,-28), Vector3(-29,-7,-7), Vector3(-6,-7,-7), Vector3(24,-7,-7), Vector3(-29, -7, 15), Vector3(-1,-7,15), Vector3(29,-7,15), Vector3(8,-7,33)]
	for i in range(light_points.size()):
		var point = light_points[i]
		_box("Linear ceiling light", Vector3(point.x, CEIL_Y - 0.30, point.z), Vector3(4.6, 0.12, 0.55), Color("#f4f0df"), false, null, 0.22, 0.0, false, Color("#f5e8d0"))
		var light := OmniLight3D.new()
		light.position = Vector3(point.x, 4.72, point.z)
		light.light_color = Color("#fff0d8")
		light.light_energy = 0.42
		light.omni_range = 11.0
		# Enable shadows on alternating lights for quality without perf overhead.
		light.shadow_enabled = i % 2 == 0
		if light.shadow_enabled:
			light.shadow_blur = 2.0
		add_child(light)
	# Lobby feature pendant lights, two rows across the expanded lobby.
	for pendant_z in [15.0, 24.0, 31.5]:
		for x in [-7.0, 0.0, 7.0]:
			_cylinder("Pendant stem", Vector3(x, 4.14, pendant_z), 0.035, 2.45, Color("#596b63"))
			_cylinder("Pendant shade", Vector3(x, 2.90, pendant_z), 0.46, 0.18, Color("#d5c49e"), null, false, 0.2)
			# Emissive shade material for warm glow.
			_box("Pendant glow", Vector3(x, 2.84, pendant_z), Vector3(0.38, 0.06, 0.38), Color("#f5e0b8"), false, null, 0.22, 0.0, false, Color("#f8ecca"))
			var pendant_light := OmniLight3D.new()
			pendant_light.position = Vector3(x, 2.76, pendant_z)
			pendant_light.light_color = Color("#ffe8c8")
			pendant_light.light_energy = 0.35
			pendant_light.omni_range = 5.5
			pendant_light.shadow_enabled = false
			add_child(pendant_light)

func _add_workstation(position: Vector3, title: String, wood: Color = Color("#9c8062"), dual_monitor: bool = true, rotation_y: float = 0.0) -> void:
	var root := Node3D.new()
	root.position = position
	root.rotation.y = rotation_y
	add_child(root)
	# Desk top, apron and four metal legs.
	_box("Desk top", Vector3(0, 0.83, 0), Vector3(2.8, 0.16, 1.42), wood, true, root, 0.34)
	_box("Desk front apron", Vector3(0, 0.63, -0.56), Vector3(2.42, 0.25, 0.10), Color("#755d49"), false, root)
	for x in [-1.22, 1.22]:
		for z in [-0.55, 0.55]:
			_box("Desk metal leg", Vector3(x, 0.39, z), Vector3(0.10, 0.76, 0.10), Color("#58635e"), false, root, 0.3, 0.62)
	# Drawer unit.
	_box("Desk drawer cabinet", Vector3(-1.02, 0.42, -0.30), Vector3(0.48, 0.78, 0.92), Color("#8b735c"), true, root)
	for y in [0.24, 0.47, 0.70]:
		_box("Drawer face", Vector3(-1.02, y, 0.18), Vector3(0.40, 0.17, 0.035), Color("#b89b79"), false, root)
		_box("Drawer handle", Vector3(-1.02, y, 0.145), Vector3(0.18, 0.035, 0.035), Color("#d0b783"), false, root, 0.25, 0.65)
	# Monitor arm and displays.
	_cylinder("Monitor stand", Vector3(0, 1.01, -0.43), 0.055, 0.32, Color("#65716c"), root, false, 0.5)
	var monitor_positions := [Vector3(-0.52, 1.43, -0.44), Vector3(0.52, 1.43, -0.44)] if dual_monitor else [Vector3(0, 1.43, -0.44)]
	for monitor_pos in monitor_positions:
		_box("Monitor bezel", monitor_pos, Vector3(0.94, 0.68, 0.12), Color("#25333a"), false, root, 0.33, 0.18)
		_box("Monitor display", monitor_pos + Vector3(0, 0, 0.069), Vector3(0.82, 0.55, 0.025), Color("#29444a"), false, root, 0.24, 0.08, false, Color("#315e55"))
		_box("Monitor status bar", monitor_pos + Vector3(0, -0.21, 0.086), Vector3(0.65, 0.025, 0.012), Color("#9fc5a9"), false, root, 0.25, 0.0, false, Color("#78b58e"))
	# Keyboard, mouse, notebook, mug and desk accessories.
	_box("Keyboard", Vector3(0.02, 0.94, 0.27), Vector3(0.86, 0.045, 0.30), Color("#35434a"), false, root, 0.45, 0.12)
	_box("Keyboard keys", Vector3(0.02, 0.966, 0.27), Vector3(0.76, 0.012, 0.22), Color("#aeb8ad"), false, root, 0.62)
	_sphere("Mouse", Vector3(0.66, 0.97, 0.23), 0.10, Color("#37454a"), Vector3(1.0, 0.38, 1.35), root)
	_box("Notebook", Vector3(-0.88, 0.94, 0.30), Vector3(0.38, 0.055, 0.48), Color("#d8cfb9"), false, root)
	_box("Notebook cover", Vector3(-0.88, 0.974, 0.30), Vector3(0.38, 0.015, 0.48), Color("#80958a"), false, root)
	_cylinder("Coffee mug", Vector3(1.08, 1.02, 0.36), 0.12, 0.18, Color("#e7e1d4"), root)
	_cylinder("Mug coffee", Vector3(1.08, 1.115, 0.36), 0.09, 0.012, Color("#73523b"), root)
	# Desk lamp.
	_cylinder("Desk lamp base", Vector3(-1.03, 0.96, -0.42), 0.18, 0.06, Color("#69766f"), root, false, 0.45)
	_cylinder("Desk lamp neck", Vector3(-1.03, 1.17, -0.42), 0.035, 0.42, Color("#69766f"), root, false, 0.5)
	_cylinder("Desk lamp shade", Vector3(-1.03, 1.39, -0.42), 0.20, 0.11, Color("#c7ad80"), root, false, 0.3)
	# Emissive lamp glow.
	_box("Lamp glow", Vector3(-1.03, 1.36, -0.42), Vector3(0.28, 0.04, 0.28), Color("#f5e8c8"), false, root, 0.22, 0.0, false, Color("#f8edcc"))
	# Desk lamp warm pool of light.
	var desk_lamp := OmniLight3D.new()
	desk_lamp.position = Vector3(-1.03, 1.30, -0.42)
	desk_lamp.light_color = Color("#ffe8b8")
	desk_lamp.light_energy = 0.25
	desk_lamp.omni_range = 3.0
	desk_lamp.shadow_enabled = false
	root.add_child(desk_lamp)
	# Ergonomic chair and floor mat. Chair faces the monitor (-Z).
	var chair_position := position + root.transform.basis * Vector3(0, 0, 1.55)
	_add_office_chair(chair_position, Color("#52675f"), rotation_y, title.split("  /  ")[0] + " · Chair")
	_box("Desk floor mat", Vector3(0, 0.145, 1.45), Vector3(2.1, 0.025, 1.95), Color("#737f78"), false, root)
	_label(title, Vector3(0, 2.35, -0.04), 0.0055, Color("#f3f1e8"), root)
	# Workstation label only visible when player is close — keeps the office clean.
	var ws_label: Label3D = _label(title, Vector3(0, 2.35, -0.04), 0.0055, Color("#f3f1e8"), root)
	ws_label.set("visibility_range_end", 6.0)
	ws_label.set("visibility_range_fade_mode", 1) # VISIBILITY_RANGE_FADE_SELF

func _add_office_chair(position: Vector3, color: Color = Color("#52675f"), facing: float = 0.0, seat_label: String = "Kursi Kantor") -> void:
	# Kursi kantor swivel: SEMUA kursi punya dudukan/sandaran penuh dan teregistrasi
	# sebagai titik duduk bebas. Pivot "ChairSwivel" berputar mengikuti pemain.
	var root := Node3D.new()
	root.name = "OfficeChair_%02d" % _office_chair_index
	_office_chair_index += 1
	root.position = position
	root.rotation.y = facing
	add_child(root)
	_cylinder("Chair gas lift", Vector3(0, 0.20, 0), 0.045, 0.20, Color("#889291"), root, false, 0.55)
	_cylinder("Chair base hub", Vector3(0, 0.24, 0), 0.12, 0.22, Color("#69736e"), root, false, 0.62)
	for angle in [0.0, PI * 0.5, PI, PI * 1.5]:
		var spoke := _box("Chair base spoke", Vector3(cos(angle) * 0.30, 0.12, sin(angle) * 0.30), Vector3(0.62, 0.065, 0.085), Color("#6a7771"), false, root, 0.32, 0.7)
		spoke.rotation.y = angle
		_cylinder("Chair caster", Vector3(cos(angle) * 0.56, 0.08, sin(angle) * 0.56), 0.085, 0.12, Color("#303a3b"), root)
	var swivel := Node3D.new()
	swivel.name = "ChairSwivel"
	swivel.position = Vector3(0, 0.18, 0)
	root.add_child(swivel)
	_box("Chair cushion", Vector3(0, 0.45, 0), Vector3(0.94, 0.18, 0.92), color, false, swivel)
	_box("Chair back cushion", Vector3(0, 1.00, 0.39), Vector3(0.92, 1.08, 0.18), color, false, swivel)
	for x in [-0.54, 0.54]:
		_box("Chair arm support", Vector3(x, 0.74, -0.02), Vector3(0.10, 0.42, 0.12), Color("#485852"), false, swivel)
		_box("Chair arm pad", Vector3(x, 0.94, 0.04), Vector3(0.19, 0.08, 0.58), Color("#3e5049"), false, swivel)
	seats.append({"position": Vector3(position.x, 0.0, position.z), "yaw": facing, "kind": "office", "pivot": swivel, "label": seat_label})

func _add_shelf(position: Vector3, width: float, height: float, depth: float, label_text: String) -> void:
	var root := Node3D.new()
	root.position = position
	add_child(root)
	_box("Shelf side", Vector3(-width * 0.5, height * 0.5, 0), Vector3(0.12, height, depth), Color("#866a50"), true, root)
	_box("Shelf side", Vector3(width * 0.5, height * 0.5, 0), Vector3(0.12, height, depth), Color("#866a50"), true, root)
	for level in range(4):
		var y := 0.25 + float(level) * (height - 0.5) / 3.0
		_box("Shelf board", Vector3(0, y, 0), Vector3(width, 0.10, depth), Color("#b18e69"), false, root)
		for item in range(8):
			var book_color: Color = [Color("#718b7d"), Color("#bf916f"), Color("#7889a8"), Color("#b8ad7b")][item % 4]
			_box("Archive binder", Vector3(-width * 0.39 + float(item) * width * 0.11, y + 0.22, 0.0), Vector3(0.22, 0.34 + float(item % 3) * 0.05, depth * 0.58), book_color, false, root)
	_label(label_text, Vector3(0, height + 0.42, 0), 0.005, Color("#f0ede3"), root)

func _build_reception() -> void:
	# Lobby tamu: dinding brand di ujung utara area resepsionis dengan teks
	# timbul, meja resepsionis menghadap pintu masuk, dan lounge simetris.
	_box("Reception brand wall", Vector3(0, 2.65, 17.4), Vector3(22.0, 4.8, 0.30), Color("#32493f"), true)
	for x in range(-10, 11):
		_box("Brand wall slat", Vector3(float(x) * 1.05, 2.65, 17.58), Vector3(0.05, 4.55, 0.05), Color("#44615a"), false)
		_box("Brand wall slat cap", Vector3(float(x) * 1.05, 4.98, 17.58), Vector3(0.09, 0.06, 0.10), Color("#5b7266"), false)
	# Papan nama perusahaan: huruf timbul (embossed) menghadap pintu masuk.
	_raised_text("BANGKAH", Vector3(0, 3.16, 17.66), 0, 0.84, 0.10, Color("#e2c98c"))
	_label("Teknologi  ·  Engineering  ·  Inovasi", Vector3(0, 2.30, 17.70), 0.0052, Color("#d6dfd4"))
	# Meja resepsionis: sisi tampil menghadap tamu (+Z / pintu masuk).
	_box("Reception counter front", Vector3(0, 0.86, 20.8), Vector3(11.2, 1.55, 1.05), Color("#80664e"), true)
	_box("Reception counter side left", Vector3(-5.25, 0.86, 19.95), Vector3(0.70, 1.55, 1.75), Color("#80664e"), true)
	_box("Reception counter side right", Vector3(5.25, 0.86, 19.95), Vector3(0.70, 1.55, 1.75), Color("#80664e"), true)
	_box("Reception counter stone top", Vector3(0, 1.68, 20.72), Vector3(11.6, 0.16, 1.48), Color("#d6c6ad"), false, null, 0.24, 0.08)
	_box("Reception brand strip", Vector3(0, 0.88, 21.35), Vector3(6.8, 0.18, 0.045), Color("#c2a36e"), false)
	for x in [-4.8, -3.9, -3.0, -2.1, -1.2, -0.3, 0.6, 1.5, 2.4, 3.3, 4.2, 5.1]:
		_box("Counter fluting", Vector3(x, 0.85, 21.36), Vector3(0.055, 1.28, 0.045), Color("#b89a74"), false)
	_label("VISITOR CHECK-IN", Vector3(0, 1.55, 21.40), 0.0052, Color("#fff7e6"))
	# Terminal & perlengkapan di sisi staf (sisi utara meja).
	_box("Reception monitor bezel", Vector3(0, 2.03, 20.30), Vector3(1.55, 0.88, 0.14), Color("#29383d"), false, null, 0.3, 0.16)
	_box("Reception monitor screen", Vector3(0, 2.04, 20.21), Vector3(1.34, 0.68, 0.025), Color("#31534b"), false, null, 0.2, 0.0, false, Color("#5e9b7c"))
	_box("Reception keyboard", Vector3(-1.0, 1.80, 20.75), Vector3(0.85, 0.04, 0.28), Color("#46524e"), false)
	_box("Visitor sign-in book", Vector3(1.35, 1.80, 20.72), Vector3(0.72, 0.06, 0.48), Color("#d2c5a9"), false)
	_cylinder("Reception pen cup", Vector3(2.1, 1.88, 20.45), 0.12, 0.25, Color("#5b7168"))
	# Meja logo: aksen etalase di atas brand wall.
	_box("Brand wall shelf", Vector3(0, 1.06, 17.95), Vector3(9.4, 0.10, 0.62), Color("#8a6f52"), false)
	for x in [-4.2, 4.2]:
		_box("Brand shelf bracket", Vector3(x, 0.58, 17.95), Vector3(0.08, 0.95, 0.10), Color("#5e7266"), false)
	# Lounge tamu simetris: dua sofa saling menghadap meja kopi di tengah.
	_add_lounge_sofa(Vector3(-7.2, 0, 15.0), PI * 0.5, Color("#738a80"), 2.6)
	_add_lounge_sofa(Vector3(7.2, 0, 15.0), -PI * 0.5, Color("#738a80"), 2.6)
	_box("Lobby coffee table", Vector3(0, 0.46, 15.0), Vector3(3.0, 0.18, 1.55), Color("#a98562"), false)
	_box("Lobby coffee tray", Vector3(0, 0.58, 15.0), Vector3(2.4, 0.05, 1.1), Color("#7b6856"), false)
	for x in [-11.2, 11.2]:
		_add_plant(Vector3(x, 0, 10.0), 1.15)
		_box("Visitor side table", Vector3(x, 0.38, 17.6), Vector3(1.0, 0.12, 0.8), Color("#9d8365"), false)

func _add_lounge_sofa(position: Vector3, rotation_y: float, color: Color, width: float = 2.8) -> void:
	var root := Node3D.new()
	root.position = position
	root.rotation.y = rotation_y
	add_child(root)
	_box("Sofa base", Vector3(0, 0.40, 0), Vector3(width, 0.72, 1.04), color, false, root)
	_box("Sofa back", Vector3(0, 0.90, -0.42), Vector3(width, 0.72, 0.22), color.lightened(0.12), false, root)
	for x in [-width * 0.5 + 0.2, width * 0.5 - 0.2]:
		_box("Sofa arm", Vector3(x, 0.71, 0), Vector3(0.28, 0.74, 1.08), color.darkened(0.08), false, root)
	for x in [-width * 0.28, 0.0, width * 0.28]:
		_box("Sofa seat cushion", Vector3(x, 0.81, 0.03), Vector3(width * 0.25, 0.15, 0.79), color.lightened(0.10), false, root)
	# Registrasi dua titik duduk sofa; pemain menghadap +z lokal (yaw = PI
	# terhadap rotasi sofa) supaya tepat duduk menghadap ruangan.
	for sx in [width * 0.24, -width * 0.24]:
		var world_sit := Vector3(position.x + cos(rotation_y) * sx, 0.0, position.z - sin(rotation_y) * sx)
		seats.append({"position": world_sit, "yaw": rotation_y + PI, "kind": "sofa", "pivot": null, "label": "Sofa"})

func _build_owner_suite() -> void:
	_label("OWNER  /  PRIVATE OFFICE", Vector3(-29.5, 3.55, -38.1), 0.006)
	_box("Owner office feature wall", Vector3(-29.5, 2.0, -38.95), Vector3(16.5, 3.8, 0.16), Color("#435c50"), true)
	_box("Owner office crest", Vector3(-29.5, 2.75, -38.82), Vector3(5.2, 1.05, 0.12), Color("#b69b70"), false)
	_label("BANGKAH  /  OWNER", Vector3(-29.5, 2.73, -38.72), 0.007)
	# Main executive desk with return, triple displays and visitor seating.
	_add_workstation(Vector3(-29.3, 0, -31.3), "OWNER  /  WORKSTATION", Color("#6f5945"), true)
	_box("Owner desk return", Vector3(-33.2, 0.72, -30.4), Vector3(1.25, 1.4, 2.6), Color("#745a43"), true)
	_box("Owner desk return top", Vector3(-33.2, 1.46, -30.4), Vector3(1.38, 0.12, 2.72), Color("#c8aa83"), false)
	_add_lounge_sofa(Vector3(-29.5, 0, -22.5), 0.0, Color("#60796e"), 3.6)
	_box("Owner coffee table", Vector3(-29.5, 0.44, -25.0), Vector3(2.5, 0.16, 1.15), Color("#a98461"), false)
	_add_plant(Vector3(-37.1, 0, -22.5), 0.95)
	_add_plant(Vector3(-21.9, 0, -22.5), 0.95)
	_add_shelf(Vector3(-37.2, 0.18, -34.3), 2.2, 2.5, 0.8, "STRATEGY")
	# Paper tray on the right side of the desk, visible as a physical object.
	_box("Owner in tray base", Vector3(-27.2, 1.05, -31.25), Vector3(0.90, 0.16, 0.78), Color("#536b61"), false)
	_box("Owner in tray left", Vector3(-27.66, 1.24, -31.25), Vector3(0.07, 0.34, 0.82), Color("#c0c7bc"), false)
	_box("Owner in tray right", Vector3(-26.74, 1.24, -31.25), Vector3(0.07, 0.34, 0.82), Color("#c0c7bc"), false)
	for i in range(4):
		_box("Paper stack in tray", Vector3(-27.2, 1.16 + float(i) * 0.035, -31.25), Vector3(0.70, 0.025, 0.61), Color("#f0eee3"), false)
	_label("INBOX TRAY", Vector3(-27.2, 1.72, -31.25), 0.0038, Color("#e8efe7"))
	# Display wall, framed certificates and acoustic panels.
	for x in [-35.4, -29.5, -23.6]:
		_box("Executive wall art frame", Vector3(x, 2.3, -21.0), Vector3(2.2, 1.35, 0.09), Color("#6a7c70"), false)
		_box("Executive wall art", Vector3(x, 2.3, -20.93), Vector3(1.98, 1.12, 0.035), Color("#c6cfc4"), false)

func _build_secretary_office() -> void:
	_label("EXECUTIVE SECRETARY", Vector3(-10.5, 3.55, -38.1), 0.006)
	_box("Secretary back wall", Vector3(-10.8, 1.75, -38.95), Vector3(15.8, 3.45, 0.16), Color("#aebbb0"), true)
	_add_workstation(Vector3(-10.8, 0, -31.3), "SECRETARY  /  AGENDA", Color("#99795d"), true)
	_box("Secretary side credenza", Vector3(-4.2, 0.78, -33.8), Vector3(1.3, 1.5, 3.2), Color("#7f6c58"), true)
	for y in [0.45, 0.85, 1.25]:
		_box("Secretary file shelf", Vector3(-4.2, y, -33.8), Vector3(1.34, 0.06, 3.22), Color("#c0a681"), false)
	_box("Secretary inbox tray", Vector3(-8.9, 1.18, -31.0), Vector3(0.82, 0.13, 0.72), Color("#5e756a"), false)
	for i in range(3):
		_box("Secretary paper", Vector3(-8.9, 1.27 + float(i) * 0.03, -31.0), Vector3(0.65, 0.022, 0.56), Color("#f0eee5"), false)
	_box("Secretary pinboard frame", Vector3(-10.8, 2.35, -38.78), Vector3(4.5, 1.7, 0.10), Color("#725e4b"), false)
	_box("Secretary pinboard", Vector3(-10.8, 2.35, -38.71), Vector3(4.28, 1.48, 0.035), Color("#b8c4b5"), false)
	for x in [-12.2, -10.8, -9.4]:
		_box("Agenda card", Vector3(x, 2.35, -38.66), Vector3(0.95, 1.10, 0.04), Color("#e4d7b8"), false)

func _build_management_offices() -> void:
	_label("ENGINEERING  /  LEADERSHIP", Vector3(8.0, 3.5, -38.1), 0.006)
	# Arman and Sinta occupy an open management suite with planning boards.
	_add_workstation(Vector3(5.8, 0, -31.3), "ARMAN  /  LEAD MANAGER", Color("#876d54"), true)
	_add_workstation(Vector3(13.2, 0, -31.3), "SINTA  /  PROJECT MANAGER", Color("#8e7763"), true)
	_box("Sprint board frame", Vector3(8.2, 2.15, -38.78), Vector3(5.6, 2.5, 0.11), Color("#4b5d55"), false)
	_box("Sprint board surface", Vector3(8.2, 2.15, -38.70), Vector3(5.34, 2.26, 0.03), Color("#283d3a"), false)
	for x in [6.5, 8.2, 9.9]:
		for y in [1.55, 2.2, 2.85]:
			_box("Sprint kanban card", Vector3(x, y, -38.66), Vector3(1.22, 0.42, 0.035), Color("#d5c9a9"), false)
	# Architect's office / system design review.
	_label("SYSTEM ARCHITECTURE", Vector3(29.0, 3.5, -38.1), 0.006)
	_add_workstation(Vector3(29.0, 0, -31.3), "RAKA  /  SYSTEM ARCHITECT", Color("#7c8c8d"), true)
	_box("Architecture display frame", Vector3(29.0, 2.2, -38.78), Vector3(6.0, 2.3, 0.12), Color("#34464d"), false)
	_box("Architecture diagram screen", Vector3(29.0, 2.2, -38.68), Vector3(5.65, 2.0, 0.035), Color("#25434a"), false, null, 0.2, 0.0, false, Color("#4e9183"))
	for x in [26.0, 28.0, 30.0, 32.0]:
		_box("Diagram node", Vector3(x, 2.2 + (1.0 if int(x) % 2 == 0 else -0.1), -38.61), Vector3(0.58, 0.34, 0.025), Color("#8fc0a1"), false)
	_add_plant(Vector3(20.7, 0, -22.4), 0.9)

func _build_engineering_floor() -> void:
	# Frontend design studio.
	_label("FRONTEND  /  DESIGN STUDIO", Vector3(-29.5, 3.45, -18.9), 0.0057)
	_add_workstation(Vector3(-29.0, 0, -8.9), "DIRA  /  FRONTEND", Color("#9a735f"), true)
	_add_workstation(Vector3(-34.5, 0, -8.9), "UI DESIGN", Color("#a38268"), false)
	_box("Frontend design board frame", Vector3(-29.5, 2.1, -19.0), Vector3(5.5, 2.35, 0.12), Color("#53655f"), false)
	_box("Frontend design board", Vector3(-29.5, 2.1, -18.91), Vector3(5.15, 2.05, 0.03), Color("#e1e6dc"), false)
	for x in [-31.1, -29.5, -27.9]:
		_box("UI design card", Vector3(x, 2.05, -18.86), Vector3(1.25, 1.4, 0.025), Color("#b7c8b9"), false)
	# QA lab with a test bench and monitor stations.
	_label("QUALITY ASSURANCE  /  TEST LAB", Vector3(-6.5, 3.45, -18.9), 0.0057)
	_add_workstation(Vector3(-5.0, 0, -8.9), "TIKA  /  QA ENGINEER", Color("#748d7e"), true)
	_add_workstation(Vector3(1.4, 0, -8.9), "AUTOMATED TEST STATION", Color("#8a9384"), true)
	_box("QA test bench", Vector3(-6.8, 0.86, -14.8), Vector3(7.8, 1.65, 1.15), Color("#7a8983"), true)
	for x in [-9.4, -6.8, -4.2]:
		_box("QA device", Vector3(x, 1.78, -14.7), Vector3(1.15, 0.72, 0.16), Color("#293940"), false)
		_box("QA device screen", Vector3(x, 1.79, -14.605), Vector3(0.98, 0.53, 0.025), Color("#30544c"), false, null, 0.2, 0.0, false, Color("#5b9b7e"))
	# Backend pod with collaborative engineering table.
	_label("BACKEND ENGINEERING", Vector3(24.0, 3.45, -18.9), 0.0057)
	_add_workstation(Vector3(27.0, 0, -8.9), "BIMA  /  BACKEND", Color("#6d8490"), true)
	_add_workstation(Vector3(34.0, 0, -8.9), "SERVICE MONITORING", Color("#708a86"), true)
	_box("Backend rack cabinet", Vector3(37.0, 1.2, -14.6), Vector3(1.6, 2.35, 0.9), Color("#3b4a4d"), true)
	for y in [0.5, 0.95, 1.40, 1.85]:
		_box("Rack server face", Vector3(36.13, y, -14.6), Vector3(0.045, 0.28, 0.68), Color("#29373c"), false)
		for x in [36.12, 36.12]:
			_sphere("Server activity LED", Vector3(x, y, -14.2), 0.035, Color("#76c59b"), Vector3.ONE)
	# Shared engineering collaboration table.
	_box("Engineering collaboration table", Vector3(0.0, 0.78, -1.0), Vector3(6.4, 0.16, 2.1), Color("#8b765d"), true)
	for x in [-2.7, 2.7]:
		for z in [-0.7, 0.7]:
			_box("Collaboration table leg", Vector3(x, 0.38, -1.0 + z), Vector3(0.12, 0.75, 0.12), Color("#66756e"), false)
	for x in [-1.7, -0.6, 0.6, 1.7]:
		_box("Collaboration laptop", Vector3(x, 0.92, -1.0), Vector3(0.66, 0.05, 0.48), Color("#3c4b50"), false)
		_box("Laptop screen", Vector3(x, 1.22, -1.20), Vector3(0.66, 0.55, 0.06), Color("#243a41"), false)
	_add_plant(Vector3(-18.2, 0, -2.0), 0.85)
	_add_plant(Vector3(10.0, 0, -2.2), 0.85)

func _build_meeting_room() -> void:
	_label("BOARDROOM  /  MEETING ROOM", Vector3(-29.5, 3.45, 4.4), 0.0057)
	var table_center := Vector3(-29.5, 0, 14.3)
	_box("Boardroom table top", table_center + Vector3(0, 0.82, 0), Vector3(10.8, 0.18, 3.1), Color("#886b50"), true)
	for x in [-4.7, 4.7]:
		for z in [-1.1, 1.1]:
			_box("Boardroom table pedestal", table_center + Vector3(x, 0.4, z), Vector3(0.28, 0.78, 0.28), Color("#586a62"), false)
	# Ten physically placed chairs support a full engineering review with room
	# for the Owner and observers. Seats align with the local meeting positions.
	for x in [-4.2, -2.1, 0.0, 2.1, 4.2]:
		_add_meeting_chair(table_center + Vector3(x, 0, -2.55), PI)
		_add_meeting_chair(table_center + Vector3(x, 0, 2.55), 0.0)
	_box("Boardroom display frame", Vector3(-29.5, 2.2, 5.05), Vector3(6.3, 2.25, 0.18), Color("#33464c"), false)
	_box("Boardroom display screen", Vector3(-29.5, 2.2, 4.93), Vector3(5.92, 1.9, 0.03), Color("#28464b"), false, null, 0.18, 0.0, false, Color("#477f76"))
	_box("Boardroom whiteboard frame", Vector3(-38.7, 1.9, 15.0), Vector3(0.13, 2.2, 6.5), Color("#6e7b74"), false)
	_box("Boardroom whiteboard", Vector3(-38.61, 1.9, 15.0), Vector3(0.03, 1.92, 6.2), Color("#e6e9e1"), false)
	_box("Boardroom credenza", Vector3(-29.5, 0.7, 23.2), Vector3(8.0, 1.35, 0.72), Color("#7b6856"), true)
	for x in [-32.0, -29.5, -27.0]:
		_cylinder("Meeting water bottle", Vector3(x, 1.49, 23.2), 0.10, 0.42, Color("#91b2af"), null, false, 0.1)

func _add_meeting_chair(position: Vector3, rotation_y: float) -> void:
	var root := Node3D.new()
	root.position = position
	root.rotation.y = rotation_y
	add_child(root)
	# Kursi rapat dengan pivot swivel supaya bisa ikut berputar saat pemain
	# duduk dan meng-interasi mouse. Sandar di sisi +z (belakang pemain yang
	# menghadap -z/varian yaw), sehingga tampilan menghadap meja betul.
	var swivel := Node3D.new()
	swivel.name = "ChairSwivel"
	root.add_child(swivel)
	_box("Meeting chair seat", Vector3(0, 0.58, 0), Vector3(0.92, 0.16, 0.82), Color("#5e766d"), false, swivel)
	_box("Meeting chair back", Vector3(0, 1.02, 0.34), Vector3(0.92, 0.88, 0.14), Color("#50675f"), false, swivel)
	for x in [-0.35, 0.35]:
		for z in [-0.28, 0.28]:
			_box("Meeting chair leg", Vector3(x, 0.27, z), Vector3(0.08, 0.55, 0.08), Color("#596a63"), false, root, 0.35, 0.5)
	seats.append({"position": position, "yaw": rotation_y, "kind": "meeting", "pivot": swivel, "label": "Kursi Rapat"})

func _build_api_lab() -> void:
	_label("API  /  INFRASTRUCTURE LAB", Vector3(29.0, 3.45, 4.4), 0.0057)
	_add_workstation(Vector3(29.0, 0, 12.65), "NAYA  /  API SPECIALIST", Color("#987f5b"), true)
	# Two compact server racks and diagnostics board.
	for x in [21.0, 24.0, 37.0]:
		_box("Infrastructure rack", Vector3(x, 1.35, 22.0), Vector3(1.8, 2.65, 0.95), Color("#344247"), true)
		for level in range(5):
			var y := 0.48 + float(level) * 0.43
			_box("Rack equipment", Vector3(x, y, 21.49), Vector3(1.52, 0.32, 0.06), Color("#202f35"), false)
			for led in range(4):
				_sphere("Rack LED", Vector3(x - 0.55 + float(led) * 0.17, y, 21.43), 0.035, Color("#73c49a"), Vector3.ONE)
	_box("API topology board", Vector3(30.0, 2.4, 24.65), Vector3(7.2, 1.55, 0.12), Color("#334a48"), false)
	for x in [27.0, 29.0, 31.0, 33.0]:
		_box("API topology node", Vector3(x, 2.4, 24.55), Vector3(0.75, 0.48, 0.04), Color("#a6c2ad"), false)

func _build_archive_and_print() -> void:
	_label("COMPANY ARCHIVE  /  PRINT ROOM", Vector3(-29.5, 3.45, 25.8), 0.0057)
	for z in [28.5, 33.0, 37.0]:
		_add_shelf(Vector3(-37.0, 0.16, z), 3.5, 2.65, 0.9, "ARCHIVE")
		_add_shelf(Vector3(-31.8, 0.16, z), 3.5, 2.65, 0.9, "REPORTS")
	# Print station with paper drawers and output tray.
	_box("Printer cabinet", Vector3(-23.2, 0.72, 31.5), Vector3(3.0, 1.4, 1.75), Color("#8b9690"), true)
	_box("Printer body", Vector3(-23.2, 1.62, 31.5), Vector3(2.5, 0.55, 1.55), Color("#e5e8e2"), false)
	_box("Printer scanner lid", Vector3(-23.2, 1.94, 31.48), Vector3(2.25, 0.10, 1.35), Color("#aab5ae"), false)
	_box("Printer touch screen frame", Vector3(-24.0, 1.69, 30.68), Vector3(0.58, 0.40, 0.08), Color("#39494b"), false)
	_box("Printer touch screen", Vector3(-24.0, 1.70, 30.625), Vector3(0.46, 0.28, 0.025), Color("#759d8e"), false, null, 0.2, 0.0, false, Color("#5b9b7f"))
	_box("Printer output slot", Vector3(-22.3, 1.49, 30.69), Vector3(1.10, 0.07, 0.12), Color("#59655f"), false)
	for i in range(5):
		_box("Printer paper stack", Vector3(-22.1, 1.58 + float(i) * 0.025, 31.1), Vector3(0.78, 0.022, 0.56), Color("#f1efe7"), false)
	_box("Archive checkout counter", Vector3(-27.4, 0.75, 29.5), Vector3(5.1, 1.42, 0.90), Color("#82694f"), true)
	_box("Archive counter top", Vector3(-27.4, 1.50, 29.5), Vector3(5.3, 0.14, 1.05), Color("#c4a984"), false)
	_add_plant(Vector3(-21.5, 0, 37.3), 0.8)

func _build_pantry_and_lounge() -> void:
	_label("PANTRY  /  STAFF LOUNGE", Vector3(10.0, 3.45, 25.8), 0.0057)
	# Ruang pribadi Owner (sebelumnya Promotion studio yang kosong): ruang
	# santai privat dengan area duduk, perpustakaan, kitchenette dan TV.
	_label("OWNER  /  RUANG PRIBADI", Vector3(-10.0, 3.45, 25.8), 0.0054)
	_box("Owner lounge accent wall", Vector3(-10.0, 1.95, 39.72), Vector3(18.6, 3.7, 0.10), Color("#6b4a38"), false)
	_box("Owner lounge accent trim", Vector3(-10.0, 0.42, 39.66), Vector3(18.6, 0.10, 0.05), Color("#c5a366"), false)
	_box("Owner lounge rug", Vector3(-10.0, 0.16, 32.0), Vector3(15.0, 0.06, 9.0), Color("#7c5f4a"), false)
	_box("Owner lounge rug inset", Vector3(-10.0, 0.20, 32.0), Vector3(13.4, 0.045, 7.6), Color("#8f7260"), false)
	_add_lounge_sofa(Vector3(-10.0, 0, 34.6), PI, Color("#7a5a44"), 4.2)
	_box("Owner lounge coffee table", Vector3(-10.0, 0.46, 32.6), Vector3(3.2, 0.60, 1.35), Color("#8a6a4c"), false)
	_box("Owner lounge table top", Vector3(-10.0, 0.80, 32.6), Vector3(3.45, 0.12, 1.55), Color("#c8aa83"), false)
	_cylinder("Owner lounge mug", Vector3(-10.8, 0.97, 32.4), 0.09, 0.14, Color("#e7e1d4"))
	_box("Owner lounge book stack", Vector3(-9.2, 0.90, 32.8), Vector3(0.55, 0.16, 0.40), Color("#5e756a"), false)
	# TV wall panel di seberang sofa.
	_box("Owner lounge TV frame", Vector3(-10.0, 2.05, 25.45), Vector3(5.4, 1.95, 0.14), Color("#2f3f3c"), false)
	_box("Owner lounge TV screen", Vector3(-10.0, 2.05, 25.36), Vector3(5.05, 1.62, 0.03), Color("#1c2f36"), false, null, 0.18, 0.0, false, Color("#3f6d68"))
	_box("Owner lounge TV bar", Vector3(-10.0, 1.18, 25.40), Vector3(3.2, 0.08, 0.05), Color("#35464a"), false)
	# Perpustakaan pribadi.
	_add_shelf(Vector3(-17.5, 0.16, 36.5), 3.4, 2.65, 0.9, "PERPUSTAKAAN PRIBADI")
	_add_shelf(Vector3(-17.5, 0.16, 29.5), 3.4, 2.65, 0.9, "KOLEKSI")
	# Kitchenette pribadi.
	_box("Owner kitchenette cabinet", Vector3(-3.4, 0.72, 36.5), Vector3(3.6, 1.42, 1.05), Color("#7c6853"), false)
	_box("Owner kitchenette countertop", Vector3(-3.4, 1.48, 36.35), Vector3(3.8, 0.14, 1.25), Color("#d3cbb9"), false)
	_box("Owner kitchenette kettle", Vector3(-3.9, 1.75, 36.2), Vector3(0.34, 0.42, 0.34), Color("#3b4e4b"), false)
	_cylinder("Owner kitchenette mug", Vector3(-3.1, 1.62, 36.2), 0.09, 0.14, Color("#e7e1d4"))
	_box("Owner mini fridge", Vector3(-1.9, 0.65, 38.3), Vector3(0.9, 1.25, 0.85), Color("#c4cbc6"), false, null, 0.28, 0.3)
	# Lampu lantai hangat + tanaman + dekorasi.
	_cylinder("Owner floor lamp pole", Vector3(-4.4, 0.85, 28.5), 0.045, 1.6, Color("#596b63"))
	_box("Owner floor lamp glow", Vector3(-4.4, 1.72, 28.5), Vector3(0.42, 0.10, 0.42), Color("#f5e0b8"), false, null, 0.22, 0.0, false, Color("#f8ecca"))
	var owner_lamp := OmniLight3D.new()
	owner_lamp.position = Vector3(-4.4, 1.85, 28.5)
	owner_lamp.light_color = Color("#ffe8c8")
	owner_lamp.light_energy = 0.38
	owner_lamp.omni_range = 7.0
	owner_lamp.shadow_enabled = false
	add_child(owner_lamp)
	_add_plant(Vector3(-18.0, 0, 26.5), 0.95)
	_add_plant(Vector3(-2.8, 0, 26.5), 0.95)
	_add_plant(Vector3(-18.0, 0, 38.5), 1.05)
	_add_framed_poster(Vector3(-19.62, 2.1, 32.5), Color("#c5a366"), "OWNER")
	_add_wall_clock(Vector3(-10.0, 3.0, 39.65))
	_box("Owner lounge sideboard", Vector3(-2.9, 0.72, 29.5), Vector3(3.2, 1.38, 0.70), Color("#8b735c"), false)
	_box("Owner lounge sideboard top", Vector3(-2.9, 1.46, 29.5), Vector3(3.4, 0.12, 0.84), Color("#c8aa83"), false)
	_cylinder("Owner lounge vase", Vector3(-3.6, 1.72, 29.5), 0.16, 0.30, Color("#5e756a"))
	_box("Owner lounge book pile", Vector3(-2.2, 1.62, 29.5), Vector3(0.5, 0.22, 0.36), Color("#7889a8"), false)
	# Kitchen run: upper cabinets, counter, sink, fridge, coffee and microwave.
	_box("Pantry lower cabinets", Vector3(29.0, 0.72, 36.5), Vector3(18.5, 1.42, 1.10), Color("#8d7b68"), true)
	_box("Pantry countertop", Vector3(29.0, 1.48, 36.35), Vector3(18.8, 0.14, 1.30), Color("#d3cbb9"), false)
	for x in [22.0, 27.0, 32.0, 37.0]:
		_box("Pantry upper cabinet", Vector3(x, 2.55, 38.25), Vector3(3.8, 1.15, 0.52), Color("#a18d74"), false)
		_box("Pantry cabinet handle", Vector3(x, 2.52, 37.96), Vector3(0.42, 0.045, 0.06), Color("#d1b987"), false, null, 0.3, 0.55)
	_box("Pantry sink", Vector3(34.0, 1.58, 36.15), Vector3(1.8, 0.08, 0.75), Color("#7b8c86"), false, null, 0.2, 0.48)
	_cylinder("Pantry faucet", Vector3(34.0, 1.89, 35.8), 0.045, 0.54, Color("#bcc7c1"), null, false, 0.85)
	_box("Coffee machine", Vector3(22.5, 2.00, 36.05), Vector3(1.0, 0.92, 0.80), Color("#3b4e4b"), false)
	_box("Coffee machine screen", Vector3(22.5, 2.15, 35.62), Vector3(0.58, 0.25, 0.035), Color("#89b7a3"), false, null, 0.18, 0.0, false, Color("#5a9b7d"))
	_box("Microwave", Vector3(26.0, 2.0, 36.05), Vector3(1.25, 0.72, 0.78), Color("#77847f"), false)
	_box("Refrigerator", Vector3(38.5, 1.45, 31.8), Vector3(1.7, 2.75, 1.55), Color("#c4cbc6"), true, null, 0.28, 0.3)
	_box("Fridge handle", Vector3(37.72, 1.55, 31.1), Vector3(0.07, 0.75, 0.08), Color("#77857f"), false, null, 0.3, 0.6)
	# Dining island and stools.
	_box("Pantry island", Vector3(27.5, 0.88, 29.0), Vector3(9.0, 1.62, 1.45), Color("#92775b"), true)
	_box("Pantry island stone top", Vector3(27.5, 1.73, 29.0), Vector3(9.25, 0.16, 1.65), Color("#d8d0be"), false)
	for x in [24.2, 27.5, 30.8]:
		_cylinder("Bar stool stem", Vector3(x, 0.55, 26.9), 0.075, 0.98, Color("#65736d"), null, false, 0.55)
		_cylinder("Bar stool seat", Vector3(x, 1.08, 26.9), 0.42, 0.14, Color("#61796e"))
	# Lounge zone with a softer rug and small group seating.
	_box("Lounge rug", Vector3(9.0, 0.16, 32.0), Vector3(16.0, 0.06, 9.5), Color("#87998d"), false)
	_add_lounge_sofa(Vector3(7.0, 0, 29.2), 0.0, Color("#687f73"), 3.8)
	_add_lounge_sofa(Vector3(7.0, 0, 35.0), PI, Color("#687f73"), 3.8)
	_box("Lounge coffee table", Vector3(7.0, 0.48, 32.1), Vector3(3.3, 0.15, 1.35), Color("#a98561"), false)
	_add_plant(Vector3(15.0, 0, 29.0), 1.0)
	_add_plant(Vector3(15.0, 0, 35.0), 1.0)
	_box("Lounge wall display", Vector3(9.0, 2.1, 38.75), Vector3(5.6, 2.0, 0.14), Color("#41544b"), false)
	_box("Lounge display screen", Vector3(9.0, 2.1, 38.65), Vector3(5.25, 1.66, 0.03), Color("#254039"), false, null, 0.18, 0.0, false, Color("#426d57"))

## Kursi bebas yang tidak terikat workstation: klaster lounge di lobby luas
## plus kursi geser di QA supaya setiap bengkel/jabatan punya tempat duduk.
func _build_free_seating() -> void:
	# Klaster duduk lobby: karpet hangat, meja kopi kecil, empat kursi swivel.
	# Ditempatkan rapi di sisi barat pintu masuk, jalur tengah tetap kosong.
	_box("Lobby seating rug", Vector3(-8.0, 0.14, 27.8), Vector3(6.6, 0.03, 5.6), Color("#b58f7d"), false, null, 0.9)
	_box("Lobby coffee table base", Vector3(-8.0, 0.42, 27.8), Vector3(1.15, 0.30, 1.75), Color("#9a7958"), true, null, 0.4)
	_box("Lobby coffee table tray", Vector3(-8.0, 0.595, 27.8), Vector3(0.95, 0.05, 1.55), Color("#7b6856"), false, null, 0.42, 0.1)
	for chair in [
		{"pos": Vector3(-9.8, 0, 26.2), "yaw": 0.0},
		{"pos": Vector3(-6.2, 0, 26.2), "yaw": 0.0},
		{"pos": Vector3(-9.8, 0, 29.4), "yaw": PI},
		{"pos": Vector3(-6.2, 0, 29.4), "yaw": PI},
	]:
		_add_office_chair(chair["pos"], Color("#5f776d"), chair["yaw"], "Kursi Tamu Lobby")
	# Tiga kursi geser di ruang QA untuk rapat cepat / pairing.
	for chair in [
		{"pos": Vector3(-4.5, 0, -3.2), "yaw": PI},
		{"pos": Vector3(-0.5, 0, -3.2), "yaw": PI},
		{"pos": Vector3(3.5, 0, -3.2), "yaw": PI},
	]:
		_add_office_chair(chair["pos"], Color("#62807c"), chair["yaw"], "Kursi Kolaborasi QA")

## Papan informasi tamu: direktori ruangan & pengumuman di sisi pintu masuk,
## jadwal rapat di dekat Boardroom. Semua menghadap jalur pengunjung.
func _build_information_boards() -> void:
	_info_board("InfoDirectory", Vector3(10.8, 0, 34.4), -0.35, "DIREKTORI RUANGAN", [
		"Utara: Owner Office · Secretariat",
		"Utara: Management · Architecture",
		"Barat: Frontend · QA Engineering",
		"Barat: Boardroom · Archive & Print",
		"Timur: Backend · API Lab · Pantry",
		"Tengah: Resepsionis · ekstensi 100",
	])
	_info_board("InfoAnnounce", Vector3(-10.8, 0, 34.4), 0.35, "PENGUMUMAN MINGGU INI", [
		"Senin 09.00 · All-hands (Boardroom)",
		"Selasa 14.00 · Fire drill area lobby",
		"Kamis 13.00 · Sharing sesi QA",
		"Jumat 15.00 · Sprint review",
		"Kopi & donat tiap Jumat 16.00",
	])
	_info_board("InfoBoardroom", Vector3(-19.35, 0, 17.8), PI * 0.5, "JADWAL BOARDROOM", [
		"Senin 09.00 · All-hands",
		"Kamis 13.00 · Review arsitektur",
		"Jumat 15.00 · Sprint review",
		"Kapasitas: 10 orang",
		"Pemesanan: hubungi resepsionis",
	], 2.1, 1.9)

func _build_accent_walls() -> void:
	# Cat aksen pada dinding fitur per ruangan — warna tenang sesuai palet
	# desain, pemasangan sebagai panel tipis agar tidak mengubah struktur.
	# Boardroom: panel terakota mengapit display + lis kuningan di whiteboard.
	for x in [-35.5, -23.5]:
		_box("Boardroom terracotta accent", Vector3(x, 1.95, 4.86), Vector3(2.4, 2.9, 0.08), Color("#9a6a58"), false)
		_box("Boardroom accent trim", Vector3(x, 0.48, 4.87), Vector3(2.4, 0.10, 0.09), Color("#c5a366"), false)
	_box("Boardroom brass line", Vector3(-39.68, 0.75, 15.0), Vector3(0.06, 0.12, 6.0), Color("#c5a366"), false)
	# Owner suite: wainscot walnut + lis kuningan di bawah crest fitur.
	_box("Owner wainscot walnut", Vector3(-29.5, 0.55, -38.88), Vector3(16.5, 0.85, 0.06), Color("#6b5238"), false)
	_box("Owner brass trim", Vector3(-29.5, 1.02, -38.89), Vector3(16.5, 0.09, 0.06), Color("#c5a366"), false)
	# Management: panel sage di atas sprint board.
	_box("Management sage accent", Vector3(8.2, 3.15, -38.80), Vector3(6.4, 0.70, 0.06), Color("#6f8a7a"), false)
	# Engineering: band slate-teal setinggi sandaran kursi di sisi selatan.
	_box("Engineering slate band", Vector3(0.0, 0.70, 3.86), Vector3(36.0, 1.0, 0.05), Color("#4c666a"), false)
	# API lab: panel grafit di dinding timur.
	_box("API graphite accent", Vector3(39.74, 1.95, 14.5), Vector3(0.06, 2.9, 5.0), Color("#3a4a4d"), false)
	for y in [1.2, 1.95, 2.7]:
		_box("API accent node", Vector3(39.70, y, 14.5), Vector3(0.04, 0.5, 0.5), Color("#73c49a"), false, null, 0.2, 0.0, false, Color("#5b9b7e"))
	# Lobby: panel pasir hangat di balik direktori + medali lantai + bangku.
	_box("Lobby sand accent", Vector3(12.05, 1.60, 28.2), Vector3(0.08, 3.2, 2.6), Color("#b8a88e"), false)
	_cylinder("Lobby floor medallion", Vector3(11.8, 0.16, 28.2), 2.1, 0.05, Color("#7c8a7e"), null, false, 0.4)
	_cylinder("Lobby medallion inner", Vector3(11.8, 0.20, 28.2), 1.35, 0.055, Color("#9aa78f"), null, false, 0.4)
	_box("Lobby visitor bench", Vector3(-14.0, 0.52, 24.5), Vector3(3.4, 0.16, 0.75), Color("#92785c"), false)
	_box("Lobby bench back", Vector3(-14.0, 0.96, 24.15), Vector3(3.4, 0.7, 0.14), Color("#92785c"), false)
	for x in [-15.4, -12.6]:
		_box("Lobby bench leg", Vector3(x, 0.25, 24.5), Vector3(0.13, 0.5, 0.13), Color("#52635b"), false)
	# Lis ambang pintu berwarna per sayap ruangan (wayfinding halus).
	for x in [-29.0, -11.0, 8.0, 29.0]:
		_box("Door threshold north wing", Vector3(x, 0.17, -20.0), Vector3(2.9, 0.045, 0.5), Color("#6f8a7a"), false)
	for x in [-29.0, -6.5, 0.0, 13.0, 29.0]:
		_box("Door threshold engineering", Vector3(x, 0.17, 4.0), Vector3(2.9, 0.045, 0.5), Color("#4c666a"), false)
	for x in [-29.0, 0.0, 29.0]:
		_box("Door threshold south wing", Vector3(x, 0.17, 25.0), Vector3(2.9, 0.045, 0.5), Color("#9a6a58"), false)
	# Tanaman sudut tambahan di koridor.
	_add_plant(Vector3(-18.5, 0, -17.5), 0.85)
	_add_plant(Vector3(18.5, 0, -17.5), 0.85)
	_add_plant(Vector3(-18.5, 0, 21.5), 0.85)
	_add_plant(Vector3(-18.5, 0, -38.5), 1.0)
	_add_plant(Vector3(18.5, 0, -38.5), 1.0)
	# Poster tambahan di lorong selatan.
	_add_framed_poster(Vector3(-19.62, 2.1, 10.0), Color("#9a6a58"), "BANGKAH")
	_add_framed_poster(Vector3(19.62, 2.1, 10.0), Color("#6f8a7a"), "INTEGRITY")

func _build_corridor_details() -> void:
	# Jalur yang rapi & lega: runner masuk saja di poros pintu, panel akustik
	# menempel di dinding nyata, koridor tengah bebas benda.
	_box("Lobby entry runner", Vector3(0, 0.148, 31.0), Vector3(5.2, 0.035, 13.0), Color("#a17a5a"), false, null, 0.86)
	for x in [-2.35, 2.35]:
		_box("Entry runner trim", Vector3(x, 0.175, 31.0), Vector3(0.05, 0.028, 13.0), Color("#d3b98a"), false, null, 0.4, 0.4)
	# Panel akustik menempel dinding exterior (bukan melayang).
	for z in [-14.0, 10.0, 22.0]:
		_box("Acoustic wall panel west", Vector3(-41.62, 1.8, z), Vector3(0.10, 1.5, 5.2), Color("#9baa9e"), false, null, 0.88)
		_box("Acoustic wall panel east", Vector3(41.62, 1.8, z), Vector3(0.10, 1.5, 5.2), Color("#9baa9e"), false, null, 0.88)
	for x in [-11.0, 11.0]:
		_box("Acoustic wall panel north", Vector3(x, 1.8, -39.64), Vector3(5.2, 1.5, 0.10), Color("#9baa9e"), false, null, 0.88)
	for x in [-38.8, 41.8]:
		for z in [-31.0, -7.0, 14.0, 33.0]:
			_add_plant(Vector3(minf(x, 41.5), 0, z), 0.85)

func _add_plant(position: Vector3, scale_value: float = 1.0) -> void:
	_cylinder("Decorative planter", position + Vector3(0, 0.32 * scale_value, 0), 0.42 * scale_value, 0.62 * scale_value, Color("#9c8268"))
	_cylinder("Planter soil", position + Vector3(0, 0.64 * scale_value, 0), 0.35 * scale_value, 0.06, Color("#493e31"))
	for i in range(6):
		var angle := TAU * float(i) / 6.0
		_sphere("Plant foliage", position + Vector3(cos(angle) * 0.28 * scale_value, 1.05 * scale_value + float(i % 2) * 0.16, sin(angle) * 0.28 * scale_value), 0.34 * scale_value, Color("#6f9275"), Vector3(1.0, 1.25, 0.84))
	_sphere("Plant crown", position + Vector3(0, 1.36 * scale_value, 0), 0.32 * scale_value, Color("#88a886"), Vector3(1.0, 1.3, 1.0))

func _build_office_accessories() -> void:
	# Wall clocks mounted on the solid north wall (was floating, now attached).
	for spot in [Vector3(-29.5, 3.2, -39.62), Vector3(8.0, 3.2, -39.62), Vector3(29.0, 3.2, -39.62)]:
		_add_wall_clock(spot, -PI * 0.5)
	# Framed posters attached to the solid west/east walls.
	_add_framed_poster(Vector3(-41.62, 2.1, -15.0), Color("#3a5a4a"), "INNOVATION", 0.0)
	_add_framed_poster(Vector3(-41.62, 2.1, 10.0), Color("#5a4a3a"), "QUALITY", 0.0)
	_add_framed_poster(Vector3(41.62, 2.1, -15.0), Color("#4a5a6a"), "COLLABORATION", PI)
	_add_framed_poster(Vector3(41.62, 2.1, 10.0), Color("#3a5a5a"), "PRECISION", PI)
	# Desk plants — small potted plants on collaboration tables and corners.
	_add_desk_plant(Vector3(0.0, 0.87, -1.0), 0.4)
	_add_desk_plant(Vector3(-29.5, 0.87, 14.3), 0.4)
	# Conference room water dispenser.
	_box("Water dispenser body", Vector3(-35.0, 1.0, 19.0), Vector3(0.6, 1.6, 0.6), Color("#3a4a4d"), true)
	_box("Water dispenser jug", Vector3(-35.0, 1.6, 19.0), Vector3(0.42, 0.62, 0.42), Color(0.6, 0.75, 0.78, 0.35), false, null, 0.16, 0.05, true)
	_box("Water dispenser tap", Vector3(-35.0, 0.78, 18.72), Vector3(0.10, 0.06, 0.08), Color("#8a928c"), false, null, 0.3, 0.5)
	# Mini fridge in the engineering area.
	_box("Mini fridge", Vector3(37.0, 0.65, -3.0), Vector3(1.0, 1.25, 0.75), Color("#c4cbc6"), true, null, 0.28, 0.3)
	_box("Fridge handle", Vector3(36.58, 0.75, -3.0), Vector3(0.05, 0.35, 0.04), Color("#77857f"), false, null, 0.3, 0.6)
	# Whiteboard markers and erasers on boards.
	for x in [6.5, 8.2, 9.9]:
		_box("Whiteboard marker", Vector3(x, 1.0, -38.62), Vector3(0.04, 0.025, 0.03), Color("#4a6e9a"), false)
		_box("Marker cap", Vector3(x, 1.0, -38.58), Vector3(0.03, 0.025, 0.02), Color("#2a4a7a"), false)
	# Coffee mug stations — random mugs on desks.
	for position in [Vector3(27.0, 0.95, -7.5), Vector3(-5.0, 0.95, -7.5), Vector3(-29.0, 0.95, -7.5)]:
		_cylinder("Desk mug", position, 0.10, 0.16, Color("#e7d8c4"))
		_cylinder("Mug coffee", position + Vector3(0, 0.04, 0), 0.075, 0.012, Color("#4a2818"))
	# Sticky notes on board surfaces.
	for x in [7.0, 8.5, 10.0]:
		for y in [1.7, 2.3, 2.85]:
			var note_color: Color = [Color("#f5e88a"), Color("#a8d8b0"), Color("#f0b8a0")][int(y) % 3]
			_box("Sticky note", Vector3(x, y, -38.63), Vector3(0.28, 0.32, 0.012), note_color, false)
	# Floor-standing magazine stand in the lounge.
	_box("Magazine stand base", Vector3(13.0, 0.25, 33.0), Vector3(0.9, 0.5, 0.4), Color("#8a7256"), true)
	for y in [0.55, 0.80, 1.05]:
		_box("Magazine stand shelf", Vector3(13.0, y, 33.0), Vector3(0.85, 0.04, 0.36), Color("#a8896a"), false)

func _add_wall_clock(position: Vector3, yaw: float = 0.0) -> void:
	# Jam dinding sebagai node berorientasi bila butuh dipasang di dinding arah lain.
	var root := Node3D.new()
	root.name = "WallClock"
	root.position = position
	root.rotation.y = yaw
	add_child(root)
	_box("Clock frame", Vector3(0, 0, 0), Vector3(0.06, 0.6, 0.6), Color("#3a3a3a"), false, root, 0.35, 0.15)
	_box("Clock face", Vector3(0.01, 0, 0), Vector3(0.04, 0.52, 0.52), Color("#f4f2e9"), false, root, 0.25, 0.0)
	_box("Clock hour hand", Vector3(0.02, 0.05, 0), Vector3(0.02, 0.14, 0.02), Color("#2a2a2a"), false, root)
	_box("Clock minute hand", Vector3(0.022, 0.08, 0), Vector3(0.015, 0.20, 0.02), Color("#2a2a2a"), false, root)
	# Clock numerals at 12, 3, 6, 9.
	for angle in [0.0, PI * 0.5, PI, PI * 1.5]:
		var x: float = sin(angle) * 0.22
		var z: float = cos(angle) * 0.22
		_box("Clock numeral", Vector3(0.03, x, z), Vector3(0.015, 0.04, 0.04), Color("#666"), false, root)
	# Center dot.
	_sphere("Clock center", Vector3(0.025, 0, 0), 0.022, Color("#1a1a1a"))

func _add_framed_poster(position: Vector3, accent: Color, text: String, yaw: float = 0.0) -> void:
	# Poster selalu menempel dinding nyata; yaw menentukan arah muka teks.
	var root := Node3D.new()
	root.name = "FramedPoster"
	root.position = position
	root.rotation.y = yaw
	add_child(root)
	_box("Poster frame", Vector3(0, 0, 0), Vector3(0.08, 1.2, 0.9), Color("#4a4035"), false, root, 0.42, 0.05)
	_box("Poster background", Vector3(0.01, 0, 0), Vector3(0.04, 1.06, 0.76), Color("#1a1e1c"), false, root)
	_box("Poster accent bar", Vector3(0.015, 0.32, 0), Vector3(0.03, 0.06, 0.68), accent, false, root, 0.3, 0.0, false, accent.lightened(0.2))
	_box("Poster text area", Vector3(0.015, -0.25, 0), Vector3(0.03, 0.42, 0.68), Color("#2a2e2c"), false, root)
	_label(text, Vector3(0.05, -0.25, 0), 0.004, Color("#e8e8e0"), root)

func _add_desk_plant(position: Vector3, scale_value: float = 0.5) -> void:
	_cylinder("Desk planter", position, 0.18 * scale_value, 0.22 * scale_value, Color("#a08868"))
	_cylinder("Desk planter rim", position + Vector3(0, 0.10 * scale_value, 0), 0.20 * scale_value, 0.04 * scale_value, Color("#8a7252"))
	for i in range(5):
		var angle := TAU * float(i) / 5.0
		var r := 0.14 * scale_value
		var h := 0.38 * scale_value + float(i % 2) * 0.10 * scale_value
		_sphere("Desk plant leaf", position + Vector3(cos(angle) * r, h, sin(angle) * r), 0.15 * scale_value, Color("#6f9275" if i % 2 == 0 else "#7ba380"), Vector3(1.0, 1.3, 0.8))
	_sphere("Desk plant crown", position + Vector3(0, 0.45 * scale_value, 0), 0.14 * scale_value, Color("#88a886"), Vector3(1.0, 1.3, 1.0))

func _build_landscape() -> void:
	# Entry landscaping, company sign, flag poles, outdoor seating and trees.
	_box("Entrance planter left", Vector3(-13.2, 0.34, 44.2), Vector3(5.5, 0.68, 2.3), Color("#8a9b88"), false)
	_box("Entrance planter right", Vector3(13.2, 0.34, 44.2), Vector3(5.5, 0.68, 2.3), Color("#8a9b88"), false)
	for x in [-14.5, -12.5, -10.5, 10.5, 12.5, 14.5]:
		_add_plant(Vector3(x, 0.55, 44.2), 0.72)
	_box("Outdoor company monument", Vector3(-24.0, 1.55, 42.3), Vector3(7.4, 3.1, 0.72), Color("#42584c"), false)
	_box("Outdoor monument fascia", Vector3(-24.0, 2.75, 41.86), Vector3(7.4, 2.0, 0.09), Color("#33453c"), false)
	_raised_text("BANGKAH", Vector3(-24.0, 2.85, 41.82), 0, 0.95, 0.11, Color("#e8d3a0"))
	_label("HEADQUARTERS", Vector3(-24.0, 1.85, 41.81), 0.0052, Color("#d5e2d3"))
	for x in [-35.0, 35.0]:
		_cylinder("Flag pole", Vector3(x, 2.5, 44.0), 0.055, 5.0, Color("#b7c0ba"), null, false, 0.7)
		_box("Company flag", Vector3(x + 0.72, 4.15, 44.0), Vector3(1.45, 0.82, 0.055), Color("#567f6a"), false)
	for position in [Vector3(-46,0,25), Vector3(-48,0,0), Vector3(-46,0,-28), Vector3(47,0,24), Vector3(48,0,-4), Vector3(46,0,-30), Vector3(-32,0,60), Vector3(32,0,60)]:
		_add_tree(position)
	_box("Outdoor bench seat", Vector3(20, 0.52, 46.5), Vector3(3.2, 0.18, 0.7), Color("#92785c"), false)
	_box("Outdoor bench back", Vector3(20, 0.96, 46.2), Vector3(3.2, 0.7, 0.14), Color("#92785c"), false)
	for x in [18.8, 21.2]:
		_box("Bench leg", Vector3(x, 0.25, 46.5), Vector3(0.13, 0.5, 0.13), Color("#52635b"), false)

func _add_tree(position: Vector3) -> void:
	_cylinder("Tree trunk", position + Vector3(0, 1.15, 0), 0.24, 2.3, Color("#735b45"))
	_sphere("Tree canopy", position + Vector3(0, 2.55, 0), 1.5, Color("#668b6d"), Vector3(1.05, 1.0, 1.05))
	_sphere("Tree canopy detail", position + Vector3(0.72, 2.85, -0.22), 0.9, Color("#83a27b"), Vector3(1.1, 0.9, 0.95))
	_sphere("Tree canopy detail", position + Vector3(-0.68, 2.78, 0.16), 0.84, Color("#779975"), Vector3(1.0, 0.94, 1.0))
