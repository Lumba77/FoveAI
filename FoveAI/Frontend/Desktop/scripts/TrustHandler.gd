class_name TrustHandler
extends Node

## Manages the "Trust Boundary" for the agent.
## Supports "Admit" (Manual Approval) and "YOLO" (Automatic) modes.

signal proposal_received(proposal: Dictionary)
signal proposal_resolved(id: String, approved: bool)

enum Mode {ADMIT, YOLO}

var current_mode: Mode = Mode.ADMIT
var pending_proposals: Dictionary = {}

func propose_action(id: String, description: String, data: Dictionary = {}) -> void:
	var proposal = {
		"id": id,
		"description": description,
		"data": data,
		"timestamp": Time.get_unix_time_from_system()
	}
	
	if current_mode == Mode.YOLO:
		_resolve_automatically(proposal)
	else:
		pending_proposals[id] = proposal
		proposal_received.emit(proposal)

func resolve_proposal(id: String, approved: bool) -> void:
	if pending_proposals.has(id):
		pending_proposals.erase(id)
		proposal_resolved.emit(id, approved)
		print("TrustHandler: Proposal ", id, " resolved. Approved: ", approved)

func _resolve_automatically(proposal: Dictionary) -> void:
	# Small delay to simulate "thinking" or processing
	await get_tree().create_timer(1.0).timeout
	proposal_resolved.emit(proposal.id, true)
	print("TrustHandler: YOLO Mode - Auto-approved: ", proposal.id)

func toggle_mode() -> void:
	if current_mode == Mode.ADMIT:
		current_mode = Mode.YOLO
	else:
		current_mode = Mode.ADMIT
	print("TrustHandler: Mode changed to ", "YOLO" if current_mode == Mode.YOLO else "ADMIT")
