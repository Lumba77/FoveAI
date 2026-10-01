extends AnimatedSprite2D

## Handles 2.5D sprite rotation for Desktop Companion.
## In Desktop mode, we use the mouse position to determine the viewing angle.

@export var interactable: bool = true
@export var follow_mouse: bool = true

func _ready() -> void:
	# Ensure transparency is working
	get_tree().get_root().transparent_bg = true
	# Play idle animation
	play("idle")
	# Start at front view
	frame = 0

func _process(_delta: float) -> void:
	if follow_mouse:
		_look_at_mouse()

func _look_at_mouse() -> void:
	var mouse_pos = get_global_mouse_position()
	var screen_center = get_viewport_rect().size / 2
	
	# Vector from sprite to mouse
	var dir = (mouse_pos - screen_center).normalized()
	
	# Calculate angle (-PI to PI)
	var angle = atan2(dir.y, dir.x)
	var _deg = rad_to_deg(angle)
	
	# Remap: In Godot 2D, 0 is Right, 90 is Down.
	# Our sprites are: 0: Front, 2: Left, 4: Back, 6: Right
	
	# Let's adjust to match our 0-index = Front (looking at user)
	# If mouse is at the bottom of the screen (looking down), we see the Top of her head? 
	# Actually, usually for a desktop sprite:
	# Mouse way left -> She looks left (sees her right profile?)
	# Let's map X position to the 8 angles.
	
	var view_angle = 0 # Default Front
	
	var viewport_width = get_viewport_rect().size.x
	var mouse_x_norm = clamp(mouse_pos.x / viewport_width, 0.0, 1.0)
	
	# Simple mapping for a desktop buddy:
	# 0.0 (Far Left) -> Right side view (6)
	# 0.5 (Center)   -> Front view (0)
	# 1.0 (Far Right) -> Left side view (2)
	
	if mouse_x_norm < 0.2:
		view_angle = 6 # Right
	elif mouse_x_norm < 0.4:
		view_angle = 7 # Front-Right
	elif mouse_x_norm < 0.6:
		view_angle = 0 # Front
	elif mouse_x_norm < 0.8:
		view_angle = 1 # Front-Left
	else:
		view_angle = 2 # Left
		
	frame = view_angle
