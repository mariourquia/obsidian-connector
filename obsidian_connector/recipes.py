"""YAML-based Workflow Orchestrator for obsidian-connector."""

import yaml
import sys
import subprocess
from pathlib import Path
from obsidian_connector.config import resolve_vault_path

RECIPE_DIR = Path.home() / ".obsx" / "recipes"

def init_recipes():
    """Create default recipes if they don't exist."""
    RECIPE_DIR.mkdir(parents=True, exist_ok=True)
    
    default_recipe = RECIPE_DIR / "morning_brief.yml"
    if not default_recipe.exists():
        default_recipe.write_text("""\
# Built-in recipe: Morning brief with Ix mapping integration
steps:
  - action: "obsx today --json"
    register: "today_status"
  - action: "obsx ix impact {{topic}}"
    register: "ix_impact"
  - action: "obsx capture --tag investigation 'Morning orchestrator completed: {{topic}}'"
""", encoding="utf-8")


def string_replace(text: str, context: dict) -> str:
    """Simple {{var}} interplation from context."""
    for k, v in context.items():
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


def run_recipe(name: str, cli_args: list[str]):
    """Execute a YAML recipe step-by-step."""
    init_recipes()
    recipe_path = RECIPE_DIR / f"{name}.yml"
    
    if not recipe_path.exists():
        print(f"Error: Recipe '{name}' not found at {recipe_path}", file=sys.stderr)
        print("Available recipes:", file=sys.stderr)
        for p in RECIPE_DIR.glob("*.yml"):
            print(f"  - {p.stem}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(recipe_path, "r", encoding="utf-8") as f:
            recipe = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing recipe: {e}", file=sys.stderr)
        sys.exit(1)

    context = {}
    
    # Parse CLI positional args to context (e.g. topic)
    if cli_args:
        context["topic"] = cli_args[0]
        context["arg1"] = cli_args[0]
    
    print(f"Running recipe: {name}...")
    
    steps = recipe.get("steps", [])
    for idx, step in enumerate(steps, 1):
        action = string_replace(step.get("action", ""), context)
        print(f"  [{idx}/{len(steps)}] Executing: {action}")
        
        # Split but preserve quotes logic could be needed, but we'll use shell=True for simplicity in pipelines
        try:
            result = subprocess.run(action, shell=True, capture_output=True, text=True)
            register_key = step.get("register")
            if register_key:
                context[register_key] = result.stdout.strip()
            
            if result.returncode != 0:
                print(f"    Warning: Step {idx} failed with code {result.returncode}\n{result.stderr}", file=sys.stderr)
        except Exception as e:
            print(f"    Error: {e}", file=sys.stderr)

    print("Recipe completed successfully.")
