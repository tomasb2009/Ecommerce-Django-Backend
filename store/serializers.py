from rest_framework import serializers

from store.models import Category, Product, Gallery, Specification, Size, Color, Cart, CartOrder, CartOrderItem, ProductFaq, Review, Wishlist, Notification, Coupon

from vendor.models import Vendor


class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):

    class Meta:
        model = Product
        fields = "__all__"


class GallerySerializer(serializers.ModelSerializer):

    class Meta:
        model = Gallery
        fields = "__all__"


class SpecificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Specification
        fields = "__all__"


class SizeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Size
        fields = "__all__"


class ColorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Color
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):

    gallery = GallerySerializer(many=True, read_only=True)
    color = ColorSerializer(many=True, read_only=True)
    specification = SpecificationSerializer(many=True, read_only=True)
    size = SizeSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "image",
            "description",
            "category",
            "price",
            "oldPrice",
            "shipping_amount",
            "stock_qty",
            "in_stock",
            "status",
            "featured",
            "views",
            "rating",
            "vendor",
            "gallery",
            "color",
            "specification",
            "size",
            "product_rating",
            "rating_count",
            "pid",
            "slug",
            "date"
        ]
        read_only_fields = ["id", "pid", "slug", "date", "views", "rating", "product_rating", "rating_count", "vendor"]

    def __init__(self, *args, **kargs):
        super(ProductSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
            # Make vendor not required during creation (it's assigned in the view)
            if 'vendor' in self.fields:
                self.fields['vendor'].required = False
        else:
            self.Meta.depth = 3


class CartSerializer(serializers.ModelSerializer):

    class Meta:
        model = Cart
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(CartSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class CartOrderItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = CartOrderItem
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(CartOrderItemSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class CartOrderSerializer(serializers.ModelSerializer):
    orderitem = CartOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = CartOrder
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(CartOrderSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class ProductFaqSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductFaq
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(ProductFaqSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class VendorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Vendor
        fields = "__all__"
        read_only_fields = ["id", "date", "slug", "user"]

    def __init__(self, *args, **kargs):
        super(VendorSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method in ["POST", "PATCH", "PUT"]:
            self.Meta.depth = 0
            # Make user and slug not required during update (they're set automatically)
            if 'user' in self.fields:
                self.fields['user'].required = False
            if 'slug' in self.fields:
                self.fields['slug'].required = False
        else:
            self.Meta.depth = 3


class ReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = Review
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(ReviewSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class WishlistSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wishlist
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(WishlistSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class CouponSerializer(serializers.ModelSerializer):

    class Meta:
        model = Coupon
        fields = "__all__"
        read_only_fields = ["id", "date", "vendor"]

    def __init__(self, *args, **kargs):
        super(CouponSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method in ["POST", "PATCH", "PUT"]:
            self.Meta.depth = 0
            # Make vendor not required during update (it's set from URL)
            if 'vendor' in self.fields:
                self.fields['vendor'].required = False
        else:
            self.Meta.depth = 1


class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = "__all__"

    def __init__(self, *args, **kargs):
        super(NotificationSerializer, self).__init__(*args, **kargs)

        request = self.context.get("request")

        if request and request.method == "POST":
            self.Meta.depth = 0
        else:
            self.Meta.depth = 3


class SummarySerializer(serializers.Serializer):
    products = serializers.IntegerField()
    orders = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class EarningSerializer(serializers.Serializer):
    monthly_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class CouponSummarySerializer(serializers.Serializer):
    total_coupons = serializers.IntegerField()
    active_coupons = serializers.IntegerField()


class NotificationSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    unseen = serializers.IntegerField()


class RevenueSerializer(serializers.Serializer):
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
