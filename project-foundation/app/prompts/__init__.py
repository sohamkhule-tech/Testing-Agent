"""Prompt management."""
from pathlib import Path

from app.prompts.prompt_loader import PromptLoader, PromptRegistry
from app.config import get_settings
from app.exceptions import PromptNotFoundError


def get_prompt(prompt_name: str) -> str:
    """
    Synchronously load a prompt template's raw content.

    Args:
        prompt_name: Name of the prompt file (without extension)

    Returns:
        Raw prompt template content as string.

    Raises:
        PromptNotFoundError: If the prompt file does not exist.
    """
    settings = get_settings()
    prompts_dir = Path(settings.prompt.prompt_base_path)
    prompt_path = prompts_dir / f"{prompt_name}.md"
    if not prompt_path.exists():
        raise PromptNotFoundError(
            f"Prompt template not found: {prompt_name}", prompt_name=prompt_name
        )
    return prompt_path.read_text(encoding="utf-8")


__all__ = [
    "PromptLoader",
    "PromptRegistry",
    "get_prompt",
]
