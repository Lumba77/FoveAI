# LUMAX VR: Godot Development Guide

**Source:** godot_docs/ directory  
**Generated:** May 5, 2026  
**Godot Version:** 4.6+

---

## Overview

This guide compiles Godot best practices from the official Godot Engine documentation, organized for LUMAX VR development. The Godot engine offers great flexibility in structuring projects - this guide helps navigate the key decisions.

---

## Table of Contents

1. [Object-Oriented Principles in Godot](#object-oriented-principles-in-godot)
2. [Scene Organization](#scene-organization)
3. [Scenes vs Scripts](#scenes-vs-scripts)
4. [Autoloads vs Regular Nodes](#autoloads-vs-regular-nodes)
5. [Node Alternatives](#node-alternatives)
6. [Godot Interfaces](#godot-interfaces)
7. [Godot Notifications](#godot-notifications)
8. [Data Preferences](#data-preferences)
9. [Logic Preferences](#logic-preferences)
10. [Project Organization](#project-organization)
11. [Version Control](#version-control)

---

## Object-Oriented Principles in Godot

### Understanding Godot's Class System

Godot offers two main ways to create reusable objects:
- **Scripts** - Define engine class extensions with **imperative code**
- **Scenes** - Define compositions with **declarative code**

Neither technically defines classes under the hood, but many best practices involve applying OOP principles to both.

### Key Concepts

| Concept | Godot Equivalent |
|---------|-----------------|
| Class | Script (.gd file) or Scene (.tscn) |
| Inheritance | `extends` keyword or Scene inheritance |
| Composition | Node trees in scenes |
| Encapsulation | Node structure and signals |

**Read more:** `godot_docs/Applying_objectoriented_principles_in_Godot.txt`

---

## Scene Organization

### Which Nodes Should You Use?

When building scenes in Godot, consider:

1. **Start with a clear root node** - Choose the most specific node type that matches your scene's purpose
2. **Keep scenes focused** - Each scene should have a single responsibility
3. **Use instancing** - Reuse scene instances rather than duplicating content

### Building Relationships

```gdscript
# Good: Clear parent-child relationship
class Player:
    extends CharacterBody2D
    
    @onready var sprite = $Sprite2D
    @onready var collision = $CollisionShape2D

# Avoid: Deeply nested structures when flat works
```

**Read more:** `godot_docs/Scene_organization.txt`

---

## Scenes vs Scripts

### When to Use Each

| Use Scenes When | Use Scripts When |
|----------------|-----------------|
| Defining node compositions | Adding behavior to nodes |
| Creating visual hierarchies | Implementing algorithms |
| Setting up initial state | Handling runtime logic |
| Using with inherited scenes | Extending engine classes |

### Anonymous Types

Scripts can define anonymous types that don't need scene files:

```gdscript
# Pure script approach - lightweight, code-only
class_name GameState
extends RefCounted

var score: int = 0
var level: int = 1
```

**Read more:** `godot_docs/When_to_use_scenes_versus_scripts.txt`

---

## Autoloads vs Regular Nodes

### What Are Autoloads?

Autoloads are nodes automatically loaded at the root of your project, providing global access (Singleton pattern).

### When to Use Autoloads

| Good Uses | Avoid When |
|-----------|-----------|
| Global game state | Scene-specific data |
| Audio managers (persistent) | Temporary data |
| Input managers | Data that should be scoped |
| Save/load systems | Everything else |

### The Cutting Audio Issue

A common problem: audio cuts when changing scenes because the audio player is part of the scene tree.

**Solution 1: Autoload**
```gdscript
# In Project Settings → Autoload
# AudioManager.gd added as autoload
AudioManager.play_music("theme.ogg")  # Available everywhere
```

**Solution 2: Scene Persistence**
```gdscript
# Keep audio in a persistent parent scene
# Use change_scene_to_packed instead
```

**Read more:** `godot_docs/Autoloads_versus_regular_nodes.txt`

---

## Node Alternatives

### When Nodes Are Too Heavy

Nodes are cheap but not free. For tens of thousands of objects, consider:

### Object (Most Lightweight)
```gdscript
# Base class for non-Node objects
class DataHolder:
    extends Object
    
    var data: Dictionary = {}
```

### RefCounted (Automatic Memory Management)
```gdscript
# Automatic reference counting
class ResourceData:
    extends RefCounted
    
    var resources: Array = []
```

### Resources (Data Containers)
```gdscript
# Use @export_resource for inspector integration
class EnemyData:
    extends Resource
    
    @export var name: String
    @export var health: int
    @export var sprite: Texture2D
```

**Read more:** `godot_docs/When_and_how_to_avoid_using_nodes_for_everything.txt`

---

## Godot Interfaces

### Acquiring Object References

```gdscript
# Method 1: Direct reference
var obj = node.obj

# Method 2: Find by path
var obj = get_node("Path/To/Node")

# Method 3: Find by type
var obj = get_tree().get_first_node_in_group("enemies")

# Method 4: Signals (loose coupling)
signal health_changed(new_value)
```

### Accessing Features

```gdscript
# Direct property access
node.position = Vector2(100, 100)

# Method calls
node.take_damage(10)

# Using has_method for safety
if node.has_method("take_damage"):
    node.take_damage(10)
```

**Read more:** `godot_docs/Godot_interfaces.txt`

---

## Godot Notifications

### Understanding Notifications

Every Object implements `_notification()`. The engine uses this for lifecycle events.

### Common Notifications

| Notification | Convenience Method | When Called |
|-------------|-------------------|-------------|
| `NOTIFICATION_READY` | `_ready()` | Node ready in scene tree |
| `NOTIFICATION_ENTER_TREE` | `_enter_tree()` | Node enters scene tree |
| `NOTIFICATION_EXIT_TREE` | `_exit_tree()` | Node exits scene tree |
| `NOTIFICATION_PROCESS` | `_process()` | Every frame |
| `NOTIFICATION_PHYSICS_PROCESS` | `_physics_process()` | Physics frame |
| `NOTIFICATION_DRAW` | `_draw()` | When redraw needed |

### Best Practices

```gdscript
# Prefer convenience methods
func _ready():
    pass  # Instead of _notification(NOTIFICATION_READY)

# Use _notification for advanced cases
func _notification(what):
    if what == NOTIFICATION_PREDELETE:
        cleanup_resources()
```

**Read more:** `godot_docs/Godot_notifications.txt`

---

## Data Preferences

### Choosing Data Structures

| Structure | Access Time | Use Case |
|-----------|------------|----------|
| Array | O(n) | Ordered lists, iteration |
| Dictionary | O(1) | Key-value lookups |
| Set | O(1) | Unique items, membership |
| QuadTree | O(log n) | Spatial queries |

### Data-Driven Design

```gdscript
# Load data from resources
@export_file("*.json") var data_file: String
@export_resource var enemy_data: EnemyData
```

**Read more:** `godot_docs/Data_preferences.txt`

---

## Logic Preferences

### Adding Nodes: Order Matters

```gdscript
# BEST: Configure before adding
var enemy = Enemy.new()
enemy.position = spawn_position
enemy.health = 100
add_child(enemy)

# AVOID: Configure after adding
var enemy = Enemy.new()
add_child(enemy)
enemy.position = spawn_position  # May trigger unnecessary updates
```

### Initialization Order

1. Create node
2. Set properties
3. Connect signals
4. Add to scene tree

**Read more:** `godot_docs/Logic_preferences.txt`

---

## Project Organization

### Recommended Structure

```
project/
├── assets/
│   ├── audio/
│   ├── fonts/
│   ├── models/
│   └── textures/
├── scenes/
│   ├── entities/
│   ├── levels/
│   └── ui/
├── scripts/
│   ├── autoloads/
│   ├── components/
│   └── utilities/
├── resources/
│   └── data/
└── addons/
```

### Godot-Specific Tips

- Godot is scene-based, not asset-database-based
- Resources are contained within scenes
- Use `.tres` files for reusable data
- Keep project root clean

**Read more:** `godot_docs/Project_organization.txt`

---

## Version Control

### Godot + Git Best Practices

1. **Enable text scenes** - `.tscn` files are mergeable
2. **Use .gitignore** - Exclude `.godot/`, `*.import~`, etc.
3. **Binary files** - Use Git LFS for large binaries
4. **Editor plugin** - Install official Git plugin for in-editor VCS

### Recommended .gitignore

```
# Godot
.godot/
*.import~
*.res~
*.tres~

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
```

**Read more:** `godot_docs/Version_control_systems.txt`

---

## LUMAX-Specific Godot Patterns

### VR Scene Structure (LUMAX)

```
Nexus (Root)
├── SkeletonKey (Main controller)
│   ├── ManifestationAnchor (Player)
│   ├── WorldAnchor (Environment)
│   └── UIAnchor (Interface)
├── Soul/Synapse (LLM bridge)
├── Senses/ (Input handlers)
│   ├── AuralAwareness (Voice)
│   └── TactileInput (Touch)
└── backend/ (Cognitive components)
    ├── TactileInput_v2
    └── DirectorManager
```

### Key Scripts

| Script | Purpose |
|--------|---------|
| `SkeletonKey.gd` | Main VR scene controller |
| `Synapse.gd` | LLM communication bridge |
| `DirectorManager.gd` | Scene state management |
| `AuralAwareness.gd` | Voice input handling |

---

## Quick Reference

### Common Patterns

```gdscript
# Singleton access (autoload)
GameManager.add_score(100)

# Signal connection
$Button.pressed.connect(_on_button_pressed)

# Scene instancing
var enemy = preload("res://scenes/enemy.tscn").instantiate()
add_child(enemy)

# Resource loading
var texture = load("res://assets/icon.png")

# Group operations
get_tree().call_group("enemies", "take_damage", 10)
```

---

## Source Files

Original documentation in `godot_docs/`:

| File | Topic |
|------|-------|
| `kb_summary.md` | Complete summary |
| `Introduction.txt` | Introduction |
| `Applying_objectoriented_principles_in_Godot.txt` | OOP in Godot |
| `Scene_organization.txt` | Scene organization |
| `When_to_use_scenes_versus_scripts.txt` | Scenes vs scripts |
| `Autoloads_versus_regular_nodes.txt` | Autoloads |
| `When_and_how_to_avoid_using_nodes_for_everything.txt` | Node alternatives |
| `Godot_interfaces.txt` | Interfaces |
| `Godot_notifications.txt` | Notifications |
| `Data_preferences.txt` | Data structures |
| `Logic_preferences.txt` | Logic patterns |
| `Project_organization.txt` | Project structure |
| `Version_control_systems.txt` | VCS integration |

---

*This guide compiled from official Godot Engine documentation (CC BY 3.0)*
*For LUMAX VR development - May 2026*