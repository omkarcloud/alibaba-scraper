# Alibaba Scraper

Alibaba Scraper gets you 🎯 accurate, 🔍 detailed Alibaba.com data as clean JSON in **Real-Time**.

No selectors, no proxies, no data cleaning. Just the data.

[**Try it now in the playground**](https://www.omkar.cloud/tools/alibaba-scraper/playground) - See the data quality for yourself in one click, **No sign-up required**.

**Build on it free:** 1,000 calls every month, no credit card ❤️

[![Alibaba Scraper API playground — run a live request in your browser, free, no sign-up](https://raw.githubusercontent.com/omkarcloud/alibaba-scraper/master/playground.png)](https://www.omkar.cloud/tools/alibaba-scraper/playground)

## What can I get

- 🔎 **Search millions of wholesale products** — 4.9M in Consumer Electronics alone; price, MOQ, orders & ratings
- 📦 **Full product pages in one call** — volume pricing, SKU variants with stock, lead times & certifications
- 🏭 **34K+ verified manufacturers** — years on Alibaba, factory size, response time, on-time rate & markets
- 📸 **Reverse image search & real reviews** — find products from a photo; buyer reviews with photos

## Why Alibaba Scraper

Most other Alibaba APIs fail you in one of four ways:

- 🗄️ **Inaccurate, cached, stale data**
- 🧩 **Low-detail endpoints** — a few fields per call, never the full picture
- 💸 **Pay more to get the same data**
- 🪦 **Works today, breaks next month** — nobody maintains it

Alibaba Scraper is scraped live on every call, priced honestly, and actively maintained.

## Example: A Full Alibaba Product

```json
{
  "id": 1600371615858,
  "title": "Custom 925 Sterling Silver Italy Link Chain Set Lobster Clasp Adjustable Snake Bone Sweater Chains Necklace",
  "link": "https://www.alibaba.com/product-detail/_1600371615858.html",
  "price": { "currency": "USD", "min": 4.72, "max": 24.47, "formatted": "$4.72-24.47", "unit": "piece" },
  "moq": { "quantity": 1, "unit": "pieces" },
  "sales": { "sold_count": 1102 },
  "rating": { "average": 5.0, "review_count": 98 },
  "variants": {
    "attributes": [
      { "id": 210192502, "name": "Design", "values": [{ "id": -1, "name": "Tile Chain(1.5mm)" }] },
      { "id": 191288010, "name": "Color", "values": [{ "id": -13, "name": "18K Gold Plated" }] }
    ],
    "skus": [{ "id": 109598013764, "price": 13.36, "formatted": "$13.36", "stock": 5000 }]
  },
  "lead_time": [{ "min_quantity": 1, "max_quantity": 2, "days": 7 }],
  "packaging": { "unit_size": "14X6X9", "unit_weight_kg": 0.005 },
  "inventory": { "ships_from": [{ "id": "CN", "name": "China" }], "total_stock": 559909 },
  "key_attributes": [{ "name": "Jewelry Main Material", "value": "925 SILVER" }],
  "supplier": {
    "name": "Haifeng County Meilong Liming Jewelry Processing Factory",
    "link": "https://limingsilver.en.alibaba.com/",
    "years_on_alibaba": 9,
    "response_time": "≤3h",
    "on_time_delivery_rate": 90.9,
    "rating": { "average": 4.8, "review_count": 80 },
    "transactions": { "half_year_order_amount": "120,000+", "half_year_order_count": 320 },
    "trade_assurance_amount": "154,000"
  },
  "is_trade_assurance": true,
  "is_customizable": true
}
```

*Trimmed for readability.*

## Get Started with 1,000 Free Calls

Start in the [playground](https://www.omkar.cloud/tools/alibaba-scraper/playground) — try any endpoint with one click, no sign-up required.

Once you're happy with the data, start with the free plan for 1,000 free calls every month:

1. [Sign up on Omkar Cloud](https://www.omkar.cloud/auth/sign-up?redirect=/tools/alibaba-scraper/playground) — free, no credit card.
2. Open the [Alibaba Scraper playground](https://www.omkar.cloud/tools/alibaba-scraper/playground) and enter any product you like. Click **Get Live Data**.
3. Enjoy your data 😎.

## Endpoints

12 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one product in a single call |
| Search Products | `/products/search` | 48 products per page, 16 filters to narrow them |
| Products By Category | `/products/by-category` | A whole category, browsable with the same filters |
| Search By Image | `/products/search-by-image` | Matching products from any photo URL |
| Product Reviews | `/products/reviews` | Buyer reviews with photos, translations & replies |
| Autocomplete | `/autocomplete` | Keyword suggestions straight from the search bar |
| Categories | `/categories` | The whole category tree, IDs included |
| Trending Keywords | `/trending-keywords` | What buyers are searching for right now |
| Search Suppliers | `/suppliers/search` | 20 manufacturers per page with trust signals |
| Supplier Details | `/suppliers/details` | A full company profile and its verification |
| Supplier Products | `/suppliers/products` | Everything one supplier sells, 16 per page |
| Supplier Reviews | `/suppliers/reviews` | Every review across a supplier's whole catalog |

## Pricing

High value, Low price.

| Plan | Price | Calls / month | Per 1,000 |
|---|---|---|---|
| **Basic** | **Free** | **1,000** — the most generous free plan | $0 |
| **Pro** | $16/mo | 20,000 | $0.80 |
| **Ultra** | $48/mo | 100,000 | $0.48 |
| **Mega** | $148/mo | 400,000 | $0.37 |

Need a bigger plan? Ask on [WhatsApp](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20a%20custom%20plan%20for%20the%20Alibaba%20Scraper%20API.) or [Email](mailto:happy.to.help@omkar.cloud?subject=Custom%20plan%20for%20Alibaba%20Scraper%20API&body=I%20need%20a%20custom%20plan%20for%20the%20Alibaba%20Scraper%20API.).

- [**90 Day 2 Click Refund Guarantee**](https://www.omkar.cloud/refund-process)
- This is an excellent API made by Omkar Cloud, which is Rated Excellent — [4.7 based on 30 reviews on Trustpilot](https://www.trustpilot.com/review/omkar.cloud).

👉 [Start with Free Plan](https://www.omkar.cloud/auth/sign-up?redirect=/tools/alibaba-scraper/playground) — 1,000 free calls/month

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Alibaba Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Alibaba%20Scraper%20API.)

[![Ask Us by Email about Alibaba Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Alibaba%20Scraper%20API&body=I%20need%20help%20using%20the%20Alibaba%20Scraper%20API.)

## Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

👉 [Start with Free Plan](https://www.omkar.cloud/auth/sign-up?redirect=/tools/alibaba-scraper/playground) — 1,000 free calls/month
