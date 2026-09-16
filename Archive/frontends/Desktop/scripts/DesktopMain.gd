extends Node2D

## Main controller for the Jen Desktop Companion.
## Unified UI: when ready, fetch `GET http://<host>:8080/api/ui_config` and apply `global` + `desktop`
## from `Frontend/Body/Webui/lumax_ui_config.json` (same contract as VR `godot_vr`).

@onready var avatar = $JenAvatar
@onready var trust_panel = $UI/MainLayout/ContentArea/ChatBox/Panel/VBox/TrustPanel
@onready var trust_desc = $UI/MainLayout/ContentArea/ChatBox/Panel/VBox/TrustPanel/HBox/Desc
@onready var logs = $UI/MainLayout/ContentArea/ChatBox/Panel/VBox/Logs
@onready var agency_tab = $UI/MainLayout/SideBar/AgencyTab
@onready var avatar_tab = $UI/MainLayout/SideBar/AvatarTab
@onready var yolo_toggle = $UI/MainLayout/SideBar/YOLOToggle

var _dragging = false
var _drag_offset = Vector2()
var trust_handler: TrustHandler

func _ready() -> void:
	trust_handler = TrustHandler.new()
	add_child(trust_handler)
	
	# Connect UI
	$UI/MainLayout/ContentArea/ChatBox/Panel/VBox/HBoxInput/SendBtn.pressed.connect(_on_send_pressed)
	$UI/MainLayout/ContentArea/ChatBox/Panel/VBox/TrustPanel/HBox/ApproveBtn.pressed.connect(_on_approve_pressed)
	$UI/MainLayout/ContentArea/ChatBox/Panel/VBox/TrustPanel/HBox/DenyBtn.pressed.connect(_on_deny_pressed)
	yolo_toggle.toggled.connect(_on_yolo_toggled)
	
	trust_handler.proposal_received.connect(_on_proposal_received)
	
	_add_log("[color=cyan]Jen:[/color] Hello! I'm your desktop companion.")

func _input(event: InputEvent) -> void:
	# Handle window dragging on background click
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				_dragging = true
				_drag_offset = get_viewport().get_mouse_position()
			else:
				_dragging = false
				
	if event is InputEventMouseMotion and _dragging:
		var current_pos = DisplayServer.window_get_position()
		DisplayServer.window_set_position(current_pos + Vector2i(get_global_mouse_position() - _drag_offset))

func _on_send_pressed() -> void:
	var input = $UI/MainLayout/ContentArea/ChatBox/Panel/VBox/HBoxInput/Input
	if input.text == "": return
	
	_add_log("[color=gray]You:[/color] " + input.text)
	
	# Simple mock response
	if "clean" in input.text.to_lower():
		trust_handler.propose_action("cleanup", "Delete 10GB of temporary build files in 'code/godot'?")
	else:
		_add_log("[color=cyan]Jen:[/color] I'm listening. I can help with system tasks or just chat.")
		
	input.text = ""

func _on_proposal_received(proposal: Dictionary) -> void:
	trust_desc.text = proposal.description
	trust_panel.show()
	_add_log("[color=yellow]System:[/color] Action proposed: " + proposal.id)

func _on_approve_pressed() -> void:
	trust_panel.hide()
	trust_handler.resolve_proposal("cleanup", true)
	_add_log("[color=green]Jen:[/color] Cleanup confirmed. Executing...")

func _on_deny_pressed() -> void:
	trust_panel.hide()
	trust_handler.resolve_proposal("cleanup", false)
	_add_log("[color=red]Jen:[/color] Cleanup cancelled.")

func _on_yolo_toggled(button_pressed: bool) -> void:
	trust_handler.current_mode = TrustHandler.Mode.YOLO if button_pressed else TrustHandler.Mode.ADMIT
	_add_log("[color=orange]System:[/color] Mode set to " + ("YOLO" if button_pressed else "ADMIT"))

func _add_log(msg: String) -> void:
	logs.append_text("\n" + msg)
