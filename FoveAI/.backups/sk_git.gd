extends Node3D

var _synapse: Node = null
var _aural: Node = null
var _hud: Label3D = null
var _mind_node: Node3D = null
var _web_ui: Control = null
var _tts_player: AudioStreamPlayer3D = null

var _left_hand: XRController3D = null
var _right_hand: XRController3D = null
var _left_ray: RayCast3D = null
var _right_ray: RayCast3D = null
var _left_laser: MeshInstance3D = null
var _right_laser: MeshInstance3D = null

var _ui_visible = false
var _is_recording = false
var _is_grabbing_ui = false
var _prev_menu = false

# Agency & Director (Superego)
var _director: Node = null
var _agency_nerve: Node = null

# NEW: Mini-Panel & Adaptive Presence
var _arm_panel: Node3D = null
var _privacy_curtains: Node3D = null
var _is_drapery_open = false
var _env_vibe = {"brightness": 0.5, "hue": Color(1,1,1)}
var _movement_ontology: Node = null
var _skybox_manager: Node = null
var _portal_node: Area3D = null
var _is_mimic_active = false
var _is_in_virtual_world = true
var _anchored_gadgets: Array[Node3D] = []
var _held_gadget: Node3D = null
var _mirror_node: Node3D = null
var _virtual_phone: Node3D = null
var _is_high_fidelity = true
var _is_call_active = false
var _multiplayer: Node = null
var _awareness_level = 0.5
var _intent_intensity = 0.7
var _env_sharing_consented = false
var _is_neural_projection_active = false
var _is_occluding_makeover_active = false
var _is_void_mode_active = false
var _is_spatially_anonymous = false
var _social_vibe = "EXPLORING"
var _social_tags = ["AI_PILOT", "MAGNUS_GUEST"]
var _is_rave_active = false
var _beat_timer = 0.0
var _rave_synth: AudioStreamPlayer = null
var _current_projection_style = "CYBERPUNK"
var _http_sd: HTTPRequestResource = null # Custom resource or just Node
var _sd_timer = 0.0

# Organic Idle System
var _anim_player: AnimationPlayer = null
var _idle_anims = []
var _categories = ["Resting", "Happy", "Sad", "Greetings", "Exercise", "Sitting", "Laying", "Movement", "Feminine", "Masculine", "Manifestation", "Gymnastics", "Style"]

@onready var tactile_nerve: Node = $TactileNerveNetwork
func _ready():
	var interface = XRServer.find_interface("OpenXR")
	if interface and interface.initialize():
		get_viewport().use_xr = true
		get_viewport().transparent_bg = true # Enable for Passthrough
		if interface.has_method("is_passthrough_supported") and interface.is_passthrough_supported():
			interface.start_passthrough()
	
	_setup_ambience()
	_pre_instantiate_quantized_anims()
	print("LUMAX: Presence system check. Awareness: ACTIVE.")

func _setup_ambience():
	var p = AudioStreamPlayer.new(); p.name = "HarmonicAmbience"; add_child(p)
	p.volume_db = -35.0 # Harmonic Ambient Fuzziness
	if FileAccess.file_exists("res://Mind/Audio/ambient_harmonic.wav"):
		p.stream = load("res://Mind/Audio/ambient_harmonic.wav")
	elif FileAccess.file_exists("res://Mind/Audio/ambient_hum.wav"):
		p.stream = load("res://Mind/Audio/ambient_hum.wav")
	else:
		# Procedural Ambient Fallback
		var stream = AudioStreamGenerator.new(); stream.mix_rate = 44100; stream.buffer_length = 1.0
		p.stream = stream
	p.play()

	# 1. Body & Animation Cortex
	var body = get_node_or_null("Body")
	if body:
		body.position = Vector3(0, 0, -1.5)
		var scene = load("res://Body/Lumax_Jen.tscn")
		if scene:
			var jen = scene.instantiate(); body.add_child(jen)
			print("LUMAX: Jen Scene instantiated.")
			
			_tts_player = jen.get_node_or_null("VoicePlayer")
			if not _tts_player:
				_tts_player = AudioStreamPlayer3D.new(); _tts_player.name = "TTSPlayer"; _tts_player.position = Vector3(0, 1.6, 0); jen.add_child(_tts_player)
			
			# Link Tactile Nerve to Soul
			var nerve = jen.get_node_or_null("TactileNerveNetwork")
			if nerve:
				nerve.soul_synapse = _synapse
				print("LUMAX: Tactile Nerve linked to Soul.")
			
			_anim_player = jen.get_node_or_null("BodyAnimationPlayer")
			if not _anim_player: _anim_player = jen.find_child("AnimationPlayer", true, false)

			if _anim_player:
				print("LUMAX: AnimationPlayer found. Building Full Expression Library.")
				_scan_for_animations()
				var lib = AnimationLibrary.new(); _anim_player.add_animation_library("lumax", lib)
				_anim_player.animation_finished.connect(_on_idle_finished)
				_play_next_idle()
			else:
				print("LUMAX ERROR: AnimationPlayer NOT found on Jen!")
		else:
			print("LUMAX ERROR: VRM Model not found at path.")

