![Alibaba Scraper Featured Image](https://raw.githubusercontent.com/omkarcloud/alibaba-scraper/master/alibaba-scraper-featured-image.png)

# Alibaba Scraper API

Search Alibaba products, get volume pricing tiers, supplier verification, MOQs, and full product specs — all via a single API call. Real-time data, structured JSON. **5,000 free requests/month.**

## Key Features

- Search Alibaba products by keyword with pagination
- Get 30+ data points per product (volume pricing tiers, MOQ, supplier verification, variants, specs)
- Full supplier profiles with Gold Supplier status, Trade Assurance, ratings, facility size
- SKU variant groups with swatch images and combination mapping
- **5,000 requests/month on free tier**
- Example Response:
```json
{
    "product_id": "1601216646059",
    "title": "E6s TWS Bluetooth 5.0 Earphone Best Gaming Headset Noise Cancelling Headphones Sports Waterproof TWS Earbuds",
    "pricing": {
        "range": "2.5-2.7",
        "range_formatted": "$2.50-2.70",
        "tiers": [
            { "unit_price": "2.7", "formatted_price": "$2.70", "min_units": 20, "max_units": 499 },
            { "unit_price": "2.5", "formatted_price": "$2.50", "min_units": 2000, "max_units": -1 }
        ],
        "minimum_order_qty": "20",
        "minimum_order_label": "20 pieces"
    },
    "supplier": {
        "name": "Shengdi (jieyang) Electronic Technology Co., Ltd.",
        "is_gold_supplier": true,
        "has_trade_assurance": true,
        "country": "China"
    }
}
```

## Get API Key

Create an account at [omkar.cloud](https://www.omkar.cloud/auth/sign-up?redirect=/api-key) to get your API key.

It takes just 2 minutes to sign up. You get 5,000 free requests every month for detailed Alibaba data — more than enough for most users to get their job done without paying a dime.

This is a well built product, and your search for the best Alibaba Scraper API ends right here.


## Quick Start

```bash
curl -X GET "https://alibaba-scraper.omkar.cloud/alibaba/products/search?search_query=wireless%20earbuds" \
  -H "API-Key: YOUR_API_KEY"
```

```json
{
    "count": 19899,
    "per_page": 20,
    "current_page": 1,
    "total_pages": 995,
    "next": "https://alibaba-scraper.omkar.cloud/alibaba/products/search?search_query=wireless+earbuds&page=2",
    "previous": null,
    "products": [
        {
            "product_id": "1601216646059",
            "title": "E6s TWS Bluetooth 5.0 Earphone Best Gaming Headset Noise Cancelling Headphones Sports Waterproof TWS Earbuds",
            "pricing": {
                "range": "2.5-2.7",
                "range_formatted": "$2.50-2.70"
            },
            "supplier": {
                "name": "Shengdi (jieyang) Electronic Technology Co., Ltd.",
                "is_gold_supplier": true,
                "has_trade_assurance": true,
                "country": "China"
            }
        }
    ]
}
```

## Quick Start (Python)

```bash
pip install requests
```

```python
import requests

# Search for products
response = requests.get(
    "https://alibaba-scraper.omkar.cloud/alibaba/products/search",
    params={"search_query": "wireless earbuds"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```


## API Reference

### Search Products

```
GET https://alibaba-scraper.omkar.cloud/alibaba/products/search
```

#### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `search_query` | Yes | — | Keyword to search for products. |
| `page` | No | `1` | Page number. |

#### Example

```python
import requests

response = requests.get(
    "https://alibaba-scraper.omkar.cloud/alibaba/products/search",
    params={"search_query": "wireless earbuds"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```

#### Response

<details>
<summary>Sample Response (click to expand)</summary>

```json
{
    "count": 19899,
    "per_page": 20,
    "current_page": 1,
    "total_pages": 995,
    "next": "https://alibaba-scraper.omkar.cloud/alibaba/products/search?search_query=wireless+earbuds&page=2",
    "previous": null,
    "products": [
        {
            "product_id": "1601216646059",
            "title": "E6s TWS Bluetooth 5.0 Earphone Best Gaming Headset Noise Cancelling Headphones Sports Waterproof TWS Earbuds",
            "url": "//www.alibaba.com/product-detail/_1601216646059.html",
            "thumbnail": "//s.alicdn.com/@sc04/kf/H9884d49fc9a64f34bb9a2222ef978785i.jpg",
            "gallery_images": [
                "//s.alicdn.com/@sc04/kf/H9884d49fc9a64f34bb9a2222ef978785i.jpg",
                "//s.alicdn.com/@sc04/kf/H12f818eafa1b4c31ab1106700ecdfdd0S.jpg",
                "//s.alicdn.com/@sc04/kf/He0d97511701840bb825261341ed4c24aN.jpg",
                "//s.alicdn.com/@sc04/kf/Hcb8a6e88979548eca529b7536df4dca1l.jpg",
                "//s.alicdn.com/@sc04/kf/H43e22b66fbfe4ca797031d4b7755d595p.jpg",
                "//s.alicdn.com/@sc04/kf/H6994b429941e4918b9593d120286b3515.jpg"
            ],
            "pricing": {
                "range": "2.5-2.7",
                "range_formatted": "$2.50-2.70",
                "tiers": [
                    {
                        "unit_price": "2.7",
                        "formatted_price": "$2.70",
                        "min_units": 20,
                        "max_units": 499,
                        "unit_label": "pieces"
                    },
                    {
                        "unit_price": "2.6",
                        "formatted_price": "$2.60",
                        "min_units": 500,
                        "max_units": 1999,
                        "unit_label": "pieces"
                    },
                    {
                        "unit_price": "2.5",
                        "formatted_price": "$2.50",
                        "min_units": 2000,
                        "max_units": -1,
                        "unit_label": "pieces"
                    }
                ],
                "minimum_order_qty": "20",
                "minimum_order_unit": "piece",
                "minimum_order_label": "20 pieces"
            },
            "seller": {
                "shop_url": "//shengdidz.en.alibaba.com/",
                "shop_logo": "//sc02.alicdn.com/kf/H307700620cf74d11bae7fe76c14ffa6bN.jpg",
                "years_active": "3",
                "ratings": [
                    { "label": "Product as Described", "score": "4.3" },
                    { "label": "Store Service", "score": "4.3" },
                    { "label": "On time Shipping", "score": "4.4" },
                    { "label": "Product Review", "score": "0.0" },
                    { "label": "All Product Review", "score": "4.3" }
                ]
            },
            "supplier": {
                "name": "Shengdi (jieyang) Electronic Technology Co., Ltd.",
                "id": 283124971,
                "is_gold_supplier": true,
                "is_assessed": true,
                "is_verified": false,
                "has_trade_assurance": true,
                "facility_size": "1700",
                "employee_count": "60",
                "country": "China",
                "country_code": "CN"
            }
        }
    ]
}
```

</details>

---

### Product Details

```
GET https://alibaba-scraper.omkar.cloud/alibaba/products/details
```

#### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `product_id` | Yes | — | Alibaba product ID (e.g., `1601422779481`). |

#### Example

```python
import requests

response = requests.get(
    "https://alibaba-scraper.omkar.cloud/alibaba/products/details",
    params={"product_id": "1601422779481"},
    headers={"API-Key": "YOUR_API_KEY"}
)

print(response.json())
```

#### Response Fields

Returns 30+ fields including availability, title, gallery images, video, full specifications, description HTML, volume pricing tiers with MOQ, variant groups with swatch images, SKU combinations, seller ID, and full supplier profile.

<details>
<summary>Sample Response (click to expand)</summary>

```json
{
    "product_id": "1601422779481",
    "is_available": true,
    "title": "Q93 Wireless AI Translator Earbuds Sports Life Waterproof and Noise Reducing Wireless Earbuds 5.4 IPX5 Waterproof Headphone",
    "category_id": 201330216,
    "url": "//www.alibaba.com/product-detail/_1601422779481.html",
    "gallery_images": [
        "//sc04.alicdn.com/kf/H307e2f578216401cb1aef67e5cd65b32b.jpg",
        "//sc04.alicdn.com/kf/H241f861127a04758846586ab89673199a.jpg",
        "//sc04.alicdn.com/kf/H35807851e0e245ab8f1f4b00a86fbb43H.jpg",
        "//sc04.alicdn.com/kf/H6e4b352c16894e10b630347e7480f804d.jpg",
        "//sc04.alicdn.com/kf/Ha16307582d2e455590d5747ff489a00af.jpg",
        "//sc04.alicdn.com/kf/H13174faf3cd84fac823ac9cb8f7f28ffx.jpg"
    ],
    "video": null,
    "specifications": {
        "summary": "feature / Display Type / brand name / Product Type / function / private mold / Operating System / Material / place of origin / Language Support / Display Color",
        "attributes": [
            { "label": "feature", "value": "translator" },
            { "label": "Display Type", "value": "Oled" },
            { "label": "brand name", "value": "Somall" },
            { "label": "Product Type", "value": "Translate Earbuds" },
            { "label": "function", "value": "translator" },
            { "label": "private mold", "value": "Yes" },
            { "label": "Operating System", "value": "Symbian" },
            { "label": "Material", "value": "ABS" },
            { "label": "place of origin", "value": "Sichuan China" },
            { "label": "Language Support", "value": "115" },
            { "label": "Display Color", "value": "Black / White" }
        ]
    },
    "pricing": {
        "currency_symbol": "$",
        "price_type": "volumePrice",
        "tiers": [
            {
                "unit_price": 7.99,
                "formatted_price": "$7.99",
                "min_units": 2,
                "max_units": 99,
                "quantity_label": "2-99 sets"
            },
            {
                "unit_price": 6.99,
                "formatted_price": "$6.99",
                "min_units": 100,
                "max_units": 499,
                "quantity_label": "100-499 sets"
            },
            {
                "unit_price": 5.99,
                "formatted_price": "$5.99",
                "min_units": 500,
                "max_units": 999,
                "quantity_label": "500-999 sets"
            },
            {
                "unit_price": 4.99,
                "formatted_price": "$4.99",
                "min_units": 1000,
                "max_units": -1,
                "quantity_label": "≥1000 sets"
            }
        ],
        "minimum_order_qty": 2,
        "minimum_order_unit": "sets",
        "minimum_order_label": "2 sets",
        "unit_singular": "set",
        "unit_plural": "sets"
    },
    "variants": {
        "groups": [
            {
                "attribute_name": "model number",
                "options": [
                    { "option_id": "3:-3", "label": "Q93" }
                ]
            },
            {
                "attribute_name": "color",
                "options": [
                    {
                        "option_id": "191288010:3331185",
                        "label": "White",
                        "swatch_image": "//sc04.alicdn.com/kf/Hc0d61ed2bfcd43fb82f0d3487b70e943V.jpg"
                    },
                    {
                        "option_id": "191288010:3327837",
                        "label": "Black",
                        "swatch_image": "//sc04.alicdn.com/kf/H8a5b2b4cb9ea4af2bdfeae9b08c16cdek.jpg"
                    }
                ]
            }
        ],
        "combinations": [
            { "sku_id": 106577366684, "attribute_map": "3:-3;191288010:3331185" },
            { "sku_id": 106577366685, "attribute_map": "3:-3;191288010:3327837" }
        ]
    },
    "seller_id": 267514978,
    "supplier": {
        "name": "Sichuan Shenmai Technology Co., Ltd.",
        "id": 274605092,
        "business_type": "Trading Company",
        "employee_count": null,
        "transaction_volume": "US$ 30,000+",
        "contact_person": "jenny jenyy"
    }
}
```

</details>

## Error Handling

```python
response = requests.get(
    "https://alibaba-scraper.omkar.cloud/alibaba/products/search",
    params={"search_query": "wireless earbuds"},
    headers={"API-Key": "YOUR_API_KEY"}
)

if response.status_code == 200:
    data = response.json()
elif response.status_code == 401:
    # Invalid API key
    pass
elif response.status_code == 429:
    # Rate limit exceeded
    pass
```

## FAQs

### What data does the API return?

**Search Products** returns title, product URL, thumbnail, gallery images, volume pricing with range and tier breakdowns, MOQ, seller info (shop URL, logo, years active, ratings), and supplier info (company name, Gold Supplier status, Trade Assurance, facility size, employee count, country).

**Product Details** returns 30+ fields — availability, title, category ID, full gallery images, video, all product specifications, description HTML with images, volume pricing with currency and tier breakdowns, variant groups (color, size, material) with swatch images, SKU combinations, seller ID, and full supplier profile (business type, transaction volume, contact person).

All in structured JSON. Ready to use in your app.

### How accurate is the data?

Data is pulled from Alibaba in real time. Every API call fetches live data — not cached or stale results. Prices, availability, supplier info, and variants reflect what's on Alibaba.com right now.

### How do I get a product ID?

Every Alibaba product URL contains the product ID. For example, in `https://www.alibaba.com/product-detail/_1601422779481.html`, the product ID is `1601422779481`.

You can also get product IDs from the Search Products endpoint — each result includes a `product_id` field.

### Can I get MOQ and volume pricing?

Yes. Both endpoints return full pricing details. Search results include the price range and all volume tiers with min/max quantity breakdowns. Product Details adds the exact MOQ, currency, and per-unit labels. Ideal for building sourcing tools where buyers compare pricing across quantities.

### How do I identify verified suppliers?

Each product result includes supplier verification data: `is_gold_supplier`, `is_assessed`, `is_verified`, and `has_trade_assurance`. Filter on these flags to surface only Trade Assurance-protected or Gold-certified suppliers in your app.

## Rate Limits

| Plan | Price | Requests/Month |
|------|-------|----------------|
| Free | $0 | 5,000 |
| Starter | $25 | 100,000 |
| Grow | $75 | 1,000,000 |
| Scale | $150 | 10,000,000 |

## Questions? We have answers.

Reach out anytime. We will solve your query within 1 working day.

[![Contact Us on WhatsApp about Alibaba Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20have%20a%20question%20about%20the%20Alibaba%20Scraper%20API.)

[![Contact Us on Email about Alibaba Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Alibaba%20Scraper%20API%20Question)
