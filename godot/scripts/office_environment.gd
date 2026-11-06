extends Node3D

## Design tokens / constants used across the office build. Raised ceiling
## heights keep first-person sightlines airy instead of cramped.
const WALL_H := 5.6			# exterior wall height
const PART_H := 5.30		# interior partition glass height
const CEIL_Y := 5.45		# acoustic ceiling panel plane
const DOOR_H := 3.35		# door opening height (taller)
const DOOR_W := 2.9			# door opening width
const FLOOR_H := 6.2			# per-floor story height (slab-to-slab)
const L1_Y := 0.0
const L2_Y := FLOOR_H		# 6.2
const L3_Y := FLOOR_H * 2.0	# 12.4

## Small-town district lives south-east of the headquarters. Employee homes and
## the company parking lot are visual/ambient spaces; they do not create backend
## state. The parking waypoint is the hand-off point for commute routes.
const TOWN_ORIGIN := Vector3(88.0, 0.0, 18.0)
const HQ_ENTRANCE := Vector3(0.0, 0.05, 36.8)
const HQ_PARKING_WALK := Vector3(16.0, 0.05, 47.5)
const HQ_SIDEWALK := Vector3(48.0, 0.05, 47.5)
const TOWN_GATE := Vector3(68.0, 0.05, 47.5)

# Procedural interior for Bangkah HQ. All objects are native Godot meshes so the
# project opens without paid asset packs or external downloads.

var _materials: Dictionary = {}
var _material_cache: Dictionary = {}
# Registrasi titik makan duduk (kursi/sofa) untuk sistem interaksi di main.gd.
# Isi: {"position": Vector3, "yaw": float, "kind": String, "pivot": Node3D or null}
var seats: Array[Dictionary] = []
# Registrasi pintu interaktif: {"position", "label", "open", "leaves": [{"node", "closed", "open"}]}
var doors: Array[Dictionary] = []
# Kendaraan drivable (visual): {"id","label","position","yaw","color","kind"}
var vehicles: Array[Dictionary] = []
var _floor_y: float = 0.0
# HQ perimeter trees collected in _build_landscape, rendered as MultiMesh in _build_town_district.
var _trees_pending: Array[Vector3] = []

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
	_build_exterior_facade()
	_build_room_partitions()
	_build_room_floors()
	_build_ceiling_and_lighting()
	# L1: lobby/reception + public/services (LANTAI 1)
	_floor_y = L1_Y
	_build_reception()
	_build_meeting_room()
	_build_api_lab()
	_build_archive_and_print()
	_build_staff_pantry_lounge()
	_build_free_seating_l1()
	_build_information_boards()
	_build_accent_walls_l1()
	_build_floor_cores() # stairs+lift landings all floors
	# L2: core employees / karyawan inti (LANTAI 2)
	_floor_y = L2_Y
	_build_secretary_office()
	_build_management_offices()
	_build_engineering_floor()
	_build_free_seating_l2()
	_build_accent_walls_l2()
	# L3: Owner (LANTAI 3)
	_floor_y = L3_Y
	_build_owner_suite()
	_build_owner_private_lounge()
	_build_accent_walls_l3()
	_floor_y = 0.0
	_build_landscape()
	_build_company_parking()
	_build_town_district()
	_build_wayfinding()
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
	root.position = position + (Vector3.ZERO if parent != null else Vector3(0, _floor_y, 0))
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
	root.position = position + (Vector3.ZERO if parent != null else Vector3(0, _floor_y, 0))
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
	mesh.position = position + (Vector3.ZERO if parent != null else Vector3(0, _floor_y, 0))
	mesh.scale = scale
	mesh.material_override = _mat(color)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	if parent != null:
		parent.add_child(mesh)
	else:
		add_child(mesh)
	return mesh

func _label(text_value: String, position: Vector3, size: float = 0.007, color: Color = Color("#f4f2e9"), parent: Node3D = null, y_off: float = 0.0) -> Label3D:
	var label := Label3D.new()
	label.text = text_value.to_upper()
	label.position = position + Vector3(0, y_off, 0) + Vector3(0, y_off, 0) + Vector3(0, y_off, 0)
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


## Flat painted text ("tali air") for road/sign logos — no 3D extrusion, no billboard.
func _painted_text(text_value: String, position: Vector3, yaw: float = 0.0, size: float = 0.0045, color: Color = Color("#f4f2e9"), outline: Color = Color(0.05,0.08,0.07,0.85), parent: Node3D = null, y_off: float = 0.0) -> Label3D:
	var label := Label3D.new()
	label.name = "PaintedText"
	label.text = text_value.to_upper()
	label.position = position + Vector3(0, y_off + (0.0 if parent != null else _floor_y), 0)
	label.rotation.y = yaw
	label.font_size = 40
	label.outline_size = 8
	label.modulate = color
	label.outline_modulate = outline
	label.billboard = BaseMaterial3D.BILLBOARD_DISABLED
	label.no_depth_test = false
	label.double_sided = true
	label.pixel_size = size
	label.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
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
	var pp := position + Vector3(0, _floor_y, 0)
	var root := Node3D.new()
	root.name = "%s_%02d" % [board_name, _door_sign_index]
	_door_sign_index += 1
	root.position = pp
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
	title_label.position = pp + text_basis * Vector3(0, 1.75 + height * 0.5 - 0.22, 0.108)
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
	body.position = pp + text_basis * Vector3(0, 1.35, 0.09)
	body.rotation.y = yaw
	add_child(body)

func _wall_segment_x(x1: float, x2: float, z: float, y: float, height: float, color: Color, glass: bool = false, y_off: float = 0.0) -> void:
	if x2 <= x1:
		return
	_box("Glass partition" if glass else "Interior wall", Vector3((x1 + x2) * 0.5, y + y_off, z), Vector3(x2 - x1, height, 0.16), color, true, null, 0.16 if glass else 0.84, 0.05 if glass else 0.0, glass)
	if glass:
		# matte-black aluminum frame posts + 60cm frosted privacy band (mid-eye)
		for x in [x1 + 0.08, x2 - 0.08]:
			_box("Glass mullion", Vector3(x, y + y_off, z), Vector3(0.075, height, 0.20), Color("#1f2326"), false, null, 0.35, 0.38)
		var bw: float = x2 - x1
		if bw > 1.2:
			_box("Glass privacy band", Vector3((x1+x2)*0.5, y_off + 1.55, z), Vector3(bw - 0.12, 0.60, 0.035), Color(0.78, 0.84, 0.82, 0.34), false, null, 0.22, 0.0, true)
			_box("Privacy band line", Vector3((x1+x2)*0.5, y_off + 1.25, z), Vector3(bw - 0.16, 0.012, 0.04), Color(0.15,0.17,0.18,0.35), false, null, 0.4)

func _wall_segment_z(x: float, z1: float, z2: float, y: float, height: float, color: Color, glass: bool = false, y_off: float = 0.0) -> void:
	if z2 <= z1:
		return
	_box("Glass partition" if glass else "Interior wall", Vector3(x, y + y_off, (z1 + z2) * 0.5), Vector3(0.16, height, z2 - z1), color, true, null, 0.16 if glass else 0.84, 0.05 if glass else 0.0, glass)
	if glass:
		for z in [z1 + 0.08, z2 - 0.08]:
			_box("Glass mullion", Vector3(x, y + y_off, z), Vector3(0.20, height, 0.075), Color("#1f2326"), false, null, 0.35, 0.38)
		var bh: float = z2 - z1
		if bh > 1.2:
			_box("Glass privacy band", Vector3(x, y_off + 1.55, (z1+z2)*0.5), Vector3(0.035, 0.60, bh - 0.12), Color(0.78, 0.84, 0.82, 0.34), false, null, 0.22, 0.0, true)
			_box("Privacy band line", Vector3(x, y_off + 1.25, (z1+z2)*0.5), Vector3(0.04, 0.012, bh - 0.16), Color(0.15,0.17,0.18,0.35), false, null, 0.4)

func _partition_x_with_door(x1: float, x2: float, z: float, door_center: float, door_width: float = DOOR_W, door_label: String = "", swing_north: bool = true, y_off: float = 0.0) -> void:
	var left_end := door_center - door_width * 0.5
	var right_start := door_center + door_width * 0.5
	_wall_segment_x(x1, left_end, z, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true, y_off)
	_wall_segment_x(right_start, x2, z, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true, y_off)
	# Frame kayu: post kiri/kanan + header, bukaan setinggi DOOR_H.
	_box("Door frame left", Vector3(left_end + 0.03, y_off + DOOR_H * 0.5, z), Vector3(0.14, DOOR_H + 0.05, 0.28), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door frame right", Vector3(right_start - 0.03, y_off + DOOR_H * 0.5, z), Vector3(0.14, DOOR_H + 0.05, 0.28), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door header", Vector3(door_center, y_off + DOOR_H + 0.09, z), Vector3(door_width + 0.30, 0.18, 0.26), Color("#574132"), false, null, 0.50, 0.1)
	# Transom kaca susu di atas daun pintu sampai atap partisi.
	var transom_h := PART_H - (DOOR_H + 0.18)
	_box("Door transom", Vector3(door_center, y_off + DOOR_H + 0.18 + transom_h * 0.5, z),
		Vector3(door_width + 0.34, transom_h, 0.10), Color(0.72, 0.82, 0.78, 0.38), false, null, 0.28, 0.0, true)
	# Daun pintu ganda membuka ajar (swing north = ke ruang utara). Daun
	# didaftarkan ke registry `doors` supaya main.gd bisa membuka/menutupnya.
	var open_amount := 0.62
	var leaf_left := _add_door_leaf(Vector3(left_end, y_off, z), 0.0, open_amount * (1.0 if swing_north else -1.0), door_width * 0.5 - 0.02)
	var leaf_right := _add_door_leaf(Vector3(right_start, y_off, z), PI, open_amount * (-1.0 if swing_north else 1.0), door_width * 0.5 - 0.02)
	doors.append({
		"position": Vector3(door_center, y_off, z),
		"label": door_label,
		"open": true,
		"leaves": [
			{"node": leaf_left, "closed": 0.0, "open": open_amount * (1.0 if swing_north else -1.0)},
			{"node": leaf_right, "closed": PI, "open": PI + open_amount * (-1.0 if swing_north else 1.0)},
		],
	})
	if door_label != "":
		_add_door_sign(door_center, z, true, swing_north, door_label, y_off)

