from llm4free import Client

client = Client()

resp = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "Give me three ideas for a weekend Python project."}
    ],
)
message = resp.choices[0].message
print(message.content if message else "")

image = client.images.generate(
    prompt="A cozy desk with a laptop, warm morning light, photorealistic",
    model="auto",
)
print(image.data[0].url)
