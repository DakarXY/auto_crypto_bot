import logging
import uuid
from asgiref.sync import sync_to_async
from typing import Optional, Tuple

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from ..models.telegram import TelegramUser

logger = logging.getLogger('trading')

AWAITING_EMAIL = 1
AWAITING_USERNAME = 2
CONFIRM_REGISTRATION = 3


class TelegramAuthService:
    def __init__(self):
        self.registration_timeout = 300  # 5 minutes

    async def check_auth(self, telegram_id: int) -> bool:
        """
        Check if user is authenticated and active
        """
        try:
            user = await self.get_telegram_user(telegram_id)
            if not user:
                logger.info(f"User {telegram_id} not registered")
                return False

            if not user.is_active:
                logger.info(f"User {telegram_id} is inactive")
                return False

            # Update last interaction
            await user.asave(update_fields=['last_interaction'])
            return True

        except Exception as e:
            logger.error(f"Error checking auth for {telegram_id}: {e}")
            return False

    @staticmethod
    async def get_telegram_user(telegram_id: int) -> Optional[TelegramUser]:
        """
        Get telegram user by telegram_id
        """
        try:
            user = await TelegramUser.objects.select_related("user").aget(
                telegram_id=telegram_id
            )
            return user
        except ObjectDoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting telegram user {telegram_id}: {e.__traceback__}")
            return None

    async def verify_admin(self, telegram_id: int) -> bool:
        """
        Check if user is admin
        """
        try:
            user = await self.get_telegram_user(telegram_id)
            if not user:
                return False

            return user.user.is_staff and user.user.is_active

        except Exception as e:
            logger.error(f"Error verifying admin {telegram_id}: {e}")
            return False

    def auth_required(self, func):
        """
        Decorator to check if user is authenticated
        """

        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await self.check_auth(update.effective_user.id):
                await update.message.reply_text(
                    "You need to register first! Use /register command."
                )
                return
            return await func(update, context)

        return wrapper

    def admin_required(self, func):
        """
        Decorator to check if user is admin
        """

        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await self.verify_admin(update.effective_user.id):
                await update.message.reply_text(
                    "This command is only available for administrators."
                )
                return
            return await func(update, context)

        return wrapper

    # async def register_user(
    #         self,
    #         telegram_id: int,
    #         username: str,
    #         email: str,
    #         telegram_username: Optional[str] = None
    # ) -> Tuple[bool, str]:
    #     """
    #     Register new user
    #     Returns (success, message)
    #     """
    #     try:
    #         # Check if already registered
    #         if await self.get_telegram_user(telegram_id):
    #             return False, "You are already registered!"
    #
    #         # Generate random password
    #         password = str(uuid.uuid4())
    #
    #         # Create Django user
    #         user = User.objects.create_user(
    #             username=username,
    #             email=email,
    #             password=password
    #         )
    #
    #         # Create telegram user
    #         await TelegramUser.objects.acreate(
    #             user=user,
    #             telegram_id=telegram_id,
    #             telegram_username=telegram_username,
    #             is_active=True,
    #             notification_enabled=True
    #         )
    #
    #         return True, f"""
    #             Registration successful! 🎉
    #
    #             Your account details:
    #             Username: {username}
    #             Password: {password}
    #
    #             Please save these credentials securely!
    #             You can use them to access the web interface.
    #
    #             Use /help to see available commands.
    #         """
    #     except Exception as e:
    #         logger.error(f"Error registering user {telegram_id}: {e}")
    #         return False, "Registration failed. Please try again later."

    async def deactivate_user(self, telegram_id: int) -> bool:
        """
        Deactivate user account
        """
        try:
            user = await self.get_telegram_user(telegram_id)
            if not user:
                return False

            user.is_active = False
            await user.asave(update_fields=['is_active'])

            # Also deactivate Django user
            django_user = user.user
            django_user.is_active = False
            await django_user.asave(update_fields=['is_active'])

            return True

        except Exception as e:
            logger.error(f"Error deactivating user {telegram_id}: {e}")
            return False

    async def toggle_notifications(self, telegram_id: int) -> Tuple[bool, bool]:
        """
        Toggle notifications for user
        Returns (success, new_state)
        """
        try:
            user = await self.get_telegram_user(telegram_id)
            if not user:
                return False, False

            user.notification_enabled = not user.notification_enabled
            await user.asave(update_fields=['notification_enabled'])

            return True, user.notification_enabled

        except Exception as e:
            logger.error(f"Error toggling notifications for {telegram_id}: {e}")
            return False, False

    def get_handlers(self):
        """Get telegram handlers for authentication"""
        # registration_handler = ConversationHandler(
        #     entry_points=[CommandHandler('register', self.start_registration)],
        #     states={
        #         AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_email)],
        #         AWAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_username)],
        #         CONFIRM_REGISTRATION: [
        #             CallbackQueryHandler(self.handle_registration_confirm, pattern='^confirm$'),
        #             CallbackQueryHandler(self.handle_registration_cancel, pattern='^cancel$')
        #         ]
        #     },
        #     fallbacks=[CommandHandler('cancel', self.cancel_registration)],
        #     conversation_timeout=300
        # )

        return [
            # registration_handler,
            CommandHandler('start', self.cmd_start),
            CommandHandler('settings', self.cmd_settings),
            CommandHandler('profile', self.cmd_profile)
        ]

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if await self.get_telegram_user(update.effective_user.id):
            await update.message.reply_text(
                "Welcome back! Use /profile to see your details or /settings to manage notifications."
            )
        else:
            await update.message.reply_text(
                "Welcome to Crypto Trading Bot!\n\n"
                "To get started, please register using /register command."
            )

    # async def start_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Start registration process"""
    #     if await self.get_telegram_user(update.effective_user.id):
    #         await update.message.reply_text("You are already registered!")
    #         return ConversationHandler.END
    #
    #     await update.message.reply_text(
    #         "Let's get you registered!\n\n"
    #         "Please enter your email address:"
    #     )
    #     return AWAITING_EMAIL
    #
    # @staticmethod
    # async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Handle email input"""
    #     email = update.message.text.lower()
    #
    #     # Basic email validation
    #     if '@' not in email or '.' not in email:
    #         await update.message.reply_text(
    #             "Please enter a valid email address!"
    #         )
    #         return AWAITING_EMAIL
    #
    #     # Check if email exists
    #     if await User.objects.filter(email=email).aexists():
    #         await update.message.reply_text(
    #             "This email is already registered!\n"
    #             "Please use another email address:"
    #         )
    #         return AWAITING_EMAIL
    #
    #     # Store email in context
    #     context.user_data['email'] = email
    #
    #     await update.message.reply_text(
    #         "Great! Now please choose a username:"
    #     )
    #     return AWAITING_USERNAME
    #
    # @staticmethod
    # async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Handle username input"""
    #     username = update.message.text.lower()
    #
    #     # Username validation
    #     if len(username) < 3:
    #         await update.message.reply_text(
    #             "Username must be at least 3 characters long!\n"
    #             "Please choose another username:"
    #         )
    #         return AWAITING_USERNAME
    #
    #     # Check if username exists
    #     if await User.objects.filter(username=username).aexists():
    #         await update.message.reply_text(
    #             "This username is already taken!\n"
    #             "Please choose another username:"
    #         )
    #         return AWAITING_USERNAME
    #
    #     # Store username in context
    #     context.user_data['username'] = username
    #
    #     # Create confirmation keyboard
    #     keyboard = [
    #         [
    #             InlineKeyboardButton("Confirm", callback_data="confirm"),
    #             InlineKeyboardButton("Cancel", callback_data="cancel")
    #         ]
    #     ]
    #     reply_markup = InlineKeyboardMarkup(keyboard)
    #
    #     await update.message.reply_text(
    #         f"Please confirm your registration details:\n\n"
    #         f"Email: {context.user_data['email']}\n"
    #         f"Username: {username}\n\n"
    #         f"Is this correct?",
    #         reply_markup=reply_markup
    #     )
    #     return CONFIRM_REGISTRATION
    #
    # async def handle_registration_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Handle registration confirmation"""
    #     query = update.callback_query
    #     await query.answer()
    #
    #     try:
    #         # Generate random password
    #         password = str(uuid.uuid4())
    #
    #         # Create user
    #         user = await sync_to_async(User.objects.create_user)(
    #             username=context.user_data['username'],
    #             email=context.user_data['email'],
    #             password=password
    #         )
    #
    #         # Create telegram user
    #         telegram_user = await TelegramUser.objects.acreate(
    #             user=user,
    #             telegram_id=update.effective_user.id,
    #             telegram_username=update.effective_user.username,
    #             language_code=update.effective_user.language_code
    #         )
    #
    #         await query.edit_message_text(
    #             f"Registration successful! 🎉\n\n"
    #             f"Your account has been created with these credentials:\n"
    #             f"Username: {user.username}\n"
    #             f"Password: {password}\n\n"
    #             f"Please save these credentials securely!\n\n"
    #             f"You can now use /settings to manage your notifications."
    #         )
    #
    #         # Send welcome message
    #         await self.send_welcome_message(telegram_user)
    #
    #     except Exception as e:
    #         logger.error(f"Registration error: {e}")
    #         await query.edit_message_text(
    #             "Sorry, there was an error during registration.\n"
    #             "Please try again later using /register command."
    #         )
    #
    #     return ConversationHandler.END
    #
    # @staticmethod
    # async def handle_registration_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Handle registration cancellation"""
    #     query = update.callback_query
    #     await query.answer()
    #
    #     await query.edit_message_text(
    #         "Registration cancelled.\n"
    #         "You can start again using /register command."
    #     )
    #     return ConversationHandler.END
    #
    # @staticmethod
    # async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Cancel registration process"""
    #     await update.message.reply_text(
    #         "Registration cancelled.\n"
    #         "You can start again using /register command."
    #     )
    #     return ConversationHandler.END

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        telegram_user = await self.get_telegram_user(update.effective_user.id)
        if not telegram_user:
            await update.message.reply_text(
                "You need to register first!\n"
                "Use /register command to get started."
            )
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔕 Disable notifications" if telegram_user.notification_enabled
                    else "🔔 Enable notifications",
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Deactivate account",
                    callback_data="deactivate_account"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Settings:\n\n"
            f"Notifications: {'Enabled ✅' if telegram_user.notification_enabled else 'Disabled ❌'}\n"
            f"Account status: {'Active ✅' if telegram_user.is_active else 'Inactive ❌'}",
            reply_markup=reply_markup
        )

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /profile command"""
        telegram_user = await self.get_telegram_user(update.effective_user.id)
        if not telegram_user:
            await update.message.reply_text(
                "You need to register first!\n"
            )
            return

        user = telegram_user.user
        await update.message.reply_text(
            f"Your Profile:\n\n"
            f"Username: {user.username}\n"
            f"Email: {user.email}\n"
            f"Registered: {telegram_user.registration_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Notifications: {'Enabled ✅' if telegram_user.notification_enabled else 'Disabled ❌'}\n"
            f"Status: {'Active ✅' if telegram_user.is_active else 'Inactive ❌'}"
        )

    @staticmethod
    async def send_welcome_message(telegram_user: TelegramUser):
        """Send welcome message to new user"""
        from .notification import NotificationService
        notification = NotificationService()

        await notification.send_message(
            telegram_user.telegram_id,
            f"Welcome to Crypto Trading Bot! 🚀\n\n"
            f"Your account is now set up and ready to go.\n\n"
            f"Available commands:\n"
            f"/profile - View your profile\n"
            f"/settings - Manage notifications\n"
            f"/help - Show all available commands\n\n"
            f"You will receive notifications about:\n"
            f"• New token listings\n"
            f"• Trading opportunities\n"
            f"• Your trade executions\n"
            f"• Important system updates\n\n"
            f"Happy trading! 📈"
        )
