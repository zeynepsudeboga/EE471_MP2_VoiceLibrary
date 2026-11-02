"""Test every endpoint once with Flask's test client (no server, no Azure calls).
Run with:  python test_endpoints.py

The app starts with 4 items: 1 Dune (book), 2 1984 (book),
3 The Matrix (DVD), 4 Interstellar (DVD). The tests run in order and
change that data, so each test expects the state the previous ones left.
"""

from app import app

client = app.test_client()
failures = 0


def check(name, response, expected_status):
    """Print one result line and count failures."""
    global failures
    ok = response.status_code == expected_status
    if not ok:
        failures += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {response.status_code} (expected {expected_status})"
          + ("" if ok else f"  body={response.get_data(as_text=True)}"))
    return response.get_json(silent=True)


def run_sentence(sentence, expected_status):
    """Do what the frontend does: parse the sentence, then send the real request."""
    command = check(f"parse {sentence!r}", client.post("/api/voice/parse", json={"text": sentence}), 200)
    response = client.open(command["path"], method=command["method"], json=command["body"])
    return check(f"  -> {command['method']} {command['path']}", response, expected_status)


print("--- The 8 library endpoints ---")
data = check("GET /api/items", client.get("/api/items"), 200)
assert len(data) == 4
check("GET /api/items?available=true&type=book", client.get("/api/items?available=true&type=book"), 200)
check("GET /api/items?available=maybe", client.get("/api/items?available=maybe"), 400)

data = check("POST /api/items", client.post("/api/items", json={
    "type": "book", "title": "Emma", "author": "Jane Austen", "page_count": 474}), 201)
assert data["id"] == 5
check("POST /api/items (missing fields)", client.post("/api/items", json={"type": "book"}), 400)

check("GET /api/items/5", client.get("/api/items/5"), 200)
check("GET /api/items/99", client.get("/api/items/99"), 404)

check("PUT /api/items/5", client.put("/api/items/5", json={
    "title": "Emma", "author": "Jane Austen", "page_count": 500}), 200)
check("PUT /api/items/5 (missing fields)", client.put("/api/items/5", json={"title": "Emma"}), 400)

check("PATCH /api/items/5", client.patch("/api/items/5", json={"page_count": 480}), 200)
check("PATCH /api/items/5 (empty body)", client.patch("/api/items/5", json={}), 400)

check("POST /api/items/5/checkout", client.post("/api/items/5/checkout"), 200)
check("POST /api/items/5/checkout (again)", client.post("/api/items/5/checkout"), 409)
check("DELETE /api/items/5 (checked out)", client.delete("/api/items/5"), 409)

check("POST /api/items/5/return", client.post("/api/items/5/return"), 200)
check("POST /api/items/5/return (again)", client.post("/api/items/5/return"), 409)

check("DELETE /api/items/5", client.delete("/api/items/5"), 204)
check("DELETE /api/items/5 (again)", client.delete("/api/items/5"), 404)

print("\n--- Voice routes (without calling Azure) ---")
check("POST /api/voice/parse (not understood)", client.post("/api/voice/parse", json={"text": "hello"}), 422)
check("POST /api/voice/parse (no JSON)", client.post("/api/voice/parse"), 400)
check("POST /api/speak (empty)", client.post("/api/speak", json={"text": ""}), 400)
check("POST /api/speak (too long)", client.post("/api/speak", json={"text": "a" * 501}), 400)
check("POST /api/voice/recognize (no audio)", client.post("/api/voice/recognize"), 400)

print("\n--- Sentences -> parser -> real endpoints ---")
run_sentence("Create item, type book, title The Catcher in the Rye, author J.D. Salinger, pages 220.", 201)
run_sentence("Create item, type DVD, title Up, author Pete Docter, duration 96 minutes.", 201)
run_sentence("Create item, type book, title Dune.", 400)
run_sentence("List available books.", 200)
run_sentence("Show item number 6.", 200)
run_sentence("Replace item 6, title The Catcher in the Rye, author J. D. Salinger, pages 230.", 200)
run_sentence("Change item 6 title to Catcher.", 200)
run_sentence("Update item 6, pages 250.", 200)
run_sentence("Check out item 6.", 200)
run_sentence("Check out item 6.", 409)
data = run_sentence("List checked out books.", 200)
assert [item["title"] for item in data] == ["Catcher"]
run_sentence("Delete item 6.", 409)
run_sentence("Return item 6.", 200)
run_sentence("Return item 6.", 409)
run_sentence("Remove item 6.", 204)
run_sentence("Show item 9.", 404)

print(f"\n{'All tests passed.' if failures == 0 else f'{failures} test(s) failed.'}")
raise SystemExit(1 if failures else 0)
