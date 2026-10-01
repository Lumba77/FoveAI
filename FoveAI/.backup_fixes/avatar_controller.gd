class_name AvatarController
extends Node

## Implements Kinematic Character Controller with Mixamo Animation States.
## ENHANCED: PUPPET LAYER (IK), STEERING, AND SENSORY AWARENESS.

@export var avatar_node: Node3D
@export var player_camera: Node3D
@export var shyness_intensity: float = 0.3

signal tts_playback_finished
signal capture_requested(source: String)

const _LIB_NAME: StringName = &"mixamo"
@export var clip_paths: Dictionary = {
	&"idle": "breathing_idle",
	&"walk": "standard_walk",
	&"walk_back": "standing_run_back",
	&"walk_left": "standing_walk_left",
	&"walk_right": "standing_walk_right",
	&"run": "walking",
	&"jump": "standing_jump",
	&"turn_left": "left_turn",
	&"turn_right": "right_turn",
	&"sit": "seated_idle",
	&"stand_to_sit": "standing_to_sit",
	&"wave": "standing_greeting",
	&"point": "sitting_and_pointing",
	&"nod": "head_nod_yes",
	&"shake": "shaking_head_no",
	&"happy": "happy_idle",
	&"sad": "sad_idle",
	&"angry": "angry",
	&"laugh": "laughing",
	&"excited": "excited",
	&"bored": "bored",
	&"dance": "dancing_twerk",
	&"texting": "talking_on_phone",
	&"look_around": "look_away_gesture",
	&"lay": "laying_idle",
	&"praying": "praying",
	&"handshake": "shaking_hands_1",
	&"clapping": "standing_clap",
}

var _animation_tree: AnimationTree
var _body_animation_player: AnimationPlayer
var _skeleton: Skeleton3D
var _head_bone_idx: int = -1
var _face_mesh: MeshInstance3D

# --- PUPPET LAYER (IK) ---
var _ik_left_hand: SkeletonIK3D
var _ik_right_hand: SkeletonIK3D
var _target_l: Marker3D
var _target_r: Marker3D
var _ik_active: bool = false

# --- NATURAL BEHAVIOR ENGINE ---
enum GazeMode { PLAYER, LOOK_AWAY, IDLE, SHY, INTERESTED, TRACK_TARGET }
var _blink_timer: float = 0.0
var _next_blink_time: float = 3.0
var _is_blinking: bool = false
var _blink_duration: float = 0.1
var _gaze_mode: int = GazeMode.PLAYER
var _gaze_timer: float = 0.0
var _gaze_target_pos: Vector3 = Vector3.ZERO
var _saccade_timer: float = 0.0
var _saccade_offset: Vector3 = Vector3.ZERO

# --- DYNAMIC POSE ENGINE ---
var _idle_variation_timer: float = 0.0
var _procedural_sway: float = 0.0
var _weight_shift: float = 0.0 

func _process(delta: float) -> void:
	if not avatar_node: return
	_update_body_orientation(delta)
	_process_natural_behavior(delta)
	_process_lip_sync(delta)
	_process_dynamic_pose(delta)
	_update_ik_blending(delta)

func _update_body_orientation(delta: float) -> void:
	var cam = get_viewport().get_camera_3d()
	if not cam or not player_camera: return
	
	var target_pos = player_camera.global_position
	target_pos.y = avatar_node.global_position.y
	
	var dir = (target_pos - avatar_node.global_position).normalized()
	if dir.length_squared() > 0.01:
		var target_basis = Basis.looking_at(-dir, Vector3.UP)
		avatar_node.global_transform.basis = avatar_node.global_transform.basis.slerp(target_basis, delta * 0.5)

func _ready() -> void:
	if not avatar_node: 
		avatar_node = get_node_or_null("AvatarModel")
		if not avatar_node:
			avatar_node = get_parent().find_child("AvatarModel", true, false)
			
	_setup_references()
	# Delaying IK 1s to allow VR Skeleton to properly stabilize in Vulkan
	get_tree().create_timer(1.0).timeout.connect(_setup_ik)
	
	if _animation_tree:
		_animation_tree.active = false
	
	call_deferred("_play_initial_greeting")

func _play_initial_greeting():
	var root = get_tree().root.find_child("SkeletonKey", true, false)
	if root and root.has_method("play_category"):
		root.call("play_category", "Greetings")

func _on_tactile_impulse(region: String, _intensity: float, _pos: Vector3):
	if region == "HEAD":
		_gaze_mode = GazeMode.PLAYER
		_gaze_timer = 5.0
		if randf() < 0.3: play_animation(&"happy")
	elif region == "CHEST" or region == "BODY_GENERAL":
		if shyness_intensity > 0.5:
			_gaze_mode = GazeMode.SHY
			_gaze_timer = 2.0