func _partition_z_with_door(x: float, z1: float, z2: float, door_center: float, door_width: float = DOOR_W, door_label: String = "", open_east: bool = true, y_off: float = 0.0) -> void:
	var left_end := door_center - door_width * 0.5
	var right_start := door_center + door_width * 0.5
	_wall_segment_z(x, z1, left_end, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true, y_off)
	_wall_segment_z(x, right_start, z2, PART_H * 0.5 + 0.02, PART_H, MAT.glass, true, y_off)
	_box("Door frame left", Vector3(x, y_off + DOOR_H * 0.5, left_end + 0.03), Vector3(0.28, DOOR_H + 0.05, 0.14), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door frame right", Vector3(x, y_off + DOOR_H * 0.5, right_start - 0.03), Vector3(0.28, DOOR_H + 0.05, 0.14), Color("#5f7368"), false, null, 0.42, 0.45)
	_box("Door header", Vector3(x, y_off + DOOR_H + 0.09, door_center), Vector3(0.26, 0.18, door_width + 0.30), Color("#574132"), false, null, 0.50, 0.1)
	var transom_h := PART_H - (DOOR_H + 0.18)
	_box("Door transom", Vector3(x, y_off + DOOR_H + 0.18 + transom_h * 0.5, door_center),
		Vector3(0.10, transom_h, door_width + 0.34), Color(0.72, 0.82, 0.78, 0.38), false, null, 0.28, 0.0, true)
	var open_amount := 0.62
	var leaf_left := _add_door_leaf(Vector3(x, y_off, left_end), -PI * 0.5, open_amount * (1.0 if open_east else -1.0), door_width * 0.5 - 0.02)
	var leaf_right := _add_door_leaf(Vector3(x, y_off, right_start), PI * 0.5, open_amount * (-1.0 if open_east else 1.0), door_width * 0.5 - 0.02)
	doors.append({
		"position": Vector3(x, y_off, door_center),
		"label": door_label,
		"open": true,
		"leaves": [
			{"node": leaf_left, "closed": -PI * 0.5, "open": -PI * 0.5 + open_amount * (1.0 if open_east else -1.0)},
			{"node": leaf_right, "closed": PI * 0.5, "open": PI * 0.5 + open_amount * (-1.0 if open_east else 1.0)},
		],
	})
	if door_label != "":
		_add_door_sign(x, door_center, false, not open_east, door_label, y_off)

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

## Plakat nama ruangan di samping/atas header pintu (micro-detail, corridor side).
## Node names keep "Door sign plate/trim" so headless registry checks remain stable.
func _add_door_sign(wall_pos: float, along_pos: float, axis_x: bool, face_south_or_east: bool, text: String, y_off: float = 0.0) -> void:
	var plate_position := Vector3(wall_pos, DOOR_H + 0.36, along_pos)
	var offset := 0.16
	if axis_x:
		plate_position.z += offset if face_south_or_east else -offset
	else:
		plate_position.x += offset if face_south_or_east else -offset
	var psize := Vector3(1.62, 0.30, 0.028) if axis_x else Vector3(0.028, 0.30, 1.62)
	var tsize := Vector3(1.52, 0.22, 0.034) if axis_x else Vector3(0.034, 0.22, 1.52)
	# Sleek black aluminum plate + subtle emissive edge (premium signage)
	_box("Door sign plate %02d" % _door_sign_index, plate_position, psize, Color("#1f2326"), false, null, 0.28, 0.55)
	_box("Door sign trim %02d" % _door_sign_index, plate_position, tsize, Color("#2a3034"), false, null, 0.24, 0.45, false, Color("#203840"))
	var eg := Vector3(1.56, 0.012, 0.02) if axis_x else Vector3(0.02, 0.012, 1.56)
	_box("Door sign glow", plate_position + Vector3(0, -0.145, 0), eg, Color("#2aa8c8"), false, null, 0.2, 0.0, false, Color("#38c8e8"))
	_door_sign_index += 1
	var label := Label3D.new()
	label.text = text.to_upper()
	label.font_size = 40
	label.outline_size = 4
	label.modulate = Color("#eaf2f6")
	label.outline_modulate = Color(0.02, 0.03, 0.04, 0.95)
	label.pixel_size = 0.0038
	label.no_depth_test = false
	if axis_x:
		label.rotation.y = 0.0 if face_south_or_east else PI
	else:
		label.rotation.y = PI * 0.5 if face_south_or_east else -PI * 0.5
	if axis_x:
		label.position = plate_position + Vector3(0, 0, 0.026 if face_south_or_east else -0.026)
	else:
		label.position = plate_position + Vector3(0.026 if face_south_or_east else -0.026, 0, 0)
	add_child(label)

func _build_site() -> void:
	# =========================================================================
	# CITY MASTER PLAN — Bangkah City
	# Grid: 4-meter module. All roads, sidewalks, and zones snap to this grid.
	# Zones: Boulevard Raya (E-W spine) | Jl. Bangkah (N-S spine)
	#        Residential (west) | Commercial (east) | HQ Corporate (center)
	# =========================================================================

	# --- Design tokens ---
	var ground := Color("#7f917d")
	var asphalt := Color("#4f5855")
	var asphalt_dark := Color("#424a46")
	var line := Color("#efe4c2")
	var curb := Color("#aeb8b1")
	var pave := Color("#c9d1c6")
	var grass := Color("#6f8b6d")

	# --- City ground plane ---
	_box("City ground", Vector3(62, -0.35, 32), Vector3(320, 0.7, 320), ground, true)

	# =========================================================================
	# BOULEVARD RAYA — main east-west spine (south edge of city)
	# 20 m wide, divided by 3 m median, 3 m sidewalks each side.
	# =========================================================================
	var blvd_z := 55.0
	var blvd_w := 20.0
	var median_w := 3.0
	var walk_w := 3.0

	# Road surface (two carriageways split by median)
	_box("Blvd carriageway N", Vector3(62, -0.06, blvd_z - median_w * 0.5 - blvd_w * 0.5 - 0.15), Vector3(320, 0.12, blvd_w), asphalt, false)
	_box("Blvd carriageway S", Vector3(62, -0.06, blvd_z + median_w * 0.5 + blvd_w * 0.5 + 0.15), Vector3(320, 0.12, blvd_w), asphalt, false)
	# Median strip
	_box("Blvd median", Vector3(62, -0.02, blvd_z), Vector3(320, 0.04, median_w), grass, false)
	# Curbs (four edges)
	_box("Blvd curb outer N", Vector3(62, 0.0, blvd_z - median_w * 0.5 - blvd_w - walk_w * 0.5 - 0.5), Vector3(320, 0.07, 1.0), curb, false)
	_box("Blvd curb inner N", Vector3(62, 0.0, blvd_z - median_w * 0.5), Vector3(320, 0.07, 1.0), curb, false)
	_box("Blvd curb inner S", Vector3(62, 0.0, blvd_z + median_w * 0.5), Vector3(320, 0.07, 1.0), curb, false)
	_box("Blvd curb outer S", Vector3(62, 0.0, blvd_z + median_w * 0.5 + blvd_w + walk_w * 0.5 + 0.5), Vector3(320, 0.07, 1.0), curb, false)
	# Center line dashes (each carriageway)
	for lx in range(-130, 140, 8):
		_box("Blvd dash N", Vector3(float(lx), 0.012, blvd_z - median_w * 0.5 - blvd_w * 0.5), Vector3(4.0, 0.01, 0.22), line, false)
		_box("Blvd dash S", Vector3(float(lx), 0.012, blvd_z + median_w * 0.5 + blvd_w * 0.5), Vector3(4.0, 0.01, 0.22), line, false)
	# Sidewalks
	_box("Blvd sidewalk N", Vector3(62, -0.02, blvd_z - median_w * 0.5 - blvd_w - walk_w), Vector3(320, 0.05, walk_w), pave, true)
	_box("Blvd sidewalk S", Vector3(62, -0.02, blvd_z + median_w * 0.5 + blvd_w), Vector3(320, 0.05, walk_w), pave, true)
	# Street trees + lamps along boulevard (every 16 m)
	for bx in range(-120, 121, 16):
		_add_tree(Vector3(float(bx), 0.0, blvd_z - median_w * 0.5 - blvd_w - walk_w - 1.6))
		_add_tree(Vector3(float(bx), 0.0, blvd_z + median_w * 0.5 + blvd_w + walk_w + 1.6))
		_add_street_lamp(Vector3(float(bx), 0.0, blvd_z - median_w * 0.5 - blvd_w - walk_w - 3.2))
		_add_street_lamp(Vector3(float(bx), 0.0, blvd_z + median_w * 0.5 + blvd_w + walk_w + 3.2))

	# =========================================================================
	# JL. BANKAH — main north-south spine (town center)
	# 12 m wide, 2.5 m sidewalks each side. Connects boulevard to north.
	# =========================================================================
	var spine_x := TOWN_ORIGIN.x + 16.0
	var spine_z_start := TOWN_ORIGIN.z + 8.0
	var spine_z_end := TOWN_ORIGIN.z + 116.0
	var spine_w := 12.0
	var spine_walk := 2.5

	_box("Jl. Bangkah", Vector3(spine_x, -0.06, (spine_z_start + spine_z_end) * 0.5), Vector3(spine_w, 0.12, spine_z_end - spine_z_start), asphalt, false)
	_box("Spine curb W", Vector3(spine_x - spine_w * 0.5 - 0.5, 0.0, (spine_z_start + spine_z_end) * 0.5), Vector3(1.0, 0.07, spine_z_end - spine_z_start), curb, false)
	_box("Spine curb E", Vector3(spine_x + spine_w * 0.5 + 0.5, 0.0, (spine_z_start + spine_z_end) * 0.5), Vector3(1.0, 0.07, spine_z_end - spine_z_start), curb, false)
	for lz in range(int(spine_z_start), int(spine_z_end), 6):
		_box("Spine dash", Vector3(spine_x, 0.012, float(lz)), Vector3(0.22, 0.01, 2.8), line, false)
	_box("Spine sidewalk W", Vector3(spine_x - spine_w * 0.5 - spine_walk, -0.02, (spine_z_start + spine_z_end) * 0.5), Vector3(spine_walk, 0.05, spine_z_end - spine_z_start), pave, true)
	_box("Spine sidewalk E", Vector3(spine_x + spine_w * 0.5, -0.02, (spine_z_start + spine_z_end) * 0.5), Vector3(spine_walk, 0.05, spine_z_end - spine_z_start), pave, true)
	# Street lamps along east sidewalk
	for lz in range(int(spine_z_start) + 8, int(spine_z_end), 16):
		_add_street_lamp(Vector3(spine_x + spine_w * 0.5 + spine_walk + 1.0, 0.0, float(lz)))

	# =========================================================================
	# RESIDENTIAL DISTRICT — west of Jl. Bangkah
	# Quiet 8 m streets on a 24 m x 24 m block grid. Houses with lawns.
	# =========================================================================
	var res_west_x := TOWN_ORIGIN.x - 60.0
	var res_east_x := spine_x - spine_w * 0.5 - spine_walk - 4.0
	var res_street_z := [24.0, 48.0, 72.0, 96.0]
	var res_street_w := 8.0

	# East-west residential streets
	for rz in res_street_z:
		var rz_abs = TOWN_ORIGIN.z + rz
		_box("Res street", Vector3((res_west_x + res_east_x) * 0.5, -0.06, rz_abs), Vector3(res_east_x - res_west_x, 0.11, res_street_w), asphalt_dark, false)
		_box("Res curb N", Vector3((res_west_x + res_east_x) * 0.5, 0.0, rz_abs - res_street_w * 0.5 - 0.5), Vector3(res_east_x - res_west_x, 0.07, 1.0), curb, false)
		_box("Res curb S", Vector3((res_west_x + res_east_x) * 0.5, 0.0, rz_abs + res_street_w * 0.5 + 0.5), Vector3(res_east_x - res_west_x, 0.07, 1.0), curb, false)
		for rx in range(int(res_west_x) + 8, int(res_east_x), 8):
			_box("Res dash", Vector3(float(rx), 0.012, rz_abs), Vector3(3.0, 0.01, 0.18), line, false)

	# North-south residential access street (connects to spine)
	var res_access_x := res_east_x - res_street_w * 0.5 - 2.0
	_box("Res access N-S", Vector3(res_access_x, -0.06, (spine_z_start + spine_z_end) * 0.5), Vector3(res_street_w, 0.11, spine_z_end - spine_z_start), asphalt_dark, false)
	_box("Res access curb W", Vector3(res_access_x - res_street_w * 0.5 - 0.5, 0.0, (spine_z_start + spine_z_end) * 0.5), Vector3(1.0, 0.07, spine_z_end - spine_z_start), curb, false)
	_box("Res access curb E", Vector3(res_access_x + res_street_w * 0.5 + 0.5, 0.0, (spine_z_start + spine_z_end) * 0.5), Vector3(1.0, 0.07, spine_z_end - spine_z_start), curb, false)
	for lz in range(int(spine_z_start), int(spine_z_end), 8):
		_box("Res access dash", Vector3(res_access_x, 0.012, float(lz)), Vector3(0.22, 0.01, 3.2), line, false)

	# House plots on a clean 24 x 24 m grid, each with lawn + walk + trees
	var house_offsets := [
		Vector2(0, 0), Vector2(24, 0), Vector2(0, 24), Vector2(24, 24),
		Vector2(0, 48), Vector2(24, 48), Vector2(0, 72), Vector2(24, 72),
		Vector2(0, 96), Vector2(24, 96), Vector2(12, 120),
	]
	for off in house_offsets:
		var hb := TOWN_ORIGIN + Vector3(off.x, 0, off.y)
		# Lawn
		_box("House lawn", Vector3(hb.x + 6.0, -0.04, hb.z + 6.0), Vector3(14.0, 0.04, 14.0), Color("#8fa58d"), false)
		# Walk from street to door
		_box("House walk", Vector3(hb.x + 6.0, -0.02, hb.z + 12.8), Vector3(2.6, 0.05, 5.2), pave, true)
		# Two street trees per lot
		_add_tree(Vector3(hb.x + 2.0, 0.0, hb.z + 2.0))
		_add_tree(Vector3(hb.x + 12.0, 0.0, hb.z + 2.0))

	# =========================================================================
	# COMMERCIAL DISTRICT — east of Jl. Bangkah (market + mall + kopdes)
	# Wide forecourt plazas, clean parking bays, connector street.
	# =========================================================================
	var mc: Vector3 = market_layout().get("center", TOWN_ORIGIN + Vector3(28, 0, 92))
	var kc: Vector3 = kopdes_layout().get("center", TOWN_ORIGIN + Vector3(46, 0, 58))
	var mbase: Vector3 = owner_mansion_layout().get("base", TOWN_ORIGIN + Vector3(44, 0, -10))

	# Market connector street (east-west, from spine to market)
	var mkt_conn_x := (spine_x + spine_w * 0.5 + spine_walk + 4.0 + mc.x) * 0.5
	_box("Market connector", Vector3(mkt_conn_x, -0.06, TOWN_ORIGIN.z + 92.0), Vector3(mc.x - spine_x - spine_w * 0.5 - spine_walk - 4.0, 0.12, 9.0), asphalt_dark, false)
	_box("Mkt curb N", Vector3(mkt_conn_x, 0.0, TOWN_ORIGIN.z + 87.5), Vector3(mc.x - spine_x - spine_w * 0.5 - spine_walk - 4.0, 0.07, 1.0), curb, false)
	_box("Mkt curb S", Vector3(mkt_conn_x, 0.0, TOWN_ORIGIN.z + 96.5), Vector3(mc.x - spine_x - spine_w * 0.5 - spine_walk - 4.0, 0.07, 1.0), curb, false)
	for lx in range(int(spine_x + spine_w * 0.5 + spine_walk + 8), int(mc.x - 6), 8):
		_box("Mkt dash", Vector3(float(lx), 0.012, TOWN_ORIGIN.z + 92.0), Vector3(3.0, 0.01, 0.18), line, false)

	# Mall forecourt plaza (clean drop-off + plaza in front of Kopdes Mall)
	_box("Mall forecourt", Vector3(kc.x, -0.02, kc.z + 16.0), Vector3(36.0, 0.05, 10.0), pave, true)
	_box("Mall forecourt border N", Vector3(kc.x, -0.01, kc.z + 11.0), Vector3(36.0, 0.04, 1.0), curb, false)
	_box("Mall forecourt border S", Vector3(kc.x, -0.01, kc.z + 21.0), Vector3(36.0, 0.04, 1.0), curb, false)
	# Mall parking lot (neat 4.2 m bays)
	_box("Mall parking lot", Vector3(kc.x, -0.035, kc.z + 28.0), Vector3(64.0, 0.07, 16.0), Color("#aeb7ae"), true)
	for px in range(-28, 29, 6):
		_box("Mall bay line", Vector3(kc.x + float(px), 0.015, kc.z + 28.0), Vector3(0.12, 0.01, 13.0), Color("#f0f1ea"), false)

	# Mansion avenue (grand west-east approach to Owner's mansion)
	_box("Mansion avenue", Vector3(mbase.x - 7.0, -0.06, mbase.z + 8.0), Vector3(16.0, 0.12, 48.0), asphalt_dark, false)
	_box("Mansion curb W", Vector3(mbase.x - 14.5, 0.0, mbase.z + 32.0), Vector3(1.0, 0.07, 48.0), curb, false)
	_box("Mansion curb E", Vector3(mbase.x + 1.5, 0.0, mbase.z + 32.0), Vector3(1.0, 0.07, 48.0), curb, false)
	for lz in range(int(mbase.z) + 16, int(mbase.z) + 44, 8):
		_box("Mansion dash", Vector3(mbase.x - 7.0, 0.012, float(lz)), Vector3(0.22, 0.01, 3.0), line, false)
	_box("Mansion walk", Vector3(mbase.x, -0.02, mbase.z + 13.5), Vector3(4.2, 0.05, 9.0), pave, true)
	# Grand trees flanking mansion avenue
	for lz in range(int(mbase.z) + 16, int(mbase.z) + 44, 10):
		_add_tree(Vector3(mbase.x - 11.0, 0.0, float(lz)))
		_add_tree(Vector3(mbase.x - 3.0, 0.0, float(lz)))

	# =========================================================================
	# HQ CORPORATE CAMPUS — center, fronting Boulevard Raya
	# Clean apron, access road, parking lot, front walk.
	# =========================================================================
	_box("HQ apron", Vector3(0, -0.09, 0), Vector3(108, 0.18, 98), Color("#adb5aa"), false)
	_box("HQ foundation", Vector3(0, -0.12, 0), Vector3(94, 0.24, 88), Color("#89958e"), true)
	# Access road from boulevard to HQ entrance
	_box("HQ access road", Vector3(24, -0.06, 48.0), Vector3(24, 0.12, 10.0), asphalt_dark, false)
	_box("HQ access curb", Vector3(24, 0.0, 43.6), Vector3(24, 0.07, 0.55), curb, false)
	_box("HQ front walk", Vector3(0, -0.02, 44.2), Vector3(20, 0.05, 14), pave, true)
	_box("HQ to parking walk", Vector3(16.0, -0.02, 48.2), Vector3(3.6, 0.05, 10.6), pave, true)
	# HQ parking lot (neat bays, employee-named)
	_box("HQ parking lot", Vector3(28.6, -0.04, 48.0), Vector3(22.0, 0.08, 12.0), Color("#5b6460"), true)
	for x in [22.0, 26.4, 30.8, 35.2]:
		_box("Parking bay side", Vector3(x, 0.012, 48.0), Vector3(0.12, 0.01, 10.0), Color("#f2efe4"), false)
		_box("Parking bay back", Vector3(x, 0.012, 52.4), Vector3(4.4, 0.01, 0.12), Color("#f2efe4"), false)
		_box("Parking bay front", Vector3(x, 0.012, 43.6), Vector3(4.4, 0.01, 0.12), Color("#f2efe4"), false)
	# Street lamps at HQ entrance
	_add_street_lamp(Vector3(-6.0, 0.0, 50.0))
	_add_street_lamp(Vector3(6.0, 0.0, 50.0))

	# =========================================================================
	# CROSSWALKS — at every major intersection (raised 1 cm to avoid z-fight)
	# =========================================================================
	var cross_zs := [blvd_z, TOWN_ORIGIN.z + 24.0, TOWN_ORIGIN.z + 48.0, TOWN_ORIGIN.z + 72.0, TOWN_ORIGIN.z + 96.0, TOWN_ORIGIN.z + 116.0]
	for zx in cross_zs:
		for sidx in range(-3, 4):
			_box("Crosswalk", Vector3(spine_x, 0.012, zx + 3.0 + float(sidx) * 0.5), Vector3(8.0, 0.01, 0.28), line, false)

	# =========================================================================
	# CITY ENTRY MONUMENT — at boulevard + Jl. Bangkah corner
	# =========================================================================
	_box("City monument base", Vector3(spine_x - 34.0, 1.3, blvd_z + 18.0), Vector3(7.0, 0.12, 3.0), Color("#6b776f"), false)
	_box("City monument", Vector3(spine_x - 34.0, 3.2, blvd_z + 18.0), Vector3(6.4, 3.0, 2.4), Color("#42584c"), false)
	_painted_text("KOTA BANGKAH", Vector3(spine_x - 34.0, 4.1, blvd_z + 18.06), 0.0, 0.008, Color("#e8fbff"), Color(0.05, 0.12, 0.14, 0.35))
	_painted_text("JL. BANKAH RAYA", Vector3(spine_x - 34.0, 3.6, blvd_z + 18.06), 0.0, 0.0034, Color("#9ad7c2"), Color(0, 0, 0, 0))

func _add_street_lamp(position: Vector3) -> void:
	# Single decorative street lamp (pole + warm head + OmniLight).
	var root := Node3D.new()
	root.name = "StreetLamp"
	root.position = position
	add_child(root)
	_box("Lamp pole", Vector3(0, 1.8, 0), Vector3(0.07, 3.6, 0.07), Color("#6b7871"), false, root, 0.55)
	_box("Lamp head", Vector3(0, 3.72, 0), Vector3(0.5, 0.12, 0.26), Color("#ded6c2"), false, root, 0.28, 0.05, false, Color("#f3e4bf"))
	var sl := OmniLight3D.new()
	sl.position = position + Vector3(-0.2, 3.55, 0)
	sl.light_color = Color("#ffe9c2")
	sl.light_energy = 0.14
	sl.omni_range = 8.5
	sl.shadow_enabled = false
	add_child(sl)

func _add_plant(position: Vector3, scale_value: float = 1.0) -> void:
	var p := position + Vector3(0, _floor_y, 0)
	_cylinder("Decorative planter", p + Vector3(0, 0.32 * scale_value, 0), 0.42 * scale_value, 0.62 * scale_value, Color("#9c8268"))
	_cylinder("Planter soil", p + Vector3(0, 0.64 * scale_value, 0), 0.35 * scale_value, 0.06, Color("#493e31"))
	for i in range(6):
		var angle := TAU * float(i) / 6.0
		_sphere("Plant foliage", p + Vector3(cos(angle) * 0.28 * scale_value, 1.05 * scale_value + float(i % 2) * 0.16, sin(angle) * 0.28 * scale_value), 0.34 * scale_value, Color("#6f9275"), Vector3(1.0, 1.25, 0.84))
	_sphere("Plant crown", p + Vector3(0, 1.36 * scale_value, 0), 0.32 * scale_value, Color("#88a886"), Vector3(1.0, 1.3, 1.0))

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
	# 3-story company building shell (L1/L2/L3). Interior room/seat/door registries
	# are rebuilt per-floor below; this builds the physical envelope + slabs.
	var total_h := FLOOR_H * 3.0 + 3.8
	_box("Office floor slab L1", Vector3(0, -0.11, 0), Vector3(84, 0.22, 80), MAT.floor, true)
	# Upper floor slabs with openings for stair (east) and lift (west) cores.
	_build_floor_slab("L2 slab", L2_Y - 0.11)
	_build_floor_slab("L3 slab", L3_Y - 0.11)
	_box("Roof slab", Vector3(0, L3_Y + FLOOR_H + 2.0, 0), Vector3(84, 0.22, 80), Color("#8f9b94"), true)
	_box("Lift headroom band", Vector3(13.8, L3_Y + FLOOR_H + 1.0, 10.7), Vector3(8.5, 2.0, 6.0), Color("#9aa6a0"), false, null, 0.7)
	# Exterior walls (full 3-story height)
	for wy in [WALL_H * 0.5, WALL_H * 0.5 + FLOOR_H, WALL_H * 0.5 + FLOOR_H * 2.0]:
		_box("North exterior wall", Vector3(0, wy, -40), Vector3(84, WALL_H, 0.34), MAT.wall, true)
		_box("West exterior wall", Vector3(-42, wy, 0), Vector3(0.34, WALL_H, 80), MAT.wall, true)
		_box("East exterior wall", Vector3(42, wy, 0), Vector3(0.34, WALL_H, 80), MAT.wall, true)
	_wall_segment_x(-42, -5.2, 40, WALL_H * 0.5, WALL_H, MAT.wall, false)
	_wall_segment_x(5.2, 42, 40, WALL_H * 0.5, WALL_H, MAT.wall, false)
	_wall_segment_x(-42, 42, 40, WALL_H * 0.5 + FLOOR_H, WALL_H, MAT.wall, false)
	_wall_segment_x(-42, 42, 40, WALL_H * 0.5 + FLOOR_H * 2.0, WALL_H, MAT.wall, false)
	# Entrance canopy upgraded in _build_exterior_facade (kept out of shell to avoid z-fighting).
		# Glazing bands per floor (north/side). South/front facade articulated in _build_exterior_facade.
	for fl: int in [0, 1, 2]:
		var fy := fl * FLOOR_H
		for x in [-34, -25, -16, -7, 2, 11, 20, 29, 38]:
			_box("North glazing", Vector3(x, fy + 2.45, -39.78), Vector3(5.6, 3.4, 0.06), MAT.glass, false, null, 0.16, 0.12, true)
			_box("North window sill", Vector3(x, fy + 0.78, -39.68), Vector3(5.8, 0.10, 0.20), Color("#9ca9a2"), false)
			_box("North glazing header", Vector3(x, fy + 4.28, -39.78), Vector3(5.6, 0.10, 0.12), Color("#7d8b84"), false)
		for z in [-32, -21, -10, 1, 12, 23, 34]:
			for x in [-41.78, 41.78]:
				_box("Side glazing", Vector3(x, fy + 2.45, z), Vector3(0.06, 3.4, 7.3), MAT.glass, false, null, 0.16, 0.12, true)
	# L1 lobby storefront kept (base envelope); L2/L3 front articulated by facade.
	for x in [-15, -10, -5, 5, 10, 15]:
		_box("Lobby storefront glass", Vector3(x, 2.0, 39.78), Vector3(4.55, 3.0, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
		_box("Storefront mullion", Vector3(x, 2.0, 39.68), Vector3(0.09, 3.15, 0.16), Color("#2a2a2a"), false, null, 0.35, 0.55)
		_box("Lobby clerestory glass", Vector3(x, 4.5, 39.78), Vector3(4.55, 1.8, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
	_box("Entry left door", Vector3(-2.25, 1.7, 39.5), Vector3(2.0, 3.25, 0.11), Color(0.44, 0.65, 0.65, 0.34), false, null, 0.12, 0.1, true)
	_box("Entry right door", Vector3(2.25, 1.7, 39.5), Vector3(2.0, 3.25, 0.11), Color(0.44, 0.65, 0.65, 0.34), false, null, 0.12, 0.1, true)
	_box("Entry transom glass", Vector3(0, 4.5, 39.78), Vector3(4.4, 1.8, 0.07), MAT.glass, false, null, 0.12, 0.1, true)
	# Vertical black matte mullion grid over L1 storefront (visual articulation).
	for mx in [-17.5, -12.5, -7.5, -2.5, 2.5, 7.5, 12.5, 17.5]:
		if absf(mx) < 3.0:
			continue
		_box("L1 facade mullion", Vector3(mx, 2.75, 39.86), Vector3(0.10, 5.1, 0.10), Color("#1f2224"), false, null, 0.32, 0.55)
	# Structural columns through 3 stories
	for x in [-39, -20, 0, 20, 39]:
		for z in [-37, -18, 4, 25, 37]:
			_box("Structural column", Vector3(x, total_h * 0.5 - 0.2, z), Vector3(0.42, total_h, 0.42), Color("#c5cec7"), true)
	var top := L3_Y + FLOOR_H + 2.02
	_box("North roof edge", Vector3(0, top, -40), Vector3(84, 0.30, 0.52), Color("#718179"), false)
	_box("West roof edge", Vector3(-42, top, 0), Vector3(0.52, 0.30, 80), Color("#718179"), false)
	_box("East roof edge", Vector3(42, top, 0), Vector3(0.52, 0.30, 80), Color("#718179"), false)
	_box("South roof edge", Vector3(0, top, 40), Vector3(84, 0.30, 0.52), Color("#718179"), false)
	# extend envelope to raised roof (lift headroom)
	var ext_y := L3_Y + FLOOR_H + 1.0
	_box("Upper ext N", Vector3(0, ext_y, -40), Vector3(84, 2.0, 0.34), MAT.wall, false)
	_box("Upper ext W", Vector3(-42, ext_y, 0), Vector3(0.34, 2.0, 80), MAT.wall, false)
	_box("Upper ext E", Vector3(42, ext_y, 0), Vector3(0.34, 2.0, 80), MAT.wall, false)
	_box("Upper ext S", Vector3(0, ext_y, 40), Vector3(84, 2.0, 0.34), MAT.wall, false)
	# Old low front sign removed (replaced by 3F articulated facade + canopy + L3 emissive brand).
	# Floor markers on exterior
	for i in range(3):
		_painted_text("L%d" % (i+1), Vector3(38.5, i*FLOOR_H + 4.8, 40.2), 0.0, 0.008, Color("#f0dfb0"), Color(0,0,0,0))

func _build_floor_slab(label_s: String, y: float) -> void:
	# Core opening: 2 tangga (naik/turun) + lift tinggi, berdampingan (x ~ 9.0..18.2, z ~ 5.8..15.8)
	_box(label_s + " N", Vector3(0, y, -17.1), Vector3(84, 0.22, 45.8), MAT.floor, true)
	_box(label_s + " S", Vector3(0, y, 27.9), Vector3(84, 0.22, 24.2), MAT.floor, true)
	_box(label_s + " W", Vector3(-16.5, y, 10.8), Vector3(51.0, 0.22, 10.0), MAT.floor, true)
	_box(label_s + " E", Vector3(30.1, y, 10.8), Vector3(23.8, 0.22, 10.0), MAT.floor, true)

func _build_exterior_facade() -> void:
	# 3-floor HQ facade: articulate each level (L1 glass/warm, L2 ribbon+louvers,
	# L3 dark slate + panoramic/cantilever balcony) without altering interior/
	# registries. Visual-only overlay in front of shell (z > 40).
	var base := Color("#e6e0d4")      # off-white / soft warm
	var slate := Color("#2c302e")     # dark charcoal panels
	var louver := Color("#232628")
	var mullion := Color("#1f2224")
	var wood := Color("#6b4a2e")
	var brass := Color("#c7a85a")
	var accent := Color("#6aa8a0")    # tech cyan/teal accent
	var smoked := Color(0.10, 0.13, 0.16, 0.58)
	var clear := Color(0.58, 0.76, 0.82, 0.22)
	var fz := 40.22 # front face overlay
	# Base plinth & floor bands (readable 3-floor articulation)
	_box("HQ plinth", Vector3(0, 0.34, 0), Vector3(85.4, 0.52, 81.4), Color("#8e9a93"), true, null, 0.62)
	for by in [FLOOR_H - 0.06, FLOOR_H * 2.0 - 0.06, FLOOR_H * 3.0 - 0.06]:
		_box("Floor band", Vector3(0, by, fz + 0.02), Vector3(84.6, 0.24, 0.16), slate, false, null, 0.45, 0.12)
		_box("Band brass inlay", Vector3(0, by + 0.14, fz + 0.11), Vector3(84.0, 0.03, 0.03), brass, false, null, 0.25, 0.55)
	# Off-white base field behind accents (non-colliding overlay)
	_box("Facade base L2", Vector3(0, L2_Y + 2.8, fz), Vector3(84.2, 5.4, 0.10), base, false, null, 0.78)
	_box("Facade base L3", Vector3(0, L3_Y + 2.8, fz), Vector3(84.2, 5.4, 0.10), slate, false, null, 0.62)

	# --- L1: clear storefront feel + black matte mullion grid + warm wood entrance ---
	_box("L1 transom strip", Vector3(0, 5.15, fz + 0.06), Vector3(84.2, 0.55, 0.06), slate, false, null, 0.5)
	for x in [-36.0, -28.0, -20.0, 20.0, 28.0, 36.0]:
		_box("L1 side glass", Vector3(x, 2.25, fz + 0.08), Vector3(6.8, 4.6, 0.06), clear, false, null, 0.08, 0.08, true)
	# vertical mullion grid (~2m rhythm) across L1, skip entry
	for mx in range(-40, 41, 2):
		var mxf := float(mx)
		if absf(mxf) < 5.5:
			continue
		_box("L1 mullion", Vector3(mxf, 2.75, fz + 0.14), Vector3(0.09, 5.2, 0.09), mullion, false, null, 0.3, 0.55)
	# fluted warm-wood entrance frame (welcoming) + emissive trim
	for sx in [-6.2, 6.2]:
		_box("Entrance wood frame", Vector3(sx, 2.65, fz + 0.12), Vector3(1.4, 5.1, 0.22), wood, false, null, 0.5)
		for fx in [-0.45, -0.15, 0.15, 0.45]:
			_box("Wood flute", Vector3(sx + fx, 2.65, fz + 0.25), Vector3(0.08, 4.9, 0.05), wood.darkened(0.12), false, null, 0.55)
	_box("Entrance header wood", Vector3(0, 5.05, fz + 0.12), Vector3(13.8, 0.9, 0.22), wood, false, null, 0.5)
	_box("Entrance cyan line", Vector3(0, 4.58, fz + 0.26), Vector3(13.2, 0.05, 0.03), accent, false, null, 0.2, 0.0, false, accent)

	# --- L2: ribbon windows + dark slate piers + black sunshade louvers ---
	var l2wy := L2_Y + 2.55
	# slate accent piers between window bays
	for px in [-38.0, -30.0, -22.0, -14.0, 14.0, 22.0, 30.0, 38.0]:
		_box("L2 slate pier", Vector3(px, L2_Y + 2.8, fz + 0.08), Vector3(2.6, 5.1, 0.12), slate, false, null, 0.58)
	# long ribbon windows (smoked glass) in bays
	for bay in [[-34.0, 5.4], [-26.0, 5.4], [-18.0, 5.4], [18.0, 5.4], [26.0, 5.4], [34.0, 5.4]]:
		var bx := float(bay[0]); var bw := float(bay[1])
		_box("L2 ribbon glass", Vector3(bx, l2wy, fz + 0.14), Vector3(bw, 2.25, 0.06), smoked, false, null, 0.08, 0.06, true)
		# sunshade louver blades projecting out (texture/depth)
		for ly in [-0.85, -0.35, 0.15, 0.65]:
			_box("L2 louver", Vector3(bx, l2wy + ly, fz + 0.42), Vector3(bw + 0.2, 0.06, 0.55), louver, false, null, 0.55, 0.15)
		_box("L2 louver frame", Vector3(bx, l2wy, fz + 0.22), Vector3(bw + 0.3, 2.4, 0.08), mullion, false, null, 0.35, 0.45)

	# --- L3: dark slate + panoramic center glass + cantilever balcony (breaks box) ---
	_box("L3 slate face", Vector3(0, L3_Y + 2.8, fz + 0.04), Vector3(84.2, 5.2, 0.08), slate, false, null, 0.6)
	# panoramic glass band (center/owner side) + corner glazing
	_box("L3 panoramic glass", Vector3(-18.0, L3_Y + 2.75, fz + 0.14), Vector3(30.0, 3.2, 0.06), smoked, false, null, 0.06, 0.05, true)
	_box("L3 panoramic mullion", Vector3(-18.0, L3_Y + 2.75, fz + 0.18), Vector3(0.10, 3.2, 0.06), mullion, false, null, 0.3, 0.55)
	_box("L3 corner glass L", Vector3(-38.5, L3_Y + 2.75, fz + 0.14), Vector3(5.5, 3.0, 0.06), clear, false, null, 0.08, 0.06, true)
	_box("L3 corner glass R", Vector3(38.5, L3_Y + 2.75, fz + 0.14), Vector3(5.5, 3.0, 0.06), clear, false, null, 0.08, 0.06, true)
	# fluted wood support accent near L3
	_box("L3 wood accent", Vector3(-2.0, L3_Y + 2.8, fz + 0.10), Vector3(1.6, 5.0, 0.16), wood, false, null, 0.5)
	# Cantilevered Owner balcony projecting outward (visual, breaks monolith)
	var bcx := -29.5
	_box("Owner ext balcony deck", Vector3(bcx, L3_Y + 0.10, 41.85), Vector3(6.2, 0.16, 3.3), wood, true, null, 0.55)
	_box("Owner ext balcony soffit", Vector3(bcx, L3_Y - 0.02, 41.85), Vector3(6.2, 0.08, 3.3), slate, false, null, 0.5)
	_box("Owner ext rail glass front", Vector3(bcx, L3_Y + 1.05, 43.45), Vector3(6.0, 1.1, 0.06), Color(0.78,0.88,0.94,0.18), false, null, 0.06, 0.02, true)
	_box("Owner ext rail glass L", Vector3(bcx - 3.0, L3_Y + 1.05, 41.85), Vector3(0.06, 1.1, 3.2), Color(0.78,0.88,0.94,0.18), false, null, 0.06, 0.02, true)
	_box("Owner ext rail glass R", Vector3(bcx + 3.0, L3_Y + 1.05, 41.85), Vector3(0.06, 1.1, 3.2), Color(0.78,0.88,0.94,0.18), false, null, 0.06, 0.02, true)
	_box("Owner ext rail cap", Vector3(bcx, L3_Y + 1.62, 43.45), Vector3(6.1, 0.05, 0.10), mullion, false, null, 0.3, 0.45)
	_painted_text("BALKON EKSEKUTIF", Vector3(bcx, L3_Y + 1.15, 43.52), 0.0, 0.0026, Color("#eef4f0"), Color(0,0,0,0))

	# --- Thin-edge steel canopy + wood soffit + warm downlights ---
	_box("Drive canopy", Vector3(0, 4.55, 44.1), Vector3(23.0, 0.16, 7.8), slate, true, null, 0.4, 0.22)
	_box("Canopy wood soffit", Vector3(0, 4.44, 44.1), Vector3(22.2, 0.10, 7.1), wood.darkened(0.05), false, null, 0.55)
	_box("Canopy fascia front", Vector3(0, 4.48, 48.0), Vector3(23.0, 0.22, 0.10), mullion, false, null, 0.35, 0.3)
	_box("Canopy fascia accent", Vector3(0, 4.34, 48.06), Vector3(22.6, 0.05, 0.04), accent, false, null, 0.2, 0.0, false, accent)
	for x in [-10.6, -3.6, 3.6, 10.6]:
		_box("Canopy post", Vector3(x, 2.25, 47.2), Vector3(0.34, 4.5, 0.34), mullion, true, null, 0.4, 0.35)
	# warm downlights under canopy
	for dx in [-8.0, -4.0, 0.0, 4.0, 8.0]:
		_box("Canopy downlight", Vector3(dx, 4.36, 44.4), Vector3(0.28, 0.03, 0.28), Color("#f7e7c2"), false, null, 0.2, 0.0, false, Color("#ffe3b0"))
		var dl := OmniLight3D.new()
		dl.position = Vector3(dx, 4.25, 45.2)
		dl.light_color = Color("#ffdca0"); dl.light_energy = 0.22; dl.omni_range = 7.5
		dl.shadow_enabled = false
		add_child(dl)

	# --- 3D emissive branding (day/night readable) ---
	_box("L3 brand backer", Vector3(18.0, L3_Y + 3.9, fz + 0.10), Vector3(20.0, 1.35, 0.16), Color("#1f2a27"), false, null, 0.3, 0.4)
	_painted_text("BANGKAH HEADQUARTERS", Vector3(18.0, L3_Y + 3.95, fz + 0.22), 0.0, 0.0105, Color("#e8fbff"), Color(0.05,0.12,0.14,0.35))
	_box("Brand emissive bar", Vector3(18.0, L3_Y + 3.35, fz + 0.18), Vector3(18.5, 0.07, 0.05), accent, false, null, 0.2, 0.0, false, accent)
	# keep existing L1 sign feel minimal (replaced by canopy/wood header); add subtle HQ marker
	# Exterior Digital Totem near drop-off (welcome screen)
	_box("Ext totem base", Vector3(-9.5, 0.30, 45.2), Vector3(0.65, 0.6, 0.45), Color("#1f2326"), false, null, 0.35, 0.4)
	_box("Ext totem frame", Vector3(-9.5, 1.45, 45.2), Vector3(0.80, 1.9, 0.12), Color("#14181b"), false, null, 0.25, 0.45)
	_box("Ext totem screen", Vector3(-9.5, 1.45, 45.27), Vector3(0.68, 1.68, 0.03), Color("#0b1820"), false, null, 0.12, 0.0, false, Color("#2aa8c8"))
	_painted_text("WELCOME", Vector3(-9.5, 1.85, 45.30), 0.0, 0.0034, Color("#e6fbff"), Color(0,0,0,0))
	_painted_text("BANGKAH HQ", Vector3(-9.5, 1.45, 45.30), 0.0, 0.0026, Color("#9ad7c2"), Color(0,0,0,0))

	# Facade up-lighting (dramatic night)
	for lx in [-30.0, -15.0, 0.0, 15.0, 30.0]:
		_box("Uplight housing", Vector3(lx, 0.12, 40.55), Vector3(0.35, 0.08, 0.18), Color("#2a2f2d"), false)
		var ul := SpotLight3D.new()
		ul.position = Vector3(lx, 0.18, 41.0)
		ul.rotation_degrees = Vector3(-105, 0, 0)
		ul.light_color = Color("#dfeee8"); ul.light_energy = 0.0; ul.spot_range = 22.0; ul.spot_angle = 32.0
		ul.shadow_enabled = false
		add_child(ul)
	# Corner massing stays light
	for c in [Vector3(-41.6, 2.9, 39.6), Vector3(41.6, 2.9, 39.6), Vector3(-41.6, 2.9, -39.6), Vector3(41.6, 2.9, -39.6)]:
		_box("Corner pier", c, Vector3(1.1, 5.5, 1.1), Color("#d3ccbf"), false, null, 0.74)
	# Roadside sign retained
	_box("Road sign post L", Vector3(-18.5, 1.45, 49.5), Vector3(0.16, 2.9, 0.16), Color("#6a776f"), false, null, 0.5)
	_box("Road sign post R", Vector3(-15.5, 1.45, 49.5), Vector3(0.16, 2.9, 0.16), Color("#6a776f"), false, null, 0.5)
	_box("Road sign board", Vector3(-17.0, 2.55, 49.5), Vector3(3.6, 1.4, 0.14), Color("#f2f1ea"), false, null, 0.45)
	_box("Road sign header", Vector3(-17.0, 3.05, 49.56), Vector3(3.6, 0.38, 0.06), accent, false, null, 0.35)
	_painted_text("BANGKAH HQ", Vector3(-17.0, 2.65, 49.61), 0.0, 0.0038, Color("#2f4339"), Color(0,0,0,0))
	_painted_text("← PARKIR  |  MASUK →", Vector3(-17.0, 2.25, 49.61), 0.0, 0.0024, Color("#3a4a42"), Color(0,0,0,0))
	# Rooftop units raised to true 3F roof level
	var rfy := L3_Y + FLOOR_H + 0.85
	_box("Roof unit A", Vector3(-18.0, rfy, -20.0), Vector3(10.0, 1.2, 6.0), Color("#8a9790"), false, null, 0.7)
	_box("Roof unit B", Vector3(22.0, rfy - 0.1, 12.0), Vector3(8.0, 1.0, 9.0), Color("#849188"), false, null, 0.7)
	_box("Stair bulkhead", Vector3(34.0, rfy + 0.25, -30.0), Vector3(5.5, 1.7, 6.5), Color("#c9d0c6"), false, null, 0.75)

func _build_room_partitions() -> void:
	# 3-floor HQ: L3 Owner, L2 core employees, L1 public/services. SAME 20 doors, same order/count.
	# L3 (Owner)
	_partition_z_with_door(-19.5, -39.8, -20.0, -29.5, DOOR_W, "RUANG OWNER", false, L3_Y) #1
	# L2 (core employees)
	_partition_z_with_door(-2.0, -39.8, -20.0, -29.5, DOOR_W, "SEKRETARIAT", false, L2_Y) #2
	_partition_z_with_door(18.5, -39.8, -20.0, -29.5, DOOR_W, "ARSITEKTUR SISTEM", true, L2_Y) #3
	# L3
	_partition_x_with_door(-39.8, -19.8, -20.0, -29.5, DOOR_W, "RUANG OWNER", true, L3_Y) #4
	# L2
	_partition_x_with_door(-19.2, -2.2, -20.0, -10.8, DOOR_W, "SEKRETARIAT", true, L2_Y) #5
	_partition_x_with_door(-1.8, 18.2, -20.0, 8.0, DOOR_W, "MANAJEMEN INTI", true, L2_Y) #6
	_partition_x_with_door(18.8, 39.8, -20.0, 29.0, DOOR_W, "ARSITEKTUR SISTEM", true, L2_Y) #7
	_partition_z_with_door(-19.5, -19.8, 4.0, -7.0, DOOR_W, "FRONTEND & DESAIN", false, L2_Y) #8
	_partition_z_with_door(6.5, -19.8, 4.0, -7.0, DOOR_W, "BACKEND ENGINEERING", true, L2_Y) #9
	# L1
	_partition_z_with_door(18.5, -19.8, 4.0, -7.0, DOOR_W, "LAB API & INFRA", true, L1_Y) #10
	_partition_x_with_door(-39.8, -19.8, 4.0, -29.5, DOOR_W, "RUANG RAPAT / BOARDROOM", false, L1_Y) #11
	# L2
	_partition_x_with_door(-19.2, 6.2, 4.0, -6.5, DOOR_W, "QA & TEST LAB", true, L2_Y) #12
	_partition_x_with_door(6.8, 18.2, 4.0, 13.0, DOOR_W, "BACKEND ENGINEERING", true, L2_Y) #13
	# L1
	_partition_x_with_door(18.8, 39.8, 4.0, 29.0, DOOR_W, "LAB API & INFRA", true, L1_Y) #14
	_partition_z_with_door(-19.5, 4.0, 25.0, 14.5, DOOR_W, "RUANG RAPAT / BOARDROOM", false, L1_Y) #15
	_partition_z_with_door(18.5, 4.0, 25.0, 14.5, DOOR_W, "LAB API & INFRA", true, L1_Y) #16
	_partition_x_with_door(-39.8, -19.8, 25.0, -29.5, DOOR_W, "ARSIP & CETAK", false, L1_Y) #17
	_partition_x_with_door(18.8, 39.8, 25.0, 29.0, DOOR_W, "PANTRY & LOUNGE", false, L1_Y) #18
	# L3 (Owner private)
	_partition_z_with_door(-0.5, 25.0, 39.8, 32.5, DOOR_W, "LOUNGE PRIBADI OWNER", true, L3_Y) #19
	_partition_x_with_door(-19.8, -0.5, 25.0, -12.5, 3.1, "SUITE OWNER", false, L3_Y) #20
	for x in [-29, -11, 8, 29]:
		_box("Glass privacy band", Vector3(x, L2_Y + 0.62, -20.0), Vector3(2.2, 0.36, 0.19), Color(0.72, 0.78, 0.73, 0.56), false, null, 0.28, 0.0, true)

	

func _build_room_floors() -> void:
	# 3-floor finishes: L1 public/services, L2 core employees, L3 Owner.
	var carpet_tex = _create_noise_texture(128, Color("#9ca99a"), 0.05)
	var carpet_mat = StandardMaterial3D.new()
	carpet_mat.albedo_texture = carpet_tex; carpet_mat.roughness = 0.94; carpet_mat.metallic = 0.0; carpet_mat.uv1_scale = Vector3(4.0, 4.0, 1.0)
	_material_cache["carpet"] = carpet_mat
	var stone_tex = _create_grid_texture(128, Color("#c8c4b8"), Color("#d3d2c8"), 32)
	var stone_mat = StandardMaterial3D.new()
	stone_mat.albedo_texture = stone_tex; stone_mat.roughness = 0.35; stone_mat.metallic = 0.05; stone_mat.uv1_scale = Vector3(6.0, 6.0, 1.0)
	_material_cache["stone"] = stone_mat
	var tile_tex = _create_grid_texture(128, Color("#b8b4a8"), Color("#c6c8bf"), 32)
	var tile_mat = StandardMaterial3D.new()
	tile_mat.albedo_texture = tile_tex; tile_mat.roughness = 0.28; tile_mat.metallic = 0.08; tile_mat.uv1_scale = Vector3(5.0, 5.0, 1.0)
	_material_cache["tile"] = tile_mat
	var carpet_material: StandardMaterial3D = _material_cache["carpet"]
	var stone_material: StandardMaterial3D = _material_cache["stone"]
	var tile_material: StandardMaterial3D = _material_cache["tile"]
	# L3 Owner (Design Bible): walnut herringbone (work) + Black Marquina feel (command) + warm lounge
	_box("Owner marquina zone L3", Vector3(-29.5, L3_Y + 0.018, -34.8), Vector3(16.5, 0.035, 6.8), Color("#1a1d20"), false, null, 0.12, 0.04)
	_box("Owner walnut herringbone L3", Vector3(-29.5, L3_Y + 0.018, -27.2), Vector3(16.5, 0.035, 10.2), Color("#8B5A2B"), false, null, 0.58, 0.02)
	_box("Owner lounge floor L3", Vector3(-10.0, L3_Y + 0.018, 32.0), Vector3(18.7, 0.035, 14.0), Color("#8B5A2B"), false, null, 0.58, 0.02)
	# L2 core employees (darker carpet tile for focus/sound)
	for d in [["Secretary carpet L2",Vector3(-10.8,L2_Y+0.018,-29.7),Vector3(16.5,0.035,17.8),Color("#6f7872")],
		["Manager carpet L2",Vector3(8.0,L2_Y+0.018,-29.7),Vector3(19.8,0.035,17.8),Color("#68746d")],
		["Architect carpet L2",Vector3(29.0,L2_Y+0.018,-29.7),Vector3(20.4,0.035,17.8),Color("#66727a")],
		["Frontend carpet L2",Vector3(-29.5,L2_Y+0.018,-7.8),Vector3(18.0,0.035,21.0),Color("#6e6862")],
		["QA carpet L2",Vector3(-6.5,L2_Y+0.018,-7.8),Vector3(25.0,0.035,21.0),Color("#67756b")],
		["Backend carpet L2",Vector3(24.0,L2_Y+0.018,-7.8),Vector3(30.0,0.035,21.0),Color("#656f6a")]]:
		_box(d[0],d[1],d[2],d[3],false,null,0.94,0.0,false,Color.BLACK,carpet_material)
	# L1 public/services (polished lobby stone/terrazzo, SSR-friendly) — Design Bible
	_box("Meeting carpet L1", Vector3(-29.5, L1_Y + 0.018, 14.5), Vector3(18.0, 0.035, 20.0), Color("#7a7582"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Lobby stone floor L1", Vector3(-0.4, L1_Y + 0.018, 14.5), Vector3(38.0, 0.035, 20.0), Color("#e6e2d8"), false, null, 0.14, 0.03, false, Color.BLACK, stone_material)
	_box("API lab floor L1", Vector3(29.0, L1_Y + 0.018, 14.5), Vector3(20.0, 0.035, 20.0), Color("#8a9698"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Archive floor L1", Vector3(-29.5, L1_Y + 0.018, 32.0), Vector3(18.0, 0.035, 14.0), Color("#a89c8e"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Staff lounge floor L1", Vector3(9.0, L1_Y + 0.018, 32.0), Vector3(18.5, 0.035, 14.0), Color("#a0ada0"), false, null, 0.92, 0.0, false, Color.BLACK, carpet_material)
	_box("Pantry tile floor L1", Vector3(30.0, L1_Y + 0.018, 32.0), Vector3(23.5, 0.035, 14.0), Color("#d4d2c8"), false, null, 0.22, 0.06, false, Color.BLACK, tile_material)
	var _fys: Array[float] = [L1_Y, L2_Y, L3_Y]
	for fy: float in _fys:
		for z in [-19.75, 4.2, 25.2]:
			_box("Floor transition strip", Vector3(0, fy + 0.058, z), Vector3(82, 0.045, 0.22), Color("#7e8b81"), false, null, 0.5, 0.18)

func _build_ceiling_and_lighting() -> void:
	# Per-floor ceilings/lighting (3 floors) + perimeter shadow gap/cove (tali air).
	var _fys: Array[float] = [L1_Y, L2_Y, L3_Y]
	for fy: float in _fys:
		for z in [-37.5, -18.5, 4.0, 25.0, 37.5]:
			_box("Ceiling cross beam", Vector3(0, fy + 5.22, z), Vector3(82, 0.18, 0.32), Color("#87948d"), false, null, 0.72, 0.12)
		for x in [-40, -19.5, -2.0, 18.5, 40]:
			_box("Ceiling spine", Vector3(x, fy + 5.22, 0), Vector3(0.28, 0.18, 78), Color("#87948d"), false, null, 0.72, 0.12)
		# drop-ceiling perimeter shadow gap (keliling)
		for zg in [-39.6, 39.6]:
			_box("Ceiling shadow gap", Vector3(0, fy + 5.32, zg), Vector3(83.0, 0.035, 0.06), Color("#1a1f1d"), false, null, 0.9)
			_box("Cove light", Vector3(0, fy + 5.28, zg + (-0.08 if zg > 0 else 0.08)), Vector3(78.0, 0.02, 0.05), Color("#f2dcb0"), false, null, 0.2, 0.0, false, Color("#ffe0a8"))
		for xg in [-41.6, 41.6]:
			_box("Ceiling shadow gap S", Vector3(xg, fy + 5.32, 0), Vector3(0.06, 0.035, 79.0), Color("#1a1f1d"), false, null, 0.9)
		for tile_x in range(-38, 39, 4):
			for tile_z in range(-37, 38, 5):
				_box("Acoustic ceiling panel", Vector3(float(tile_x) + 2.0, fy + CEIL_Y, float(tile_z) + 2.5), Vector3(3.70, 0.075, 4.68), Color("#e2e5df"), false, null, 0.92)
		for pt in [Vector3(-34,5.39,-27), Vector3(-14,5.39,-27), Vector3(8,5.39,-27), Vector3(30,5.39,-27), Vector3(-33,5.39,-4), Vector3(5,5.39,-4), Vector3(31,5.39,16), Vector3(8,5.39,34)]:
			_box("HVAC ceiling grille", Vector3(pt.x, fy + pt.y, pt.z), Vector3(0.95, 0.018, 0.42), Color("#87918c"), false, null, 0.62, 0.22)
		var light_points := [Vector3(-29,0,-29), Vector3(-10,0,-29), Vector3(8,0,-29), Vector3(29,0,-29), Vector3(-29,0,-7), Vector3(-6,0,-7), Vector3(24,0,-7), Vector3(-29,0,15), Vector3(-1,0,15), Vector3(29,0,15), Vector3(8,0,33)]
		for i in range(light_points.size()):
			var lp: Vector3 = light_points[i]
			_box("Linear ceiling light", Vector3(lp.x, fy + CEIL_Y - 0.30, lp.z), Vector3(4.6, 0.12, 0.55), Color("#f4f0df"), false, null, 0.22, 0.0, false, Color("#f5e8d0"))
			var light := OmniLight3D.new()
			light.position = Vector3(lp.x, fy + 4.72, lp.z)
			light.light_color = Color("#fff0d8"); light.light_energy = 0.38; light.omni_range = 10.5
			light.shadow_enabled = (i % 3 == 0 and fy == L1_Y)
			add_child(light)
	# Lobby ring LED pendants only on L1 (grand)
	for pendant_z in [15.0, 24.0, 31.5]:
		for x in [-7.0, 0.0, 7.0]:
			_cylinder("Pendant stem", Vector3(x, L1_Y + 4.14, pendant_z), 0.035, 2.45, Color("#596b63"))
			_cylinder("Pendant shade", Vector3(x, L1_Y + 2.90, pendant_z), 0.46, 0.18, Color("#d5c49e"), null, false, 0.2)
			_box("Pendant glow", Vector3(x, L1_Y + 2.84, pendant_z), Vector3(0.38, 0.06, 0.38), Color("#f5e0b8"), false, null, 0.22, 0.0, false, Color("#f8ecca"))
			var pendant_light := OmniLight3D.new()
			pendant_light.position = Vector3(x, L1_Y + 2.76, pendant_z)
			pendant_light.light_color = Color("#ffe8c8"); pendant_light.light_energy = 0.35; pendant_light.omni_range = 5.5
			add_child(pendant_light)

func _add_workstation(position: Vector3, title: String, wood: Color = Color("#9c8062"), dual_monitor: bool = true, rotation_y: float = 0.0) -> void:
	var p := position + Vector3(0, _floor_y, 0)
	var root := Node3D.new()
	root.position = p
	root.rotation.y = rotation_y
	add_child(root)
	# Desk top, apron and four metal legs.
	_box("Desk top", Vector3(0, 0.83, 0), Vector3(2.8, 0.16, 1.42), wood, true, root, 0.34)
	_box("Desk front apron", Vector3(0, 0.63, -0.56), Vector3(2.42, 0.25, 0.10), Color("#755d49"), false, root)
	for x in [-1.22, 1.22]:
		for z in [-0.55, 0.55]:
			_box("Desk metal leg", Vector3(x, 0.39, z), Vector3(0.10, 0.76, 0.10), Color("#58635e"), false, root, 0.3, 0.62)
	# Cable tray (under-desk, tidy core-team look) — visual only
	_box("Cable tray", Vector3(0, 0.52, -0.18), Vector3(2.15, 0.06, 0.22), Color("#2C302E"), false, root, 0.45, 0.25)
	# Drawer unit.
	_box("Desk drawer cabinet", Vector3(-1.02, 0.42, -0.30), Vector3(0.48, 0.78, 0.92), Color("#8b735c"), true, root)
	for y in [0.24, 0.47, 0.70]:
		_box("Drawer face", Vector3(-1.02, y, 0.18), Vector3(0.40, 0.17, 0.035), Color("#b89b79"), false, root)
		_box("Drawer handle", Vector3(-1.02, y, 0.145), Vector3(0.18, 0.035, 0.035), Color("#d0b783"), false, root, 0.25, 0.65)
	# Monitor arm and bezel-less displays.
	_cylinder("Monitor stand", Vector3(0, 1.01, -0.43), 0.045, 0.30, Color("#65716c"), root, false, 0.5)
	_box("Monitor arm bar", Vector3(0, 1.18, -0.44), Vector3(1.25, 0.04, 0.05), Color("#2C302E"), false, root, 0.35, 0.35)
	var monitor_positions := [Vector3(-0.52, 1.43, -0.44), Vector3(0.52, 1.43, -0.44)] if dual_monitor else [Vector3(0, 1.43, -0.44)]
	for monitor_pos in monitor_positions:
		_box("Monitor shell", monitor_pos, Vector3(0.92, 0.60, 0.035), Color("#1a1f22"), false, root, 0.3, 0.2)
		_box("Monitor display", monitor_pos + Vector3(0, 0, 0.022), Vector3(0.88, 0.56, 0.012), Color("#29444a"), false, root, 0.18, 0.06, false, Color("#315e55"))
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
	_box("Lamp glow", Vector3(-1.03, 1.36, -0.42), Vector3(0.28, 0.04, 0.28), Color("#f5e8c8"), false, root, 0.22, 0.0, false, Color("#f8edcc"))
	var desk_lamp := OmniLight3D.new()
	desk_lamp.position = Vector3(-1.03, 1.30, -0.42)
	desk_lamp.light_color = Color("#ffe8b8")
	desk_lamp.light_energy = 0.25
	desk_lamp.omni_range = 3.0
	desk_lamp.shadow_enabled = false
	root.add_child(desk_lamp)
	# Ergonomic chair and floor mat. Chair faces the monitor (-Z). (SEAT REGISTRY PRESERVED)
	var chair_position := p + root.transform.basis * Vector3(0, 0, 1.55)
	_add_office_chair(chair_position, Color("#52675f"), rotation_y, title.split("  /  ")[0] + " · Chair")
	_box("Desk floor mat", Vector3(0, 0.145, 1.45), Vector3(2.1, 0.025, 1.95), Color("#737f78"), false, root)
	# Workstation label only visible when player is close — keeps the office clean.
	var ws_label: Label3D = _label(title, Vector3(0, 2.35, -0.04), 0.0055, Color("#f3f1e8"), root)
	ws_label.set("visibility_range_end", 6.0)
	ws_label.set("visibility_range_fade_mode", 1) # VISIBILITY_RANGE_FADE_SELF

func _add_office_chair(position: Vector3, color: Color = Color("#52675f"), facing: float = 0.0, seat_label: String = "Kursi Kantor") -> void:
	# Kursi kantor swivel: SEMUA kursi punya dudukan/sandaran penuh dan teregistrasi
	# sebagai titik duduk bebas. Pivot "ChairSwivel" berputar mengikuti pemain.
	var p := position + Vector3(0, _floor_y, 0)
	var root := Node3D.new()
	root.name = "OfficeChair_%02d" % _office_chair_index
	_office_chair_index += 1
	root.position = p
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
	seats.append({"position": Vector3(p.x, p.y, p.z), "yaw": facing, "kind": "office", "pivot": swivel, "label": seat_label})

func _add_shelf(position: Vector3, width: float, height: float, depth: float, label_text: String, y_off: float = 0.0) -> void:
	var root := Node3D.new()
	root.position = position + Vector3(0, y_off + _floor_y, 0)
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
	# L1 Zone A (Public Impression): feature wall, floating reception desk, waiting lounge.
	var slate := Color("#2c302e"); var oak := Color("#8a6a46"); var cyan := Color("#44d8e8")
	_box("Reception brand wall", Vector3(0, 2.65, 17.4), Vector3(22.0, 4.8, 0.30), slate, true, null, 0.55)
	# fluted vertical oak/metal accent bands
	for x in range(-10, 11):
		var col: Color = oak.darkened(0.08) if absi(x) % 2 == 0 else slate.lightened(0.06)
		_box("Brand wall slat", Vector3(float(x) * 1.05, 2.65, 17.58), Vector3(0.06, 4.55, 0.05), col, false, null, 0.5)
	# Backlit 3D logo BANGKAH (cyan glow)
	_box("Backlit logo panel", Vector3(0, 3.22, 17.62), Vector3(8.4, 1.15, 0.06), Color("#14181b"), false, null, 0.25, 0.5)
	_box("Logo glow bar", Vector3(0, 2.72, 17.66), Vector3(7.8, 0.05, 0.04), cyan, false, null, 0.2, 0.0, false, cyan)
	_painted_text("BANGKAH", Vector3(0, 3.22, 17.70), 0.0, 0.019, Color("#e8fbff"), Color(0.02,0.06,0.08,0.4))
	_label("HEADQUARTERS  ·  TECHNOLOGY  ·  ENGINEERING", Vector3(0, 2.45, 17.72), 0.0046, Color("#b9d8d8"))
	# Floating curved reception desk: marble top + fluted oak base + under-desk warm glow
	_box("Reception base oak", Vector3(0, 0.62, 20.85), Vector3(10.6, 1.05, 0.95), oak, true, null, 0.52)
	_box("Reception base curve L", Vector3(-5.6, 0.62, 20.5), Vector3(1.3, 1.05, 0.8), oak, true, null, 0.52)
	_box("Reception base curve R", Vector3(5.6, 0.62, 20.5), Vector3(1.3, 1.05, 0.8), oak, true, null, 0.52)
	for fx in range(-10, 11):
		_box("Reception flute", Vector3(float(fx)*0.5, 0.62, 21.34), Vector3(0.06, 0.95, 0.03), oak.darkened(0.14), false, null, 0.58)
	_box("Reception marble top", Vector3(0, 1.22, 20.78), Vector3(11.8, 0.14, 1.45), Color("#f3efe6"), false, null, 0.14, 0.03)
	_box("Reception underglow", Vector3(0, 0.12, 20.7), Vector3(10.0, 0.03, 0.9), Color("#f0d8a8"), false, null, 0.2, 0.0, false, Color("#ffd9a0"))
	_box("Reception brand strip", Vector3(0, 0.72, 21.38), Vector3(6.8, 0.10, 0.03), cyan, false, null, 0.2, 0.0, false, cyan)
	_label("VISITOR CHECK-IN", Vector3(0, 1.12, 21.45), 0.0048, Color("#fff7e6"))
	_box("Reception monitor bezel", Vector3(0, 1.62, 20.30), Vector3(1.55, 0.88, 0.14), Color("#29383d"), false)
	_box("Reception monitor screen", Vector3(0, 1.63, 20.21), Vector3(1.34, 0.68, 0.025), Color("#31534b"), false, null, 0.2, 0.0, false, Color("#5e9b7c"))
	_box("Reception keyboard", Vector3(-1.0, 1.32, 20.75), Vector3(0.85, 0.04, 0.28), Color("#46524e"), false)
	_box("Visitor sign-in book", Vector3(1.35, 1.32, 20.72), Vector3(0.72, 0.06, 0.48), Color("#d2c5a9"), false)

	# Zone B: Security turnstiles (flap barrier feel) — centered, clear 3m+ clearance to core
	for tx in [-2.6, 0.0, 2.6]:
		_box("Turnstile housing", Vector3(tx, 0.52, 15.2), Vector3(0.55, 1.02, 0.95), Color("#1f2326"), true, null, 0.3, 0.35)
		_box("Turnstile glass flap", Vector3(tx, 0.78, 14.78), Vector3(0.05, 0.62, 0.55), Color(0.72,0.84,0.90,0.22), false, null, 0.06, 0.02, true)
		_box("Turnstile reader", Vector3(tx+0.30, 0.88, 15.0), Vector3(0.08, 0.18, 0.10), Color("#0f1416"), false, null, 0.25, 0.0, false, Color("#52c49a"))
		_box("Turnstile arrow", Vector3(tx, 1.08, 14.72), Vector3(0.22, 0.08, 0.02), Color("#52c49a"), false, null, 0.2, 0.0, false, Color("#62d4aa"))
	_box("Turnstile rail", Vector3(0, 0.52, 15.2), Vector3(7.2, 0.06, 0.06), Color("#2a3034"), false, null, 0.35, 0.35)
	# Digital Directory Totem beside turnstile (relocated off center)
	_box("Directory totem base", Vector3(5.4, 0.35, 15.2), Vector3(0.65, 0.7, 0.45), Color("#1f2326"), false, null, 0.35, 0.4)
	_box("Directory totem frame", Vector3(5.4, 1.55, 15.2), Vector3(0.82, 2.0, 0.12), Color("#14181b"), false, null, 0.25, 0.45)
	_box("Directory totem screen", Vector3(5.4, 1.55, 15.27), Vector3(0.70, 1.78, 0.03), Color("#0d1a20"), false, null, 0.12, 0.0, false, Color("#2aa8c8"))
	_painted_text("DIRECTORY / PETA", Vector3(5.4, 1.95, 15.30), 0.0, 0.0022, Color("#dff8ff"), Color(0,0,0,0))
	_painted_text("L1 LAYANAN  L2 TIM  L3 OWNER", Vector3(5.4, 1.45, 15.30), 0.0, 0.0016, Color("#9ad7c2"), Color(0,0,0,0))

	# Zone A: Waiting lounge — cognac/charcoal leather low-profile, wool rug, marble coffee table, textured plants
	_box("Lobby wool rug", Vector3(0, 0.155, 10.8), Vector3(14.5, 0.04, 5.8), Color("#5a5f63"), false, null, 0.95)
	_add_lounge_sofa(Vector3(-5.8, 0, 10.8), PI * 0.5, Color("#3a3f43"), 3.0) # charcoal leather
	_add_lounge_sofa(Vector3(5.8, 0, 10.8), -PI * 0.5, Color("#8a5a3a"), 3.0) # cognac leather
	_box("Lobby coffee table base", Vector3(0, 0.34, 10.8), Vector3(0.9, 0.32, 0.9), Color("#1f2326"), false, null, 0.3, 0.25)
	_box("Lobby coffee table top", Vector3(0, 0.52, 10.8), Vector3(2.2, 0.08, 1.35), Color("#2a2f33"), false, null, 0.14, 0.04) # dark marble
	for x in [-10.5, 10.5]:
		_box("Planter box tall", Vector3(x, 0.55, 10.8), Vector3(0.85, 1.05, 0.85), Color("#b7bdb6"), false, null, 0.55)
		_add_plant(Vector3(x, 1.05, 10.8), 1.05) # Monstera/textured feel (procedural)
	# Centerpiece linear pendant over reception/waiting (replaces scattered feel) + track lights by turnstile
	_box("Lobby linear pendant", Vector3(0, 4.75, 15.8), Vector3(8.5, 0.06, 0.26), Color("#1f2326"), false, null, 0.3, 0.25)
	_box("Lobby linear glow", Vector3(0, 4.71, 15.8), Vector3(8.1, 0.03, 0.18), Color("#f4e6c8"), false, null, 0.2, 0.0, false, Color("#ffe6b8"))
	_box("Track rail", Vector3(0, 5.15, 15.2), Vector3(6.5, 0.04, 0.08), Color("#1f2326"), false, null, 0.35, 0.4)
	for sx in [-2.4, 0.0, 2.4]:
		_box("Track spot", Vector3(sx, 5.08, 15.2), Vector3(0.18, 0.12, 0.12), Color("#2a3034"), false, null, 0.3, 0.35)
		var sl := SpotLight3D.new()
		sl.position = Vector3(sx, 5.0, 15.2)
		sl.rotation_degrees = Vector3(-90, 0, 0)
		sl.light_color = Color("#fff0d8"); sl.light_energy = 0.22; sl.spot_range = 7.0; sl.spot_angle = 38.0
		sl.shadow_enabled = false
		add_child(sl)
	# Perimeter ceiling shadow gap (tali air) L1 lobby
	_box("Lobby shadow gap", Vector3(0, 5.32, 39.62), Vector3(36.0, 0.03, 0.05), Color("#1a1f1d"), false, null, 0.9)

func _add_lounge_sofa(position: Vector3, rotation_y: float, color: Color, width: float = 2.8) -> void:
	var p := position + Vector3(0, _floor_y, 0)
	var root := Node3D.new()
	root.position = p
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
		var world_sit := Vector3(p.x + cos(rotation_y) * sx, p.y, p.z - sin(rotation_y) * sx)
		seats.append({"position": world_sit, "yaw": rotation_y + PI, "kind": "sofa", "pivot": null, "label": "Sofa"})

func _build_owner_suite() -> void:
	# L3 Executive Suite (mewah/modern, terisi rapi). Seat/workstation registries PRESERVED.
	_label("LANTAI 3  /  EXECUTIVE SUITE  /  OWNER", Vector3(-29.5, 3.55, -38.1), 0.006)
	var walnut := Color("#6b4a2e"); var matte := Color("#1f2326"); var slate := Color("#2c302e")
	var brass := Color("#c7a85a"); var smoke := Color(0.18,0.20,0.22,0.35); var leather := Color("#3b3028")
	# Fluted/slate feature wall + cove warm strip (modern, not old)
	_box("Owner fluted wall", Vector3(-29.5, 2.0, -38.95), Vector3(16.8, 3.9, 0.18), slate, true)
	for fx in range(-8,9):
		_box("Flute", Vector3(-29.5 + fx*1.0, 2.0, -38.84), Vector3(0.10, 3.7, 0.06), Color("#343a36"), false)
	_box("Cove LED warm", Vector3(-29.5, 3.78, -38.78), Vector3(14.5, 0.06, 0.06), Color("#f2d9a6"), false, null, 0.2, 0.0, false, Color("#ffdca0"))
	_box("Owner crest", Vector3(-29.5, 3.05, -38.82), Vector3(4.8, 0.85, 0.10), walnut, false)
	_painted_text("BANGKAH  /  OWNER", Vector3(-29.5, 3.05, -38.74), 0.0, 0.0065, Color("#f0dfb0"), Color(0,0,0,0))
	# Floor zoning: polished dark marble (work) + dark walnut herringbone feel (lounge)
	_box("Marble work zone", Vector3(-29.5, 0.16, -31.2), Vector3(16.5, 0.03, 11.5), Color("#232628"), false, null, 0.12, 0.02)
	_box("Walnut lounge zone", Vector3(-29.5, 0.16, -24.2), Vector3(16.5, 0.03, 6.8), Color("#4a3523"), false, null, 0.55)
	_box("Area rug", Vector3(-29.5, 0.185, -24.0), Vector3(8.5, 0.02, 4.2), Color("#4a4f53"), false, null, 0.92)
	# A) EXECUTIVE WORKSTATION (seat/workstation PRESERVED at -29.3,0,-31.3 / OWNER-PC-001)
	_add_workstation(Vector3(-29.3, 0, -31.3), "OWNER  /  EXECUTIVE DESK", walnut, true)
	# Design Bible: floating curved walnut desk (visual overlay; seat/ID unchanged)
	_box("Exec desk slab", Vector3(-29.3, 0.79, -31.25), Vector3(5.4, 0.11, 2.3), walnut, false, null, 0.44)
	_box("Exec desk curve L", Vector3(-31.75, 0.79, -30.85), Vector3(1.5, 0.11, 1.6), walnut, false, null, 0.44)
	_box("Exec desk curve R", Vector3(-26.85, 0.79, -30.85), Vector3(1.5, 0.11, 1.6), walnut, false, null, 0.44)
	_box("Desk underglow", Vector3(-29.3, 0.63, -31.25), Vector3(4.8, 0.03, 1.9), Color("#FFD166"), false, null, 0.2, 0.0, false, Color("#FFD166"))
	# Wall Monitor Array — 6 bezel-less AI/server displays (visual; workstation/registry unchanged)
	_box("Monitor array panel", Vector3(-29.5, 2.35, -38.72), Vector3(11.2, 2.5, 0.10), matte, false)
	for mi in range(6):
		var mx := -33.8 + float(mi) * 1.72
		var ec: Color = [Color("#00FFFF"),Color("#55d6b0"),Color("#6aa8ff"),Color("#00FFFF"),Color("#55d6b0"),Color("#6aa8ff")][mi]
		_box("Wall monitor shell", Vector3(mx, 2.35, -38.65), Vector3(1.62, 1.95, 0.025), Color("#0a0f12"), false, null, 0.18)
		_box("Wall monitor", Vector3(mx, 2.35, -38.63), Vector3(1.56, 1.88, 0.012), Color("#0f171a"), false, null, 0.14, 0.0, false, ec)
	_label("COMMAND CENTER · AI / SERVER / OMNISERVE", Vector3(-29.5, 3.72, -38.58), 0.0042, Color("#00FFFF"))
	_box("Chair premium headrest", Vector3(-29.3, 1.55, -29.9), Vector3(0.62, 0.22, 0.10), leather, false, null, 0.7)
	# B) PRIVATE LOUNGE & ENTERTAINMENT (keep existing sofa seat registration)
	_add_lounge_sofa(Vector3(-29.5, 0, -22.5), 0.0, Color("#7a5230"), 3.8) # cognac leather, PRESERVES 2 sofa seats
	_box("Stagger table A", Vector3(-30.4, 0.42, -24.6), Vector3(1.5, 0.08, 1.1), Color("#1f2326"), false, null, 0.1, 0.02) # black marble
	_box("Stagger table B", Vector3(-28.6, 0.34, -24.9), Vector3(1.3, 0.08, 1.0), Color("#ece7dc"), false, null, 0.12, 0.02)
	# OLED + fluted entertainment wall
	_box("Entertainment fluted", Vector3(-29.5, 2.0, -20.55), Vector3(9.5, 3.2, 0.12), Color("#3a3028"), false)
	_box("OLED TV", Vector3(-29.5, 2.25, -20.46), Vector3(4.8, 2.2, 0.05), Color("#101418"), false, null, 0.12, 0.0, false, Color("#2a5a6a"))
	_box("TV bias light", Vector3(-29.5, 2.25, -20.42), Vector3(5.0, 2.4, 0.02), Color("#f0d8a8"), false, null, 0.2, 0.0, false, Color("#ffd9a0"))
	_box("Soundbar", Vector3(-29.5, 1.05, -20.44), Vector3(3.2, 0.12, 0.10), matte, false, null, 0.3, 0.2)
	# Biometric reader by suite entry (visual)
	_box("Biometric panel", Vector3(-20.2, 1.45, -19.9), Vector3(0.12, 0.22, 0.08), Color("#14181b"), false, null, 0.25, 0.4)
	_box("Biometric glow", Vector3(-20.2, 1.45, -19.85), Vector3(0.08, 0.14, 0.02), Color("#2aa8c8"), false, null, 0.2, 0.0, false, Color("#44d8ff"))
	_box("PC glass rig", Vector3(-33.6, 0.95, -21.4), Vector3(0.9, 1.5, 0.8), smoke, false, null, 0.08, 0.02, true)
	_box("Rig glow", Vector3(-33.6, 1.0, -21.38), Vector3(0.6, 0.9, 0.02), Color("#6ad0ff"), false, null, 0.2, 0.0, false, Color("#58c8ff"))
	# C) MINI BAR & COFFEE CORNER
	_box("Mini bar counter", Vector3(-22.4, 0.95, -35.8), Vector3(3.4, 0.14, 1.2), Color("#1c1f22"), false, null, 0.12, 0.05)
	_box("Bar waterfall", Vector3(-22.4, 0.48, -36.4), Vector3(3.4, 0.96, 0.10), Color("#1c1f22"), false, null, 0.12, 0.05)
	_box("Espresso", Vector3(-23.2, 1.28, -35.8), Vector3(0.55, 0.55, 0.55), Color("#7a8488"), false, null, 0.25, 0.6)
	_box("Under fridge", Vector3(-21.5, 0.55, -35.8), Vector3(0.9, 1.0, 0.9), smoke, false, null, 0.08, 0.02, true)
	_box("Glass rack", Vector3(-22.4, 1.85, -36.1), Vector3(2.2, 0.08, 0.35), matte, false)
	for gx in [-23.0,-22.4,-21.8]: _box("Goblet", Vector3(gx, 1.65, -36.05), Vector3(0.08,0.28,0.08), Color(0.85,0.9,0.95,0.35), false, null, 0.05,0.0,true)
	# D) TROPHY & HOBBY GALLERY (floating shelves, backlit)
	for sd in [[1.2,3.8],[2.0,3.2],[2.8,2.6]]:
		var sy: float = float(sd[0]); var sw: float = float(sd[1])
		_box("Floating shelf", Vector3(-37.2, sy, -27.5), Vector3(0.35, 0.06, sw), walnut, false)
		_box("Shelf backlight", Vector3(-37.05, sy-0.05, -27.5), Vector3(0.02, 0.02, sw-0.2), Color("#ffd9a0"), false, null, 0.2, 0.0, false, Color("#ffc978"))
	_box("Plaque", Vector3(-37.05, 1.45, -28.6), Vector3(0.03, 0.45, 0.35), Color("#d7c08a"), false, null, 0.25, 0.4)
	_box("Cert frame", Vector3(-37.05, 2.25, -28.8), Vector3(0.03, 0.55, 0.42), matte, false)
	_box("Keyboard display", Vector3(-37.05, 2.95, -27.2), Vector3(0.18, 0.08, 0.55), Color("#2a2f33"), false)
	_add_plant(Vector3(-37.3, 0, -22.2), 1.35) # Monstera-like large corner plant
	_add_plant(Vector3(-21.6, 0, -22.2), 1.1)
	# Keep STRATEGY shelf + command markers (relocated already) and tray (PRESERVED coords)
	_add_shelf(Vector3(-37.2, 0.18, -34.3), 2.2, 2.5, 0.8, "STRATEGY")
	# Command center side array kept as accent (separate from wall array above)
	_box("Command frame side", Vector3(-21.1, 2.25, -30.0), Vector3(0.12, 2.8, 8.5), Color("#3a4542"), false)
	for mz in [-33.2,-31.1,-29.0,-26.9]:
		for my in [1.55,2.35,3.15]:
			_box("Side cmd", Vector3(-21.02, my, mz), Vector3(0.03, 0.62, 1.55), Color("#1f3b3a"), false, null, 0.18, 0.0, false, Color("#4bbf9a"))
	# En-suite + Balcony (frameless sliding glass door + railing to city view)
	_box("En-suite frame", Vector3(-38.7, 1.35, -34.5), Vector3(0.10, 2.7, 1.6), walnut, false)
	_label("EN-SUITE", Vector3(-38.58, 2.55, -34.5), 0.0038, Color("#e8dcc8"))
	_box("Balcony sliding glass", Vector3(-29.5, 1.55, -20.32), Vector3(4.2, 3.0, 0.08), Color(0.72,0.84,0.90,0.18), false, null, 0.06, 0.02, true)
	_box("Balcony frame", Vector3(-29.5, 3.08, -20.32), Vector3(4.4, 0.10, 0.12), matte, false)
	# Balcony outside (on L3 edge) — simple outdoor deck with glass railing
	_box("Balcony deck", Vector3(-29.5, L3_Y + 0.06 - _floor_y, -18.6), Vector3(5.6, 0.12, 3.2), Color("#6a5a48"), true)
	_box("Balcony rail glass", Vector3(-29.5, L3_Y + 1.05 - _floor_y, -17.05), Vector3(5.4, 1.1, 0.06), Color(0.78,0.88,0.94,0.18), false, null, 0.06, 0.02, true)
	for bx in [-31.9,-27.1]: _box("Balcony chair", Vector3(bx, L3_Y + 0.42 - _floor_y, -18.6), Vector3(0.9,0.55,0.9), Color("#8a7a66"), true)
	_box("Balcony table", Vector3(-29.5, L3_Y + 0.38 - _floor_y, -18.6), Vector3(0.7,0.08,0.7), Color("#d8d2c6"), false)
	_label("BALKON PRIBADI", Vector3(-29.5, L3_Y + 1.35 - _floor_y, -17.15), 0.0036, Color("#eaf2ee"))
	# Paper tray (PRESERVED position relative to workstation/main interactable)
	_box("Owner in tray base", Vector3(-27.2, 1.05, -31.25), Vector3(0.90, 0.16, 0.78), Color("#536b61"), false)
	_box("Owner in tray left", Vector3(-27.66, 1.24, -31.25), Vector3(0.07, 0.34, 0.82), Color("#c0c7bc"), false)
	_box("Owner in tray right", Vector3(-26.74, 1.24, -31.25), Vector3(0.07, 0.34, 0.82), Color("#c0c7bc"), false)
	for i in range(4): _box("Paper stack in tray", Vector3(-27.2, 1.16 + float(i) * 0.035, -31.25), Vector3(0.70, 0.025, 0.61), Color("#f0eee3"), false)
	_label("INBOX TRAY", Vector3(-27.2, 1.72, -31.25), 0.0038, Color("#e8efe7"))

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
	# Standing agenda board near lift/stair landing (L2, visual) + directory hint
	_box("Agenda stand post", Vector3(-1.2, 0.75, -21.6), Vector3(0.08, 1.5, 0.08), Color("#2a3034"), false, null, 0.3, 0.45)
	_box("Agenda stand board", Vector3(-1.2, 1.55, -21.52), Vector3(1.5, 1.0, 0.06), Color("#1f2326"), false, null, 0.28, 0.4)
	_box("Agenda stand screen", Vector3(-1.2, 1.55, -21.48), Vector3(1.34, 0.84, 0.03), Color("#142028"), false, null, 0.15, 0.0, false, Color("#4aa8a0"))
	_painted_text("AGENDA PERUSAHAAN", Vector3(-1.2, 1.82, -21.45), PI, 0.0024, Color("#eaf6f2"), Color(0,0,0,0))

func _build_management_offices() -> void:
	_label("LANTAI 2  /  CORE LEADERSHIP", Vector3(8.0, 3.5, -38.1), 0.006)
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
	_label("LANTAI 1  /  MAIN BOARDROOM", Vector3(-29.5, 3.45, 4.4), 0.0057)
	var table_center := Vector3(-29.5, 0, 14.3)
	# Oval-feel boardroom table (layered) + leather chairs (registry preserved: 10 seats)
	_box("Boardroom table top", table_center + Vector3(0, 0.82, 0), Vector3(10.2, 0.16, 3.0), Color("#6f563f"), true, null, 0.38)
	_box("Boardroom table cap L", table_center + Vector3(-5.1, 0.82, 0), Vector3(1.1, 0.16, 2.4), Color("#6f563f"), false, null, 0.38)
	_box("Boardroom table cap R", table_center + Vector3(5.1, 0.82, 0), Vector3(1.1, 0.16, 2.4), Color("#6f563f"), false, null, 0.38)
	for x in [-4.2, 4.2]:
		_box("Boardroom table pedestal", table_center + Vector3(x, 0.4, 0), Vector3(0.32, 0.78, 1.2), Color("#2f3538"), false, null, 0.35, 0.25)
	# 10 chairs (same count/positions/yaws as before)
	for x in [-4.2, -2.1, 0.0, 2.1, 4.2]:
		_add_meeting_chair(table_center + Vector3(x, 0, -2.55), PI)
		_add_meeting_chair(table_center + Vector3(x, 0, 2.55), 0.0)
	# Reeded-glass partition feel overlay on boardroom front (privacy, light passes)
	_box("Boardroom reeded glass", Vector3(-29.5, 2.1, 4.28), Vector3(14.5, 3.6, 0.05), Color(0.78,0.84,0.82,0.22), false, null, 0.18, 0.0, true)
	for rx in range(-7, 8):
		_box("Reed", Vector3(-29.5 + float(rx)*0.95, 2.1, 4.31), Vector3(0.06, 3.5, 0.02), Color(0.88,0.92,0.90,0.28), false, null, 0.14, 0.0, true)
	_box("Boardroom display frame", Vector3(-29.5, 2.2, 5.05), Vector3(6.6, 2.35, 0.18), Color("#1f2326"), false, null, 0.3, 0.35)
	_box("Boardroom display screen", Vector3(-29.5, 2.2, 4.93), Vector3(6.2, 2.0, 0.03), Color("#142028"), false, null, 0.16, 0.0, false, Color("#3a7a8a"))
	# Linear pendant above table
	_box("Boardroom linear pendant", Vector3(-29.5, 3.25, 14.3), Vector3(7.5, 0.06, 0.22), Color("#1f2326"), false, null, 0.3, 0.25)
	_box("Boardroom linear glow", Vector3(-29.5, 3.21, 14.3), Vector3(7.2, 0.03, 0.16), Color("#f4e6c8"), false, null, 0.2, 0.0, false, Color("#ffe6b8"))
	_box("Boardroom whiteboard frame", Vector3(-38.7, 1.9, 15.0), Vector3(0.13, 2.2, 6.5), Color("#6e7b74"), false)
	_box("Boardroom whiteboard", Vector3(-38.61, 1.9, 15.0), Vector3(0.03, 1.92, 6.2), Color("#e6e9e1"), false)
	_box("Boardroom credenza", Vector3(-29.5, 0.7, 23.2), Vector3(8.0, 1.35, 0.72), Color("#7b6856"), true)
	for x in [-32.0, -29.5, -27.0]:
		_cylinder("Meeting water bottle", Vector3(x, 1.49, 23.2), 0.10, 0.42, Color("#91b2af"), null, false, 0.1)

func _add_meeting_chair(position: Vector3, rotation_y: float) -> void:
	var p := position + Vector3(0, _floor_y, 0)
	var root := Node3D.new()
	root.position = p
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
	seats.append({"position": Vector3(p.x, p.y, p.z), "yaw": rotation_y, "kind": "meeting", "pivot": swivel, "label": "Kursi Rapat"})

func _build_api_lab() -> void:
	_label("API  /  INFRASTRUCTURE LAB", Vector3(29.0, 3.45, 4.4), 0.0057)
	_add_workstation(Vector3(29.0, 0, 12.65), "NAYA  /  API SPECIALIST", Color("#987f5b"), true)
	# Server racks, glowing LEDs (cyan/tech), diagnostics — visual; workstation/seat preserved.
	var rack := Color("#344247"); var ledc := Color("#00FFFF")
	for x in [21.0, 24.0, 37.0]:
		_box("Infrastructure rack", Vector3(x, 1.35, 22.0), Vector3(1.8, 2.65, 0.95), rack, true, null, 0.45, 0.2)
		for level in range(6):
			var y := 0.42 + float(level) * 0.38
			_box("Rack equipment", Vector3(x, y, 21.49), Vector3(1.52, 0.28, 0.06), Color("#202f35"), false)
			for led in range(5):
				var lc: Color = ledc if (level+led)%3!=0 else Color("#52ff9a")
				_sphere("Rack LED", Vector3(x - 0.58 + float(led) * 0.145, y, 21.44), 0.028, lc, Vector3.ONE)
	_box("API topology board frame", Vector3(30.0, 2.4, 24.65), Vector3(7.4, 1.65, 0.14), Color("#1f2326"), false, null, 0.3, 0.4)
	_box("API topology board", Vector3(30.0, 2.4, 24.56), Vector3(7.1, 1.38, 0.04), Color("#0f1820"), false, null, 0.2, 0.0, false, Color("#1e5060"))
	for x in [27.0, 29.0, 31.0, 33.0]:
		_box("API topology node", Vector3(x, 2.4, 24.52), Vector3(0.75, 0.48, 0.03), Color("#7fd4d8"), false, null, 0.2, 0.0, false, Color("#3aa8b0"))

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

func _build_owner_private_lounge() -> void:
	# L3 — Ruang pribadi Owner
	_label("LANTAI 3  /  OWNER  /  RUANG PRIBADI", Vector3(-10.0, 3.45, 25.8), 0.0054)
	_box("Owner lounge accent wall", Vector3(-10.0, 1.95, 39.72), Vector3(18.6, 3.7, 0.10), Color("#6b4a38"), false)
	_box("Owner lounge accent trim", Vector3(-10.0, 0.42, 39.66), Vector3(18.6, 0.10, 0.05), Color("#c5a366"), false)
	_box("Owner lounge rug", Vector3(-10.0, 0.16, 32.0), Vector3(15.0, 0.06, 9.0), Color("#7c5f4a"), false)
	_box("Owner lounge rug inset", Vector3(-10.0, 0.20, 32.0), Vector3(13.4, 0.045, 7.6), Color("#8f7260"), false)
	_add_lounge_sofa(Vector3(-10.0, 0, 34.6), PI, Color("#7a5a44"), 4.2)
	_box("Owner lounge coffee table", Vector3(-10.0, 0.46, 32.6), Vector3(3.2, 0.60, 1.35), Color("#8a6a4c"), false)
	_box("Owner lounge table top", Vector3(-10.0, 0.80, 32.6), Vector3(3.45, 0.12, 1.55), Color("#c8aa83"), false)
	_cylinder("Owner lounge mug", Vector3(-10.8, 0.97, 32.4), 0.09, 0.14, Color("#e7e1d4"))
	_box("Owner lounge book stack", Vector3(-9.2, 0.90, 32.8), Vector3(0.55, 0.16, 0.40), Color("#5e756a"), false)
	_box("Owner lounge TV frame", Vector3(-10.0, 2.05, 25.45), Vector3(5.4, 1.95, 0.14), Color("#2f3f3c"), false)
	_box("Owner lounge TV screen", Vector3(-10.0, 2.05, 25.36), Vector3(5.05, 1.62, 0.03), Color("#1c2f36"), false, null, 0.18, 0.0, false, Color("#3f6d68"))
	_box("Owner lounge TV bar", Vector3(-10.0, 1.18, 25.40), Vector3(3.2, 0.08, 0.05), Color("#35464a"), false)
	_add_shelf(Vector3(-17.5, 0.16, 36.5), 3.4, 2.65, 0.9, "PERPUSTAKAAN PRIBADI")
	_add_shelf(Vector3(-17.5, 0.16, 29.5), 3.4, 2.65, 0.9, "KOLEKSI")
	_box("Owner kitchenette cabinet", Vector3(-3.4, 0.72, 36.5), Vector3(3.6, 1.42, 1.05), Color("#7c6853"), false)
	_box("Owner kitchenette countertop", Vector3(-3.4, 1.48, 36.35), Vector3(3.8, 0.14, 1.25), Color("#d3cbb9"), false)
	_box("Owner kitchenette kettle", Vector3(-3.9, 1.75, 36.2), Vector3(0.34, 0.42, 0.34), Color("#3b4e4b"), false)
	_cylinder("Owner kitchenette mug", Vector3(-3.1, 1.62, 36.2), 0.09, 0.14, Color("#e7e1d4"))
	_box("Owner mini fridge", Vector3(-1.9, 0.65, 38.3), Vector3(0.9, 1.25, 0.85), Color("#c4cbc6"), false, null, 0.28, 0.3)
	_cylinder("Owner floor lamp pole", Vector3(-4.4, 0.85, 28.5), 0.045, 1.6, Color("#596b63"))
	_box("Owner floor lamp glow", Vector3(-4.4, 1.72, 28.5), Vector3(0.42, 0.10, 0.42), Color("#f5e0b8"), false, null, 0.22, 0.0, false, Color("#f8ecca"))
	var owner_lamp := OmniLight3D.new()
	owner_lamp.position = Vector3(-4.4, _floor_y + 1.85, 28.5)
	owner_lamp.light_color = Color("#ffe8c8"); owner_lamp.light_energy = 0.38; owner_lamp.omni_range = 7.0
	add_child(owner_lamp)
	_add_plant(Vector3(-18.0, 0, 26.5), 0.95); _add_plant(Vector3(-2.8, 0, 26.5), 0.95); _add_plant(Vector3(-18.0, 0, 38.5), 1.05)
	_add_framed_poster(Vector3(-19.62, 2.1, 32.5), Color("#c5a366"), "OWNER")
	_add_wall_clock(Vector3(-10.0, 3.0, 39.65))
	_box("Owner lounge sideboard", Vector3(-2.9, 0.72, 29.5), Vector3(3.2, 1.38, 0.70), Color("#8b735c"), false)
	_box("Owner lounge sideboard top", Vector3(-2.9, 1.46, 29.5), Vector3(3.4, 0.12, 0.84), Color("#c8aa83"), false)
	_cylinder("Owner lounge vase", Vector3(-3.6, 1.72, 29.5), 0.16, 0.30, Color("#5e756a"))
	_box("Owner lounge book pile", Vector3(-2.2, 1.62, 29.5), Vector3(0.5, 0.22, 0.36), Color("#7889a8"), false)

func _build_staff_pantry_lounge() -> void:
	# L1 — Pantry & staff lounge
	_label("LANTAI 1  /  PANTRY  /  STAFF LOUNGE", Vector3(10.0, 3.45, 25.8), 0.0057)
	# Pantry/coffee — keeps `coffee` interactable anchor (22.5,0,34.8 in main.gd) coherent.
	_box("Pantry island bar", Vector3(27.5, 0.88, 29.0), Vector3(9.0, 1.62, 1.45), Color("#3a3f43"), true, null, 0.4)
	_box("Pantry island top", Vector3(27.5, 1.73, 29.0), Vector3(9.25, 0.16, 1.65), Color("#d8d2c8"), false, null, 0.2, 0.06)
	_box("Coffee machine", Vector3(22.5, 2.00, 36.05), Vector3(1.0, 0.92, 0.80), Color("#2C302E"), false, null, 0.35, 0.25)
	_box("Coffee machine screen", Vector3(22.5, 2.15, 35.62), Vector3(0.58, 0.25, 0.035), Color("#89b7a3"), false, null, 0.18, 0.0, false, Color("#00FFFF"))
	_box("Pantry sink", Vector3(34.0, 1.58, 36.15), Vector3(1.8, 0.08, 0.75), Color("#7b8c86"), false, null, 0.2, 0.48)
	_cylinder("Pantry faucet", Vector3(34.0, 1.89, 35.8), 0.045, 0.54, Color("#bcc7c1"), null, false, 0.85)
	_box("Microwave", Vector3(26.0, 2.0, 36.05), Vector3(1.25, 0.72, 0.78), Color("#77847f"), false)
	_box("Refrigerator", Vector3(38.5, 1.45, 31.8), Vector3(1.7, 2.75, 1.55), Color("#c4cbc6"), true, null, 0.28, 0.3)
	for x in [24.2, 27.5, 30.8]:
		_cylinder("Bar stool stem", Vector3(x, 0.55, 26.9), 0.075, 0.98, Color("#65736d"), null, false, 0.55)
		_cylinder("Bar stool seat", Vector3(x, 1.08, 26.9), 0.42, 0.14, Color("#61796e"))
	# Staff lounge — sofas use cognac/charcoal palette (seats preserved via _add_lounge_sofa)
	_box("Lounge rug", Vector3(9.0, 0.16, 32.0), Vector3(16.0, 0.06, 9.5), Color("#87998d"), false)
	_add_lounge_sofa(Vector3(7.0, 0, 29.2), 0.0, Color("#8B5A2B"), 3.8) # cognac
	_add_lounge_sofa(Vector3(7.0, 0, 35.0), PI, Color("#3a3f43"), 3.8)  # charcoal
	_box("Lounge coffee table", Vector3(7.0, 0.48, 32.1), Vector3(3.3, 0.15, 1.35), Color("#2a2f33"), false, null, 0.14, 0.04)
	_add_plant(Vector3(15.0, 0, 29.0), 1.0); _add_plant(Vector3(15.0, 0, 35.0), 1.0)
	_box("Lounge wall display", Vector3(9.0, 2.1, 38.75), Vector3(5.6, 2.0, 0.14), Color("#41544b"), false)
	_box("Lounge display screen", Vector3(9.0, 2.1, 38.65), Vector3(5.25, 1.66, 0.03), Color("#254039"), false, null, 0.18, 0.0, false, Color("#426d57"))

## Kursi bebas yang tidak terikat workstation: klaster lounge di lobby luas
## plus kursi geser di QA supaya setiap bengkel/jabatan punya tempat duduk.
func _build_information_boards() -> void:
	# L1 Zone B — Digital Directory / announcements placed beside security/columns (not blocking flow)
	_info_board("InfoDirectory", Vector3(9.2, 0, 16.8), -PI * 0.5, "DIREKTORI RUANGAN", [
		"L1: Resepsionis · Security · Boardroom",
		"L1: Lab API & Infra · Arsip & Cetak",
		"L1: Pantry & Staff Lounge",
		"L2: Sekretariat · Manajemen · Arsitektur",
		"L2: Frontend/Desain · QA · Backend",
		"L3: Executive Suite / Ruang Owner",
	])
	_info_board("InfoAnnounce", Vector3(-9.2, 0, 16.8), PI * 0.5, "PENGUMUMAN MINGGU INI", [
		"Senin 09.00 · All-hands (Boardroom)",
		"Selasa 14.00 · Fire drill area lobby",
		"Kamis 13.00 · Sharing sesi QA",
		"Jumat 15.00 · Sprint review",
		"Akses via kartu / Security Turnstile",
	])
	_info_board("InfoBoardroom", Vector3(-19.35, 0, 17.8), PI * 0.5, "JADWAL BOARDROOM", [
		"Senin 09.00 · All-hands",
		"Kamis 13.00 · Review arsitektur",
		"Jumat 15.00 · Sprint review",
		"Kapasitas: 10 orang",
		"Pemesanan: hubungi resepsionis",
	], 2.1, 1.9)

func _build_accent_walls_l1() -> void:
	for x in [-35.5, -23.5]:
		_box("Boardroom terracotta accent", Vector3(x, 1.95, 4.86), Vector3(2.4, 2.9, 0.08), Color("#9a6a58"), false)
		_box("Boardroom accent trim", Vector3(x, 0.48, 4.87), Vector3(2.4, 0.10, 0.09), Color("#c5a366"), false)
	_box("Boardroom brass line", Vector3(-39.68, 0.75, 15.0), Vector3(0.06, 0.12, 6.0), Color("#c5a366"), false)
	_box("API graphite accent", Vector3(39.74, 1.95, 14.5), Vector3(0.06, 2.9, 5.0), Color("#3a4a4d"), false)
	_box("Lobby sand accent", Vector3(12.05, 1.60, 28.2), Vector3(0.08, 3.2, 2.6), Color("#b8a88e"), false)
	_cylinder("Lobby floor medallion", Vector3(11.8, 0.16, 28.2), 2.1, 0.05, Color("#7c8a7e"), null, false, 0.4)
	_cylinder("Lobby medallion inner", Vector3(11.8, 0.20, 28.2), 1.35, 0.055, Color("#9aa78f"), null, false, 0.4)
	_add_framed_poster(Vector3(-19.62, 2.1, 10.0), Color("#9a6a58"), "BANGKAH")
	_add_framed_poster(Vector3(19.62, 2.1, 10.0), Color("#6f8a7a"), "INTEGRITY")
	for x in [-29.0, 0.0, 29.0]:
		_box("Door threshold south wing", Vector3(x, 0.17, 25.0), Vector3(2.9, 0.045, 0.5), Color("#9a6a58"), false)

func _build_accent_walls_l2() -> void:
	_box("Management sage accent", Vector3(8.2, 3.15, -38.80), Vector3(6.4, 0.70, 0.06), Color("#6f8a7a"), false)
	_box("Engineering slate band", Vector3(0.0, 0.70, 3.86), Vector3(36.0, 1.0, 0.05), Color("#4c666a"), false)
	for x in [-29.0, -11.0, 8.0, 29.0]:
		_box("Door threshold north wing", Vector3(x, 0.17, -20.0), Vector3(2.9, 0.045, 0.5), Color("#6f8a7a"), false)
	for x in [-29.0, -6.5, 0.0, 13.0, 29.0]:
		_box("Door threshold engineering", Vector3(x, 0.17, 4.0), Vector3(2.9, 0.045, 0.5), Color("#4c666a"), false)
	_add_plant(Vector3(-18.5, 0, -17.5), 0.85); _add_plant(Vector3(18.5, 0, -17.5), 0.85)
	_add_plant(Vector3(-18.5, 0, -38.5), 1.0); _add_plant(Vector3(18.5, 0, -38.5), 1.0)

func _build_accent_walls_l3() -> void:
	_box("Owner wainscot walnut", Vector3(-29.5, 0.55, -38.88), Vector3(16.5, 0.85, 0.06), Color("#6b5238"), false)
	_box("Owner brass trim", Vector3(-29.5, 1.02, -38.89), Vector3(16.5, 0.09, 0.06), Color("#c5a366"), false)

func _build_free_seating_l1() -> void:
	# L1 lobby cluster (4 office seats) — positioned off main axis (keeps counts stable)
	_box("Lobby seating rug", Vector3(-9.5, 0.14, 19.8), Vector3(6.2, 0.03, 4.8), Color("#5a5f63"), false, null, 0.95)
	_box("Lobby coffee table base", Vector3(-9.5, 0.34, 19.8), Vector3(0.75, 0.30, 0.75), Color("#1f2326"), true, null, 0.3, 0.25)
	_box("Lobby coffee table top", Vector3(-9.5, 0.52, 19.8), Vector3(1.45, 0.08, 1.05), Color("#2a2f33"), false, null, 0.14, 0.04)
	for chair in [{"pos": Vector3(-11.0, 0, 18.6), "yaw": 0.0},{"pos": Vector3(-8.0, 0, 18.6), "yaw": 0.0},{"pos": Vector3(-11.0, 0, 21.0), "yaw": PI},{"pos": Vector3(-8.0, 0, 21.0), "yaw": PI}]:
		_add_office_chair(chair["pos"], Color("#3a3f43"), chair["yaw"], "Kursi Tamu Lobby")

func _build_free_seating_l2() -> void:
	# L2 QA collaboration (3 office seats) — moved to LANTAI 2
	for chair in [{"pos": Vector3(-4.5, 0, -3.2), "yaw": PI},{"pos": Vector3(-0.5, 0, -3.2), "yaw": PI},{"pos": Vector3(3.5, 0, -3.2), "yaw": PI}]:
		_add_office_chair(chair["pos"], Color("#62807c"), chair["yaw"], "Kursi Kolaborasi QA")

func _build_floor_cores() -> void:
	# Design Bible: floating open-riser stairs (transparent/open between treads, no dark slab),
	# frameless glass railing + matte-black handrail, under-tread warm LED, planter under L1 stairs,
	# panoramic smoked-glass lift with cyan indicators. Climbable collision (ramp+step strips) kept
	# invisible for playability; HQ registries/interactable positions in main.gd unchanged.
	var fys: Array[float] = [L1_Y, L2_Y, L3_Y]
	var labels := ["LANTAI 1","LANTAI 2","LANTAI 3"]
	var cx := 13.2
	var lxs := cx - 2.6 # tangga turun
	var rxs := cx + 0.4 # tangga naik
	var lx := cx + 3.4  # lift
	var cz := 10.7
	var marble := Color("#e9e4da"); var walnut := Color("#8B5A2B"); var matte := Color("#2C302E")
	var cyan := Color("#00FFFF"); var warm := Color("#FFD166"); var glass := Color(0.70,0.84,0.90,0.14)
	for fi in range(fys.size()):
		var fy: float = fys[fi]
		_box("Core landing", Vector3(cx, fy + 0.07, cz), Vector3(10.2, 0.14, 5.0), marble, true, null, 0.42)
		_box("Core inlay trim", Vector3(cx, fy + 0.155, cz), Vector3(10.3, 0.02, 5.1), Color("#c7a85a"), false, null, 0.3, 0.4)
		_box("Core feature wall", Vector3(cx, fy + 1.65, 15.45), Vector3(10.4, 3.3, 0.18), Color("#d6d9d2"), false)
		_box("Core shadow gap", Vector3(cx, fy + 0.02, 15.36), Vector3(10.3, 0.03, 0.04), Color("#1a1f1d"), false, null, 0.9)
		_box("Core header", Vector3(cx, fy + 3.08, 15.32), Vector3(9.2, 0.55, 0.10), matte, false, null, 0.3, 0.0, false, Color("#40524d"))
		_painted_text(labels[fi] + "  ·  TANGGA  &  LIFT", Vector3(cx, fy + 3.08, 15.38), 0.0, 0.0028, Color("#f3ecd8"), Color(0,0,0,0))
		_painted_text("TURUN ↓   NAIK ↑      LIFT →", Vector3(cx, fy + 2.15, 8.05), 0.0, 0.0038, Color("#243530"), Color("#f2ecda"))
	# --- Floating open-riser stairs (2 per link) ---
	for link in [{"fy": L1_Y, "to": "LANTAI 2"}, {"fy": L2_Y, "to": "LANTAI 3"}]:
		var fy: float = float(link["fy"])
		var flight_h := FLOOR_H
		var run_len := 8.4
		var steps_n := 16
		var rise := flight_h / float(steps_n)
		var step_run := run_len / float(steps_n)
		var z_top := 7.0
		var z_bot := z_top + run_len
		var z_mid := (z_top + z_bot) * 0.5
		var slope := atan2(flight_h, run_len)
		var ramp_len := sqrt(flight_h*flight_h + run_len*run_len)
		for sc in [{"x": rxs, "name": "TANGGA NAIK", "dir": "NAIK ↑"}, {"x": lxs, "name": "TANGGA TURUN", "dir": "TURUN ↓"}]:
			var sx: float = float(sc["x"])
			# Landing pads at top and bottom
			_box(str(sc["name"]) + " lower", Vector3(sx, fy + 0.07, z_bot + 0.4), Vector3(2.8, 0.14, 1.4), marble, true, null, 0.42)
			_box(str(sc["name"]) + " upper", Vector3(sx, fy + flight_h + 0.07, z_top - 0.4), Vector3(2.8, 0.14, 1.4), marble, true, null, 0.42)
			# Invisible climbable ramp + step-collision (playability; no solid dark slab visual)
			var ramp := _box(str(sc["name"]) + " ramp", Vector3(sx, fy + flight_h*0.5 + 0.02, z_mid), Vector3(2.4, 0.16, ramp_len + 0.2), Color(0,0,0,0.001), true)
			ramp.rotation.x = -slope
			for si in range(steps_n):
				var t := (float(si) + 0.5) / float(steps_n)
				_box("Step col", Vector3(sx, fy + 0.04 + t*flight_h, z_bot - t*run_len), Vector3(2.4, 0.04, step_run*0.85), Color(0,0,0,0), true)
			# Stringer wall (angled walnut support on outer side of each flight)
			var str_side := 1.42 if sx > cx else -1.42
			var str_x := sx + str_side
			var sw := _box("Stringer", Vector3(str_x, fy + flight_h*0.5 + 0.55, z_mid), Vector3(0.16, 1.2, ramp_len), walnut, false, null, 0.55)
			sw.rotation.x = -slope
			# Newel posts at top and bottom of handrail
			for nz in [z_bot - 0.4, z_top + 0.4]:
				var ny := fy + 0.95 if nz > z_mid else fy + flight_h - 0.95
				_box("Newel post", Vector3(str_x, ny, nz), Vector3(0.22, 1.0, 0.22), walnut, false, null, 0.6)
			# Floating walnut treads (open-riser: no riser panels) + warm under-tread LED
			for si in range(steps_n):
				var t := (float(si) + 0.5) / float(steps_n)
				var sy := fy + 0.14 + t*flight_h; var sz := z_bot - t*run_len
				_box("Tread", Vector3(sx, sy, sz), Vector3(2.5, 0.14, step_run*0.9), walnut, false, null, 0.48)
				_box("Tread LED", Vector3(sx, sy - 0.08, sz), Vector3(2.3, 0.012, step_run*0.5), warm, false, null, 0.2, 0.0, false, warm)
			# Frameless glass railing + matte-black handrail
			for side in [-1.32, 1.32]:
				var gp := _box("Glass bal", Vector3(sx + side, fy + 0.88 + flight_h*0.5, z_mid), Vector3(0.03, 0.95, ramp_len*0.96), glass, false, null, 0.06, 0.02, true)
				gp.rotation.x = -slope
				var hr := _box("Handrail", Vector3(sx + side, fy + 1.35 + flight_h*0.5, z_mid), Vector3(0.08, 0.065, ramp_len+0.12), matte, false, null, 0.35, 0.38)
				hr.rotation.x = -slope
			_painted_text(str(sc["dir"]) + "  KE " + str(link["to"]), Vector3(sx, fy + 1.95, z_bot+0.18), 0.0, 0.0023, Color("#243530"), Color("#f2ecda"))
	# Under-stair L1: planter box, white pebbles, Snake Plant feel, uplight (open under floating treads)
	var ug_z := 10.5
	_box("Under-stair planter", Vector3(cx - 1.1, L1_Y + 0.18, ug_z), Vector3(5.8, 0.34, 5.4), Color("#3a3f3c"), false, null, 0.55)
	_box("Pebble bed", Vector3(cx - 1.1, L1_Y + 0.36, ug_z), Vector3(5.4, 0.06, 5.0), Color("#f0efe8"), false, null, 0.95)
	_add_plant(Vector3(cx - 2.6, L1_Y + 0.36, ug_z - 1.4), 0.8)
	_add_plant(Vector3(cx - 0.8, L1_Y + 0.36, ug_z + 0.6), 0.75)
	_add_plant(Vector3(cx + 0.8, L1_Y + 0.36, ug_z - 0.8), 0.78)
	_box("Planter uplight", Vector3(cx - 1.1, L1_Y + 0.42, ug_z), Vector3(0.5, 0.03, 0.2), warm, false, null, 0.2, 0.0, false, warm)
	# --- Panoramic smoked-glass lift (black steel frame, cyan indicators), full height ---
	var shaft_h := FLOOR_H * 3.0 + 2.0
	_box("Lift shaft frame", Vector3(lx, shaft_h*0.5 - 0.1, cz-0.9), Vector3(2.9, shaft_h, 2.7), matte, true, null, 0.4, 0.3)
	_box("Lift shaft glass", Vector3(lx, shaft_h*0.5, cz-2.27), Vector3(2.6, shaft_h-0.5, 0.07), Color(0.28,0.30,0.34,0.22), false, null, 0.06, 0.04, true)
	for fi in range(fys.size()):
		var fy: float = fys[fi]
		_box("Lift landing", Vector3(lx, fy + 0.07, cz+0.35), Vector3(2.7, 0.14, 2.3), marble, true, null, 0.42)
		_box("Lift interior", Vector3(lx, fy + 1.45, cz-0.85), Vector3(2.3, 2.7, 2.2), Color("#e6ece8"), false)
		_box("Lift door frame", Vector3(lx, fy + 1.45, cz-2.18), Vector3(2.45, 2.8, 0.10), matte, false, null, 0.3, 0.35)
		_box("Lift door L", Vector3(lx-0.5, fy + 1.35, cz-2.25), Vector3(0.9, 2.4, 0.07), Color(0.36,0.40,0.46,0.26), false, null, 0.08, 0.06, true)
		_box("Lift door R", Vector3(lx+0.5, fy + 1.35, cz-2.25), Vector3(0.9, 2.4, 0.07), Color(0.36,0.40,0.46,0.26), false, null, 0.08, 0.06, true)
		_box("Lift indicator", Vector3(lx, fy + 2.78, cz-2.33), Vector3(0.90, 0.34, 0.04), Color("#0c1412"), false, null, 0.2, 0.0, false, cyan)
		_painted_text(labels[fi] + "  ↑↓", Vector3(lx, fy + 2.78, cz-2.36), 0.0, 0.0024, Color("#eaffff"), Color(0,0,0,0))
		_box("Lift panel", Vector3(lx-1.28, fy + 1.38, cz-2.33), Vector3(0.26, 0.66, 0.05), Color("#1f2326"), false)
		_box("Lift up", Vector3(lx-1.28, fy + 1.56, cz-2.36), Vector3(0.12, 0.12, 0.03), cyan, false, null, 0.3, 0.0, false, cyan)
		_box("Lift down", Vector3(lx-1.28, fy + 1.24, cz-2.36), Vector3(0.12, 0.12, 0.03), Color("#5a6662"), false)
		_painted_text("LIFT", Vector3(lx, fy + 0.45, cz-2.40), 0.0, 0.0026, Color("#243530"), Color("#f2ecda"))
		_painted_text(labels[fi], Vector3(0, fy + 3.25, 17.55), 0.0, 0.0065, Color("#2f4339"), Color(0,0,0,0))
	_box("Lift machine cap", Vector3(lx, L3_Y + FLOOR_H + 1.2, cz-0.9), Vector3(3.0, 1.2, 2.8), Color("#4a5552"), false, null, 0.5, 0.2)

func _add_wall_clock(position: Vector3, yaw: float = 0.0) -> void:
	var root := Node3D.new()
	root.name = "WallClock"
	root.position = position + Vector3(0, _floor_y, 0)
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
	var root := Node3D.new()
	root.name = "FramedPoster"
	root.position = position + Vector3(0, _floor_y, 0)
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


	# Petunjuk arah ruangan (wayfinding) per lantai — visual only
	_build_wayfinding()

func _build_wayfinding() -> void:
	# Sleek dark-acrylic directory totems per floor (micro-detail signage).
	var _fys := [{"y":L1_Y,"f":"L1"},{"y":L2_Y,"f":"L2"},{"y":L3_Y,"f":"L3"}]
	for fl in _fys:
		var fy: float = float(fl["y"]); var fn := str(fl["f"])
		_box("Dir post "+fn, Vector3(0, fy+0.85, 8.5), Vector3(0.10,1.7,0.10), Color("#2a3034"), true, null, 0.3, 0.45)
		_box("Dir board "+fn, Vector3(0, fy+1.55, 8.58), Vector3(3.3,1.25,0.07), Color("#14181b"), false, null, 0.22, 0.5)
		_box("Dir glow "+fn, Vector3(0, fy+1.0, 8.62), Vector3(3.0,0.02,0.02), Color("#2aa8c8"), false, null, 0.2, 0.0, false, Color("#38c8e8"))
		_painted_text("DIRECTORY " + fn, Vector3(0, fy+2.02, 8.63), 0.0, 0.0022, Color("#dff8ff"), Color(0,0,0,0))
	if true:
		var fy1 := L1_Y
		_painted_text("L1  →  LOBI · RESEPSIONIS · BOARDROOM · LAB API · ARSIP · PANTRY", Vector3(0, fy1+1.55, 8.64), 0.0, 0.0025, Color("#f2ecda"), Color(0,0,0,0))
		_painted_text("← ARSIP & CETAK", Vector3(-10.5, fy1+1.15, 24.85), 0.0, 0.0032, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("RUANG RAPAT / BOARDROOM →", Vector3(-18.8, fy1+1.15, 14.2), -PI*0.5, 0.0030, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("PANTRY & LOUNGE →", Vector3(10.5, fy1+1.15, 24.85), 0.0, 0.0032, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("← LAB API & INFRA", Vector3(18.8, fy1+1.15, 14.2), -PI*0.5, 0.0030, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("↑ TANGGA & LIFT KE LANTAI 2/3", Vector3(6.5, fy1+1.15, 12.2), 0.0, 0.0032, Color("#2f4339"), Color(0,0,0,0))
		var fy2 := L2_Y
		_painted_text("L2  →  SEKRETARIAT · MANAJEMEN · ARSITEKTUR · FRONTEND · QA · BACKEND", Vector3(0, fy2+1.55, 8.64), 0.0, 0.0024, Color("#f2ecda"), Color(0,0,0,0))
		_painted_text("← SEKRETARIAT / OWNER ACCESS", Vector3(-10.5, fy2+1.15, -19.8), PI, 0.0030, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("MANAJEMEN & ARSITEKTUR ->", Vector3(10.5, fy2+1.15, -19.8), PI, 0.0030, Color("#2f4339"), Color(0,0,0,0))
		# Kanban board on L2 corridor (visual)
		_box("Corridor kanban frame", Vector3(6.2, L2_Y + 1.85, 3.86), Vector3(3.8, 1.6, 0.08), Color("#2a3034"), false, null, 0.35, 0.3)
		_box("Corridor kanban", Vector3(6.2, L2_Y + 1.85, 3.91), Vector3(3.6, 1.42, 0.03), Color("#e6e2d6"), false, null, 0.7)
		for kx in [5.1, 6.2, 7.3]:
			for ky in [2.2, 1.75, 1.35]:
				_box("Kanban note", Vector3(kx, L2_Y + ky, 3.94), Vector3(0.85, 0.32, 0.02), Color("#f2e6b8") if ky > 1.8 else Color("#cfe3d6"), false, null, 0.85)
		_painted_text("KANBAN", Vector3(6.2, L2_Y + 2.55, 3.95), PI, 0.0026, Color("#2f4339"), Color(0,0,0,0))
		var fy3 := L3_Y
		_painted_text("L3  ->  RUANG OWNER · SUITE OWNER · LOUNGE PRIBADI", Vector3(0, fy3+1.55, 8.64), 0.0, 0.0026, Color("#f2ecda"), Color(0,0,0,0))
		_painted_text("<- RUANG OWNER", Vector3(-10.5, fy3+1.15, -19.8), PI, 0.0034, Color("#2f4339"), Color(0,0,0,0))
		_painted_text("LOUNGE PRIBADI ->", Vector3(-1.2, fy3+1.15, 29.5), -PI*0.5, 0.0032, Color("#2f4339"), Color(0,0,0,0))

func _build_landscape() -> void:
	# Entry landscaping: concrete planter boxes + shrubs/low lights + paving feel (visual).
	var pcon := Color("#b7bdb6"); var soil := Color("#5a4a3a")
	for side in [-1.0, 1.0]:
		var sidef := float(side)
		var px := 13.2 * sidef
		_box("Planter box", Vector3(px, 0.34, 44.6), Vector3(6.2, 0.52, 2.1), pcon, false, null, 0.55)
		_box("Planter soil", Vector3(px, 0.62, 44.6), Vector3(5.8, 0.06, 1.7), soil, false, null, 0.9)
		for ox in [-2.0, -0.6, 0.8, 2.2]:
			_add_plant(Vector3(px + float(ox), 0.62, 44.6), 0.55)
		# low bollard/garden light
		_cylinder("Garden light", Vector3(px + sidef * 3.6, 0.28, 45.9), 0.06, 0.56, Color("#4a5550"), null, false, 0.4)
		_box("Garden light cap", Vector3(px + sidef * 3.6, 0.58, 45.9), Vector3(0.16, 0.06, 0.16), Color("#f2e6c8"), false, null, 0.2, 0.0, false, Color("#ffe8b8"))
	# Paving grid on HQ front walk
	for gx in range(-7, 8, 2):
		for gz in range(0, 6):
			_box("Paver", Vector3(float(gx)*1.05, 0.012, 41.2 + float(gz)*1.25), Vector3(1.9, 0.012, 1.1), Color("#c6cec3") if (gx+gz)%2==0 else Color("#bcc6bc"), false, null, 0.72)
	_box("Outdoor company monument", Vector3(-24.0, 1.55, 42.3), Vector3(7.4, 3.1, 0.72), Color("#42584c"), false)
	_box("Outdoor monument fascia", Vector3(-24.0, 2.75, 41.86), Vector3(7.4, 2.0, 0.09), Color("#33453c"), false)
	_box("Monument banner", Vector3(-24.0, 2.45, 41.7), Vector3(6.2, 1.35, 0.06), Color("#f4f0e4"), false, null, 0.55)
	_painted_text("BANGKAH", Vector3(-24.0, 2.65, 41.75), 0.0, 0.011, Color("#2f4339"), Color(0,0,0,0))
	_painted_text("HEADQUARTERS", Vector3(-24.0, 2.15, 41.75), 0.0, 0.0048, Color("#3f574c"), Color(0,0,0,0))
	
	for x in [-35.0, 35.0]:
		_cylinder("Flag pole", Vector3(x, 2.5, 44.0), 0.055, 5.0, Color("#b7c0ba"), null, false, 0.7)
		_box("Company flag", Vector3(x + 0.72, 4.15, 44.0), Vector3(1.45, 0.82, 0.055), Color("#567f6a"), false)
	# HQ perimeter trees — positions collected for MultiMesh (draw-call reduction)
	var _hq_tree_pos: Array[Vector3] = [Vector3(-46,0,25), Vector3(-48,0,0), Vector3(-46,0,-28), Vector3(47,0,24), Vector3(48,0,-4), Vector3(46,0,-30), Vector3(-32,0,60), Vector3(32,0,60)]
	_trees_pending = _hq_tree_pos
	_box("Outdoor bench seat", Vector3(20, 0.52, 46.5), Vector3(3.2, 0.18, 0.7), Color("#92785c"), false)
	_box("Outdoor bench back", Vector3(20, 0.96, 46.2), Vector3(3.2, 0.7, 0.14), Color("#92785c"), false)
	for x in [18.8, 21.2]:
		_box("Bench leg", Vector3(x, 0.25, 46.5), Vector3(0.13, 0.5, 0.13), Color("#52635b"), false)

func _add_tree(position: Vector3) -> void:
	_cylinder("Tree trunk", position + Vector3(0, 1.15, 0), 0.24, 2.3, Color("#735b45"))
	_sphere("Tree canopy", position + Vector3(0, 2.55, 0), 1.5, Color("#668b6d"), Vector3(1.05, 1.0, 1.05))
	_sphere("Tree canopy detail", position + Vector3(0.72, 2.85, -0.22), 0.9, Color("#83a27b"), Vector3(1.1, 0.9, 0.95))
	_sphere("Tree canopy detail", position + Vector3(-0.68, 2.78, 0.16), 0.84, Color("#779975"), Vector3(1.0, 0.94, 1.0))
## Parkir perusahaan: slot bernama per karyawan, mobil prosedural, dan lampu.
func _build_company_parking() -> void:
	var assignments := [
		{"id":"lead","name":"Arman","x":22.0,"z":47.0,"body":Color("#4a6a82")},
		{"id":"coo","name":"Sinta","x":26.4,"z":47.0,"body":Color("#8b6a72")},
		{"id":"architect","name":"Raka","x":30.8,"z":47.0,"body":Color("#5a7a6a")},
		{"id":"backend","name":"Bima","x":35.2,"z":47.0,"body":Color("#6a7288")},
		{"id":"api","name":"Naya","x":22.0,"z":47.0,"body":Color("#8a7a5a")},
		{"id":"frontend","name":"Dira","x":26.4,"z":47.0,"body":Color("#7a5f52")},
		{"id":"qa","name":"Tika","x":30.8,"z":47.0,"body":Color("#5f7a6a")},
	]
	# Signage (tali air / painted)
	_box("Parking sign post", Vector3(18.2, 1.1, 43.2), Vector3(0.14, 2.2, 0.14), Color("#5a6862"), false, null, 0.5)
	_box("Parking sign face", Vector3(18.9, 1.45, 43.2), Vector3(1.9, 0.85, 0.08), Color("#2f4339"), false, null, 0.4, 0.1)
	_painted_text("PARKIR HQ", Vector3(18.95, 1.55, 43.25), -PI*0.5, 0.0038, Color("#e8dfc4"), Color(0,0,0,0))
	_painted_text("KARYAWAN", Vector3(18.95, 1.28, 43.25), -PI*0.5, 0.0026, Color("#d8e6d6"), Color(0,0,0,0))
	# Wheel stops / bay markers + drivable cars
	for i in range(assignments.size()):
		var a: Dictionary = assignments[i]
		var car_pos := Vector3(float(a["x"]), 0.0, float(a["z"]))
		var eid := str(a.get("id", ""))
		_box("Wheel stop", car_pos + Vector3(0, 0.08, -3.6), Vector3(2.2, 0.14, 0.22), Color("#d8cfa8"), false, null, 0.6)
		_add_parked_car(car_pos, 0.0, a["body"], str(a["name"]), "car_" + eid, true, "Mobil " + str(a["name"]))
		_painted_text(str(a["name"]).to_upper(), car_pos + Vector3(0, 0.03, -4.35), 0.0, 0.0032, Color("#f3f1e8"), Color(0.1,0.12,0.1,0.2))
	# Lights (visual) — poles/heads via MultiMesh; actual parking lights kept sparse in town lamps
	# (HQ parking lamp positions added to town multimesh)




func _add_parked_car(position: Vector3, yaw: float, body: Color, _label_text: String = "", car_id: String = "", drivable: bool = false, car_label: String = "") -> Node3D:
	var root := Node3D.new()
	root.name = "ParkedCar"
	root.position = position
	root.rotation.y = yaw
	add_child(root)
	var dark := body.darkened(0.18)
	var trim := Color("#2c3338")
	var chrome := Color("#aeb8bb")
	# Chassis / body (layered for a more realistic silhouette)
	_box("Car chassis", Vector3(0, 0.38, 0), Vector3(2.02, 0.22, 4.45), trim, true, root, 0.55, 0.25)
	_box("Car body lower", Vector3(0, 0.56, 0), Vector3(2.12, 0.34, 4.38), body, true, root, 0.36, 0.22)
	_box("Car hood", Vector3(0, 0.72, 1.25), Vector3(1.98, 0.18, 1.65), body.lightened(0.04), false, root, 0.32, 0.2)
	_box("Car trunk", Vector3(0, 0.72, -1.35), Vector3(1.98, 0.18, 1.45), dark, false, root, 0.34, 0.18)
	_box("Car cabin", Vector3(0, 1.04, -0.12), Vector3(1.82, 0.56, 1.95), body.lightened(0.06), false, root, 0.34, 0.16)
	_box("Roof", Vector3(0, 1.34, -0.18), Vector3(1.78, 0.08, 1.75), dark, false, root, 0.4, 0.12)
	# Glass
	var glass := Color(0.38, 0.55, 0.62, 0.30)
	_box("Windshield", Vector3(0, 1.04, 0.78), Vector3(1.62, 0.46, 0.06), glass, false, root, 0.08, 0.05, true)
	_box("Rear glass", Vector3(0, 1.04, -1.06), Vector3(1.52, 0.40, 0.06), glass, false, root, 0.08, 0.05, true)
	_box("Side glass L", Vector3(-0.92, 1.04, -0.12), Vector3(0.05, 0.38, 1.45), glass, false, root, 0.08, 0.05, true)
	_box("Side glass R", Vector3(0.92, 1.04, -0.12), Vector3(0.05, 0.38, 1.45), glass, false, root, 0.08, 0.05, true)
	# Bumpers, grille, plates
	_box("Front bumper", Vector3(0, 0.42, 2.18), Vector3(2.06, 0.20, 0.18), trim, false, root, 0.5, 0.2)
	_box("Rear bumper", Vector3(0, 0.42, -2.18), Vector3(2.06, 0.20, 0.18), trim, false, root, 0.5, 0.2)
	_box("Grille", Vector3(0, 0.56, 2.16), Vector3(1.0, 0.22, 0.05), Color("#1f2528"), false, root, 0.7, 0.1)
	_box("Plate front", Vector3(0, 0.38, 2.28), Vector3(0.52, 0.14, 0.03), Color("#eef0e6"), false, root, 0.6)
	_box("Plate rear", Vector3(0, 0.40, -2.28), Vector3(0.52, 0.14, 0.03), Color("#eef0e6"), false, root, 0.6)
	# Mirrors & handles (detail)
	_box("Mirror L", Vector3(-1.08, 1.0, 0.55), Vector3(0.14, 0.10, 0.18), dark, false, root, 0.35, 0.25)
	_box("Mirror R", Vector3(1.08, 1.0, 0.55), Vector3(0.14, 0.10, 0.18), dark, false, root, 0.35, 0.25)
	_box("Handle L", Vector3(-1.06, 0.86, -0.05), Vector3(0.04, 0.05, 0.22), chrome, false, root, 0.2, 0.75)
	_box("Handle R", Vector3(1.06, 0.86, -0.05), Vector3(0.04, 0.05, 0.22), chrome, false, root, 0.2, 0.75)
	# Wheels + arches (proper orientation: axle along X, wheel rotates around X when rolling)
	for wx in [-0.86, 0.86]:
		for wz in [-1.28, 1.28]:
			_box("Wheel arch", Vector3(wx, 0.52, wz), Vector3(0.30, 0.22, 0.64), dark, false, root, 0.5, 0.1)
			var wheel := Node3D.new()
			wheel.name = "Wheel"
			wheel.position = Vector3(wx, 0.29, wz)
			root.add_child(wheel)
			# CylinderMesh default axis is Y; rotate 90deg around Z to align axle to X.
			for part in [
				{"n":"Tire", "r":0.30, "h":0.24, "c":Color("#1e2226"), "rough":0.95, "met":0.0},
				{"n":"Rim", "r":0.19, "h":0.26, "c":chrome, "rough":0.25, "met":0.78},
				{"n":"Hub", "r":0.08, "h":0.28, "c":trim, "rough":0.35, "met":0.4},
			]:
				var wn := Node3D.new(); wn.name = str(part["n"]); wn.position.y = 0.0
				wn.rotation.z = PI * 0.5
				wheel.add_child(wn)
				var wm := MeshInstance3D.new()
				var wc := CylinderMesh.new(); wc.top_radius = float(part["r"]); wc.bottom_radius = float(part["r"]); wc.height = float(part["h"])
				wm.mesh = wc
				wm.material_override = _mat(part["c"], float(part["rough"]), float(part["met"]))
				wn.add_child(wm)
	# Lights
	_box("Headlight L", Vector3(-0.62, 0.62, 2.16), Vector3(0.42, 0.18, 0.05), Color("#f6efd6"), false, root, 0.15, 0.0, false, Color("#fff2c8"))
	_box("Headlight R", Vector3(0.62, 0.62, 2.16), Vector3(0.42, 0.18, 0.05), Color("#f6efd6"), false, root, 0.15, 0.0, false, Color("#fff2c8"))
	_box("DRL L", Vector3(-0.88, 0.62, 2.14), Vector3(0.10, 0.14, 0.04), Color("#e8f4ff"), false, root, 0.2, 0.0, false, Color("#d8ecff"))
	_box("DRL R", Vector3(0.88, 0.62, 2.14), Vector3(0.10, 0.14, 0.04), Color("#e8f4ff"), false, root, 0.2, 0.0, false, Color("#d8ecff"))
	_box("Taillight L", Vector3(-0.66, 0.66, -2.16), Vector3(0.40, 0.16, 0.05), Color("#c45a52"), false, root, 0.22, 0.0, false, Color("#c04840"))
	_box("Taillight R", Vector3(0.66, 0.66, -2.16), Vector3(0.40, 0.16, 0.05), Color("#c45a52"), false, root, 0.22, 0.0, false, Color("#c04840"))
	if drivable and not car_id.is_empty():
		vehicles.append({"id": car_id, "label": car_label if not car_label.is_empty() else car_id, "position": position, "yaw": yaw, "color": body, "kind": "car", "node": root})
	return root

## Distrik kota kecil: setiap karyawan punya rumah + mobil di carport. Rumah
## adalah geometri prosedural (visual); tidak mengubah state backend.
func _build_town_district() -> void:
	# Tidy city signage (clear, aligned to grid) — roads/connectivity unchanged.
	_add_road_sign(Vector3(56.0, 0, 49.8), 0.0, "KOTA BANGKAH", "← HQ  |  PERUMAHAN →", Color("#2f4339"), Color("#f2f1ea"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 3.0, 0, 12.0), -PI * 0.5, "PERUMAHAN", "RUMAH KARYAWAN", Color("#3f574c"), Color("#efe7d2"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 3.0, 0, 78.0), -PI * 0.5, "PASAR KOTA", "BELANJA SEGAR / JAJAN", Color("#7a5a46"), Color("#f4ead2"))
	var kc: Vector3 = kopdes_layout().get("center", TOWN_ORIGIN + Vector3(46, 0, 58))
	_add_road_sign(Vector3(kc.x, 0, 49.8), 0.0, "KOPDES MALL", "PUSAT BELANJA ↓", Color("#3a3a38"), Color("#f2f1ea"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x - 30.0, 0, 50.0), PI * 0.5, "KOPDES MERAH PUTIH", "LANDMARK LOKAL", Color("#3a3a38"), Color("#f2f1ea"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x - 30.0, 0, 70.0), PI * 0.5, "KOPDES UNIT", "ATM / LAYANAN CEPAT", Color("#3a3a38"), Color("#f2f1ea"))
	var ml: Dictionary = owner_mansion_layout()
	var mbase: Vector3 = ml.get("base", TOWN_ORIGIN + Vector3(44, 0, -10))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 22.0, 0, mbase.z + 9.0), 0.0, "RUMAH OWNER", "MANSION →", Color("#4f5f78"), Color("#f3e8c8"))
	_add_road_sign(Vector3(38.0, 0, 49.8), 0.0, "PARKIR HQ", "KARYAWAN & TAMU", Color("#4a5a52"), Color("#f2f1ea"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 16.8, 0, 49.2), PI * 0.5, "JL. BANGKAH", "UTARA: PERUMAHAN  SELATAN: HQ", Color("#2f4339"), Color("#f2f1ea"))
	for zc in [18.0, 40.0, 62.0, 84.0]:
		var rz: float = TOWN_ORIGIN.z + float(zc)
		_add_road_sign(Vector3(TOWN_ORIGIN.x + 16.5, 0, rz - 3.0), PI * 0.5, "BLOK RUMAH", "← BARAT  |  TIMUR →", Color("#3f574c"), Color("#eef1ea"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 16.5, 0, TOWN_ORIGIN.z + 88.5), PI * 0.5, "PUSAT KOTA", "PASAR →", Color("#7a5a46"), Color("#f4ead2"))
	_add_road_sign(Vector3(TOWN_ORIGIN.x + 38.0, 0, TOWN_ORIGIN.z + 88.5), 0.0, "PASAR", "KIOS & JAJANAN", Color("#7a5a46"), Color("#f4ead2"))
	# Street lamps (MultiMesh). HQ perimeter trees via _trees_pending.
	var _lamp_pos: Array[Vector3] = []
	for i in range(11):
		_lamp_pos.append(Vector3(TOWN_ORIGIN.x + 16.8, 0.0, 6.0 + float(i) * 9.5))
	for lp in [market_layout().get("center", TOWN_ORIGIN) + Vector3(-10, 0, -8), market_layout().get("center", TOWN_ORIGIN) + Vector3(10, 0, -8), kc + Vector3(-10, 0, 22), kc + Vector3(10, 0, 22), mbase + Vector3(-4, 0, 14)]:
		_lamp_pos.append(Vector3(lp.x, 0.0, lp.z))
	for px in [24.2, 33.0]:
		_lamp_pos.append(Vector3(px, 0.0, 42.0))
	var _mkt_c: Vector3 = market_layout().get("center", TOWN_ORIGIN + Vector3(28, 0, 92))
	for lp in [Vector3(float(_mkt_c.x) - 8.0, 0.0, float(_mkt_c.z) - 6.5), Vector3(float(_mkt_c.x) + 8.0, 0.0, float(_mkt_c.z) - 6.5)]:
		_lamp_pos.append(lp)
	_add_street_lamp_multimesh(_lamp_pos)
	_add_tree_multimesh(_trees_pending)


	var homes := [
		{"id":"lead", "name":"Arman", "offset": Vector2(0, 0), "wall": Color("#d8d2c4"), "roof": Color("#7a5a48"), "door": Color("#5f7a68"), "car": Color("#4a6a82")},
		{"id":"coo", "name":"Sinta", "offset": Vector2(24, 0), "wall": Color("#e0d8cc"), "roof": Color("#6f5f74"), "door": Color("#7a6658"), "car": Color("#8b6a72")},
		{"id":"architect", "name":"Raka", "offset": Vector2(0, 22), "wall": Color("#d4dcd6"), "roof": Color("#546a74"), "door": Color("#5a6e62"), "car": Color("#5a7a6a")},
		{"id":"backend", "name":"Bima", "offset": Vector2(24, 22), "wall": Color("#ddd6c8"), "roof": Color("#6a5f54"), "door": Color("#4f675d"), "car": Color("#6a7288")},
		{"id":"api", "name":"Naya", "offset": Vector2(0, 44), "wall": Color("#d9ddd2"), "roof": Color("#7a6a52"), "door": Color("#6b775e"), "car": Color("#8a7a5a")},
		{"id":"frontend", "name":"Dira", "offset": Vector2(24, 44), "wall": Color("#e2d6c8"), "roof": Color("#8a624f"), "door": Color("#6a5a6a"), "car": Color("#7a5f52")},
		{"id":"qa", "name":"Tika", "offset": Vector2(12, 66), "wall": Color("#d6dfd8"), "roof": Color("#5f7468"), "door": Color("#5f6f7a"), "car": Color("#5f7a6a")},
	]
	for h in homes:
		var base := TOWN_ORIGIN + Vector3(h["offset"].x, 0, h["offset"].y)
		_build_house(base, str(h["id"]), str(h["name"]), h["wall"], h["roof"], h["door"], h["car"])

	# Street props + curb-parked cars (non-drivable visual density; keeps roads navigable)
	_add_street_props()

	# Owner's mansion (paling besar & mewah) + market/Kopdes — all in one connected city.
	_build_owner_mansion()
	_build_market()
	_build_kopdes_merah_putih()
	_build_kopdes_unit()
	_build_grand_mall()

func _add_road_sign(pos: Vector3, yaw: float, title: String, subtitle: String, head: Color, board: Color) -> void:
	var root := Node3D.new()
	root.name = "RoadSign"
	root.position = pos
	root.rotation.y = yaw
	add_child(root)
	_cylinder("Sign post L", Vector3(-1.25, 1.45, 0), 0.07, 2.9, Color("#6a776f"), root)
	_cylinder("Sign post R", Vector3(1.25, 1.45, 0), 0.07, 2.9, Color("#6a776f"), root)
	_box("Sign board", Vector3(0, 2.55, 0), Vector3(3.4, 1.35, 0.10), board, false, root, 0.42)
	_box("Sign head", Vector3(0, 3.05, 0.04), Vector3(3.4, 0.38, 0.05), head, false, root, 0.35)
	_box("Sign border", Vector3(0, 2.55, 0.055), Vector3(3.34, 1.29, 0.01), head.darkened(0.15), false, root, 0.5)
	# Flat painted text (tali air style) — facing forward on the board
	_painted_text(title, Vector3(0, 2.68, 0.07), 0.0, 0.0036, Color("#1f2c27"), Color(0,0,0,0), root)
	_painted_text(subtitle, Vector3(0, 2.26, 0.07), 0.0, 0.0023, Color("#2f3f38"), Color(0,0,0,0), root)


func _build_house(base: Vector3, employee_id: String, employee_name: String, wall: Color, roof: Color, door: Color, car: Color) -> void:
	var root := Node3D.new()
	root.name = "House_%s" % employee_id
	root.position = base
	add_child(root)
	# Lot, path, fence hint.
	_box("House lot", Vector3(6.0, -0.04, 5.0), Vector3(16.5, 0.08, 14.5), Color("#8ca087"), true, root, 0.92)
	_box("House path", Vector3(2.2, -0.03, 8.2), Vector3(1.8, 0.06, 4.2), Color("#c3ccbf"), true, root, 0.68)
	# Main volume + porch roof.
	_box("House body", Vector3(6.0, 1.75, 4.2), Vector3(9.4, 3.5, 7.8), wall, true, root, 0.84)
	_box("House roof", Vector3(6.0, 3.72, 4.2), Vector3(10.2, 0.55, 8.6), roof, false, root, 0.68)
	_box("House trim", Vector3(6.0, 3.48, 8.12), Vector3(9.5, 0.12, 0.12), roof.darkened(0.12), false, root, 0.5)
	_box("Roof ridge", Vector3(6.0, 4.12, 4.2), Vector3(10.4, 0.18, 0.55), roof.darkened(0.08), false, root, 0.65)
	_box("Porch roof", Vector3(2.4, 2.55, 7.1), Vector3(3.2, 0.18, 2.2), roof.lightened(0.05), false, root, 0.68)
	_cylinder("Porch post L", Vector3(1.1, 1.25, 8.0), 0.07, 2.4, Color("#d8d2c6"), root)
	_cylinder("Porch post R", Vector3(3.7, 1.25, 8.0), 0.07, 2.4, Color("#d8d2c6"), root)
	# Enterable doorway: build wall segments around a real opening (player can enter).
	var d_c := 2.2
	var d_w := 1.25
	var front_z := 8.1
	var wall_left := 1.3
	var wall_right := 10.7
	var left_end := d_c - d_w * 0.5
	var right_start := d_c + d_w * 0.5
	_box("Front wall L", Vector3((wall_left + left_end) * 0.5, 1.75, front_z), Vector3(maxf(0.1, left_end - wall_left), 3.5, 0.18), wall, true, root, 0.84)
	_box("Front wall R", Vector3((right_start + wall_right) * 0.5, 1.75, front_z), Vector3(maxf(0.1, wall_right - right_start), 3.5, 0.18), wall, true, root, 0.84)
	_box("Front wall top", Vector3(d_c, 2.95, front_z), Vector3(d_w + 0.2, 1.1, 0.18), wall, true, root, 0.84)
	_box("Door frame", Vector3(d_c, 1.25, front_z + 0.02), Vector3(d_w + 0.14, 2.45, 0.08), Color("#6b5a4a"), false, root, 0.5)
	_box("Front door", Vector3(d_c, 1.25, front_z + 0.08), Vector3(1.05, 2.35, 0.1), door, false, root, 0.45)
	_box("Door window", Vector3(d_c, 1.75, front_z + 0.14), Vector3(0.55, 0.7, 0.04), Color(0.55, 0.7, 0.74, 0.35), false, root, 0.14, 0.05, true)
	# Interior (enterable) — warmer, clearer layout.
	_box("Interior floor", Vector3(6.0, -0.03, 4.2), Vector3(8.8, 0.06, 7.2), Color("#d6cdbb"), true, root, 0.68)
	_box("Interior rug", Vector3(6.0, 0.015, 4.8), Vector3(4.6, 0.03, 3.0), Color("#7f8f86"), false, root, 0.82)
	_box("Back wall paint", Vector3(6.0, 1.75, 0.55), Vector3(8.8, 3.5, 0.08), wall.lightened(0.06), false, root, 0.85)
	_box("Sofa", Vector3(6.0, 0.46, 2.1), Vector3(3.4, 0.92, 1.15), Color("#6f827c"), true, root, 0.74)
	_box("Sofa arm L", Vector3(4.45, 0.56, 2.1), Vector3(0.3, 0.72, 1.15), Color("#687a74"), true, root, 0.74)
	_box("Sofa arm R", Vector3(7.55, 0.56, 2.1), Vector3(0.3, 0.72, 1.15), Color("#687a74"), true, root, 0.74)
	_box("Coffee table", Vector3(6.0, 0.4, 3.55), Vector3(1.7, 0.42, 0.95), Color("#8a6746"), true, root, 0.58, 0.08)
	_box("Shelf", Vector3(9.55, 1.05, 2.3), Vector3(0.95, 2.1, 2.4), Color("#c2b08c"), true, root, 0.7)
	_box("Wall frame", Vector3(3.2, 2.0, 0.62), Vector3(1.4, 1.0, 0.05), Color("#d8c49a"), false, root, 0.5)
	_painted_text("RUMAH", Vector3(3.2, 2.0, 0.66), 0.0, 0.0028, Color("#5a4a3a"), Color(0,0,0,0), root)
	var il := OmniLight3D.new()
	il.position = base + Vector3(6.0, 2.6, 4.2)
	il.light_color = Color("#ffe8c8")
	il.light_energy = 0.18
	il.omni_range = 6.5
	il.shadow_enabled = false
	add_child(il)
	for wx in [5.2, 8.4]:
		_box("Window frame", Vector3(wx, 2.1, front_z + 0.02), Vector3(1.7, 1.35, 0.12), Color("#eef1ea"), false, root, 0.52)
		_box("Window glass", Vector3(wx, 2.1, front_z + 0.08), Vector3(1.45, 1.1, 0.05), Color(0.52, 0.68, 0.72, 0.28), false, root, 0.12, 0.08, true)
	_box("Side window", Vector3(10.72, 2.0, 4.2), Vector3(0.12, 1.2, 1.6), Color("#eef1ea"), false, root, 0.52)
	_box("Side glass", Vector3(10.78, 2.0, 4.2), Vector3(0.05, 1.0, 1.35), Color(0.52, 0.68, 0.72, 0.28), false, root, 0.12, 0.08, true)
	# Nameplate and small garden.
	_box("Nameplate", Vector3(3.35, 1.55, front_z + 0.06), Vector3(1.1, 0.38, 0.05), Color("#f2ead8"), false, root, 0.5)
	_painted_text(employee_name.to_upper(), Vector3(3.35, 1.55, front_z + 0.095), 0.0, 0.0034, Color("#2f4339"), Color(0,0,0,0), root)
	_add_plant(base + Vector3(0.4, 0, 5.2), 0.75)
	_add_plant(base + Vector3(9.8, 0, 8.8), 0.7)
	# Carport + employee car (visual commute prop).
	_box("Carport slab", Vector3(12.8, -0.04, 9.8), Vector3(4.6, 0.08, 6.2), Color("#aab5ad"), true, root, 0.7)
	_box("Carport roof", Vector3(12.8, 2.45, 9.8), Vector3(4.9, 0.16, 6.5), roof.darkened(0.05), false, root, 0.65)
	for px in [10.9, 14.7]:
		for pz in [7.1, 12.5]:
			_cylinder("Carport post", Vector3(px, 1.22, pz), 0.06, 2.35, Color("#d0ccc2"), root)
	_add_parked_car(base + Vector3(12.8, 0, 9.8), 0.0, car, employee_name, "car_home_" + employee_id, true, "Mobil " + employee_name)
	# Warm porch light.
	_box("Porch light", Vector3(1.35, 2.1, front_z + 0.08), Vector3(0.18, 0.26, 0.1), Color("#e8d6a8"), false, root, 0.22, 0.1, false, Color("#f4dca0"))
	var porch := OmniLight3D.new()
	porch.position = base + Vector3(1.35, 2.1, front_z + 0.8)
	porch.light_color = Color("#ffe6b8")
	porch.light_energy = 0.14
	porch.omni_range = 3.8
	porch.shadow_enabled = false
	add_child(porch)

## Rumah Owner: paling besar & mewah (visual). Player bisa bertamu/berinteraksi.
func _build_owner_mansion() -> void:
	var layout: Dictionary = owner_mansion_layout()
	var base: Vector3 = layout.get("base", TOWN_ORIGIN + Vector3(44, 0, -10))
	var root := Node3D.new()
	root.name = "OwnerMansion"
	root.position = base
	add_child(root)
	var wall := Color("#efe6d6")
	var roof := Color("#4f5f78")
	var trim := Color("#d6c48a")
	_box("Estate lot", Vector3(0, -0.04, 2.0), Vector3(28.0, 0.08, 24.0), Color("#8ea58c"), true, root, 0.9)
	_box("Driveway", Vector3(-7.5, -0.035, 8.5), Vector3(5.2, 0.07, 11.5), Color("#b8c1b8"), true, root, 0.68)
	_box("Front path", Vector3(0.0, -0.035, 11.2), Vector3(3.2, 0.07, 6.0), Color("#c7cfc4"), true, root, 0.66)
	# Main mass + wings (grand/luxurious scale).
	_box("Mansion body", Vector3(0, 2.45, 0), Vector3(16.5, 4.9, 12.5), wall, true, root, 0.82)
	_box("Mansion wing L", Vector3(-8.8, 1.95, 0.8), Vector3(6.2, 3.9, 9.5), wall.darkened(0.02), true, root, 0.82)
	_box("Mansion wing R", Vector3(8.8, 1.95, 0.8), Vector3(6.2, 3.9, 9.5), wall.darkened(0.02), true, root, 0.82)
	_box("Mansion roof", Vector3(0, 5.25, 0), Vector3(17.6, 0.7, 13.4), roof, false, root, 0.68)
	_box("Roof ridge", Vector3(0, 5.75, 0), Vector3(17.8, 0.22, 0.7), roof.darkened(0.1), false, root, 0.62)
	_box("Wing roof L", Vector3(-8.8, 4.2, 0.8), Vector3(6.8, 0.55, 10.2), roof.lightened(0.04), false, root, 0.68)
	_box("Wing roof R", Vector3(8.8, 4.2, 0.8), Vector3(6.8, 0.55, 10.2), roof.lightened(0.04), false, root, 0.68)
	# Columns/portico.
	for cx in [-2.4, -0.8, 0.8, 2.4]:
		_cylinder("Portico column", Vector3(cx, 1.55, 6.2), 0.16, 3.1, Color("#e8e1d2"), root, true, 0.18)
	_box("Portico roof", Vector3(0, 3.15, 6.4), Vector3(6.4, 0.22, 2.8), roof.lightened(0.08), false, root, 0.65)
	# Build front wall around a doorway instead of a solid entry block.
	var md_c := 0.0
	var md_w := 2.2
	var front_z := 6.26
	var w_left := -9.0
	var w_right := 9.0
	_box("Mansion front L", Vector3((w_left + (md_c - md_w*0.5)) * 0.5, 2.2, front_z), Vector3(maxf(0.1, (md_c - md_w*0.5) - w_left), 4.4, 0.16), wall, true, root, 0.78)
	_box("Mansion front R", Vector3(((md_c + md_w*0.5) + w_right) * 0.5, 2.2, front_z), Vector3(maxf(0.1, w_right - (md_c + md_w*0.5)), 4.4, 0.16), wall, true, root, 0.78)
	_box("Mansion front top", Vector3(md_c, 3.75, front_z), Vector3(md_w + 0.3, 1.3, 0.16), wall, true, root, 0.78)
	_box("Entry frame", Vector3(md_c, 1.45, front_z + 0.02), Vector3(md_w + 0.2, 2.8, 0.12), trim, false, root, 0.42, 0.22)
	_box("Entry door leaf L", Vector3(-0.52, 1.35, front_z + 0.08), Vector3(0.95, 2.55, 0.1), Color("#5a6f62"), false, root, 0.38)
	_box("Entry door leaf R", Vector3(0.52, 1.35, front_z + 0.08), Vector3(0.95, 2.55, 0.1), Color("#5a6f62"), false, root, 0.38)
	# Grand interior (enterable) — Owner's house.
	_box("Mansion interior floor", Vector3(0, -0.03, 0.0), Vector3(17.2, 0.06, 11.4), Color("#d8d1c2"), true, root, 0.62)
	_box("Mansion rug", Vector3(0, 0.015, 1.8), Vector3(8.5, 0.03, 4.8), Color("#7a5a52"), false, root, 0.82)
	_box("Mansion sofa", Vector3(0, 0.5, -1.8), Vector3(5.8, 1.0, 1.4), Color("#4f6a63"), true, root, 0.72)
	_box("Sofa side L", Vector3(-3.2, 0.5, -0.2), Vector3(1.2, 1.0, 2.2), Color("#4f6a63"), true, root, 0.72)
	_box("Sofa side R", Vector3(3.2, 0.5, -0.2), Vector3(1.2, 1.0, 2.2), Color("#4f6a63"), true, root, 0.72)
	_box("Mansion table", Vector3(0, 0.5, 0.8), Vector3(2.6, 0.55, 1.4), Color("#7a5a3a"), true, root, 0.55, 0.12)
	_box("Art panel", Vector3(-6.5, 2.2, -5.7), Vector3(3.2, 1.8, 0.08), Color("#c9b58a"), false, root, 0.6)
	_box("Shelf wall", Vector3(6.8, 1.2, -2.0), Vector3(1.2, 2.4, 4.5), Color("#bfae8a"), true, root, 0.7)
	var ml := OmniLight3D.new()
	ml.position = base + Vector3(0.0, 3.5, 0.5)
	ml.light_color = Color("#ffe8c2")
	ml.light_energy = 0.28
	ml.omni_range = 11.0
	ml.shadow_enabled = false
	add_child(ml)
	# Large windows + balcony accents.
	for wx in [-5.2, 5.2]:
		_box("Mansion window", Vector3(wx, 2.35, 6.28), Vector3(2.6, 1.9, 0.12), Color("#f2f4ee"), false, root, 0.5)
		_box("Mansion glass", Vector3(wx, 2.35, 6.34), Vector3(2.3, 1.6, 0.05), Color(0.5, 0.66, 0.72, 0.26), false, root, 0.12, 0.08, true)
	_box("Balcony", Vector3(0, 3.55, 6.55), Vector3(5.8, 0.12, 1.1), trim, false, root, 0.48, 0.2)
	_painted_text("RUMAH OWNER", base + Vector3(0, 5.15, 6.82), 0.0, 0.0052, Color("#f3e8c8"), Color(0.15,0.18,0.22,0.35), root)

	# Garage/carport for Owner vehicle.
	_box("Garage slab", Vector3(-7.5, -0.04, 11.0), Vector3(5.6, 0.08, 7.2), Color("#aab5ad"), true, root, 0.7)
	_box("Garage roof", Vector3(-7.5, 2.75, 11.0), Vector3(6.0, 0.18, 7.6), roof.darkened(0.05), false, root, 0.65)
	for px in [-9.9, -5.1]:
		for pz in [7.9, 14.1]:
			_cylinder("Garage post", Vector3(px, 1.38, pz), 0.07, 2.65, Color("#d6d0c4"), root)
	_add_parked_car(base + Vector3(-7.5, 0, 11.0), 0.0, Color("#2f3b4a"), "Owner", "car_owner_mansion", true, "Mobil Owner")
	# Luxury lights/landscape.
	for sx in [-10.5, 10.5, 0.0]:
		_box("Estate light", Vector3(sx, 1.15, 10.8), Vector3(0.14, 2.2, 0.14), Color("#6a776f"), false, root, 0.5)
		_box("Estate lamp", Vector3(sx, 2.28, 10.8), Vector3(0.36, 0.18, 0.22), Color("#efe1b8"), false, root, 0.25, 0.05, false, Color("#f6e4b8"))
		var el := OmniLight3D.new()
		el.position = base + Vector3(sx, 2.12, 11.8)
		el.light_color = Color("#ffe7bf")
		el.light_energy = 0.2
		el.omni_range = 7.5
		el.shadow_enabled = false
		add_child(el)
	for pp in [Vector3(-11.5, 0, 4.5), Vector3(11.5, 0, 4.5), Vector3(-11.5, 0, -3.5), Vector3(11.5, 0, -3.5)]:
		_add_plant(base + pp, 0.95)

## Pasar kota kecil: kios, kanopi, lampu, area jalan kaki (visual & interaktif).
func _build_market() -> void:
	var layout: Dictionary = market_layout()
	var c: Vector3 = layout.get("center", TOWN_ORIGIN + Vector3(28, 0, 92))
	_box("Market plaza", Vector3(c.x, -0.04, c.z), Vector3(26.0, 0.08, 18.0), Color("#c2bca8"), true, null, 0.72)
	_box("Market sign post", Vector3(c.x - 9.0, 1.15, c.z - 8.2), Vector3(0.14, 2.3, 0.14), Color("#6a776f"), false, null, 0.5)
	_box("Market sign", Vector3(c.x - 7.6, 1.6, c.z - 8.2), Vector3(2.8, 0.9, 0.12), Color("#7a5a46"), false, null, 0.45)
	_painted_text("PASAR BANGKAH", Vector3(c.x - 7.6, 1.6, c.z - 8.11), 0.0, 0.0042, Color("#f4ead2"), Color(0,0,0,0))
	var stalls := [
		{"x": -7.0, "z": -2.0, "name": "Sayur", "c": Color("#6f8a5a")},
		{"x": 7.0, "z": -2.0, "name": "Buah", "c": Color("#b07a52")},
		{"x": -7.0, "z": 4.5, "name": "Warung Kopi", "c": Color("#6a7288")},
		{"x": 7.0, "z": 4.5, "name": "Kue", "c": Color("#8a6a72")},
	]
	for s in stalls:
		var sp := Vector3(c.x + float(s["x"]), 0, c.z + float(s["z"]))
		_box("Stall counter", sp + Vector3(0, 0.55, 0), Vector3(4.2, 1.1, 2.4), Color("#d8ccb6"), true, null, 0.72)
		_box("Stall top", sp + Vector3(0, 1.12, 0), Vector3(4.4, 0.12, 2.6), s["c"], false, null, 0.6)
		_box("Stall canopy", sp + Vector3(0, 2.35, 0), Vector3(4.8, 0.16, 3.0), s["c"].lightened(0.12), false, null, 0.62)
		for px in [-2.0, 2.0]:
			for pz in [-1.1, 1.1]:
				_cylinder("Canopy post", sp + Vector3(px, 1.75, pz), 0.05, 1.2, Color("#8a8f86"), null)
		_label(str(s["name"]).to_upper(), sp + Vector3(0, 1.55, 1.35), 0.0034, Color("#3f3a32"))
		seats.append({"position": sp + Vector3(0, 0.05, 1.65), "yaw": 0.0, "kind": "sofa", "pivot": null, "label": "Kios " + str(s["name"])})
	for lx in [-4.0, 4.0]:
		_cylinder("Market lamp pole", Vector3(c.x + lx, 1.7, c.z - 6.5), 0.055, 3.4, Color("#6b7871"), null)
		_box("Market lamp", Vector3(c.x + lx, 3.42, c.z - 6.5), Vector3(0.45, 0.12, 0.24), Color("#efe2c0"), false, null, 0.26, 0.05, false, Color("#f5e4bf"))
		var ml := OmniLight3D.new()
		ml.position = Vector3(c.x + lx, 3.25, c.z - 5.5)
		ml.light_color = Color("#ffe8c0")
		ml.light_energy = 0.18
		ml.omni_range = 8.0
		ml.shadow_enabled = false
		add_child(ml)


## Kopdes / Koperasi Merah Putih — warga (termasuk Owner) bisa belanja kebutuhan
## rumah & kantor. Interaksi bersifat lokal/visual (tidak mengubah backend).
func _build_kopdes(pos: Vector3 = Vector3.ZERO) -> void:
	# Back-compat wrapper; Kopdes is now a separate mall.
	_build_grand_mall()

func _build_grand_mall() -> void:
	# KOPDES MERAH PUTIH MALL — pusat perbelanjaan komersial, estetika
	# perkantoran komersial netral per VISUAL-STYLE-GUIDE.md. Tidak emas,
	# tidak chandelier, tidak fountain, tidak neon berlebihan.
	var layout: Dictionary = kopdes_layout()
	var pos: Vector3 = layout.get("center", TOWN_ORIGIN + Vector3(46, 0, 58))
	var root := Node3D.new()
	root.name = "KopdesMall"
	root.position = pos
	add_child(root)

	# --- Palette netral, restrained ---
	var wall_c := Color("#e8e6e0")      # warm off-white wall
	var wall_shade := Color("#d8d6d0")  # slightly deeper for shadow reads
	var charcoal := Color("#3a3a38")    # dark metal / frame
	var metal_dark := Color("#4a4a48")  # anodized dark aluminum
	var glass_tint := Color(0.55, 0.60, 0.63, 0.20)  # slight cool tint, clear
	var glass_frame := Color(0.16, 0.18, 0.19, 0.55) # dark aluminum mullion
	var floor_c := Color("#dcdad4")     # large-format porcelain, low contrast
	var floor_mat := Color("#cbc9c2")   # mat for floor reads
	var sign_c := Color("#2a2a29")      # understated signage
	var accent := Color("#6f5e4e")      # restrained warm timber accent
	var plant_c := Color("#7a8a78")     # muted green for planting

	# --- Site & podium ---
	var mall_w := 84.0
	var mall_d := 62.0
	var wall_h := 5.6  # single story, matches HQ exterior wall height
	_box("Mall podium", Vector3(0, -0.05, 0), Vector3(mall_w + 4.0, 0.12, mall_d + 4.0), Color("#b7c0aa"), true, root, 0.78)
	_box("Mall forecourt", Vector3(0, 0.02, 22.0), Vector3(mall_w + 8.0, 0.05, 14.0), Color("#c9d0c6"), true, root, 0.62)
	_box("Mall floor", Vector3(0, 0.08, 0), Vector3(mall_w - 6.0, 0.06, mall_d - 6.0), floor_c, true, root, 0.55)

	# --- Shell: single-story commercial ---
	_box("Back wall", Vector3(0, wall_h * 0.5, -mall_d * 0.5), Vector3(mall_w + 2.0, wall_h, 0.6), wall_c, true, root, 0.8)
	_box("Left wall", Vector3(-mall_w * 0.5 - 1.0, wall_h * 0.5, 0), Vector3(0.6, wall_h, mall_d + 2.0), wall_c, true, root, 0.8)
	_box("Right wall", Vector3(mall_w * 0.5 + 1.0, wall_h * 0.5, 0), Vector3(0.6, wall_h, mall_d + 2.0), wall_c, true, root, 0.8)
	_box("Roof", Vector3(0, wall_h + 0.3, 0), Vector3(mall_w + 6.0, 0.45, mall_d + 6.0), Color("#7a6660"), false, root, 0.6)
	_box("Roof eave", Vector3(0, wall_h + 0.52, 0), Vector3(mall_w + 2.0, 0.22, mall_d + 2.0), wall_shade, false, root, 0.55)

	# --- Facade curtain wall (front +Z) — glass with dark aluminum mullions ---
	var front_z := mall_d * 0.5 + 0.32
	var facade_h := wall_h - 0.9
	var facade_y := wall_h * 0.5 - 0.45
	_box("Curtain wall center", Vector3(0, facade_y, front_z), Vector3(44.0, facade_h, 0.10), glass_tint, false, root, 0.12, 0.06, true)
	_box("Curtain wall L", Vector3(-26.0, facade_y, front_z), Vector3(16.0, facade_h, 0.10), glass_tint, false, root, 0.12, 0.06, true)
	_box("Curtain wall R", Vector3(26.0, facade_y, front_z), Vector3(16.0, facade_h, 0.10), glass_tint, false, root, 0.12, 0.06, true)
	# Dark aluminum mullion grid (subtle, not decorative)
	for mx in [-38.0, -26.0, -13.0, 0.0, 13.0, 26.0, 38.0]:
		_box("Mullion vertical", Vector3(mx, facade_y, front_z + 0.06), Vector3(0.10, facade_h, 0.10), metal_dark, false, root, 0.35, 0.5)
	for fy in [facade_y - facade_h * 0.33, facade_y + facade_h * 0.33]:
		_box("Mullion horizontal", Vector3(0, fy, front_z + 0.06), Vector3(46.0, 0.10, 0.10), metal_dark, false, root, 0.35, 0.5)
	# Side facade panels (warm off-white)
	for sx in [-40.0, 40.0]:
		_box("Stone panel", Vector3(sx, facade_y, front_z), Vector3(6.0, facade_h, 0.10), Color("#e2e0d8"), false, root, 0.7, 0.2)

	# --- Main entrance (south-facing, glazed double door + canopy) ---
	var ent_w := 10.0
	var ent_h := 4.2
	var ent_depth := 5.0
	# Entrance canopy (modest, not porte-cochère)
	_box("Entrance canopy roof", Vector3(0, 3.3, front_z + ent_depth * 0.5 + 0.8), Vector3(16.0, 0.14, ent_depth + 1.6), charcoal, false, root, 0.45, 0.3)
	_box("Entrance canopy soffit", Vector3(0, 3.18, front_z + ent_depth * 0.5 + 0.8), Vector3(14.0, 0.06, ent_depth + 0.4), Color("#dcdad4"), false, root, 0.5)
	# Entrance columns (dark metal, restrained)
	for cx in [-6.5, 6.5]:
		_cylinder("Entrance column", Vector3(cx, 1.7, front_z + ent_depth * 0.5 + 0.8), 0.28, 3.3, metal_dark, root)
		_box("Column base", Vector3(cx, 0.12, front_z + ent_depth * 0.5 + 0.8), Vector3(0.9, 0.12, 0.9), charcoal, false, root, 0.3)
		_box("Column cap", Vector3(cx, 3.32, front_z + ent_depth * 0.5 + 0.8), Vector3(0.9, 0.12, 0.9), charcoal, false, root, 0.3)
	# Glazed double doors
	_box("Door frame", Vector3(0, facade_y - facade_h * 0.33 + 2.2, front_z + 0.1), Vector3(ent_w + 1.0, ent_h - 0.4, 0.12), metal_dark, false, root, 0.35, 0.5)
	_box("Door L", Vector3(-ent_w * 0.42, facade_y - facade_h * 0.33 + 2.1, front_z + 0.14), Vector3(ent_w * 0.4 - 0.1, ent_h - 0.6, 0.06), glass_tint, false, root, 0.06, 0.03, true)
	_box("Door R", Vector3(ent_w * 0.42, facade_y - facade_h * 0.33 + 2.1, front_z + 0.14), Vector3(ent_w * 0.4 - 0.1, ent_h - 0.6, 0.06), glass_tint, false, root, 0.06, 0.03, true)
	# Entrance sign (understated, no gold)
	_box("Sign backer", Vector3(0, facade_y + facade_h * 0.4 - 0.5, front_z + 0.12), Vector3(24.0, 1.4, 0.10), wall_shade, false, root, 0.35, 0.5)
	_painted_text("KOPDES MERAH PUTIH", Vector3(-4.0, facade_y + facade_h * 0.4 - 0.4, front_z + 0.16), 0.0, 0.012, sign_c, Color(0,0,0,0), root)
	_painted_text("MALL  ·  PUSAT PERBELANJAAN KOTA BANGKAH", Vector3(0, facade_y + facade_h * 0.4 - 0.95, front_z + 0.16), 0.0, 0.005, Color("#5a5a58"), Color(0,0,0,0), root)

	# --- Interior: wide central atrium, single level ---
	var atrium_w := 26.0
	var atrium_d := 30.0
	_box("Atrium floor", Vector3(0, 0.10, 0), Vector3(atrium_w, 0.04, atrium_d), floor_mat, true, root, 0.35, 0.05)
	_box("Atrium rug", Vector3(0, 0.12, 4.0), Vector3(12.0, 0.02, 16.0), Color("#c9c7c0"), false, root, 0.8)
	# Reception / info desk (center, facing entry)
	_box("Reception desk base", Vector3(0, 0.8, 8.0), Vector3(6.0, 1.1, 2.4), Color("#c8b89a"), true, root, 0.7)
	_box("Reception desk top", Vector3(0, 1.95, 8.0), Vector3(6.4, 0.10, 2.7), floor_c, false, root, 0.3, 0.05)
	_painted_text("INFORMASI", Vector3(0, 2.1, 9.0), 0.0, 0.004, Color("#fff6f2"), Color(0,0,0,0), root)
	_painted_text("KOPDES MERAH PUTIH", Vector3(0, 1.8, 9.0), 0.0, 0.0032, Color("#5a5a58"), Color(0,0,0,0), root)

	# --- Left wing: household needs (neat rows, restrained) ---
	_box("Home wing sign", Vector3(-24.0, 2.6, 4.0), Vector3(12.0, 0.8, 0.08), Color("#f3ead8"), false, root, 0.5)
	_painted_text("KEBUTUHAN RUMAH", Vector3(-24.0, 2.6, 4.06), 0.0, 0.004, Color("#5a4a3a"), Color(0,0,0,0), root)
	_box("Home counter", Vector3(-22.0, 0.7, 2.0), Vector3(5.5, 1.2, 2.2), Color("#c8b89a"), true, root, 0.7)
	for gx in [-30.0, -22.0, -16.0]:
		for gz in [-12.0, -6.0, 0.0, 6.0, 12.0]:
			_box("Home shelf", Vector3(gx, 1.15, gz), Vector3(2.0, 2.4, 3.4), Color("#bfae8a"), true, root, 0.72)
			for gy in [0.55, 1.15]:
				_box("Home goods", Vector3(gx, gy, gz), Vector3(1.5, 0.2, 2.8), Color("#ddd4c2"), false, root, 0.82)

	# --- Right wing: office needs (neat rows, restrained) ---
	_box("Office wing sign", Vector3(24.0, 2.6, 4.0), Vector3(12.0, 0.8, 0.08), Color("#eef3ec"), false, root, 0.5)
	_painted_text("KEBUTUHAN KANTOR", Vector3(24.0, 2.6, 4.06), 0.0, 0.004, Color("#3f4a44"), Color(0,0,0,0), root)
	_box("Office counter", Vector3(22.0, 0.7, 2.0), Vector3(5.5, 1.2, 2.2), Color("#b8c4b8"), true, root, 0.7)
	for gx in [16.0, 22.0, 28.0]:
		for gz in [-12.0, -6.0, 0.0, 6.0, 12.0]:
			_box("Office shelf", Vector3(gx, 1.15, gz), Vector3(2.0, 2.4, 3.4), Color("#aeb8ad"), true, root, 0.72)
			for gy in [0.55, 1.15]:
				_box("Office goods", Vector3(gx, gy, gz), Vector3(1.5, 0.2, 2.8), Color("#e2e8e0"), false, root, 0.82)

	# --- Back: cashier / service center ---
	_box("Cashier desk", Vector3(0, 0.7, -14.0), Vector3(8.0, 1.3, 2.6), Color("#c8b89a"), true, root, 0.7)
	_box("Cashier top", Vector3(0, 1.4, -14.0), Vector3(8.4, 0.10, 2.9), floor_c, false, root, 0.3, 0.05)
	_painted_text("KASIR PUSAT  ·  LAYANAN PELANGGAN", Vector3(0, 1.55, -15.2), 0.0, 0.004, Color("#3a3a38"), Color(0,0,0,0), root)

	# --- Ceiling lighting: recessed, neutral, restrained ---
	for lx in [-28.0, -14.0, 0.0, 14.0, 28.0]:
		for lz in [-20.0, -10.0, 0.0, 10.0, 20.0]:
			_box("Recessed light", Vector3(lx, wall_h - 0.4, lz), Vector3(1.0, 0.08, 1.0), Color("#f3e8c8"), false, root, 0.22, 0.05, false, Color("#f0e8d8"))
			var ml := OmniLight3D.new()
			ml.position = pos + Vector3(lx, wall_h - 1.2, lz)
			ml.light_color = Color("#f3efe8")
			ml.light_energy = 0.2
			ml.omni_range = 10.0
			ml.shadow_enabled = false
			add_child(ml)

	# --- Exterior planters at corners (muted, tidy) ---
	for px in [-38.0, 38.0]:
		for pz in [-26.0, 26.0]:
			_box("Planter", Vector3(px, 0.4, pz), Vector3(2.8, 0.8, 2.8), Color("#b7c0aa"), false, root, 0.55)
			_add_plant(pos + Vector3(px, 1.15, pz), 0.95)

	# --- Street lamps approaching mall ---
	for lx in [-22.0, 22.0]:
		_add_street_lamp(pos + Vector3(lx, 0.0, 26.0))



func _build_kopdes_merah_putih() -> void:
	# Kopdes Merah Putih (iconic 2 lantai) — landmark lokal; estetika netral
	# per VISUAL-STYLE-GUIDE.md: tanpa merah menyala, tanpa glow berlebihan.
	var l: Dictionary = kopdes_merah_putih_layout()
	var b: Vector3 = l.get("base", TOWN_ORIGIN + Vector3(-44,0,40))
	var root := Node3D.new(); root.name = "KopdesMerahPutih"; root.position = b; add_child(root)
	var accent := Color("#6f5e4e")   # restrained warm timber
	var white := Color("#f4f1ea"); var glass := Color(0.55,0.7,0.74,0.20)
	var frame := Color(0.16,0.18,0.19,0.55)  # dark aluminum mullion
	_box("KMP lot", Vector3(0,-0.04,1.5), Vector3(18.0,0.08,15.0), Color("#b7c0aa"), true, root, 0.78)
	_box("KMP building L1", Vector3(0,1.45,0), Vector3(14.0,2.9,11.0), white, true, root, 0.82)
	_box("KMP building L2", Vector3(0,4.0,0), Vector3(14.0,2.2,11.0), white, true, root, 0.82)
	_box("KMP roof", Vector3(0,5.25,0), Vector3(14.8,0.3,11.8), Color("#6f7a76"), false, root)
	# Timber accents (pillars/canopy), restrained
	_box("KMP lisplang", Vector3(0,5.0,5.55), Vector3(14.6,0.35,0.18), accent, false, root, 0.45)
	for px in [-5.2,-1.8,1.8,5.2]: _box("KMP pillar", Vector3(px,2.1,5.55), Vector3(0.35,4.2,0.35), accent, false, root, 0.45)
	_box("KMP canopy", Vector3(0,3.05,6.9), Vector3(10.5,0.16,2.6), accent, false, root, 0.5)
	for cx in [-4.0,0.0,4.0]: _cylinder("KMP canopy post", Vector3(cx,1.5,7.9), 0.08,3.0, Color("#4a3f3a"), root)
	# Large front glass
	_box("KMP glass L", Vector3(-4.0,1.55,5.58), Vector3(4.2,2.4,0.08), glass, false, root, 0.12,0.08,true)
	_box("KMP glass R", Vector3(4.0,1.55,5.58), Vector3(4.2,2.4,0.08), glass, false, root, 0.12,0.08,true)
	# Sign board (understated, no red)
	_box("KMP sign board", Vector3(0,3.85,5.62), Vector3(10.2,0.95,0.12), Color("#c8c6c0"), false, root, 0.4, 0.0, false, Color("#e0ded8"))
	_painted_text("KOPERASI DESA MERAH PUTIH", Vector3(0,3.85,5.7), 0.0, 0.0044, Color("#2a2a29"), Color(0,0,0,0), root)
	# Flag (neutral)
	_cylinder("Flag pole", Vector3(-7.8,2.2,6.8), 0.05,4.4, Color("#9aa3a0"), root)
	_box("Flag dark", Vector3(-7.25,3.95,6.8), Vector3(1.1,0.35,0.04), Color("#3a3a38"), false, root)
	_box("Flag white", Vector3(-7.25,3.6,6.8), Vector3(1.1,0.35,0.04), white, false, root)
	# Interior hint
	_box("KMP counter", Vector3(0,0.55,-2.5), Vector3(3.2,1.1,1.2), Color("#c8b89a"), true, root)
	_box("KMP shelf", Vector3(-4.8,1.0,-1.5), Vector3(1.2,2.0,4.5), Color("#cfc4b0"), true, root)

func _build_kopdes_unit() -> void:
	# Kopdes Unit standard (1 lantai, cabang cepat) — estetika netral.
	var l: Dictionary = kopdes_unit_layout()
	var b: Vector3 = l.get("base", TOWN_ORIGIN + Vector3(-44,0,68))
	var root := Node3D.new(); root.name = "KopdesUnit"; root.position = b; add_child(root)
	var accent := Color("#6f5e4e")
	var white := Color("#f7f4ee")
	_box("Unit lot", Vector3(0,-0.04,1.0), Vector3(14.0,0.08,12.0), Color("#b7c0aa"), true, root, 0.78)
	_box("Unit building", Vector3(0,1.35,0), Vector3(10.5,2.7,8.5), white, true, root, 0.82)
	_box("Unit roof", Vector3(0,2.85,0), Vector3(11.2,0.28,9.2), Color("#7a8580"), false, root)
	_box("Unit sign", Vector3(0,2.35,4.32), Vector3(8.5,0.75,0.12), Color("#c8c6c0"), false, root, 0.4, 0.0, false, Color("#e0ded8"))
	_painted_text("KOPDES UNIT", Vector3(0,2.35,4.4), 0.0, 0.0046, Color("#2a2a29"), Color(0,0,0,0), root)
	_box("Unit glass", Vector3(0,1.25,4.3), Vector3(6.0,1.9,0.08), Color(0.55,0.7,0.74,0.22), false, root, 0.12,0.08,true)
	_box("Unit counter", Vector3(0,0.55,-1.8), Vector3(2.6,1.1,1.0), Color("#c8b89a"), true, root)
	_label("ATM / LAYANAN CEPAT", Vector3(0,1.35,-1.2), 0.0032, Color("#4a3f3a"))

func _add_street_lamp_multimesh(positions: Array[Vector3]) -> void:
	# Repeated street/area lamps as MultiMeshInstance3D (visual) + per-instance lights.
	if positions.is_empty(): return
	var root := Node3D.new(); root.name = "StreetLamps_MM"; add_child(root)
	var pole_mm := MultiMesh.new(); pole_mm.transform_format = MultiMesh.TRANSFORM_3D; pole_mm.instance_count = positions.size()
	var pc := CylinderMesh.new(); pc.top_radius = 0.055; pc.bottom_radius = 0.055; pc.height = 3.6; pc.radial_segments = 8
	pole_mm.mesh = pc
	var head_mm := MultiMesh.new(); head_mm.transform_format = MultiMesh.TRANSFORM_3D; head_mm.instance_count = positions.size()
	var hc := BoxMesh.new(); hc.size = Vector3(0.5, 0.12, 0.26); head_mm.mesh = hc
	for i in range(positions.size()):
		var p: Vector3 = positions[i]
		pole_mm.set_instance_transform(i, Transform3D(Basis(), p + Vector3(0, 1.85, 0)))
		head_mm.set_instance_transform(i, Transform3D(Basis(), p + Vector3(0, 3.72, 0)))
		var sl := OmniLight3D.new(); sl.position = p + Vector3(-0.2, 3.55, 0); sl.light_color = Color("#ffe9c2"); sl.light_energy = 0.14; sl.omni_range = 8.5; sl.shadow_enabled = false; add_child(sl)
	var pmi := MultiMeshInstance3D.new(); pmi.multimesh = pole_mm; pmi.material_override = _mat(Color("#6b7871"), 0.55); pmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON; root.add_child(pmi)
	var hmi := MultiMeshInstance3D.new(); hmi.multimesh = head_mm; hmi.material_override = _mat(Color("#ded6c2"), 0.28, 0.05, false, Color("#f3e4bf")); root.add_child(hmi)

func _add_tree_multimesh(positions: Array[Vector3]) -> void:
	if positions.is_empty(): return
	var root := Node3D.new(); root.name = "Trees_MM"; add_child(root)
	var trunk_mm := MultiMesh.new(); trunk_mm.transform_format = MultiMesh.TRANSFORM_3D; trunk_mm.instance_count = positions.size()
	var tc := CylinderMesh.new(); tc.top_radius = 0.22; tc.bottom_radius = 0.24; tc.height = 2.3; tc.radial_segments = 8
	trunk_mm.mesh = tc
	var can_mm := MultiMesh.new(); can_mm.transform_format = MultiMesh.TRANSFORM_3D; can_mm.instance_count = positions.size()
	var sc := SphereMesh.new(); sc.radius = 1.5; sc.height = 3.0; sc.radial_segments = 10; sc.rings = 6
	can_mm.mesh = sc
	for i in range(positions.size()):
		var p: Vector3 = positions[i]
		trunk_mm.set_instance_transform(i, Transform3D(Basis(), p + Vector3(0, 1.15, 0)))
		can_mm.set_instance_transform(i, Transform3D(Basis().scaled(Vector3(1.05,1.0,1.05)), p + Vector3(0, 2.55, 0)))
	var tmi := MultiMeshInstance3D.new(); tmi.multimesh = trunk_mm; tmi.material_override = _mat(Color("#735b45"), 0.9); tmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON; root.add_child(tmi)
	var cmi := MultiMeshInstance3D.new(); cmi.multimesh = can_mm; cmi.material_override = _mat(Color("#668b6d"), 0.85); cmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON; root.add_child(cmi)

func _add_street_props() -> void:
	# Non-drivable parked cars and small props for city density. Kept off road centerlines
	# and away from HQ entrance/workstation areas; do not add to HQ door/seat registries.
	var parked := [
		{"p": Vector3(TOWN_ORIGIN.x + 4.5, 0, TOWN_ORIGIN.z + 18.0), "y": 0.0, "c": Color("#6a7f90")},
		{"p": Vector3(TOWN_ORIGIN.x + 28.5, 0, TOWN_ORIGIN.z + 40.0), "y": PI, "c": Color("#8a6a5a")},
		{"p": Vector3(TOWN_ORIGIN.x + 4.5, 0, TOWN_ORIGIN.z + 62.0), "y": 0.0, "c": Color("#5f7a66")},
		{"p": Vector3(TOWN_ORIGIN.x + 28.5, 0, TOWN_ORIGIN.z + 84.0), "y": PI, "c": Color("#7a6f86")},
		{"p": Vector3(TOWN_ORIGIN.x + 36.0, 0, TOWN_ORIGIN.z + 96.0), "y": -PI*0.5, "c": Color("#607888")},
		{"p": Vector3(TOWN_ORIGIN.x + 4.0, 0, TOWN_ORIGIN.z + 96.0), "y": PI*0.5, "c": Color("#8b7662")},
		{"p": Vector3(TOWN_ORIGIN.x + 16.5, 0, TOWN_ORIGIN.z + 6.0), "y": PI*0.5, "c": Color("#556a78")},
		{"p": Vector3(TOWN_ORIGIN.x + 16.5, 0, TOWN_ORIGIN.z + 50.0), "y": -PI*0.5, "c": Color("#7a6658")},
		{"p": Vector3(TOWN_ORIGIN.x + 30.0, 0, TOWN_ORIGIN.z + 70.0), "y": PI, "c": Color("#5f6f80")},
	]
	for pc in parked:
		_add_parked_car(pc["p"], float(pc["y"]), pc["c"], "", "", false, "")
	# Benches/planters along sidewalks (collidable/visual as before; planters remain individual for variety)
	var mc: Vector3 = market_layout().get("center", TOWN_ORIGIN + Vector3(28, 0, 92))
	for bx in [-4.0, 4.0]:
		_box("Bench", mc + Vector3(bx, 0.28, -6.5), Vector3(1.8, 0.12, 0.55), Color("#7a6a56"), true, null, 0.7)
		_box("Bench back", mc + Vector3(bx, 0.55, -6.78), Vector3(1.8, 0.42, 0.08), Color("#7a6a56"), true, null, 0.7)
	for pxp in [Vector3(TOWN_ORIGIN.x + 2.2, 0, TOWN_ORIGIN.z + 10.0), Vector3(TOWN_ORIGIN.x + 2.2, 0, TOWN_ORIGIN.z + 32.0), Vector3(TOWN_ORIGIN.x + 2.2, 0, TOWN_ORIGIN.z + 54.0), Vector3(TOWN_ORIGIN.x + 2.2, 0, TOWN_ORIGIN.z + 76.0)]:
		_add_plant(pxp, 0.65)
	# (Crosswalks drawn once in _build_site to avoid z-fighting.)

func _apply_led_billboard_shader(bb_node: Node3D) -> void:
	# Design Bible: giant LED billboard with animated promo (procedural GDShader, no external texture).
	var mesh := bb_node.get_node_or_null("Mesh") as MeshInstance3D
	if mesh == null: return
	var sh := Shader.new()
	sh.code = """shader_type spatial;
render_mode unshaded, cull_disabled;
uniform float speed : hint_range(0.0,3.0) = 0.45;
void fragment(){
	vec2 uv = UV;
	float scan = step(0.92, fract(uv.y*48.0 + TIME*0.4));
	float band = smoothstep(0.0,0.2,fract(uv.x + TIME*speed)) * (1.0-smoothstep(0.2,0.4,fract(uv.x + TIME*speed)));
	vec3 base = mix(vec3(0.05,0.10,0.14), vec3(0.12,0.55,0.60), uv.x);
	vec3 promo = mix(vec3(0.85,0.22,0.22), vec3(0.95,0.85,0.55), band);
	vec3 col = mix(base, promo, band*0.65) + scan*0.06;
	ALBEDO = col; EMISSION = col * 1.15;
}"""
	var sm := ShaderMaterial.new()
	sm.shader = sh
	mesh.material_override = sm

## Compute the employee's home/commute anchors (used by NPCs and main).
static func employee_house_layout(employee_id: String) -> Dictionary:
	var offsets := {
		"lead": Vector2(0, 0), "coo": Vector2(24, 0), "architect": Vector2(0, 22),
		"backend": Vector2(24, 22), "api": Vector2(0, 44), "frontend": Vector2(24, 44), "qa": Vector2(12, 66),
	}
	var off: Vector2 = offsets.get(employee_id, Vector2(12, 22))
	var base := TOWN_ORIGIN + Vector3(off.x, 0, off.y)
	var door := base + Vector3(2.2, 0.05, 9.2)
	var carport := base + Vector3(12.8, 0.05, 13.8)
	var street := Vector3(TOWN_ORIGIN.x + 6.0, 0.05, base.z + 9.8)
	return {
		"id": employee_id,
		"door": door,
		"carport": carport,
		"street": street,
		"parking": HQ_PARKING_WALK,
		"entrance": HQ_ENTRANCE,
		"commute_to_work": [door, carport, street, TOWN_GATE, HQ_SIDEWALK, HQ_PARKING_WALK, HQ_ENTRANCE],
		"commute_home": [HQ_ENTRANCE, HQ_PARKING_WALK, HQ_SIDEWALK, TOWN_GATE, street, carport, door],
	}

## Owner's mansion (largest, most luxurious) — visitable/town anchor.
static func owner_mansion_layout() -> Dictionary:
	var base := TOWN_ORIGIN + Vector3(44.0, 0.0, -10.0)
	return {
		"id": "owner",
		"base": base,
		"door": base + Vector3(0.0, 0.05, 10.2),
		"carport": base + Vector3(-7.5, 0.05, 11.0),
		"parking": base + Vector3(-7.5, 0.05, 14.5),
		"gate": base + Vector3(0.0, 0.05, 16.5),
		"street": Vector3(TOWN_ORIGIN.x + 6.0, 0.05, base.z + 14.5),
	}

static func kopdes_layout() -> Dictionary:
	# Kopdes Merah Putih Mall (pusat perbelanjaan besar). Kept id/door compatible
	# with any main.gd portal/trade and with kopdes_layout()/market seats contracts.
	var center := TOWN_ORIGIN + Vector3(46.0, 0.0, 58.0)
	return {"id":"kopdes", "center": center, "door": center + Vector3(0.0, 0.05, 18.8)}

static func kopdes_merah_putih_layout() -> Dictionary:
	# Iconic landmark 2 lantai di strip jalan utama (depan Kopdes Mall).
	var base := TOWN_ORIGIN + Vector3(-44.0, 0.0, 40.0)
	return {"id":"kopdes_mp", "base": base, "door": base + Vector3(0.0, 0.05, 8.2)}

static func kopdes_unit_layout() -> Dictionary:
	var base := TOWN_ORIGIN + Vector3(-44.0, 0.0, 68.0)
	return {"id":"kopdes_unit", "base": base, "door": base + Vector3(0.0, 0.05, 6.6)}

## Town market square — hub for roaming and social interaction.
static func market_layout() -> Dictionary:
	var center := TOWN_ORIGIN + Vector3(28.0, 0.0, 92.0)
	return {
		"center": center,
		"entry": center + Vector3(0.0, 0.05, -10.0),
		"spots": [
			center + Vector3(-6.0, 0.05, -2.0),
			center + Vector3(6.0, 0.05, -2.0),
			center + Vector3(-6.0, 0.05, 4.0),
			center + Vector3(6.0, 0.05, 4.0),
		],
	}
