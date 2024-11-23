import asyncio

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import render

from .models.wallet import Wallet
from .models.provider_configs import BSCConfig
from .models.config import AutoTradingConfig
from .models.currency import Currency
from .models.telegram import TelegramUser
from .models.trade import Trade
from .services.bsc_trade import BSCTradingService


ACTION_CHECKBOX_NAME = "select_across"


@admin.register(AutoTradingConfig)
class AutoTradingConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Trading Parameters", {
            "fields": ("max_active_trades", "trade_amount", "min_liquidity_usd", "max_transactions_count", "min_transactions_count", "provider")
        }),
        ("Price Targets", {
            "fields": ("max_price_drop_percent", "profit_target_multiplier")
        }),
        ("Time Intervals", {
            "fields": ("price_check_interval", )
        }),
        ("Transaction Settings", {
            "fields": ("slippage_percent", "gas_limit")
        }),
        ("General", {
            "fields": ("trading_enabled",)
        })
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        """Prevent creating multiple configurations"""
        return not AutoTradingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the configuration"""
        return False

class SellTradeForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    reason = forms.ChoiceField(
        choices=[
            ("MANUAL", "Manual sell"),
            ("DROP_FROM_PEAK", "Price dropped from peak"),
            ("BELOW_ENTRY", "Price below entry"),
            ("PROFIT_TARGET", "Profit target reached")
        ],
        label="Sell Reason"
    )
    amount = forms.DecimalField(decimal_places=2)

class BuyCurrencyForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    amount = forms.DecimalField(
        min_value=1,
        max_value=1000,
        decimal_places=2,
        label="Amount USDT"
    )

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = [
        "currency", "status", "buy_amount", "sell_amount", "wallet",
        "profit_loss_percentage", "buy_timestamp", "sell_timestamp"
    ]
    list_filter = ["status", "sell_reason", "buy_timestamp"]
    search_fields = ["currency__symbol", "currency__address"]
    readonly_fields = ["profit_loss", "profit_loss_percentage"]
    actions = ["sell_trades"]

    def sell_trades(self, request, queryset):
        """Action to sell selected trades"""
        form = None

        if "apply" in request.POST:
            form = SellTradeForm(request.POST)

            if form.is_valid():
                reason = form.cleaned_data["reason"]

                success_count = 0
                error_count = 0

                for trade in queryset:
                    if trade.status != "BOUGHT":
                        self.message_user(
                            request,
                            f"Trade {trade.id} is not in BOUGHT status",
                            messages.WARNING
                        )
                        continue

                    try:
                        trader = BSCTradingService(trade.currency.address)

                        # Run sell in sync context
                        asyncio.get_event_loop().run_until_complete(
                            trader.sell(trade.buy_amount)
                        )
                        trade.sell_reason = reason
                        trade.save()
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        self.message_user(
                            request,
                            f"Error selling trade {trade.id}: {str(e)}",
                            messages.ERROR
                        )

                if success_count:
                    self.message_user(
                        request,
                        f"Successfully sold {success_count} trades",
                        messages.SUCCESS
                    )
                if error_count:
                    self.message_user(
                        request,
                        f"Failed to sell {error_count} trades",
                        messages.ERROR
                    )
                return None

        if not form:
            form = SellTradeForm(initial={
                "_selected_action": request.POST.getlist()
            })

        return render(
            request,
            "admin/sell_trades.html",
            context={
                "trades": queryset,
                "form": form,
                "title": "Sell trades"
            }
        )
    sell_trades.short_description = "Sell selected trades"

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "address", "status", "price_first_seen",
        "current_price", "created_at"
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["symbol", "address"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["buy_currencies"]

    def buy_currencies(self, request, queryset):
        """Action to buy selected currencies"""
        form = None

        if "apply" in request.POST:
            form = BuyCurrencyForm(request.POST)

            if form.is_valid():
                amount = form.cleaned_data["amount"]

                success_count = 0
                error_count = 0

                for currency in queryset:
                    trader = BSCTradingService(currency.address)
                    if currency.status not in ["NEW", "ANALYZING"]:
                        self.message_user(
                            request,
                            f"Currency {currency.symbol} is not in NEW or ANALYZING status",
                            messages.WARNING
                        )
                        continue

                    try:
                        # Run buy in sync context
                        asyncio.get_event_loop().run_until_complete(
                            trader.buy(amount=amount)
                        )
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        self.message_user(
                            request,
                            f"Error buying currency {currency.symbol}: {str(e)}",
                            messages.ERROR
                        )

                if success_count:
                    self.message_user(
                        request,
                        f"Successfully bought {success_count} currencies",
                        messages.SUCCESS
                    )
                if error_count:
                    self.message_user(
                        request,
                        f"Failed to buy {error_count} currencies",
                        messages.ERROR
                    )
                return None

        if not form:
            form = BuyCurrencyForm(initial={
                "_selected_action": request.POST.getlist(ACTION_CHECKBOX_NAME)
            })

        return render(
            request,
            "admin/buy_currencies.html",
            context={
                "currencies": queryset,
                "form": form,
                "title": "Buy currencies"
            }
        )
    buy_currencies.short_description = "Buy selected currencies"

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = [
        "user", "telegram_username", "telegram_id",
        "is_active", "notification_enabled", "registration_date"
    ]
    list_filter = ["is_active", "notification_enabled", "registration_date"]
    search_fields = ["user__username", "telegram_username", "telegram_id"]
    readonly_fields = ["registration_date", "last_interaction"]

    actions = ["enable_notifications", "disable_notifications"]

    def enable_notifications(self, request, queryset):
        queryset.update(notification_enabled=True)

    enable_notifications.short_description = "Enable notifications for selected users"

    def disable_notifications(self, request, queryset):
        queryset.update(notification_enabled=False)

    disable_notifications.short_description = "Disable notifications for selected users"

from django.contrib import admin


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("address", "currency_symbol")
    search_fields = ("address", "currency_symbol")


class BSCConfigForm(forms.ModelForm):
    rpc_nodes = forms.CharField(widget=forms.Textarea(attrs={'cols': 80, 'rows': 20}), help_text="Delimiter is ' ' (space)")
    known_tokens = forms.CharField(widget=forms.Textarea, help_text="Example: 'USDT,<addr> WBNB,<addr>'")

    class Meta:
        model = BSCConfig
        exclude = []

@admin.register(BSCConfig)
class BSCConfigAdmin(admin.ModelAdmin):
    form = BSCConfigForm
    list_display = ("wallet", "router_address")
    search_fields = ("wallet", "router_address")

    def has_add_permission(self, request):
        """Prevent creating multiple configurations"""
        return not BSCConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the configuration"""
        return False