func _process_lip_sync(_delta: float) -> void:
	if not _face_mesh: return
	var voice_player = get_node_or_null("VoicePlayer") as AudioStreamPlayer3D
	if not voice_player or not voice_player.playing:
		_set_blend_shape("Fcl_MTH_A", 0.0) 
		return
	_set_blend_shape("Fcl_MTH_A", randf_range(0.0, 0.4))

func _process_natural_behavior(delta: float) -> void:
	_process_blink(delta)
	if _skeleton: _process_eye_contact(delta)

func _process_blink(delta: float) -> void:
	if not _face_mesh: _find_face_mesh(avatar_node)
	if not _face_mesh: return
	
	if not _is_blinking:
		_blink_timer += delta
		if _blink_timer >= _next_blink_time:
			_is_blinking = true
			_blink_timer = 0.0
			_next_blink_time = randf_range(2.0, 6.0)
	else:
		_blink_timer += delta
		var weight = 0.0
		if _blink_timer < _blink_duration * 0.5:
			weight = _blink_timer / (_blink_duration * 0.5)
		elif _blink_timer < _blink_duration:
			weight = 1.0 - ((_blink_timer - _blink_duration * 0.5) / (_blink_duration * 0.5))
		else:
			_is_blinking = false
			_blink_timer = 0.0
			weight = 0.0
		_set_blend_shape("Fcl_EYE_Close", weight)

func _process_dynamic_pose(delta: float) -> void:
	_procedural_sway += delta * 0.5
	var sway_v = sin(_procedural_sway) * 0.02
	var sway_h = cos(_procedural_sway * 0.7) * 0.01
	
	if _skeleton:
		var hips = _skeleton.find_bone("Hips")
		if hips != -1:
			var cur_pos = _skeleton.get_bone_pose_position(hips)
			_skeleton.set_bone_pose_position(hips, cur_pos + Vector3(sway_h, sway_v, 0) * delta)

	_idle_variation_timer -= delta
	if _idle_variation_timer <= 0:
		_idle_variation_timer = randf_range(10.0, 30.0)
		_weight_shift = randf_range(-1.0, 1.0)

func _process_eye_contact(delta: float) -> void:
	if not _skeleton or _head_bone_idx == -1 or not player_camera: return
	
	_gaze_timer -= delta
	if _gaze_timer <= 0:
		_update_gaze_strategy()
	
	var look_target = player_camera.global_position if _gaze_mode == GazeMode.PLAYER else _gaze_target_pos
	
	_saccade_timer -= delta
	if _saccade_timer <= 0:
		_saccade_timer = randf_range(0.5, 2.5)
		_saccade_offset = Vector3(randf_range(-0.04, 0.04), randf_range(-0.04, 0.04), 0)
	
	look_target += _saccade_offset
	var local_look = _skeleton.to_local(look_target)
	var rest_origin = _skeleton.get_bone_rest(_head_bone_idx).origin
	var diff = local_look - rest_origin
	if diff.length_squared() < 0.01: return
	
	var bone_pos = _skeleton.to_global(_skeleton.get_bone_global_pose(_head_bone_idx).origin)
	var forward_dir = (look_target - bone_pos).normalized()
	var target_quat: Quaternion
	
	if forward_dir.length_squared() > 0.01:
		target_quat = Basis.looking_at(-forward_dir, Vector3.UP).get_rotation_quaternion()
	else:
		target_quat = _skeleton.get_bone_pose_rotation(_head_bone_idx)

	var current_quat = _skeleton.get_bone_pose_rotation(_head_bone_idx)
	var speed = 3.5
	if _gaze_mode == GazeMode.SHY: speed = 1.5
	elif _gaze_mode == GazeMode.INTERESTED or _gaze_mode == GazeMode.TRACK_TARGET: speed = 5.0
	
	_skeleton.set_bone_pose_rotation(_head_bone_idx, current_quat.slerp(target_quat, delta * speed))

func _update_gaze_strategy():
	var roll = randf()
	if roll < shyness_intensity:
		_gaze_mode = GazeMode.SHY
		_gaze_timer = randf_range(1.5, 4.0)
		_gaze_target_pos = avatar_node.global_position + (avatar_node.global_transform.basis * Vector3(0.4, -0.8, 1.5))
	elif roll < 0.8:
		_gaze_mode = GazeMode.PLAYER
		_gaze_timer = randf_range(4.0, 12.0)
	else:
		_gaze_mode = GazeMode.LOOK_AWAY
		_gaze_timer = randf_range(2.0, 6.0)
		_gaze_target_pos = avatar_node.global_position + Vector3(randf_range(-4,4), randf_range(0.5, 2.5), -4)

