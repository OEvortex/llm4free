from llm4free import Client

client = Client()

# 1. Auto mode: picks a working engine and fails over on errors.
response = client.search.create(
    query="best python web scraping library",
    max_results=3,
)
print(f"engine={response.engine} results={len(response)}")
for result in response.data:
    print(f"- {result.title} -> {result.href}")

# 2. Pin each registered engine explicitly.
for engine in client.search.list_engines():
    try:
        result = client.search.create(query="python programming", engine=engine, max_results=1)
        first = result[0].title if result else "-"
        print(f"{engine:12} {len(result)} result(s) | {first[:50]}")
    except Exception as exc:
        print(f"{engine:12} unavailable: {exc}")

# 3. Search other categories.
for category in ("images", "news", "suggestions"):
    try:
        result = client.search.create(query="mount everest", category=category, max_results=2)
        print(f"{category:12} {len(result)} result(s) via {result.engine}")
    except Exception as exc:
        print(f"{category:12} unavailable: {exc}")

# 4. The response is JSON-ready.
print(response.to_dict())
