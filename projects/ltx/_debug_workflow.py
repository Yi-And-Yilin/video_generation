import sys
sys.path.insert(0, r'C:\SimpleAIHelper\video_generation\projects\ltx')
from workflow_generator import generate_api_workflow

wf = generate_api_workflow('ltx', 'video', 'ltx_preparation', work_id='test001', width=1280, height=720, length=241, prompt='test prompt')

print('=== UNRESOLVED inputs (with ** patterns) ===')
has_unresolved = False
for nid, node in sorted(wf.items()):
    inp = node.get('inputs', {})
    for k, v in inp.items():
        if isinstance(v, str) and '**' in v:
            print(f'  UNRESOLVED: Node {nid}: inputs[{k}] = {v}')
            has_unresolved = True
if not has_unresolved:
    print('  All inputs properly resolved!')

print()
print('=== Sample nodes ===')
for nid in ['2', '4', '16', '8', '24']:
    if nid in wf:
        node = wf[nid]
        title = node.get('_meta', {}).get('title', '')
        print(f'Node {nid}: class={node.get("class_type", "")}')
        print(f'  title: {title}')
        print(f'  inputs: {node.get("inputs", {})}')
        print()

print('=== Sample nodes from ltx_decode ===')
wf2 = generate_api_workflow('ltx', 'video', 'ltx_decode', work_id='test001')
for nid, node in sorted(wf2.items()):
    title = node.get('_meta', {}).get('title', '')
    inp = node.get('inputs', {})
    print(f'Node {nid}: class={node.get("class_type", "")}')
    print(f'  title: {title}')
    print(f'  inputs: {inp}')
    print()
