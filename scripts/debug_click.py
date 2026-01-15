from src.green_agent.environment.session_manager import SessionManager
from src.green_agent.environment.entities import EnvironmentConfig
import os
import time

# Ensure dataset path is set
os.environ.setdefault('MINIWOB_URL', 'file:///E:/Maaz/Projects/weag/benchmarks/miniwob/html/')

sm = SessionManager()
config = EnvironmentConfig(task_id='miniwob.click-test', max_steps=50, seed=42)
print('Creating session...')
session = sm.create_session(config)
print('Session created:', session.session_id)
print('Initial observation keys:', list(session.current_observation.keys()))
print('Focused element bid:', session.current_observation.get('focused_element_bid'))
print('Sample extra_element_properties keys:', list(session.current_observation.get('extra_element_properties', {}) )[:10])
# Print a small slice of the DOM to inspect element ids
dom = session.current_observation.get('dom_object', '')
if isinstance(dom, str):
	print('DOM snippet (first 2000 chars):\n', dom[:2000])

axt = session.current_observation.get('axtree_object')
print('AXTree object type:', type(axt))
try:
	import json as _json
	print('AXTree (summary):', _json.dumps(axt)[:2000])
except Exception:
	pass
if isinstance(axt, dict):
	print('\nScanning AXTree nodes for button-like nodes:')
	for node in axt.get('nodes', [])[:200]:
		role = node.get('role', {}).get('value') if isinstance(node.get('role'), dict) else node.get('role')
		name = node.get('name', {}).get('value') if isinstance(node.get('name'), dict) else node.get('name')
		bgid = node.get('browsergym_id') or node.get('backendDOMNodeId')
		if role and 'button' in str(role).lower() or (isinstance(name, str) and 'click' in name.lower() or 'button' in (name or '').lower()):
			print('  node browsergym_id:', bgid, 'role:', role, 'name:', name)

# Give page a moment
time.sleep(1)

print("Stepping: click('subbtn')")
obs, reward, done, truncated, info = session.env_instance.step("click('subbtn')")
print('Step result - reward:', reward, 'done:', done, 'truncated:', truncated)
print('Info:', info)
print('Observation keys after step:', list(obs.keys()))
print('Focused element bid after step:', obs.get('focused_element_bid'))
props = obs.get('extra_element_properties') or {}
print('Extra element properties sample count:', len(props))
# Find element whose DOM id == 'subbtn'
found = None
for bid, pdata in props.items():
	try:
		# pdata may be a dict with 'attributes' mapping
		attrs = pdata.get('attributes', {}) if isinstance(pdata, dict) else {}
		if attrs.get('id') == 'subbtn':
			found = bid
			print('Found bid for DOM id subbtn ->', bid)
			break
	except Exception:
		continue
if not found:
	print('Did not find bid for id=subbtn in extra_element_properties')
    
# Try clicking several candidate bids discovered in AXTree scan
candidates = []
if isinstance(axt, dict):
	for node in axt.get('nodes', [])[:200]:
		role = node.get('role', {}).get('value') if isinstance(node.get('role'), dict) else node.get('role')
		bgid = node.get('browsergym_id')
		if role and 'button' in str(role).lower():
			candidates.append(bgid)

print('Candidate button bids to try:', candidates)

for b in candidates[:3]:
	if not b:
		continue
	print(f"Trying click on bid {b}")
	obs2, reward2, done2, trunc2, info2 = session.env_instance.step(f"click('{b}')")
	print('Result:', reward2, done2, trunc2)
	if reward2 > 0 or done2:
		print('Success with bid', b)
		break

# Cleanup
sm.cleanup_session(session.session_id)
print('Cleaned up')
