extends Node3D
class_name StubMain

const PLAYER_SCRIPT = preload("res://scripts/player.gd")
const NPC_SCRIPT = preload("res://scripts/npc.gd")
const COMPANY_UI_SCRIPT = preload("res://scripts/company_ui.gd")

# Every employee desk now owns a real workstation from the backend catalog
# (PC-MGT-001, PC-MGT-002, PC-ARC-001, PC-BE-001, PC-API-001, PC-FE-001,
# PC-QA-001). Seat / camera / target use the formulas of _add_workstation in
# office_environment.gd: seat = P + (0, 0.05, 1.55),
# camera = seat + (0, 1.22, -0.2), target = P + (0, 1.35, -0.44) when the
# desk rotation is 0 as for every employee desk.
const EMPLOYEE_STATIONS := {
	"arman_desk": {"workstation_id": "PC-MGT-001", "title": "Arman", "account": "lead", "position": Vector3(5.8, 6.2, -31.3)},
	"sinta_desk": {"workstation_id": "PC-MGT-002", "title": "Sinta", "account": "coo", "position": Vector3(13.2, 6.2, -31.3)},
	"raka_desk": {"workstation_id": "PC-ARC-001", "title": "Raka", "account": "architect", "position": Vector3(29.0, 6.2, -31.3)},
	"dira_desk": {"workstation_id": "PC-FE-001", "title": "Dira", "account": "frontend", "position": Vector3(-29.0, 6.2, -8.9)},
	"tika_desk": {"workstation_id": "PC-QA-001", "title": "Tika", "account": "qa", "position": Vector3(-5.0, 6.2, -8.9)},
	"bima_desk": {"workstation_id": "PC-BE-001", "title": "Bima", "account": "backend", "position": Vector3(27.0, 6.2, -8.9)},
	"naya_desk": {"workstation_id": "PC-API-001", "title": "Naya", "account": "api", "position": Vector3(29.0, 0.0, 12.65)},
}
# Workstation tanpa NPC khusus. Semuanya wajib bisa diakses pemain (desktop OS).
const EXTRA_STATIONS := {
	"secretary_pc": {"workstation_id": "PC-SEC-001", "title": "Sekretaris", "account": "secretary", "position": Vector3(-10.8, 6.2, -31.3)},
	"ui_design_desk": {"workstation_id": "PC-FE-002", "title": "UI Design", "account": "frontend", "position": Vector3(-34.5, 6.2, -8.9)},
	"auto_test_desk": {"workstation_id": "PC-QA-002", "title": "Automated Test", "account": "qa", "position": Vector3(1.4, 6.2, -8.9)},
	"service_mon_desk": {"workstation_id": "PC-BE-002", "title": "Service Monitoring", "account": "backend", "position": Vector3(34.0, 6.2, -8.9)},
}
const OFFICE_WORLD_SCRIPT = preload("res://scripts/office_environment.gd")
const WORKSTATION_SYSTEM_SCRIPT = preload("res://scripts/workstation_sys.gd")
const DESKTOP_UI_SCRIPT = preload("res://scripts/desktop_ui.gd")

const ROOM_CENTERS := {
	"owner": Vector2(-29.5, -29.7), "secretary": Vector2(-10.8, -29.7),
	"manager": Vector2(8.0, -29.7), "architect": Vector2(29.0, -29.7),
	"frontend": Vector2(-29.5, -7.8), "qa": Vector2(-6.5, -7.8),
	"backend": Vector2(24.0, -7.8), "meeting": Vector2(-29.5, 14.5),
	"lobby": Vector2(-0.4, 14.5), "api": Vector2(29.0, 14.5),
	"archive": Vector2(-29.5, 32.0), "kitchen": Vector2(29.0, 32.0),
	"owner_lounge": Vector2(-10.0, 32.0), "lounge": Vector2(8.0, 32.0), "entrance": Vector2(0.0, 35.0)
}

const EMPLOYEES := [
	{"id":"lead", "name":"Arman", "role":"Lead Manager", "room":"manager", "position":Vector3(5.8, 0.05, -29.75), "shirt":Color("#466d68"), "hair":Color("#28343b"), "body_type":"average", "gender":"male", "floor":2},
	{"id":"coo", "name":"Sinta", "role":"COO / Project Manager", "room":"manager", "position":Vector3(13.2, 0.05, -29.75), "shirt":Color("#8b6d83"), "hair":Color("#3a3036"), "body_type":"slim", "gender":"female", "wear_hijab":true, "floor":2},
	{"id":"architect", "name":"Raka", "role":"System Architect", "room":"architect", "position":Vector3(29.0, 0.05, -29.75), "shirt":Color("#547b9a"), "hair":Color("#292e34"), "body_type":"tall", "gender":"male", "floor":2},
	{"id":"frontend", "name":"Dira", "role":"Frontend Developer", "room":"frontend", "position":Vector3(-29.0, 0.05, -7.35), "shirt":Color("#b17d62"), "hair":Color("#40352d"), "body_type":"average", "gender":"female", "wear_hijab":false, "floor":2},
	{"id":"qa", "name":"Tika", "role":"QA Engineer", "room":"qa", "position":Vector3(-5.0, 0.05, -7.35), "shirt":Color("#6b8c73"), "hair":Color("#302c2b"), "body_type":"slim", "gender":"female", "wear_hijab":false, "floor":2},
	{"id":"backend", "name":"Bima", "role":"Backend Developer", "room":"backend", "position":Vector3(27.0, 0.05, -7.35), "shirt":Color("#55758c"), "hair":Color("#252e31"), "body_type":"stocky", "gender":"male", "floor":2},
	{"id":"api", "name":"Naya", "role":"API Specialist", "room":"api", "position":Vector3(29.0, 0.05, 14.2), "shirt":Color("#ad8a56"), "hair":Color("#39312d"), "body_type":"average", "gender":"female", "wear_hijab":true, "floor":1}
]

var player
var npcs: Dictionary = {}
var receptionist
var _interactables: Array[Dictionary] = []
# Sistem duduk bebas: kursi swivel mengikuti rotasi pemain selama ia duduk.
var _free_seat_pivot: Node3D = null
var _free_seat_base_yaw: float = 0.0
var _material_cache: Dictionary = {}
var _status_http: HTTPRequest
var _player_http: HTTPRequest
var _post_http: HTTPRequest
var _chat_http: HTTPRequest
var _company_http: HTTPRequest
var _print_download_http: HTTPRequest
var _pending_print_job_id: String = ""
var _company_busy: bool = false
var _status_busy: bool = false
var _player_busy: bool = false
var _post_busy: bool = false
var _chat_busy: bool = false
var _post_context: String = "movement"
var _status_elapsed: float = 10.0
var _save_elapsed: float = 0.0
var _toast_elapsed: float = 0.0
var _last_saved_position: Vector3 = Vector3(INF, INF, INF)
var _selected_employee: String = ""
var _server_url: String = "http://127.0.0.1:8765"
var _api_token: String = ""
var _project_title: String = "Belum ada proyek aktif"
var _connection_online: bool = false
var _company_ui
var _workstation_sys
var _desktop_ui
var _desktop_active: bool = false
var _coffee_carried: bool = false
var _coffee_cup: Node3D = null
var _coffee_placed_count: int = 0
var _local_meeting_active: bool = false
var _local_meeting_time_left: float = 0.0
var _local_meeting_speaker_elapsed: float = 0.0
var _local_meeting_attendees: Array[String] = []
var _local_meeting_speaker_index: int = -1
var _town_shift_on_duty: bool = true

var _api_label: Label
var _location_label: Label
var _summary_label: Label
var _project_label: Label
var _roster_text: Label
var _prompt_label: Label
var _prompt_panel: PanelContainer
var _toast_label: Label
var _toast_panel: PanelContainer
var _status_dot: Label
var _hud_clock_label: Label
var _hud_clock_elapsed: float = 0.0
var _toast_text: String = ""
var _api_url_input: LineEdit
var _hud_layer: CanvasLayer
var _chat_panel: PanelContainer
var _chat_title: Label
var _chat_log: TextEdit
var _chat_input: LineEdit
var _send_chat_button: Button
var _chat_header_label: Label

func _ready() -> void:
	_build_environment()
	_build_office()
	_spawn_characters()
	_build_interaction_points()
	_build_ui()
	_setup_http()
	_request_initial_state()
	_show_toast("Bangkah HQ siap. Jelajahi kantor dan temui tim kamu.")

func _process(delta: float) -> void:
	_status_elapsed += delta
	_save_elapsed += delta
	_hud_clock_elapsed += delta
	if _hud_clock_elapsed >= 1.0:
		_hud_clock_elapsed = 0.0
		if is_instance_valid(_hud_clock_label):
			_hud_clock_label.text = Time.get_time_string_from_system().left(5)
	if _toast_elapsed > 0.0:
		_toast_elapsed -= delta
		if _toast_elapsed <= 0.0:
			if is_instance_valid(_toast_panel):
				_toast_panel.visible = false
			if is_instance_valid(_toast_label):
				_toast_label.visible = false
	if _status_elapsed >= 3.5:
		_status_elapsed = 0.0
		_request_status()
	_update_local_meeting(delta)
	_update_free_seat_swivel(delta)
	if _save_elapsed >= 5.0:
		_save_elapsed = 0.0
		_save_player_if_needed()
	_update_interaction_prompt()

