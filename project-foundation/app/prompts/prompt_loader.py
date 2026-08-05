"""
Prompt Loader and Registry

Manages prompt templates with versioning and variable substitution.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

from app.config import get_settings
from app.core.interfaces import IPromptLoader
from app.exceptions import PromptNotFoundError, PromptRenderError
from app.logging import LoggerMixin


class PromptLoader(IPromptLoader, LoggerMixin):
    """
    Loads and renders prompt templates using Jinja2.

    Supports:
    - Template inheritance
    - Variable substitution
    - Filters and functions
    - Template versioning
    """

    def __init__(self) -> None:
        """Initialize prompt loader."""
        super().__init__()
        settings = get_settings()
        self.prompts_dir = Path(settings.prompt.prompt_base_path)

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            autoescape=False,  # Prompts are not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Register custom filters
        self.env.filters["truncate_middle"] = self._truncate_middle

        self._template_cache: dict[str, Template] = {}

    @staticmethod
    def _truncate_middle(text: str, max_length: int = 1000) -> str:
        """Truncate text in the middle if too long."""
        if len(text) <= max_length:
            return text
        half = max_length // 2
        return f"{text[:half]}...{text[-half:]}"

    async def load_prompt(self, prompt_name: str, version: str | None = None) -> str:
        """
        Load prompt template content.

        Args:
            prompt_name: Name of the prompt file (without extension)
            version: Optional version (not implemented yet, reserved for future)

        Returns:
            Raw prompt template content

        Raises:
            PromptNotFoundError: If prompt doesn't exist
        """
        try:
            # Construct filename
            filename = f"{prompt_name}.md"

            # Load template
            template = self.env.get_template(filename)

            self.logger.info("prompt_loaded", prompt_name=prompt_name)

            return template.source

        except TemplateNotFound:
            self.logger.error("prompt_not_found", prompt_name=prompt_name)
            raise PromptNotFoundError(
                f"Prompt template not found: {prompt_name}",
                prompt_name=prompt_name,
            )
        except Exception as e:
            self.logger.error(
                "prompt_load_failed",
                prompt_name=prompt_name,
                error=str(e),
            )
            raise PromptNotFoundError(
                f"Failed to load prompt {prompt_name}: {str(e)}",
                prompt_name=prompt_name,
            )

    async def render_prompt(
        self, prompt_name: str, variables: dict[str, Any]
    ) -> str:
        """
        Render prompt with variables.

        Args:
            prompt_name: Name of the prompt
            variables: Template variables

        Returns:
            Rendered prompt

        Raises:
            PromptNotFoundError: If prompt doesn't exist
            PromptRenderError: If rendering fails
        """
        try:
            # Construct filename
            filename = f"{prompt_name}.md"

            # Get template (uses cache)
            cache_key = f"{prompt_name}"
            if cache_key not in self._template_cache:
                self._template_cache[cache_key] = self.env.get_template(filename)

            template = self._template_cache[cache_key]

            # Render
            rendered = template.render(**variables)

            self.logger.info(
                "prompt_rendered",
                prompt_name=prompt_name,
                variables_count=len(variables),
            )

            return rendered

        except TemplateNotFound:
            self.logger.error("prompt_not_found", prompt_name=prompt_name)
            raise PromptNotFoundError(
                f"Prompt template not found: {prompt_name}",
                prompt_name=prompt_name,
            )
        except Exception as e:
            self.logger.error(
                "prompt_render_failed",
                prompt_name=prompt_name,
                error=str(e),
            )
            raise PromptRenderError(
                f"Failed to render prompt {prompt_name}: {str(e)}",
                prompt_name=prompt_name,
            )

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._template_cache.clear()
        self.logger.info("template_cache_cleared")


class PromptRegistry:
    """
    Registry for prompt metadata and discovery.

    Manages prompt catalog and metadata.
    """

    def __init__(self, prompts_dir: Path) -> None:
        """
        Initialize prompt registry.

        Args:
            prompts_dir: Directory containing prompts
        """
        self.prompts_dir = prompts_dir
        self.logger = LoggerMixin().logger

    def list_prompts(self) -> list[str]:
        """
        List all available prompts.

        Returns:
            List of prompt names (without extensions)
        """
        if not self.prompts_dir.exists():
            return []

        prompts = [
            p.stem
            for p in self.prompts_dir.glob("*.md")
            if p.is_file()
        ]

        return sorted(prompts)

    def prompt_exists(self, prompt_name: str) -> bool:
        """
        Check if prompt exists.

        Args:
            prompt_name: Name of the prompt

        Returns:
            True if prompt exists
        """
        prompt_path = self.prompts_dir / f"{prompt_name}.md"
        return prompt_path.exists()