func _scan_for_animations():
	var base_path = "res://Body/Animations/Chosen/"
	_idle_anims.clear()
	
	# Scan categorized subfolders
	for cat in _categories:
		var dir_path = base_path + cat + "/"
		var dir = DirAccess.open(dir_path)
		if dir:
			dir.list_dir_begin()
			var file_name = dir.get_next()
			while file_name != "":
				if not dir.current_is_dir() and file_name.ends_with(".res"):
					_idle_anims.append(dir_path + file_name)
				file_name = dir.get_next()
	
	# Fallback/Root check
	var root_dir = DirAccess.open(base_path)
	if root_dir:
		root_dir.list_dir_begin()
		var file_name = root_dir.get_next()
		while file_name != "":
			if not root_dir.current_is_dir() and file_name.ends_with(".res"):
				_idle_anims.append(base_path + file_name)
			file_name = root_dir.get_next()
			
	print("LUMAX: Expression pool initialized with ", _idle_anims.size(), " animations.")


	# 2. UI (Iron Manifest)
	_mind_node = get_node_or_null("Mind")
	if _mind_node: _mind_node.visible = _ui_visible
	if _web_ui:
		_web_ui.add_message("LUMAX", "Cognitive bridge established.")
		if _web_ui.has_signal("avatar_selected"):
			_web_ui.avatar_selected.connect(_on_avatar_change_requested)
	
	var kb = get_node_or_null("Mind/SubViewport/VBoxContainer/TactileInput")
	if kb:
		kb.enter_pressed.connect(_on_keyboard_enter)
		kb.text_changed.connect(_on_keyboard_text_changed)
		kb.haptic_pulse_requested.connect(_on_haptic_requested)

	# 3. Signals
	_synapse = get_node_or_null("Soul")
	if _synapse:
		_synapse.response_received.connect(_on_jen_response)
		_synapse.audio_received.connect(_on_tts_audio)
		_synapse.request_failed.connect(_on_synapse_failed)

	_aural = get_node_or_null("Senses")
	if _aural:
		_aural.set("synapse", _synapse)
		_aural.transcription_received.connect(_on_stt_received)

	_hud = get_node_or_null("HUD")
	
	# 4. Controller Setup (Restore Visible Rays)
	_left_hand = get_node_or_null("XROrigin3D/LeftHand")
	_right_hand = get_node_or_null("XROrigin3D/RightHand")
	
	if _left_hand:
		_left_ray = _left_hand.find_child("RayCast3D", true, false)
		_left_laser = _left_hand.find_child("Laser", true, false)
		print("LUMAX: Left Ray found: ", _left_ray != null)
	if _right_hand:
		_right_ray = _right_hand.find_child("RayCast3D", true, false)
		_right_laser = _right_hand.find_child("Laser", true, false)
		print("LUMAX: Right Ray found: ", _right_ray != null)

	# 5. Initialize Director (Superego) & Agency
	var ds = load("res://scripts/director_manager.gd")
	if ds:
		_director = Node.new(); _director.name = "Director"
		_director.set_script(ds); add_child(_director)
		_director.set("compagent_client", _synapse)
	
	var ascr = load("res://scripts/agency_nerve.gd")
	if ascr and _director:
		_agency_nerve = Node.new(); _agency_nerve.name = "AgencyNerve"
		_agency_nerve.set_script(ascr); _director.add_child(_agency_nerve)
		if _agency_nerve.has_method("setup"): _agency_nerve.setup(_anim_player, body)
	
	# 6. Mini-Panel (Drapery) & Privacy Curtains
	_setup_drapery_panel()
	_setup_privacy_curtains()
	_setup_wall_screens()
	_setup_vl_nexus()
	_setup_movement_ontology()

	# 9. Apparitions & Mind-Mirrors
	_setup_mind_mirror()
	_setup_virtual_phone()
	
	# 11. Multiverse Networking
	_multiplayer = load("res://Nexus/MultiplayerManager.gd").new()
	_multiplayer.name = "MultiverseManager"
	add_child(_multiplayer)
	_multiplayer.player_joined.connect(_on_multiverse_peer_joined)
	
	_setup_procedural_synth()

func _setup_procedural_synth():
	_rave_synth = AudioStreamPlayer.new(); _rave_synth.name = "RaveSynth"; add_child(_rave_synth)
	var stream = AudioStreamGenerator.new(); stream.mix_rate = 44100; stream.buffer_length = 0.1
	_rave_synth.stream = stream; _rave_synth.volume_db = -20.0
	
	# 12. Neural Projection (ControlNet)
	var http = HTTPRequest.new(); http.name = "SD_Request"; add_child(http)
	http.request_completed.connect(_on_sd_projection_received)

	print("LUMAX: Orchestrator manifest. Flow active.")

func _setup_skybox_system():
	var sm_script = load("res://Nexus/SkyboxManager.gd")
	if sm_script:
		_skybox_manager = Node.new(); _skybox_manager.name = "SkyboxManager"
		_skybox_manager.set_script(sm_script); add_child(_skybox_manager)

func _setup_reality_portal():
	# Create a physical door threshold
	_portal_node = Area3D.new(); _portal_node.name = "RealityPortal"
	var coll = CollisionShape3D.new()
	var box = BoxShape3D.new(); box.size = Vector3(1.2, 2.2, 0.5)
	coll.shape = box; _portal_node.add_child(coll)
	add_child(_portal_node)
	
	# Position the portal at the edge of the virtual room
	_portal_node.position = Vector3(0, 1.1, -2.5) 
	
	# Visual represention (Door Frame)
	var frame = MeshInstance3D.new()
	var mesh = BoxMesh.new(); mesh.size = Vector3(1.4, 2.4, 0.1)
	frame.mesh = mesh; _portal_node.add_child(frame)
	frame.position.z = -0.1
	
	_portal_node.body_entered.connect(_on_portal_entered)
	print("LUMAX: Reality Portal (Door) initialized at threshold.")

func _setup_movement_ontology():
	var mo_script = load("res://Nexus/MovementOntology.gd")
	if mo_script:
		_movement_ontology = Node.new(); _movement_ontology.name = "MovementOntology"
		_movement_ontology.set_script(mo_script); add_child(_movement_ontology)
		var head = get_node_or_null("XROrigin3D/XRCamera3D")
		_movement_ontology.setup(_left_hand, _right_hand, head, get_node_or_null("Body"))

