import os
import traceback

os.environ["HF_HOME"] = "F:/Lumax/models"

try:
    print("Importing KPipeline...")
    from kokoro import KPipeline

    print("Constructing KPipeline...")
    pipeline = KPipeline(lang_code="a")
    print("Success!")
except Exception:
    print("Error occurred:")
    traceback.print_exc()
