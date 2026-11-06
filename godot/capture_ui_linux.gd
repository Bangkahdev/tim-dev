extends SceneTree

const OUT := "/tmp/opencode/shots/"
var _main

func _initialize() -> void:
	call_deferred("_run")

func _snapshot() -> Dictionary:
	return {
		"company": {
			"employees": [
				{"id":"lead","name":"Arman","role":"Lead Manager","department_id":"mgmt","status":"working","active_task":{"title":"Sprint review"}},
				{"id":"coo","name":"Sinta","role":"COO / Project Manager","department_id":"mgmt","status":"working","active_task":{"title":"Roadmap Q4"}},
				{"id":"architect","name":"Raka","role":"System Architect","department_id":"eng","status":"working","active_task":{"title":"Blueprint API"}},
				{"id":"frontend","name":"Dira","role":"Frontend Developer","department_id":"eng","status":"working","active_task":{"title":"Design system"}},
				{"id":"qa","name":"Tika","role":"QA Engineer","department_id":"eng","status":"idle"},
				{"id":"backend","name":"Bima","role":"Backend Developer","department_id":"eng","status":"working","active_task":{"title":"Auth service"}},
				{"id":"api","name":"Naya","role":"API Specialist","department_id":"eng","status":"working","active_task":{"title":"Gateway v2"}}
			],
			"departments": [
				{"id":"mgmt","name":"Management","description":"Leadership"},
				{"id":"eng","name":"Engineering","description":"Product delivery"}
			],
			"tasks": [
				{"id":"t1","title":"Rilis v1.0","status":"in_progress","assignee_id":"lead","acceptance_criteria":"QA pass","evidence":[]},
				{"id":"t2","title":"Perbaiki build staging","status":"blocked","assignee_id":"qa","evidence":[]},
				{"id":"t3","title":"Audit API gateway","status":"pending","assignee_id":"api","evidence":[]}
			],
			"projects": [{"name":"Bangkah Platform","directory":"E:/tim-dev","status":"in_progress","current_phase":"Build"}],
			"papers": [
				{"id":"p1","title":"Memo rilis v1.0","origin":"Owner","status":"unread","paper_type":"memo","priority":"high","body":"Isi memo"},
				{"id":"p2","title":"Laporan QA mingguan","origin":"QA","status":"read","paper_type":"report","priority":"normal","body":"Laporan"},
				{"id":"p3","title":"Ringkasan sprint","origin":"Secretary","status":"deferred","paper_type":"report","priority":"low","body":"Ringkasan"}
			],
			"approvals": [{"id":"a1","summary":"Deploy staging","action_type":"website.deploy","status":"pending","payload_sha256":"abc123","payload":{"ref":"main"}}],
			"meetings": [{"id":"m1","title":"Weekly sync","agenda":"Progress","attendee_ids":["lead","qa"],"room_id":"meeting","status":"scheduled","created_at":"2026-11-03T10:00:00"}],
			"outbox": [{"id":"o1","summary":"Deploy staging","action_type":"website.deploy","status":"queued"}],
			"knowledge_documents": [{"title":"Playbook operasi","source":"docs/playbook.md","chunks":12}],
			"print_jobs": [{"id":"pj1","paper_id":"p1","status":"completed"}],
			"events": [{"actor":"Arman","detail":"Task diperbarui","created_at":"2026-11-03T10:00:00"}]
		}
	}

func _capture(file_name: String) -> void:
	await process_frame
	await process_frame
	var image := root.get_texture().get_image()
	image.save_png(OUT + file_name)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var scene: PackedScene = load("res://scenes/main.tscn")
	_main = scene.instantiate()
	root.add_child(_main)
	var ui = _main._company_ui
	ui.set_connection_state(true)
	ui.set_company_snapshot(_snapshot())
	for page in ["overview", "documents", "projects", "team", "settings"]:
		ui.open_panel(page)
		for i in range(16):
			await process_frame
		await _capture("ui-" + page + ".png")
		print("CAPTURE: ui-" + page)
	ui.close_panel()
	for i in range(12):
		await process_frame
	await _capture("ui-hud.png")
	print("CAPTURE: ui-hud")
	print("CAPTURE_OK")
	quit()