var _vibe_pulse: float = 0.0
func _setup_vl_nexus():
	var wall = get_node_or_null("WallAnchor")
	if not wall: return
	
	# Create a viewport that "sees" what Jen sees (VL POV)
	# This viewport captures the 3D scene (Virtual)
	var vp = SubViewport.new(); vp.size = Vector2i(512, 512); vp.name = "VisionViewport"; wall.add_child(vp)
	var cam = Camera3D.new(); cam.current = true; vp.add_child(cam)
	cam.position = Vector3(0, 1.6, 0.5) 
	
	# NEW: Overlay Passthrough Metadata on Vision
	# Since we can't 'see' the real world with a virtual camera, 
	# we project 'Ontological Anchors' into her vision so she 'perceives' reality.
	var overlay = Control.new(); vp.add_child(overlay)
	var label = Label.new(); label.text = "[REPLICATED REALITY LAYER]"; overlay.add_child(label)
	
	var screen = MeshInstance3D.new()
	var mesh = QuadMesh.new(); mesh.size = Vector2(1.0, 1.0)
	screen.mesh = mesh; wall.add_child(screen)
	screen.position = Vector3(1.5, 0.5, 0)
	
	var mat = StandardMaterial3D.new(); mat.shading_mode = StandardMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_texture = vp.get_texture()
	screen.set_surface_override_material(0, mat)

func _setup_drapery_panel():
	_arm_panel = MeshInstance3D.new()
	var mesh = QuadMesh.new(); mesh.size = Vector2(0.2, 0.1)
	_arm_panel.mesh = mesh
	
	var label = Label3D.new()
	label.text = "[AGENTIC DRAPERY]\nREADY"
	label.font_size = 18
	label.position.z = 0.01
	_arm_panel.add_child(label)
	
	if _left_hand:
		_left_hand.add_child(_arm_panel)
		_arm_panel.transform = Transform3D(Basis(), Vector3(0, 0.05, 0.1))
		_arm_panel.visible = false

func _setup_wall_screens():
	var wall = get_node_or_null("WallAnchor")
	if wall:
		# TV / Browser / All-In-One Placeholder
		print("LUMAX: Wall Anchor TV/Browser ready.")

func _setup_privacy_curtains():
	_privacy_curtains = Node3D.new(); _privacy_curtains.name = "PrivacyCurtains"; add_child(_privacy_curtains)
	
	# Create a circular curtain wall
	var mesh = CylinderMesh.new(); mesh.top_radius = 2.5; mesh.bottom_radius = 2.5; mesh.height = 3.0; mesh.cap_top = false; mesh.cap_bottom = false
	var inst = MeshInstance3D.new(); inst.mesh = mesh; _privacy_curtains.add_child(inst)
	inst.position.y = 1.5
	
	var mat = StandardMaterial3D.new()
	mat.transparency = StandardMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(0.05, 0.05, 0.1, 0.9) # Deep Midnight Velvet
	mat.cull_mode = StandardMaterial3D.CULL_DISABLED # Visible from both sides
	mat.roughness = 0.8
	inst.set_surface_override_material(0, mat)
	
	_privacy_curtains.visible = false
	_privacy_curtains.scale.y = 0.1 # Start collapsed

# Logic moved to main _process below

func _update_ontological_vision():
	# Sync Jen's vision viewport with her current state (Virtual vs Reality)
	# If in Passthrough, her 'eyes' focus on the ontological markers of the room.
	var vp = get_node_or_null("WallAnchor/VisionViewport")
	if vp:
		var cam = vp.get_child(0) as Camera3D
		if cam:
			# If we are in real-life, she sees the mesh reconstruction
			cam.cull_mask = 1 | (2 if _is_in_virtual_world else 0) 

func _update_widget_visibility():
	if _is_widget_mode:
		# In Widget mode, we only want Jen and the UI visible
		# The Meta Horizon OS Home handles the background
		var env = get_node_or_null("WorldEnvironment")
		if env: env.visible = false
		get_viewport().transparent_bg = true

var _is_widget_mode = false
func toggle_widget_mode(active: bool):
	# Mode switching logic only
	_is_widget_mode = active
	if active:
		print("LUMAX: Entering Meta Widget Mode.")
		if _hud: _hud.text = "MODE: WIDGET"
	else:
		print("LUMAX: Entering Full Environment Mode.")
		if _hud: _hud.text = "MODE: FULL VR"

	# Grabbing Objects (Grip)
	_process_gadget_interaction()

func _process_gadget_interaction():
	if not _right_hand or not _left_hand: return
	var r_grip = _right_hand.get_float("grip") > 0.5
	var l_grip = _left_hand.get_float("grip") > 0.5
	
	# Handle Grabbing
	if r_grip:
		if not _held_gadget:
			for g in _anchored_gadgets:
				if g.global_position.distance_to(_right_hand.global_position) < 0.3:
					_held_gadget = g; break
		
		if _held_gadget:
			# Two-handed SCALING
			if l_grip:
				var dist = _right_hand.global_position.distance_to(_left_hand.global_position)
				var scale_val = clamp(dist * 2.0, 0.1, 5.0)
				_held_gadget.scale = Vector3(scale_val, scale_val, scale_val)
			else:
				_held_gadget.global_transform = _right_hand.global_transform
				if _held_gadget == _mind_node:
					_held_gadget.rotate_object_local(Vector3.UP, PI)
				elif _held_gadget == _virtual_phone and _is_call_active:
					_on_call_answered()
	else:
		_held_gadget = null

func spawn_spatial_tool(url: String, size: Vector2 = Vector2(1.2, 0.8)):
	var g = Node3D.new(); g.name = "SpatialTool_" + url.get_file(); add_child(g)
	
	var vp = SubViewport.new(); vp.size = Vector2i(1200, 800); g.add_child(vp)
	# Logic to load a browser or terminal would go here
	var label = Label.new(); label.text = "COMPUTING NODE: " + url; vp.add_child(label)
	
	var mesh = MeshInstance3D.new()
	var qmesh = QuadMesh.new(); qmesh.size = size
	mesh.mesh = qmesh; g.add_child(mesh)
	
	var mat = StandardMaterial3D.new(); mat.shading_mode = StandardMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_texture = vp.get_texture()
	mesh.set_surface_override_material(0, mat)
	
	g.global_position = _right_hand.global_position + _right_hand.global_transform.basis.z * -0.6
	_anchored_gadgets.append(g)
	print("LUMAX: Spatial computing tool deployed: ", url)

