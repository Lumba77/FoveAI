"""
FoveAI Monetizing Machine State Monitor
Real-time tracking of agent machine health with simplified diagrams
Updated every 5 minutes for fresh snapshot
"""

import json
import os
import platform
import subprocess
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class MachineState:
    """State of an agent's execution machine"""

    agent_id: str
    timestamp: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_percent: float = 0.0
    network_up_mbps: float = 0.0
    network_down_mbps: float = 0.0
    process_count: int = 0
    uptime_seconds: int = 0
    status: str = "unknown"  # healthy, degraded, critical, idle
    temperature_c: float = 0.0
    fan_percent: float = 0.0


@dataclass
class TrendData:
    """Historical trend data for a metric"""

    metric: str
    values: deque  # Last N values (5-minute window = 60 values at 5-sec intervals)
    trend: str = "stable"  # increasing, decreasing, stable, volatile


class MachineMonitor:
    """Monitor machine states across all FoveAI agents"""

    def __init__(self, data_dir: str = "Integrator/cogni_data/monetizing"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.machine_states: dict[str, MachineState] = {}
        self.trends: dict[str, dict[str, TrendData]] = {}
        self.history_file = os.path.join(data_dir, "machine_history.json")
        self.snapshots_dir = os.path.join(data_dir, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)

        # Configuration
        self.update_interval = 300  # 5 minutes = 300 seconds
        self.max_history_points = 60  # 5 minutes of data at 5-sec intervals
        self.health_thresholds = {
            "cpu_critical": 90,
            "cpu_degraded": 70,
            "memory_critical": 90,
            "memory_degraded": 80,
            "temp_critical": 85,
            "temp_degraded": 70,
        }

        self._load_history()

    def _load_history(self):
        """Load previous machine state history"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    self.machine_states = {
                        k: MachineState(**v) if isinstance(v, dict) else v
                        for k, v in data.get("machine_states", {}).items()
                    }
                    self.trends = data.get("trends", {})
            except Exception as e:
                print(f"Warning: Could not load history: {e}")

    def _save_history(self):
        """Save current machine state history"""
        data = {
            "machine_states": {
                k: asdict(v) if hasattr(v, "__dataclass_fields__") else v
                for k, v in self.machine_states.items()
            },
            "trends": self.trends,
            "last_update": datetime.now().isoformat(),
        }
        try:
            with open(self.history_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save history: {e}")

    def get_system_metrics(self) -> dict[str, float]:
        """Get current system-wide metrics"""
        metrics = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_used_gb": 0.0,
            "memory_total_gb": 0.0,
            "disk_percent": 0.0,
            "network_up_mbps": 0.0,
            "network_down_mbps": 0.0,
            "process_count": 0,
            "temperature_c": 0.0,
            "fan_percent": 0.0,
        }

        try:
            # CPU and Memory
            if platform.system() == "Windows":
                # Use PowerShell for Windows metrics
                cmd = "Get-Process | Measure-Object -Property CPU -Sum | Select-Object -ExpandProperty Sum"
                try:
                    result = subprocess.run(
                        ["powershell", "-Command", cmd],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    # Simple CPU estimation
                    metrics["cpu_percent"] = self._get_windows_cpu_percent()
                except:
                    pass

                # Memory info
                cmd = "(Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | ForEach-Object { ($_.TotalVisibleMemorySize - $_.FreePhysicalMemory) / $_.TotalVisibleMemorySize * 100 })"
                try:
                    result = subprocess.run(
                        ["powershell", "-Command", cmd],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.stdout.strip():
                        metrics["memory_percent"] = float(result.stdout.strip())
                except:
                    pass

                # Disk info
                cmd = "(Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' } | ForEach-Object { (($_.Size - $_.SizeRemaining) / $_.Size) * 100 } | Measure-Object -Average | Select-Object -ExpandProperty Average)"
                try:
                    result = subprocess.run(
                        ["powershell", "-Command", cmd],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.stdout.strip():
                        metrics["disk_percent"] = float(result.stdout.strip())
                except:
                    pass

                # Process count
                try:
                    result = subprocess.run(
                        ["powershell", "-Command", "(Get-Process).Count"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.stdout.strip():
                        metrics["process_count"] = int(result.stdout.strip())
                except:
                    pass

            elif platform.system() == "Linux":
                # Linux metrics via /proc
                try:
                    with open("/proc/stat", "r") as f:
                        line = f.readline()
                        parts = line.split()
                        total = sum(map(int, parts[1:]))
                        idle = int(parts[4])
                        metrics["cpu_percent"] = (
                            (1 - idle / total) * 100 if total > 0 else 0
                        )
                except:
                    pass

                # Memory info from /proc/meminfo
                try:
                    with open("/proc/meminfo", "r") as f:
                        meminfo = {}
                        for line in f:
                            parts = line.split(":")
                            if len(parts) == 2:
                                key = parts[0].strip()
                                val = parts[1].strip().split()[0]
                                meminfo[key] = int(val)
                        total = meminfo.get("MemTotal", 1)
                        available = meminfo.get("MemAvailable", 0)
                        metrics["memory_percent"] = (
                            ((total - available) / total) * 100 if total > 0 else 0
                        )
                        metrics["memory_total_gb"] = (
                            total / 1024 / 1024
                        )  # Convert to GB
                        metrics["memory_used_gb"] = (total - available) / 1024 / 1024
                except:
                    pass

                # Disk info
                try:
                    stat = os.statvfs("/")
                    total = stat.f_blocks * stat.f_frsize
                    free = stat.f_bfree * stat.f_frsize
                    metrics["disk_percent"] = (
                        ((total - free) / total) * 100 if total > 0 else 0
                    )
                except:
                    pass

                # Process count
                try:
                    metrics["process_count"] = (
                        len(os.listdir("/proc")) - 1
                    )  # Exclude . and ..
                except:
                    pass

        except Exception as e:
            print(f"Error getting system metrics: {e}")

        return metrics

    def _get_windows_cpu_percent(self) -> float:
        """Get CPU percent on Windows"""
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    '(Get-Counter "\\Processor(_Total)\\% Processor Time").CounterSamples.CookedValue',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
        except:
            pass
        return 0.0

    def update_machine_state(self, agent_id: str) -> MachineState:
        """Update and return machine state for an agent"""
        metrics = self.get_system_metrics()

        state = MachineState(
            agent_id=agent_id,
            timestamp=datetime.now().isoformat(),
            cpu_percent=metrics["cpu_percent"],
            memory_percent=metrics["memory_percent"],
            memory_used_gb=metrics["memory_used_gb"],
            memory_total_gb=metrics["memory_total_gb"],
            disk_percent=metrics["disk_percent"],
            network_up_mbps=metrics["network_up_mbps"],
            network_down_mbps=metrics["network_down_mbps"],
            process_count=metrics["process_count"],
            temperature_c=metrics["temperature_c"],
            fan_percent=metrics["fan_percent"],
            status=self._determine_status(metrics),
        )

        self.machine_states[agent_id] = state
        self._update_trends(agent_id, state)
        self._save_history()

        return state

    def _determine_status(self, metrics: dict[str, float]) -> str:
        """Determine machine status based on metrics"""
        # Check CPU
        if metrics.get("cpu_percent", 0) >= self.health_thresholds["cpu_critical"]:
            return "critical"
        if metrics.get("cpu_percent", 0) >= self.health_thresholds["cpu_degraded"]:
            return "degraded"

        # Check memory
        if (
            metrics.get("memory_percent", 0)
            >= self.health_thresholds["memory_critical"]
        ):
            return "critical"
        if (
            metrics.get("memory_percent", 0)
            >= self.health_thresholds["memory_degraded"]
        ):
            return "degraded"

        # Check temperature
        if metrics.get("temperature_c", 0) >= self.health_thresholds["temp_critical"]:
            return "critical"
        if metrics.get("temperature_c", 0) >= self.health_thresholds["temp_degraded"]:
            return "degraded"

        # Check disk
        if metrics.get("disk_percent", 0) >= 95:
            return "critical"

        return "healthy"

    def _update_trends(self, agent_id: str, state: MachineState):
        """Update trend data for an agent"""
        if agent_id not in self.trends:
            self.trends[agent_id] = {}

        metrics_to_track = {
            "cpu_percent": state.cpu_percent,
            "memory_percent": state.memory_percent,
            "disk_percent": state.disk_percent,
        }

        for metric, value in metrics_to_track.items():
            if metric not in self.trends[agent_id]:
                self.trends[agent_id][metric] = TrendData(
                    metric=metric, values=deque(maxlen=self.max_history_points)
                )

            trend = self.trends[agent_id][metric]
            trend.values.append(value)
            self._calculate_trend(trend)

    def _calculate_trend(self, trend: TrendData):
        """Calculate trend direction based on values"""
        if len(trend.values) < 2:
            trend.trend = "stable"
            return

        values = list(trend.values)
        if len(values) < 2:
            trend.trend = "stable"
            return

        # Simple linear trend calculation
        n = len(values)
        if n < 3:
            trend.trend = "stable"
            return

        # Calculate slope
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            trend.trend = "stable"
            return

        slope = numerator / denominator
        threshold = 0.01  # Minimum slope for trend

        if slope > threshold:
            trend.trend = "increasing"
        elif slope < -threshold:
            trend.trend = "decreasing"
        else:
            trend.trend = "stable"

        # Check for volatility
        variance = sum((x - y_mean) ** 2 for x in values) / n
        if variance > 10:  # High variance threshold
            trend.trend = "volatile"

    def get_snapshot(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get snapshot of machine states"""
        snapshot = {"timestamp": datetime.now().isoformat(), "agents": {}}

        if agent_id and agent_id in self.machine_states:
            snapshot["agents"][agent_id] = asdict(self.machine_states[agent_id])
        else:
            for aid, state in self.machine_states.items():
                snapshot["agents"][aid] = asdict(state)

        return snapshot

    def save_snapshot(self, filename: str | None = None) -> str:
        """Save snapshot to file"""
        if filename is None:
            filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(self.snapshots_dir, filename)
        snapshot = self.get_snapshot()

        with open(filepath, "w") as f:
            json.dump(snapshot, f, indent=2)

        return filepath

    def generate_simple_diagram(self, agent_id: str) -> str:
        """Generate simplified ASCII/SVG diagram for an agent's machine state"""
        if agent_id not in self.machine_states:
            return f"Machine state not found for agent: {agent_id}"

        state = self.machine_states[agent_id]

        # Build ASCII bar for each metric
        def make_bar(
            value: float, max_val: float = 100, width: int = 20, char: str = "█"
        ) -> str:
            filled = int((value / max_val) * width)
            return f"{char * filled}{'○' * (width - filled)} {value:.1f}%"

        # Status indicator
        status_colors = {
            "healthy": "🟢",
            "degraded": "🟡",
            "critical": "🔴",
            "idle": "⚪",
            "unknown": "❓",
        }
        status_icon = status_colors.get(state.status, "❓")

        # Build diagram
        diagram = f"""
╔══════════════════════════════════════════════════════════════╗
║  FoveAI AGENT: {agent_id:<40}║
║  Status: {status_icon} {state.status.upper():<54}║
╠══════════════════════════════════════════════════════════════╣
║  CPU:    {make_bar(state.cpu_percent)}║
║  RAM:    {make_bar(state.memory_percent)}║
║  DISK:   {make_bar(state.disk_percent)}║
╠══════════════════════════════════════════════════════════════╣
║  NET:    ↑ {state.network_up_mbps:.1f} Mbps  ↓ {state.network_down_mbps:.1f} Mbps       ║
║  PROCS:  {state.process_count:<4}                                              ║
║  TEMP:   {state.temperature_c:.1f}°C  FAN: {make_bar(state.fan_percent, 100, 10)}║
╠══════════════════════════════════════════════════════════════╣
║  UPTIME: {self._format_uptime(state.uptime_seconds):<51}║
║  UPDATED: {state.timestamp:<51}║
╚══════════════════════════════════════════════════════════════╝
"""

        return diagram

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime seconds to readable string"""
        if seconds <= 0:
            return "N/A"

        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        mins = (seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")

        return " ".join(parts) if parts else "0m"

    def generate_summary_diagram(self) -> str:
        """Generate summary diagram with trends across all agents"""
        snapshot = self.get_snapshot()

        if not snapshot["agents"]:
            return "No agents to monitor"

        # Aggregate metrics
        total_cpu = sum(a["cpu_percent"] for a in snapshot["agents"].values())
        total_mem = sum(a["memory_percent"] for a in snapshot["agents"].values())
        agent_count = len(snapshot["agents"])

        avg_cpu = total_cpu / agent_count if agent_count > 0 else 0
        avg_mem = total_mem / agent_count if agent_count > 0 else 0

        # Count statuses
        status_counts = {"healthy": 0, "degraded": 0, "critical": 0, "idle": 0}
        for agent in snapshot["agents"].values():
            status_counts[agent["status"]] = status_counts.get(agent["status"], 0) + 1

        # Build summary
        summary = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    FoveAI MONETIZING AGENT SWARM SUMMARY                        ║
║                           Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  AGENTS: {agent_count:<5}  AVG CPU: {avg_cpu:>5.1f}%  AVG RAM: {avg_mem:>5.1f}%                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  STATUS BREAKDOWN:                                                             ║
║    🟢 Healthy:   {status_counts["healthy"]:<4}   🟡 Degraded:   {status_counts["degraded"]:<4}   🔴 Critical:   {status_counts["critical"]:<4}   ⚪ Idle:   {status_counts["idle"]:<4} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  MACHINE TRENDS (5-min window):                                                ║
"""

        # Add trends for each agent
        for agent_id, state in snapshot["agents"].items():
            trends = self.trends.get(agent_id, {})
            cpu_trend = trends.get("cpu_percent", {}).get("trend", "stable")
            mem_trend = trends.get("memory_percent", {}).get("trend", "stable")

            trend_icons = {
                "increasing": "↑",
                "decreasing": "↓",
                "stable": "•",
                "volatile": "×",
            }

            summary += f"║    {agent_id[:20]:<20} CPU: {trend_icons.get(cpu_trend, '?')} {cpu_trend:<8} RAM: {trend_icons.get(mem_trend, '?')} {mem_trend:<8}              ║\n"

        summary += """╚══════════════════════════════════════════════════════════════════════════════╝
        """

        return summary

    def run_monitoring_cycle(self, agents: list[str]):
        """Run a complete monitoring cycle for all agents"""
        print(f"\n{'=' * 80}")
        print(
            f"FoveAI MONETIZING MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print(f"{'=' * 80}")

        for agent_id in agents:
            print(f"\n{agent_id}:")
            print(self.generate_simple_diagram(agent_id))

        print(f"\n{'=' * 80}")
        print("SWARM SUMMARY")
        print(f"{'=' * 80}")
        print(self.generate_summary_diagram())

        # Save snapshot
        snapshot_path = self.save_snapshot()
        print(f"\nSnapshot saved to: {snapshot_path}")


# Example usage
if __name__ == "__main__":
    import sys

    monitor = MachineMonitor()

    # Agent IDs to monitor
    agents = sys.argv[1:] if len(sys.argv) > 1 else ["agent_1", "agent_2", "agent_3"]

    # Update states for all agents
    for agent_id in agents:
        monitor.update_machine_state(agent_id)

    # Run monitoring cycle
    monitor.run_monitoring_cycle(agents)
