import torch
import torch.nn as nn
import math

class QuantumInspiredNeuron(nn.Module):
    """
    Simulates a phase-aware quantum neuron using complex-valued weight matrices.
    Leverages amplitude and phase tracking to mimic quantum interference states.
    """
    def __init__(self, dimensions: int):
        super(QuantumInspiredNeuron, self).__init__()
        self.dimensions = dimensions
        
        # Trainable parameters representing the unitary transformation gates (Amplitudes & Phases)
        self.amplitude_weights = nn.Parameter(torch.randn(dimensions, dimensions) * 0.02)
        self.phase_weights = nn.Parameter(torch.randn(dimensions, dimensions) * math.pi)

    def forward(self, classical_embeddings: torch.Tensor) -> torch.Tensor:
        """
        Transforms input text embeddings into a simulated entangled quantum state space.
        """
        # 1. Map input features into a complex tensor (Real = Amplitude, Imaginary = Phase)
        amplitudes = torch.clamp(torch.sigmoid(classical_embeddings), min=1e-9, max=1.0)
        phases = torch.sin(classical_embeddings) * math.pi
        
        real_state = amplitudes * torch.cos(phases)
        imag_state = amplitudes * torch.sin(phases)
        
        # 2. Execute simulated unitary gate matrix multiplication
        gate_real = self.amplitude_weights * torch.cos(self.phase_weights)
        gate_imag = self.amplitude_weights * torch.sin(self.phase_weights)
        
        # Complex multiplication: (A + iB)(C + iD) = (AC - BD) + i(AD + BC)
        output_real = torch.matmul(real_state, gate_real) - torch.matmul(imag_state, gate_imag)
        output_imag = torch.matmul(real_state, gate_imag) + torch.matmul(imag_state, gate_real)
        
        # 3. Compute quantum probability amplitudes (Born Rule tracking)
        probabilities = (output_real ** 2) + (output_imag ** 2)
        normalized_resonance = torch.nn.functional.normalize(probabilities, p=2, dim=-1)
        
        return normalized_resonance

if __name__ == "__main__":
    print("🛸 [QUANTUM NEURON] Initializing simulated phase-aware network node...")
    neuron = QuantumInspiredNeuron(dimensions=384) # Aligned to Stardust vector dimensions
    mock_intent = torch.randn(1, 384)
    resonance_state = neuron(mock_intent)
    print(f"✅ Quantum state space collapsed. Unified resonance vector shape: {resonance_state.shape}")