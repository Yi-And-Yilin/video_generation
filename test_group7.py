import sys, os

# Test Group 7: main_ui.py - bridge integration
with open(r'C:\SimpleAIHelper\video_generation\main_ui.py', 'r', encoding='utf-8') as f:
    source = f.read()

assert 'new_tab_last_job_id' in source, 'new_tab_last_job_id NOT found'
print('PASS: new_tab_last_job_id attribute exists')

assert 'def new_tab_run_ltx_video_generation' in source, 'new_tab_run_ltx_video_generation NOT found'
print('PASS: new_tab_run_ltx_video_generation method exists')

assert 'new_tab_task_to_ltx_batch_tasks' in source, 'new_tab_task_to_ltx_batch_tasks NOT imported'
print('PASS: new_tab_task_to_ltx_batch_tasks imported in main_ui')

assert 'BatchRunner' in source, 'BatchRunner NOT imported'
print('PASS: BatchRunner imported in main_ui')
