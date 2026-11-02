"""Tests for voice_commands.parse(). Run with:  python test_voice_commands.py

Each case is (sentence, expected result). Many sentences are written the way
Azure speech-to-text really returns them: capital letters, commas, periods,
digits, and sometimes number words or homophones ("to" = 2, "for" = 4).
"""

from voice_commands import parse

BOOK_BODY = {"type": "book", "title": "The Catcher in the Rye", "author": "J.D. Salinger", "page_count": 220}

CASES = [
    # --- Create (POST /api/items) ---
    ("Create item, type book, title The Catcher in the Rye, author J.D. Salinger, pages 220",
     {"method": "POST", "path": "/api/items", "body": BOOK_BODY}),
    ("Create item, type book, title The Catcher in the Rye, author J.D. Salinger, pages 220.",
     {"method": "POST", "path": "/api/items", "body": BOOK_BODY}),
    ("Create item. Type book. Title The Catcher in the Rye. Author J.D. Salinger. Pages 220.",
     {"method": "POST", "path": "/api/items", "body": BOOK_BODY}),
    ("create item type book title The Catcher in the Rye author J.D. Salinger pages two hundred twenty",
     {"method": "POST", "path": "/api/items", "body": BOOK_BODY}),
    ("Create item, type DVD, title The Godfather, author Francis Ford Coppola, minutes 175.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "dvd", "title": "The Godfather", "author": "Francis Ford Coppola", "duration": 175}}),
    ("Create item, type DVD, title Up, author Pete Docter, duration 96 minutes.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "dvd", "title": "Up", "author": "Pete Docter", "duration": 96}}),
    ("Add a DVD, title Alien, director Ridley Scott, duration 117.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "dvd", "title": "Alien", "author": "Ridley Scott", "duration": 117}}),
    ("Create item, type book, title War and Peace, author Leo Tolstoy, pages 1,225.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "book", "title": "War and Peace", "author": "Leo Tolstoy", "page_count": 1225}}),
    ("Create item, type book, title To Kill a Mockingbird, author Harper Lee, page count 281.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "book", "title": "To Kill a Mockingbird", "author": "Harper Lee", "page_count": 281}}),
    ("Create item, type book, title Love, Actually, author Someone, pages 10.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "book", "title": "Love, Actually", "author": "Someone", "page_count": 10}}),
    # Missing or wrong fields are still sent: the API answers 400 with a clear message.
    ("Create item, type book, title Dune.",
     {"method": "POST", "path": "/api/items", "body": {"type": "book", "title": "Dune"}}),
    ("Create item, type book, title Dune, author Frank Herbert, pages many.",
     {"method": "POST", "path": "/api/items",
      "body": {"type": "book", "title": "Dune", "author": "Frank Herbert", "page_count": "many"}}),

    # --- List (GET /api/items) ---
    ("list all items", {"method": "GET", "path": "/api/items", "body": None}),
    ("List all items.", {"method": "GET", "path": "/api/items", "body": None}),
    ("List available books.", {"method": "GET", "path": "/api/items?available=true&type=book", "body": None}),
    ("list checked out DVDs", {"method": "GET", "path": "/api/items?available=false&type=dvd", "body": None}),
    ("List checked-out DVDs.", {"method": "GET", "path": "/api/items?available=false&type=dvd", "body": None}),
    ("Show me all books.", {"method": "GET", "path": "/api/items?type=book", "body": None}),
    ("List all DVD's.", {"method": "GET", "path": "/api/items?type=dvd", "body": None}),
    ("What's available?", {"method": "GET", "path": "/api/items?available=true", "body": None}),
    ("List books that are not available.",
     {"method": "GET", "path": "/api/items?available=false&type=book", "body": None}),
    ("List all books and DVDs.", {"method": "GET", "path": "/api/items", "body": None}),

    # --- Get (GET /api/items/<id>) ---
    ("show item 3", {"method": "GET", "path": "/api/items/3", "body": None}),
    ("Show item 3.", {"method": "GET", "path": "/api/items/3", "body": None}),
    ("Get item three.", {"method": "GET", "path": "/api/items/3", "body": None}),
    ("Show item number 3.", {"method": "GET", "path": "/api/items/3", "body": None}),
    ("Show item #12.", {"method": "GET", "path": "/api/items/12", "body": None}),
    ("Show item No. 7.", {"method": "GET", "path": "/api/items/7", "body": None}),
    ("Get item twenty-one.", {"method": "GET", "path": "/api/items/21", "body": None}),
    ("Show item for.", {"method": "GET", "path": "/api/items/4", "body": None}),
    ("Get item won.", {"method": "GET", "path": "/api/items/1", "body": None}),

    # --- Replace (PUT, all fields) ---
    ("replace item 3, title X, author Y, pages 300",
     {"method": "PUT", "path": "/api/items/3", "body": {"title": "X", "author": "Y", "page_count": 300}}),
    ("Replace item three, title Animal Farm, author George Orwell, pages 112.",
     {"method": "PUT", "path": "/api/items/3",
      "body": {"title": "Animal Farm", "author": "George Orwell", "page_count": 112}}),
    ("Replace item to, title Brave New World, author Aldous Huxley, pages 311.",
     {"method": "PUT", "path": "/api/items/2",
      "body": {"title": "Brave New World", "author": "Aldous Huxley", "page_count": 311}}),

    # --- Update (PATCH, only the given fields) ---
    ("update item 3, pages 250", {"method": "PATCH", "path": "/api/items/3", "body": {"page_count": 250}}),
    ("Update item 3, pages 250.", {"method": "PATCH", "path": "/api/items/3", "body": {"page_count": 250}}),
    ("change item 3 title to X", {"method": "PATCH", "path": "/api/items/3", "body": {"title": "X"}}),
    ("Change item 3 title to Animal Farm.",
     {"method": "PATCH", "path": "/api/items/3", "body": {"title": "Animal Farm"}}),
    ("Change item 3 title to To Kill a Mockingbird.",
     {"method": "PATCH", "path": "/api/items/3", "body": {"title": "To Kill a Mockingbird"}}),
    ("Change item for author to Jane Austen.",
     {"method": "PATCH", "path": "/api/items/4", "body": {"author": "Jane Austen"}}),
    ("Set item 4 duration to 170 minutes.",
     {"method": "PATCH", "path": "/api/items/4", "body": {"duration": 170}}),
    ("Update item number two, title Nineteen Eighty-Four, pages 330.",
     {"method": "PATCH", "path": "/api/items/2", "body": {"title": "Nineteen Eighty-Four", "page_count": 330}}),
    ("Update item 3.", {"method": "PATCH", "path": "/api/items/3", "body": {}}),

    # --- Delete ---
    ("delete item 3", {"method": "DELETE", "path": "/api/items/3", "body": None}),
    ("Delete item 3.", {"method": "DELETE", "path": "/api/items/3", "body": None}),
    ("Remove item too.", {"method": "DELETE", "path": "/api/items/2", "body": None}),
    ("Please remove item number 9.", {"method": "DELETE", "path": "/api/items/9", "body": None}),

    # --- Checkout ---
    ("check out item 3", {"method": "POST", "path": "/api/items/3/checkout", "body": None}),
    ("Check out item 3.", {"method": "POST", "path": "/api/items/3/checkout", "body": None}),
    ("Checkout item three.", {"method": "POST", "path": "/api/items/3/checkout", "body": None}),
    ("Check out item to.", {"method": "POST", "path": "/api/items/2/checkout", "body": None}),
    ("Can you check out item 3 for me?", {"method": "POST", "path": "/api/items/3/checkout", "body": None}),
    ("I'd like to borrow item 1.", {"method": "POST", "path": "/api/items/1/checkout", "body": None}),

    # --- Return ---
    ("return item 3", {"method": "POST", "path": "/api/items/3/return", "body": None}),
    ("Return item 3.", {"method": "POST", "path": "/api/items/3/return", "body": None}),
    ("Return item for.", {"method": "POST", "path": "/api/items/4/return", "body": None}),
    ("Return item won.", {"method": "POST", "path": "/api/items/1/return", "body": None}),
]

# Sentences that must give an error, and a word the error message must contain.
ERROR_CASES = [
    ("", "didn't hear"),
    ("   ", "didn't hear"),
    ("Hello, how are you?", "didn't understand"),
    ("Check out the book.", "Which item"),
    ("Delete it.", "Which item"),
    ("Return item.", "Which item"),
    ("Update the pages to 250.", "Which item"),
]


def main():
    failures = 0
    for sentence, expected in CASES:
        result = parse(sentence)
        if result != expected:
            failures += 1
            print(f"FAIL: {sentence!r}\n   expected {expected}\n   got      {result}")

    for sentence, expected_words in ERROR_CASES:
        result = parse(sentence)
        if "error" not in result or expected_words not in result["error"]:
            failures += 1
            print(f"FAIL: {sentence!r}\n   expected an error with {expected_words!r}\n   got {result}")

    total = len(CASES) + len(ERROR_CASES)
    print(f"{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
