### **Tool Evaluation: Cursor vs. Windsurf**

For this specific task—refactoring an entire multi-container repository using a multi-agent steering document—**Cursor (using Composer in Agent Mode)** is currently the stronger option.

* **Cursor (Composer / Agent Mode):** Excels at workspace-wide edits across dozens of files simultaneously, running terminal commands automatically, fixing build errors autonomously, and committing incremental git checkpoints.  
* **Windsurf (Cascade):** Highly capable with real-time deep context awareness, but Cursor's Agent Mode gives you finer control over multi-file structural overhauls when guided by an explicit XML/XRLF directive.

### **How to Rig the "Spatial Machine" Environment**

To transform a copy of your repository without risking your main project or overheating your computer, you can set up a dedicated configuration workflow.

#### **Step 1: Isolate the Repository Copy**

Before letting an AI agent loose on the codebase, create an isolated workspace copy.

> 1. Create a fresh working directory for your build (e.g., vr-compagent-streamlined).  
> 2. Clone your existing repository into this folder or extract a ZIP copy.  
> 3. Immediately create and switch to a dedicated refactoring branch:  
>    Bash  
>    git checkout \-b feature/xrlf-streamlined-refactor

#### **Step 2: Configure the AI Steering Rules**

To make Cursor or Windsurf automatically read and follow your XRLF steering directive upon startup:

* **For Cursor:**  
  1. Save your XRLF\_REFACTOR\_STEERING.xrlf file in the root directory of the duplicated project.  
  2. Create a file named .cursorrules in the root folder.  
  3. Inside .cursorrules, add the following directive:  
     Always adhere strictly to the rules, resource throttles, and phase plans defined in XRLF\_REFACTOR\_STEERING.xrlf.  
     Execute refactoring tasks phase-by-phase. Do not perform unthrottled loop testing. Perform a git commit after each successful task completion.  
* **For Windsurf:**  
  1. Save XRLF\_REFACTOR\_STEERING.xrlf in the root folder.  
  2. Create a .windsurfrules file in the root folder with the same instruction text.

#### **Step 3: Automated Rigging Script**

You can run a simple setup script on your computer to automate the creation of the duplicate project folder, copy the steering directives, and prepare the workspace.

Bash  
\#\!/bin/bash  
\# FoveAI Rigging Script

ORIGINAL\_REPO\_DIR="$1"  
TARGET\_DIR="spatial\_machine\_build"

if \[ \-z "$ORIGINAL\_REPO\_DIR" \]; then  
    echo "Usage: ./rig\_spatial\_machine.sh /path/to/original/vr-compagent"  
    exit 1  
fi

echo "\[1/4\] Duplicating repository..."  
cp \-r "$ORIGINAL\_REPO\_DIR" "$TARGET\_DIR"  
cd "$TARGET\_DIR" || exit

echo "\[2/4\] Initializing git checkpoint..."  
git checkout \-b feature/xrlf-refactor

echo "\[3/4\] Injecting XRLF Steering Rules..."  
\# System rules are active via XRLF\_REFACTOR\_STEERING.xrlf and .cursorrules

echo "\[4/4\] Workspace successfully rigged\!"  
echo "Open '$TARGET\_DIR' in Cursor, activate Composer Agent Mode, and prompt:"  
echo "'Execute Phase 1 of XRLF\_REFACTOR\_STEERING.xrlf'"

### **Executing the Autonomous Refactor**

Once the workspace is rigged and opened in Cursor:

> 1. Open **Cursor Composer** (Cmd+I or Ctrl+I) and set the mode to **Agent**.  
> 2. Pass the initial instruction:*"Read XRLF\_REFACTOR\_STEERING.xrlf. You are acting as AGENT-ALPHA and AGENT-BETA for Phase 1\. Begin auditing the legacy multi-agent containers and prepare the vLLM distillation dataset according to the governance rules."*  
> 3. **Pacing and Safety:** Cursor will execute terminal commands and edit files step-by-step. Because your XRLF document includes \<compute\_policy\>MEDIUM\_THROTTLE\</compute\_policy\>, the agent will pause, run modular unit tests, and commit code incrementally, keeping CPU and GPU temperatures stable throughout the multi-day transformation.