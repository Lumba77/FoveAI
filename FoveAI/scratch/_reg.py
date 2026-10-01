
path = r"c:\Users\lumba\Program\FoveAI\frontend\XR_Vessel\src\senses\ModelRegistry.ts"
with open(path, "w", encoding="utf-8") as f:
    f.write("/** MODEL REGISTRY v2 - HF Hub */\n")
    f.write(
        "export interface ModelEntry { localPath: string; hfRepo: string; hfSubPath?: string; gated?: boolean; type: string; sizeMb?: number; }\n"
    )
    f.write("export const MODEL_REGISTRY: Record^<string, ModelEntry^> = {\n")
