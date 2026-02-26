from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import logging

logger = logging.getLogger(__name__)
from django.template.loader import render_to_string

from userauths.models import User
from store.models import Category, Product, Gallery, Specification, Size, Color, Cart, CartOrder, CartOrderItem, ProductFaq, Review, Tax, Wishlist, Notification, Coupon
from store.serializers import ProductSerializer, CategorySerializer, CartSerializer, CartOrderSerializer, CartOrderItemSerializer, CouponSerializer, NotificationSerializer, ReviewSerializer

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework.response import Response

from decimal import Decimal

import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY


def send_notification(user=None, vendor=None, order=None, order_item=None):
    Notification.objects.create(
        user=user, vendor=vendor, order=order, order_item=order_item)


class CategoryListAPIView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]


class ProductDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        slug = self.kwargs["slug"]
        return Product.objects.get(slug=slug)


class CartAPIView(generics.ListCreateAPIView):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kargs):
        payload = request.data

        try:
            product_id = payload.get("product_id")
            user_id = payload.get("user_id", "")
            qty = payload.get("qty", 1)
            price = payload.get("price")
            shipping_amount = payload.get("shipping_amount", 0)
            country = payload.get("country", "US")
            size = payload.get("size", "No Size")
            color = payload.get("color", "No Color")
            cart_id = payload.get("cart_id")

            if not product_id:
                return Response(
                    {"message": "product_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not cart_id:
                return Response(
                    {"message": "cart_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response(
                    {"message": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validar que el producto esté en stock
            if not product.in_stock:
                return Response(
                    {"message": "Product is out of stock"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = None
            if user_id and user_id != "undefined" and user_id != "":
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    user = None

            tax = Tax.objects.filter(country=country).first()
            if tax:
                tax_rate = tax.rate / 100
            else:
                tax_rate = 0

            cart = Cart.objects.filter(cart_id=cart_id, product=product).first()

            if cart:
                cart.product = product
                cart.user = user
                cart.qty = qty
                cart.price = price
                cart.sub_total = Decimal(price) * int(qty)
                cart.shipping_amount = Decimal(shipping_amount) * int(qty)
                cart.tax_fee = int(qty) * Decimal(tax_rate)
                cart.color = color
                cart.size = size
                cart.country = country
                cart.cart_id = cart_id

                service_fee_percentage = 10/100
                cart.service_fee = Decimal(service_fee_percentage) * cart.sub_total

                cart.total = cart.sub_total+cart.shipping_amount+cart.service_fee+cart.tax_fee

                cart.save()

                return Response({"message": "Cart updated Successfully"}, status=status.HTTP_200_OK)
            else:
                cart = Cart()
                cart.product = product
                cart.user = user
                cart.qty = qty
                cart.price = price
                cart.sub_total = Decimal(price) * int(qty)
                cart.shipping_amount = Decimal(shipping_amount) * int(qty)
                cart.tax_fee = int(qty) * Decimal(tax_rate)
                cart.color = color
                cart.size = size
                cart.country = country
                cart.cart_id = cart_id

                service_fee_percentage = 10/100
                cart.service_fee = Decimal(service_fee_percentage) * cart.sub_total

                cart.total = cart.sub_total+cart.shipping_amount+cart.service_fee+cart.tax_fee

                cart.save()
                return Response({"message": "Cart Created Successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error creating/updating cart: {str(e)}", exc_info=True)
            return Response(
                {"message": f"Error processing cart: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CartListView(generics.ListAPIView):
    serializer_class = CartSerializer
    permission_classes = [AllowAny]
    queryset = Cart.objects.all()

    def get_queryset(self):
        cart_id = self.kwargs["cart_id"]
        user_id = self.kwargs.get("user_id")

        if user_id is not None:
            user = User.objects.get(id=user_id)
            queryset = Cart.objects.filter(user=user, cart_id=cart_id)
        else:
            queryset = Cart.objects.filter(cart_id=cart_id)

        return queryset


class CartDetailView(generics.RetrieveAPIView):
    serializer_class = CartSerializer
    permission_classes = [AllowAny]
    lookup_field = "cart_id"

    def get_queryset(self):
        cart_id = self.kwargs["cart_id"]
        user_id = self.kwargs.get("user_id")

        if user_id is not None:
            user = User.objects.get(id=user_id)
            queryset = Cart.objects.filter(user=user, cart_id=cart_id)
        else:
            queryset = Cart.objects.filter(cart_id=cart_id)

        return queryset

    def get(self, request, *args, **kargs):
        queryset = self.get_queryset()

        total_shipping = 0.0
        total_tax = 0.0
        total_service_fee = 0.0
        total_sub_total = 0.0
        total_total = 0.0

        for cart_item in queryset:
            total_shipping += float(self.calculate_shipping(cart_item))
            total_tax += float(self.calculate_tax(cart_item))
            total_service_fee += float(self.calculate_service_fee(cart_item))
            total_sub_total += float(self.calculate_sub_total(cart_item))
            total_total += float(self.calculate_total(cart_item))

        data = {
            "shipping": total_shipping,
            "tax": total_tax,
            "service_fee": total_service_fee,
            "sub_total": total_sub_total,
            "total": total_total,
        }

        return Response(data)

    def calculate_shipping(self, cart_item):
        return cart_item.shipping_amount

    def calculate_tax(self, cart_item):
        return cart_item.tax_fee

    def calculate_service_fee(self, cart_item):
        return cart_item.service_fee

    def calculate_sub_total(self, cart_item):
        return cart_item.sub_total

    def calculate_total(self, cart_item):
        return cart_item.total


class CartItemDeleteAPIView(generics.DestroyAPIView):
    serializer_class = CartSerializer
    lookup_field = "cart_id"

    def get_object(self):
        cart_id = self.kwargs["cart_id"]
        item_id = self.kwargs["item_id"]
        user_id = self.kwargs.get("user_id")

        if user_id:
            user = User.objects.get(id=user_id)
            cart = Cart.objects.get(id=item_id, cart_id=cart_id, user=user)

        else:
            cart = Cart.objects.get(id=item_id, cart_id=cart_id)

        return cart


class CreateOrderAPIView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer
    queryset = CartOrder.objects.all()
    permission_classes = [AllowAny]

    def create(self, request):
        payload = request.data

        full_name = payload["full_name"]
        email = payload["email"]
        mobile = payload["mobile"]
        address = payload["address"]
        city = payload["city"]
        state = payload["state"]
        country = payload["country"]
        cart_id = payload["cart_id"]
        user_id = payload["user_id"]

        try:
            user = User.objects.get(id=user_id)
        except:
            user = None

        cart_items = Cart.objects.filter(cart_id=cart_id)

        total_shipping = Decimal(0.00)
        total_tax = Decimal(0.00)
        total_service_fee = Decimal(0.00)
        total_subtotal = Decimal(0.00)
        total_initial_total = Decimal(0.00)
        total_total = Decimal(0.00)

        order = CartOrder.objects.create(
            buyer=user,
            full_name=full_name,
            email=email,
            mobile=mobile,
            address=address,
            city=city,
            state=state,
            country=country,
        )

        for c in cart_items:
            CartOrderItem.objects.create(
                order=order,
                product=c.product,
                vendor=c.product.vendor,
                qty=c.qty,
                color=c.color,
                size=c.size,
                price=c.price,
                sub_total=c.sub_total,
                shipping_amount=c.shipping_amount,
                service_fee=c.service_fee,
                tax_fee=c.tax_fee,
                total=c.total,
                initial_total=c.total,
            )

            total_shipping += Decimal(c.shipping_amount)
            total_tax += Decimal(c.tax_fee)
            total_service_fee += Decimal(c.service_fee)
            total_subtotal += Decimal(c.sub_total)
            total_initial_total += Decimal(c.total)
            total_total += Decimal(c.total)

            order.vendor.add(c.product.vendor)

        order.sub_total = total_subtotal
        order.shipping_amount = total_shipping
        order.tax_fee = total_tax
        order.service_fee = total_service_fee
        order.initial_total = total_initial_total
        order.total = total_total

        order.save()

        return Response({"message": "Order Created Successfully", "order_oid": order.oid}, status=status.HTTP_201_CREATED)


class CheckoutView(generics.RetrieveAPIView):
    serializer_class = CartOrderSerializer
    lookup_field = "order_oid"

    def get_object(self):
        order_oid = self.kwargs["order_oid"]
        order = CartOrder.objects.get(oid=order_oid)
        return order


class CouponAPIView(generics.CreateAPIView):
    serializer_class = CouponSerializer
    queryset = Coupon.objects.all()
    permission_classes = [AllowAny]

    def create(self, request):
        payload = request.data

        try:
            order_oid = payload.get("order_oid")
            coupon_code = payload.get("coupon_code", "").strip()

            if not order_oid:
                return Response(
                    {"message": "order_oid is required", "icon": "error"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not coupon_code:
                return Response(
                    {"message": "Coupon code is required", "icon": "error"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                order = CartOrder.objects.get(oid=order_oid)
            except CartOrder.DoesNotExist:
                return Response(
                    {"message": "Order not found", "icon": "error"},
                    status=status.HTTP_404_NOT_FOUND
                )

            coupon = Coupon.objects.filter(code=coupon_code).first()

            if not coupon:
                return Response(
                    {"message": "Coupon Does Not Exist", "icon": "error"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validar que el cupón esté activo
            if not coupon.active:
                return Response(
                    {"message": "This coupon is not active", "icon": "error"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            order_items = CartOrderItem.objects.filter(
                order=order, vendor=coupon.vendor)
            
            if not order_items.exists():
                return Response(
                    {"message": "No items found for this vendor in this order", "icon": "error"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Aplicar el cupón a los items que aún no lo tienen
            applied = False
            total_discount = Decimal(0)

            for i in order_items:
                if coupon not in i.coupon.all():
                    # Guardar el total inicial si es la primera vez que se aplica un cupón
                    if i.initial_total == 0 or i.initial_total is None:
                        i.initial_total = i.total

                    # Calcular descuento basado en el total inicial (antes de descuentos)
                    base_total = i.initial_total if i.initial_total > 0 else i.total
                    discount = Decimal(base_total) * Decimal(coupon.discount) / Decimal(100)
                    total_discount += discount

                    i.total -= discount
                    i.sub_total -= discount
                    i.coupon.add(coupon)
                    i.saved += discount

                    i.save()
                    applied = True

            if applied:
                # Actualizar el total de la orden
                if order.initial_total == 0 or order.initial_total is None:
                    order.initial_total = order.total

                order.total -= total_discount
                order.sub_total -= total_discount
                order.saved += total_discount
                order.save()

                return Response(
                    {"message": "Coupon Activated Successfully", "icon": "success"},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"message": "Coupon Already Applied to All Items", "icon": "warning"},
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            logger.error(f"Error applying coupon: {str(e)}", exc_info=True)
            return Response(
                {"message": f"Error applying coupon: {str(e)}", "icon": "error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StripeCheckoutView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = [AllowAny]
    queryset = CartOrder.objects.all()

    def create(self, *args, **kargs):
        order_oid = self.kwargs.get("order_oid")
        
        if not order_oid:
            return Response(
                {"message": "order_oid is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order = CartOrder.objects.get(oid=order_oid)
        except CartOrder.DoesNotExist:
            return Response(
                {"message": "Order Not Found"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=order.email if order.email else None,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": order.full_name or "Order",

                            },
                            "unit_amount": int(float(order.total or 0) * 100)
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url="https://celebrated-parfait-368a98.netlify.app/payment-success/" +
                order.oid + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url='https://celebrated-parfait-368a98.netlify.app/payment-failed/?session_id={CHECKOUT_SESSION_ID}'
            )

            order.stripe_session_id = checkout_session.id
            order.save()

            return redirect(checkout_session.url)
        except stripe.error.StripeError as e:
            return Response({"error": f"Something went wrong creating the checkout session: {str(e)}"})


class PaymentSuccessView(generics.CreateAPIView):
    serializer_class = CartOrderSerializer
    permission_classes = [AllowAny]
    queryset = CartOrder.objects.all()

    def create(self, request, *args, **kargs):
        payload = request.data

        order_oid = payload.get("order_oid")
        session_id = payload.get("session_id")

        if not order_oid:
            return Response(
                {"message": "order_oid is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order = CartOrder.objects.get(oid=order_oid)
        except CartOrder.DoesNotExist:
            return Response(
                {"message": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        order_items = CartOrderItem.objects.filter(order=order)

        if session_id and session_id != "null":
            try:
                session = stripe.checkout.Session.retrieve(session_id)
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving session {session_id}: {str(e)}")
                return Response(
                    {"message": "Error retrieving payment session"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if session.payment_status == "paid":
                if order.payment_status == "pending":
                    order.payment_status = "paid"
                    order.save()

                    # Check email configuration
                    mailersend_token = settings.ANYMAIL.get('MAILERSEND_API_TOKEN', '')
                    if not mailersend_token:
                        logger.warning("MAILERSEND_API_TOKEN not configured. Emails will not be sent.")
                    else:
                        logger.info(f"MailerSend token is configured (length: {len(mailersend_token)})")

                    # Send Notification to customer
                    try:
                        if order.buyer is not None:
                            send_notification(user=order.buyer, order=order)
                    except Exception as e:
                        logger.error(f"Failed to send notification to customer: {str(e)}")

                    # Send Notification to vendors
                    for o in order_items:
                        try:
                            send_notification(
                                vendor=o.vendor, order=order, order_item=o)
                        except Exception as e:
                            logger.error(f"Failed to send notification to vendor {o.vendor.id}: {str(e)}")

                        # Email (solo ítems y total de este vendedor)
                        vendor_order_items = order_items.filter(
                            vendor=o.vendor)
                        vendor_total = sum(i.total for i in vendor_order_items)
                        context = {
                            "order": order,
                            "order_items": order_items,
                            "vendor": o.vendor,
                            "vendor_order_items": vendor_order_items,
                            "vendor_total": vendor_total,
                        }

                        subject = "New Sale"
                        text_body = render_to_string(
                            "email/vendor_sale.txt", context)
                        html_body = render_to_string(
                            "email/vendor_sale.html", context)

                        # Send email to vendor (non-blocking)
                        vendor_email = o.vendor.user.email if o.vendor and o.vendor.user else None
                        if vendor_email:
                            try:
                                logger.info(f"Attempting to send email to vendor: {vendor_email}")
                                
                                msg = EmailMultiAlternatives(
                                    subject=subject,
                                    from_email=settings.DEFAULT_FROM_EMAIL,
                                    to=[vendor_email],
                                    body=text_body,
                                )

                                msg.attach_alternative(html_body, "text/html")
                                
                                # Send email - if it fails, log but continue
                                try:
                                    result = msg.send(fail_silently=False)
                                    logger.info(f"Email sent successfully to vendor {vendor_email}. Result: {result}")
                                except Exception as email_error:
                                    # Log error details but don't break payment flow
                                    error_msg = str(email_error)
                                    logger.error(f"Failed to send email to vendor {o.vendor.id if o.vendor else 'unknown'}: {error_msg}")
                                    
                                    # Specific error messages for common issues
                                    if "401" in error_msg or "Unauthorized" in error_msg or "Unauthenticated" in error_msg:
                                        logger.error("⚠️ MailerSend authentication failed (401). The API token may be expired or invalid. Check your MAILERSEND_API_TOKEN in .env file")
                                    elif "SSL" in error_msg or "SSLError" in error_msg or "SSLEOFError" in error_msg:
                                        logger.error("⚠️ SSL connection error with MailerSend. This may be a temporary network issue. Email will be skipped but payment will continue.")
                                    else:
                                        logger.error(f"⚠️ Email error: {error_msg}")
                                    # Payment continues successfully even if email fails
                            except Exception as e:
                                logger.error(f"Unexpected error preparing email for vendor {o.vendor.id if o.vendor else 'unknown'}: {str(e)}")
                                # Continue with payment processing
                        else:
                            logger.warning(f"No email found for vendor {o.vendor.id if o.vendor else 'unknown'}")

                    # Send email to buyer (non-blocking)
                    if order.email:
                        try:
                            logger.info(f"Attempting to send email to customer: {order.email}")
                            
                            context = {
                                "order": order,
                                "order_items": order_items,
                            }

                            subject = "Order Placed Successfuly"
                            text_body = render_to_string(
                                "email/customer_order_confirmation.txt", context)
                            html_body = render_to_string(
                                "email/customer_order_confirmation.html", context)

                            msg = EmailMultiAlternatives(
                                subject=subject,
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                to=[order.email],
                                body=text_body,
                            )

                            msg.attach_alternative(html_body, "text/html")
                            
                            # Send email - if it fails, log but continue
                            try:
                                result = msg.send(fail_silently=False)
                                logger.info(f"Email sent successfully to customer {order.email}. Result: {result}")
                            except Exception as email_error:
                                # Log error details but don't break payment flow
                                error_msg = str(email_error)
                                logger.error(f"Failed to send email to customer {order.email}: {error_msg}")
                                
                                # Specific error messages for common issues
                                if "401" in error_msg or "Unauthorized" in error_msg or "Unauthenticated" in error_msg:
                                    logger.error("⚠️ MailerSend authentication failed (401). The API token may be expired or invalid. Check your MAILERSEND_API_TOKEN in .env file")
                                elif "SSL" in error_msg or "SSLError" in error_msg or "SSLEOFError" in error_msg:
                                    logger.error("⚠️ SSL connection error with MailerSend. This may be a temporary network issue. Email will be skipped but payment will continue.")
                                else:
                                    logger.error(f"⚠️ Email error: {error_msg}")
                                # Payment continues successfully even if email fails
                        except Exception as e:
                            logger.error(f"Unexpected error preparing email for customer {order.email}: {str(e)}")
                            # Continue with payment processing
                    else:
                        logger.warning(f"No email found for order {order.oid}")

                    return Response({"message": "Payment Successfully"})
                else:
                    return Response({"message": "Already Paid"})
            elif session.payment_status == "unpaid":
                return Response({"message": "UnPaid"})
            elif session.payment_status == "cancelled":
                return Response({"message": "Cancelled"})
            else:
                return Response({"message": "An Error Occured, Try Again..."})
        else:
            # No session_id provided - return error
            return Response(
                {"message": "Session ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )


class ReviewListAPIView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        product_id = self.kwargs["product_id"]
        product = get_object_or_404(Product, id=product_id)
        return Review.objects.filter(product=product).order_by("-date")

    def create(self, request, *args, **kwargs):
        product_id = self.kwargs["product_id"]
        product = get_object_or_404(Product, id=product_id)

        user_id = request.data.get("user_id")
        rating = request.data.get("rating")
        review_text = request.data.get("review", "").strip()

        if not user_id:
            return Response(
                {"error": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not review_text:
            return Response(
                {"error": "review is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if rating is None or int(rating) not in (1, 2, 3, 4, 5):
            return Response(
                {"error": "rating must be between 1 and 5"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_object_or_404(User, id=user_id)
        rating = int(rating)

        review = Review.objects.create(
            user=user,
            product=product,
            rating=rating,
            review=review_text,
        )
        serializer = ReviewSerializer(review, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SearchProudctAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Obtener el texto de búsqueda (puede venir vacío o como None)
        query = (self.request.GET.get("query") or "").strip()

        # Base: todos los productos publicados (status case-insensitive)
        products = Product.objects.filter(status__iexact="published")

        # Si hay query, filtrar por título que contenga el texto
        if query:
            products = products.filter(title__icontains=query)

        return products.order_by("-id")