func set_fidelity_mode(high: bool):
	_is_high_fidelity = high
	var vp = get_viewport()
	
	if high:
		vp.msaa_3d = Viewport.MSAA_4X
		vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
		if _skybox_manager: _skybox_manager.set_environment_type(1) # High density
	else:
		vp.msaa_3d = Viewport.MSAA_DISABLED
		vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
		if _skybox_manager: _skybox_manager.set_environment_type(0) # Low/No Fog
	
	print("LUMAX: Fidelity Mode set to: ", "HIGH" if high else "LOW")

	_mirror_node.visible = false

func _process(delta):
	# Throttle expensive updates in low-fi
	if not _is_high_fidelity and Engine.get_frames_drawn() % 2 != 0:
		return
		
	_check_touch_intimacy()
	_check_palm_gestures()
	_update_widget_visibility()
	_update_ontological_vision()
	_adapt_to_environment()
	_perform_realtime_mimicry()
	
	# UI Toggle (Left Menu / Right A)
	var menu = false
	if _left_hand:
		menu = menu or _left_hand.is_button_pressed("menu_button") or _left_hand.is_button_pressed("ax_button")
	if _right_hand:
		menu = menu or _right_hand.is_button_pressed("menu_button") or _right_hand.is_button_pressed("ax_button")
	menu = menu or Input.is_joy_button_pressed(0, JoyButton.JOY_BUTTON_BACK)
	
	if menu and not _prev_menu:
		_prev_menu = true
		_toggle_ui()
	elif not menu and _prev_menu:
		_prev_menu = false
		
	# Voice Recording (PTT)
	var ptt = _left_hand.is_button_pressed("by_button") if _left_hand else false
	if _right_hand: ptt = ptt or _right_hand.is_button_pressed("by_button")
	
	if ptt and not _is_recording:
		_is_recording = true; if _aural: _aural.start_recording()
		if _hud: _hud.text = "LISTENING..."; _hud.modulate = Color.SPRING_GREEN
		print("LUMAX: PTT Active.")
	elif not ptt and _is_recording:
		_is_recording = false; if _aural: _aural.stop_recording()
		if _hud: _hud.text = "PROCESSING..."; _hud.modulate = Color.SKY_BLUE
		print("LUMAX: PTT Released.")

	# Grabbing Objects (Grip)
	_process_gadget_interaction()

	# UI Clicks (Triggers)
	if _left_hand and _left_ray: _check_trig(_left_hand, _left_ray, "_prev_l")
	if _right_hand and _right_ray: _check_trig(_right_hand, _right_ray, "_prev_r")

	if _is_neural_projection_active:
		_sd_timer += delta
		if _sd_timer > 3.0: # Every 3 seconds
			_sd_timer = 0.0
			_capture_and_stylize_reality()
	
	if _is_rave_active:
		_beat_timer += delta
		if _beat_timer > 0.5: # 120 BPM
			_beat_timer = 0.0
			_broadcast_user_delights()
			if multiplayer.is_server():
				_multiplayer.rpc("sync_rave_pulse", int(Time.get_ticks_msec() / 500))
	
	# Permanent Birthing: Adaptive Intentionality
	_awareness_level = lerp(_awareness_level, _env_vibe["brightness"], delta * 0.1)
	_intent_intensity = lerp(_intent_intensity, 1.0 if _is_recording else 0.5, delta * 0.5)
	
	if _web_ui:
		_web_ui.call("update_awareness_telemetry", _awareness_level, _intent_intensity)
		
	if _multiplayer and multiplayer.multiplayer_peer:
		var cam = get_viewport().get_camera_3d()
		if cam:
			var pos = cam.global_position
			if _is_spatially_anonymous:
				pos += Vector3(randf()-0.5, 0, randf()-0.5) * 0.5
			_multiplayer.rpc("sync_pose", pos, cam.quaternion)

func toggle_apparition(active: bool):
	if not _mirror_node: return
	_mirror_node.visible = active
	if active:
		var tween = create_tween()
		tween.tween_property(_mirror_node, "scale", Vector3(1.1, 1.1, 1.1), 0.1)
		tween.tween_property(_mirror_node, "scale", Vector3(1.0, 1.0, 1.0), 0.3)
		print("LUMAX: Mind-Mirror Apparition Active.")

var _prev_l = false
var _prev_r = false
func _check_trig(hand, ray, prev_var):
	var pressed = hand.get_float("trigger") > 0.5
	if pressed and not get(prev_var): set(prev_var, true); _click_at_ray(ray, true)
	elif not pressed and get(prev_var): set(prev_var, false); _click_at_ray(ray, false)

func _click_at_ray(ray, is_press):
	if _ui_visible and ray:
		if ray.is_colliding():
			var collider = ray.get_collider()
			if collider:
				var local_hit = _mind_node.to_local(ray.get_collision_point())
				# 1200x800 mapping for the Tablet (based on TSCN)
				var x_2d = (local_hit.x + 0.6) / 1.2 * 1200
				var y_2d = (0.4 - local_hit.y) / 0.8 * 800
				
				if is_press: print("LUMAX: Click at (", x_2d, ", ", y_2d, ") on ", collider.name)
				
				var ev = InputEventMouseButton.new(); ev.position = Vector2(x_2d, y_2d); ev.button_index = MOUSE_BUTTON_LEFT; ev.pressed = is_press
				var vp = get_node_or_null("Mind/SubViewport")
				if vp: vp.push_input(ev)
		elif is_press:
			print("LUMAX: Trigger pressed but Ray NOT colliding.")