func _build_environment() -> void:
	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()

	# Realistic sky with atmospheric depth and gradient.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.24, 0.38, 0.52)
	sky_material.sky_horizon_color = Color(0.74, 0.80, 0.72)
	sky_material.ground_bottom_color = Color(0.30, 0.34, 0.32)
	sky_material.ground_horizon_color = Color(0.56, 0.60, 0.56)
	sky_material.sun_angle_max = 30.0
	sky_material.sun_curve = 0.15
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.72

	# Design Bible: ACESTonemap, Exposure 1.15, clean vibrant (no far blur).
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_exposure = 1.15
	environment.adjustment_enabled = true
	environment.adjustment_brightness = 1.0
	environment.adjustment_contrast = 1.06
	environment.adjustment_saturation = 1.05

	# SSAO (radius 1.2, intensity 2.0).
	environment.ssao_enabled = true
	environment.ssao_radius = 1.2
	environment.ssao_intensity = 2.0
	environment.ssao_power = 1.8
	environment.ssao_light_affect = 0.65
	environment.ssao_ao_channel_affect = 1.0

	# Glow — thin bloom (LED/screens), threshold 0.85.
	environment.glow_enabled = true
	environment.glow_intensity = 0.30
	environment.glow_bloom = 0.08
	environment.glow_hdr_threshold = 0.85
	environment.glow_hdr_scale = 1.1

	# Atmosphere fog (wide city scale; DoF/Far Blur OFF for sharp distant city).
	environment.fog_enabled = true
	environment.fog_density = 0.005
	environment.fog_light_color = Color(0.78, 0.82, 0.80)
	environment.fog_aerial_perspective = 0.22

	# Volumetric fog — very light shafts.
	environment.volumetric_fog_enabled = true
	environment.volumetric_fog_density = 0.003
	environment.volumetric_fog_anisotropy = 0.40
	environment.volumetric_fog_length = 40.0
	environment.volumetric_fog_ambient_inject = 0.10

	# SSR for glossy marble floors / screens.
	environment.ssr_enabled = true
	environment.ssr_fade_in = 0.15
	environment.ssr_fade_out = 0.30
	environment.ssr_depth_tolerance = 0.2

	world_environment.environment = environment
	add_child(world_environment)

	# Sun — cascaded shadows. Bias/pancake tuned to stop shadow acne/flicker
	# (blend_splits off: seam blending can shimmer with a moving camera).
	var sun := DirectionalLight3D.new()
	sun.name = "AfternoonSun"
	sun.rotation_degrees = Vector3(-38, -35, 0)
	sun.light_color = Color(1.0, 0.94, 0.80)
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	sun.shadow_bias = 0.035
	sun.shadow_normal_bias = 1.8
	sun.shadow_reverse_cull_face = true
	sun.shadow_blur = 1.2
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_split_1 = 0.08
	sun.directional_shadow_split_2 = 0.22
	sun.directional_shadow_split_3 = 0.55
	sun.directional_shadow_blend_splits = false
	sun.directional_shadow_max_distance = 180.0
	sun.directional_shadow_fade_start = 0.85
	sun.directional_shadow_pancake_size = 24.0
	add_child(sun)

	# Fill light — cool ambient bounce from sky.
	var fill := DirectionalLight3D.new()
	fill.name = "FillLight"
	fill.rotation_degrees = Vector3(-25, 145, 0)
	fill.light_color = Color(0.70, 0.80, 0.92)
	fill.light_energy = 0.35
	fill.shadow_enabled = false
	add_child(fill)

	# Reflection probes for realistic floor and screen reflections.
	var probe := ReflectionProbe.new()
	probe.name = "CentralReflection"
	probe.position = Vector3(0, 2.5, 0)
	probe.size = Vector3(84, 8, 80)
	probe.origin_offset = Vector3(0, 2.5, 0)
	probe.intensity = 0.75
	probe.max_distance = 140.0
	probe.box_projection = true
	add_child(probe)

	var probe2 := ReflectionProbe.new()
	probe2.name = "MeetingReflection"
	probe2.position = Vector3(-29.5, 2.5, 14.5)
	probe2.size = Vector3(18, 8, 22)
	probe2.origin_offset = Vector3(0, 2.5, 0)
	probe2.intensity = 0.65
	probe2.box_projection = true
	add_child(probe2)

	var probe3 := ReflectionProbe.new()
	probe3.name = "LobbyReflection"
	probe3.position = Vector3(0, 2.5, 14.5)
	probe3.size = Vector3(38, 8, 22)
	probe3.origin_offset = Vector3(0, 2.5, 0)
	probe3.intensity = 0.70
	probe3.box_projection = true
	add_child(probe3)

	var probe4 := ReflectionProbe.new()
	probe4.name = "SouthReflection"
	probe4.position = Vector3(15, 2.5, 32.0)
	probe4.size = Vector3(50, 8, 18)
	probe4.origin_offset = Vector3(0, 2.5, 0)
	probe4.intensity = 0.65
	probe4.box_projection = true
	add_child(probe4)

func _material(color: Color, roughness: float = 0.78, metallic: float = 0.0, transparent: bool = false) -> StandardMaterial3D:
	var key := "%s|%.2f|%.2f|%s" % [color.to_html(true), roughness, metallic, str(transparent)]
	if _material_cache.has(key):
		return _material_cache[key]
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.roughness = roughness
	result.metallic = metallic
	# Enable proper specular for realistic light response.
	if metallic > 0.01:
		result.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	if transparent:
		result.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		result.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	_material_cache[key] = result
	return result

func _add_sphere(object_name: String, position: Vector3, radius: float, color: Color, scale: Vector3 = Vector3.ONE, parent: Node3D = null) -> MeshInstance3D:
	var target_parent: Node3D = parent if parent != null else self
	var mesh := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	mesh.mesh = sphere
	mesh.name = object_name
	mesh.position = position
	mesh.scale = scale
	mesh.material_override = _material(color)
	mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	target_parent.add_child(mesh)
	return mesh

func _build_office() -> void:
	var office_world = OFFICE_WORLD_SCRIPT.new()
	office_world.name = "BangkahHeadquarters"
	add_child(office_world)
	office_world.build()

func _spawn_characters() -> void:
	for employee in EMPLOYEES:
		var npc = NPC_SCRIPT.new()
		npc.employee_id = employee.id
		npc.display_name = employee.name
		npc.job_title = employee.role
		npc.shirt_color = employee.shirt
		npc.hair_color = employee.hair
		npc.gender = employee.get("gender", "male")
		npc.wear_hijab = bool(employee.get("wear_hijab", false))
		npc.skin_color = employee.get("skin_color", Color("#c89e84"))
		npc.body_type = employee.get("body_type", "average")
		npc.home_position = employee.position
		npc.name = "NPC_" + employee.id
		add_child(npc)
		npc.set_ambient_plans(_ambient_plans_for(employee.id, employee.position))
		_configure_employee_home(npc)
		npcs[employee.id] = npc

	receptionist = NPC_SCRIPT.new()
	receptionist.employee_id = "reception"
	receptionist.display_name = "Mira · Receptionist"
	receptionist.job_title = "Front Desk"
	receptionist.shirt_color = Color("#b88a66")
	receptionist.hair_color = Color("#46362f")
	receptionist.home_position = Vector3(0, 0.05, 18.95)
	receptionist.rotation.y = PI # Face visitors entering from the south entrance.
	receptionist.is_receptionist = true
	receptionist.name = "Receptionist_Mira"
	add_child(receptionist)

	# Secretary has a dedicated physical desk and character slot. The backend agent
	# is not fabricated here; until it is registered, this character remains visibly idle.
	var secretary = NPC_SCRIPT.new()
	secretary.employee_id = "secretary"
	secretary.display_name = "Sekretaris"
	secretary.job_title = "Executive Secretary · belum tersambung"
	secretary.shirt_color = Color("#6e8278")
	secretary.hair_color = Color("#342e2a")
	secretary.home_position = Vector3(-10.8, 6.2+0.05, -29.75)
	secretary.name = "Secretary_Visual_Slot"
	add_child(secretary)

	player = PLAYER_SCRIPT.new()
	player.name = "Player_Owner"
	player.position = Vector3(-5.0, 0.06, 23.0)
	# Spawn menghadap diagonal ke arah lobby/meja resepsionis: lengan kamera
	# mengarah ke lantai terbuka (bukan ke partisi di z=25), sehingga jarak
	# kamera ketiga penuh dan avatar tidak memenuhi layar.
	player.rotation.y = deg_to_rad(-68.0)
	add_child(player)
	player.interact_requested.connect(_on_player_interact)
	player.ui_requested.connect(_on_player_ui_requested)

func _ambient_plans_for(employee_id: String, _home: Vector3) -> Array:
	# Ambient routes are short, role-specific office routines. They are only used
	# while the backend reports idle/completed; they never imply active project work.
	match employee_id:
		"lead":
			return [
				{"label":"Meninjau papan sprint", "mode":"review_board", "target":Vector3(15.0,0.05,-35.0)},
				{"label":"Memeriksa ruang perencanaan", "mode":"review_documents", "target":Vector3(2.5,0.05,-25.0)}
			]
		"coo":
			return [
				{"label":"Memeriksa agenda proyek", "mode":"review_documents", "target":Vector3(14.0,0.05,-25.0)},
				{"label":"Meninjau catatan sprint", "mode":"review_board", "target":Vector3(8.0,0.05,-35.0)}
			]
		"architect":
			return [
				{"label":"Meninjau diagram sistem", "mode":"inspect_diagram", "target":Vector3(36.0,0.05,-34.0)},
				{"label":"Mencatat keputusan teknis", "mode":"review_documents", "target":Vector3(22.0,0.05,-24.0)}
			]
		"frontend":
			return [
				{"label":"Meninjau desain antarmuka", "mode":"inspect_design", "target":Vector3(-35.0,0.05,-14.0)},
				{"label":"Memeriksa komponen UI", "mode":"inspect_design", "target":Vector3(-22.0,0.05,-5.0)}
			]
		"qa":
			return [
				{"label":"Meninjau test case", "mode":"review_documents", "target":Vector3(-10.0,0.05,-15.0)},
				{"label":"Memeriksa hasil pengujian", "mode":"inspect_test_bench", "target":Vector3(1.0,0.05,-14.0)}
			]
		"backend":
			return [
				{"label":"Memeriksa service log", "mode":"inspect_logs", "target":Vector3(36.0,0.05,-15.0)},
				{"label":"Meninjau dokumentasi backend", "mode":"review_documents", "target":Vector3(18.0,0.05,-3.0)}
			]
		"api":
			return [
				{"label":"Memeriksa integrasi API", "mode":"inspect_server", "target":Vector3(37.0,0.05,20.0)},
				{"label":"Meninjau server rack", "mode":"inspect_server", "target":Vector3(22.0,0.05,21.0)}
			]
	return []

