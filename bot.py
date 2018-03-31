#!/usr/bin/env python3

import logging
import json
import re
import urllib.request
import math

from bs4 import BeautifulSoup
from telegram import ParseMode
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

url = 'http://www.amt.genova.it/amt/servizi/passaggi_i.php?CodiceFermata='

stops = json.load(open('stops.json'))


# Download the AMT page
def download(code):
    with urllib.request.urlopen(url + code) as response:
        return response.read()


# Parse the HTML in a JSON object
def parse(html):
    soup = BeautifulSoup(html, "lxml")

    font = soup.find_all('font')[1].text
    tds = soup.find_all('td')

    json_message = {
        "name": font,
        "stops": []
    }

    for x in range(0, len(tds), 4):
        stop = {
            "line": tds[x + 0].text,
            "dest": tds[x + 1].text,
            "time": tds[x + 2].text,
            "eta": tds[x + 3].text,
        }
        json_message["stops"].append(stop)

    return json_message


# Create a nice message from the JSON object
def beautify(json):
    if len(json["stops"]) == 0:
        return "Nessun transito", None

    message = "`"
    message += "Fermata          : " + json["name"] + "\n\n"
    for stop in json["stops"]:
        message += "Numero Autobus   : " + stop["line"] + "\n"
        message += "Direzione        : " + stop["dest"] + "\n"
        message += "Orario di arrivo : " + stop["time"] + "\n"
        message += "Tempo rimanente  : " + stop["eta"] + "\n\n"
    message += "`"

    return message, ParseMode.MARKDOWN


def distance(x1, y1, x2, y2):
    return math.hypot(float(x2) - float(x1), float(y2) - float(y1))


def get_nearest(longitude, latitude):
    nearest_stop = {
        "stop": stops[0],
        "distance": distance(stops[0]["longitude"], stops[0]["latitude"], longitude, latitude)
    }
    for stop in stops:
        new_distance = distance(stop["longitude"], stop["latitude"], longitude, latitude)
        if new_distance < nearest_stop["distance"]:
            nearest_stop["stop"] = stop
            nearest_stop["distance"] = new_distance
    return nearest_stop["stop"]["code"]


def handle_code(bot, update):
    if not re.match(r"^\d{4}$", update.message.text):
        bot.send_message(chat_id=update.message.chat_id,
                         text="Codice non valido")
    page = download(update.message.text)
    json_message = parse(page)
    message, mode = beautify(json_message)
    bot.send_message(chat_id=update.message.chat_id,
                     text=message,
                     parse_mode=mode)


def handle_location(bot, update):
    message = "Fermata più vicina : "
    message += get_nearest(update.message.location.longitude, update.message.location.latitude)
    bot.send_message(chat_id=update.message.chat_id,
                     text=message)


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="""Ricevi informazioni sulle fermate degli autobus AMT a Genova.\n
Basta semplicemente mandare il codice della fermata e riceverai la lista delle prossime fermate.""")


key = open("key.txt", "r").read().strip()
updater = Updater(key)

updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(MessageHandler(Filters.text, handle_code))
updater.dispatcher.add_handler(MessageHandler(Filters.location, handle_location))

updater.start_polling()
updater.idle()