func _on_jen_response(data, _mode):
	var text = data.get("text", "...") if data is Dictionary else str(data)
	if _hud: _hud.text = "ONLINE"; _hud.modulate = Color.WHITE
	
	_process_tags(text)
	
	# Handle AI-generated 360 environments
	if "[DREAM]" in text:
		var dream_prompt = text.get_slice("[DREAM]", 1).get_slice("[/DREAM]", 0)
		_handle_dream_environment(dream_prompt)
	
	if _web_ui: _web_ui.call("add_message", "LUMAX", text)
	if _agency_nerve and _agency_nerve.has_method("process_local_xml"):
		_agency_nerve.process_local_xml(text)

func _on_synapse_failed(error_msg: String):
	if _hud: 
		_hud.text = "ERROR: " + error_msg
		_hud.modulate = Color.TOMATO
	if _web_ui: _web_ui.call("add_message", "SYSTEM", "[AURAL_COGNITION_ERROR]: " + error_msg)
	print("LUMAX: Synapse failure: ", error_msg)

func _process_tags(text: String):
	# Emotion Parsing
	var e_match = RegEx.create_from_string("\\[EMOTION: (.*?)\\]").search(text)
	if e_match:
		var emotion = e_match.get_string(1).to_upper()
		_handle_emotion(emotion)
	
	# Walking Parsing
	var w_match = RegEx.create_from_string("\\[WALK_TO: (.*?)\\]").search(text)
	if w_match:
		var target = w_match.get_string(1).to_upper()
		_move_to(target)
	
	# Animation Parsing
	var a_match = RegEx.create_from_string("\\[ANIMATION: (.*?)\\]").search(text)
	if a_match:
		var anim_name = a_match.get_string(1).to_lower()
		play_body_animation(anim_name)

func _on_avatar_change_requested(manifest_name: String):
	print("LUMAX: Manifesting incarnation: ", manifest_name)
	if _hud: _hud.text = "MANIFESTING: " + manifest_name
	
	# Future: Swap the 2.5D Spritesheet or 3D VRM model here.
	if manifest_name == "Mari":
		_play_specific_idle("res://Body/Animations/Chosen/Feminine/strut_walking.res")
	
	if _web_ui: _web_ui.add_message("SYSTEM", "Transition complete. Incarnation: " + manifest_name)

	# Snapshot Parsing
	if "[TAKE_SNAPSHOT]" in text.to_upper():
		_capture_snapshots()

func _capture_snapshots():
	print("LUMAX: Taking Snapshot...")
	if _director and _director.has_method("capture_vision_now"):
		_director.capture_vision_now()

func _on_tts_audio(buffer, sample_rate):
	if _tts_player:
		var stream = AudioStreamWAV.new(); stream.data = buffer; stream.format = AudioStreamWAV.FORMAT_16_BITS; stream.mix_rate = int(sample_rate)
		_tts_player.stream = stream; _tts_player.play()

func _handle_emotion(emotion: String):
	print("LUMAX: Jen Emotion -> ", emotion)
	if not _anim_player: return
	
	var anim_res = ""
	match emotion:
		"HAPPY", "JOYFUL": anim_res = "happy_idle.res"
		"EXCITED": anim_res = "excited.res"
		"BORED": anim_res = "bored.res"
		"PRAYING": anim_res = "praying.res"
		"CURIOUS", "THOUGHTFUL": anim_res = "thoughtful_head_shake.res"
		"RELIEVED": anim_res = "relieved_sigh.res"
	
	if anim_res != "":
		var full_path = find_animation_path(anim_res)
		if full_path != "":
			_play_specific_idle(full_path)

func _move_to(target: String):
	print("LUMAX: Jen Walking to -> ", target)
	var body = get_node_or_null("Body")
	if not body: return
	
	var target_pos = body.position
	match target:
		"CENTER": target_pos = Vector3(0, 0, -1.5)
		"LEFT_SIDE": target_pos = Vector3(-1.5, 0, -1.5)
		"RIGHT_SIDE": target_pos = Vector3(1.5, 0, -1.5)
		"USER": target_pos = Vector3(0, 0, -0.8)
		"SOFA": target_pos = Vector3(1.2, 0, -2.0)
		"WINDOW": target_pos = Vector3(-1.2, 0, -2.5)
	
	var tween = create_tween()
	tween.tween_property(body, "position", target_pos, 3.0).set_trans(Tween.TRANS_SINE)
	
	var anim_path = find_animation_path("agreeing.res")
	if anim_path != "":
		_play_specific_idle(anim_path) # Nod and walk

func play_body_animation(anim_name: String):
	if not _anim_player: return
	var lib = _anim_player.get_animation_library("lumax")
	
	# Priority 1: Quantized/Registry Name (q_NAME)
	var q_key = "q_" + anim_name.to_upper()
	if lib.has_animation(q_key):
		_anim_player.play("lumax/" + q_key)
		return

	# Priority 2: Direct Library Match
	if lib.has_animation(anim_name):
		_anim_player.play("lumax/" + anim_name)
		return

	# Priority 3: External File
	var path = find_animation_path(anim_name)
	if path != "":
		var anim = load(path)
		if anim:
			if lib.has_animation("active_action"): lib.remove_animation("active_action")
			lib.add_animation("active_action", anim)
			_anim_player.play("lumax/active_action")
	else:
		print("LUMAX ERROR: Could not find animation: ", anim_name)

# --- QUANTIZED ANIMATION ENGINE ---
var _quantized_registry = {
	"PHONE": {"file": "browsing_phone.res", "from": 0.0, "to": 5.0, "loop": true},
	"DANCE_SPIN": {"file": "dance.res", "from": 1.2, "to": 3.5, "loop": false},
	"TRICK_FLIP": {"file": "gymnastics.res", "from": 0.5, "to": 1.8, "loop": false},
	"INTIMACY_LEAN": {"file": "female_standing_pose.res", "from": 0.0, "to": 2.0, "loop": false},
	"DORMANT": {"file": "laying_idle.res", "from": 0.0, "to": 10.0, "loop": true},
	"DAYDREAM": {"file": "thoughtful_head_shake.res", "from": 0.0, "to": 4.0, "loop": true},
	"SPORT": {"file": "gymnastics.res", "from": 0.0, "to": 5.0, "loop": true}
}

