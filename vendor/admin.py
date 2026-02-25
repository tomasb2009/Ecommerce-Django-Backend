from django.contrib import admin

from vendor.models import Vendor


class VendorAdmin(admin.ModelAdmin):
    list_display = ["id", "user"]


admin.site.register(Vendor, VendorAdmin)
