# Requirements for Authoritative Z-Order (Staying above Start Menu)

To achieve a Z-order that overlays system elements like the Windows Start Menu, the application must meet three strict security requirements to trigger the `uiAccess="true"` privilege:

## 1. Digital Signature (Mandatory)
The compiled `.exe` must be digitally signed.
- For local use, we can use a **Self-Signed Certificate**.
- The certificate must be imported into the **"Trusted Root Certification Authorities"** store on your machine.
- Without a signature, Windows ignores the high-priority request.

## 2. Secure Installation Path (Mandatory)
The application must be run from a protected Windows directory:
- `C:\Program Files\` (Recommended)
- `C:\Program Files (x86)\`
- `C:\Windows\System32\`
Running from a user folder or Downloads will disable the privilege.

## 3. Manifest Integration
The application must contain an embedded manifest with:
`<requestedExecutionLevel level="asInvoker" uiAccess="true" />`

---

# Automation Strategy

I have created a build script `build_authoritative_exe.ps1` that automates this process:
1. Creates a local code-signing certificate (if one doesn't exist).
2. Compiles the script into a single `.exe` using PyInstaller.
3. Embeds the `uiAccess` manifest.
4. Signs the resulting `.exe` with the local certificate.

# Usage
Once built, you **MUST** move the resulting EXE into `C:\Program Files\LumaxStressMeter\` for the Z-order privilege to activate.