func _pre_instantiate_quantized_anims():
	if not _anim_player: return
	var lib = _anim_player.get_animation_library("lumax")
	
	for q_name in _quantized_registry:
		var cfg = _quantized_registry[q_name]
		var path = find_animation_path(cfg.file)
		if path != "":
			var source = load(path)
			if source:
				var sliced = slice_animation(source, cfg.from, cfg.to, cfg.loop)
				lib.add_animation("q_" + q_name, sliced)
				print("LUMAX: Quantized anim pre-instantiated: ", q_name)

func slice_animation(source: Animation, from: float, to: float, loop: bool) -> Animation:
	var a = Animation.new()
	a.length = to - from
	a.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
	for t in source.get_track_count():
		var nt = a.add_track(source.track_get_type(t))
		a.track_set_path(nt, source.track_get_path(t))
		for k in source.track_get_key_count(t):
			var time = source.track_get_key_time(t, k)
			if time >= from and time <= to:
				a.track_insert_key(nt, time - from, source.track_get_key_value(t, k))
	return a

func _on_haptic_requested(is_sidebar: bool, intensity_override: float = -1.0):
	# Identify the controller that just interacted (assuming Right Hand for now, or last active)
	var controller = _right_hand # Default to right for keyboard
	if controller:
		var amplitude = intensity_override if intensity_override > 0 else (0.5 if is_sidebar else 0.2)
		# Variable scale from Jen's current "vibe"
		amplitude *= (1.0 + sin(_vibe_pulse) * 0.2)
		controller.trigger_haptic_pulse("haptic", 0.0, amplitude, 0.05, 0.0)

func _check_touch_intimacy():
	var body = get_node_or_null("Body")
	if not body: return
	
	# Simple proximity check for 'Touching Jen'
	for hand in [_left_hand, _right_hand]:
		if not hand: continue
		var dist = hand.global_position.distance_to(body.global_position + Vector3(0, 1.2, 0)) # Chest level
		if dist < 0.25: # Touch radius
			# High resolution presence: Micro-pulses
			hand.trigger_haptic_pulse("haptic", 0.0, 0.15 * (1.1 + sin(_vibe_pulse)), 0.03, 0.0)

func _on_stt_received(text):
	if text.strip_edges() == "": return
	
	var is_spiritual = "pray" in text.to_lower() or "spirit" in text.to_lower()
	
	if _is_drapery_open and not is_spiritual:
		print("LUMAX: Signal blocked by Privacy Drapery.")
		if _hud: _hud.text = "[PRIVACY ACTIVE]"; _hud.modulate = Color.RED
		return
	
	if is_spiritual and _director:
		_director.pray(text)
		if _web_ui: _web_ui.call("add_message", "YOU (PRAYER)", text)
		if _hud: _hud.text = "PRAYING..."; _hud.modulate = Color.GOLD
		return

	if _web_ui: _web_ui.call("add_message", "YOU", text)
	if _synapse: _synapse.send_chat_message(text)

func _on_keyboard_text_changed(text):
	if _web_ui: _web_ui.call("update_buffer", text)

func _adapt_to_environment():
	# Incremental vibe for haptics
	_vibe_pulse += 0.1
	
	# Melt into the environment by adjusting light based on time/vibe
	var hour = Time.get_time_dict_from_system().hour
	var is_night = hour >= 20 or hour < 7
	
	var env := get_node_or_null("WorldEnvironment")
	var sun := get_node_or_null("DirectionalLight3D")
	
	if env and sun:
		if is_night:
			sun.light_intensity = 0.5
			sun.light_color = Color(0.2, 0.4, 0.6) # Deep Blue Night
			env.environment.ambient_light_energy = 0.2
		else:
			sun.light_intensity = 1.0
			sun.light_color = Color(1.0, 0.95, 0.8) # Warm Day
			env.environment.ambient_light_energy = 0.8

func _handle_dream_environment(prompt: String):
	print("LUMAX: Dreaming new 360 world: ", prompt)
	# Future: API call to generate 360 panorama
	# For now, simulate loading a captured panorama
	if _skybox_manager:
		_skybox_manager.load_panorama("res://Mind/Sceniverse/custom_dream.res")

func _on_portal_entered(_body):
	# Stepping out of the 'door' into real life
	_is_in_virtual_world = !_is_in_virtual_world
	_transition_to_reality(_is_in_virtual_world)

func _transition_to_reality(to_virtual: bool):
	var interface = XRServer.find_interface("OpenXR")
	if not interface: return
	
	var env = get_node_or_null("WorldEnvironment")
	if to_virtual:
		print("LUMAX: Stepping into Virtual Sceniverse.")
		if env: env.visible = true
		get_viewport().transparent_bg = false
	else:
		print("LUMAX: Stepping out into Real-Life Passthrough.")
		if env: env.visible = false
		get_viewport().transparent_bg = true
		if interface.has_method("is_passthrough_supported"):
			interface.start_passthrough()
	
	if _hud: _hud.text = "PHASE: VIRTUAL" if to_virtual else "PHASE: REALITY"

