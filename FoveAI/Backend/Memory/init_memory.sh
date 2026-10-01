#!/bin/bash
# LUMAX Memory Initialization Script
# Run this to import all previous sessions into MCP memory

echo "=== LUMAX Memory Initialization ==="
echo ""

# Import all Cline history
echo "Importing Cline history..."
import_sessions --import-cline

# Import CON Vessel history
echo "Importing CON Vessel history..."
import_sessions --import-con

# Create summary for quick reference
echo ""
echo "Creating session summary..."
import_sessions --list

echo ""
echo "=== Memory Initialized ==="
echo ""
echo "Your previous sessions are now available via:"
echo "  - MCP tool: get_lumax_memory"
echo "  - MCP tool: search_lumax_memory"
echo "  - MCP tool: get_session_injection"
echo ""
echo "In new Cline sessions, the memory will be automatically loaded."