func _build_interaction_points() -> void:
	_interactables = [
		{"id":"reception", "label":"Reception Desk", "position":Vector3(0,0,22.7), "prompt":"Sapa resepsionis Mira"},
		_station_interactable("workstation", "Owner Workstation", "OWNER-PC-001", "owner", Vector3(-29.3,12.4,-31.3)),
		{"id":"owner_tray", "label":"Owner Paper Tray", "position":Vector3(-27.2,12.4,-29.8), "prompt":"Periksa dokumen di tray Owner"},
		{"id":"meeting", "label":"Boardroom", "position":Vector3(-29.5,0,10.0), "prompt":"Masuk ke ruang rapat"},
		{"id":"printer", "label":"Office Printer", "position":Vector3(-23.2,0,29.9), "prompt":"Gunakan printer kantor"},
		{"id":"coffee", "label":"Coffee Station", "position":Vector3(22.5,0,34.8), "prompt":"Ambil kopi di pantry"},
		{"id":"coffee_lounge_table", "label":"Meja Lounge", "position":Vector3(7.0,0,32.1), "prompt":"Taruh kopi di meja lounge", "drop_position":Vector3(7.0,0.61,32.1)},
		{"id":"coffee_pantry_bar", "label":"Bar Pantry", "position":Vector3(24.5,0,29.0), "prompt":"Taruh kopi di bar pantry", "drop_position":Vector3(24.5,1.865,29.0)},
		{"id":"lounge", "label":"Staff Lounge", "position":Vector3(7.0,0,32.1), "prompt":"Beristirahat di lounge"},
		{"id":"archive", "label":"Company Archive", "position":Vector3(-29.5,0,27.2), "prompt":"Buka arsip perusahaan"},
		{"id":"lift_l1", "label":"Lift (Lantai 1)", "position":Vector3(15.3,0.0,8.7), "prompt":"E · Naik/Turun Lift (samping tangga naik/turun)", "lift_floor":"L1"},
		{"id":"lift_l2", "label":"Lift (Lantai 2)", "position":Vector3(15.3,6.2,8.7), "prompt":"E · Pilih lantai Lift (samping tangga)", "lift_floor":"L2"},
		{"id":"lift_l3", "label":"Lift (Lantai 3)", "position":Vector3(15.3,12.4,8.7), "prompt":"E · Naik/Turun Lift (samping tangga)", "lift_floor":"L3"},
		{"id":"stair_up_l1", "label":"Tangga Naik (ke L2)", "position":Vector3(13.6,0.0,14.7), "prompt":"E · Naik via Tangga Naik → Lantai 2", "to_floor":"L2", "to_pos":"stair"},
		{"id":"stair_up_l2", "label":"Tangga Naik (ke L3)", "position":Vector3(13.6,6.2,14.7), "prompt":"E · Naik via Tangga Naik → Lantai 3", "to_floor":"L3", "to_pos":"stair"},
		{"id":"stair_down_l2", "label":"Tangga Turun (ke L1)", "position":Vector3(10.6,6.2,6.6), "prompt":"E · Turun via Tangga Turun → Lantai 1", "to_floor":"L1", "to_pos":"stair"},
		{"id":"stair_down_l3", "label":"Tangga Turun (ke L2)", "position":Vector3(10.6,12.4,6.6), "prompt":"E · Turun via Tangga Turun → Lantai 2", "to_floor":"L2", "to_pos":"stair"},
	]
	for desk_id in EMPLOYEE_STATIONS:
		var station: Dictionary = EMPLOYEE_STATIONS[desk_id]
		_interactables.append(
			_station_interactable(desk_id, str(station["title"]) + " Workstation",
				str(station["workstation_id"]), str(station["account"]),
				station["position"]))
	for desk_id in EXTRA_STATIONS:
		var station: Dictionary = EXTRA_STATIONS[desk_id]
		_interactables.append(
			_station_interactable(desk_id, str(station["title"]) + " Workstation",
				str(station["workstation_id"]), str(station["account"]),
				station["position"]))
	_append_free_seat_interactables()
	_append_door_interactables()

# Kursi dan sofa yang dibangun office_environment.gd didaftarkan sebagai titik
# interaksi "duduk". Kursi kantor yang punya komputer dipetakan ke workstation
# terdekat: E langsung duduk + membuka layar komputer, bukan duduk biasa.
func _append_free_seat_interactables() -> void:
	var office_world = get_node_or_null("BangkahHeadquarters")
	if not is_instance_valid(office_world) or not ("seats" in office_world):
		return
	var stations: Array = []
	for item in _interactables:
		if item.has("workstation_id"):
			stations.append(item)
	var seat_index := 0
	for seat_entry in office_world.seats:
		var seat_position: Vector3 = seat_entry.get("position", Vector3.ZERO)
		var seat_yaw: float = float(seat_entry.get("yaw", 0.0))
		var seat_kind := str(seat_entry.get("kind", "office"))
		var seat_label := str(seat_entry.get("label", "Kursi"))
		var pivot_node = seat_entry.get("pivot", null)
		var entry: Dictionary = {
			"id": "free_seat_%d" % seat_index,
			"label": seat_label,
			"position": seat_position,
			"prompt": "Duduk di " + seat_label.to_lower(),
			"seat": seat_position,
			"seat_yaw": seat_yaw,
			"kind": seat_kind,
			"pivot": pivot_node if pivot_node is Node3D else null,
			"pivot_base_yaw": seat_yaw,
		}
		if seat_kind == "office":
			var best: Dictionary = {}
			var best_distance := 0.85
			for station in stations:
				var station_seat: Vector3 = station.get("seat", Vector3.ZERO)
				var dx := station_seat.x - seat_position.x
				var dz := station_seat.z - seat_position.z
				var distance := sqrt(dx * dx + dz * dz)
				if distance < best_distance and absf(station_seat.y - seat_position.y) < 0.6:
					best_distance = distance
					best = station
			if not best.is_empty():
				entry["workstation"] = best
				entry["prompt"] = "E · Duduk & akses komputer — " + str(best.get("label", seat_label))
		_interactables.append(entry)
		seat_index += 1

# Pintu juga jadi titik interaksi: E membuka/menutup daun pintu dengan animasi.
func _append_door_interactables() -> void:
	var office_world = get_node_or_null("BangkahHeadquarters")
	if not is_instance_valid(office_world) or not ("doors" in office_world):
		return
	for door_index in range(office_world.doors.size()):
		var door: Dictionary = office_world.doors[door_index]
		var door_label := str(door.get("label", "Pintu"))
		if door_label.is_empty():
			door_label = "Pintu"
		_interactables.append({
			"id": "free_door_%d" % door_index,
			"label": "Pintu " + door_label,
			"position": door.get("position", Vector3.ZERO),
			"prompt": "Buka/tutup pintu " + door_label.to_lower(),
			"kind": "door",
			"door_index": door_index,
		})