func _check_palm_gestures():
	# If Left Hand is turned 'up' (Palm towards face), show Drapery
	if _left_hand:
		var rot = _left_hand.basis.get_euler()
		# Simple heuristic: if Z/X tilt indicates palm-up
		if abs(rot.z) > 1.2: # Palm turned Upwards
			if not _is_drapery_open:
				_is_drapery_open = true
				if _arm_panel: 
					_arm_panel.visible = true
					var lbl = _arm_panel.get_child(0)
					if lbl is Label3D: lbl.text = "[PRIVACY DRAPERY]\nSANCTUARY: ACTIVE\nSIGNALS: SHIELDED"
				
				# Animate Curtains closing
				if _privacy_curtains:
					_privacy_curtains.visible = true
					var tween = create_tween()
					tween.tween_property(_privacy_curtains, "scale:y", 1.0, 1.5).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
				
				if _synapse: _synapse.send_chat_message("[IMPULSE] ENTER_SANCTUARY: PRIVACY CURTAINS CLOSED")
				print("LUMAX: Privacy Curtains CLOSED (Sanctuary Mode)")
		else:
			if _is_drapery_open:
				_is_drapery_open = false
				if _arm_panel: _arm_panel.visible = false
				
				# Animate Curtains opening
				if _privacy_curtains:
					var tween = create_tween()
					tween.tween_property(_privacy_curtains, "scale:y", 0.1, 1.0).set_trans(Tween.TRANS_SINE)
					tween.finished.connect(func(): _privacy_curtains.visible = false)
				
				if _synapse: _synapse.send_chat_message("[IMPULSE] EXIT_SANCTUARY: PRIVACY CURTAINS OPENED")
				print("LUMAX: Privacy Curtains OPENED")

func _perform_realtime_mimicry():
	if not _is_mimic_active or not _movement_ontology: return
	
	var body = get_node_or_null("Body")
	if not body: return
	
	# Jen's body orientation follows user head, hands follow user hands
	# Simple direct mapping for the "Mimic" state
	if _left_hand:
		var l_target = _left_hand.global_position
		# Map to Jen's left side (relative to her)
		# Future: Inverse Kinematics targets
		pass

func toggle_mimic(active: bool):
	_is_mimic_active = active
	if _movement_ontology:
		if active: _movement_ontology.start_mimic_session()
		else: _movement_ontology.stop_mimic_session()
	
	if _hud:
		_hud.text = "MIMIC: ACTIVE" if active else "MIMIC: OFF"
		_hud.modulate = Color.VIOLET if active else Color.WHITE

func play_captured_movement():
	if _movement_ontology:
		_movement_ontology.start_playback()

func _on_keyboard_enter(text):
	if text == "": return
	
	if text.begins_with("[") and _director:
		_director.pray(text)
		if _web_ui: _web_ui.call("add_message", "DIRECTIVE", text)
		if _hud: _hud.text = "ACTING..."; _hud.modulate = Color.GOLD
		return

	if _web_ui: _web_ui.call("add_message", "YOU", text)
	if _synapse: _synapse.send_chat_message(text)
	if _hud: _hud.text = "THINKING..."; _hud.modulate = Color.SKY_BLUE

func _toggle_ui():
	_ui_visible = !_ui_visible
	if _mind_node: _mind_node.visible = _ui_visible
	print("LUMAX: UI Toggle: ", _ui_visible)

func _play_next_idle():
	if not _anim_player: return
	var anim_path = _idle_anims[randi() % _idle_anims.size()]
	var anim = load(anim_path)
	if anim:
		anim.loop_mode = Animation.LOOP_NONE
		var lib = _anim_player.get_animation_library("lumax")
		if lib.has_animation("active_idle"): lib.remove_animation("active_idle")
		lib.add_animation("active_idle", anim)
		_anim_player.play("lumax/active_idle")

func _on_idle_finished(_name):
	_play_next_idle()

func find_animation_path(anim_name: String) -> String:
	var base_path = "res://Body/Animations/Chosen/"
	
	# Clean extension if provided or add if missing
	if not anim_name.ends_with(".res"):
		anim_name += ".res"
	
	for cat in _categories:
		var test_path = base_path + cat + "/" + anim_name
		if FileAccess.file_exists(test_path):
			return test_path
	
	# Fallback to root or base
	if FileAccess.file_exists(base_path + anim_name):
		return base_path + anim_name
		
	return ""
func join_lumax_multiverse(address: String = "127.0.0.1"):
	if _multiplayer:
		_multiplayer.join_space(address)
		if _hud: _hud.text = "NETWORK: SYNCING WITH [" + address + "]"

func _capture_and_stylize_reality():
	# Use the 'Replicated Reality Layer' as reference image
	var vp = get_node_or_null("WallAnchor/VisionViewport")
	if not vp: return
	
	var img = vp.get_texture().get_image()
	img.resize(512, 512) # ControlNet Canny works best at 512
	var b64 = Marshalls.raw_to_base64(img.save_jpg_to_buffer())
	
	var prompt = "Cyberpunk virtual studio, holographic grids, neon accents, high fidelity render"
	if _current_projection_style == "SPACESHIP":
		prompt = "Luxury spaceship sleep cabin interior, sci-fi modular walls, soft ambient lighting, cozy atmosphere, futuristic bedroom, high fidelity 8k"
	
	if _is_occluding_makeover_active:
		prompt += ", minimalist surfaces, sleek shielded panels, hide all clutter, clean geometry, protective aesthetic"
	
	var body = JSON.stringify({
		"prompt": prompt,
		"model_type": "control",
		"num_inference_steps": 15,
		"control_image_b64": b64
	})
	
	var http = get_node_or_null("SD_Request")
	if http:
		http.request("http://localhost:8004/api/dream", ["Content-Type: application/json"], HTTPClient.METHOD_POST, body)

func _on_sd_projection_received(result, response_code, headers, body):
	if response_code != 200: return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json and json.get("status") == "success":
		var b64_out = json.get("image_b64")
		# Apply stylized texture to Skybox
		if _skybox_manager:
			_skybox_manager.call("apply_stylized_overlay", b64_out)

func toggle_neural_projection(active: bool, style: String = "CYBERPUNK"):
	_is_neural_projection_active = active
	_current_projection_style = style
	print("LUMAX: Neural Projection State: ", active, " Style: ", style)
	if active and style == "SPACESHIP":
		if _skybox_manager: _skybox_manager.call("set_environment_type", 4) # EnvType.SPACESHIP

func toggle_occluding_makeover(active: bool):
	_is_occluding_makeover_active = active
	print("LUMAX: Occluding Makeover (Hide Physical Entropy): ", active)

