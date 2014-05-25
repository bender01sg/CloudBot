import re
from datetime import datetime

from sqlalchemy import Table, Column, String, Boolean, DateTime
from sqlalchemy.sql import select

from cloudbot import hook, timesince, botvars

table = Table(
    'tells',
    botvars.metadata,
    Column('connection', String),
    Column('sender', String),
    Column('target', String),
    Column('message', String),
    Column('is_read', Boolean),
    Column('time_sent', DateTime),
    Column('time_read', DateTime)
)


def get_unread(db, server, target):
    query = select([table.c.sender, table.c.message, table.c.time_sent]) \
        .where(table.c.connection == server) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .order_by(table.c.time_sent)
    return db.execute(query).fetchall()


def count_unread(db, server, target):
    query = select([table]) \
        .where(table.c.connection == server) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .count()
    return db.execute(query).fetchone()[0]


def read_all_tells(db, server, target):
    query = table.update() \
        .where(table.c.connection == server) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .values(is_read=1)
    db.execute(query)
    db.commit()


def read_tell(db, server, target, message):
    query = table.update() \
        .where(table.c.connection == server) \
        .where(table.c.target == target.lower()) \
        .where(table.c.message == message) \
        .values(is_read=1)
    db.execute(query)
    db.commit()


def add_tell(db, server, sender, target, message):
    query = table.insert().values(
        connection=server,
        sender=sender,
        target=target,
        message=message,
        is_read=False,
        time_sent=datetime.today()
    )
    db.execute(query)
    db.commit()


@hook.event('PRIVMSG', singlethread=True)
def tellinput(event, notice, db, nick, conn):
    if 'showtells' in event.irc_message.lower():
        return

    tells = get_unread(db, conn.server, nick)

    if tells:
        user_from, message, time_sent = tells[0]
        reltime = timesince.timesince(time_sent)

        reply = "{} sent you a message {} ago: {}".format(user_from, reltime, message)
        if len(tells) > 1:
            reply += " (+{} more, {}showtells to view)".format(len(tells) - 1, conn.config["command_prefix"])

        read_tell(db, conn.server, nick, message)
        notice(reply)


@hook.command(autohelp=False)
def showtells(nick, notice, db, conn):
    """showtells -- View all pending tell messages (sent in a notice)."""

    tells = get_unread(db, conn.server, nick)

    if not tells:
        notice("You have no pending messages.")
        return

    for tell in tells:
        sender, message, time_sent = tell
        past = timesince.timesince(time_sent)
        notice("{} sent you a message {} ago: {}".format(sender, past, message))

    read_all_tells(db, conn.server, nick)


@hook.command("tell")
def tell_cmd(inp, nick, db, notice, conn):
    """tell <nick> <message> -- Relay <message> to <nick> when <nick> is around."""
    query = inp.split(' ', 1)

    if len(query) != 2:
        notice(conn.config("command_prefix") + tell_cmd.__doc__)
        return

    target = query[0].lower()
    message = query[1].strip()
    sender = nick

    if target == sender.lower():
        notice("Have you looked in a mirror lately?")
        return

    if target.lower() == conn.nick.lower():
        # we can't send messages to ourselves
        notice("Invalid nick '{}'.".format(target))
        return

    if not re.match("^[A-Za-z0-9_|.\-\]\[]*$", target.lower()):
        notice("Invalid nick '{}'.".format(target))

    if count_unread(db, conn.server, target) >= 10:
        notice("Sorry, {} has too many messages queued already.".format(target))
        return

    add_tell(db, conn.server, sender, target, message)

    notice("Your message has been saved, and {} will be notified once they are active.".format(target))