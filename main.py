"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. See README.md → "Use it from Python" for the full function list.
"""
import json
import os

from alibaba.product import product_details, product_reviews
from alibaba.search import search_products

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # 48 products per page, with the same filters as the API
    results = search_products(query="raspberry pi", page=1, currency="USD")
    save("search_raspberry_pi.json", results)

    # a product id or any alibaba.com product link
    details = product_details("https://www.alibaba.com/product-detail/x_1600371615858.html", currency="USD")
    save("product_1600371615858.json", details)

    reviews = product_reviews(1600371615858, page=1)
    save("reviews_1600371615858.json", reviews)