# Interaction entry for a backend workstation. Station seat/camera/target
# follow _add_workstation geometry: seat = P + (0, 0.05, 1.55),
# camera = seat + (0, 1.22, -0.2), target = P + (0, 1.35, -0.44) when the
# desk rotation is 0 as for all mapped desks.
func _station_interactable(desk_id: String, label: String, workstation_id: String, account: String, position: Vector3) -> Dictionary:
	var seat := position + Vector3(0, 0.05, 1.55)
	return {"id":desk_id, "label":label, "position":position,
		"prompt":"Duduk di workstation %s (%s)" % [label, workstation_id],
		"workstation_id":workstation_id, "account_id":account,
		"seat":seat, "seat_yaw":0.0,
		"camera":seat + Vector3(0, 1.22, -0.2),
		"camera_target":position + Vector3(0, 1.35, -0.44)}

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	_hud_layer = layer
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)

	# Restrained first-person HUD: the office remains the primary interface.
	var status_panel := _make_panel(root, Vector2(22, 18), Vector2(320, 90))
	var status_box := VBoxContainer.new()
	status_box.add_theme_constant_override("separation", 3)
	status_panel.add_child(status_box)
	var title_row := HBoxContainer.new()
	title_row.add_theme_constant_override("separation", 8)
	_status_dot = _ui_label("●", 10, Color("#d9cba8"), true, false)
	_status_dot.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	title_row.add_child(_status_dot)
	title_row.add_child(_ui_label("BANGKAH  /  HEADQUARTERS", 15, Color("#f0f2ec"), true, false))
	status_box.add_child(title_row)
	_api_label = _ui_label("LOCAL OFFICE  ·  CONNECTING", 10, Color("#d9cba8"), true)
	status_box.add_child(_api_label)
	var meta_row := HBoxContainer.new()
	meta_row.add_theme_constant_override("separation", 12)
	_location_label = _ui_label("LOBBY  /  GROUND FLOOR", 10, Color("#c6d1ca"))
	_location_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	meta_row.add_child(_location_label)
	_hud_clock_label = _ui_label("--:--", 10, Color("#c6d1ca"), true, false)
	_hud_clock_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	meta_row.add_child(_hud_clock_label)
	status_box.add_child(meta_row)

	var company_status := _make_panel(root, Vector2.ZERO, Vector2(238, 52))
	company_status.anchor_left = 1.0
	company_status.anchor_right = 1.0
	company_status.offset_left = -260
	company_status.offset_right = -22
	company_status.offset_top = 18
	company_status.offset_bottom = 70
	var status_content := VBoxContainer.new()
	status_content.add_theme_constant_override("separation", 1)
	company_status.add_child(status_content)
	_summary_label = _ui_label("TEAM  ·  7 ENGINEERING", 10, Color("#e4e9e3"), true, false)
	_project_label = _ui_label("NO ACTIVE PROJECT", 9, Color("#bac8be"), false, false)
	_project_label.clip_text = true
	_project_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	status_content.add_child(_summary_label)
	status_content.add_child(_project_label)

	# Keep a hidden API field for compatibility with the settings panel callbacks.
	_api_url_input = LineEdit.new()
	_api_url_input.text = _server_url
	_api_url_input.visible = false
	root.add_child(_api_url_input)
	_roster_text = _ui_label("", 10, Color.WHITE)
	_roster_text.visible = false
	root.add_child(_roster_text)

	# Small center reticle and contextual interaction strip.
	var reticle := Control.new()
	reticle.name = "FirstPersonReticle"
	reticle.set_anchors_preset(Control.PRESET_CENTER)
	reticle.position = Vector2(-5, -5)
	reticle.size = Vector2(10, 10)
	reticle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(reticle)
	var dot := ColorRect.new()
	dot.color = Color(0.95, 0.96, 0.91, 0.85)
	dot.position = Vector2(4, 4)
	dot.size = Vector2(2, 2)
	reticle.add_child(dot)

	_prompt_label = _ui_label("", 13, Color("#f3f2ea"), true)
	_prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_prompt_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_prompt_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_prompt_label.visible = false
	_prompt_panel = _make_panel(root, Vector2(-240, -90), Vector2(480, 50))
	_prompt_panel.anchor_left = 0.5
	_prompt_panel.anchor_right = 0.5
	_prompt_panel.anchor_top = 1.0
	_prompt_panel.anchor_bottom = 1.0
	_prompt_panel.offset_left = -240
	_prompt_panel.offset_right = 240
	_prompt_panel.offset_top = -90
	_prompt_panel.offset_bottom = -40
	_prompt_panel.visible = false
	var prompt_row := HBoxContainer.new()
	prompt_row.add_theme_constant_override("separation", 10)
	_prompt_panel.add_child(prompt_row)
	var key_panel := PanelContainer.new()
	key_panel.custom_minimum_size = Vector2(28, 28)
	key_panel.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	key_panel.add_theme_stylebox_override("panel", _hud_box(Color("#2d403b"), Color("#52775a"), 6, 1))
	var key_label := _ui_label("E", 12, Color("#eaf3ec"), true)
	key_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	key_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	key_panel.add_child(key_label)
	prompt_row.add_child(key_panel)
	prompt_row.add_child(_prompt_label)

	_toast_panel = _make_panel(root, Vector2(-340, -150), Vector2(680, 40))
	_toast_panel.anchor_left = 0.5
	_toast_panel.anchor_right = 0.5
	_toast_panel.anchor_top = 1.0
	_toast_panel.anchor_bottom = 1.0
	_toast_panel.offset_left = -340
	_toast_panel.offset_right = 340
	_toast_panel.offset_top = -150
	_toast_panel.offset_bottom = -110
	_toast_panel.visible = false
	var toast_style := _hud_box(Color(0.055, 0.085, 0.09, 0.94), Color("#4a6a55"), 10, 1)
	toast_style.shadow_color = Color(0, 0, 0, 0.35)
	toast_style.shadow_size = 8
	toast_style.shadow_offset = Vector2(0, 3)
	_toast_panel.add_theme_stylebox_override("panel", toast_style)
	var toast_row := HBoxContainer.new()
	toast_row.add_theme_constant_override("separation", 10)
	_toast_panel.add_child(toast_row)
	var toast_accent := ColorRect.new()
	toast_accent.color = Color("#8fb59a")
	toast_accent.custom_minimum_size = Vector2(3, 0)
	toast_accent.size_flags_vertical = Control.SIZE_EXPAND_FILL
	toast_row.add_child(toast_accent)
	_toast_label = _ui_label("", 12, Color("#f4f3e9"), true)
	_toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_toast_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toast_row.add_child(_toast_label)

	var help_panel := _make_panel(root, Vector2(22, 0), Vector2(520, 34))
	help_panel.anchor_top = 1.0
	help_panel.anchor_bottom = 1.0
	help_panel.offset_top = -54
	help_panel.offset_bottom = -20
	var help := _ui_label("WASD GERAK · SHIFT LARI · E INTERAKSI · V KAMERA · F1-F4 PANEL · ESC", 9, Color("#d2dbd4"))
	help_panel.add_child(help)

	_chat_panel = _make_panel(root, Vector2.ZERO, Vector2(390, 330))
	_chat_panel.anchor_left = 1.0
	_chat_panel.anchor_right = 1.0
	_chat_panel.anchor_top = 1.0
	_chat_panel.anchor_bottom = 1.0
	_chat_panel.offset_left = -412
	_chat_panel.offset_right = -22
	_chat_panel.offset_top = -360
	_chat_panel.offset_bottom = -22
	_chat_panel.size = Vector2(390, 338)
	_chat_panel.visible = false
	var chat_box := VBoxContainer.new()
	chat_box.add_theme_constant_override("separation", 7)
	_chat_panel.add_child(chat_box)
	var chat_header := HBoxContainer.new()
	chat_box.add_child(chat_header)
	_chat_title = _ui_label("EMPLOYEE CONVERSATION", 16, Color("#f5f5ee"), true)
	_chat_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chat_header.add_child(_chat_title)
	var close_button := Button.new()
	close_button.text = "×"
	close_button.custom_minimum_size = Vector2(34, 30)
	_style_hud_button(close_button)
	close_button.pressed.connect(_close_chat)
	chat_header.add_child(close_button)
	_chat_header_label = _ui_label("Pesan diproses oleh backend AI Office. Esc untuk menutup.", 11, Color("#c5d2ce"))
	chat_box.add_child(_chat_header_label)
	_chat_log = TextEdit.new()
	_chat_log.custom_minimum_size = Vector2(350, 190)
	_chat_log.editable = false
	_chat_log.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_chat_log.text = "Percakapan belum dimulai.\n"
	_style_hud_input(_chat_log)
	chat_box.add_child(_chat_log)
	var send_row := HBoxContainer.new()
	chat_box.add_child(send_row)
	_chat_input = LineEdit.new()
	_chat_input.placeholder_text = "Tulis pesan ke karyawan..."
	_chat_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_chat_input.text_submitted.connect(_on_chat_text_submitted)
	_style_hud_input(_chat_input)
	send_row.add_child(_chat_input)
	_send_chat_button = Button.new()
	_send_chat_button.text = "KIRIM"
	_style_hud_button(_send_chat_button, true)
	_send_chat_button.pressed.connect(_send_employee_chat)
	send_row.add_child(_send_chat_button)

	_company_ui = COMPANY_UI_SCRIPT.new()
	_company_ui.set_server_url(_server_url)
	add_child(_company_ui)
	_company_ui.panel_visibility_changed.connect(_on_company_panel_visibility_changed)
	_company_ui.employee_chat_requested.connect(_on_company_employee_chat_requested)
	_company_ui.demo_action_requested.connect(_show_toast)
	_company_ui.connect_backend_requested.connect(_on_company_connect_requested)
	_company_ui.company_action_requested.connect(_on_company_action_requested)
	_company_ui.set_connection_state(_connection_online)

	_workstation_sys = WORKSTATION_SYSTEM_SCRIPT.new()
	_workstation_sys.name = "WorkstationSystem"
	add_child(_workstation_sys)
	_desktop_ui = DESKTOP_UI_SCRIPT.new()
	_desktop_ui.name = "BangkahDesktop"
	_desktop_ui.set_server_url(_server_url)
	_desktop_ui.close_requested.connect(_exit_workstation)
	_desktop_ui.company_requested.connect(_on_desktop_company_requested)
	_desktop_ui.toast_requested.connect(_show_toast)
	add_child(_desktop_ui)

func _make_panel(parent: Control, position: Vector2, minimum_size: Vector2) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = position
	panel.custom_minimum_size = minimum_size
	panel.size = minimum_size
	var style := StyleBoxFlat.new()
	# Dark glass-like background with subtle transparency.
	style.bg_color = Color(0.035, 0.055, 0.065, 0.93)
	style.border_color = Color(0.28, 0.36, 0.33, 0.45)
	style.set_border_width_all(1)
	style.set_corner_radius_all(14)
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	# Drop shadow for depth.
	style.shadow_color = Color(0, 0, 0, 0.40)
	style.shadow_size = 12
	style.shadow_offset = Vector2(0, 4)
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	return panel

func _ui_label(text_value: String, font_size: int, color: Color, bold: bool = false, wrap: bool = true) -> Label:
	var label := Label.new()
	label.text = text_value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	if bold:
		label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.45))
		label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.3))
		label.add_theme_constant_override("outline_size", 1)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if wrap else TextServer.AUTOWRAP_OFF
	# Letter spacing for a more premium feel.
	label.add_theme_constant_override("line_spacing", 2)
	return label

func _hud_box(background: Color, border: Color, radius: int, border_width: int, draw_center: bool = true) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(border_width)
	style.set_corner_radius_all(radius)
	style.draw_center = draw_center
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 7
	style.content_margin_bottom = 7
	return style

func _style_hud_button(button: Button, primary: bool = false) -> void:
	button.focus_mode = Control.FOCUS_ALL
	button.add_theme_font_size_override("font_size", 11)
	button.add_theme_color_override("font_color", Color("#e8ece8"))
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	# Subtle text outline for readability.
	button.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.25))
	button.add_theme_constant_override("outline_size", 1)
	var normal := Color("#2d403b") if primary else Color("#1a2326")
	var border := Color("#52775a") if primary else Color("#3a484a")
	var hover_bg := Color("#364940") if primary else Color("#222d30")
	var pressed_bg := Color("#25372d") if primary else Color("#161e21")
	button.add_theme_stylebox_override("normal", _hud_box(normal, border, 8, 1))
	button.add_theme_stylebox_override("hover", _hud_box(hover_bg, Color("#5d7667"), 8, 1))
	button.add_theme_stylebox_override("pressed", _hud_box(pressed_bg, Color("#6e8b73"), 8, 1))
	button.add_theme_stylebox_override("focus", _hud_box(Color(0, 0, 0, 0), Color("#8fb59a"), 8, 2, false))
	# Add subtle hover scale animation.
	button.mouse_entered.connect(func():
		var t := create_tween()
		t.tween_property(button, "scale", Vector2(1.02, 1.02), 0.08).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)
	button.mouse_exited.connect(func():
		var t := create_tween()
		t.tween_property(button, "scale", Vector2(1.0, 1.0), 0.10).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	)

func _style_hud_input(control: Control) -> void:
	if control is LineEdit:
		var line := control as LineEdit
		line.custom_minimum_size.y = 36
		line.add_theme_font_size_override("font_size", 12)
		line.add_theme_color_override("font_color", Color("#e8ece8"))
		line.add_theme_color_override("font_placeholder_color", Color("#8f9c96"))
		line.add_theme_color_override("caret_color", Color("#a8b9ae"))
		line.add_theme_stylebox_override("normal", _hud_box(Color("#111719"), Color("#3a484a"), 8, 1))
		line.add_theme_stylebox_override("focus", _hud_box(Color("#111719"), Color("#8fb59a"), 8, 1))
	elif control is TextEdit:
		var edit := control as TextEdit
		edit.add_theme_font_size_override("font_size", 12)
		edit.add_theme_color_override("font_color", Color("#e8ece8"))
		edit.add_theme_color_override("caret_color", Color("#a8b9ae"))
		edit.add_theme_stylebox_override("normal", _hud_box(Color("#111719"), Color("#3a484a"), 8, 1))
		edit.add_theme_stylebox_override("focus", _hud_box(Color("#111719"), Color("#8fb59a"), 8, 1))

func _setup_http() -> void:
	_status_http = HTTPRequest.new()
	_status_http.timeout = 4.0
	_status_http.request_completed.connect(_on_status_completed)
	add_child(_status_http)
	_player_http = HTTPRequest.new()
	_player_http.timeout = 4.0
	_player_http.request_completed.connect(_on_player_completed)
	add_child(_player_http)
	_post_http = HTTPRequest.new()
	_post_http.timeout = 5.0
	_post_http.request_completed.connect(_on_post_completed)
	add_child(_post_http)
	_chat_http = HTTPRequest.new()
	_chat_http.timeout = 60.0
	_chat_http.request_completed.connect(_on_chat_completed)
	add_child(_chat_http)
	_company_http = HTTPRequest.new()
	_company_http.timeout = 20.0
	_company_http.request_completed.connect(_on_company_action_completed)
	add_child(_company_http)
	_print_download_http = HTTPRequest.new()
	_print_download_http.timeout = 30.0
	_print_download_http.request_completed.connect(_on_print_download_completed)
	add_child(_print_download_http)

