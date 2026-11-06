extends RefCounted

## Enhanced procedural humanoid for Bangkah HQ.
## Builds a realistic office worker with improved body proportions, PBR materials,
## detailed facial features, layered hair, articulated hands, and natural clothing.
## Designed to be replaced by GLB characters if available.
##
## API (unchanged from previous version):
##   arms: Array[Node3D]      – shoulder pivots
##   legs: Array[Node3D]      – hip pivots
##   eyes: Array[MeshInstance3D] – eyeball meshes for blink
##   head_pivot: Node3D       – head rotation pivot
##   label: Label3D           – floating name (hidden by default)
##   status_label: Label3D    – status text (hidden by default)
##   visual: Node3D           – root visual node
##   animation_player / external_model – optional GLB overrides

# ---- Material helpers ----

static func material(color: Color, roughness: float = 0.86, metallic: float = 0.0) -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.roughness = roughness
	result.metallic = metallic
	result.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return result

static func skin_material(base: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = base
	mat.roughness = 0.55
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	# Subsurface scattering approximation — warm inner glow for realistic skin.
	mat.emission_enabled = true
	mat.emission = base.lightened(0.18)
	mat.emission_energy_multiplier = 0.06
	# Rim lighting for depth and separation from background.
	mat.rim_enabled = true
	mat.rim = 0.35
	mat.rim_tint = 0.45
	# Subtle specular for skin oiliness.
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return mat

static func fabric_material(color: Color, roughness: float = 0.88) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mat.rim_enabled = true
	mat.rim = 0.12
	mat.rim_tint = 0.25
	return mat

static func leather_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.30
	mat.metallic = 0.05
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return mat

static func hair_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.75
	mat.metallic = 0.02
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mat.rim_enabled = true
	mat.rim = 0.20
	mat.rim_tint = 0.5
	return mat

static func metallic_material(color: Color, roughness: float = 0.25, metallic: float = 0.7) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = metallic
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return mat

static func hijab_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.92
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mat.rim_enabled = true
	mat.rim = 0.08
	mat.rim_tint = 0.2
	return mat

static func makeup_material(color: Color, roughness: float = 0.30) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return mat

# ---- Mesh helpers ----

static func _mesh(parent: Node3D, mesh_resource: Mesh, mat: Material, position: Vector3, scale: Vector3 = Vector3.ONE) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh_resource
	instance.material_override = mat
	instance.position = position
	instance.scale = scale
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(instance)
	return instance

static func _sphere_mesh(radius: float, radial: int = 32, rings: int = 16) -> SphereMesh:
	var m := SphereMesh.new()
	m.radius = radius
	m.height = radius * 2.0
	m.radial_segments = radial
	m.rings = rings
	return m

static func _capsule_mesh(radius: float, height: float, radial: int = 20, rings: int = 8) -> CapsuleMesh:
	var m := CapsuleMesh.new()
	m.radius = radius
	m.height = height
	m.radial_segments = radial
	m.rings = rings
	return m

static func _box_mesh(size: Vector3) -> BoxMesh:
	var m := BoxMesh.new()
	m.size = size
	m.subdivide_width = 2
	m.subdivide_depth = 2
	m.subdivide_height = 2
	return m

static func _cylinder_mesh(radius_top: float, radius_bottom: float, height: float, segments: int = 24) -> CylinderMesh:
	var m := CylinderMesh.new()
	m.top_radius = radius_top
	m.bottom_radius = radius_bottom
	m.height = height
	m.radial_segments = segments
	return m

static func _tapered_torso(width_bottom: float, width_top: float, _depth: float, height: float) -> CapsuleMesh:
	var m := CapsuleMesh.new()
	m.radius = (width_bottom + width_top) * 0.25
	m.height = height
	m.radial_segments = 32
	m.rings = 14
	return m

static func _make_label(parent: Node3D, text_value: String, height: float, font_size: int, pixel_size: float) -> Label3D:
	var label := Label3D.new()
	label.text = text_value
	label.position = Vector3(0, height, 0)
	label.font_size = font_size
	label.outline_size = 5
	label.modulate = Color("#f4f3ed")
	label.outline_modulate = Color(0.04, 0.07, 0.065, 0.88)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.pixel_size = pixel_size
	label.visible = false
	parent.add_child(label)
	return label

static func _find_animation_player(root: Node) -> AnimationPlayer:
	if root is AnimationPlayer:
		return root as AnimationPlayer
	for child in root.get_children():
		var found := _find_animation_player(child)
		if found != null:
			return found
	return null

static func _build_from_glb(parent: Node3D, employee_id: String, label_text: String) -> Dictionary:
	if employee_id.is_empty():
		return {}
	var asset_path := "res://assets/characters/" + employee_id + ".glb"
	if not ResourceLoader.exists(asset_path):
		return {}
	var packed := load(asset_path) as PackedScene
	if packed == null:
		push_warning("Character asset exists but is not a PackedScene: " + asset_path)
		return {}
	var instance := packed.instantiate()
	if not instance is Node3D:
		instance.queue_free()
		push_warning("Character GLB root must inherit Node3D: " + asset_path)
		return {}
	var model := instance as Node3D
	model.name = "RiggedCharacter_%s" % employee_id
	model.position = Vector3.ZERO
	parent.add_child(model)
	var label := _make_label(model, label_text, 2.67, 26, 0.006)
	var status_label := _make_label(model, "IDLE", 2.43, 15, 0.005)
	return {
		"arms": [],
		"legs": [],
		"eyes": [],
		"head_pivot": null,
		"label": label,
		"status_label": status_label,
		"visual": model,
		"animation_player": _find_animation_player(model),
		"external_model": true
	}

static func build(parent: Node3D, shirt: Color, hair: Color, label_text: String, employee_id: String = "", skin: Color = Color("#c89e84"), gender: String = "male", hijab: bool = false, body_type: String = "average", floor: int = 1):
	var external := _build_from_glb(parent, employee_id, label_text)
	if not external.is_empty():
		return external

	# -- Procedural detailed humanoid with enhanced proportions --
	var body := Node3D.new()
	body.name = "HumanoidVisual"
	parent.add_child(body)

	var is_female := gender.to_lower() == "female"
	var wear_hijab := is_female and hijab

	# Generate skin tones from the base.
	var skin_mat := skin_material(skin)
	var dark_skin := skin.darkened(0.07)
	var dark_skin_mat := skin_material(dark_skin)
	var light_skin := skin.lightened(0.06)
	var light_skin_mat := skin_material(light_skin)

	# Clothing materials.
	var fabric_mat := fabric_material(shirt, 0.86)
	var shirt_dark := fabric_material(shirt.darkened(0.08), 0.90)
	var shirt_light := fabric_material(shirt.lightened(0.10), 0.84)
	var pants_color := Color("#2d3640")
	var pants_mat := fabric_material(pants_color, 0.92)
	var pants_dark := fabric_material(pants_color.darkened(0.06), 0.94)
	var shoe_mat := leather_material(Color("#1a2024"))
	var hair_mat := hair_material(hair)
	var hair_dark_mat := hair_material(hair.darkened(0.15))
	var hair_light_mat := hair_material(hair.lightened(0.08))

	# Hijab material (neutral office-appropriate).
	var hijab_color := Color("#222a2f")
	var hijab_mat := hijab_material(hijab_color)

	# Makeup materials (female only).
	var eyeshadow_mat := makeup_material(Color("#5a4a5a"), 0.28)
	var lipstick_mat := makeup_material(Color("#b85a6a"), 0.25)
	var blush_mat := makeup_material(skin.lightened(0.15).lerp(Color("#e8a08c"), 0.5), 0.45)
	var lash_mat := makeup_material(Color("#1a1a1a"), 0.4)

	# Stubble material (male only).
	var stubble_mat := makeup_material(hair.darkened(0.25), 0.55)

	# ---- BODY TYPE & PROPORTIONS (7–7.5 head ratio, stylized realism) ----
	var head_h := 0.20   # head diameter reference
	var total_h := 1.68  # ~7-7.5 heads tall adult

	# Body type modifiers: affects shoulder width, waist, leg thickness.
	var bt_shoulder_w := 1.0
	var bt_waist_w := 1.0
	var bt_leg_w := 1.0
	var bt_height_mult := 1.0
	if body_type == "slim":
		bt_shoulder_w = 0.88
		bt_waist_w = 0.80
		bt_leg_w = 0.82
		bt_height_mult = 1.03
	elif body_type == "average":
		bt_shoulder_w = 1.0
		bt_waist_w = 1.0
		bt_leg_w = 1.0
		bt_height_mult = 1.0
	elif body_type == "stocky":
		bt_shoulder_w = 1.14
		bt_waist_w = 1.10
		bt_leg_w = 1.08
		bt_height_mult = 0.96
	elif body_type == "tall":
		bt_shoulder_w = 1.0
		bt_waist_w = 0.94
		bt_leg_w = 0.94
		bt_height_mult = 1.12
	elif body_type == "short":
		bt_shoulder_w = 0.94
		bt_waist_w = 1.0
		bt_leg_w = 1.0
		bt_height_mult = 0.88

	total_h *= bt_height_mult

	# Gender-specific silhouette shaping.
	# Men: broader shoulders, V-taper torso. Women: hourglass (narrow waist, wider hips).
	var male_shoulder_boost := 1.0 if not is_female else 1.0
	var female_hip_boost := 1.0 if is_female else 1.0
	var male_waist_narrow := 0.92 if not is_female else 1.0
	var female_waist_narrow := 0.85 if is_female else 1.0

	# ---- TORSO — anatomically tapered, attractive silhouette ----
	var shoulder_w := 0.64 * bt_shoulder_w * male_shoulder_boost
	var waist_w := (0.44 if is_female else 0.47) * bt_waist_w
	waist_w *= (female_waist_narrow if is_female else male_waist_narrow)
	var hip_w := (0.50 if is_female else 0.46) * bt_shoulder_w * female_hip_boost

	# Upper chest — broad shoulders with natural taper (more pronounced for men).
	var chest := _mesh(body, _tapered_torso(shoulder_w, waist_w * 1.08, 0.42, 0.55), fabric_mat, Vector3(0, 1.45, 0))
	chest.scale = Vector3(1.08 * bt_shoulder_w * male_shoulder_boost, 1.0, 0.82)
	# Upper back.
	_mesh(body, _capsule_mesh(0.245, 0.36, 30, 14), shirt_dark, Vector3(0, 1.52, -0.05)).scale = Vector3(1.0, 0.85, 0.75)
	# Mid torso — waist narrows naturally (hourglass for women, V-taper for men).
	var waist := _mesh(body, _tapered_torso(waist_w, waist_w * 0.90, 0.38, 0.38), shirt_dark, Vector3(0, 1.10, 0))
	waist.scale = Vector3(0.94 if is_female else 0.98, 1.0, 0.80 if is_female else 0.82)
	# Hips / pelvis — wider than waist (more pronounced for women).
	var pelvis := _mesh(body, _capsule_mesh(0.26, 0.34, 26, 8), pants_mat, Vector3(0, 0.80, 0))
	pelvis.scale = Vector3(1.12 * bt_shoulder_w * female_hip_boost, 1.0, 0.85 if is_female else 0.82)
	# Glutes for seated posture.
	_mesh(body, _sphere_mesh(0.090, 22, 11), pants_mat, Vector3(-0.095, 0.72, -0.13)).scale = Vector3(1.15, 0.72, 0.88)
	_mesh(body, _sphere_mesh(0.090, 22, 11), pants_mat, Vector3(0.095, 0.72, -0.13)).scale = Vector3(1.15, 0.72, 0.88)

	# Neck — tapered cylinder with natural slope.
	_mesh(body, _cylinder_mesh(0.064, 0.085, 0.16, 16), skin_mat, Vector3(0, 1.76, 0))
	# Adam's apple hint (male only, more defined).
	if not is_female:
		_mesh(body, _sphere_mesh(0.024, 14, 8), skin_mat, Vector3(0, 1.75, -0.075)).scale = Vector3(0.85, 1.3, 0.65)

	# Shoulder caps — defined deltoids.
	for sx in [-0.31, 0.31]:
		var deltoid := _mesh(body, _sphere_mesh(0.088, 26, 14), fabric_mat, Vector3(sx * bt_shoulder_w * male_shoulder_boost, 1.65, -0.01))
		deltoid.scale = Vector3(1.0, 0.85, 0.92)

	# Shirt collar — crisp V-neck.
	var collar := _mesh(body, _box_mesh(Vector3(0.28, 0.065, 0.15)), shirt_light, Vector3(0, 1.70, -0.12))
	collar.rotation.x = 0.15
	# Collar points.
	for sx in [-0.09, 0.09]:
		var point := _mesh(body, _box_mesh(Vector3(0.065, 0.055, 0.022)), shirt_light, Vector3(sx, 1.66, -0.16))
		point.rotation.x = 0.22
		point.rotation.z = sx * 0.10
	# Button line.
	for y in [1.56, 1.43, 1.30, 1.17, 1.04]:
		_mesh(body, _sphere_mesh(0.013, 12, 8), metallic_material(Color("#888070"), 0.35, 0.4), Vector3(0, y, -0.19))
	# Belt.
	_mesh(body, _box_mesh(Vector3(0.48 * bt_shoulder_w, 0.05, 0.35)), leather_material(Color("#1a1a1a")), Vector3(0, 0.86, 0))
	# Belt buckle.
	_mesh(body, _box_mesh(Vector3(0.11, 0.05, 0.022)), metallic_material(Color("#9a8a5a"), 0.25, 0.6), Vector3(0, 0.86, -0.175))

	# ---- LANAYARD / ID CARD KANTOR (micro-detail, Bangkah logo) ----
	var lanyard_mat := leather_material(Color("#1a1a1a"))
	_mesh(body, _box_mesh(Vector3(0.105, 0.028, 0.065)), lanyard_mat, Vector3(0, 1.74, -0.105))
	_mesh(body, _box_mesh(Vector3(0.105, 0.028, 0.065)), lanyard_mat, Vector3(0, 1.715, 0.105))
	var id_card_mat := StandardMaterial3D.new()
	id_card_mat.albedo_color = Color("#ffffff")
	id_card_mat.roughness = 0.28
	id_card_mat.metallic = 0.05
	id_card_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	_mesh(body, _box_mesh(Vector3(0.080, 0.105, 0.022)), id_card_mat, Vector3(0.120, 1.46, -0.24))
	_mesh(body, _box_mesh(Vector3(0.019, 0.055, 0.009)), metallic_material(Color("#999"), 0.3, 0.5), Vector3(0.120, 1.55, -0.247))
	_mesh(body, _box_mesh(Vector3(0.058, 0.020, 0.014)), metallic_material(Color("#44d8e8"), 0.2, 0.4), Vector3(0.120, 1.51, -0.248))

	# ---- HEAD — attractive, well-proportioned face ----
	var head_pivot := Node3D.new()
	head_pivot.name = "HeadPivot"
	head_pivot.position = Vector3(0, 1.85, 0)
	body.add_child(head_pivot)

	# Head — attractive oval shape, wider at cheekbones, narrower at jaw.
	var head := _mesh(head_pivot, _sphere_mesh(head_h, 44, 28), skin_mat, Vector3(0, 0.24, -0.005))
	head.scale = Vector3(0.92 if is_female else 0.96, 1.10, 0.86)

	# Forehead — smooth, slightly rounded.
	var forehead := _mesh(head_pivot, _sphere_mesh(0.105, 28, 16), light_skin_mat, Vector3(0, 0.38, -0.04))
	forehead.scale = Vector3(1.32, 0.58, 0.80)

	# Cheekbones — defined, higher for women, broader for men.
	for sx in [-1.0, 1.0]:
		var cheek := _mesh(head_pivot, _sphere_mesh(0.052, 18, 10), dark_skin_mat, Vector3(sx * 0.135, 0.14, -0.01))
		cheek.scale = Vector3(0.88 if is_female else 0.82, 0.70 if is_female else 0.64, 0.58)
		# Blush on cheekbones (women only).
		if is_female:
			_mesh(head_pivot, _sphere_mesh(0.035, 14, 8), blush_mat, Vector3(sx * 0.130, 0.10, 0.02)).scale = Vector3(1.2, 0.7, 0.5)

	# Jaw — attractive shape: strong square for men, soft V-shape for women.
	var jaw_scale := 0.92 if is_female else 0.98
	var jaw := _mesh(head_pivot, _sphere_mesh(0.185, 34, 20), dark_skin_mat, Vector3(0, 0.05, 0.05))
	jaw.scale = Vector3(jaw_scale, 0.58, 1.0)
	if not is_female:
		# Stronger, square jawline (ganteng/maskulin).
		for sx in [-1.0, 1.0]:
			_mesh(head_pivot, _box_mesh(Vector3(0.07, 0.014, 0.055)), dark_skin_mat, Vector3(sx * 0.125, 0.050, 0.060)).rotation.z = sx * 0.20
	else:
		# Softer, V-shaped jawline (cantik).
		for sx in [-1.0, 1.0]:
			_mesh(head_pivot, _box_mesh(Vector3(0.055, 0.012, 0.045)), dark_skin_mat, Vector3(sx * 0.110, 0.045, 0.055)).rotation.z = sx * 0.15

	# Chin — defined projection (stronger for men, softer for women).
	var chin_scale := 0.75 if is_female else 0.85
	var chin := _mesh(head_pivot, _sphere_mesh(0.060, 20, 12), skin_mat, Vector3(0, -0.010, 0.11))
	chin.scale = Vector3(chin_scale, 0.55, 0.80)

	# Temple — slight indentation for skull shape.
	for sx in [-1.0, 1.0]:
		_mesh(head_pivot, _sphere_mesh(0.042, 14, 8), dark_skin_mat, Vector3(sx * 0.16, 0.24, -0.01)).scale = Vector3(0.65, 0.85, 0.55)

	# ---- HAIR — attractive, gender-specific styling ----
	if wear_hijab:
		# Minimal hair visible under hijab — just fringe at forehead.
		var hair_top := _mesh(head_pivot, _sphere_mesh(0.200, 34, 20), hair_mat, Vector3(0, 0.35, -0.008))
		hair_top.scale = Vector3(1.0, 0.52, 0.80)
		var fringe := _mesh(head_pivot, _sphere_mesh(0.075, 16, 10), hair_mat, Vector3(0, 0.34, -0.150))
		fringe.scale = Vector3(1.40, 0.35, 0.62)
	else:
		if is_female:
			# Longer, styled hair (cantik) — voluminous crown and back.
			var hair_top := _mesh(head_pivot, _sphere_mesh(0.220, 38, 22), hair_mat, Vector3(0, 0.40, -0.008))
			hair_top.scale = Vector3(1.05, 0.65, 0.88)
			var hair_back := _mesh(head_pivot, _sphere_mesh(0.218, 34, 16), hair_dark_mat, Vector3(0, 0.30, 0.055))
			hair_back.scale = Vector3(1.05, 0.68, 0.68)
			for sx in [-1.0, 1.0]:
				var side := _mesh(head_pivot, _sphere_mesh(0.075, 24, 14), hair_mat, Vector3(sx * 0.200, 0.32, 0.015))
				side.scale = Vector3(0.62, 0.95, 1.05)
				_mesh(head_pivot, _sphere_mesh(0.040, 14, 8), hair_dark_mat, Vector3(sx * 0.208, 0.20, -0.005)).scale = Vector3(0.45, 1.3, 0.55)
			var fringe := _mesh(head_pivot, _sphere_mesh(0.090, 20, 12), hair_mat, Vector3(0, 0.38, -0.160))
			fringe.scale = Vector3(1.50, 0.42, 0.70)
			# Hair clumps for volume.
			for i in range(6):
				var a := TAU * float(i) / 6.0
				var clump := _mesh(head_pivot, _sphere_mesh(0.058, 14, 8), hair_light_mat, Vector3(cos(a) * 0.145, 0.45 + sin(a) * 0.03, -0.02 + sin(a * 2.0) * 0.035))
				clump.scale = Vector3(1.0, 0.65, 1.0)
		else:
			# Short, styled masculine hair (ganteng) — neat, tapered.
			var hair_top := _mesh(head_pivot, _sphere_mesh(0.212, 36, 20), hair_mat, Vector3(0, 0.36, -0.010))
			hair_top.scale = Vector3(1.02, 0.55, 0.84)
			var hair_back := _mesh(head_pivot, _sphere_mesh(0.208, 32, 14), hair_dark_mat, Vector3(0, 0.26, 0.040))
			hair_back.scale = Vector3(1.02, 0.58, 0.60)
			for sx in [-1.0, 1.0]:
				var side := _mesh(head_pivot, _sphere_mesh(0.062, 20, 12), hair_mat, Vector3(sx * 0.185, 0.28, 0.010))
				side.scale = Vector3(0.52, 0.80, 0.98)
				_mesh(head_pivot, _sphere_mesh(0.032, 12, 6), hair_dark_mat, Vector3(sx * 0.192, 0.16, -0.005)).scale = Vector3(0.38, 1.0, 0.50)
			var fringe := _mesh(head_pivot, _sphere_mesh(0.078, 18, 11), hair_mat, Vector3(0, 0.34, -0.150))
			fringe.scale = Vector3(1.42, 0.34, 0.64)

	# ---- HIJAB — proper head covering for women who wear it ----
	if wear_hijab:
		# Hijab cap — covers head and neck.
		var hijab_cap := _mesh(head_pivot, _sphere_mesh(0.230, 36, 22), hijab_mat, Vector3(0, 0.30, 0.0))
		hijab_cap.scale = Vector3(1.0, 0.95, 0.90)
		# Hijab wrap — drapes around head and down neck.
		var hijab_wrap := _mesh(head_pivot, _capsule_mesh(0.240, 0.50, 32, 12), hijab_mat, Vector3(0, 0.15, 0.02))
		hijab_wrap.scale = Vector3(1.0, 1.0, 0.95)
		# Hijab side panels.
		for sx in [-1.0, 1.0]:
			_mesh(head_pivot, _box_mesh(Vector3(0.14, 0.45, 0.04)), hijab_mat, Vector3(sx * 0.185, 0.05, 0.05)).rotation.x = sx * 0.10
		# Hijab front edge — frames the face.
		_mesh(head_pivot, _box_mesh(Vector3(0.30, 0.10, 0.03)), hijab_mat, Vector3(0, 0.42, 0.08))
		# Undercap hairline peeking at forehead.
		var hairline := _mesh(head_pivot, _sphere_mesh(0.045, 16, 10), hair_mat, Vector3(0, 0.40, -0.135))
		hairline.scale = Vector3(1.35, 0.30, 0.55)

	# ---- EARS — anatomical with helix and earlobe ----
	for sx in [-1.0, 1.0]:
		var ear := _mesh(head_pivot, _sphere_mesh(0.052, 22, 14), skin_mat, Vector3(sx * 0.200, 0.16, -0.005))
		ear.scale = Vector3(0.46, 1.20, 0.62)
		_mesh(head_pivot, _sphere_mesh(0.028, 16, 10), dark_skin_mat, Vector3(sx * 0.206, 0.16, 0.020), Vector3(0.36, 0.92, 0.28))
		_mesh(head_pivot, _sphere_mesh(0.022, 12, 8), skin_mat, Vector3(sx * 0.202, 0.10, 0.005), Vector3(0.52, 0.82, 0.42))
		var helix := _mesh(head_pivot, _sphere_mesh(0.016, 12, 8), skin_mat, Vector3(sx * 0.204, 0.19, 0.012), Vector3(0.36, 1.05, 0.38))

	# ---- EYES — large, expressive, with lashes (women) ----
	var eye_white_mat := StandardMaterial3D.new()
	eye_white_mat.albedo_color = Color("#f4f2ed")
	eye_white_mat.roughness = 0.20
	eye_white_mat.metallic = 0.0
	eye_white_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX

	var iris_mat := StandardMaterial3D.new()
	iris_mat.albedo_color = Color("#3d5a2e")
	iris_mat.roughness = 0.08
	iris_mat.metallic = 0.10
	iris_mat.emission_enabled = true
	iris_mat.emission = Color("#4a6e38")
	iris_mat.emission_energy_multiplier = 0.03
	iris_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX

	var pupil_mat := StandardMaterial3D.new()
	pupil_mat.albedo_color = Color(0.01, 0.01, 0.01)
	pupil_mat.roughness = 0.03
	pupil_mat.metallic = 0.0

	var eyes: Array = []
	for sx in [-1.0, 1.0]:
		var eye_pivot := Node3D.new()
		eye_pivot.name = "EyePivot_%s" % str(sx)
		eye_pivot.position = Vector3(sx * 0.075, 0.245, -0.200)
		head_pivot.add_child(eye_pivot)
		# Eye white — larger sclera, pushed forward.
		var white := _mesh(eye_pivot, _sphere_mesh(0.030, 28, 18), eye_white_mat, Vector3.ZERO)
		white.scale = Vector3(1.35, 0.82, 1.0)
		eyes.append(eye_pivot)
		# Iris — colored, glossy.
		var iris := _mesh(eye_pivot, _sphere_mesh(0.021, 18, 12), iris_mat, Vector3(0, 0, -0.024))
		iris.scale = Vector3(1.08, 1.0, 0.58)
		# Pupil.
		_mesh(eye_pivot, _sphere_mesh(0.013, 14, 10), pupil_mat, Vector3(0, 0, -0.032), Vector3(1.0, 0.95, 0.4))
		# Upper eyelid.
		var lid_mat := StandardMaterial3D.new()
		lid_mat.albedo_color = skin.darkened(0.08)
		lid_mat.roughness = 0.66
		_mesh(eye_pivot, _box_mesh(Vector3(0.036, 0.007, 0.014)), lid_mat, Vector3(0, 0.018, -0.016))
		# Eyeshadow (women only, above eyelid).
		if is_female:
			_mesh(head_pivot, _box_mesh(Vector3(0.042, 0.010, 0.018)), eyeshadow_mat, Vector3(sx * 0.072, 0.265, -0.195)).rotation.z = sx * 0.08
		# Lower lash line.
		_mesh(eye_pivot, _box_mesh(Vector3(0.032, 0.005, 0.010)), lid_mat, Vector3(0, -0.016, -0.014))
		# Eyelashes (women only — longer, more defined).
		if is_female:
			# Upper lashes.
			for lx in [-0.012, 0.0, 0.012]:
				_mesh(eye_pivot, _box_mesh(Vector3(0.006, 0.016, 0.004)), lash_mat, Vector3(lx, 0.022, -0.018))
			# Lower lashes.
			for lx in [-0.010, 0.0, 0.010]:
				_mesh(eye_pivot, _box_mesh(Vector3(0.006, 0.012, 0.004)), lash_mat, Vector3(lx, -0.018, -0.016))
		# Eye corner.
		var corner_mat := StandardMaterial3D.new()
		corner_mat.albedo_color = skin.darkened(0.12)
		corner_mat.roughness = 0.52
		_mesh(eye_pivot, _sphere_mesh(0.009, 10, 6), corner_mat, Vector3(sx * -0.024, 0, -0.016), Vector3(0.55, 0.85, 0.55))

	# ---- EYEBROWS — defined arches (thicker men, arched thinner women) ----
	var brow_mat := hair_material(hair.darkened(0.10))
	for sx in [-1.0, 1.0]:
		var brow_thickness := 0.024 if not is_female else 0.018
		var brow_width := 0.095 if not is_female else 0.085
		var brow := _mesh(head_pivot, _box_mesh(Vector3(brow_width, brow_thickness, 0.036)), brow_mat, Vector3(sx * 0.075, 0.295, -0.194))
		brow.rotation.z = sx * 0.07
		brow.rotation.x = -0.04
		brow.scale = Vector3(1.0, 1.0, 1.0)
		# Brow tail — thinner end.
		var tail := _mesh(head_pivot, _box_mesh(Vector3(0.032, 0.016 if not is_female else 0.012, 0.026)), brow_mat, Vector3(sx * 0.122, 0.278, -0.190))
		tail.rotation.z = sx * 0.14

	# ---- NOSE — bridge, tip, nostrils, with depth ----
	var nose_bridge := _mesh(head_pivot, _box_mesh(Vector3(0.040, 0.096, 0.036)), dark_skin_mat, Vector3(0, 0.180, -0.218))
	nose_bridge.rotation.x = 0.05
	for sx in [-1.0, 1.0]:
		_mesh(head_pivot, _box_mesh(Vector3(0.016, 0.065, 0.022)), dark_skin_mat, Vector3(sx * 0.022, 0.180, -0.208))
	var nose_tip_scale := 1.25 if is_female else 1.35
	var nose_tip := _mesh(head_pivot, _sphere_mesh(0.028, 18, 12), skin_mat, Vector3(0, 0.132, -0.228))
	nose_tip.scale = Vector3(nose_tip_scale, 0.85, 1.02)
	for sx in [-1.0, 1.0]:
		var nostril := _mesh(head_pivot, _sphere_mesh(0.014, 12, 8), dark_skin_mat, Vector3(sx * 0.020, 0.116, -0.226))
		nostril.scale = Vector3(1.0, 0.68, 0.58)
		var nostril_dark_mat := StandardMaterial3D.new()
		nostril_dark_mat.albedo_color = Color(0.08, 0.04, 0.04)
		nostril_dark_mat.roughness = 0.82
		_mesh(head_pivot, _sphere_mesh(0.009, 10, 6), nostril_dark_mat, Vector3(sx * 0.020, 0.112, -0.230), Vector3(1.0, 0.52, 0.42))
	# Nasolabial fold.
	for sx in [-1.0, 1.0]:
		var fold := _mesh(head_pivot, _box_mesh(Vector3(0.011, 0.055, 0.013)), dark_skin_mat, Vector3(sx * 0.040, 0.090, -0.208))
		fold.rotation.z = sx * 0.20
	# Philtrum.
	_mesh(head_pivot, _box_mesh(Vector3(0.018, 0.028, 0.020)), dark_skin_mat, Vector3(0, 0.108, -0.210))

	# ---- LIPS — fuller for women with lipstick, defined for men ----
	var lip_mat := StandardMaterial3D.new()
	lip_mat.albedo_color = skin.darkened(0.12).lerp(Color("#8a4a3a"), 0.15)
	lip_mat.roughness = 0.36
	lip_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	var upper_lip_scale := 1.05 if is_female else 1.0
	var lower_lip_scale := 1.10 if is_female else 1.0
	var upper_lip_thickness := 0.026 if is_female else 0.022
	var lower_lip_thickness := 0.032 if is_female else 0.026
	var upper_lip := _mesh(head_pivot, _box_mesh(Vector3(0.102 * upper_lip_scale, upper_lip_thickness, 0.028)), lipstick_mat if is_female else lip_mat, Vector3(0, 0.095, -0.216))
	upper_lip.scale = Vector3(1.0, 0.72, 0.85)
	var lower_lip := _mesh(head_pivot, _box_mesh(Vector3(0.092 * lower_lip_scale, lower_lip_thickness, 0.028)), lipstick_mat if is_female else lip_mat, Vector3(0, 0.068, -0.214))
	lower_lip.scale = Vector3(1.0, 1.0, 0.85)
	_mesh(head_pivot, _box_mesh(Vector3(0.088, 0.005, 0.011)), dark_skin_mat, Vector3(0, 0.082, -0.219)).scale = Vector3(1.0, 1.0, 0.8)

	# ---- STUBBLE (male only — 5 o'clock shadow, ganteng) ----
	if not is_female:
		var stubble_areas := [
			Vector3(0.0, 0.125, -0.195),   # above lip
			Vector3(-0.055, 0.060, -0.185), # left cheek
			Vector3(0.055, 0.060, -0.185),  # right cheek
			Vector3(0.0, 0.020, -0.180),    # chin
		]
		for sa in stubble_areas:
			_mesh(head_pivot, _sphere_mesh(0.028, 14, 8), stubble_mat, sa).scale = Vector3(0.7, 0.6, 0.4)

	# ---- ARMS — shoulder → upper arm → elbow → forearm → wrist → hand ----
	var arms: Array[Node3D] = []
	for side in [-1.0, 1.0]:
		var shoulder := Node3D.new()
		shoulder.name = "ArmPivot_%s" % ("L" if side < 0 else "R")
		shoulder.position = Vector3(side * 0.310 * bt_shoulder_w * male_shoulder_boost, 1.62, 0)
		body.add_child(shoulder)
		# Upper arm — sleeve.
		_mesh(shoulder, _capsule_mesh(0.086, 0.35, 24, 10), fabric_mat, Vector3(0, -0.175, 0))
		# Deltoid bulge.
		_mesh(shoulder, _sphere_mesh(0.092, 20, 12), shirt_light, Vector3(0, -0.02, 0)).scale = Vector3(1.08, 0.72, 1.02)
		# Elbow joint.
		_mesh(shoulder, _sphere_mesh(0.070, 20, 12), dark_skin_mat, Vector3(0, -0.35, 0))
		# Forearm — skin.
		_mesh(shoulder, _capsule_mesh(0.064, 0.35, 20, 10), skin_mat, Vector3(0, -0.53, 0))
		# Forearm muscle hint.
		_mesh(shoulder, _sphere_mesh(0.060, 16, 10), skin_mat, Vector3(0, -0.59, 0)).scale = Vector3(0.92, 0.62, 0.88)
		# Wrist.
		_mesh(shoulder, _sphere_mesh(0.048, 16, 10), skin_mat, Vector3(0, -0.70, 0))
		# Wristwatch.
		var watch_mat := metallic_material(Color("#2a2e30"), 0.20, 0.5)
		_mesh(shoulder, _cylinder_mesh(0.050, 0.048, 0.042, 16), watch_mat, Vector3(0, -0.67, 0))
		_mesh(shoulder, _sphere_mesh(0.017, 12, 8), metallic_material(Color("#1a1a1a"), 0.15, 0.3), Vector3(0, -0.67, -0.042))

		# Hand — palm with detailed fingers.
		var hand := Node3D.new()
		hand.position = Vector3(0, -0.77, 0)
		shoulder.add_child(hand)
		var palm := _mesh(hand, _box_mesh(Vector3(0.115, 0.040, 0.140)), skin_mat, Vector3(0, -0.036, 0))
		palm.scale = Vector3(1.0, 1.0, 1.0)
		for fi in range(4):
			var fx: float = -0.038 + float(fi) * 0.026
			_mesh(hand, _sphere_mesh(0.015, 12, 8), dark_skin_mat, Vector3(fx, -0.064, -0.006)).scale = Vector3(0.82, 0.62, 0.72)
		for fi in range(4):
			var fx: float = -0.038 + float(fi) * 0.026
			var finger_length: float = 0.085 if fi == 2 else (0.078 if fi == 1 else (0.070 if fi == 0 else 0.068))
			var p1 := _mesh(hand, _capsule_mesh(0.013, finger_length, 12, 6), skin_mat, Vector3(fx, -0.088, -0.006))
			_mesh(hand, _sphere_mesh(0.012, 10, 7), dark_skin_mat, Vector3(fx, -0.088 - finger_length * 0.5, -0.004)).scale = Vector3(0.8, 0.52, 0.72)
			var distal_len := finger_length * 0.65
			_mesh(hand, _capsule_mesh(0.011, distal_len, 10, 6), skin_mat, Vector3(fx, -0.088 - finger_length * 0.5 - distal_len * 0.5, -0.004))
			_mesh(hand, _box_mesh(Vector3(0.015, 0.005, 0.011)), light_skin_mat, Vector3(fx, -0.088 - finger_length * 0.5 - distal_len + 0.006, -0.013))
		var thumb := _mesh(hand, _capsule_mesh(0.016, 0.060, 12, 6), skin_mat, Vector3(-0.056 if side < 0 else 0.056, -0.052, 0.020))
		thumb.rotation.z = side * 0.62
		thumb.rotation.x = 0.16
		_mesh(hand, _sphere_mesh(0.013, 10, 7), skin_mat, Vector3(-0.062 if side < 0 else 0.062, -0.082, 0.022)).scale = Vector3(0.72, 0.62, 0.72)

		arms.append(shoulder)

	# ---- LEGS — hip → thigh → knee → shin → ankle → shoe ----
	var legs: Array[Node3D] = []
	var leg_len := 0.90 * bt_leg_w
	for side in [-1.0, 1.0]:
		var hip := Node3D.new()
		hip.name = "LegPivot_%s" % ("L" if side < 0 else "R")
		hip.position = Vector3(side * 0.152 * bt_shoulder_w * male_shoulder_boost, 0.80, 0)
		body.add_child(hip)
		# Thigh — tapered.
		_mesh(hip, _capsule_mesh(0.098 * bt_leg_w, leg_len * 0.5, 24, 10), pants_mat, Vector3(0, -leg_len * 0.25, 0))
		_mesh(hip, _sphere_mesh(0.088 * bt_leg_w, 16, 10), pants_dark, Vector3(0, -leg_len * 0.22, 0.02)).scale = Vector3(0.94, 0.56, 0.90)
		# Knee joint.
		_mesh(hip, _sphere_mesh(0.084 * bt_leg_w, 20, 12), dark_skin_mat, Vector3(0, -leg_len * 0.5, 0))
		_mesh(hip, _sphere_mesh(0.060 * bt_leg_w, 16, 10), skin_mat, Vector3(0, -leg_len * 0.5, -0.03)).scale = Vector3(0.82, 0.52, 0.68)
		# Shin.
		_mesh(hip, _capsule_mesh(0.076 * bt_leg_w, leg_len * 0.5, 20, 10), pants_mat, Vector3(0, -leg_len * 0.75, 0))
		_mesh(hip, _sphere_mesh(0.068 * bt_leg_w, 16, 10), pants_dark, Vector3(0, -leg_len * 0.80, -0.02)).scale = Vector3(0.88, 0.56, 0.84)
		# Ankle.
		_mesh(hip, _sphere_mesh(0.052 * bt_leg_w, 16, 10), skin_mat, Vector3(0, -leg_len * 0.99, 0))
		# Sock.
		_mesh(hip, _cylinder_mesh(0.054 * bt_leg_w, 0.057 * bt_leg_w, 0.085, 16), fabric_material(Color("#e8e6e0"), 0.82), Vector3(0, -leg_len * 1.00, 0))
		# Shoe.
		var shoe := _mesh(hip, _box_mesh(Vector3(0.185 * bt_leg_w, 0.092 * bt_leg_w, 0.33 * bt_leg_w)), shoe_mat, Vector3(0, -leg_len * 1.06, -0.03 * bt_leg_w))
		shoe.scale = Vector3(1.0, 0.86, 1.0)
		var toe := _mesh(hip, _sphere_mesh(0.074 * bt_leg_w, 16, 10), shoe_mat, Vector3(0, -leg_len * 1.08, -0.15 * bt_leg_w))
		toe.scale = Vector3(1.28, 0.66, 0.80)
		_mesh(hip, _sphere_mesh(0.054 * bt_leg_w, 14, 8), shoe_mat, Vector3(0, -leg_len * 1.05, 0.09 * bt_leg_w), Vector3(0.92, 0.60, 1.08))
		var sole_mat := StandardMaterial3D.new()
		sole_mat.albedo_color = Color("#2a2e30")
		sole_mat.roughness = 0.55
		sole_mat.metallic = 0.05
		_mesh(hip, _box_mesh(Vector3(0.195 * bt_leg_w, 0.026 * bt_leg_w, 0.35 * bt_leg_w)), sole_mat, Vector3(0, -leg_len * 1.13, -0.03 * bt_leg_w))
		for ly in [-leg_len * 1.04, -leg_len * 1.06, -leg_len * 1.08]:
			_mesh(hip, _box_mesh(Vector3(0.125 * bt_leg_w, 0.009 * bt_leg_w, 0.020 * bt_leg_w)), fabric_material(Color("#d0c8b8"), 0.7), Vector3(0, ly, -0.08 * bt_leg_w))
		_mesh(hip, _box_mesh(Vector3(0.105 * bt_leg_w, 0.062 * bt_leg_w, 0.085 * bt_leg_w)), shoe_mat, Vector3(0, -leg_len * 1.02, -0.06 * bt_leg_w))

		legs.append(hip)

	# ---- BADGE / NAME TAG ----
	var badge_mat := StandardMaterial3D.new()
	badge_mat.albedo_color = Color("#e0dfd0")
	badge_mat.roughness = 0.26
	badge_mat.metallic = 0.24
	badge_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	_mesh(body, _box_mesh(Vector3(0.145, 0.185, 0.026)), badge_mat, Vector3(0.110, 1.46, -0.24))
	_mesh(body, _box_mesh(Vector3(0.019, 0.055, 0.009)), metallic_material(Color("#999"), 0.3, 0.5), Vector3(0.110, 1.55, -0.247))
	_mesh(body, _box_mesh(Vector3(0.085, 0.028, 0.009)), fabric_material(Color("#597d6e"), 0.5), Vector3(0.110, 1.49, -0.247))

	# ---- LABELS ----
	var label := Label3D.new()
	label.text = label_text
	label.position = Vector3(0, 2.72, 0)
	label.font_size = 26
	label.outline_size = 5
	label.modulate = Color("#f4f3ed")
	label.outline_modulate = Color(0.04, 0.07, 0.065, 0.88)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.pixel_size = 0.006
	label.visible = false
	body.add_child(label)

	var status_label := Label3D.new()
	status_label.text = "IDLE"
	status_label.position = Vector3(0, 2.48, 0)
	status_label.font_size = 15
	status_label.outline_size = 4
	status_label.modulate = Color("#d7e1da")
	status_label.outline_modulate = Color(0.04, 0.07, 0.065, 0.88)
	status_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	status_label.no_depth_test = true
	status_label.pixel_size = 0.005
	status_label.visible = false
	body.add_child(status_label)

	return {
		"arms": arms,
		"legs": legs,
		"eyes": eyes,
		"head_pivot": head_pivot,
		"label": label,
		"status_label": status_label,
		"visual": body,
	}
