---
name: azure-deploy
description: "Execute Azure deployments for ALREADY-PREPARED applications that have existing .azure/deployment-plan.md and infrastructure files. DO NOT use this skill when the user asks to CREATE a new application — use azure-prepare instead. This skill runs azd up, azd deploy, terraform apply, and az deployment commands with built-in error recovery. Requires .azure/deployment-plan.md from azure-prepare and validated status from azure-validate. WHEN: \\"run azd up\\", \\"run azd deploy\\", \\"execute deployment\\", \\"push to production\\", \\"push to cloud\\", \\"go live\\", \\"ship it\\", \\"bicep deploy\\", \\"terraform apply\\", \\"publish to Azure\\", \\"launch on Azure\\". DO NOT USE WHEN: \\"create and deploy\\", \\"build and deploy\\", \\"create a new app\\", \\"set up infrastructure\\", \\"create and deploy to Azure using Terraform\\" — use azure-prepare for these."
version: 1.0.0
---

# Activate Skill: azure-deploy

Please read and internalize the skill documentation located at:
**`c:/Users/danie/program/LUMAX/.github/skills/azure-deploy/SKILL.md`**

(And any other relevant files in that directory)

## Mission
Execute Azure deployments for ALREADY-PREPARED applications that have existing .azure/deployment-plan.md and infrastructure files. DO NOT use this skill when the user asks to CREATE a new application — use azure-prepare instead. This skill runs azd up, azd deploy, terraform apply, and az deployment commands with built-in error recovery. Requires .azure/deployment-plan.md from azure-prepare and validated status from azure-validate. WHEN: \"run azd up\", \"run azd deploy\", \"execute deployment\", \"push to production\", \"push to cloud\", \"go live\", \"ship it\", \"bicep deploy\", \"terraform apply\", \"publish to Azure\", \"launch on Azure\". DO NOT USE WHEN: \"create and deploy\", \"build and deploy\", \"create a new app\", \"set up infrastructure\", \"create and deploy to Azure using Terraform\" — use azure-prepare for these.

## Instructions
1.  **Load Context**: Read the file path provided above.
2.  **Activate Persona**: Adopt the role and expertise defined in that document.
3.  **Execute**: Await further user instructions acting as this expert.
