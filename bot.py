"""
Telegram Group Management Bot
==============================
Ek full-featured group management bot — moderation, welcome messages,
aur owner-defined custom commands sab ek jagah.

Setup: README.md dekho.
"""

import logging
import sqlite3
from datetime import timedelta

from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN = "8652908353:AAEf-uYfvz8CcCskO-gcUyKiG_NMx-tN6pc"  # @BotFather se milega
DB_PATH = "bot_data.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS custom_commands (
            chat_id INTEGER, name TEXT, response TEXT,
            PRIMARY KEY (chat_id, name)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY, welcome TEXT, rules TEXT
        )"""
    )
    return conn


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    member = await context.bot.get_chat_member(
        update.effective_chat.id, update.effective_user.id
    )
    return member.status in ("administrator", "creator")


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ Yeh command sirf group admins use kar sakte hain.")
        return False
    return True


def get_target_user(update: Update):
    """Reply karke command use karne par target user return karta hai."""
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None


# ---------------------------------------------------------------------------
# Basic commands
# ---------------------------------------------------------------------------


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Namaste! Main is group ka management bot hoon.\n"
        "Sab commands dekhne ke liye /help bhejo."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*🤖 Bot Commands*\n\n"
        "*General*\n"
        "/start – Bot shuru karo\n"
        "/help – Yeh message\n"
        "/id – Apna ya reply kiye user ka ID dikhao\n"
        "/rules – Group rules dekho\n"
        "/cmds – Custom commands ki list\n\n"
        "*Moderation* _(admins only, reply karke use karo)_\n"
        "/warn – User ko warning do (3 warnings = auto-ban)\n"
        "/warnings – Warning count dekho\n"
        "/unwarn – Last warning hatao\n"
        "/mute [minutes] – User ko mute karo\n"
        "/unmute – User ko unmute karo\n"
        "/kick – User ko group se nikaalo\n"
        "/ban – User ko ban karo\n"
        "/unban – User ko unban karo (reply ya user_id se)\n"
        "/pin – Message pin karo\n"
        "/unpin – Message unpin karo\n"
        "/purge – Reply se ab tak ke messages delete karo\n\n"
        "*Settings* _(admins only)_\n"
        "/setwelcome <text> – Welcome message set karo ({name}, {group} use kar sakte ho)\n"
        "/setrules <text> – Group rules set karo\n"
        "/addcmd <name> <response> – Naya custom command banao\n"
        "/delcmd <name> – Custom command hatao"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = get_target_user(update) or update.effective_user
    await update.message.reply_text(
        f"👤 Name: {target.full_name}\n🆔 ID: `{target.id}`", parse_mode=ParseMode.MARKDOWN
    )


# ---------------------------------------------------------------------------
# Welcome new members
# ---------------------------------------------------------------------------


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    row = conn.execute(
        "SELECT welcome FROM settings WHERE chat_id=?", (update.effective_chat.id,)
    ).fetchone()
    conn.close()

    template = row[0] if row and row[0] else "Welcome {name} to {group}! 🎉"

    for member in update.message.new_chat_members:
        text = template.replace("{name}", member.full_name).replace(
            "{group}", update.effective_chat.title or "the group"
        )
        await update.message.reply_text(text)


async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /setwelcome <message>\nTip: {name} aur {group} placeholders use kar sakte ho."
        )
        return
    text = " ".join(context.args)
    conn = db()
    conn.execute(
        "INSERT INTO settings (chat_id, welcome) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET welcome=excluded.welcome",
        (update.effective_chat.id, text),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Welcome message set ho gaya!")


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /setrules <rules text>")
        return
    text = " ".join(context.args)
    conn = db()
    conn.execute(
        "INSERT INTO settings (chat_id, rules) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET rules=excluded.rules",
        (update.effective_chat.id, text),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Rules set ho gaye!")


async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    row = conn.execute(
        "SELECT rules FROM settings WHERE chat_id=?", (update.effective_chat.id,)
    ).fetchone()
    conn.close()
    if row and row[0]:
        await update.message.reply_text(f"📜 *Group Rules*\n\n{row[0]}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Is group ke liye abhi tak koi rules set nahi hain.")


# ---------------------------------------------------------------------------
# Moderation: warn / unwarn / warnings
# ---------------------------------------------------------------------------


async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /warn use karo.")
        return

    conn = db()
    conn.execute(
        "INSERT INTO warnings (chat_id, user_id, count) VALUES (?, ?, 1) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1",
        (update.effective_chat.id, target.id),
    )
    count = conn.execute(
        "SELECT count FROM warnings WHERE chat_id=? AND user_id=?",
        (update.effective_chat.id, target.id),
    ).fetchone()[0]
    conn.commit()
    conn.close()

    if count >= 3:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(
            f"🚫 {target.full_name} ko 3 warnings ke baad ban kar diya gaya."
        )
    else:
        await update.message.reply_text(
            f"⚠️ {target.full_name} ko warning di gayi ({count}/3)."
        )


async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /unwarn use karo.")
        return

    conn = db()
    conn.execute(
        "UPDATE warnings SET count = MAX(count - 1, 0) WHERE chat_id=? AND user_id=?",
        (update.effective_chat.id, target.id),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ {target.full_name} ki ek warning hata di gayi.")


async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = get_target_user(update) or update.effective_user
    conn = db()
    row = conn.execute(
        "SELECT count FROM warnings WHERE chat_id=? AND user_id=?",
        (update.effective_chat.id, target.id),
    ).fetchone()
    conn.close()
    count = row[0] if row else 0
    await update.message.reply_text(f"⚠️ {target.full_name} ke paas {count}/3 warnings hain.")


# ---------------------------------------------------------------------------
# Moderation: ban / kick / mute
# ---------------------------------------------------------------------------


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /ban use karo.")
        return
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await update.message.reply_text(f"🚫 {target.full_name} ko ban kar diya gaya.")


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    user_id = target.id if target else (int(context.args[0]) if context.args else None)
    if not user_id:
        await update.message.reply_text("Usage: reply karke /unban, ya /unban <user_id>")
        return
    await context.bot.unban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("✅ User unban ho gaya.")


async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /kick use karo.")
        return
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await context.bot.unban_chat_member(update.effective_chat.id, target.id)
    await update.message.reply_text(f"👢 {target.full_name} ko group se nikaal diya gaya.")


async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /mute [minutes] use karo.")
        return

    minutes = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    kwargs = {"permissions": ChatPermissions(can_send_messages=False)}
    if minutes:
        kwargs["until_date"] = timedelta(minutes=minutes)

    await context.bot.restrict_chat_member(update.effective_chat.id, target.id, **kwargs)
    duration_text = f" {minutes} minute ke liye" if minutes else ""
    await update.message.reply_text(f"🔇 {target.full_name} ko{duration_text} mute kar diya gaya.")


async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /unmute use karo.")
        return
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )
    await update.message.reply_text(f"🔊 {target.full_name} ko unmute kar diya gaya.")


# ---------------------------------------------------------------------------
# Pin / Unpin / Purge
# ---------------------------------------------------------------------------


async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Jis message ko pin karna hai, uspe reply karo.")
        return
    await context.bot.pin_chat_message(
        update.effective_chat.id, update.message.reply_to_message.message_id
    )
    await update.message.reply_text("📌 Message pin kar diya gaya.")


async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    await context.bot.unpin_chat_message(update.effective_chat.id)
    await update.message.reply_text("📍 Message unpin kar diya gaya.")


async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Jahan se purge shuru karna hai, uss message pe reply karo.")
        return

    start_id = update.message.reply_to_message.message_id
    end_id = update.message.message_id
    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(update.effective_chat.id, msg_id)
            deleted += 1
        except Exception:
            pass
    logger.info(f"Purged {deleted} messages in chat {update.effective_chat.id}")


# ---------------------------------------------------------------------------
# Custom commands
# ---------------------------------------------------------------------------


async def addcmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addcmd <name> <response text>")
        return
    name = context.args[0].lower().lstrip("/")
    response = " ".join(context.args[1:])
    conn = db()
    conn.execute(
        "INSERT INTO custom_commands (chat_id, name, response) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, name) DO UPDATE SET response=excluded.response",
        (update.effective_chat.id, name, response),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Custom command /{name} ban gaya!")


async def delcmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /delcmd <name>")
        return
    name = context.args[0].lower().lstrip("/")
    conn = db()
    conn.execute(
        "DELETE FROM custom_commands WHERE chat_id=? AND name=?",
        (update.effective_chat.id, name),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ Custom command /{name} hata diya gaya.")


async def cmds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    rows = conn.execute(
        "SELECT name FROM custom_commands WHERE chat_id=?", (update.effective_chat.id,)
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Is group mein abhi koi custom command nahi hai.")
        return
    names = ", ".join(f"/{r[0]}" for r in rows)
    await update.message.reply_text(f"📋 Custom commands: {names}")


async def handle_possible_custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agar message koi unknown /command hai, custom_commands table check karo."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text.startswith("/"):
        return
    name = text[1:].split()[0].split("@")[0].lower()

    conn = db()
    row = conn.execute(
        "SELECT response FROM custom_commands WHERE chat_id=? AND name=?",
        (update.effective_chat.id, name),
    ).fetchone()
    conn.close()
    if row:
        await update.message.reply_text(row[0])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # General
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("setrules", setrules_cmd))
    app.add_handler(CommandHandler("cmds", cmds_cmd))

    # Welcome
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # Warnings
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("unwarn", unwarn_cmd))
    app.add_handler(CommandHandler("warnings", warnings_cmd))

    # Moderation
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("unpin", unpin_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))

    # Custom commands
    app.add_handler(CommandHandler("addcmd", addcmd_cmd))
    app.add_handler(CommandHandler("delcmd", delcmd_cmd))

    # Catch-all: unknown /command -> check custom commands table
    app.add_handler(MessageHandler(filters.COMMAND, handle_possible_custom_command))

    logger.info("Bot shuru ho raha hai...")
    app.run_polling()


if __name__ == "__main__":
    main()
  
