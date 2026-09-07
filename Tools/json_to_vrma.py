import json
import os
import struct
import numpy as np
from pygltflib import GLTF2, Scene, Node, Animation, AnimationChannel, AnimationSampler, AnimationChannelTarget, Accessor, Buffer, BufferView, Asset

# VRM 1.0 Humanoid Bone Names (standardized)
VRM_HUMANOID_BONES = [
    "hips", "spine", "chest", "upperChest", "neck", "head", "leftShoulder", "rightShoulder",
    "leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm", "leftHand", "rightHand",
    "leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg", "leftFoot", "rightFoot",
    "leftToes", "rightToes"
]

def convert_json_to_vrma(json_path, output_path):
    with open(json_path, 'r') as f:
        data = json.load(f)

    gltf = GLTF2()
    gltf.asset = Asset(version="2.0", generator="FoveAI Animation Converter")
    
    # Extensions
    gltf.extensionsUsed.append("VRMC_vrm_animation")
    gltf.extensions["VRMC_vrm_animation"] = {
        "specVersion": "1.0",
        "humanoid": {
            "humanBones": {}
        }
    }

    gltf.scenes.append(Scene(nodes=[]))
    gltf.scene = 0

    animation = Animation(name=data["name"])
    gltf.animations.append(animation)

    buffer_data = bytearray()
    
    def add_to_buffer(array, component_type, data_type):
        offset = len(buffer_data)
        if component_type == 5126: # FLOAT
            packed = struct.pack(f"<{len(array)}f", *array)
        else:
            packed = bytearray()
        
        buffer_data.extend(packed)
        while len(buffer_data) % 4 != 0:
            buffer_data.append(0)
            
        view_idx = len(gltf.bufferViews)
        gltf.bufferViews.append(BufferView(
            buffer=0,
            byteOffset=offset,
            byteLength=len(packed),
        ))
        
        accessor_idx = len(gltf.accessors)
        count = len(array) // (1 if data_type == "SCALAR" else 3 if data_type == "VEC3" else 4)
        
        # Calculate min/max for accessors
        arr_np = np.array(array).reshape(count, -1)
        mins = arr_np.min(axis=0).tolist()
        maxs = arr_np.max(axis=0).tolist()

        gltf.accessors.append(Accessor(
            bufferView=view_idx,
            componentType=component_type,
            count=count,
            type=data_type,
            min=mins,
            max=maxs
        ))
        return accessor_idx

    bone_to_node = {}
    
    for track in data["tracks"]:
        bone = track["bone"]
        
        # VRM Animation Spec: Only hips can have translation. Others only rotation.
        if track["type"] == 1 and bone != "hips": # 1 = Position/Translation
            continue

        if bone not in bone_to_node:
            node_idx = len(gltf.nodes)
            gltf.nodes.append(Node(name=bone))
            gltf.scenes[0].nodes.append(node_idx)
            bone_to_node[bone] = node_idx
            
            if bone in VRM_HUMANOID_BONES:
                gltf.extensions["VRMC_vrm_animation"]["humanoid"]["humanBones"][bone] = {"node": node_idx}

        node_idx = bone_to_node[bone]
        
        times = []
        values = []
        for k in track["keys"]:
            times.append(k["time"])
            values.extend(k["value"])
            
        if not times:
            continue

        time_accessor = add_to_buffer(times, 5126, "SCALAR")
        
        if track["type"] == 1: # Position
            target_path = "translation"
            value_accessor = add_to_buffer(values, 5126, "VEC3")
        else: # Rotation
            target_path = "rotation"
            value_accessor = add_to_buffer(values, 5126, "VEC4")
            
        sampler_idx = len(animation.samplers)
        animation.samplers.append(AnimationSampler(
            input=time_accessor,
            output=value_accessor,
            interpolation="LINEAR"
        ))
        
        animation.channels.append(AnimationChannel(
            sampler=sampler_idx,
            target=AnimationChannelTarget(
                node=node_idx,
                path=target_path
            )
        ))

    gltf.buffers.append(Buffer(byteLength=len(buffer_data)))
    gltf.set_binary_blob(buffer_data)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    gltf.save_binary(output_path)

if __name__ == "__main__":
    import sys
    input_root = "frontend/XR_godot/Animations/Dumped"
    output_root = "frontend/XR_Vessel/public/Animations"
    manifest_path = os.path.join(output_root, "animation_manifest.json")
    
    if not os.path.exists(input_root):
        print(f"Input root {input_root} does not exist. Please run the Godot dump script first.")
        sys.exit(1)

    manifest = {}

    for root, dirs, files in os.walk(input_root):
        for file in files:
            if file.ends_with(".json"):
                rel_path = os.path.relpath(root, input_root)
                category = rel_path.replace("\\", "/").split("/")[0]
                if category == ".": category = "General"
                
                input_path = os.path.join(root, file)
                vrma_file = file.replace(".json", ".vrma")
                output_path = os.path.join(output_root, rel_path, vrma_file)
                
                # URL relative to public root
                vrma_url = "/Animations/" + rel_path.replace("\\", "/") + "/" + vrma_file
                vrma_url = vrma_url.replace("//", "/")
                
                print(f"Converting {input_path} -> {output_path}")
                try:
                    convert_json_to_vrma(input_path, output_path)
                    
                    if category not in manifest:
                        manifest[category] = []
                    manifest[category].append({
                        "name": file.replace(".json", ""),
                        "url": vrma_url
                    })
                except Exception as e:
                    print(f"Error converting {input_path}: {e}")

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest generated: {manifest_path}")
