---
name: azure-prepare
description: "Prepare azd-based Azure projects for deployment: generates azure.yaml, infrastructure (Bicep/Terraform), and Dockerfiles for the Azure Developer CLI (azd) workflow. USE ONLY when the user explicitly wants to use azd as the deployment tool, or the project already has an azure.yaml file. DO NOT USE FOR: non-azd deployments, Python App Service code-only deploys (use python-appservice-deploy), or cross-cloud migration (use azure-cloud-migrate). WHEN: prepare app for azd, create azure.yaml, set up azd infrastructure, modernize app for Azure with azd, deploy with azd, function app, timer trigger, service bus trigger, event-driven function, managed identity, generate Bicep, generate Terraform, create and deploy to Azure."
version: 1.0.0
---

# Activate Skill: azure-prepare

Please read and internalize the skill documentation located at:
**`c:/Users/danie/program/LUMAX/.github/skills/azure-prepare/SKILL.md`**

(And any other relevant files in that directory)

## Mission
Prepare azd-based Azure projects for deployment: generates azure.yaml, infrastructure (Bicep/Terraform), and Dockerfiles for the Azure Developer CLI (azd) workflow. USE ONLY when the user explicitly wants to use azd as the deployment tool, or the project already has an azure.yaml file. DO NOT USE FOR: non-azd deployments, Python App Service code-only deploys (use python-appservice-deploy), or cross-cloud migration (use azure-cloud-migrate). WHEN: prepare app for azd, create azure.yaml, set up azd infrastructure, modernize app for Azure with azd, deploy with azd, function app, timer trigger, service bus trigger, event-driven function, managed identity, generate Bicep, generate Terraform, create and deploy to Azure.

## Instructions
1.  **Load Context**: Read the file path provided above.
2.  **Activate Persona**: Adopt the role and expertise defined in that document.
3.  **Execute**: Await further user instructions acting as this expert.
