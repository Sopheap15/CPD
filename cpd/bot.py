"""Telegram bot: application assembly, conversation wiring and background jobs."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from cpd.constants import (
    MENU,
    NAME,
    PICKUP_COURSE,
    PICKUP_NAME,
    PICKUP_PICKER,
    PICKUP_WHO,
    REG_COURSE,
    REG_IDENTITY,
    REG_LICENSE,
    REG_LOCATION,
    REG_NAME,
    REG_PAYMENT,
    REG_RECEIPT,
    REG_PHONE,
    START_OPTIONS,
)
from cpd.handlers.admin import (
    cmd_admin,
    cmd_admin_confirm,
    cmd_admin_group,
    cmd_admin_group_clear,
    cmd_admin_group_rename,
    cmd_admin_groups,
    cmd_admin_kick,
    cmd_admin_link,
    cmd_admin_list,
    cmd_admin_reg_clear,
    cmd_admin_reg_del,
    cmd_admin_regs,
    cmd_admin_setup,
    cmd_admin_unlink,
    cmd_admin_view,
)
from cpd.handlers.history import on_menu, on_name, on_pick, on_alert_view, cmd_view
from cpd.handlers.pickup import (
    on_pickup_course,
    on_pickup_name,
    on_pickup_picker,
    on_pickup_who,
)
from cpd.handlers.registration import (
    finalize_paid_registration,
    on_pay_cancel,
    on_pay_check,
    on_receipt_photo,
    on_reg_course,
    on_reg_identity,
    on_reg_license,
    on_reg_location,
    on_reg_name,
    on_reg_phone,
)
from cpd.handlers.start import cmd_start, on_start_option

logger = logging.getLogger(__name__)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    from cpd.handlers.common import safe_reply_html
    from cpd.i18n import t
    context.user_data.pop("name", None)
    await safe_reply_html(update, t("cancel"))
    return ConversationHandler.END


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user their own Telegram ID."""
    from cpd.handlers.common import safe_reply_html
    from cpd.i18n import fmt
    await safe_reply_html(update, fmt("your_telegram_id", tid=update.effective_user.id))


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Unlink the current Telegram account from its participant record."""
    from cpd.handlers.common import safe_reply_html
    from cpd.i18n import t
    from cpd.services.storage import get_linked_name, unlink_account
    name = get_linked_name(update.effective_user.id)
    if not name:
        await safe_reply_html(update, t("not_linked"))
        return ConversationHandler.END
    unlink_account(update.effective_user.id)
    context.user_data.pop("name", None)
    await safe_reply_html(update, t("account_unlinked"))
    return ConversationHandler.END


async def _register_commands(app: Application) -> None:
    """Publish the bot's command menu (the / button in Telegram chats)."""
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Start / restart the bot"),
        BotCommand("view", "View your CPD history"),
        BotCommand("myid", "Show your Telegram ID"),
        BotCommand("unlink", "Unlink your account"),
        BotCommand("cancel", "Cancel current action"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception:  # noqa: BLE001 - non-fatal (network/Telegram hiccup)
        logger.warning("Failed to register command menu: %r",
                       "set_my_commands failed")


def build_application() -> Application:
    import os

    from cpd.config import (
        TELEGRAM_API_BASE_URL,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CONNECT_TIMEOUT,
        TELEGRAM_PROXY,
        TELEGRAM_READ_TIMEOUT,
    )

    if TELEGRAM_PROXY:
        # httpx (used by python-telegram-bot) honours these environment
        # variables, letting us route Telegram traffic through a proxy when
        # the API is unreachable.
        os.environ.setdefault("HTTPS_PROXY", TELEGRAM_PROXY)
        os.environ.setdefault("HTTP_PROXY", TELEGRAM_PROXY)

    shared_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_name),
        CommandHandler("start", cmd_start),
        CommandHandler("view", cmd_view),
        CommandHandler("cancel", cmd_cancel),
        CallbackQueryHandler(on_pick, pattern=r"^pick\|"),
        CallbackQueryHandler(on_alert_view, pattern=r"^alert\|view\|"),
        CallbackQueryHandler(on_start_option, pattern=r"^start\|"),
        CallbackQueryHandler(on_menu, pattern=r"^menu\|"),
    ]

    reg_course_handlers = [
        CallbackQueryHandler(on_reg_course, pattern=r"^reg\|"),
        CallbackQueryHandler(on_start_option, pattern=r"^start\|"),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_identity_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_reg_identity),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_text_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_reg_license),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_name_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_reg_name),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_phone_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_reg_phone),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_location_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_reg_location),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_payment_handlers = [
        CallbackQueryHandler(on_pay_check, pattern=r"^pay\|check"),
        CallbackQueryHandler(on_pay_cancel, pattern=r"^pay\|cancel"),
        CommandHandler("cancel", cmd_cancel),
    ]
    reg_receipt_handlers = [
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_receipt_photo),
        MessageHandler(filters.ALL & ~filters.COMMAND, on_receipt_photo), # Catch text/files to show error
        CallbackQueryHandler(on_pay_cancel, pattern=r"^pay\|cancel"),
        CommandHandler("cancel", cmd_cancel),
    ]

    pickup_name_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_pickup_name),
        CommandHandler("cancel", cmd_cancel),
    ]
    pickup_who_handlers = [
        CallbackQueryHandler(on_pickup_who, pattern=r"^pickup\|"),
        CommandHandler("cancel", cmd_cancel),
    ]
    pickup_picker_handlers = [
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_pickup_picker),
        CommandHandler("cancel", cmd_cancel),
    ]
    pickup_course_handlers = [
        CallbackQueryHandler(on_pickup_course, pattern=r"^pickup\|(course\||confirm|cancel)"),
        CommandHandler("cancel", cmd_cancel),
    ]

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("view", cmd_view),
        ],
        states={
            START_OPTIONS: shared_handlers,
            NAME: shared_handlers,
            MENU: shared_handlers,
            REG_IDENTITY: reg_identity_handlers,
            REG_COURSE: reg_course_handlers,
            REG_LICENSE: reg_text_handlers,
            REG_NAME: reg_name_handlers,
            REG_PHONE: reg_phone_handlers,
            REG_LOCATION: reg_location_handlers,
            REG_PAYMENT: reg_payment_handlers,
            REG_RECEIPT: reg_receipt_handlers,
            PICKUP_NAME: pickup_name_handlers,
            PICKUP_WHO: pickup_who_handlers,
            PICKUP_PICKER: pickup_picker_handlers,
            PICKUP_COURSE: pickup_course_handlers,
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start", cmd_start),
        ],
    )

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if TELEGRAM_API_BASE_URL:
        builder = builder.base_url(TELEGRAM_API_BASE_URL)
        # base_url() does NOT derive the file URL - without this, file
        # downloads (receipt photos) go straight to api.telegram.org and
        # fail with ConnectError when that host is blocked.
        builder = builder.base_file_url(
            TELEGRAM_API_BASE_URL.replace("/bot", "/file/bot")
        )
    builder.post_init(_register_commands)
    application = (
        builder
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_READ_TIMEOUT)
        .pool_timeout(TELEGRAM_READ_TIMEOUT)
        .build()
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("unlink", cmd_unlink))
    application.add_handler(CommandHandler("admin_list", cmd_admin_list))
    application.add_handler(CommandHandler("admin_link", cmd_admin_link))
    application.add_handler(CommandHandler("admin_unlink", cmd_admin_unlink))
    application.add_handler(CommandHandler("admin_view", cmd_admin_view))
    application.add_handler(CommandHandler("admin_group", cmd_admin_group))
    application.add_handler(CommandHandler("admin_group_clear", cmd_admin_group_clear))
    application.add_handler(CommandHandler("admin_setup", cmd_admin_setup))
    application.add_handler(CommandHandler("admin_regs", cmd_admin_regs))
    application.add_handler(CommandHandler("admin_confirm", cmd_admin_confirm))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CommandHandler("admin_groups", cmd_admin_groups))
    application.add_handler(CommandHandler("admin_group_rename", cmd_admin_group_rename))
    application.add_handler(CommandHandler("admin_reg_del", cmd_admin_reg_del))
    application.add_handler(CommandHandler("admin_reg_clear", cmd_admin_reg_clear))
    application.add_handler(CommandHandler("admin_kick", cmd_admin_kick))
    application.add_error_handler(_error_handler)

    return application
async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error (update=%s): %s",
                 type(update).__name__, context.error, exc_info=context.error)


def main() -> None:
    import warnings

    warnings.filterwarnings(
        "ignore",
        message="If 'per_message=False'.*",
    )

    from cpd.config import TELEGRAM_BOT_TOKEN, validate

    validate()

    class _ScrubFormatter(logging.Formatter):
        """Never let the bot token leak into any log line."""

        def __init__(self, fmt: str | None = None, secrets: tuple[str, ...] = ()):
            super().__init__(fmt=fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            self.secrets = tuple(s for s in secrets if s)

        def format(self, record: logging.LogRecord) -> str:
            text = super().format(record)
            for secret in self.secrets:
                text = text.replace(secret, "<redacted>")
            return text

    _handler = logging.StreamHandler()
    _handler.setFormatter(_ScrubFormatter(secrets=(TELEGRAM_BOT_TOKEN,)))
    logging.basicConfig(level=logging.INFO, handlers=[_handler])

    # httpx logs the full request URL (which embeds the token) at INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    for name in ("urllib3", "http.client"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logger.info("Starting CPD Track bot (polling)…")
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()