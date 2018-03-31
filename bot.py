#!/usr/bin/env python3

import json
import logging
import re
import urllib.request
from math import asin, cos, floor, radians, sin, sqrt

from bs4 import BeautifulSoup
from telegram import ParseMode
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater

logging.basicConfig(level=logging.INFO,
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


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(
        radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers. Use 3956 for miles
    return c * r


def get_nearest(longitude, latitude):
    nearest_stop = {
        "stop": stops[0],
        "distance": haversine(stops[0]["longitude"], stops[0]["latitude"], longitude, latitude)
    }
    for stop in stops:
        new_distance = haversine(
            stop["longitude"], stop["latitude"], longitude, latitude)
        if new_distance < nearest_stop["distance"]:
            nearest_stop["stop"] = stop
            nearest_stop["distance"] = new_distance
    return nearest_stop["stop"], nearest_stop["distance"]


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
    message = "Fermata più vicina : \n"
    stop, distance = get_nearest(update.message.location.longitude,
                                 update.message.location.latitude)
    message += "Nome : " + stop["name"] + "\n"
    message += "Codice : " + stop["code"] + "\n"
    message += "Distanza : " + str(floor(distance * 1000)) + " metri\n"
    bot.send_message(chat_id=update.message.chat_id,
                     text=message)


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="""Ricevi informazioni sulle fermate degli autobus AMT a Genova.\n
Basta semplicemente mandare il codice della fermata e riceverai la lista delle prossime fermate.""")


key = open("key.txt", "r").read().strip()
updater = Updater(key)

updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(MessageHandler(Filters.text, handle_code))
updater.dispatcher.add_handler(
    MessageHandler(Filters.location, handle_location))

updater.start_polling()
updater.idle()
