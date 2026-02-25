from django.db import models
from django.utils.text import slugify
from userauths.models import User


class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.FileField(
        upload_to="vendor", blank=True, null=True, default="vendor.jpg")
    name = models.CharField(
        max_length=100, help_text="Shop Name", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    mobile = models.CharField(
        max_length=100, help_text="Shop Mobile Number", null=True, blank=True)
    active = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(unique=True, max_length=500)

    class Meta:
        verbose_name_plural = "Vendors"
        ordering = ["-date"]

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kargs):
        if not self.slug or self.slug == "":
            base_slug = slugify(self.name) if self.name else "vendor"
            slug = base_slug
            # Ensure uniqueness for slug
            import uuid
            while Vendor.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slug

        super(Vendor, self).save(*args, **kargs)
