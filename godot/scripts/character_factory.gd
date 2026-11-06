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
	mat.roughness = 0.58
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	# Subsurface scattering approximation — warm inner glow.
	mat.emission_enabled = true
	mat.emission = base.lightened(0.20)
	mat.emission_energy_multiplier = 0.08
	# Rim lighting for depth.
	mat.rim_enabled = true
	mat.rim = 0.40
	mat.rim_tint = 0.50
	return mat

static func fabric_material(color: Color, roughness: float = 0.88) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = 0.0
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	# Subtle fabric sheen.
	mat.rim_enabled = true
	mat.rim = 0.15
	mat.rim_tint = 0.3
	return mat

static func leather_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.32
	mat.metallic = 0.05
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	return mat

static func hair_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.78
	mat.metallic = 0.02
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	# Subtle rim for natural hair sheen.
	mat.rim_enabled = true
	mat.rim = 0.25
	mat.rim_tint = 0.6
	return mat

static func metallic_material(color: Color, roughness: float = 0.25, metallic: float = 0.7) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.metallic = metallic
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
	# Use a capsule with custom scale to approximate a tapered torso.
	# The caller scales it further for precise proportions.
	var m := CapsuleMesh.new()
	m.radius = (width_bottom + width_top) * 0.25
	m.height = height
	m.radial_segments = 28
	m.rings = 12
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

