import pandas as pd
import random
import re

def parse_weighted_items(value):
    if pd.isna(value):
        return None

    # First handle {...} groups by temporarily replacing them
    temp_holder = {}
    counter = 0
    
    # Replace all {...} groups with temporary placeholders
    while True:
        brace_match = re.search(r'\{([^}]+)\}', value)
        if not brace_match:
            break
        temp_key = f'__TEMP_{counter}__'
        temp_holder[temp_key] = brace_match.group(1).replace(',', '|')
        value = value.replace(brace_match.group(0), temp_key)
        counter += 1

    # Split by commas
    items = [item.strip() for item in value.split(',') if item.strip()]
    if len(items) == 1:
        # Only one item, return it (remove weight if any)
        result = re.sub(r'\s*\(\d+\)', '', items[0]).strip()
        # Check if it's a 'none' value
        if result.lower() == 'none':
            return ' '
        # Restore any temporary placeholders
        if result in temp_holder:
            return temp_holder[result].replace('|', ',')
        return result

    weighted_items = []
    unweighted_items = []

    total_weight = 0

    for item in items:
        # Restore temporary placeholders before processing
        for temp_key, temp_value in temp_holder.items():
            if temp_key in item:
                item = item.replace(temp_key, f'{{{temp_value}}}')
                break
                
        match = re.match(r'(.*?)(?:\s*\((\d+)\))?$', item.strip())
        name = match.group(1).strip()
        weight = match.group(2)

        if weight:
            weight = int(weight)
            weighted_items.append((name, weight))
            total_weight += weight
        else:
            unweighted_items.append(name)

    if weighted_items:
        # Distribute remaining weight equally among unweighted items
        remaining_weight = 10 - total_weight
        if unweighted_items:
            per_item_weight = remaining_weight / len(unweighted_items)
            weighted_items.extend((name, per_item_weight) for name in unweighted_items)

        # Create a weighted choice list
        choices, weights = zip(*weighted_items)
        selected = random.choices(choices, weights=weights, k=1)[0]
        return selected
    else:
        return random.choice(unweighted_items)
    
    
def clean_row(row):
    return {k: v for k, v in row.items() if pd.notna(v)}

def clean_string(s: str) -> str:
    return s.replace("'", "").replace("\n", "").replace("{", "").replace("}", "").replace("|", ",").replace("none,", "")
