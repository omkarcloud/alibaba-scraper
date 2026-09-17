"""Marshmallow request schemas for every /alibaba/* route.

Generic fields (strings, flags, pages, choices, comma lists, ISO codes,
urls, the id-or-link `RefField`) live in the shared top-level
schema_fields.py; this module only adds the Alibaba resolvers, the option
tables and the per-route schemas. Every schema's load() output is the
kwargs dict its endpoint function takes.
"""
from marshmallow import ValidationError, post_load, validate, validates_schema

from schema_fields import (
    BaseSchema, ChoiceField, CommaListField, CountryCodeField, CurrencyField, Flag,
    PageField, PageSizeField, Price, PositiveInt, QueryField, Quantity, RefField,
    StrippedString, UrlField, load_query,
)
from alibaba import refs
from alibaba.search import IMAGE_MAX_PAGE, REVIEW_SCORE_OPTIONS, SHIPS_FROM_OPTIONS, SORT_OPTIONS, MAX_PAGE
from alibaba.supplier import PRODUCT_SORT_OPTIONS, PRODUCTS_MAX_PAGE, REVIEWS_MAX_PAGE_SIZE


# ---- alibaba id-or-link fields --------------------------------------------------

class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product_ref)


class SupplierRefField(RefField):
    resolver = staticmethod(refs.resolve_supplier_ref)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category_ref)


class ImageRefField(RefField):
    """Photo URL to upload, OR the `image_path` a previous response returned."""
    resolver = staticmethod(refs.resolve_image_ref)


class SupplierOrCompanyIdField(RefField):
    """Store subdomain / link, OR a numeric company id (reviews only)."""

    @staticmethod
    def resolver(value):
        if value.isdigit():
            return int(value)
        return refs.resolve_supplier_ref(value)


class RegionField(StrippedString):
    """Crop box 'x,y,width,height' in pixels of the uploaded image."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        value = value.replace(" ", "")
        parts = value.split(",")
        if len(parts) != 4 or not all(p.isdigit() for p in parts):
            raise ValidationError("Must be 'x,y,width,height' pixel coordinates.")
        return value


def _reviews_page_size():
    return PageSizeField(default=10, max_size=REVIEWS_MAX_PAGE_SIZE)


# ---- products ----------------------------------------------------------------

class _SearchFilters(BaseSchema):
    page = PageField(max_page=MAX_PAGE)
    sort_by = ChoiceField(list(SORT_OPTIONS), load_default="best_match")
    min_price = Price()
    max_price = Price()
    min_moq = Quantity()
    max_moq = Quantity()
    min_review_score = ChoiceField(REVIEW_SCORE_OPTIONS)
    supplier_country = CountryCodeField()
    trade_assurance = Flag()
    verified_supplier = Flag()
    verified_pro = Flag()
    alibaba_guaranteed = Flag()
    free_sample = Flag()
    ships_from = ChoiceField([k for k in SHIPS_FROM_OPTIONS if k != "any"])
    delivery_days = PositiveInt(max_value=90)
    supplier_certifications = CommaListField()
    product_certifications = CommaListField()
    currency = CurrencyField()

    @validates_schema
    def _ranges(self, data, **kwargs):
        if data.get("min_price") is not None and data.get("max_price") is not None \
                and data["min_price"] > data["max_price"]:
            raise ValidationError("min_price must be <= max_price.", "min_price")
        if data.get("min_moq") is not None and data.get("max_moq") is not None \
                and data["min_moq"] > data["max_moq"]:
            raise ValidationError("min_moq must be <= max_moq.", "min_moq")


class ProductSearchSchema(_SearchFilters):
    query = QueryField()
    category = CategoryRefField(required=False, load_default=None)

    @post_load
    def _rename(self, data, **kwargs):
        data["category_id"] = data.pop("category", None)
        return data


class ProductsByCategorySchema(_SearchFilters):
    category = CategoryRefField()
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))

    @post_load
    def _rename(self, data, **kwargs):
        data["category_id"] = data.pop("category")
        return data


class ImageSearchSchema(BaseSchema):
    image = ImageRefField()
    page = PageField(max_page=IMAGE_MAX_PAGE)
    category = CategoryRefField(required=False, load_default=None)
    region = RegionField(required=False, load_default=None)

    @post_load
    def _rename(self, data, **kwargs):
        data["category_id"] = data.pop("category", None)
        return data


class ProductDetailsSchema(BaseSchema):
    product = ProductRefField()
    currency = CurrencyField()


class ProductReviewsSchema(BaseSchema):
    product = ProductRefField()
    page = PageField(max_page=10000)
    page_size = _reviews_page_size()


# ---- suppliers ---------------------------------------------------------------

class SupplierSearchSchema(BaseSchema):
    query = QueryField()
    page = PageField(max_page=MAX_PAGE)
    supplier_country = CountryCodeField()
    verified_supplier = Flag()
    verified_pro = Flag()
    trade_assurance = Flag()
    supplier_certifications = CommaListField()


class SupplierDetailsSchema(BaseSchema):
    supplier = SupplierRefField()


class SupplierProductsSchema(BaseSchema):
    supplier = SupplierRefField()
    page = PageField(max_page=PRODUCTS_MAX_PAGE)
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))
    sort_by = ChoiceField(list(PRODUCT_SORT_OPTIONS), load_default="newest")
    currency = CurrencyField()


class SupplierReviewsSchema(BaseSchema):
    supplier = SupplierOrCompanyIdField()
    page = PageField(max_page=10000)
    page_size = _reviews_page_size()


# ---- discovery ---------------------------------------------------------------

class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = PageSizeField(default=10, max_size=20)


class TrendingSchema(BaseSchema):
    limit = PageSizeField(default=10, max_size=20)


class CategoriesSchema(BaseSchema):
    parent = CategoryRefField(required=False, load_default=None)


__all__ = [name for name in globals() if name.endswith("Schema")] + ["load_query"]