func _request_initial_state() -> void:
	_request_status()
	if not _player_busy:
		_player_busy = true
		_player_http.request(_url("/api/office/player"), _request_headers(["Cache-Control: no-cache"]))

func _connect_backend() -> void:
	var candidate := _api_url_input.text.strip_edges().trim_suffix("/")
	if not candidate.begins_with("http://") and not candidate.begins_with("https://"):
		_show_toast("Alamat API harus diawali http:// atau https://")
		return
	_server_url = candidate
	_status_elapsed = 10.0
	_request_status()
	_show_toast("Menghubungkan ke Bangkah AI Office...")

func _url(path: String) -> String:
	return _server_url.trim_suffix("/") + path

func _request_headers(extra: Array = []) -> PackedStringArray:
	var headers := PackedStringArray()
	for value in extra:
		headers.append(str(value))
	if not _api_token.is_empty():
		headers.append("Authorization: Bearer " + _api_token)
	return headers

func _request_status() -> void:
	if _status_busy or not is_instance_valid(_status_http):
		return
	_status_busy = true
	var error := _status_http.request(_url("/api/status"), _request_headers(["Cache-Control: no-cache"]))
	if error != OK:
		_status_busy = false
		_set_connection(false)

func _on_status_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_status_busy = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		_set_connection(false)
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not data is Dictionary:
		_set_connection(false)
		return
	_set_connection(true)
	var office: Dictionary = data.get("office", {})
	var rows: Array = office.get("employees", [])
	var working := 0
	var talking := 0
	var listening := 0
	var roster_lines: Array[String] = []
	for row in rows:
		if not row is Dictionary:
			continue
		var employee_id := str(row.get("id", ""))
		if npcs.has(employee_id):
			npcs[employee_id].apply_employee_record(row)
		var status := str(row.get("status", "idle"))
		if status == "working":
			working += 1
		elif status == "talking":
			talking += 1
		elif status == "listening":
			listening += 1
		var employee_name := str(row.get("name", employee_id))
		var employee_role := str(row.get("role", "Team Member"))
		roster_lines.append("%s  ·  %s  [%s]" % [employee_name, employee_role, status.to_upper()])
	for interaction in office.get("interactions", []):
		if not interaction is Dictionary:
			continue
		var sender_id := str(interaction.get("sender_id", ""))
		if npcs.has(sender_id):
			npcs[sender_id].set_speech(str(interaction.get("message", "")))
	var idle := maxi(0, rows.size() - working - talking - listening)
	_summary_label.text = "TEAM %d  ·  WORKING %d  ·  IDLE %d" % [rows.size(), working, idle]
	if not roster_lines.is_empty():
		_roster_text.text = "\n".join(roster_lines)
	var project: Variant = data.get("project", null)
	if project is Dictionary:
		_project_title = str(project.get("name", "Belum ada proyek aktif"))
	else:
		var projects_value: Variant = data.get("projects", [])
		if projects_value is Array and projects_value.size() > 0 and projects_value[0] is Dictionary:
			_project_title = str(projects_value[0].get("name", "Belum ada proyek aktif"))
	_project_label.text = "PROJECT · " + _project_title
	if is_instance_valid(_company_ui):
		_company_ui.set_company_snapshot(data)
	_apply_activity_engine_state(data)

func _apply_activity_engine_state(data: Dictionary) -> void:
	# Use backend workshift state to drive visual commute (no backend state changes).
	var engine: Variant = data.get("activity_engine", {})
	if not engine is Dictionary:
		return
	var on_duty := bool(engine.get("duty_open", true))
	var enabled := bool(engine.get("enabled", true))
	if not enabled:
		on_duty = true
	if on_duty == _town_shift_on_duty:
		return
	_town_shift_on_duty = on_duty
	for employee_id in npcs:
		var npc = npcs[employee_id]
		if is_instance_valid(npc) and npc.has_method("set_shift_on_duty"):
			npc.set_shift_on_duty(on_duty)
	if on_duty:
		_show_toast("Jam kerja dimulai — karyawan berangkat ke kantor.")
	else:
		_show_toast("Jam kerja selesai — karyawan pulang ke rumah masing-masing.")

func _set_connection(online: bool) -> void:
	_connection_online = online
	if not is_instance_valid(_api_label):
		return
	if online:
		_api_label.text = "DATABASE CONNECTED · SQLITE SYNC ACTIVE"
		_api_label.add_theme_color_override("font_color", Color("#a9d8b1"))
		if is_instance_valid(_status_dot):
			_status_dot.add_theme_color_override("font_color", Color("#8fb59a"))
	else:
		_api_label.text = "LOCAL SIMULATION · API OFFLINE"
		_api_label.add_theme_color_override("font_color", Color("#e4c99b"))
		if is_instance_valid(_status_dot):
			_status_dot.add_theme_color_override("font_color", Color("#d4a96a"))
	if is_instance_valid(_company_ui):
		_company_ui.set_connection_state(online)

func _on_player_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_player_busy = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not data is Dictionary or not data.get("player") is Dictionary:
		return
	var saved: Dictionary = data.player
	var world_x := clampf(float(saved.get("x", 50.0)) / 100.0 * 84.0 - 42.0, -39.0, 39.0)
	var world_z := clampf(float(saved.get("y", 90.0)) / 100.0 * 80.0 - 40.0, -37.0, 37.0)
	player.global_position = Vector3(world_x, 0, world_z)
	_last_saved_position = player.global_position

func _save_player_if_needed() -> void:
	if _desktop_active or not _connection_online or _post_busy or not is_instance_valid(player):
		return
	if _last_saved_position.distance_to(player.global_position) < 0.65:
		return
	var payload := _player_payload()
	payload["activity"] = player.activity
	_send_post("/api/office/player", payload, "movement")

func _player_payload() -> Dictionary:
	var x := clampf((player.global_position.x + 42.0) / 84.0 * 100.0, 0.0, 100.0)
	var y := clampf((player.global_position.z + 40.0) / 80.0 * 100.0, 0.0, 100.0)
	return {"x":x, "y":y, "room_id":_room_from_position(player.global_position)}

