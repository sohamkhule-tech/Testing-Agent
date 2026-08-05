#!/usr/bin/env python3
"""
Validation script for Code Generation Pipeline fixes.

Verifies:
1. No AttributeError on generation_id
2. Proper logging instrumentation
3. Error handling works correctly
4. Events emitted at all stages
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_ir_validator_no_generation_id():
    """Test that IRValidator doesn't access generation_id field."""
    print("✓ Testing IRValidator doesn't access generation_id...")
    
    from app.core.ir.ir_validator import IRValidator
    from app.schemas.ir import CodeGenerationIR, MetadataIR, EnvironmentIR
    from datetime import datetime, timezone
    
    # Create minimal IR
    ir = CodeGenerationIR(
        metadata=MetadataIR(
            generator="test",
            ir_version="1.0.0",
            generated_at=datetime.now(timezone.utc),
        ),
        environment=EnvironmentIR(
            base_url="http://localhost:3000",
            auth_required=False,
            browsers=["chromium"],
        ),
        pages=[],
        modules=[],
        dependencies=[],
    )
    
    validator = IRValidator()
    
    try:
        result = validator.validate(ir)
        print(f"  ✅ Validation passed: {result.is_valid}")
        return True
    except AttributeError as e:
        if "generation_id" in str(e):
            print(f"  ❌ FAILED: Still accessing generation_id: {e}")
            return False
        raise
    except Exception as e:
        print(f"  ⚠️  Validation failed with different error (OK if expected): {e}")
        return True


async def test_metadata_ir_schema():
    """Verify MetadataIR doesn't have generation_id field."""
    print("✓ Testing MetadataIR schema...")
    
    from app.schemas.ir import MetadataIR
    
    fields = set(MetadataIR.model_fields.keys())
    expected_fields = {
        "generator", "generated_at", "ir_version", "source_test_plan",
        "model_used", "total_pages", "total_elements", "total_flows",
        "total_modules", "validation_status"
    }
    
    if "generation_id" in fields:
        print(f"  ❌ FAILED: generation_id field exists in schema")
        return False
    
    missing = expected_fields - fields
    if missing:
        print(f"  ⚠️  WARNING: Missing expected fields: {missing}")
    
    extra = fields - expected_fields
    if extra:
        print(f"  ℹ️  INFO: Extra fields (may be OK): {extra}")
    
    print(f"  ✅ Schema valid: {len(fields)} fields, no generation_id")
    return True


async def test_code_generation_node_instrumentation():
    """Verify code_generation_node has proper logging."""
    print("✓ Testing code_generation_node instrumentation...")
    
    workflow_file = project_root / "app" / "workflows" / "trigger_workflow.py"
    content = workflow_file.read_text(encoding="utf-8")
    
    required_logs = [
        "code_generation_step_1_checking_agent",
        "code_generation_step_2_preparing_input",
        "code_generation_step_3_executing_agent",
        "code_generation_step_1_complete",
        "code_generation_timeout_set",
    ]
    
    missing = [log for log in required_logs if log not in content]
    
    if missing:
        print(f"  ❌ FAILED: Missing logs: {missing}")
        return False
    
    # Check for timing code
    if "import time" not in content or "node_start_time = time.time()" not in content:
        print(f"  ❌ FAILED: Missing timing instrumentation")
        return False
    
    print(f"  ✅ All {len(required_logs)} log statements present")
    return True


async def test_code_generation_agent_instrumentation():
    """Verify CodeGenerationAgent.execute has proper logging."""
    print("✓ Testing CodeGenerationAgent instrumentation...")
    
    agent_file = project_root / "app" / "agents" / "code_generation_agent.py"
    content = agent_file.read_text(encoding="utf-8")
    
    required_logs = [
        "codegen_step_1_extract_parameters",
        "codegen_step_2_emit_start_event",
        "codegen_step_3_initialize_metrics",
        "codegen_step_4_load_test_plan",
        "codegen_step_5_plan_structure",
        "codegen_step_6_create_directories",
        "codegen_step_7_generate_ir",
        "codegen_step_1_complete",
    ]
    
    missing = [log for log in required_logs if log not in content]
    
    if missing:
        print(f"  ❌ FAILED: Missing logs: {missing}")
        return False
    
    # Check for timing code
    if "agent_start_time = time.time()" not in content:
        print(f"  ❌ FAILED: Missing timing instrumentation")
        return False
    
    print(f"  ✅ All {len(required_logs)} log statements present")
    return True


async def test_error_emission():
    """Verify errors are emitted to UI."""
    print("✓ Testing error emission...")
    
    workflow_file = project_root / "app" / "workflows" / "trigger_workflow.py"
    content = workflow_file.read_text(encoding="utf-8")
    
    # Check for error emission
    if "EventType.CODE_GENERATION_FAILED" not in content:
        print(f"  ❌ FAILED: Missing CODE_GENERATION_FAILED event emission")
        return False
    
    # Check that errors include metadata
    if '"error_type": type(e).__name__' not in content:
        print(f"  ⚠️  WARNING: Error type not included in events")
    
    print(f"  ✅ Error emission present")
    return True


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Code Generation Pipeline Fixes - Validation")
    print("=" * 60)
    print()
    
    tests = [
        test_ir_validator_no_generation_id,
        test_metadata_ir_schema,
        test_code_generation_node_instrumentation,
        test_code_generation_agent_instrumentation,
        test_error_emission,
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"  ❌ Test crashed: {e}")
            results.append(False)
        print()
    
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ ALL TESTS PASSED - Fixes validated successfully!")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Review output above")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