func puppet_reach(side: String, target_pos: Vector3, duration: float = 2.0):
	_ik_active = true
	var marker = _target_l if side.to_upper() == "LEFT" else _target_r
	if not marker: return
	
	var tween = create_tween()
	tween.tween_property(marker, "global_position", target_pos, duration)
	
	_gaze_mode = GazeMode.TRACK_TARGET
	_gaze_target_pos = target_pos
	_gaze_timer = duration + 1.0

func reset_puppet():
	_ik_active = false
	_gaze_mode = GazeMode.PLAYER

func _update_ik_blending(delta: float):
	if not _ik_left_hand or not _ik_right_hand: return
	var target_val = 1.0 if _ik_active else 0.0
	_ik_left_hand.interpolation = lerp(_ik_left_hand.interpolation, target_val, delta * 2.0)
	_ik_right_hand.interpolation = lerp(_ik_right_hand.interpolation, target_val, delta * 2.0)
	
	if _ik_left_hand.interpolation > 0.01:
		if not _ik_left_hand.is_running(): _ik_left_hand.start()
		if not _ik_right_hand.is_running(): _ik_right_hand.start()
	elif _ik_left_hand.is_running():
		_ik_left_hand.stop()
		_ik_right_hand.stop()
	
func _setup_ik():
	if not _skeleton: return
	for child in _skeleton.get_children():
		if child is SkeletonIK3D: child.queue_free()
	
	_target_l = Marker3D.new(); _target_l.name = "Target_L"; add_child(_target_l)
	_target_r = Marker3D.new(); _target_r.name = "Target_R"; add_child(_target_r)
	
	# Detect Sidebones
	var l_hand = _find_bone_id(["LeftHand", "Hand_L", "mixamorig_LeftHand"])
	var r_hand = _find_bone_id(["RightHand", "Hand_R", "mixamorig_RightHand"])
	var l_arm = _find_bone_id(["LeftUpperArm", "UpperArm_L", "mixamorig_LeftUpperArm"])
	var r_arm = _find_bone_id(["RightUpperArm", "UpperArm_R", "mixamorig_RightUpperArm"])
	
	# Setup Left Hand IK
	if l_hand != -1 and l_arm != -1:
		_ik_left_hand = SkeletonIK3D.new(); _ik_left_hand.name = "IK_L"
		_ik_left_hand.root_bone = _skeleton.get_bone_name(l_arm)
		_ik_left_hand.tip_bone = _skeleton.get_bone_name(l_hand)
		
		# Safety: Ensure root is a parent of tip
		if _is_bone_ancestor_of(l_arm, l_hand):
			_skeleton.add_child(_ik_left_hand)
			_ik_left_hand.target_node = _ik_left_hand.get_path_to(_target_l)
			_ik_left_hand.start()
		else:
			print("LUMAX IK: Left arm bone structure invalid for chain.")

	# Setup Right Hand IK
	if r_hand != -1 and r_arm != -1:
		_ik_right_hand = SkeletonIK3D.new(); _ik_right_hand.name = "IK_R"
		_ik_right_hand.root_bone = _skeleton.get_bone_name(r_arm)
		_ik_right_hand.tip_bone = _skeleton.get_bone_name(r_hand)
		
		# Safety: Ensure root is a parent of tip
		if _is_bone_ancestor_of(r_arm, r_hand):
			_skeleton.add_child(_ik_right_hand)
			_ik_right_hand.target_node = _ik_right_hand.get_path_to(_target_r)
			_ik_right_hand.start()
		else:
			print("LUMAX IK: Right arm bone structure invalid for chain.")

func _is_bone_ancestor_of(parent_idx: int, child_idx: int) -> bool:
	var curr = child_idx
	var safety = 0
	while curr != -1 and safety < 100:
		if curr == parent_idx: return true
		curr = _skeleton.get_bone_parent(curr)
		safety += 1
	return false

func _find_bone_id(names: Array) -> int:
	for n in names:
		var idx = _skeleton.find_bone(n)
		if idx != -1: return idx
	return -1

func play_animation(anim_name: StringName) -> void:
	if not _animation_tree: return
	var playback = _animation_tree.get("parameters/playback")
	if playback: 
		var state_name = String(anim_name).capitalize().replace(" ", "")
		if playback.get_current_node() != state_name:
			playback.travel(state_name)

