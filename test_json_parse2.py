import json
from llm_conversation import LLMUtils, Conversation

# Test the actual LLM response
llm_output = '''{


 
 "locations":
 [


   
 {


     
 "location": "Modern Loft Bedroom",


     
 "time": "midnight",


     
 "lighting": "moonlight through sheer curtains with warm accent lamps",


     
 "prompts": [


       
 {


         
 "sex_act": "missionary position",


         
 "prompt": "A young American man with an athletic build and confident demeanor lies on his back on a luxurious silk duvet, wearing only grey boxer briefs. A young French woman with slender hips and wavy hair leans over him, wearing a black lace bra and matching thong, her tongue kissing his deeply. Her legs wrap around his waist as he thrusts his penis into her vagina, the intimate connection highlighted by the dim moonlight filtering through the sheer curtains of the modern loft bedroom. The scene is shot on 85mm lens, shallow depth of field, high resolution, realistic texture of skin and fabric."


       
 },


       
 {


         
 "sex_act": "cowgirl position",


         
 "prompt": "The young American man sits upright against the headboard of the bed, wearing grey boxer briefs, looking up with a confident gaze. The young French woman straddles his lap in the cowgirl position, wearing a white silk robe that is slipping off her shoulders, revealing her breasts and nipples. She leans forward to kiss him while grinding her pussy against his erect penis, preparing for penetration. The background shows a minimalist modern bedroom with nightstands and soft lamps. Cinematic lighting, 4k detail, photorealistic."


       
 }


     
 ]


   
 },


   
 {


     
 "location": "Luxury Bathroom",


     
 "time": "night",


     
 "lighting": "soft overhead shower light and candlelight on the counter",


     
 "prompts": [


       
 {


         
 "sex_act": "blowjob",


         
 "prompt": "The young American man stands leaning against the marble sink counter, fully naked. The young French woman is on her knees before him, wearing a translucent white silk robe that leaves her breasts exposed. She holds his erect penis in her hand, guiding it towards her mouth to perform a blowjob, her tongue visible licking the tip. Steam rises from the bathtub in the background. The lighting is warm and intimate, coming from candles placed on the bathroom counter. Close-up shot, detailed facial expressions, sensual atmosphere."


       
 },


       
 {


         
 "sex_act": "doggy style",


         
 "prompt": "The young American man stands behind the young French woman, who is bent over the edge of a clawfoot bathtub. She wears only a sheer white towel that is falling down, exposing her vagina and buttocks. He grips her hips, thrusting his penis into her vagina in the doggy style position. The bathroom is filled with steam, illuminated by soft candlelight reflecting off the tiles. The man's athletic muscles are tense, and the woman's wavy hair falls over her face. High contrast, dramatic shadows, realistic skin tones."


       
 }


     
 ]


   
 }


 
 ]
}'''

print('=== Testing json.loads on full output ===')
try:
    parsed = json.loads(llm_output)
    print('SUCCESS: Full output parsed successfully')
    print(f'Locations: {[loc["location"] for loc in parsed["locations"]]}')
except json.JSONDecodeError as e:
    print(f'FAILED: {e}')
