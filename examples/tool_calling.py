from llm4free import Client


c = Client()

weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name."}
            },
            "required": ["city"],
        },
    },
}
resp = c.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "what is wether in New York City?"},
    ],
    max_tokens=100,
    tools=[weather_tool],
)
from rich import print
print(resp)

