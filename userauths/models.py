from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save

from shortuuid.django_fields import ShortUUIDField


class User(AbstractUser):
    username = models.CharField(unique=True, max_length=100)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=100, null=True, blank=True)
    otp = models.CharField(max_length=100, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    def save(self, *args, **kargs):
        email_username, mobile = self.email.split("@")

        if self.full_name == "" or self.full_name == None:
            self.full_name = email_username

        if self.username == "" or self.username == None:
            self.username = email_username

        super(User, self).save(*args, **kargs)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.FileField(
        upload_to="image", default="default/default-user.jpg", null=True, blank=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    about = models.CharField(max_length=300, null=True, blank=True)
    gender = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    adress = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    pid = ShortUUIDField(unique=True, length=10,
                         max_length=20, alphabet="abcdefghijk")

    def __str__(self):
        if self.full_name:
            return str(self.full_name)
        else:
            return str(self.user.full_name)

    def save(self, *args, **kargs):

        if self.full_name == "" or self.full_name == None:
            self.full_name = self.user.full_name

        super(Profile, self).save(*args, **kargs)


def create_user_profile(sender, instance, created, **kargs):
    if created:
        Profile.objects.create(user=instance)


def save_user_profile(sender, instance, **kargs):
    instance.profile.save()


def create_user_vendor(sender, instance, created, **kargs):
    if created:
        # Import here to avoid circular imports
        from vendor.models import Vendor
        # Check if vendor already exists (to avoid duplicates)
        if not Vendor.objects.filter(user=instance).exists():
            vendor_name = instance.full_name if instance.full_name else instance.username
            Vendor.objects.create(
                user=instance,
                name=vendor_name,
                active=True  # Auto-activate vendor
            )


post_save.connect(create_user_profile, sender=User)
post_save.connect(save_user_profile, sender=User)
post_save.connect(create_user_vendor, sender=User)
