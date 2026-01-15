import importlib

ig = importlib.import_module('src.green_agent.agent.guardrails.input_guardrails')
og = importlib.import_module('src.green_agent.agent.guardrails.output_guardrails')

print('input.validate type', type(ig.validate_evaluation_request))
print('input.decorated type', type(ig.validate_evaluation_request_guardrail))
print('input.decorated has run_in_parallel', hasattr(ig.validate_evaluation_request_guardrail,'run_in_parallel'))
print('output.validate type', type(og.validate_evaluation_artifact))
print('output.decorated type', type(og.validate_evaluation_artifact_guardrail))
print('output.decorated has run_in_parallel', hasattr(og.validate_evaluation_artifact_guardrail,'run_in_parallel'))