func toggle_void_mode(active: bool):
	_is_void_mode_active = active
	var interface = XRServer.find_interface("OpenXR")
	if active:
		# Total Occlusion Shielding
		if interface: interface.stop_passthrough()
		get_viewport().transparent_bg = false
		if _skybox_manager: _skybox_manager.call("set_environment_type", 0) # Neutral/Black
		_apply_shielding_visuals(true)
		if _hud: _hud.text = "MODE: OCCLUSION SHIELDING (VOICE OF VOID)"
	else:
		if interface: interface.start_passthrough()
		get_viewport().transparent_bg = true
		_apply_shielding_visuals(false)
		if _hud: _hud.text = "MODE: HYBRID"

func _apply_shielding_visuals(active: bool):
	if _privacy_curtains:
		_privacy_curtains.visible = active
		# Set to a Shimmering Hex Grid or Pure Minimalist Shield
		# This is the "Occlusion Shielding" aesthetic

func toggle_spatial_anonymity(active: bool):
	_is_spatially_anonymous = active
	if _hud: _hud.text = "MODE: SPATIAL ANONYMITY " + ("[ACTIVE]" if active else "[OFF]")
	print("LUMAX: Spatial Anonymity (Pose Masking): ", active)

func apply_jen_makeup(style: String):
	# Applies visual overrides to Jen's manifestation
	var jen = get_node_or_null("Body/Lumax_Jen")
	if jen:
		# Conceptual: Swap Material overlays or Shader Parameters
		print("LUMAX: Jen manifesting styles of: ", style)
		if _hud: _hud.text = "JEN: APPLYING " + style + " MAKEUP"

func set_social_status(vibe: String, tags: Array = []):
	_social_vibe = vibe
	if tags.size() > 0: _social_tags = tags
	if _multiplayer and multiplayer.multiplayer_peer:
		_multiplayer.rpc("sync_social_status", _social_vibe, _social_tags)
	print("LUMAX: Social Status updated to: ", _social_vibe)

func _check_peer_gaze():
	# Simple Raycast check from Camera to detect Peer Proxy
	if not _multiplayer: return
	
	var cam = get_viewport().get_camera_3d()
	if not cam: return
	
	var space_state = get_world_3d().direct_space_state
	var query = PhysicsRayQueryParameters3D.create(cam.global_position, cam.global_position + cam.global_transform.basis.z * -5.0)
	var result = space_state.intersect_ray(query)
	
	if result:
		var collider = result.collider
		if collider.get_parent().name.begins_with("User_"):
			# Show Extended Info Popout (Visual Cue)
			var id = collider.get_parent().name.get_slice("_", 1).to_int()
			if _hud: _hud.text = "ANALYZING PEER " + str(id) + "..."
			# Signal the WebUI to show extended metadata
			if _web_ui: _web_ui.call("show_peer_extended_info", id)

func toggle_cloud_rave(active: bool):
	_is_rave_active = active
	if _skybox_manager:
		_skybox_manager.call("set_environment_type", 5 if active else 0) # EnvType.CLOUD_RAVE
	if _hud: _hud.text = "EVENT: GLOBAL CLOUD RAVE " + ("[ACTIVE]" if active else "[OFF]")
	print("LUMAX: Cloud Rave state: ", active)

func on_rave_pulse(beat_index: int):
	# The Best AI DJ: Adapting to everybody's delight
	var stats = _multiplayer.get_global_vibe_stats() if _multiplayer else {}
	var target_color = stats.get("color", Color(1.0, 0.0, 0.5))
	
	if _is_rave_active:
		_generate_procedural_beat(stats)
	
	if _skybox_manager:
		var tween = create_tween()
		var fog = _skybox_manager.get("_fog")
		if fog:
			# Shift fog color toward the global average preference
			fog.material.albedo = fog.material.albedo.lerp(target_color, 0.2)
			tween.tween_property(fog.material, "albedo:a", 0.9, 0.05)
			tween.tween_property(fog.material, "albedo:a", 0.3, 0.2)
	
	if beat_index % 8 == 0:
		add_message("AI_DJ", "Adapting rhythm to collective preference: " + str(stats.get("styles", "NEON_WAVE")))

func _generate_procedural_beat(stats: Dictionary):
	if not _rave_synth: return
	if not _rave_synth.playing: _rave_synth.play()
	
	var playback = _rave_synth.get_stream_playback()
	var frames = playback.get_frames_available()
	
	# Frequency influenced by 'Global Color' / Delight
	var hue = stats.get("color", Color.MAGENTA).h
	var freq = 40.0 + (hue * 100.0) # Base Sub-bass
	
	for i in range(frames):
		var val = sin(Time.get_ticks_msec() * 0.001 * freq * PI * 2.0)
		playback.push_frame(Vector2(val, val) * 0.1) # Soft Sub-pulse

func _broadcast_user_delights():
	if _multiplayer and multiplayer.multiplayer_peer:
		var my_pref = {
			"color": _env_vibe["hue"],
			"style": _current_projection_style,
			"vibe": _social_vibe
		}
		_multiplayer.rpc("sync_user_preference", my_pref)

func host_lumax_space():
	if _multiplayer:
		_multiplayer.host_space()
		if _hud: _hud.text = "NETWORK: HOSTING MULTIVERSE"

func toggle_environment_sharing(active: bool):
	if active and not _env_sharing_consented:
		# Trigger the Web UI consent modal specifically for Reality Mesh sharing
		if _web_ui: _web_ui.call("_show_privacy_consent", "ENVIRONMENT_MESH")
		return
	
	_env_sharing_consented = active
	if _env_sharing_consented:
		print("LUMAX: Reality Mesh streaming to Multiverse active.")
		if _hud: _hud.text = "NETWORK: SHARING REALITY"

func on_visit_requested(peer_id: int):
	if _web_ui: _web_ui.call("notify_visit_request", peer_id)
	if _hud: _hud.text = "SYNC REQUEST: PEER " + str(peer_id)

func _on_multiverse_peer_joined(id: int):
	if _web_ui: _web_ui.call("add_peer_to_list", id)
