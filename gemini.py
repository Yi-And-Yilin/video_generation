# Install the SDK if you haven't already:
# pip install google-genai
import os
from comfyui_job import comfyui
import google.generativeai as genai
import json

prompt = '''
You are a prompt engineer who excel at writing prompts for AI image generator to draw pictures.

Important:
1. Your output is pure json array without any explanation or introduction, It should be json array even there is only one enitiy.
2. tags should inclue all elements, each tag is separate by comman
3. don't mention eyes in your prompt
4. The main character is a woman, who is riding a pillar, but, she can wear any clothes and the location can be any place
5. the location prefer to indoor, or some private outdoor, like a backyard or somthing else
5. IMPORTANT: the action of 

The output format:
{"location":"rigged living room",
settings:"sofa, tv set, lamp, desk, bookshelf",
angle:"from below",
face expression:"for example, happy",
woman_clothes_upperbody:"t-shirt",
woman_clothes_lowerbody:"pants",
woman_footware:"boots",
woman_hairstyle:"straight hair",
other_tags:"illustrative style",
main_body_part:"front_upper, front_lower, front_full_body, back_upper, back_lower, back_full_body"}
'''

lookup_table = {
    "bamboo": "penis",
    "flower": "pussy",
    "rabbit": "breast",
    "box": "ass",
    "bullet": "nipples",
    "eruption": "cum",
    "riding": "riding on penis",
    "dog": "doggy style",
    "oral": "oral sex, penis in the mouth",
    "lick": "tougn in pussy, man's head, head between legs",
    "footwork": "footjob",
    "handmaster": "handjob",
    "go-in": "penetration,penis in pussy",
    "rubbing": "masturbation,hand on pussy",
    "skirt": "skirt pulled up",
    "jeans": "jeans pulled down",
    "bullet": "nipples",
    "bullet": "nipples",
    "bullet": "nipples",
    # add more mappings as needed
}

prefix_table = {
    "man_gesture": "man ",
    "woman_gesture": "woman ",
    "male":"male is ",
    "female":"female is "
}


prompt_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.txt")
# # Hard-code your API key directly here
# API_KEY = "AIzaSyC1Cox0aIiAtub0HqAXFH4RxJnAulfl-3s"
# model_name = 'gemini-2.0-flash'

# # Initialize the client

# genai.configure(api_key=API_KEY)

# gemini_model = genai.GenerativeModel(model_name)
# gemini_generation_config = {
#     "temperature": 0.7,
# }

# response = gemini_model.generate_content(prompt, generation_config=gemini_generation_config)


# # Print the response text
# print(response.text)





# This is your JSON string from response.text
# text = response.text.strip()

additional_prompt = ''''
masterpiece, high_quality, highres, detailed skin,dynamic lighting,
 sweating, moaning, suggestive expression,
 young boy,mature lady,  
'''

action_group = [
    # "doggy style, penetration, pussy, penis,",
    # "riding on a penis, cowgirl, hand in hand,",
    # "oral sex, penis in mouth, head between legs,",
    # "lie on back, legs up,penis in pussy, ",
    # "sex from behind, ass up,penis in pussy, hands on ass,"
    # "suspended congress , penis in pussy,",
    # "cumshot, overhead view,",
    # "blowjob, overhead view,penis in the mouth,",
    # "cowgirl, pov,",
    # "pov missionary,penis in pussy,cleavage,",
    # "female masterbation, pussy focus,finger in pussy,",  
    # "suspended congress, grab ass,",
    "female masterbation, pussy focus,ass up,finger in pussy,",
    "kneel on the floor, pussy focus,ass up,finger in pussy,hand between legs,",
    "kneel on the floor, pussy focus,ass up,spread pussy,",
    "squat , pussy focus,spread pussy,high heels,",
    "sit on man's face, ass focus,man lie on back,",
    ]


additional_prompt = additional_prompt.replace("\n", "")

with open(prompt_file_path, "r", encoding="utf-8") as f:
    text = f.read()


# Remove Markdown code fences if present
if text.startswith("```"):
    cleaned_lines = []
    lines = text.splitlines()
    for line in lines:
        if not line.strip().startswith("```"):
            cleaned_lines.append(line)
    clean_text = "\n".join(cleaned_lines)
else:
    clean_text = text

# Parse the JSON string
data = json.loads(clean_text)

# Define keys to exclude
keys_to_exclude = ["main_body_part","face_expression",
                   "man_clothes_upperbody","man_clothes_lowerbody",
                   "man_footwear"]  # add more keys to exclude if needed

# Loop over each entity dict in the list
for entity in data:
    for act in action_group:
    # Keep only keys not excluded
        filtered_items = []
        for k, v in entity.items():
            if k not in keys_to_exclude:
                value = str(v)
                # Apply the lookup table replacements
                for old, new in lookup_table.items():
                    value = value.replace(old, new)
                value = value.replace("-", " ")
                
                if k in prefix_table:
                    value = prefix_table[k] + value
                filtered_items.append(value)
    
        # Join values with commas
        entity_str = act+","+additional_prompt+",".join(filtered_items)
    
        # Print and send to your function
        print(entity_str)
        comfyui(entity_str)
