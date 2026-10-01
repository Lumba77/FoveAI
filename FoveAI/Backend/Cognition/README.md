# Lumax Mind: Cognition Layer

This directory contains the central reasoning logic for the Lumax sovereign OS.

## The Lumax Engine Concept

We use the term "Engine" in two distinct but related contexts:

### 1. LumaxEngine (Reasoning Core)
The `LumaxEngine` class in `lumax_engine.py` is the **Cognitive Wrapper**. It orchestrates the loading and inference of Large Language Models (LLMs) and Vision-Language Models (VLMs).
- **Supported Backends**: GGUF (via llama-cpp-python), Transformers (Hugging Face), and native vision handlers.
- **Role**: It acts as the "Brain" that decides what the avatar says, feels, and does.

### 2. Hardware Engines (TensorRT / ONNX)
In high-performance AI deployment, `.engine` files refer to **TensorRT-optimized** hardware blobs.
- **ONNX**: Used in the `backend/Memory` stack for high-speed vector embeddings and sensory digestion.
- **TensorRT**: Frequently utilized in the **Body** (Vessels) for zero-latency Speech-to-Text (STT) and Text-to-Speech (TTS), such as F5-TTS or XTTS.

## Biological Sovereignty
This folder is the **Mind** of the system. It is designed to be independent of specific frontend "Vessels" (Body). It maintains its own state and memory, isolated from the rendering and interaction layers.