func _setup_references() -> void:
	_animation_tree = get_node_or_null("AnimationTree")
	_body_animation_player = avatar_node.find_child("AnimationPlayer", true, false)
	if not _body_animation_player: _body_animation_player = avatar_node.find_child("*AnimationPlayer*", true, false)
	
	if not _skeleton:
		_skeleton = avatar_node.find_child("GeneralSkeleton", true, false)
		if not _skeleton: _skeleton = avatar_node.find_child("*Skeleton*", true, false)
			
	if _skeleton: 
		_head_bone_idx = _skeleton.find_bone("Head")
		if _head_bone_idx == -1: _head_bone_idx = _skeleton.find_bone("head")
	
	if _body_animation_player: _setup_animation_library()

func refresh_animation_system() -> void:
	_setup_animation_library()
	force_resanitize_animations()
	_setup_animation_graph()

func _setup_animation_library() -> void:
	var lib = null
	if _body_animation_player.has_animation_library(_LIB_NAME): lib = _body_animation_player.get_animation_library(_LIB_NAME)
	if not lib:
		lib = AnimationLibrary.new(); _body_animation_player.add_animation_library(_LIB_NAME, lib)
		
	var root = get_tree().root.find_child("SkeletonKey", true, false)
	if not root: return
		
	if lib.get_animation_list().is_empty():
		for key in clip_paths.keys():
			var path = root.call("find_animation_path", clip_paths[key])
			if path != "" and FileAccess.file_exists(path):
				var res = load(path)
				if res is Animation: lib.add_animation(key, res)

func force_resanitize_animations() -> void:
	if not _body_animation_player or not avatar_node: return
	var skel = avatar_node.find_child("Skeleton3D", true, false)
	if not skel: skel = avatar_node.find_child("*Skeleton*", true, false)
	if not skel: return
	
	_face_mesh = null
	_find_face_mesh(avatar_node)
	if not _face_mesh: return
	
	var skel_path = String(_body_animation_player.get_path_to(skel))
	var face_path = String(_body_animation_player.get_path_to(_face_mesh))
	
	for lib_name in _body_animation_player.get_animation_library_list():
		var lib = _body_animation_player.get_animation_library(lib_name)
		for anim_name in lib.get_animation_list():
			var anim = lib.get_animation(anim_name)
			var meta_key = "sanitized_" + str(skel.get_instance_id()) + "_" + str(_face_mesh.get_instance_id())
			if not anim or anim.get_meta(meta_key, false): continue
			
			for i in range(anim.get_track_count()):
				var old_path = String(anim.track_get_path(i))
				if "blend_shapes/" in old_path or "Fcl_" in old_path:
					var parts = old_path.split(":")
					var property = ":" + parts[1] if parts.size() > 1 else ""
					if not old_path.begins_with(face_path):
						anim.track_set_path(i, NodePath(face_path + property))
				else:
					for target in ["Skeleton3D", "GeneralSkeleton", "Armature"]:
						if target in old_path and not old_path.begins_with(skel_path):
							var parts = old_path.split(":")
							var property = ":" + parts[1] if parts.size() > 1 else ""
							anim.track_set_path(i, NodePath(skel_path + property))
							break
			anim.set_meta(meta_key, true)

func _setup_animation_graph() -> void:
	var root = AnimationNodeStateMachine.new()
	var lib = _body_animation_player.get_animation_library(_LIB_NAME)
	if lib.has_animation(&"idle"):
		var locomotion = AnimationNodeAnimation.new(); locomotion.animation = _LIB_NAME + "/idle"
		root.add_node("Locomotion", locomotion)
	_animation_tree.tree_root = root
	_animation_tree.anim_player = _animation_tree.get_path_to(_body_animation_player)
	_animation_tree.active = false 
	var playback = _animation_tree.get("parameters/playback")
	if playback and root.has_node("Locomotion"): playback.start("Locomotion")

func _set_blend_shape(shape_name: String, value: float) -> void:
	if not _face_mesh or not _face_mesh.mesh: return
	var idx = _face_mesh.find_blend_shape_by_name(shape_name)
	if idx == -1: idx = _face_mesh.find_blend_shape_by_name(shape_name.to_lower())
	if idx != -1: _face_mesh.set_blend_shape_value(idx, value)

func _find_face_mesh(node: Node) -> void:
	if not node: return
	if node is MeshInstance3D and node.mesh:
		if node.mesh.get_blend_shape_count() > 0:
			if node.name.to_lower().contains("face") or node.find_blend_shape_by_name("Fcl_EYE_Close") != -1:
				_face_mesh = node; return
	for c in node.get_children(): _find_face_mesh(c); if _face_mesh: return
