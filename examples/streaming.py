from llm4free import Client

client = Client()

stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain HTTP streaming in three sentences."}],
    stream=True,
)

for chunk in stream:
    content = chunk.choices[0].delta.content if chunk.choices else None
    if content:
        print(content, end="", flush=True)
print()
