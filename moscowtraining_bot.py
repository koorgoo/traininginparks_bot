# -*- coding: utf-8 -*-

from __future__ import unicode_literals, print_function

import json
import logging
import os
import time

import pymongo
import telegram
from telegram.contrib.botan import Botan
from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram.ext import Updater

from google_calendar import dump_calendar, dump_mongodb, get_events

# Set up Updater and Dispatcher

updater = Updater(token=os.environ['TOKEN'])
updater.stop()
dispatcher = updater.dispatcher

# Set up Botan

botan = Botan(os.environ['BOTAN_API_KEY'])

# Add logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)


def botan_track(message, update):
    """
    Call Bota API and send info
    :param message: message that was send to User
    :param update: telegram API state 
    :return: N/A
    """

    message_dict = message.to_dict()
    event_name = update.message.text
    botan.track(message_dict, event_name)


def start(bot, update):
    """
    Send welcome message to new users. 
    :return: N/A
    """

    # bot.sendMessage(chat_id=update.message.chat_id, text=os.environ['WELCOMETEXT'])

    botan_track(update.message, update)
    kb = [[telegram.KeyboardButton('/train')],
          [telegram.KeyboardButton('/attendees')]]
    kb_markup = telegram.ReplyKeyboardMarkup(kb)
    bot.send_message(chat_id=update.message.chat_id,
                     text="Добро пожаловать, атлет!",
                     reply_markup=kb_markup,
                     resize_keyboard=True)


def attendees(bot, update):
    """
    Count number of attendees for each planned event and share with User
    :param bot: telegram API object
    :param update: telegram API state
    :return: N/A
    """

    bot.sendMessage(chat_id=update.message.chat_id,
                    text="Список людей, записавшихся на предстоящие тренировки:")
    events = get_events(5)
    if events:
        for event in events:
            if "attendee" in event.keys():
                attendees_list = ''
                for attendee in event["attendee"]:
                    attendees_list = attendees_list + ' @' + attendee
                bot.sendMessage(chat_id=update.message.chat_id,
                                text="{}: {} ({}) - {}".format(event["start"]["dateTime"].split("T")[0],
                                                               event["summary"],
                                                               len(event["attendee"]), attendees_list))
            else:
                bot.sendMessage(chat_id=update.message.chat_id,
                                text="{}: {} ({}) - {}".format(event["start"]["dateTime"].split("T")[0],
                                                               event["summary"],
                                                               0, 'пока никто не записался'))
        botan_track(update.message, update)
    else:
        bot.sendMessage(chat_id=update.message.chat_id, text="Нет трениировок, нет и записавшихся")


def reply(bot, update, text):
    """
    Reply to User and calls Botan API
    :param bot: telegram API object
    :param update: telegram API state
    :param text: message that was send to User
    :return: N/A
    """

    # TODO: не найден chat_id
    bot.sendMessage(chat_id=update.message.chat_id, text=text)
    botan_track(update.message, update)


def train(bot, update, num):
    """
    Get a NUM of upcoming events and offer to attend any
    :param bot: telegram API object
    :param update: telegram API state
    :param num: number of upcoming events to retieve
    :return: N/A
    """

    events = get_events(num)
    if events:
        reply(bot, update, text="Расписание следующих тренировок:")
        botan_track(update.message, update)
        for event in events:
            reply(bot, update,
                  text="{}: {} с {} до {}".format(event["start"]["dateTime"].split("T")[0], event["summary"],
                                                  event["start"]["dateTime"].split("T")[1][:5],
                                                  event["end"]["dateTime"].split("T")[1][:5]))
            botan_track(update.message, update)
        kb_markup = event_keyboard(bot, update, events)
        update.message.reply_text('Давай запишемся на одну из тренировок:', reply_markup=kb_markup)
    else:
        reply(bot, update, text="Пока тренировки не запланированы. Восстанавливаемся!")
        botan_track(update.message, update)


def event_keyboard(bot, update, events):
    """
    Create keyboard markup that can be shown to User
    :param bot: telegram API object
    :param update: telegram API state
    :param events: list of events
    :return: keyboard markup that can be shown to User
    """

    kb = []
    for event in events:
        text = "{}: {}".format(event["summary"], event["start"]["dateTime"].split("T")[0])
        item = telegram.InlineKeyboardButton(text=text, callback_data=event["id"])
        kb.append([item])
    kb_markup = telegram.inlinekeyboardmarkup.InlineKeyboardMarkup(kb)
    return kb_markup


def train_button(bot, update):
    """
    Get a User selected event from call back, add User to attendees list for the event
    and gives User info about selected event (date, time, location)
    :param bot: telegram API object
    :param update: telegram API state
    :return: N/A
    """

    query = update.callback_query
    connection = pymongo.MongoClient(os.environ['MONGODB_URI'])
    db = connection["heroku_r261ww1k"]
    if db.events.find({"id": query.data, "attendee": query.message.chat.username}).count() == 0:
        event = db.events.find_one({"id": query.data})
        db.events.update({"id": query.data}, {"$push": {"attendee": query.message.chat.username}}, upsert=True)
        bot.sendMessage(text="Отлично, записались!", chat_id=query.message.chat_id, message_id=query.message.message_id)
        if "dozen" in event["summary"].lower():
            bot.sendMessage(text="Ждем тебя {} с {} по адресу:".format(event["start"]["dateTime"].split("T")[0],
                                                                       event["start"]["dateTime"].split("T")[1][:5]),
                            chat_id=query.message.chat_id, message_id=query.message.message_id)
            dozen_loc(bot, query)
        elif "нескучный" in event["summary"].lower():
            bot.sendMessage(text="Ждем тебя {} с {} по адресу:".format(event["start"]["dateTime"].split("T")[0],
                                                                       event["start"]["dateTime"].split("T")[1][:5]),
                            chat_id=query.message.chat_id, message_id=query.message.message_id)
            sad_loc(bot, query)
    else:
        bot.sendMessage(text="Ты уже записан(а) на эту тренировку", chat_id=query.message.chat_id,
                        message_id=query.message.message_id)
    connection.close()


def dozen_loc(bot, update):
    """
    Send User CrossFit Dozen location on map
    :param bot: telegram API object
    :param update: telegram API state
    :return: N/A
    """

    dozen = json.loads(os.environ['DOZEN'])
    bot.send_venue(chat_id=update.message.chat_id, latitude=dozen["latitude"],
                   longitude=dozen["longitude"], title=dozen["title"], address=dozen["address"])


def sad_loc(bot, update):
    """
    Send User Neskuchniy Sad location on map
    :param bot: telegram API object
    :param update: telegram API state
    :return: N/A
    """

    sad = json.loads(os.environ['SAD'])
    bot.send_venue(chat_id=update.message.chat_id, latitude=sad["latitude"],
                   longitude=sad["longitude"], title=sad["title"], address=sad["address"])


def main():
    # Set up handlers and buttons

    start_handler = CommandHandler("start", start)
    dispatcher.add_handler(start_handler)

    train_handler = CommandHandler("train", train(num=5))
    dispatcher.add_handler(train_handler)

    train_handler = CommandHandler("attendees", attendees)
    dispatcher.add_handler(train_handler)

    updater.dispatcher.add_handler(CallbackQueryHandler(train_button))

    # Poll user actions

    updater.start_polling()

    # Update 10 events from calendar every 60 secs

    starttime = time.time()
    while True:
        events = dump_calendar(10)
        dump_mongodb(events)
        time.sleep(60.0 - ((time.time() - starttime) % 60.0))


if __name__ == '__main__':
    main()
