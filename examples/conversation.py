from llm4free import Client

client = Client()
messages = [{"role": "system", "content": "You are a senior Python engineer. Be direct."}]

for question in [
    "How do I sort a list of dicts by the 'score' key?",
    "Show the same sort with reverse=True.",
    "What is the time complexity of that sort?",
]:
    messages.append({"role": "user", "content": question})

    resp = client.chat.completions.create(model="auto", messages=messages)
    message = resp.choices[0].message
    reply = (message.content if message else "") or ""
    messages.append({"role": "assistant", "content": reply})

    print(f"\nUser: {question}")
    print(f"Assistant: {reply}")
