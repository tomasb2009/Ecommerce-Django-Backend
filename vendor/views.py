from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import models
from django.db.models.functions import ExtractMonth

from vendor.models import Vendor
from userauths.models import User
from store.models import Category, Product, Gallery, Specification, Size, Color, Cart, CartOrder, CartOrderItem, ProductFaq, Review, Tax, Wishlist, Notification, Coupon
from store.serializers import (
    CartOrderSerializer,
    CouponSerializer,
    CouponSummarySerializer,
    EarningSerializer,
    NotificationSerializer,
    ProductSerializer,
    ReviewSerializer,
    SummarySerializer,
    VendorSerializer,
    NotificationSummarySerializer,
    RevenueSerializer,
)

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from rest_framework.response import Response

from decimal import Decimal
import json
import logging

import stripe
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DashboardStatsAPIView(generics.ListAPIView):
    serializer_class = SummarySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]

        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return [{"products": 0, "orders": 0, "revenue": 0}]

        # Calculate the summary values
        product_count = Product.objects.filter(vendor=vendor).count()
        # CartOrder.vendor is ManyToMany, so we need to filter through the relationship
        order_count = CartOrder.objects.filter(
            vendor__in=[vendor], payment_status="paid").distinct().count()

        revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F("sub_total") + models.F("shipping_amount")))["total_revenue"] or 0

        return [
            {
                "products": product_count,
                "orders": order_count,
                "revenue": revenue,
            }
        ]

    def list(self, *args, **kargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


@api_view(["GET"])
def MonthlyOrderChartAPIView(request, vendor_id):
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response([], status=status.HTTP_404_NOT_FOUND)
    
    orders = CartOrder.objects.filter(vendor__in=[vendor], payment_status="paid").distinct()
    orders_by_month = orders.annotate(month=ExtractMonth("date")).values(
        "month").annotate(orders=models.Count("id")).order_by("month")

    return Response(orders_by_month)


@api_view(["GET"])
def MonthlyProductChartAPIView(request, vendor_id):
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response([], status=status.HTTP_404_NOT_FOUND)
    
    products = Product.objects.filter(vendor=vendor)
    products_by_month = products.annotate(month=ExtractMonth("date")).values(
        "month").annotate(product=models.Count("id")).order_by("month")

    return Response(products_by_month)


class ProductAPIView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Product.objects.none()

        return Product.objects.filter(vendor=vendor).order_by("-id")

    def create(self, request, *args, **kwargs):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Response(
                {"detail": f"Vendor with id {vendor_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(data=request.data, context={'request': request, 'vendor': vendor})
        serializer.is_valid(raise_exception=True)
        product = serializer.save(vendor=vendor)

        # Handle specifications
        raw_specs = request.data.get("specifications")
        if raw_specs:
            try:
                specs = json.loads(raw_specs) if isinstance(raw_specs, str) else raw_specs
                if isinstance(specs, list):
                    spec_objects = []
                    for spec in specs:
                        title = (spec.get("title") or "").strip()
                        content = (spec.get("content") or "").strip()
                        if title and content:
                            spec_objects.append(
                                Specification(product=product, title=title, content=content)
                            )
                        elif title and not content:
                            logger.warning(f"Specification with title '{title}' missing content, skipping")
                    if spec_objects:
                        Specification.objects.bulk_create(spec_objects)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        # Handle gallery images (multiple images)
        gallery_images = request.FILES.getlist("gallery_images")
        if gallery_images:
            gallery_objects = []
            for img in gallery_images:
                if img:
                    gallery_objects.append(
                        Gallery(product=product, image=img, active=True)
                    )
            if gallery_objects:
                Gallery.objects.bulk_create(gallery_objects)

        # Handle colors
        raw_colors = request.data.get("colors")
        if raw_colors:
            try:
                colors = json.loads(raw_colors) if isinstance(raw_colors, str) else raw_colors
                if isinstance(colors, list):
                    color_objects = []
                    for color_data in colors:
                        name = (color_data.get("name") or "").strip()
                        color_code = (color_data.get("color_code") or "").strip()
                        if name and color_code:
                            color_objects.append(
                                Color(product=product, name=name, color_code=color_code)
                            )
                    if color_objects:
                        Color.objects.bulk_create(color_objects)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        # Handle sizes
        raw_sizes = request.data.get("sizes")
        if raw_sizes:
            try:
                sizes = json.loads(raw_sizes) if isinstance(raw_sizes, str) else raw_sizes
                if isinstance(sizes, list):
                    size_objects = []
                    for size_data in sizes:
                        name = (size_data.get("name") or "").strip()
                        price = size_data.get("price", 0)
                        if name:
                            try:
                                price_decimal = Decimal(str(price))
                            except (ValueError, TypeError):
                                price_decimal = Decimal("0.00")
                            size_objects.append(
                                Size(product=product, name=name, price=price_decimal)
                            )
                    if size_objects:
                        Size.objects.bulk_create(size_objects)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class VendorProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        product_id = self.kwargs["product_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
            product = Product.objects.get(id=product_id, vendor=vendor)
            return product
        except (Vendor.DoesNotExist, Product.DoesNotExist):
            raise Http404("Product not found")
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # Handle specifications update
        raw_specs = request.data.get("specifications")
        if raw_specs is not None:
            try:
                Specification.objects.filter(product=product).delete()
                specs = json.loads(raw_specs) if isinstance(raw_specs, str) else raw_specs
                if isinstance(specs, list):
                    spec_objects = []
                    for spec in specs:
                        title = (spec.get("title") or "").strip()
                        content = (spec.get("content") or "").strip()
                        if title and content:
                            spec_objects.append(
                                Specification(product=product, title=title, content=content)
                            )
                        elif title and not content:
                            logger.warning(f"Specification with title '{title}' missing content, skipping")
                    if spec_objects:
                        Specification.objects.bulk_create(spec_objects)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                logger.error(f"Error updating specifications: {str(e)}")

        # Handle gallery images update
        gallery_images = request.FILES.getlist("gallery_images")
        if gallery_images:
            gallery_objects = []
            for img in gallery_images:
                if img:
                    gallery_objects.append(
                        Gallery(product=product, image=img, active=True)
                    )
            if gallery_objects:
                Gallery.objects.bulk_create(gallery_objects)

        # Handle colors update
        raw_colors = request.data.get("colors")
        if raw_colors is not None:
            try:
                Color.objects.filter(product=product).delete()
                colors = json.loads(raw_colors) if isinstance(raw_colors, str) else raw_colors
                if isinstance(colors, list):
                    color_objects = []
                    for color_data in colors:
                        name = (color_data.get("name") or "").strip()
                        color_code = (color_data.get("color_code") or "").strip()
                        if name and color_code:
                            color_objects.append(
                                Color(product=product, name=name, color_code=color_code)
                            )
                    if color_objects:
                        Color.objects.bulk_create(color_objects)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                logger.error(f"Error updating colors: {str(e)}")

        # Handle sizes update
        raw_sizes = request.data.get("sizes")
        if raw_sizes is not None:
            try:
                Size.objects.filter(product=product).delete()
                sizes = json.loads(raw_sizes) if isinstance(raw_sizes, str) else raw_sizes
                if isinstance(sizes, list):
                    size_objects = []
                    for size_data in sizes:
                        name = (size_data.get("name") or "").strip()
                        price = size_data.get("price", 0)
                        if name:
                            try:
                                price_decimal = Decimal(str(price))
                            except (ValueError, TypeError):
                                price_decimal = Decimal("0.00")
                            size_objects.append(
                                Size(product=product, name=name, price=price_decimal)
                            )
                    if size_objects:
                        Size.objects.bulk_create(size_objects)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                logger.error(f"Error updating sizes: {str(e)}")

        return Response(serializer.data)


class OrderAPIView(generics.ListAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return CartOrder.objects.none()

        # CartOrder.vendor is ManyToMany, so we need to filter through the relationship
        return CartOrder.objects.filter(vendor__in=[vendor], payment_status="paid").distinct().order_by("-id")


class OrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        order_oid = self.kwargs["order_oid"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
            order = CartOrder.objects.get(oid=order_oid, payment_status="paid")
            # Verify that this vendor is associated with this order
            if vendor not in order.vendor.all():
                raise Http404("Order not found for this vendor")
            return order
        except (Vendor.DoesNotExist, CartOrder.DoesNotExist):
            raise Http404("Order not found")


class RevenueAPIView(generics.ListAPIView):
    serializer_class = RevenueSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return [{"total_revenue": 0}]

        total_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F("sub_total") + models.F("shipping_amount")))["total_revenue"] or 0
        return [{"total_revenue": total_revenue}]

    def list(self, *args, **kargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class FilterProductAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Product.objects.none()

        filter = self.request.GET.get("filter")

        if filter == "published":
            products = Product.objects.filter(
                vendor=vendor, status="published")

        elif filter == "in_review":
            products = Product.objects.filter(
                vendor=vendor, status="in_review")
        elif filter == "draft":
            products = Product.objects.filter(vendor=vendor, status="draft")
        elif filter == "disabled":
            products = Product.objects.filter(vendor=vendor, status="disabled")
        else:
            products = Product.objects.filter(vendor=vendor)

        return products


class EarningAPIView(generics.ListAPIView):
    serializer_class = EarningSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return [{"monthly_revenue": 0, "total_revenue": 0}]

        one_month_ago = datetime.today() - timedelta(days=28)
        monthly_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid", date__gt=one_month_ago).aggregate(
            total_revenue=models.Sum(models.F("sub_total") + models.F("shipping_amount")))["total_revenue"] or 0

        total_revenue = CartOrderItem.objects.filter(vendor=vendor, order__payment_status="paid").aggregate(
            total_revenue=models.Sum(models.F("sub_total") + models.F("shipping_amount")))["total_revenue"] or 0

        return [{
            "monthly_revenue": monthly_revenue,
            "total_revenue": total_revenue,
        }]

    def list(self, *args, **kargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


@api_view(["GET"])
def MonthlyEarningTracker(request, vendor_id):
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response([], status=status.HTTP_404_NOT_FOUND)
    
    monthly_earning_tracker = (
        CartOrderItem.objects
        .filter(vendor=vendor, order__payment_status="paid")
        .annotate(month=ExtractMonth("date"))
        .values("month")
        .annotate(sales_count=models.Sum("qty"), total_earning=models.Sum(models.F("sub_total") + models.F("shipping_amount"))).order_by("-month")
    )

    return Response(monthly_earning_tracker)


class ReviewListAPIView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Review.objects.none()
        return Review.objects.filter(product__vendor=vendor)


class ReviewDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        review_id = self.kwargs["review_id"]

        try:
            vendor = Vendor.objects.get(id=vendor_id)
            review = Review.objects.get(id=review_id, product__vendor=vendor)
            return review
        except (Vendor.DoesNotExist, Review.DoesNotExist):
            raise Http404("Review not found")


class CouponListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CouponSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Coupon.objects.none()

        return Coupon.objects.filter(vendor=vendor)

    def create(self, request, *args, **kargs):
        payload = request.data
        vendor_id = self.kwargs["vendor_id"]

        code = payload.get("code")
        discount = payload.get("discount")
        active = payload.get("active", False)

        if not code:
            return Response({"detail": "code is required"}, status=status.HTTP_400_BAD_REQUEST)
        if discount is None:
            return Response({"detail": "discount is required"}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(active, str):
            active = active.strip().lower() in ("true", "1", "yes", "on")
        else:
            active = bool(active)

        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Response(
                {"detail": f"Vendor with id {vendor_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        coupon = Coupon.objects.create(
            vendor=vendor,
            code=code,
            discount=int(discount),
            active=active,
        )

        serializer = CouponSerializer(coupon, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CouponDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CouponSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        coupon_id = self.kwargs["coupon_id"]

        try:
            vendor = Vendor.objects.get(id=vendor_id)
            coupon = Coupon.objects.get(vendor=vendor, id=coupon_id)
            return coupon
        except (Vendor.DoesNotExist, Coupon.DoesNotExist):
            raise Http404("Coupon not found")
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Manejar el campo active correctamente
        data = request.data.copy()
        if 'active' in data:
            active_value = data.get('active')
            if isinstance(active_value, str):
                data['active'] = active_value.strip().lower() in ("true", "1", "yes", "on")
            else:
                data['active'] = bool(active_value)
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class CouponStatsAPIView(generics.ListAPIView):
    serializer_class = CouponSummarySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return [{"total_coupons": 0, "active_coupons": 0}]

        total_coupons = Coupon.objects.filter(vendor=vendor).count()

        active_coupons = Coupon.objects.filter(
            vendor=vendor, active=True).count()

        return [{
            "total_coupons": total_coupons,
            "active_coupons": active_coupons
        }]

    def list(self, *args, **kargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


class VendorNotificationAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return Notification.objects.none()

        seen = self.request.GET.get("seen")
        queryset = Notification.objects.filter(vendor=vendor).order_by("-date")
        if seen is None:
            return queryset.filter(seen=False)

        if str(seen).strip().lower() in ("true", "1", "yes", "on"):
            return queryset.filter(seen=True)
        if str(seen).strip().lower() in ("false", "0", "no", "off"):
            return queryset.filter(seen=False)
        return queryset


class MarkVendorNotificationAsSeen(generics.RetrieveAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        noti_id = self.kwargs["noti_id"]

        try:
            vendor = Vendor.objects.get(id=vendor_id)
            noti = Notification.objects.get(id=noti_id, vendor=vendor)

            if not noti.seen:
                noti.seen = True
                noti.save()

            return noti
        except (Vendor.DoesNotExist, Notification.DoesNotExist):
            raise Http404("Notification not found")


class VendorNotificationSummaryAPIView(generics.ListAPIView):
    serializer_class = NotificationSummarySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            vendor = Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            return [{"total": 0, "unseen": 0}]

        total = Notification.objects.filter(vendor=vendor).count()
        unseen = Notification.objects.filter(vendor=vendor, seen=False).count()
        return [{"total": total, "unseen": unseen}]

    def list(self, *args, **kargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class VendorShopAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = VendorSerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        vendor_id = self.kwargs["vendor_id"]
        try:
            return Vendor.objects.get(id=vendor_id)
        except Vendor.DoesNotExist:
            raise Http404("Vendor not found")
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
