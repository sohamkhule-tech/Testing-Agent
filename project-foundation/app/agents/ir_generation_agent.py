"""
IR Generation Agent

Generates framework-independent Intermediate Representation from approved test plans using LLM.
"""

import json
from datetime import datetime
from typing import Any

import asyncio

from app.core.event_bus import EventType, emit
from app.core.interfaces import ILLMClient
from app.core.ir.dependency_graph_builder import DependencyGraphBuilder
from app.core.ir.ir_pre_validator import IRAutoRepairer, IRPreValidator
from app.core.ir.ir_validator import IRValidator
from app.core.ir.prompt_composer import PromptComposer
from app.exceptions import AgentExecutionError
from app.logging import LoggerMixin
from app.schemas.ir import CodeGenerationIR, IRValidationResult
from app.schemas.review import ApprovedTestPlan


async def _emit(run_id: str | None, event_type: str, data: dict[str, Any]) -> None:
    if not run_id:
        return
    await emit(run_id, event_type, data)


class IRGenerationAgent(LoggerMixin):
    """
    IR Generation Agent.
    
    Generates IR from approved test plans using LLM.
    Validates and refines IR until acceptable.
    """

    def __init__(self, llm_client: ILLMClient, max_refinement_attempts: int = 3) -> None:
        """
        Initialize IR generation agent.

        Args:
            llm_client: LLM client
            max_refinement_attempts: Maximum refinement attempts
        """
        super().__init__()
        self.llm_client = llm_client
        self.max_refinement_attempts = max_refinement_attempts
        self.run_id: str | None = None
        
        self.prompt_composer = PromptComposer()
        self.validator = IRValidator()
        self.graph_builder = DependencyGraphBuilder()
        self.pre_validator = IRPreValidator()
        self.auto_repairer = IRAutoRepairer()

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute IR generation.

        Args:
            input_data: Input containing:
                - approved_test_plan: ApprovedTestPlan object
                - base_url: Application base URL

        Returns:
            Dictionary containing:
                - ir: CodeGenerationIR object
                - validation_result: IRValidationResult
                - dependency_graph: DependencyGraph
                - refinement_attempts: Number of refinement attempts
                - success: Whether generation succeeded

        Raises:
            AgentExecutionError: If IR generation fails
        """
        self.logger.info("ir_generation_started")
        await _emit(self.run_id, EventType.IR_GENERATION_STARTED, {"label": "Generating intermediate representation"})

        try:
            approved_plan: ApprovedTestPlan = input_data["approved_test_plan"]
            base_url: str = input_data.get("base_url", "http://localhost:3000")

            # Generate initial IR
            ir = await self._generate_ir(approved_plan, base_url)

            # Validate and refine IR
            validation_result, refinement_attempts = await self._validate_and_refine_ir(
                ir, approved_plan, base_url
            )

            if not validation_result.is_valid:
                raise AgentExecutionError(
                    f"IR validation failed after {refinement_attempts} attempts. "
                    f"Errors: {validation_result.error_count}"
                )

            # Build dependency graph
            dependency_graph = self.graph_builder.build_graph(ir)

            self.logger.info(
                "ir_generation_completed",
                refinement_attempts=refinement_attempts,
                error_count=validation_result.error_count,
                warning_count=validation_result.warning_count
            )

            await _emit(self.run_id, EventType.IR_GENERATED, {
                "pages": len(ir.pages),
                "modules": len(ir.modules),
                "flows": sum(len(m.flows) for m in ir.modules),
                "refinement_attempts": refinement_attempts,
            })

            return {
                "ir": ir,
                "validation_result": validation_result,
                "dependency_graph": dependency_graph,
                "refinement_attempts": refinement_attempts,
                "success": True,
            }

        except Exception as e:
            self.logger.error("ir_generation_failed", error=str(e))
            raise AgentExecutionError(f"IR generation failed: {str(e)}") from e

    async def _generate_ir(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str
    ) -> CodeGenerationIR:
        """
        Generate IR using LLM.

        Args:
            approved_plan: Approved test plan
            base_url: Application base URL

        Returns:
            Generated IR
        """
        self.logger.info("generating_initial_ir")

        # Compose prompt
        prompt = self.prompt_composer.compose_ir_generation_prompt(
            approved_plan, base_url
        )
        
        prompt_tokens = len(prompt.split())  # Rough estimate

        await _emit(self.run_id, EventType.PROMPTS_PREPARED, {
            "purpose": "generate_intermediate_representation",
            "prompt_length": len(prompt),
            "estimated_prompt_tokens": prompt_tokens,
            "label": "Prompts prepared for IR generation",
        })

        # Log detailed request information
        self.logger.info(
            "llm_request_prepared",
            model=self.llm_client.model,
            prompt_length=len(prompt),
            estimated_tokens=prompt_tokens,
            max_tokens=self.llm_client.default_max_tokens,
        )
        
        await _emit(self.run_id, EventType.SENDING_LLM_REQUEST, {
            "purpose": "generate_intermediate_representation",
            "prompt_length": len(prompt),
            "estimated_prompt_tokens": prompt_tokens,
            "model": self.llm_client.model,
            "max_tokens": self.llm_client.default_max_tokens,
            "temperature": 0.3,
            "label": f"Sending request to {self.llm_client.model}...",
        })

        await _emit(self.run_id, EventType.LLM_CALL_STARTED, {
            "purpose": "Generate Playwright IR Code",
            "model": self.llm_client.model,
            "prompt_tokens": prompt_tokens,
            "label": f"Calling {self.llm_client.model} for IR Generation",
        })

        ir = await self._complete_and_parse_ir(prompt, prompt_tokens)

        self.logger.info("initial_ir_generated")
        return ir

    MAX_JSON_RETRIES = 3

    async def _complete_and_parse_ir(self, prompt: str, prompt_tokens: int) -> CodeGenerationIR:
        """Call the LLM and parse its IR JSON output, retrying on malformed JSON.

        Smaller models occasionally emit invalid JSON on long, exhaustive IR
        generations. A single bad response must not hard-fail the run, so the
        call is retried a bounded number of times — with a slightly higher
        temperature on each retry so the regenerated output differs. The raw
        response is never logged; only parse status is.
        """
        import time
        last_error = ""
        for attempt in range(1, self.MAX_JSON_RETRIES + 1):
            await _emit(self.run_id, EventType.WAITING_FOR_LLM_RESPONSE, {
                "label": f"Waiting for {self.llm_client.model} response...",
                "model": self.llm_client.model,
                "estimated_prompt_tokens": prompt_tokens,
                "status": "generating",
            })

            llm_call_start = time.time()
            self.logger.info(
                "llm_call_started",
                model=self.llm_client.model,
                prompt_length=len(prompt),
                estimated_tokens=prompt_tokens,
                max_tokens=self.llm_client.default_max_tokens,
                temperature=0.3,
                timestamp=llm_call_start,
            )

            # Double-layer timeout protection: even if AsyncOpenAI client hangs,
            # this outer timeout will fire
            from app.config import get_settings
            settings = get_settings()
            # Add 60s buffer beyond the client's internal timeout
            outer_timeout = settings.llm.openai_timeout + 60
            self.logger.info(
                "llm_call_initiating",
                outer_timeout=outer_timeout,
                client_timeout=settings.llm.openai_timeout,
            )

            try:
                response = await asyncio.wait_for(
                    self.llm_client.complete(
                        prompt=prompt,
                        max_tokens=self.llm_client.default_max_tokens,
                        temperature=0.3 + (0.2 * (attempt - 1)),
                    ),
                    timeout=outer_timeout,
                )
            except asyncio.TimeoutError as timeout_err:
                llm_call_duration = time.time() - llm_call_start
                error_msg = f"LLM call timed out after {llm_call_duration:.1f}s (limit: {outer_timeout}s)"
                self.logger.error(
                    "llm_call_timeout",
                    duration=llm_call_duration,
                    timeout_limit=outer_timeout,
                    model=self.llm_client.model,
                )
                await _emit(self.run_id, EventType.LLM_TIMEOUT, {
                    "error": error_msg,
                    "duration_seconds": llm_call_duration,
                    "timeout_seconds": outer_timeout,
                    "model": self.llm_client.model,
                    "label": "LLM request timed out",
                })
                raise AgentExecutionError(error_msg) from timeout_err
            except Exception as llm_err:
                llm_call_duration = time.time() - llm_call_start
                error_msg = f"LLM call failed: {str(llm_err)}"
                self.logger.error(
                    "llm_call_failed",
                    duration=llm_call_duration,
                    error=str(llm_err),
                    error_type=type(llm_err).__name__,
                    model=self.llm_client.model,
                )
                await _emit(self.run_id, EventType.LLM_ERROR, {
                    "error": str(llm_err),
                    "error_type": type(llm_err).__name__,
                    "duration_seconds": llm_call_duration,
                    "model": self.llm_client.model,
                    "label": f"LLM error: {type(llm_err).__name__}",
                })
                raise AgentExecutionError(error_msg) from llm_err

            llm_call_duration = time.time() - llm_call_start
            response_tokens = len(response.split()) if response else 0
            self.logger.info(
                "llm_call_completed",
                duration=llm_call_duration,
                response_length=len(response) if response else 0,
                estimated_completion_tokens=response_tokens,
            )
            await _emit(self.run_id, EventType.RECEIVED_LLM_RESPONSE, {
                "model": self.llm_client.model,
                "response_length": len(response) if response else 0,
                "estimated_prompt_tokens": prompt_tokens,
                "estimated_completion_tokens": response_tokens,
                "estimated_total_tokens": prompt_tokens + response_tokens,
                "duration_seconds": llm_call_duration,
                "label": f"Model response received ({llm_call_duration:.1f}s)",
            })
            await _emit(self.run_id, EventType.LLM_CALL_COMPLETED, {
                "model": self.llm_client.model,
                "response_tokens": response_tokens,
                "duration_seconds": llm_call_duration,
                "label": "LLM generation complete",
            })

            await _emit(self.run_id, EventType.PARSING_RESPONSE, {
                "label": "Parsing JSON response...",
                "status": "parsing",
            })

            try:
                ir = await self._parse_ir_response(response)
            except AgentExecutionError as e:
                last_error = str(e)
                self.logger.warning(
                    "ir_json_retry",
                    attempt=attempt,
                    max_attempts=self.MAX_JSON_RETRIES,
                    error=last_error,
                )
                if attempt < self.MAX_JSON_RETRIES:
                    await asyncio.sleep(0.5 * attempt)
                continue

            await _emit(self.run_id, EventType.JSON_PARSED, {
                "label": "JSON parsed successfully",
                "pages": len(ir.pages),
                "modules": len(ir.modules),
            })
            return ir

        raise AgentExecutionError(
            f"LLM returned invalid IR JSON after {self.MAX_JSON_RETRIES} attempts: {last_error}"
        )

    async def _parse_ir_response(self, response: str) -> CodeGenerationIR:
        """
        Parse LLM response into CodeGenerationIR with pre-validation and auto-repair.
        
        Steps:
        1. Extract JSON from response
        2. Parse JSON
        3. Pre-validate (check required fields exist)
        4. Auto-repair (fix common issues)
        5. Construct Pydantic model
        
        Args:
            response: LLM response text
            
        Returns:
            Parsed and validated IR
            
        Raises:
            AgentExecutionError: If parsing fails after all repair attempts
        """
        try:
            # Step 1: Extract JSON
            json_str = self._extract_json(response)
            
            # Step 2: Parse JSON
            ir_data = json.loads(json_str, strict=False)
            
            # Step 3: Pre-validate
            await _emit(self.run_id, EventType.IR_VALIDATION_STARTED, {
                "label": "Validating IR schema...",
                "validation_type": "pre_validation",
            })
            
            is_valid, errors, warnings = self.pre_validator.validate(ir_data)
            
            if warnings:
                for warning in warnings:
                    self.logger.warning("ir_pre_validation_warning", message=warning)
            
            # Step 4: Auto-repair if needed
            if not is_valid:
                self.logger.warning(
                    "ir_pre_validation_failed_attempting_repair",
                    error_count=len(errors)
                )
                for error in errors:
                    self.logger.error("ir_pre_validation_error", message=error)
                
                await _emit(self.run_id, EventType.IR_AUTO_REPAIR_STARTED, {
                    "label": "Auto-repairing IR issues...",
                    "error_count": len(errors),
                })
                
                # Attempt auto-repair
                ir_data = self.auto_repairer.repair(ir_data)
                
                if self.auto_repairer.repairs_made:
                    self.logger.info(
                        "ir_auto_repaired",
                        repairs=self.auto_repairer.repairs_made
                    )
                    
                    await _emit(self.run_id, EventType.IR_AUTO_REPAIR_SUCCESS, {
                        "label": "IR auto-repaired successfully",
                        "repairs_count": len(self.auto_repairer.repairs_made),
                        "repairs": self.auto_repairer.repairs_made,
                    })
                
                # Re-validate after repair
                is_valid, errors, _ = self.pre_validator.validate(ir_data)
                
                if not is_valid:
                    # Still invalid after repair - log detailed report
                    error_report = self._format_validation_error_report(errors)
                    self.logger.error("ir_validation_failed_after_repair", report=error_report)
                    
                    await _emit(self.run_id, EventType.IR_VALIDATION_FAILED, {
                        "label": "IR validation failed",
                        "error_count": len(errors),
                        "errors": errors[:10],  # First 10 errors
                    })
                    
                    raise AgentExecutionError(
                        f"IR validation failed after auto-repair. Errors:\n{error_report}"
                    )
                else:
                    await _emit(self.run_id, EventType.IR_VALIDATION_SUCCESS, {
                        "label": "IR validation successful after repair",
                    })
            else:
                await _emit(self.run_id, EventType.IR_VALIDATION_SUCCESS, {
                    "label": "IR validation successful",
                })
            
            # Step 5: Normalize and construct Pydantic model
            ir_data = self._normalize_ir_data(ir_data)
            ir = CodeGenerationIR(**ir_data)
            
            self.logger.info("ir_parsed_successfully")
            return ir

        except json.JSONDecodeError as e:
            # JSON syntax error - attempt repair
            self.logger.error("json_parse_error", error=str(e))
            
            json_str = self._extract_json(response)
            json_str = self._repair_json(json_str)
            
            try:
                ir_data = json.loads(json_str, strict=False)
                ir_data = self.auto_repairer.repair(ir_data)
                ir_data = self._normalize_ir_data(ir_data)
                ir = CodeGenerationIR(**ir_data)
                self.logger.info("ir_json_repaired_and_parsed")
                return ir
            except Exception as repair_error:
                self.logger.error("json_repair_failed", error=str(repair_error))
                raise AgentExecutionError(
                    f"Failed to parse IR JSON even after repair. Original error: {str(e)}, Repair error: {str(repair_error)}"
                ) from e

        except Exception as e:
            self.logger.error("ir_parse_error", error=str(e))
            
            # If it's a Pydantic validation error, provide detailed report
            if "validation error" in str(e).lower():
                error_report = self._format_pydantic_error(e)
                self.logger.error("pydantic_validation_failed", report=error_report)
                raise AgentExecutionError(
                    f"IR Pydantic validation failed:\n{error_report}"
                ) from e
            
            raise AgentExecutionError(f"Failed to parse IR: {str(e)}") from e

    def _format_validation_error_report(self, errors: list[str]) -> str:
        """Format pre-validation errors into readable report."""
        report_lines = [
            "IR Pre-Validation Failed",
            "=" * 60,
            f"Total Errors: {len(errors)}",
            "",
            "Errors:"
        ]
        
        for idx, error in enumerate(errors, 1):
            report_lines.append(f"  {idx}. {error}")
        
        report_lines.extend([
            "",
            "This indicates the LLM response did not match the required IR schema.",
            "The prompt may need to be updated to include these fields."
        ])
        
        return "\n".join(report_lines)

    def _format_pydantic_error(self, error: Exception) -> str:
        """Format Pydantic validation error into readable report."""
        error_str = str(error)
        
        report_lines = [
            "IR Pydantic Validation Failed",
            "=" * 60,
            "",
            "Pydantic reported the following validation errors:",
            "",
            error_str,
            "",
            "Common Causes:",
            "  1. Missing required fields (metadata.generator, dependencies[].source_id, etc.)",
            "  2. Wrong field types (string instead of int, etc.)",
            "  3. Invalid enum values (action_type, assertion_type)",
            "  4. Null values for required fields",
            "",
            "Fix: Update the IR generation prompt to include ALL required fields."
        ]
        
        return "\n".join(report_lines)

    @staticmethod
    def _repair_json(text: str) -> str:
        import re as _re
        text = text.strip()
        text = _re.sub(r"```json\s*", "", text)
        text = _re.sub(r"```\s*", "", text)

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1:
            if last_brace == -1 or last_brace < first_brace:
                open_braces = text.count("{") - text.count("}")
                open_brackets = text.count("[") - text.count("]")
                text = text[first_brace:].rstrip(", \t\n\r")
                text += "}" * max(open_braces, 0) + "]" * max(open_brackets, 0)
            elif last_brace > first_brace:
                text = text[first_brace:last_brace + 1]

        # Fix trailing commas
        text = _re.sub(r",\s*([}\]])", r"\1", text)

        try:
            json.loads(text, strict=False)
            return text
        except Exception:
            pass

        # Fix unquoted keys
        text = _re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', text)
        text = _re.sub(r",\s*([}\]])", r"\1", text)

        try:
            json.loads(text, strict=False)
            return text
        except Exception:
            pass

        # Fix single-quoted string values (only where safe)
        text = _re.sub(r":\s+'([^'\n]*)'\s*([,}\]])", r': "\1"\2', text)
        try:
            json.loads(text, strict=False)
            return text
        except Exception:
            pass

        return text

    @staticmethod
    def _normalize_ir_data(data: dict) -> dict:
        for dep in data.get("dependencies", []) or []:
            if isinstance(dep, dict):
                if "from" in dep and "source_id" not in dep:
                    dep["source_id"] = dep.pop("from")
                if "to" in dep and "target_id" not in dep:
                    dep["target_id"] = dep.pop("to")
                if "dependency_type" not in dep:
                    dep["dependency_type"] = "requires"

        elements = data.get("common_elements", []) or []
        data["common_elements"] = [
            {"id": e, "name": e, "locator_strategy": "testId", "locator_value": e}
            if isinstance(e, str) else e
            for e in elements
        ]

        def _normalize_element(el: dict) -> dict:
            if "element_ref" in el and "id" not in el:
                ref = str(el.pop("element_ref")).strip()
                el["id"] = ref
                el.setdefault("name", ref.replace("-", " ").title())
                el.setdefault("locator_strategy", "testId")
                el.setdefault("locator_value", ref)
            return el

        def _normalize_elements(elements_list: list) -> list:
            result = []
            for el in elements_list:
                if isinstance(el, dict):
                    result.append(_normalize_element(el))
                elif isinstance(el, str):
                    result.append({"id": el, "name": el, "locator_strategy": "testId", "locator_value": el})
                else:
                    result.append(el)
            return result

        for page in data.get("pages", []) or []:
            if "description" not in page:
                page["description"] = page.get("name", "")
            if "elements" in page:
                page["elements"] = _normalize_elements(page["elements"])

        if "common_elements" in data:
            data["common_elements"] = _normalize_elements(data["common_elements"])

        VALID_ACTIONS = {"click", "fill", "select", "check", "uncheck", "hover",
                         "focus", "press", "upload", "clear", "doubleClick", "rightClick"}
        VALID_ASSERTIONS = {"toBeVisible", "toBeHidden", "toBeEnabled", "toBeDisabled",
                           "toBeChecked", "toBeUnchecked", "toHaveText", "toHaveValue",
                           "toHaveURL", "toHaveTitle", "toHaveCount", "toContainText"}

        def _normalize_flow(flow: dict) -> None:
            for step in flow.get("steps", []) or []:
                nav = step.get("navigation")
                if isinstance(nav, dict) and "description" not in nav:
                    nav["description"] = f"Navigate to {nav.get('target', '')}"
                actions = step.get("actions") or []
                step["actions"] = [a for a in actions if isinstance(a, dict) and a.get("action_type") in VALID_ACTIONS]
                assertions = step.get("assertions") or []
                step["assertions"] = [a for a in assertions if isinstance(a, dict) and a.get("assertion_type") in VALID_ASSERTIONS]
                wfc = step.get("wait_for_condition")
                if isinstance(wfc, dict):
                    step["wait_for_condition"] = wfc.get("value") or wfc.get("description") or str(wfc)
                elif wfc is not None and not isinstance(wfc, str):
                    step["wait_for_condition"] = str(wfc)

        for mod in data.get("modules", []) or []:
            if "description" not in mod:
                mod["description"] = mod.get("name", "")
            for flow in mod.get("flows", []) or []:
                _normalize_flow(flow)

        for flow in data.get("common_flows", []) or []:
            _normalize_flow(flow)

        if "metadata" not in data:
            data["metadata"] = {"generator": "llm", "ir_version": "1.0",
                "generated_at": datetime.utcnow().isoformat() + "Z", "model_used": "deepseek-v4-flash-free"}

        env = data.get("environment", {})
        if isinstance(env, dict):
            tos = env.get("timeouts", {})
            if isinstance(tos, dict):
                for k in list(tos.keys()):
                    v = tos.get(k)
                    if isinstance(v, str) and not v.isdigit():
                        tos[k] = 30000

        return data

    def _extract_json(self, response: str) -> str:
        """
        Extract JSON from LLM response.

        Args:
            response: LLM response

        Returns:
            Extracted JSON string
        """
        # Look for JSON block in markdown
        if "```json" in response:
            start = response.index("```json") + 7
            try:
                end = response.index("```", start)
            except ValueError:
                end = len(response)
            return response[start:end].strip()
        
        # Look for plain JSON block
        if "```" in response:
            start = response.index("```") + 3
            try:
                end = response.index("```", start)
            except ValueError:
                end = len(response)
            return response[start:end].strip()
        
        # Try to find JSON object
        if "{" in response and "}" in response:
            start = response.index("{")
            end = response.rindex("}") + 1
            return response[start:end]
        
        # Return as is
        return response.strip()

    async def _validate_and_refine_ir(
        self,
        ir: CodeGenerationIR,
        approved_plan: ApprovedTestPlan,
        base_url: str
    ) -> tuple[IRValidationResult, int]:
        """
        Validate IR and refine if needed.

        Args:
            ir: Initial IR
            approved_plan: Approved test plan
            base_url: Application base URL

        Returns:
            Tuple of (validation result, refinement attempts)
        """
        refinement_attempts = 0

        while refinement_attempts <= self.max_refinement_attempts:
            # Validate IR
            validation_result = self.validator.validate(ir)

            # If valid or only warnings, we're done
            if validation_result.is_valid:
                self.logger.info(
                    "ir_validation_passed",
                    attempts=refinement_attempts,
                    warnings=validation_result.warning_count
                )
                return validation_result, refinement_attempts

            # If max attempts reached, return current state
            if refinement_attempts >= self.max_refinement_attempts:
                self.logger.warning(
                    "max_refinement_attempts_reached",
                    errors=validation_result.error_count
                )
                return validation_result, refinement_attempts

            # Refine IR
            self.logger.info(
                "refining_ir",
                attempt=refinement_attempts + 1,
                errors=validation_result.error_count
            )

            ir = await self._refine_ir(ir, validation_result)
            refinement_attempts += 1

        return validation_result, refinement_attempts

    async def _refine_ir(
        self,
        ir: CodeGenerationIR,
        validation_result: IRValidationResult
    ) -> CodeGenerationIR:
        """
        Refine IR based on validation issues.

        Args:
            ir: Current IR
            validation_result: Validation result with issues

        Returns:
            Refined IR
        """
        # Compose refinement prompt
        prompt = self.prompt_composer.compose_ir_refinement_prompt(
            ir.model_dump(mode="json"),
            [issue.model_dump(mode="json") for issue in validation_result.issues]
        )

        await _emit(self.run_id, EventType.SENDING_LLM_REQUEST, {
            "purpose": "refine_intermediate_representation",
            "issue_count": validation_result.error_count + validation_result.warning_count,
            "prompt_length": len(prompt),
            "label": "Sending refinement request to LLM...",
        })

        # Call LLM with timeout protection and detailed logging
        import time
        llm_call_start = time.time()
        
        self.logger.info(
            "llm_refinement_call_started",
            model=self.llm_client.model,
            issue_count=validation_result.error_count + validation_result.warning_count,
            prompt_length=len(prompt),
        )
        
        await _emit(self.run_id, EventType.WAITING_FOR_LLM_RESPONSE, {
            "label": "Waiting for model refinement",
            "purpose": "refine_ir",
        })
        
        try:
            from app.config import get_settings
            settings = get_settings()
            outer_timeout = settings.llm.openai_timeout + 60
            
            response = await asyncio.wait_for(
                self.llm_client.complete(
                    prompt=prompt,
                    max_tokens=self.llm_client.default_max_tokens,
                    temperature=0.2,
                ),
                timeout=outer_timeout,
            )
            
            llm_call_duration = time.time() - llm_call_start
            
            self.logger.info(
                "llm_refinement_call_completed",
                duration=llm_call_duration,
                response_length=len(response) if response else 0,
            )
            
            await _emit(self.run_id, EventType.RECEIVED_LLM_RESPONSE, {
                "response_length": len(response) if response else 0,
                "duration_seconds": llm_call_duration,
                "label": f"Refinement response received ({llm_call_duration:.1f}s)",
            })
            
        except asyncio.TimeoutError as timeout_err:
            llm_call_duration = time.time() - llm_call_start
            error_msg = f"LLM refinement call timed out after {llm_call_duration:.1f}s"
            
            self.logger.error(
                "llm_refinement_timeout",
                duration=llm_call_duration,
                timeout_limit=outer_timeout,
            )
            
            await _emit(self.run_id, EventType.LLM_TIMEOUT, {
                "error": error_msg,
                "purpose": "refine_ir",
                "duration_seconds": llm_call_duration,
                "label": "LLM refinement timed out",
            })
            
            raise AgentExecutionError(error_msg) from timeout_err
            
        except Exception as llm_err:
            llm_call_duration = time.time() - llm_call_start
            error_msg = f"LLM refinement call failed: {str(llm_err)}"
            
            self.logger.error(
                "llm_refinement_failed",
                duration=llm_call_duration,
                error=str(llm_err),
                error_type=type(llm_err).__name__,
            )
            
            await _emit(self.run_id, EventType.LLM_ERROR, {
                "error": str(llm_err),
                "error_type": type(llm_err).__name__,
                "purpose": "refine_ir",
                "duration_seconds": llm_call_duration,
                "label": f"LLM refinement error: {type(llm_err).__name__}",
            })
            
            raise AgentExecutionError(error_msg) from llm_err

        # Parse refined IR
        await _emit(self.run_id, EventType.PARSING_RESPONSE, {"label": "Parsing refined model response"})
        refined_ir = await self._parse_ir_response(response)

        return refined_ir
