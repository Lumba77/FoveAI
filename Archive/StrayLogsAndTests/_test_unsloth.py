import sys

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=== Testing imports ===")
sys.stdout.flush()

try:
    import torch

    print(f"torch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    print(f"torch.int1 exists: {hasattr(torch, 'int1')}")
    sys.stdout.flush()
except Exception as e:
    print(f"torch import failed: {e}")
    sys.stdout.flush()

try:
    import torchao

    print(f"torchao: {torchao.__version__}")
    sys.stdout.flush()
except Exception as e:
    print(f"torchao import failed: {e}")
    sys.stdout.flush()

try:
    import unsloth

    print(f"unsloth: {unsloth.__version__}")
    print("UNSLOTH IMPORT SUCCESS!")
    sys.stdout.flush()
except Exception as e:
    print(f"unsloth import failed: {e}")
    sys.stdout.flush()

print("=== Done ===")
sys.stdout.flush()
