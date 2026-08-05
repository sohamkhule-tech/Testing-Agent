#!/usr/bin/env python3
"""
Quick script to add issue_type to all IRValidationIssue creations.
"""

import re
from pathlib import Path

validator_file = Path(__file__).parent.parent / "app" / "core" / "ir" / "ir_validator.py"
content = validator_file.read_text(encoding="utf-8")

# Define replacements: (pattern_to_match, issue_type_to_add)
replacements = [
    # Duplicate page ID
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="page",\s+component_id=page\.page_id,\s+)(message=f"Duplicate page ID)',
     r'\1issue_type="duplicate_id",\n                        \2'),
    
    # Duplicate element ID
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="element",\s+component_id=element\.id,\s+)(message=f"Duplicate element ID)',
     r'\1issue_type="duplicate_id",\n                            \2'),
    
    # Invalid locator strategy
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="element",\s+component_id=element\.id,\s+)(message=f"Invalid locator strategy)',
     r'\1issue_type="invalid_locator_strategy",\n                            \2'),
    
    # Locator preference warning
    (r'(IRValidationIssue\(\s+severity="warning",\s+component_type="element",\s+component_id=element\.id,\s+)(message=f"Using \{element\.locator_strategy\})',
     r'\1issue_type="locator_preference",\n                            \2'),
    
    # Empty locator value
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="element",\s+component_id=element\.id,\s+)(message="Empty locator value")',
     r'\1issue_type="empty_locator",\n                            \2'),
    
    # Duplicate module ID
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="module",\s+component_id=module\.module_id,\s+)(message=f"Duplicate module ID)',
     r'\1issue_type="duplicate_id",\n                        \2'),
    
    # Module references non-existent page
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="module",\s+component_id=module\.module_id,\s+)(message=f"Module references non-existent page)',
     r'\1issue_type="broken_reference",\n                            \2'),
    
    # Duplicate flow ID
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Duplicate flow ID)',
     r'\1issue_type="duplicate_id",\n                            \2'),
    
    # Flow has no steps
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message="Flow has no steps")',
     r'\1issue_type="missing_steps",\n                            \2'),
    
    # Invalid action type
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Invalid action type)',
     r'\1issue_type="invalid_action_type",\n                                    \2'),
    
    # Action references non-existent element
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Action references non-existent element)',
     r'\1issue_type="broken_reference",\n                                    \2'),
    
    # Action has no value (warning)
    (r'(IRValidationIssue\(\s+severity="warning",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Action \{action\.action_type\}.*? has no value")',
     r'\1issue_type="missing_value",\n                                    \2'),
    
    # Invalid assertion type
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Invalid assertion type)',
     r'\1issue_type="invalid_assertion_type",\n                                    \2'),
    
    # Assertion references non-existent element
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message=f"Assertion references non-existent element)',
     r'\1issue_type="broken_reference",\n                                    \2'),
    
    # Flow has no assertions (warning)
    (r'(IRValidationIssue\(\s+severity="warning",\s+component_type="flow",\s+component_id=flow\.flow_id,\s+)(message="Flow has no assertions")',
     r'\1issue_type="missing_assertions",\n                            \2'),
    
    # Dependency issues
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="dependency",\s+component_id=dep\.dependency_id,\s+)(message=f"Dependency .*? not found)',
     r'\1issue_type="broken_reference",\n                        \2'),
    
    # Circular dependency
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="dependency",\s+component_id=node,\s+)(message=f"Circular dependency)',
     r'\1issue_type="circular_dependency",\n                            \2'),
    
    # Common element issues
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="common_element",\s+component_id=element\.id,\s+)(message=f"Duplicate common element ID)',
     r'\1issue_type="duplicate_id",\n                        \2'),
    
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="common_element",\s+component_id=element\.id,\s+)(message=f"Invalid locator strategy)',
     r'\1issue_type="invalid_locator_strategy",\n                        \2'),
    
    # Common flow issues
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="common_flow",\s+component_id=flow\.flow_id,\s+)(message=f"Duplicate common flow ID)',
     r'\1issue_type="duplicate_id",\n                        \2'),
    
    (r'(IRValidationIssue\(\s+severity="warning",\s+component_type="common_flow",\s+component_id=flow\.flow_id,\s+)(message="Common flow has no steps")',
     r'\1issue_type="missing_steps",\n                        \2'),
    
    (r'(IRValidationIssue\(\s+severity="error",\s+component_type="common_flow",\s+component_id=flow\.flow_id,\s+)(message=f"Action references non-existent element)',
     r'\1issue_type="broken_reference",\n                                \2'),
]

# Apply replacements
for pattern, replacement in replacements:
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

# Write back
validator_file.write_text(content, encoding="utf-8")
print(f"✅ Fixed {len(replacements)} IRValidationIssue patterns in {validator_file}")
