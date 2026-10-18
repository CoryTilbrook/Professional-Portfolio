from ollama import chat

prompt = "What are the five most important sections of a Product Requirements Document for software product management?"

print("Starting PRD Agent test...")
print("Sending prompt:", prompt)

response = chat(
    model="Qwen3:8b",
    messages=[
        {
            "role": "system", 
            "content": "You are an experienced software Product Manager who specializes in writing clear, detailed Product Requirements Documents (PRDs)."
        },
        {
            "role": "user",
            "content" : "What are the five most important sections of a Product requirements Document?"
        }
    ]
)

print(response.message.content)