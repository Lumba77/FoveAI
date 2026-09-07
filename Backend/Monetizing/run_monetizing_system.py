"""
FoveAI Monetizing System Runner
Orchestrates machine state monitoring, idea discovery, and certification
"""

import sys
import os
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from machine_state import MachineMonitor, MachineState
from idea_engine import IdeaEngine, IdeaCategory, Idea


class MonetizingSystem:
    """Main orchestrator for FoveAI monetizing system"""
    
    def __init__(self, data_dir: str = "Integrator/cogni_data/monetizing"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize subsystems
        self.machine_monitor = MachineMonitor(data_dir)
        self.idea_engine = IdeaEngine(data_dir)
        
        # Config
        self.update_interval = 300  # 5 minutes
        self.monitoring_enabled = True
        self.certification_enabled = True
        
        # Runtime state
        self.running = False
        self.agents: List[str] = []
        self.certified_ideas: Dict[str, Dict[str, Any]] = {}
        
        self.log_file = os.path.join(data_dir, "system_log.txt")
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        print(log_entry)
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry + "\n")
    
    def add_agent(self, agent_id: str):
        """Add an agent to monitor"""
        if agent_id not in self.agents:
            self.agents.append(agent_id)
            self.log(f"Added agent: {agent_id}")
    
    def remove_agent(self, agent_id: str):
        """Remove an agent from monitoring"""
        if agent_id in self.agents:
            self.agents.remove(agent_id)
            self.log(f"Removed agent: {agent_id}")
    
    def run_monitoring_cycle(self):
        """Run a complete monitoring cycle"""
        if not self.agents:
            self.log("No agents to monitor", "WARN")
            return
        
        self.log(f"Starting monitoring cycle for {len(self.agents)} agents...")
        
        # Update machine states
        for agent_id in self.agents:
            self.machine_monitor.update_machine_state(agent_id)
        
        # Run monitoring cycle
        self.machine_monitor.run_monitoring_cycle(self.agents)
        
        self.log("Monitoring cycle complete")
    
    def discover_ideas(self, search_depth: int = 10) -> List[Idea]:
        """Discover new monetizing ideas"""
        self.log("Starting idea discovery...")
        
        ideas = self.idea_engine.discover_new_ideas(search_depth=search_depth)
        
        self.log(f"Discovered {len(ideas)} ideas")
        
        return ideas
    
    def certify_idea(self, idea_id: str) -> Optional[Dict[str, Any]]:
        """Run local AI certification for an idea"""
        if not self.certification_enabled:
            self.log("Certification disabled", "WARN")
            return None
        
        self.log(f"Running certification for idea: {idea_id}")
        
        certainty = self.idea_engine.local_ai_certify(idea_id)
        
        if certainty.certification_status == "certified":
            self.log(f"Idea {idea_id} certified successfully", "SUCCESS")
            result = {
                "idea_id": idea_id,
                "status": "certified",
                "total_score": certainty.total_score,
                "certification_status": certainty.certification_status
            }
            self.certified_ideas[idea_id] = result
            return result
        else:
            self.log(f"Idea {idea_id} certification failed: {certainty.certification_status}", "WARN")
            return None
    
    def run_implementation_plan(self, idea_id: str) -> Dict[str, Any]:
        """Generate and run implementation plan"""
        self.log(f"Generating implementation plan for: {idea_id}")
        
        plan = self.idea_engine.generate_implementation_plan(idea_id)
        
        if not plan:
            return {"error": "Failed to generate plan"}
        
        result = {
            "idea_id": idea_id,
            "idea_title": plan.idea_title,
            "timeline_days": plan.timeline_days,
            "estimated_cost": plan.estimated_cost,
            "estimated_revenue": plan.estimated_revenue,
            "phases": plan.phases,
            "status": "plan_generated"
        }
        
        self.log(f"Plan generated: {plan.timeline_days} days, ${plan.estimated_cost} cost")
        
        return result
    
    def publish_idea(self, idea_id: str) -> Dict[str, Any]:
        """Publish a certified idea for deployment"""
        if idea_id not in self.certified_ideas:
            return {"error": f"Idea {idea_id} not certified"}
        
        idea = self.idea_engine.ideas[idea_id]
        
        # Create deployment package
        deployment = {
            "idea_id": idea_id,
            "idea_title": idea.title,
            "category": idea.category.value,
            "tools": idea.tools_required,
            "skills": idea.skills_required,
            "config": {
                "risk_tolerance": "moderate",
                "max_daily_loss": 100.0,
                "max_positions": 3
            },
            "certification": self.certified_ideas[idea_id],
            "timestamp": datetime.now().isoformat(),
            "status": "published"
        }
        
        # Save deployment package
        deploy_file = os.path.join(self.data_dir, "deployments", f"{idea_id}.json")
        os.makedirs(os.path.dirname(deploy_file), exist_ok=True)
        
        with open(deploy_file, 'w') as f:
            json.dump(deployment, f, indent=2)
        
        self.log(f"Idea {idea_id} published to {deploy_file}", "SUCCESS")
        
        return deployment
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        snapshot = self.machine_monitor.get_snapshot()
        ideas = list(self.idea_engine.ideas.values())
        certified = list(self.certified_ideas.values())
        
        return {
            "timestamp": datetime.now().isoformat(),
            "agents_monitored": len(self.agents),
            "agents_status": snapshot['agents'],
            "ideas_discovered": len(ideas),
            "ideas_certified": len(certified),
            "certified_ideas": certified,
            "certification_enabled": self.certification_enabled,
            "monitoring_enabled": self.monitoring_enabled
        }
    
    def run_full_cycle(self):
        """Run a complete system cycle: monitor + discover + certify"""
        print(f"\n{'='*80}")
        print(f"FoveAI MONETIZING SYSTEM - FULL CYCLE")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")
        
        # Step 1: Monitoring
        print("📋 STEP 1: MACHINE MONITORING")
        print("-" * 40)
        self.run_monitoring_cycle()
        
        # Step 2: Idea Discovery
        print("\n\n🔍 STEP 2: IDEA DISCOVERY")
        print("-" * 40)
        ideas = self.discover_ideas(search_depth=5)
        
        # Step 3: Certification (first 3 ideas)
        print("\n\n🛡️  STEP 3: AI CERTIFICATION")
        print("-" * 40)
        for idea in ideas[:3]:
            self.certify_idea(idea.id)
        
        # Step 4: Summary
        print("\n\n📊 STEP 4: SYSTEM SUMMARY")
        print("-" * 40)
        status = self.get_system_status()
        print(f"Agents monitored: {status['agents_monitored']}")
        print(f"Ideas discovered: {status['ideas_discovered']}")
        print(f"Ideas certified: {status['ideas_certified']}")
        
        # Save status
        status_file = os.path.join(self.data_dir, "system_status.json")
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)
        self.log(f"System status saved to {status_file}", "SUCCESS")
        
        print(f"\n{'='*80}")
        print(f"FULL CYCLE COMPLETE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")


def main():
    """Main entry point"""
    print("\n" + "="*80)
    print("FoveAI MONETIZING SYSTEM")
    print("="*80)
    print("\nSelect an action:")
    print("  1. Run full system cycle")
    print("  2. Run monitoring cycle only")
    print("  3. Discover ideas")
    print("  4. List system status")
    print("  5. Test idea certification")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    system = MonetizingSystem()
    
    if choice == "1":
        system.add_agent("agent_1")
        system.add_agent("agent_2")
        system.add_agent("agent_3")
        system.run_full_cycle()
    elif choice == "2":
        system.add_agent("agent_1")
        system.run_monitoring_cycle()
    elif choice == "3":
        system.discover_ideas()
    elif choice == "4":
        print(json.dumps(system.get_system_status(), indent=2))
    elif choice == "5":
        idea_id = input("Enter idea ID to certify: ").strip()
        result = system.certify_idea(idea_id)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Certification failed or disabled")
    else:
        print("Invalid choice")
    
    print("\n")


if __name__ == "__main__":
    main()