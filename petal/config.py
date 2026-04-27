"""Configuration file management for Petal (.petal.yml)."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class PetalConfig:
    """Load and manage .petal.yml configuration files."""
    
    def __init__(self, config_path: str = ".petal.yml"):
        """Initialize config manager.
        
        Args:
            config_path: Path to .petal.yml file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        
        if self.config_path.exists():
            self.load()
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from .petal.yml file.
        
        Returns:
            Configuration dictionary
        """
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {self.config_path}: {e}")
        except FileNotFoundError:
            self.config = {}
        
        return self.config
    
    def save(self) -> None:
        """Save configuration to .petal.yml file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.
        
        Args:
            key: Configuration key (supports nested keys with '.')
            default: Default value if key not found
        
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value.
        
        Args:
            key: Configuration key (supports nested keys with '.')
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    @staticmethod
    def create_default() -> str:
        """Create a default .petal.yml file content.
        
        Returns:
            Default configuration YAML as string
        """
        return """# Petal Energy Optimizer Configuration
# Place this file in your project root as .petal.yml

# Default optimization policy: eco, balanced, or perf
policy: balanced

# Number of benchmark runs to average results
benchmark_runs: 3

# Telemetry collector: auto, synthetic, rapl, perf, amd_uprof, intel_pcm, apple_io
telemetry_collector: auto

# Output options
output:
  # Generate HTML report
  html_report: true
  # Report output directory
  report_dir: frontend/report
  # Output optimized C files
  output_dir: .
  # Generate JSON output
  json: false

# Optimization options
optimization:
  # Enable optimization (can be overridden by --analyse)
  enabled: true
  # Block size for loop tiling
  tile_size: 64
  # Verify correctness after optimization
  verify: true

# File patterns to process
files:
  # Include patterns (glob)
  include:
    - "**/*.c"
  # Exclude patterns (glob)
  exclude:
    - "test_*.c"
    - "*_test.c"
    - "backend/test_workloads/*"

# Logging options
logging:
  # Log level: debug, info, warning, error
  level: info
  # Show structured logs
  structured: true
"""


def load_config(config_file: str = ".petal.yml") -> Optional[PetalConfig]:
    """Load configuration from file.
    
    Args:
        config_file: Path to configuration file
    
    Returns:
        PetalConfig object or None if file doesn't exist
    """
    config_path = Path(config_file)
    if config_path.exists():
        config = PetalConfig(config_file)
        config.load()
        return config
    return None


def merge_with_args(config: Optional[PetalConfig], args: Any) -> None:
    """Merge configuration file values with command-line arguments.
    
    Command-line arguments take precedence over config file values.
    
    Args:
        config: PetalConfig object
        args: argparse Namespace with command-line arguments
    """
    if config is None:
        return
    
    # Policy
    if hasattr(args, 'policy') and args.policy is None:
        args.policy = config.get('policy', 'balanced')
    
    # Benchmark runs
    if hasattr(args, 'runs') and args.runs is None:
        args.runs = config.get('benchmark_runs', 1)
    
    # Telemetry collector
    if hasattr(args, 'collector') and args.collector is None:
        args.collector = config.get('telemetry_collector', 'auto')
    
    # HTML report
    if hasattr(args, 'html') and not args.html:
        args.html = config.get('output.html_report', False)
    
    # JSON output
    if hasattr(args, 'json') and not args.json:
        args.json = config.get('output.json', False)