static func build(parent: Node3D, shirt: Color, hair: Color, label_text: String, employee_id: String = "", skin: Color = Color("#c89e84")):
	var external := _build_from_glb(parent, employee_id, label_text)
	if not external.is_empty():
		return external

	# -- Procedural detailed humanoid with enhanced proportions --
	var body := Node3D.new()
	body.name = "HumanoidVisual"
	parent.add_child(body)

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

	# ---- TORSO — anatomically tapered from shoulders to waist ----
	# Upper chest — broad shoulders with natural taper.
	var chest := _mesh(body, _tapered_torso(0.62, 0.42, 0.40, 0.52), fabric_mat, Vector3(0, 1.42, 0))
	chest.scale = Vector3(1.05, 1.0, 0.80)
	# Upper back — slightly narrower for natural posture.
	_mesh(body, _capsule_mesh(0.235, 0.34, 28, 12), shirt_dark, Vector3(0, 1.50, -0.04)).scale = Vector3(1.0, 0.8, 0.72)
	# Mid torso — waist narrows naturally.
	var waist := _mesh(body, _tapered_torso(0.48, 0.42, 0.36, 0.36), shirt_dark, Vector3(0, 1.12, 0))
	waist.scale = Vector3(1.0, 1.0, 0.80)
	# Hips / pelvis — wider than waist.
	var pelvis := _mesh(body, _capsule_mesh(0.248, 0.32, 24, 6), pants_mat, Vector3(0, 0.82, 0))
	pelvis.scale = Vector3(1.04, 1.0, 0.80)
	# Glutes for seated posture.
	_mesh(body, _sphere_mesh(0.085, 20, 10), pants_mat, Vector3(-0.09, 0.74, -0.12)).scale = Vector3(1.1, 0.7, 0.85)
	_mesh(body, _sphere_mesh(0.085, 20, 10), pants_mat, Vector3(0.09, 0.74, -0.12)).scale = Vector3(1.1, 0.7, 0.85)

	# Neck — tapered cylinder with natural slope.
	_mesh(body, _cylinder_mesh(0.062, 0.082, 0.15, 16), skin_mat, Vector3(0, 1.74, 0))
	# Adam's apple hint.
	_mesh(body, _sphere_mesh(0.022, 12, 6), skin_mat, Vector3(0, 1.73, -0.072)).scale = Vector3(0.8, 1.2, 0.6)

	# Shoulder caps — deltoid membulat tapi proporsional lebih ramping.
	for sx in [-0.302, 0.302]:
		var deltoid := _mesh(body, _sphere_mesh(0.084, 24, 12), fabric_mat, Vector3(sx, 1.62, -0.01))
		deltoid.scale = Vector3(1.0, 0.82, 0.90)

	# Shirt collar — V-neck with depth.
	var collar := _mesh(body, _box_mesh(Vector3(0.26, 0.06, 0.14)), shirt_light, Vector3(0, 1.68, -0.11))
	collar.rotation.x = 0.14
	# Collar points.
	for sx in [-0.08, 0.08]:
		var point := _mesh(body, _box_mesh(Vector3(0.06, 0.05, 0.02)), shirt_light, Vector3(sx, 1.65, -0.15))
		point.rotation.x = 0.20
		point.rotation.z = sx * 0.08
	# Button line.
	for y in [1.55, 1.42, 1.29, 1.16, 1.03]:
		_mesh(body, _sphere_mesh(0.012, 10, 6), metallic_material(Color("#888070"), 0.35, 0.4), Vector3(0, y, -0.188))
	# Belt.
	_mesh(body, _box_mesh(Vector3(0.46, 0.05, 0.34)), leather_material(Color("#1a1a1a")), Vector3(0, 0.88, 0))
	# Belt buckle.
	_mesh(body, _box_mesh(Vector3(0.10, 0.05, 0.02)), metallic_material(Color("#9a8a5a"), 0.25, 0.6), Vector3(0, 0.88, -0.17))
	# Shirt cuffs at wrists will be added with arms below.

	# ---- HEAD — realistic skull with defined jaw and facial features ----
	var head_pivot := Node3D.new()
	head_pivot.name = "HeadPivot"
	head_pivot.position = Vector3(0, 1.82, 0)
	body.add_child(head_pivot)

	# Head — slightly elongated skull, wider at temples.
	var head := _mesh(head_pivot, _sphere_mesh(0.205, 40, 24), skin_mat, Vector3(0, 0.22, -0.005))
	head.scale = Vector3(0.94, 1.08, 0.88)
	# Forehead — smooth bulge.
	var forehead := _mesh(head_pivot, _sphere_mesh(0.10, 24, 12), light_skin_mat, Vector3(0, 0.36, -0.04))
	forehead.scale = Vector3(1.35, 0.55, 0.82)
	# Jaw — defined lower face with chin.
	var jaw := _mesh(head_pivot, _sphere_mesh(0.178, 30, 16), dark_skin_mat, Vector3(0, 0.06, 0.04))
	jaw.scale = Vector3(0.92, 0.54, 0.98)
	# Chin — defined projection.
	var chin := _mesh(head_pivot, _sphere_mesh(0.055, 18, 10), skin_mat, Vector3(0, 0.005, 0.10))
	chin.scale = Vector3(0.7, 0.5, 0.75)
	# Cheekbones — subtle definition.
	for sx in [-1.0, 1.0]:
		var cheek := _mesh(head_pivot, _sphere_mesh(0.045, 14, 8), dark_skin_mat, Vector3(sx * 0.125, 0.13, -0.02))
		cheek.scale = Vector3(0.8, 0.62, 0.55)
	# Temple — slight indentation for skull shape.
	for sx in [-1.0, 1.0]:
		_mesh(head_pivot, _sphere_mesh(0.038, 12, 6), dark_skin_mat, Vector3(sx * 0.15, 0.22, -0.01)).scale = Vector3(0.6, 0.8, 0.5)

	# ---- HAIR — multi-layered with natural volume ----
	# Crown — main volume. Kedalaman-z dipangkas supaya puncak rambut tak menjorok
	# ke depan melewati bidang mata/browo.
	var hair_top := _mesh(head_pivot, _sphere_mesh(0.216, 36, 20), hair_mat, Vector3(0, 0.37, -0.008))
	hair_top.scale = Vector3(1.02, 0.60, 0.86)
	# Back — flowing back hair. Dikecilkan & digeser ke belakang agar tidak
	# menelan wajah depan (elipsoid penuh dulu menutupi mata dari depan).
	var hair_back := _mesh(head_pivot, _sphere_mesh(0.212, 32, 14), hair_dark_mat, Vector3(0, 0.28, 0.045))
	hair_back.scale = Vector3(1.02, 0.62, 0.62)
	# Side hair / temples.
	for sx in [-1.0, 1.0]:
		var side := _mesh(head_pivot, _sphere_mesh(0.068, 22, 12), hair_mat, Vector3(sx * 0.188, 0.30, 0.012))
		side.scale = Vector3(0.58, 0.90, 1.02)
		# Sideburn hint.
		_mesh(head_pivot, _sphere_mesh(0.035, 12, 6), hair_dark_mat, Vector3(sx * 0.195, 0.18, -0.005)).scale = Vector3(0.4, 1.2, 0.5)
	# Front fringe — natural hairline.
	var fringe := _mesh(head_pivot, _sphere_mesh(0.082, 18, 10), hair_mat, Vector3(0, 0.35, -0.155))
	fringe.scale = Vector3(1.45, 0.38, 0.65)
		# Top texture — subtle hair clumps for volume.
	for i in range(5):
		var a := TAU * float(i) / 5.0
		var clump := _mesh(head_pivot, _sphere_mesh(0.052, 12, 6), hair_light_mat, Vector3(cos(a) * 0.13, 0.43 + sin(a) * 0.025, -0.02 + sin(a * 2.0) * 0.03))
		clump.scale = Vector3(1.0, 0.60, 0.95)

	# ---- EARS — anatomical with helix and earlobe ----
	for sx in [-1.0, 1.0]:
		# Outer ear.
		var ear := _mesh(head_pivot, _sphere_mesh(0.050, 20, 12), skin_mat, Vector3(sx * 0.194, 0.17, -0.005))
		ear.scale = Vector3(0.44, 1.18, 0.60)
		# Inner ear — darker recess.
		_mesh(head_pivot, _sphere_mesh(0.026, 14, 8), dark_skin_mat, Vector3(sx * 0.200, 0.17, 0.018), Vector3(0.35, 0.9, 0.25))
		# Earlobe.
		_mesh(head_pivot, _sphere_mesh(0.020, 10, 6), skin_mat, Vector3(sx * 0.196, 0.105, 0.005), Vector3(0.5, 0.8, 0.4))
		# Helix — curved ridge.
		var helix := _mesh(head_pivot, _sphere_mesh(0.015, 10, 6), skin_mat, Vector3(sx * 0.198, 0.20, 0.01), Vector3(0.35, 1.0, 0.35))

	# ---- EYES — detailed with whites, iris, pupil, eyelids ----
	var eye_white_mat := StandardMaterial3D.new()
	eye_white_mat.albedo_color = Color("#f4f2ed")
	eye_white_mat.roughness = 0.22
	eye_white_mat.metallic = 0.0
	eye_white_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX

	var iris_mat := StandardMaterial3D.new()
	iris_mat.albedo_color = Color("#3d5a2e")
	iris_mat.roughness = 0.10
	iris_mat.metallic = 0.10
	iris_mat.emission_enabled = true
	iris_mat.emission = Color("#4a6e38")
	iris_mat.emission_energy_multiplier = 0.03
	iris_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX

	var pupil_mat := StandardMaterial3D.new()
	pupil_mat.albedo_color = Color(0.01, 0.01, 0.01)
	pupil_mat.roughness = 0.04
	pupil_mat.metallic = 0.0

	var eyes: Array = []
	for sx in [-1.0, 1.0]:
		# Eye pivot for blink.
		var eye_pivot := Node3D.new()
		eye_pivot.name = "EyePivot_%s" % str(sx)
		eye_pivot.position = Vector3(sx * 0.072, 0.235, -0.196)
		head_pivot.add_child(eye_pivot)
		# Eye white — larger sclera, pushed forward so the eye reads clearly.
		var white := _mesh(eye_pivot, _sphere_mesh(0.028, 24, 14), eye_white_mat, Vector3.ZERO)
		white.scale = Vector3(1.30, 0.78, 0.95)
		eyes.append(eye_pivot)
		# Iris — colored circle facing forward.
		var iris := _mesh(eye_pivot, _sphere_mesh(0.019, 16, 10), iris_mat, Vector3(0, 0, -0.022))
		iris.scale = Vector3(1.05, 1.0, 0.55)
		# Pupil.
		_mesh(eye_pivot, _sphere_mesh(0.012, 12, 6), pupil_mat, Vector3(0, 0, -0.030), Vector3(1.0, 0.95, 0.4))
		# Upper eyelid hint.
		var lid_mat := StandardMaterial3D.new()
		lid_mat.albedo_color = skin.darkened(0.08)
		lid_mat.roughness = 0.68
		_mesh(eye_pivot, _box_mesh(Vector3(0.034, 0.006, 0.012)), lid_mat, Vector3(0, 0.015, -0.014))
		# Lower lash line.
		_mesh(eye_pivot, _box_mesh(Vector3(0.030, 0.004, 0.008)), lid_mat, Vector3(0, -0.014, -0.012))
		# Eye corner — slight skin tone shift.
		var corner_mat := StandardMaterial3D.new()
		corner_mat.albedo_color = skin.darkened(0.12)
		corner_mat.roughness = 0.55
		_mesh(eye_pivot, _sphere_mesh(0.008, 8, 4), corner_mat, Vector3(sx * -0.022, 0, -0.014), Vector3(0.5, 0.8, 0.5))

	# ---- EYEBROWS — defined arches ----
	var brow_mat := hair_material(hair.darkened(0.10))
	for sx in [-1.0, 1.0]:
		# Main brow — angled for expression.
		var brow := _mesh(head_pivot, _box_mesh(Vector3(0.090, 0.020, 0.034)), brow_mat, Vector3(sx * 0.072, 0.285, -0.192))
		brow.rotation.z = sx * 0.06
		brow.rotation.x = -0.03
		brow.scale = Vector3(1.0, 1.0, 1.0)
		# Brow tail — thinner end.
		var tail := _mesh(head_pivot, _box_mesh(Vector3(0.030, 0.014, 0.024)), brow_mat, Vector3(sx * 0.118, 0.27, -0.188))
		tail.rotation.z = sx * 0.12

	# ---- NOSE — bridge, tip, nostrils, with depth ----
	var nose_bridge := _mesh(head_pivot, _box_mesh(Vector3(0.038, 0.092, 0.034)), dark_skin_mat, Vector3(0, 0.175, -0.214))
	nose_bridge.rotation.x = 0.04
	# Nose bridge sides — for natural width.
	for sx in [-1.0, 1.0]:
		_mesh(head_pivot, _box_mesh(Vector3(0.014, 0.06, 0.020)), dark_skin_mat, Vector3(sx * 0.020, 0.175, -0.205))
	# Nose tip — rounded, sedikit lebih besar & menonjol agar s tombak profil terbaca.
	var nose_tip := _mesh(head_pivot, _sphere_mesh(0.026, 16, 10), skin_mat, Vector3(0, 0.128, -0.224))
	nose_tip.scale = Vector3(1.30, 0.88, 1.05)
	# Nostrils — defined openings.
	for sx in [-1.0, 1.0]:
		var nostril := _mesh(head_pivot, _sphere_mesh(0.013, 10, 6), dark_skin_mat, Vector3(sx * 0.018, 0.113, -0.222))
		nostril.scale = Vector3(1.0, 0.65, 0.55)
		# Nostril opening — darker.
		var nostril_dark_mat := StandardMaterial3D.new()
		nostril_dark_mat.albedo_color = Color(0.08, 0.04, 0.04)
		nostril_dark_mat.roughness = 0.8
		_mesh(head_pivot, _sphere_mesh(0.008, 8, 4), nostril_dark_mat, Vector3(sx * 0.018, 0.110, -0.226), Vector3(1.0, 0.5, 0.4))
	# Nasolabial fold — subtle line from nose to mouth.
	for sx in [-1.0, 1.0]:
		var fold := _mesh(head_pivot, _box_mesh(Vector3(0.010, 0.052, 0.012)), dark_skin_mat, Vector3(sx * 0.038, 0.088, -0.206))
		fold.rotation.z = sx * 0.18
	# Philtrum — groove above upper lip.
	_mesh(head_pivot, _box_mesh(Vector3(0.016, 0.026, 0.018)), dark_skin_mat, Vector3(0, 0.105, -0.208))

	# ---- LIPS — upper and lower with natural shape ----
	var lip_mat := StandardMaterial3D.new()
	lip_mat.albedo_color = skin.darkened(0.12).lerp(Color("#8a4a3a"), 0.15)
	lip_mat.roughness = 0.38
	lip_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	# Upper lip — cupid's bow shape.
	var upper_lip := _mesh(head_pivot, _box_mesh(Vector3(0.098, 0.022, 0.026)), lip_mat, Vector3(0, 0.093, -0.213))
	upper_lip.scale = Vector3(1.0, 0.68, 0.82)
	# Lower lip — fuller.
	var lower_lip := _mesh(head_pivot, _box_mesh(Vector3(0.088, 0.028, 0.026)), lip_mat, Vector3(0, 0.068, -0.212))
	lower_lip.scale = Vector3(1.0, 1.0, 0.82)
	# Lip line — subtle shadow.
	_mesh(head_pivot, _box_mesh(Vector3(0.085, 0.004, 0.010)), dark_skin_mat, Vector3(0, 0.080, -0.217)).scale = Vector3(1.0, 1.0, 0.8)

	# ---- ARMS — shoulder → upper arm → elbow → forearm → wrist → hand ----
	var arms: Array[Node3D] = []
	for side in [-1.0, 1.0]:
		var shoulder := Node3D.new()
		shoulder.name = "ArmPivot_%s" % ("L" if side < 0 else "R")
		shoulder.position = Vector3(side * 0.302, 1.60, 0)
		body.add_child(shoulder)
		# Upper arm — sleeve with slight taper.
		_mesh(shoulder, _capsule_mesh(0.084, 0.34, 22, 8), fabric_mat, Vector3(0, -0.17, 0))
		# Deltoid bulge.
		_mesh(shoulder, _sphere_mesh(0.088, 18, 10), shirt_light, Vector3(0, -0.02, 0)).scale = Vector3(1.05, 0.7, 1.0)
		# Elbow joint.
		_mesh(shoulder, _sphere_mesh(0.068, 18, 10), dark_skin_mat, Vector3(0, -0.34, 0))
		# Forearm — skin (rolled up sleeves look).
		_mesh(shoulder, _capsule_mesh(0.062, 0.34, 18, 8), skin_mat, Vector3(0, -0.52, 0))
		# Forearm muscle hint.
		_mesh(shoulder, _sphere_mesh(0.058, 14, 8), skin_mat, Vector3(0, -0.58, 0)).scale = Vector3(0.9, 0.6, 0.85)
		# Wrist.
		_mesh(shoulder, _sphere_mesh(0.046, 14, 8), skin_mat, Vector3(0, -0.69, 0))
		# Wristwatch.
		var watch_mat := metallic_material(Color("#2a2e30"), 0.20, 0.5)
		_mesh(shoulder, _cylinder_mesh(0.048, 0.046, 0.04, 16), watch_mat, Vector3(0, -0.66, 0))
		# Watch face.
		_mesh(shoulder, _sphere_mesh(0.016, 10, 6), metallic_material(Color("#1a1a1a"), 0.15, 0.3), Vector3(0, -0.66, -0.040))

		# Hand — palm with detailed fingers.
		var hand := Node3D.new()
		hand.position = Vector3(0, -0.76, 0)
		shoulder.add_child(hand)
		# Palm — anatomical shape.
		var palm := _mesh(hand, _box_mesh(Vector3(0.11, 0.038, 0.135)), skin_mat, Vector3(0, -0.035, 0))
		palm.scale = Vector3(1.0, 1.0, 1.0)
		# Knuckles — defined bumps.
		for fi in range(4):
			var fx: float = -0.036 + float(fi) * 0.024
			_mesh(hand, _sphere_mesh(0.014, 10, 6), dark_skin_mat, Vector3(fx, -0.062, -0.005)).scale = Vector3(0.8, 0.6, 0.7)
		# Fingers — 4 fingers with 2 segments each, proper proportions.
		for fi in range(4):
			var fx: float = -0.036 + float(fi) * 0.024
			var finger_length: float = 0.082 if fi == 2 else (0.075 if fi == 1 else (0.068 if fi == 0 else 0.065))
			# Proximal phalanx.
			var p1 := _mesh(hand, _capsule_mesh(0.012, finger_length, 10, 4), skin_mat, Vector3(fx, -0.085, -0.005))
			# Middle joint.
			_mesh(hand, _sphere_mesh(0.011, 8, 5), dark_skin_mat, Vector3(fx, -0.085 - finger_length * 0.5, -0.003)).scale = Vector3(0.8, 0.5, 0.7)
			# Distal phalanx — shorter.
			var distal_len := finger_length * 0.65
			_mesh(hand, _capsule_mesh(0.010, distal_len, 8, 4), skin_mat, Vector3(fx, -0.085 - finger_length * 0.5 - distal_len * 0.5, -0.003))
			# Fingernail hint.
			_mesh(hand, _box_mesh(Vector3(0.014, 0.004, 0.010)), light_skin_mat, Vector3(fx, -0.085 - finger_length * 0.5 - distal_len + 0.005, -0.012))
		# Thumb — angled, shorter.
		var thumb := _mesh(hand, _capsule_mesh(0.015, 0.058, 10, 4), skin_mat, Vector3(-0.054 if side < 0 else 0.054, -0.05, 0.018))
		thumb.rotation.z = side * 0.6
		thumb.rotation.x = 0.15
		# Thumb tip.
		_mesh(hand, _sphere_mesh(0.012, 8, 5), skin_mat, Vector3(-0.060 if side < 0 else 0.060, -0.08, 0.020)).scale = Vector3(0.7, 0.6, 0.7)

		arms.append(shoulder)

	# ---- LEGS — hip → thigh → knee → shin → ankle → shoe ----
	var legs: Array[Node3D] = []
	for side in [-1.0, 1.0]:
		var hip := Node3D.new()
		hip.name = "LegPivot_%s" % ("L" if side < 0 else "R")
		hip.position = Vector3(side * 0.148, 0.80, 0)
		body.add_child(hip)
		# Thigh — tapered, wider at top. Radius diperkecil supaya kedua paha
		# tidak menyatu ("culottes") saat dilihat dari depan bawah.
		_mesh(hip, _capsule_mesh(0.096, 0.44, 22, 8), pants_mat, Vector3(0, -0.22, 0))
		# Thigh muscle hint.
		_mesh(hip, _sphere_mesh(0.085, 14, 8), pants_dark, Vector3(0, -0.18, 0.02)).scale = Vector3(0.92, 0.55, 0.88)
		# Knee joint.
		_mesh(hip, _sphere_mesh(0.082, 18, 10), dark_skin_mat, Vector3(0, -0.44, 0))
		# Knee cap.
		_mesh(hip, _sphere_mesh(0.058, 14, 8), skin_mat, Vector3(0, -0.44, -0.03)).scale = Vector3(0.8, 0.5, 0.65)
		# Shin — slightly thinner than thigh.
		_mesh(hip, _capsule_mesh(0.074, 0.42, 18, 8), pants_mat, Vector3(0, -0.66, 0))
		# Calf muscle.
		_mesh(hip, _sphere_mesh(0.066, 14, 8), pants_dark, Vector3(0, -0.70, -0.02)).scale = Vector3(0.85, 0.55, 0.82)
		# Ankle.
		_mesh(hip, _sphere_mesh(0.050, 14, 8), skin_mat, Vector3(0, -0.87, 0))
		# Sock.
		_mesh(hip, _cylinder_mesh(0.052, 0.055, 0.08, 16), fabric_material(Color("#e8e6e0"), 0.82), Vector3(0, -0.88, 0))
		# Shoe — realistic shape with toe box, sole, laces.
		var shoe := _mesh(hip, _box_mesh(Vector3(0.18, 0.09, 0.32)), shoe_mat, Vector3(0, -0.93, -0.03))
		shoe.scale = Vector3(1.0, 0.85, 1.0)
		# Shoe toe box — rounded front.
		var toe := _mesh(hip, _sphere_mesh(0.072, 14, 8), shoe_mat, Vector3(0, -0.95, -0.15))
		toe.scale = Vector3(1.25, 0.65, 0.78)
		# Shoe heel.
		_mesh(hip, _sphere_mesh(0.052, 12, 6), shoe_mat, Vector3(0, -0.92, 0.09), Vector3(0.9, 0.58, 1.05))
		# Shoe sole — lighter strip at bottom.
		var sole_mat := StandardMaterial3D.new()
		sole_mat.albedo_color = Color("#2a2e30")
		sole_mat.roughness = 0.55
		sole_mat.metallic = 0.05
		_mesh(hip, _box_mesh(Vector3(0.19, 0.025, 0.34)), sole_mat, Vector3(0, -0.985, -0.03))
		# Shoe laces — 3 cross bands.
		for ly in [-0.88, -0.90, -0.92]:
			_mesh(hip, _box_mesh(Vector3(0.12, 0.008, 0.018)), fabric_material(Color("#d0c8b8"), 0.7), Vector3(0, ly, -0.08))
		# Shoe tongue.
		_mesh(hip, _box_mesh(Vector3(0.10, 0.06, 0.08)), shoe_mat, Vector3(0, -0.90, -0.06))

		legs.append(hip)

	# ---- BADGE / NAME TAG ----
	var badge_mat := StandardMaterial3D.new()
	badge_mat.albedo_color = Color("#e0dfd0")
	badge_mat.roughness = 0.28
	badge_mat.metallic = 0.22
	badge_mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	_mesh(body, _box_mesh(Vector3(0.14, 0.18, 0.025)), badge_mat, Vector3(0.105, 1.44, -0.236))
	# Badge clip.
	_mesh(body, _box_mesh(Vector3(0.018, 0.05, 0.008)), metallic_material(Color("#999"), 0.3, 0.5), Vector3(0.105, 1.53, -0.243))
	# Badge text line.
	_mesh(body, _box_mesh(Vector3(0.08, 0.026, 0.008)), fabric_material(Color("#597d6e"), 0.5), Vector3(0.105, 1.47, -0.243))

	# ---- LABELS ----
	var label := Label3D.new()
	label.text = label_text
	label.position = Vector3(0, 2.67, 0)
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
	status_label.position = Vector3(0, 2.43, 0)
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
