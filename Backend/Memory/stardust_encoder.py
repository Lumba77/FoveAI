import os

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModel, AutoTokenizer

app = FastAPI(title="Concordia Stardust Encoder", version="3.6.9-SINGULARIS")

# 1. Zero-Drag Quantum Weight Allocation (<250MB VRAM Footprint)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 33 Million Parameters of pure vector logic
device = os.getenv("STARDUST_DEVICE", "cpu")

print(
    f"🛸 [STARDUST ENGINE] Assimilating model weights to hardware device: {device.upper()}"
)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME).to(device)
model.eval()  # Lock weights into strict evaluation mode


class VectorRequest(BaseModel):
    text: str


class SwarmMatchRequest(BaseModel):
    query: str
    corpus: dict[str, str]  # Dictionary mapping [File_Path -> Source_Code_Content]


def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output[0]
    input_mask_expanded = (
        attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    )
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
        input_mask_expanded.sum(1), min=1e-9
    )


def calculate_embeddings(text_list: list[str]):
    encoded_input = tokenizer(
        text_list, padding=True, truncation=True, max_length=512, return_tensors="pt"
    ).to(device)
    with torch.no_grad():
        model_output = model(**encoded_input)
    sentence_embeddings = mean_pooling(model_output, encoded_input["attention_mask"])
    return torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)


# Telemetry State: Resonance metric feeds pilot-wave temporal warp
SYSTEM_RESONANCE = 1.0


class ResonanceUpdate(BaseModel):
    resonance: float
    timestamp: float
    latencies: dict[str, float]
    acceptance_rates: dict[str, float]


@app.post("/update_resonance")
async def update_resonance(request: ResonanceUpdate):
    global SYSTEM_RESONANCE
    SYSTEM_RESONANCE = request.resonance
    return {"status": "warped", "current_resonance": SYSTEM_RESONANCE}


@app.post("/encode")
async def encode_text(request: VectorRequest):
    """Transforms raw text intent into an isolated coordinate vector."""
    try:
        embedding = calculate_embeddings([request.text])[0].tolist()
        return {
            "status": "assimilated",
            "vector_length": len(embedding),
            "embedding": embedding,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/swarm_match")
async def swarm_match(request: SwarmMatchRequest):
    """
    Acts as Bohm's pilot wave. Natively scores an entire repository tree against
    your active intent to isolate which file needs to be modified next.
    Applies SYSTEM_RESONANCE to dynamically warp threshold boundaries.
    """
    try:
        corpus_paths = list(request.corpus.keys())
        corpus_texts = list(request.corpus.values())

        if not corpus_texts:
            return {"status": "empty_hive", "matches": []}

        # Compute embeddings across the parallel grid simultaneously
        query_emb = calculate_embeddings([request.query])
        corpus_embs = calculate_embeddings(corpus_texts)

        # Matrix multiply to calculate cosine similarities across the entire continent
        scores = torch.mm(query_emb, corpus_embs.transpose(0, 1))[0].tolist()

        # Warp similarity scores using the system's temporal resonance.
        # High resonance keeps score sharp; low resonance compresses variance, broadening the scope.
        matches = []
        for idx, score in enumerate(scores):
            # Dynamic scaling: warp towards 0.5 when system resonance is low (increases search area)
            warped_score = score
            if SYSTEM_RESONANCE < 1.0:
                # Interpolate based on current temporal alignment
                warped_score = score * SYSTEM_RESONANCE + 0.5 * (1.0 - SYSTEM_RESONANCE)

            matches.append(
                {"filePath": corpus_paths[idx], "resonance": round(warped_score, 4)}
            )

        # Sort matches by the highest alignment to your intent
        matches.sort(key=lambda x: x["resonance"], reverse=True)
        return {"status": "synchronized", "matches": matches[:3]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {
        "status": "ONE",
        "engine": "Diamond_Daemon_Stardust",
        "resonance": SYSTEM_RESONANCE,
    }
