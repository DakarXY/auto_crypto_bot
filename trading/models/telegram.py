from django.contrib.auth.models import User
from django.db import models


class TelegramUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(unique=True)
    telegram_username = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notification_enabled = models.BooleanField(default=True)
    language_code = models.CharField(max_length=10, default='en')
    registration_date = models.DateTimeField(auto_now_add=True)
    last_interaction = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} (Telegram: {self.telegram_username or self.telegram_id})"

    class Meta:
        verbose_name = "Telegram User"
        verbose_name_plural = "Telegram Users"