func _send_post(path: String, payload: Dictionary, context: String) -> void:
	if _post_busy:
		return
	_post_busy = true
	_post_context = context
	var headers := _request_headers(["Content-Type: application/json"])
	var error := _post_http.request(_url(path), headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_post_busy = false
		if context != "movement":
			_show_toast("Gagal mengirim tindakan ke backend.")

func _on_post_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_post_busy = false
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		if _post_context != "movement":
			var error_text := "Interaksi gagal disimpan."
			if data is Dictionary:
				error_text = str(data.get("error", error_text))
			_show_toast(error_text)
		return
	if _post_context == "movement":
		_last_saved_position = player.global_position
	elif data is Dictionary:
		var player_data: Dictionary = data.get("player", {})
		_show_toast(str(player_data.get("detail", "Aktivitas kantor berhasil dicatat.")))

func _room_from_position(position: Vector3) -> String:
	var best_room := "corridor"
	var best_distance := INF
	for room_id in ROOM_CENTERS:
		var center: Vector2 = ROOM_CENTERS[room_id]
		var distance := Vector2(position.x, position.z).distance_to(center)
		if distance < best_distance:
			best_distance = distance
			best_room = room_id
	return best_room if best_distance < 10.5 else "corridor"

func _update_interaction_prompt() -> void:
	if not is_instance_valid(player):
		_prompt_label.visible = false
		if is_instance_valid(_prompt_panel): _prompt_panel.visible = false
		return
	_location_label.text = "LOKASI · " + _room_label(_room_from_position(player.global_position))
	if _desktop_active:
		_prompt_label.visible = false
		_prompt_panel.visible = false
		return
	# Saat duduk di kursi bebas, tampilkan instruksi berdiri.
	if player.is_seated:
		_prompt_label.text = "E · BERDIRI DARI KURSI"
		_prompt_label.visible = true
		_prompt_panel.visible = true
		return
	if is_instance_valid(_company_ui) and _company_ui.is_panel_open():
		_prompt_label.visible = false
		_prompt_panel.visible = false
		return
	if _chat_panel.visible:
		_prompt_label.visible = false
		_prompt_panel.visible = false
		return
	var target := _nearest_target()
	if target.is_empty():
		_prompt_label.visible = false
		_prompt_panel.visible = false
		return
	var prompt_text := str(target.get("prompt", "INTERACT"))
	var target_id := str(target.get("id", ""))
	if target_id == "coffee" and _coffee_carried:
		prompt_text = "E · Kamu sudah membawa kopi — taruh di meja"
	elif (target_id in ["coffee_lounge_table", "coffee_pantry_bar"]) and not _coffee_carried:
		prompt_text = "E · Belum ada kopi — ambil dulu di coffee station"
	if str(target.get("kind", "")) == "door":
		var office_world = get_node_or_null("BangkahHeadquarters")
		var label_text := "Pintu"
		var is_open := true
		if is_instance_valid(office_world) and "doors" in office_world:
			var idx: int = int(target.get("door_index", -1))
			if idx >= 0 and idx < office_world.doors.size():
				label_text = str(office_world.doors[idx].get("label", "")) if str(office_world.doors[idx].get("label", "")) != "" else "Pintu"
				is_open = bool(office_world.doors[idx].get("open", true))
		prompt_text = ("E · TUTUP PINTU — %s" if is_open else "E · BUKA PINTU — %s") % label_text
	_prompt_label.text = prompt_text
	_prompt_label.visible = true
	_prompt_panel.visible = true

func _nearest_target() -> Dictionary:
	var nearest: Dictionary = {}
	var nearest_distance := 3.25
	var eye_position: Vector3 = player.global_position + Vector3(0, 1.55, 0)
	var view_forward: Vector3 = player.get_view_forward()
	for item in _interactables:
		# Kursi & pintu pakai jangkauan lebih besar + kerucut lebih longgar:
		# pemain bisa jadi berdiri agak menyamping dari objeknya.
		var item_kind := str(item.get("kind", ""))
		var is_seat := item_kind in ["office", "meeting", "sofa"]
		var is_door := item_kind == "door"
		var reach_cap := 3.4 if is_door else (2.9 if is_seat else nearest_distance)
		var cone_min := -0.45 if (is_seat or is_door) else 0.48
		var target_position: Vector3 = item.position + Vector3(0, 0.85, 0)
		var to_target := target_position - eye_position
		var distance := to_target.length()
		if distance < reach_cap and distance > 0.01 and view_forward.dot(to_target.normalized()) > cone_min:
			nearest_distance = distance
			nearest = item
	for employee_id in npcs:
		var npc = npcs[employee_id]
		var target_position: Vector3 = npc.global_position + Vector3(0, 1.0, 0)
		var to_target := target_position - eye_position
		var distance := to_target.length()
		if distance < nearest_distance and distance > 0.01 and view_forward.dot(to_target.normalized()) > 0.48:
			nearest_distance = distance
			nearest = {"id":"employee", "employee_id":employee_id, "label":npc.display_name, "prompt":"Bicara dengan " + npc.display_name}
	if is_instance_valid(receptionist):
		var target_position: Vector3 = receptionist.global_position + Vector3(0, 1.0, 0)
		var to_target := target_position - eye_position
		var distance := to_target.length()
		if distance < nearest_distance and distance > 0.01 and view_forward.dot(to_target.normalized()) > 0.48:
			nearest_distance = distance
			nearest = {"id":"reception", "label":"Mira", "prompt":"Sapa resepsionis Mira"}
	return nearest

func _on_player_interact() -> void:
	# Duduk bebas di kursi: tekan E lagi untuk berdiri, mouse memutar kursi.
	if is_instance_valid(player) and player.is_seated and not _desktop_active:
		_leave_free_seat()
		return
	var target := _nearest_target()
	if target.is_empty():
		_show_toast("Tidak ada objek dalam jangkauan. Dekati workstation atau karyawan.")
		return
	var target_id := str(target.get("id", ""))
	if str(target.get("kind", "")) in ["office", "meeting", "sofa"]:
		var workstation = target.get("workstation", null)
		if workstation is Dictionary and not (workstation as Dictionary).is_empty():
			_enter_workstation(workstation)
		else:
			_take_free_seat(target)
		return
	if str(target.get("kind", "")) == "door":
		_toggle_free_door(target)
		return
	if target_id == "coffee":
		_take_coffee()
		return
	if target_id in ["coffee_lounge_table", "coffee_pantry_bar"]:
		_place_coffee(target)
		return
	if target_id == "employee":
		_open_employee_chat(str(target.get("employee_id", "")))
		return
	if target_id == "reception":
		receptionist.trigger_greeting()
		_show_toast("Mira: Selamat datang di Bangkah Headquarters. Ada yang bisa saya bantu?")
		return
	if target_id in ["lift_l1","lift_l2","lift_l3"]:
		_use_lift(str(target.get("lift_floor","L1")))
		return
	if str(target.get("to_pos","")) == "stair":
		var destf := str(target.get("to_floor","L1"))
		var ys2 := {"L1":0.06,"L2":6.26,"L3":12.46}
		var sxp := 13.6 if str(target_id).begins_with("stair_up") else 10.6
		if is_instance_valid(player):
			player.global_position = Vector3(sxp, float(ys2.get(destf,0.06)), 14.1)
			if player.has_method("exit_seat"): player.exit_seat()
		_show_toast(("Tangga Naik → " if str(target_id).begins_with("stair_up") else "Tangga Turun → ") + ({"L1":"Lantai 1","L2":"Lantai 2","L3":"Lantai 3"}.get(destf,destf)))
		return
		return
	if target_id == "workstation":
		_enter_workstation(target)
		return
	var info := _interaction_info(target_id)
	# Only send interaction IDs understood by the currently existing backend.
	# Paper, printer and Secretary panels remain local prototypes until v1.3 APIs exist.
	if _connection_online and target_id in ["meeting", "coffee", "lounge", "archive", "secretary_desk"]:
		var payload := _player_payload()
		payload["interaction"] = target_id
		_send_post("/api/office/player", payload, "interaction")
	elif not _connection_online or target_id not in ["meeting", "coffee", "lounge", "archive", "secretary_desk"]:
		_show_toast(str(info.get("detail", "Interaksi lokal.")))
	if target_id == "secretary_desk":
		player.activity = "working"
		_show_toast(str(info.get("detail", "Anda menggunakan workstation ini.")))
	elif target_id == "meeting":
		player.activity = "meeting"
		_start_local_meeting_preview()
	elif target_id == "coffee":
		player.activity = "making_coffee"
	elif target_id == "lounge":
		player.activity = "resting"
	elif target_id == "archive":
		player.activity = "viewing_archive"
	if is_instance_valid(_company_ui):
		if target_id == "owner_tray":
			_company_ui.open_panel("documents")
		elif target_id == "secretary_desk":
			_company_ui.open_panel("documents")
		elif target_id == "meeting":
			_company_ui.open_panel("meetings")
		elif target_id == "archive":
			_company_ui.open_panel("archive")
	if target_id in ["coffee", "lounge"]:
		_show_toast(str(info.get("detail", "Aktivitas dilakukan.")))



func _use_lift(from_floor: String) -> void:
	if not is_instance_valid(player): return
	var order := ["L1","L2","L3"]; var ys := {"L1":0.06, "L2":6.26, "L3":12.46}
	var names := {"L1":"Lantai 1 (Lobi/Layanan)", "L2":"Lantai 2 (Karyawan Inti)", "L3":"Lantai 3 (Owner)"}
	var idx := order.find(from_floor); if idx < 0: idx = 0
	var next_idx := (idx + 1) % order.size(); var dest := str(order[next_idx])
	player.global_position = Vector3(15.3, float(ys.get(dest, 0.06)), 9.6)
	if player.has_method("exit_seat"): player.exit_seat()
	_show_toast("Lift: %s → %s" % [names.get(from_floor, from_floor), names.get(dest, dest)])

func _enter_workstation(target: Dictionary) -> void:
	if _desktop_active:
		return
	if not is_instance_valid(_workstation_sys) or not is_instance_valid(_desktop_ui):
		_show_toast("Sistem workstation belum siap.")
		return
	_desktop_active = true
	if _connection_online:
		var payload := _player_payload()
		payload["interaction"] = "computer"
		_send_post("/api/office/player", payload, "interaction")
	if is_instance_valid(_chat_panel) and _chat_panel.visible:
		_close_chat()
	if is_instance_valid(_hud_layer):
		_hud_layer.visible = false
	player.activity = "working"
	var workstation_id := str(target.get("workstation_id", "OWNER-PC-001"))
	var seat: Vector3 = target.get("seat", player.global_position)
	var seat_yaw := float(target.get("seat_yaw", 0.0))
	var camera_position: Vector3 = target.get("camera", player.global_position)
	var camera_target: Vector3 = target.get("camera_target", player.global_position + Vector3(0.0, 1.0, -1.0))
	_desktop_ui.set_offline_mode(not _connection_online)
	_workstation_sys.enter(player, workstation_id, seat, seat_yaw, camera_position, camera_target)
	_desktop_ui.open_for(workstation_id, str(target.get("label", "Workstation")), str(target.get("account_id", "owner")))

func _exit_workstation() -> void:
	if not _desktop_active:
		return
	_desktop_active = false
	if is_instance_valid(_desktop_ui):
		_desktop_ui.hide_ui()
	if is_instance_valid(_workstation_sys):
		_workstation_sys.exit()
	if is_instance_valid(_hud_layer):
		_hud_layer.visible = true
	if is_instance_valid(player):
		player.activity = "idle"
		player.set_input_enabled(true)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_show_toast("Kamu berdiri dari workstation. Sesi desktop tetap aktif sampai logout.")

## Duduk di kursi/sofa bebas. Mouse tetap aktif untuk memutar badan; pivot
## kursi swivel mengikuti rotasi pemain sehingga terasa seperti kursi kantor.
func _take_free_seat(target: Dictionary) -> void:
	if not is_instance_valid(player):
		return
	if _desktop_active and is_instance_valid(_workstation_sys) and _workstation_sys.is_active():
		return
	if is_instance_valid(_chat_panel) and _chat_panel.visible:
		_close_chat()
	var pivot_node: Variant = target.get("pivot", null)
	_free_seat_pivot = pivot_node if pivot_node is Node3D else null
	_free_seat_base_yaw = float(target.get("pivot_base_yaw", target.get("seat_yaw", 0.0)))
	player.activity = "resting" if str(target.get("kind", "")) == "sofa" else "sitting"
	player.sit_at(target.get("seat", player.global_position), float(target.get("seat_yaw", 0.0)))
	# sit_at mematikan input; nyalakan lagi supaya mouse memutar kursi.
	# Gerak masih terkunci karena _physics_process memeriksa is_seated.
	player.set_input_enabled(true)
	_show_toast(str(target.get("label", "Kursi")) + ": duduk nyaman. Mouse memutar kursi, E untuk berdiri.")

func _leave_free_seat() -> void:
	if is_instance_valid(player) and player.is_seated:
		player.stand_up()
		player.activity = "idle"
	_free_seat_pivot = null
	_show_toast("Kamu berdiri kembali. Kursi tetap menghadap posisi terakhir.")

## Kopi pantry yang nyata: ambil di coffee station, cangkir menempel di tangan
## pemain, lalu ditaruh di meja lounge atau bar pantry sebagai objek statis.
func _build_coffee_cup() -> Node3D:
	var cup := Node3D.new()
	cup.name = "CoffeeCup"
	var ceramic := StandardMaterial3D.new()
	ceramic.albedo_color = Color("#f3efe6")
	ceramic.roughness = 0.26
	ceramic.metallic = 0.0
	var body := MeshInstance3D.new()
	var body_mesh := CylinderMesh.new()
	body_mesh.top_radius = 0.055
	body_mesh.bottom_radius = 0.045
	body_mesh.height = 0.105
	body_mesh.radial_segments = 20
	body.mesh = body_mesh
	body.material_override = ceramic
	cup.add_child(body)
	var coffee := MeshInstance3D.new()
	var coffee_mesh := CylinderMesh.new()
	coffee_mesh.top_radius = 0.046
	coffee_mesh.bottom_radius = 0.046
	coffee_mesh.height = 0.012
	coffee_mesh.radial_segments = 20
	coffee.mesh = coffee_mesh
	var coffee_mat := StandardMaterial3D.new()
	coffee_mat.albedo_color = Color("#4a2f20")
	coffee_mat.roughness = 0.18
	coffee.material_override = coffee_mat
	coffee.position.y = 0.049
	cup.add_child(coffee)
	var handle := MeshInstance3D.new()
	var handle_mesh := TorusMesh.new()
	handle_mesh.inner_radius = 0.026
	handle_mesh.outer_radius = 0.044
	handle_mesh.rings = 16
	handle_mesh.ring_segments = 10
	handle.mesh = handle_mesh
	handle.material_override = ceramic
	handle.rotation.x = PI * 0.5
	handle.position = Vector3(0.062, 0.0, 0.0)
	cup.add_child(handle)
	return cup

func _take_coffee() -> void:
	if _coffee_carried:
		_show_toast("Kamu sudah membawa kopi. Taruh di meja lounge atau bar pantry (E).")
		return
	if not is_instance_valid(player):
		return
	_coffee_cup = _build_coffee_cup()
	player.add_child(_coffee_cup)
	_coffee_cup.position = Vector3(0.36, 1.08, -0.30)
	_coffee_cup.rotation = Vector3.ZERO
	_coffee_carried = true
	player.activity = "carrying_coffee"
	_show_toast("Kopi panas diambil dari coffee station. Bawa ke meja lounge atau bar pantry.")

func _place_coffee(target: Dictionary) -> void:
	if not _coffee_carried:
		_show_toast("Belum ada kopi di tangan. Ambil dulu di coffee station pantry.")
		return
	var drop: Vector3 = target.get("drop_position", target.get("position", player.global_position))
	var placed := _build_coffee_cup()
	_coffee_placed_count += 1
	placed.name = "CoffeeCup_Placed_%02d" % _coffee_placed_count
	add_child(placed)
	placed.global_position = drop
	placed.rotation.y = deg_to_rad(-18.0)
	if is_instance_valid(_coffee_cup):
		_coffee_cup.queue_free()
	_coffee_cup = null
	_coffee_carried = false
	if is_instance_valid(player):
		player.activity = "idle"
	_show_toast("Kopi ditaruh di %s. Silakan dinikmati." % str(target.get("label", "meja")).to_lower())

## Buka/tutup pintu: daun pintu dianimasikan lewat tween ke yaw tertutup atau
## terbuka. State disimpan di registry doors milik office_environment.
func _toggle_free_door(target: Dictionary) -> void:
	var office_world = get_node_or_null("BangkahHeadquarters")
	if not is_instance_valid(office_world) or not ("doors" in office_world):
		return
	var all_doors: Array = office_world.doors
	var door_index: int = int(target.get("door_index", -1))
	if door_index < 0 or door_index >= all_doors.size():
		return
	var door: Dictionary = all_doors[door_index]
	var opening: bool = not bool(door.get("open", true))
	# Hentikan tween lama bila toggling di tengah animasi.
	for old_tween in door.get("tweens", []):
		if old_tween is Tween and old_tween.is_valid():
			old_tween.kill()
	var active_tweens: Array = []
	for leaf in door.get("leaves", []):
		var leaf_node: Node = leaf.get("node", null)
		if not (leaf_node is Node3D and is_instance_valid(leaf_node)):
			continue
		var target_yaw: float = float(leaf.get("open", 0.0)) if opening else float(leaf.get("closed", 0.0))
		var swing_tween := create_tween()
		swing_tween.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		swing_tween.tween_property(leaf_node, "rotation:y", target_yaw, 0.55)
		active_tweens.append(swing_tween)
	door["tweens"] = active_tweens
	door["open"] = opening
	var door_label := str(door.get("label", "Pintu"))
	_show_toast(("%s terbuka lebar." if opening else "%s ditutup kembali.") % (door_label if not door_label.is_empty() else "Pintu"))

## Pivot kursi menyalin rotasi badan pemain (relatif terhadap yaw dasar
## kursinya), sehingga kursi berputar seperti kursi kantor sungguhan.
func _update_free_seat_swivel(delta: float) -> void:
	if _free_seat_pivot == null or not is_instance_valid(_free_seat_pivot):
		return
	if not is_instance_valid(player) or not player.is_seated:
		_free_seat_pivot = null
		return
	var target_yaw: float = player.global_rotation.y - _free_seat_base_yaw
	_free_seat_pivot.rotation.y = lerp_angle(_free_seat_pivot.rotation.y, target_yaw, minf(1.0, delta * 9.0))

func _on_desktop_company_requested() -> void:
	if is_instance_valid(_company_ui):
		_company_ui.open_panel("overview")

func _meeting_seats() -> Array[Dictionary]:
	# Ten chairs are part of the boardroom geometry. Seven employee seats are
	# reserved here, leaving one chair free for the Owner and two spare seats.
	return [
		{"position":Vector3(-33.7,0.05,11.75), "yaw":PI},
		{"position":Vector3(-31.6,0.05,11.75), "yaw":PI},
		{"position":Vector3(-29.5,0.05,11.75), "yaw":PI},
		{"position":Vector3(-27.4,0.05,11.75), "yaw":PI},
		{"position":Vector3(-33.7,0.05,16.85), "yaw":0.0},
		{"position":Vector3(-31.6,0.05,16.85), "yaw":0.0},
		{"position":Vector3(-29.5,0.05,16.85), "yaw":0.0}
	]

func _meeting_route_for(employee_id: String, seat_position: Vector3) -> Array[Vector3]:
	var route: Array[Vector3] = []
	match employee_id:
		"lead", "coo":
			route = [Vector3(8.0,0.05,-21.0), Vector3(8.0,0.05,-17.0), Vector3(6.5,0.05,-7.0), Vector3(13.0,0.05,2.0), Vector3(13.0,0.05,5.0)]
		"architect":
			route = [Vector3(29.0,0.05,-21.0), Vector3(29.0,0.05,-17.0), Vector3(18.5,0.05,-7.0), Vector3(29.0,0.05,2.0), Vector3(29.0,0.05,5.0)]
		"frontend":
			route = [Vector3(-29.0,0.05,2.0), Vector3(-29.0,0.05,5.0)]
		"qa":
			route = [Vector3(-6.5,0.05,-7.0), Vector3(13.0,0.05,-7.0), Vector3(13.0,0.05,2.0), Vector3(13.0,0.05,5.0)]
		"backend":
			route = [Vector3(29.0,0.05,-7.0), Vector3(29.0,0.05,2.0), Vector3(29.0,0.05,5.0)]
		"api":
			route = [Vector3(19.5,0.05,14.5)]
	# The south lobby connects to the boardroom through the glass partition door
	# at x=-19.5, z=14.5. The approach remains outside the table footprint.
	route.append(Vector3(-18.0,0.05,14.5))
	route.append(Vector3(-20.5,0.05,14.5))
	var approach_z := 11.75 if seat_position.z < 14.3 else 16.85
	route.append(Vector3(-22.0,0.05,approach_z))
	route.append(seat_position)
	return route

func _start_local_meeting_preview() -> void:
	if _local_meeting_active:
		_show_toast("Rapat lokal sedang berlangsung di Boardroom.")
		return
	var seats := _meeting_seats()
	var seat_index := 0
	_local_meeting_attendees.clear()
	for employee in EMPLOYEES:
		var employee_id := str(employee.id)
		if not npcs.has(employee_id) or seat_index >= seats.size():
			continue
		var npc = npcs[employee_id]
		# When online, do not infer idle status before the backend has supplied
		# an employee record. Offline mode remains explorable as a local preview.
		if _connection_online and not npc.backend_record_received:
			continue
		if not npc.can_join_local_meeting():
			continue
		var seat: Dictionary = seats[seat_index]
		var route := _meeting_route_for(employee_id, seat.position)
		if npc.begin_local_meeting(route, float(seat.yaw)):
			_local_meeting_attendees.append(employee_id)
			seat_index += 1
	if _local_meeting_attendees.size() < 2:
		for employee_id in _local_meeting_attendees:
			npcs[employee_id].end_local_meeting()
		_local_meeting_attendees.clear()
		_show_toast("Belum cukup karyawan idle untuk rapat. Tim yang sedang bekerja tidak ditarik dari task.")
		return
	_local_meeting_active = true
	_local_meeting_time_left = 88.0
	_local_meeting_speaker_elapsed = 5.2
	_local_meeting_speaker_index = -1
	_cycle_local_meeting_speaker()
	_show_toast("Rapat visual dimulai: %d peserta. Simulasi lokal, belum membuat notulen atau task backend." % _local_meeting_attendees.size())

func _cycle_local_meeting_speaker() -> void:
	if _local_meeting_attendees.is_empty():
		return
	if _local_meeting_speaker_index >= 0 and _local_meeting_speaker_index < _local_meeting_attendees.size():
		npcs[_local_meeting_attendees[_local_meeting_speaker_index]].set_local_meeting_speaker(false)
	var attempts := _local_meeting_attendees.size()
	while attempts > 0:
		_local_meeting_speaker_index = (_local_meeting_speaker_index + 1) % _local_meeting_attendees.size()
		var speaker_id := _local_meeting_attendees[_local_meeting_speaker_index]
		if npcs.has(speaker_id) and npcs[speaker_id].is_local_meeting_seated():
			npcs[speaker_id].set_local_meeting_speaker(true)
			return
		attempts -= 1
	_local_meeting_speaker_index = -1

func _update_local_meeting(delta: float) -> void:
	if not _local_meeting_active:
		return
	_local_meeting_time_left -= delta
	_local_meeting_speaker_elapsed += delta
	if _local_meeting_speaker_elapsed >= 5.2:
		_local_meeting_speaker_elapsed = 0.0
		_cycle_local_meeting_speaker()
	if _local_meeting_time_left <= 0.0:
		_end_local_meeting_preview()

func _end_local_meeting_preview() -> void:
	if not _local_meeting_active:
		return
	_local_meeting_active = false
	for employee_id in _local_meeting_attendees:
		if npcs.has(employee_id):
			npcs[employee_id].end_local_meeting()
	_local_meeting_attendees.clear()
	_local_meeting_speaker_index = -1
	_show_toast("Simulasi rapat selesai. Peserta kembali ke workstation masing-masing.")

func _interaction_info(target_id: String) -> Dictionary:
	var details := {
		"workstation":{"title":"Owner Workstation", "detail":"Komputer Owner membuka Bangkah OS: file, terminal, dan status infrastruktur."},
		"owner_tray":{"title":"Owner Paper Tray", "detail":"Tray dokumen Owner berisi laporan dan proposal yang menunggu pemeriksaan."},
		"secretary_desk":{"title":"Secretary Desk", "detail":"Meja Sekretaris berisi agenda, ringkasan, dan daftar persetujuan."},
		"arman_desk":{"title":"Arman Workstation", "detail":"Workstation Arman, Lead Manager. Monitor menampilkan metrics tim dan sprint board."},
		"sinta_desk":{"title":"Sinta Workstation", "detail":"Workstation Sinta, Project Manager. Berisi timeline proyek dan status deliverables."},
		"raka_desk":{"title":"Raka Workstation", "detail":"Workstation Raka, System Architect. Menampilkan diagram arsitektur dan tech specs."},
		"dira_desk":{"title":"Dira Workstation", "detail":"Workstation Dira, Frontend Engineer. Berisi desain UI komponen dan prototype."},
		"meeting":{"title":"Boardroom", "detail":"Ruang rapat Bangkah. Interaksi ini menjalankan pratinjau pergerakan rapat lokal; notulen, keputusan, dan task tetap memerlukan API meeting backend."},
		"printer":{"title":"Office Printer", "detail":"Printer fisik kantor siap digunakan. Integrasi PrintJob/PDF akan diaktifkan bersama API v1.3."},
		"coffee":{"title":"Coffee Station", "detail":"Kamu mengambil kopi di pantry."},
		"lounge":{"title":"Staff Lounge", "detail":"Kamu beristirahat sejenak di lounge."},
		"archive":{"title":"Company Archive", "detail":"Arsip perusahaan dan laporan tersimpan di ruang arsip."},
		"reception":{"title":"Reception Desk", "detail":"Mira menyambut pengunjung di front office."}
	}
	var fallback: Dictionary = {"title":"Office", "detail":"Interaksi kantor."}
	return details.get(target_id, fallback)

func _room_label(room_id: String) -> String:
	var labels := {
		"owner":"OWNER OFFICE", "secretary":"EXECUTIVE SECRETARY", "manager":"ENGINEERING LEADERSHIP",
		"architect":"SYSTEM ARCHITECTURE", "frontend":"FRONTEND DESIGN STUDIO", "qa":"QUALITY ASSURANCE LAB",
		"backend":"BACKEND ENGINEERING", "meeting":"BOARDROOM", "lobby":"RECEPTION / LOBBY",
		"api":"API / INFRASTRUCTURE LAB", "archive":"COMPANY ARCHIVE", "owner_lounge":"OWNER LOUNGE / RUANG PRIBADI", "lounge":"STAFF LOUNGE",
		"kitchen":"PANTRY", "entrance":"MAIN ENTRANCE", "corridor":"OFFICE CORRIDOR"
	}
	return str(labels.get(room_id, room_id.to_upper()))

func _on_company_action_requested(action: String, payload: Dictionary) -> void:
	if not _connection_online:
		_show_toast("Backend belum terhubung. Operasi perusahaan tidak dikirim.")
		return
	var path := ""
	var body := payload.duplicate(true)
	match action:
		"create_task": path = "/api/tasks"
		"task_transition":
			path = "/api/tasks/%s/transition" % str(body.get("task_id", ""))
			body.erase("task_id")
		"create_meeting": path = "/api/meetings"
		"create_paper": path = "/api/papers"
		"create_approval": path = "/api/approvals"
		"paper_read":
			path = "/api/papers/%s/review" % str(body.get("paper_id", ""))
			body = {"status":"read"}
		"print_paper": path = "/api/print-jobs"
		"download_print_job":
			_request_print_download(str(body.get("print_job_id", "")))
			return
		"meeting_start":
			path = "/api/meetings/%s/start" % str(body.get("meeting_id", ""))
			body = {}
		"meeting_complete":
			path = "/api/meetings/%s/complete" % str(body.get("meeting_id", ""))
			body.erase("meeting_id")
		"meeting_cancel":
			path = "/api/meetings/%s/cancel" % str(body.get("meeting_id", ""))
			body = {}
		"approve":
			path = "/api/approvals/%s/approve" % str(body.get("approval_id", ""))
			body = {}
		"reject":
			path = "/api/approvals/%s/reject" % str(body.get("approval_id", ""))
			body = {}
		"execute_outbox":
			path = "/api/outbox/%s/execute" % str(body.get("outbox_id", ""))
			body = {}
		_:
			_show_toast("Operasi belum dikenal oleh client.")
			return
	if path.contains("//") or path.ends_with("/"):
		_show_toast("ID operasi tidak valid.")
		return
	if _company_busy:
		_show_toast("Operasi lain sedang dikirim. Tunggu hasilnya sebelum mengirim lagi.")
		return
	_company_busy = true
	var error := _company_http.request(_url(path), _request_headers(["Content-Type: application/json"]), HTTPClient.METHOD_POST, JSON.stringify(body))
	if error != OK:
		_company_busy = false
		_show_toast("Permintaan operasi tidak dapat dikirim.")

func _request_print_download(job_id: String) -> void:
	if job_id.is_empty() or not _pending_print_job_id.is_empty():
		_show_toast("Unduhan lain sedang berjalan atau ID cetak tidak valid.")
		return
	_pending_print_job_id = job_id
	var error := _print_download_http.request(_url("/api/print-jobs/%s/download" % job_id), _request_headers(["Cache-Control: no-cache"]))
	if error != OK:
		_pending_print_job_id = ""
		_show_toast("PDF tidak dapat diminta dari backend.")

func _on_print_download_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var job_id := _pending_print_job_id
	_pending_print_job_id = ""
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or body.size() < 5 or body.slice(0, 4).get_string_from_ascii() != "%PDF":
		_show_toast("Unduhan PDF gagal. Periksa status PrintJob di backend.")
		return
	var directory := ProjectSettings.globalize_path("user://Bangkah/Prints")
	var make_error := DirAccess.make_dir_recursive_absolute(directory)
	if make_error != OK and make_error != ERR_ALREADY_EXISTS:
		_show_toast("Folder penyimpanan PDF tidak dapat dibuat.")
		return
	var output_path := directory.path_join(job_id + ".pdf")
	var file := FileAccess.open(output_path, FileAccess.WRITE)
	if file == null:
		_show_toast("File PDF tidak dapat disimpan.")
		return
	file.store_buffer(body)
	file.close()
	_show_toast("PDF tersimpan: " + output_path)
	OS.shell_open(output_path)

func _on_company_action_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_company_busy = false
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		var detail := "Operasi perusahaan gagal."
		if data is Dictionary:
			detail = str(data.get("error", detail))
		_show_toast(detail)
		return
	_show_toast("Operasi perusahaan berhasil disimpan.")
	_status_elapsed = 10.0
	_request_status()

func _on_company_connect_requested(url: String, token: String) -> void:
	_server_url = url
	_api_token = token.strip_edges()
	if is_instance_valid(_api_url_input):
		_api_url_input.text = url
	if is_instance_valid(_company_ui):
		_company_ui.set_server_url(url)
	_connect_backend()

func _on_player_ui_requested(page_id: String) -> void:
	if is_instance_valid(_company_ui):
		if is_instance_valid(_chat_panel) and _chat_panel.visible:
			_close_chat()
		_company_ui.open_panel(page_id)

func _on_company_panel_visibility_changed(is_visible: bool) -> void:
	if not is_instance_valid(player):
		return
	if _desktop_active:
		if is_instance_valid(_desktop_ui):
			if is_visible:
				_desktop_ui.hide_ui()
			else:
				_desktop_ui.show_ui()
		player.set_input_enabled(false)
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		return
	if is_instance_valid(_hud_layer):
		_hud_layer.visible = not is_visible
	player.set_input_enabled(not is_visible and not _chat_panel.visible)
	if is_visible:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif not _chat_panel.visible:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _on_company_employee_chat_requested(employee_id: String) -> void:
	_open_employee_chat(employee_id)

func _open_employee_chat(employee_id: String) -> void:
	if not npcs.has(employee_id):
		return
	_selected_employee = employee_id
	var npc = npcs[employee_id]
	_chat_title.text = npc.display_name + "  ·  " + npc.job_title
	_chat_header_label.text = "Percakapan langsung melalui Bangkah AI Office backend."
	_chat_log.text = "Kamu sedang menghubungi %s.\n\n" % npc.display_name
	_chat_panel.visible = true
	player.set_input_enabled(false)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_chat_input.grab_focus()

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		if is_instance_valid(_chat_panel) and _chat_panel.visible:
			_close_chat()
			get_viewport().set_input_as_handled()
			return
		if is_instance_valid(_company_ui) and _company_ui.is_panel_open():
			return
		if _desktop_active:
			_exit_workstation()
			get_viewport().set_input_as_handled()

func _close_chat() -> void:
	_chat_panel.visible = false
	_selected_employee = ""
	var panel_open: bool = is_instance_valid(_company_ui) and _company_ui.is_panel_open()
	player.set_input_enabled(not panel_open)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if panel_open else Input.MOUSE_MODE_CAPTURED

func _on_chat_text_submitted(_text: String) -> void:
	_send_employee_chat()

func _send_employee_chat() -> void:
	if _chat_busy or _selected_employee.is_empty():
		return
	var message := _chat_input.text.strip_edges()
	if message.is_empty():
		return
	if not _connection_online:
		_show_toast("Hubungkan backend AI Office untuk mengirim pesan.")
		return
	_chat_log.text += "KAMU: " + message + "\n\n"
	_chat_input.clear()
	_send_chat_button.disabled = true
	_chat_busy = true
	var payload := {"channel_id":_selected_employee, "message":message}
	var error := _chat_http.request(_url("/api/room-chat"), _request_headers(["Content-Type: application/json"]), HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_chat_busy = false
		_send_chat_button.disabled = false
		_chat_log.text += "SYSTEM: Gagal menghubungi backend.\n\n"

func _on_chat_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_chat_busy = false
	_send_chat_button.disabled = false
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		var error_text := "Karyawan belum dapat membalas."
		if data is Dictionary:
			error_text = str(data.get("error", error_text))
		_chat_log.text += "SYSTEM: " + error_text + "\n\n"
		return
	if data is Dictionary:
		var reply := str(data.get("reply", data.get("message", "Pesan diterima.")))
		var speaker := "Karyawan"
		if not _selected_employee.is_empty() and npcs.has(_selected_employee):
			speaker = str(npcs[_selected_employee].display_name)
		_chat_log.text += "%s: %s\n\n" % [speaker, reply]
		_chat_log.scroll_vertical = _chat_log.get_line_count()
	_request_status()

func _show_toast(message: String) -> void:
	if not is_instance_valid(_toast_label):
		return
	_toast_label.text = message
	_toast_label.visible = true
	if is_instance_valid(_toast_panel):
		_toast_panel.visible = true
	_toast_elapsed = 4.5

func _configure_employee_home(npc) -> void:
	if not is_instance_valid(npc) or not npc.has_method("set_commute"):
		return
	var layout: Dictionary = OFFICE_WORLD_SCRIPT.employee_house_layout(str(npc.employee_id))
	npc.set_commute(layout.get("door", npc.home_position),
		layout.get("commute_to_work", []), layout.get("commute_home", []))
	if not _town_shift_on_duty:
		npc.global_position = layout.get("door", npc.home_position)
		npc._at_residence = true
		npc._ambient_phase = "at_home"
		npc._activity_mode = "resting_home"
		npc.activity_text = "Di rumah · istirahat"
		if "_labels" in npc and npc._labels.has("status_label") and is_instance_valid(npc._labels.status_label):
			npc._labels.status_label.text = "DI RUMAH"
