import pandas as pd
from utils import parse_weighted_items, clean_row,clean_string
import random
from comfyui_job import comfyui
import re

def main_flow(characters, prefix,expression = "",lower_part=""):
    
    _characters = characters
    append = ""
    all_sheets = pd.read_excel("prompt_engine.xlsx", sheet_name=None)
    core_df = all_sheets["core"] 
    character_df = all_sheets.get("character")
    location_df = all_sheets.get("location")
    view_df = all_sheets.get("view")
    vocabulary_df = all_sheets.get("vocabulary")
    
    random_row = core_df.sample(n=1)
    # Print selected ID if exists
    if 'id' in random_row.columns:
        print(f"Selected ID: {random_row['id'].values[0]}")
    row_dict = random_row.to_dict(orient='records')[0]
    
    # Handle solo mode if specified
    if 'solo' in row_dict and str(row_dict['solo']).lower() == 'yes':
        _characters = [_characters[0]]  # Keep only first character
    # Exclude 'id' and 'solo' columns from filtered_row
    filtered_row = {k: v for k, v in row_dict.items() if pd.notna(v) and k not in ['id', 'solo']}
    # Add face value if _face, _head or _top exists in filtered_row
    if any(key in filtered_row for key in ['face', 'head', 'top']):
        append += expression
    if any(key in filtered_row for key in ['pussy']):
        append += ","+lower_part
    
    selected_values = []
    for field, value in filtered_row.items():
        selected = parse_weighted_items(str(value))
        if selected:
            selected_values.append(selected)
    
    selected_location = None
    location_horizontal = None
    location_vertical = None
    if location_df is not None and not location_df.empty:
        # Fill NaN in 'chance' column with 5
        location_df['chance'] = location_df['chance'].fillna(5)
    
        # Ensure 'chance' is numeric
        location_df['chance'] = pd.to_numeric(location_df['chance'], errors='coerce').fillna(5)
    
        # Prepare the choices and weights
        locations = location_df['location'].tolist()
        weights = location_df['chance'].tolist()
    
        # Randomly select one location based on weight
        selected_location = random.choices(locations, weights=weights, k=1)[0]
        
        # Get the horizontal and vertical values for the selected location
        location_row = location_df[location_df['location'] == selected_location].iloc[0]
        location_horizontal = location_row['horizontal'] if 'horizontal' in location_df.columns and pd.notna(location_row['horizontal']) else None
        location_vertical = location_row['vertical'] if 'vertical' in location_df.columns and pd.notna(location_row['vertical']) else None
    
    else:
        print("Sheet 'location' not found or is empty.")
    
    selected_view = None
    if view_df is not None and not view_df.empty:
        # Fill NaN in 'chance' column with 5
        view_df['chance'] = view_df['chance'].fillna(5)
    
        # Ensure 'chance' is numeric
        view_df['chance'] = pd.to_numeric(view_df['chance'], errors='coerce').fillna(5)
    
        # Prepare the choices and weights
        views = view_df['view'].tolist()
        weights = view_df['chance'].tolist()
    
        # Randomly select one view based on weight
        selected_view = random.choices(views, weights=weights, k=1)[0]
    
    else:
        print("Sheet 'view' not found or is empty.")
    
    selected_characters = []
    if character_df is not None and not character_df.empty:
        for t in _characters:
            # Filter rows where 'Type' column matches the type (case-insensitive)
            matching_rows = character_df[character_df['Type'].str.lower() == t.lower()]
    
            if not matching_rows.empty:
                # Randomly select one matching row
                row = matching_rows.sample(n=1).to_dict(orient='records')[0]
                cleaned = clean_row(row)
                selected_characters.append(cleaned)
            else:
                print(f"No matching character found for type: {t}")
    else:
        print("Sheet 'character' not found or is empty.")
        
    final_values = []
    
    print(selected_values)
    
    def replace_underscored_terms(text):
        # Find all underscore-prefixed words that are standalone (not part of another word)
        underscored_terms = re.findall(r'(?<!\w)_\w+', text)
        
        for term in underscored_terms:
            key = term[1:]  # Remove the underscore
            
            replacement = None
            
            if key == "location" and selected_location:
                replacement = " " if str(selected_location).lower() == "none" else selected_location
            elif key == "vertical" and location_vertical:
                replacement = parse_weighted_items(str(location_vertical))
            elif key == "horizontal" and location_horizontal:
                replacement = parse_weighted_items(str(location_horizontal))
            elif key == "view" and selected_view:
                replacement = " " if str(selected_view).lower() == "none" else selected_view
            elif key == "male" and selected_characters:
                for char in selected_characters:
                    if "gender" in char and char["gender"].lower() == "male" and "object" in char:
                        replacement = char["object"]
                        break
            elif key == "female" and selected_characters:
                for char in selected_characters:
                    if "gender" in char and char["gender"].lower() == "female" and "object" in char:
                        replacement = char["object"]
                        break
            elif character_df is not None and key in character_df.columns:
                column_series = character_df[key].dropna()
                if not column_series.empty:
                    source_string = column_series.iloc[0]
                    replacement = parse_weighted_items(str(source_string))
            elif vocabulary_df is not None:
                vocab_match = vocabulary_df[vocabulary_df["object"].str.lower() == key.lower()]
                if not vocab_match.empty:
                    vocab_string = vocab_match.iloc[0]["vocabulary"]
                    replacement = parse_weighted_items(str(vocab_string))
            
            if replacement is not None:
                # Handle "none" values for all replacements
                if isinstance(replacement, str) and replacement.lower() == "none":
                    replacement = " "
                text = text.replace(term, replacement)
            else:
                text = text.replace(term, key)  # Fallback to just the key name
        
        return text
    
    for val in selected_values:
        val = str(val).strip()
        
        # Handle both strings that start with _ and contain _terms
        processed_val = replace_underscored_terms(val)
        final_values.append(processed_val)
    
    # Join into final string
    final_prompt = ", ".join(final_values) +","+ _characters[0] + ("" if len(_characters) == 1 else ","+_characters[1]) +","+ prefix
    final_prompt += (","+append) if append!="" else ""
    final_prompt = clean_string(final_prompt)
    print(final_prompt)
    comfyui(final_prompt)